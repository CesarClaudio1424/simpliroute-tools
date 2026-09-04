import requests
import streamlit as st
from config import API_BASE, ACCOUNT_LOOKUP_COUNTRIES, ACCOUNT_LOOKUP_TIMEOUT, RETOOL_ACCOUNT_LOOKUP_URL
from utils import render_tip

PRIMARY_COUNTRIES = [codigo for codigo, _ in ACCOUNT_LOOKUP_COUNTRIES]


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
    return response.json().get("queryData", {})


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


def resolver_token(account_id: int) -> str | None:
    """Token de API de una cuenta (query Retool GetToken)."""
    data = _run_retool_query("GetToken", [account_id])
    keys = data.get("key", [])
    return keys[0] if keys else None


def validar_token_cuenta(token: str) -> tuple[bool, str | None]:
    try:
        response = requests.get(
            f"{API_BASE}/accounts/me/",
            headers={"Authorization": f"Token {token}"},
            timeout=ACCOUNT_LOOKUP_TIMEOUT,
        )
        if response.status_code == 200:
            return True, response.json().get("account", {}).get("name", "Sin nombre")
    except requests.exceptions.RequestException:
        pass
    return False, None


def render_sidebar_cuenta_activa():
    """Widget global de la barra lateral: busca una cuenta por nombre y la deja activa
    para toda la sesion. El token nunca se muestra — solo el nombre de la cuenta."""
    activa = st.session_state.get("cuenta_activa")

    if activa:
        st.markdown(f"🟢 **Cuenta activa:**  \n{activa['name']}")
        if st.button("Quitar cuenta activa", key="cuenta_activa_quitar", use_container_width=True):
            st.session_state["cuenta_activa"] = None
            st.session_state.pop("sidebar_al_resultados", None)
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

        if st.button("Buscar", key="sidebar_al_buscar", use_container_width=True):
            with st.spinner("Consultando catalogo..."):
                try:
                    st.session_state["sidebar_al_resultados"] = buscar_cuentas(pais)
                except requests.exceptions.RequestException as e:
                    st.error(f"Error: {e}")
                    st.session_state["sidebar_al_resultados"] = []

        resultados = st.session_state.get("sidebar_al_resultados", [])
        if nombre.strip():
            filtro = nombre.strip().lower()
            resultados = [c for c in resultados if filtro in c["name"].lower()]

        for cuenta in resultados[:10]:
            if st.button(f"{cuenta['name']} (#{cuenta['id']})", key=f"sidebar_al_usar_{cuenta['id']}", use_container_width=True):
                with st.spinner("Resolviendo..."):
                    try:
                        token = resolver_token(cuenta["id"])
                    except requests.exceptions.RequestException as e:
                        st.error(f"No se pudo resolver el token: {e}")
                        token = None
                if not token:
                    st.error("No se encontro un token para esta cuenta.")
                else:
                    valido, nombre_validado = validar_token_cuenta(token)
                    if valido:
                        st.session_state["cuenta_activa"] = {"token": token, "name": nombre_validado, "id": cuenta["id"]}
                        st.rerun()
                    else:
                        st.error("El token resuelto no paso la validacion contra /accounts/me/.")

        if len(resultados) > 10:
            st.caption(f"+{len(resultados) - 10} mas — refina el nombre para acotar.")
        elif nombre.strip() and "sidebar_al_resultados" in st.session_state and not resultados:
            st.caption("Sin resultados para ese nombre en el pais seleccionado.")


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
