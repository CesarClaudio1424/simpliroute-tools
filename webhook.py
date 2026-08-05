import requests
import time
from config import (
    API_BASE, REQUEST_TIMEOUT, CLEANUP_TIMEOUT, WEBHOOK_DELAY,
    API_SEND_WEBHOOKS, API_SEND_ROUTE_WEBHOOKS, MAX_RETRIES, RETRY_BASE_DELAY,
)

# Exclusion sigue yendo directo al middleware Likewise (sin equivalente nativo en SimpliRoute)
EXCLUSION_ENDPOINTS = {
    "Telefonica": "https://us-central1-likewizemiddleware-telefonica.cloudfunctions.net/likewize/webhook/visits/support",
    "Entel": "https://us-central1-likewizemiddleware-entel.cloudfunctions.net/likewize/webhook/visits/support",
    "Omnicanalidad": "https://us-central1-likewizemiddleware-omni.cloudfunctions.net/likewize/webhook/visits/support",
    "Biobio": "https://us-central1-likewizemiddleware-biobio.cloudfunctions.net/likewize/webhook/visits/support",
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


def obtener_visitas_fecha(token, fecha):
    headers = {"Authorization": f"Token {token}"}
    url = f"{API_BASE}/routes/visits/?planned_date={fecha}"
    visitas = []
    while url:
        resp = requests.get(url, headers=headers, timeout=CLEANUP_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            visitas.extend(data)
            url = None
        else:
            visitas.extend(data.get("results", []))
            url = data.get("next")
    return visitas


def limpiar_visitas_batch(token, visitas):
    url = f"{API_BASE}/routes/visits/"
    headers = {
        "Authorization": f"Token {token}",
        "Content-Type": "application/json",
    }
    payload = [{"id": v["id"], "title": v.get("title", ""), "address": v.get("address", ""), "route": "", "planned_date": "2020-01-01"} for v in visitas]
    try:
        resp = requests.put(url, headers=headers, json=payload, timeout=CLEANUP_TIMEOUT)
        return resp.status_code == 200, resp.status_code, resp.text
    except requests.exceptions.RequestException as e:
        return False, 0, f"Error de conexion: {str(e)}"


def enviar_webhook(url, payload):
    headers = {"Content-Type": "application/json"}
    response = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
    return response.status_code, response.text


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


def procesar_exclusion(visita_ids, url):
    payload = {"visits": [int(v) for v in visita_ids]}
    try:
        status, body = enviar_webhook(url, payload)
        time.sleep(WEBHOOK_DELAY)
        ok = status == 200 and body.strip() != ""
        return ok, status, body
    except requests.exceptions.RequestException as e:
        return False, 0, f"Error de conexion: {str(e)}"
