import requests
import time
import streamlit as st
from config import (
    API_BASE, REQUEST_TIMEOUT, CLEANUP_TIMEOUT,
    API_SEND_WEBHOOKS, API_SEND_ROUTE_WEBHOOKS, MAX_RETRIES, RETRY_BASE_DELAY,
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

# account_id real en SimpliRoute de cada cuenta Likewise (via GET /v1/accounts/me/)
ACCOUNT_IDS = {
    "Telefonica": 15289,
    "Entel": 28920,
    "Omnicanalidad": 32597,
    "Biobio": 70696,
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


def excluir_visitas_hermes(api_key, visita_ids):
    """POST a Hermes (accion exclude_visits). visita_ids = IDs de SimpliRoute ya resueltos."""
    headers = {"Authorization": f"ApiKey {api_key}", "Content-Type": "application/json"}
    payload = {"action": "exclude_visits", "ids": [int(v) for v in visita_ids]}
    try:
        resp = requests.post(HERMES_URL, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
    except requests.exceptions.RequestException as e:
        return None, 0, f"Error de conexion: {str(e)}"
    if resp.status_code != 200:
        return None, resp.status_code, resp.text[:500]
    try:
        return resp.json().get("results", []), resp.status_code, None
    except ValueError:
        return None, resp.status_code, "Respuesta no es JSON valido"


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


def _post_con_reintentos(url, headers, payload):
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                return True, ""
            if resp.status_code >= 500 and attempt < MAX_RETRIES:
                time.sleep(RETRY_BASE_DELAY * (2 ** attempt))
                continue
            return False, f"HTTP {resp.status_code}: {resp.text[:300]}"
        except requests.exceptions.RequestException as e:
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BASE_DELAY * (2 ** attempt))
                continue
            return False, f"Error de conexion: {str(e)}"
    return False, "Reintentos agotados"


def enviar_route_webhook(token_post, route_id, action):
    """Creacion/Inicio: POST /v1/mobile/send-route-webhooks (igual que Reenvio de Webhooks > Rutas)."""
    headers = {"Authorization": f"Token {token_post}", "Content-Type": "application/json"}
    payload = {"route_id": route_id, "action": action}
    return _post_con_reintentos(API_SEND_ROUTE_WEBHOOKS, headers, payload)


def obtener_planned_date(token, route_id):
    headers = {"Authorization": f"Token {token}"}
    url = f"{API_BASE}/routes/routes/{route_id}/"
    try:
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            planned_date = resp.json().get("planned_date")
            if not planned_date:
                return None, "Respuesta sin planned_date"
            return planned_date, None
        return None, f"HTTP {resp.status_code}: {resp.text[:300]}"
    except requests.exceptions.RequestException as e:
        return None, f"Error de conexion: {str(e)}"


def procesar_checkout(token_get, token_post, account_id, route_id):
    """Checkout: igual que Checkout General — POST /v1/mobile/send-webhooks con route_ids."""
    planned_date, err = obtener_planned_date(token_get, route_id)
    if err:
        return False, f"GET ruta: {err}"
    headers = {"Authorization": f"Token {token_post}", "Content-Type": "application/json"}
    payload = {"account_ids": [account_id], "planned_date": planned_date, "route_ids": [route_id]}
    return _post_con_reintentos(API_SEND_WEBHOOKS, headers, payload)
