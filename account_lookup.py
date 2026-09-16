import requests
import streamlit as st
from config import API_BASE, ACCOUNT_LOOKUP_COUNTRIES, ACCOUNT_LOOKUP_TIMEOUT, RETOOL_ACCOUNT_LOOKUP_URL
from utils import render_tip

PRIMARY_COUNTRIES = [codigo for codigo, _ in ACCOUNT_LOOKUP_COUNTRIES if codigo != "OTHER"]
MIN_CHARS_AUTOBUSCAR = 2

ADMIN_PORTAL_URL = f"{API_BASE}/accounts/admin-portal/accounts/"
ADMIN_PORTAL_STATUSES = ["active", "trialing"]
ADMIN_PORTAL_PAGE_SIZE = 50
ADMIN_PORTAL_MAX_PAGES = 5
ADMIN_PORTAL_MAX_MATCHES = 25


def _run_retool_query(query_name: str, params: list):
    query_params = {str(i): valor for i, valor in enumerate(params)}
    query_params["length"] = len(params)
    body = {
        "userParams": {
            "queryParams": query_params,
            "databaseNameOverrideParams": {"length": 0},
            "databaseHostOverrideParams": {"length": 0},
            "databaseUsernameOverrideParams": {"length": 0},
            "databasePasswordOverrideParams": {"length": 0},
        },
        "password": "",
        "environment": "production",
        "queryType": "SqlQuery",
        "frontendVersion": "1",
        "releaseVersion": None,
        "includeQueryExecutionMetadata": True,
        "streamResponse": False,
    }
    response = requests.post(
        f"{RETOOL_ACCOUNT_LOOKUP_URL}/query",
        params={"queryName": query_name},
        json=body,
        timeout=ACCOUNT_LOOKUP_TIMEOUT,
    )
    response.raise_for_status()
    try:
        payload = response.json()
    except ValueError:
        raise RuntimeError(f"Retool ({query_name}) no devolvio JSON valido: {response.text[:200]}")
    return _extraer_query_data(payload, query_name)


def _extraer_query_data(payload, query_name: str) -> dict:
    """Retool devuelve el resultado en uno de dos formatos segun la version del endpoint:
    el clasico {"queryData": {columna: [valores]}}, o una lista [{"cols": [...], "data": [...]}]
    donde "data" trae los resultados partidos en varios batches (mismas columnas, filas sin
    solapar) que hay que concatenar por columna."""
    if isinstance(payload, dict) and isinstance(payload.get("queryData"), dict):
        return payload["queryData"]

    if isinstance(payload, list) and payload and isinstance(payload[0], dict) and "cols" in payload[0]:
        cols = payload[0].get("cols", [])
        batches = payload[0].get("data", [])
        combinado = {col: [] for col in cols}
        for batch in batches:
            for i, col in enumerate(cols):
                combinado[col].extend(batch[i])
        return combinado

    detalle = payload.get("queryDataError") or payload.get("error") or payload if isinstance(payload, dict) else payload
    raise RuntimeError(f"Retool ({query_name}) devolvio una respuesta inesperada: {str(detalle)[:200]}")


def buscar_cuentas(country: str) -> list[dict]:
    """Catalogo de cuentas activas/trialing de un pais (query Retool clients_by_country)."""
    data = _run_retool_query("clients_by_country", [False, PRIMARY_COUNTRIES, country])
    ids = data.get("id", [])
    names = data.get("name", [])
    countries = data.get("country", [])
    statuses = data.get("status", [])
    return [
        {"id": ids[i], "name": names[i], "country": countries[i], "status": statuses[i]}
        for i in range(len(ids))
    ]


def _get_staff_token() -> str | None:
    try:
        return st.secrets["account_lookup"]["staff_token"]
    except (KeyError, AttributeError):
        return None


def buscar_cuentas_otros(query: str) -> list[dict]:
    """Cuentas fuera de los paises principales, via API Admin Portal de SimpliRoute
    (requiere Staff Token interno — [account_lookup].staff_token en secrets)."""
    staff_token = _get_staff_token()
    if not staff_token:
        raise RuntimeError("Falta configurar [account_lookup].staff_token en secrets.")

    headers = {"Authorization": f"Token {staff_token}", "Accept": "application/json"}
    matches: dict[int, dict] = {}
    for status in ADMIN_PORTAL_STATUSES:
        for page in range(1, ADMIN_PORTAL_MAX_PAGES + 1):
            params = {"status": status, "page": page, "page_size": ADMIN_PORTAL_PAGE_SIZE}
            if query.strip():
                params["search"] = query.strip()
            response = requests.get(ADMIN_PORTAL_URL, headers=headers, params=params, timeout=ACCOUNT_LOOKUP_TIMEOUT)
            if response.status_code in (401, 403):
                raise RuntimeError("El Staff Token no es valido o no tiene permisos suficientes.")
            response.raise_for_status()
            payload = response.json()
            for row in payload.get("results", []):
                country = str(row.get("country") or "").strip().upper()
                status_val = row.get("status")
                account_id = row.get("id")
                if country in PRIMARY_COUNTRIES or status_val not in ADMIN_PORTAL_STATUSES or not account_id:
                    continue
                matches[account_id] = {
                    "id": account_id, "name": row.get("name", ""),
                    "country": country, "status": status_val,
                }
            if not payload.get("next") or len(matches) >= ADMIN_PORTAL_MAX_MATCHES:
                break

    return list(matches.values())[:ADMIN_PORTAL_MAX_MATCHES]


