import requests
import time
import streamlit as st
from config import (
    API_BASE, REQUEST_TIMEOUT, CLEANUP_TIMEOUT,
    MAX_RETRIES, RETRY_BASE_DELAY,
)

# Exclusion via gateway Hermes/Brightcell (el middleware Likewise viejo fue retirado)
HERMES_URL = "https://connect.simpliroute.com/brightcell/reprocess"

# nombre de la clave por cuenta en secrets [brightcell_hermes]
HERMES_KEYS = {
    "Telefonica": "telefonica",
    "Entel": "entel",
    "Omnicanalidad": "omnicanalidad",
    "Biobio": "biobio",
}


ACCOUNT_TOKENS = {
    "Telefonica": "token_telefonica",
    "Entel": "token_entel",
    "Omnicanalidad": "token_omnicanalidad",
    "Biobio": "token_biobio",
}


def obtener_hermes_api_key(cuenta):
    try:
        return st.secrets["brightcell_hermes"][HERMES_KEYS[cuenta]]
    except (KeyError, AttributeError):
        return None


def resolver_visita_por_reference(token, reference):
    """GET /v1/routes/visits/reference/{reference}/ -- IDs de SimpliRoute que coinciden (puede haber mas de uno)."""
    url = f"{API_BASE}/routes/visits/reference/{reference}/"
    headers = {"Authorization": f"Token {token}"}
    try:
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
    except requests.exceptions.RequestException as e:
        return [], f"Error de conexion: {str(e)}"
    if resp.status_code != 200:
        return [], f"HTTP {resp.status_code}: {resp.text[:300]}"
    data = resp.json()
    if isinstance(data, dict) and "results" in data:
        registros = data["results"]
    elif isinstance(data, list):
        registros = data
    elif isinstance(data, dict) and "id" in data:
        registros = [data]
    else:
        registros = []
    ids = [r["id"] for r in registros if r.get("id")]
    return ids, None


def _post_hermes(action, api_key, ids):
    """POST generico a Hermes con reintentos en 5xx. Devuelve (results, status_code, error_transporte)."""
    headers = {"Authorization": f"ApiKey {api_key}", "Content-Type": "application/json"}
    payload = {"action": action, "ids": list(ids)}
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = requests.post(HERMES_URL, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
        except requests.exceptions.RequestException as e:
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BASE_DELAY * (2 ** attempt))
                continue
            return None, 0, f"Error de conexion: {str(e)}"
        if resp.status_code == 200:
            try:
                return resp.json().get("results", []), 200, None
            except ValueError:
                return [], 200, None
        if resp.status_code >= 500 and attempt < MAX_RETRIES:
            time.sleep(RETRY_BASE_DELAY * (2 ** attempt))
            continue
        return None, resp.status_code, resp.text[:500]
    return None, 0, "Reintentos agotados"


def excluir_visitas_hermes(api_key, visita_ids):
    """POST a Hermes (accion exclude_visits). visita_ids = IDs de SimpliRoute ya resueltos."""
    return _post_hermes("exclude_visits", api_key, [int(v) for v in visita_ids])


def accion_ruta_hermes(api_key, route_id, action):
    """Creacion/Inicio/Checkout via Hermes: un POST por ruta.
    action: "create_plan" | "route_started" | "route_checkout"."""
    results, status, err = _post_hermes(action, api_key, [route_id])
    if err:
        return False, err
    if results:
        r = results[0]
        if r.get("status") == "ok":
            return True, ""
        return False, r.get("error") or f"Hermes: status {r.get('status')}"
    return True, ""


def limpiar_visitas_hermes(token, visita_ids):
    """PATCH minimo (route + planned_date) para las visitas que Hermes confirmo excluidas."""
    url = f"{API_BASE}/routes/visits/"
    headers = {"Authorization": f"Token {token}", "Content-Type": "application/json"}
    payload = [{"id": int(vid), "route": "", "planned_date": "2020-01-01"} for vid in visita_ids]
    try:
        resp = requests.patch(url, headers=headers, json=payload, timeout=CLEANUP_TIMEOUT)
        return resp.status_code == 200, resp.status_code, resp.text
    except requests.exceptions.RequestException as e:
        return False, 0, f"Error de conexion: {str(e)}"


def procesar_exclusion_hermes(token, api_key, references):
    """Resuelve cada reference a su(s) ID(s) de SimpliRoute y los excluye via Hermes.
    Devuelve (detalle_por_id, sin_resolver, ids_confirmados) -- la limpieza en SimpliRoute
    queda a cargo del llamador (solo debe aplicarse a ids_confirmados)."""
    mapa_id_reference = {}
    sin_resolver = []
    for ref in references:
        ids, err = resolver_visita_por_reference(token, ref)
        if err or not ids:
            sin_resolver.append({"reference": ref, "error": err or "No se encontraron visitas con ese reference."})
            continue
        for vid in ids:
            mapa_id_reference[vid] = ref

    if not mapa_id_reference:
        return [], sin_resolver, []

    resultados, status, err = excluir_visitas_hermes(api_key, list(mapa_id_reference.keys()))
    if err:
        detalle_err = [{"reference": ref, "id": vid, "status": "error", "error": err} for vid, ref in mapa_id_reference.items()]
        return detalle_err, sin_resolver, []

    detalle = []
    confirmados = []
    for r in resultados:
        vid = int(r["id"])
        ref = mapa_id_reference.get(vid, "?")
        if r.get("status") == "ok":
            confirmados.append(vid)
        detalle.append({"reference": ref, "id": vid, "status": r.get("status"), "error": r.get("error")})

    return detalle, sin_resolver, confirmados