def resolver_token(account_id: int) -> str | None:
    """Token de API de una cuenta (query Retool GetToken)."""
    data = _run_retool_query("GetToken", [account_id])
    keys = data.get("key", [])
    return keys[0] if keys else None


def validar_token_cuenta(token: str) -> tuple[bool, str | None, str | None]:
    try:
        response = requests.get(
            f"{API_BASE}/accounts/me/",
            headers={"Authorization": f"Token {token}"},
            timeout=ACCOUNT_LOOKUP_TIMEOUT,
        )
        if response.status_code == 200:
            return True, response.json().get("account", {}).get("name", "Sin nombre"), None
        return False, None, f"HTTP {response.status_code}: {response.text[:200]}"
    except requests.exceptions.RequestException as e:
        return False, None, str(e)


def render_sidebar_cuenta_activa():
    """Widget global de la barra lateral: busca una cuenta por nombre y la deja activa
    para toda la sesion. El token nunca se muestra — solo el nombre de la cuenta."""
    activa = st.session_state.get("cuenta_activa")

    if activa:
        st.markdown(f"🟢 **Cuenta activa:**  \n{activa['name']} (#{activa['id']})")
        if st.button("Quitar cuenta activa", key="cuenta_activa_quitar", use_container_width=True):
            st.session_state["cuenta_activa"] = None
            for key in [k for k in st.session_state if k.startswith("sidebar_al_cache_")]:
                st.session_state.pop(key, None)
            st.rerun()
        return

    with st.expander("🔍 Buscar cuenta"):
        pais = st.selectbox(
            "Pais",
            options=[codigo for codigo, _ in ACCOUNT_LOOKUP_COUNTRIES],
            format_func=lambda c: dict(ACCOUNT_LOOKUP_COUNTRIES)[c],
            key="sidebar_al_pais",
        )
        nombre = st.text_input(
            "Nombre de cuenta", placeholder="Liverpool, Unilever...",
            key="sidebar_al_nombre",
        )

        es_otros = pais == "OTHER"
        query = nombre.strip()
        cache_key = f"sidebar_al_cache_OTHER::{query.lower()}" if es_otros else f"sidebar_al_cache_{pais}"
        ya_cargado = cache_key in st.session_state
        puede_autocargar = len(query) >= MIN_CHARS_AUTOBUSCAR
        autocargar = not ya_cargado and puede_autocargar
        boton_deshabilitado = es_otros and not puede_autocargar

        clic = st.button(
            "Buscar" if es_otros else "Cargar cuentas", key="sidebar_al_buscar",
            use_container_width=True, disabled=boton_deshabilitado,
        )
        if (clic or autocargar) and not boton_deshabilitado:
            with st.spinner("Consultando..."):
                try:
                    st.session_state[cache_key] = buscar_cuentas_otros(query) if es_otros else buscar_cuentas(pais)
                except (requests.exceptions.RequestException, RuntimeError) as e:
                    st.error(f"Error: {e}")
                    st.session_state[cache_key] = []
            ya_cargado = True

        resultados = st.session_state.get(cache_key, [])
        if not es_otros and query:
            filtro = query.lower()
            resultados = [c for c in resultados if filtro in c["name"].lower()]

        for cuenta in resultados[:10]:
            if st.button(f"{cuenta['name']} (#{cuenta['id']})", key=f"sidebar_al_usar_{cuenta['id']}", use_container_width=True):
                with st.spinner("Resolviendo..."):
                    try:
                        token = resolver_token(cuenta["id"])
                    except (requests.exceptions.RequestException, RuntimeError) as e:
                        st.error(f"No se pudo resolver el token: {e}")
                        token = None
                if not token:
                    st.error("No se encontro un token para esta cuenta.")
                else:
                    valido, nombre_validado, detalle = validar_token_cuenta(token)
                    if valido:
                        st.session_state["cuenta_activa"] = {"token": token, "name": nombre_validado, "id": cuenta["id"]}
                        st.rerun()
                    else:
                        st.error(f"El token resuelto no paso la validacion contra /accounts/me/.\n\n{detalle}")

        if len(resultados) > 10:
            st.caption(f"+{len(resultados) - 10} mas — refina el nombre para acotar.")
        elif ya_cargado and query and not resultados:
            st.caption("Sin resultados para ese nombre en el pais seleccionado.")
        elif es_otros and not puede_autocargar:
            st.caption("Escribe al menos 2 letras para buscar en Otros paises (usa el directorio Admin Portal, no el catalogo).")
        elif not es_otros and not ya_cargado:
            st.caption("Escribe al menos 2 letras para ver un prelistado, o carga el catalogo completo.")


def campo_token(key_prefix: str, placeholder: str = "Ingresa el token de API", label_visibility: str = "collapsed") -> str:
    """Campo de token de una pagina: usa la cuenta activa global (buscada en la barra lateral,
    token nunca expuesto) o, si no hay ninguna, un campo manual como antes."""
    activa = st.session_state.get("cuenta_activa")
    if activa:
        render_tip(f"✓ Usando la <strong>cuenta activa</strong> de la barra lateral: <strong>{activa['name']}</strong>")
        return activa["token"]

    return st.text_input(
        "Token", type="password", placeholder=placeholder,
        label_visibility=label_visibility, key=f"{key_prefix}_token",
    )
