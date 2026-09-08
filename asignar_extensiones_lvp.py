import copy
import time

import pandas as pd
import requests
import streamlit as st

from config import RETOOL_EXTENSIONS_URL, RETOOL_EXTENSIONS_TIMEOUT, EXTENSIONES_ASIGNAR_DELAY
from utils import (
    render_header, render_guide, render_label, render_tip,
    render_cuenta_badge, render_stat,
    create_progress_tracker, update_progress, finish_progress,
)

# Catalogo fijo de extensiones reutilizables (igual al dropdown "Seleccionar la extension"
# del Retool original, que tambien es una lista hardcodeada, no una consulta a la BD).
# con_account_id=False solo para LIT: su URL nunca lleva el fragmento #account_id=... (confirmado
# contra 1677 filas reales del export de extensions_extensions/extensions_userextensions).
CATALOGO_EXTENSIONES = [
    {"label": "CAT", "base_url": "https://simpliroute.tryretool.com/embedded/public/6fbcbd52-a7c0-4ba5-826a-6f73d6b4ec8a", "con_account_id": True},
    {"label": "Visitas CAT", "base_url": "https://simpliroute.tryretool.com/embedded/public/81b2e2fe-4311-4d6b-b9a9-1c5e7ea610a4", "con_account_id": True},
    {"label": "Zonas", "base_url": "https://simpliroute.tryretool.com/embedded/public/87697f2d-3b5b-418b-8f77-24c5c01b8976", "con_account_id": True},
    {"label": "Cargas Manuales", "base_url": "https://simpliroute.tryretool.com/embedded/public/0fe79a86-6714-4335-b3f1-8a472e83caf7", "con_account_id": True},
    {"label": "LIT", "base_url": "https://lit.app-sr.co/login", "con_account_id": False},
    {"label": "Visitas GESTOR", "base_url": "https://simpliroute.tryretool.com/embedded/public/4c15ed97-9b53-4054-bfba-577387fe79fc", "con_account_id": True},
    {"label": "Buscador de visitas", "base_url": "https://simpliroute.tryretool.com/embedded/public/08d2c196-1adb-4fa7-95e2-867e55115f19", "con_account_id": True},
    {"label": "Eliminacion de Visitas", "base_url": "https://simpliroute.tryretool.com/embedded/public/2fea4292-4439-4be3-bc3e-ae7870669e06", "con_account_id": True},
    {"label": "Tripulantes/Hom Plan", "base_url": "https://simpliroute.tryretool.com/embedded/public/44bf560d-19b7-499d-bb3e-4bff5b66cca8", "con_account_id": True},
    {"label": "Seguimiento de pedido", "base_url": "https://simpliroute.tryretool.com/embedded/public/2fc8c0f9-6714-4c9b-b58b-c0d1f92c7d6e", "con_account_id": True},
]


@st.cache_data
def _cargar_cuentas():
    try:
        df = pd.read_csv("cuentas.csv", encoding="latin-1")
    except FileNotFoundError:
        return {}
    return {str(nombre): int(id_) for nombre, id_ in zip(df.nombre, df.id)}


def _staff_token():
    try:
        return st.secrets["api_config"]["checkout_token"]
    except KeyError:
        return None


def _listar_usuarios(account_id: int) -> tuple[list[dict], str]:
    """queryName=users (SqlQuery) del endpoint Retool publico de SimpliRoute."""
    payload = {
        "userParams": {
            "queryParams": {"0": account_id, "length": 1},
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
    try:
        r = requests.post(
            f"{RETOOL_EXTENSIONS_URL}/query?queryName=users",
            json=payload,
            timeout=RETOOL_EXTENSIONS_TIMEOUT,
        )
    except requests.exceptions.RequestException as e:
        return [], f"Error de conexion: {e}"
    if r.status_code != 200:
        return [], f"HTTP {r.status_code}: {r.text[:300]}"
    try:
        data = r.json().get("queryData", {})
    except ValueError:
        return [], "Respuesta invalida (no es JSON)."
    ids = data.get("id") or []
    usernames = data.get("username") or []
    return [{"id": i, "username": u} for i, u in zip(ids, usernames)], ""


def _asignar_extension(account_id: int, user_ids: list[int], label: str, ext: dict, staff_token: str):
    """queryName=embedear (RESTQuery) del mismo endpoint Retool. Escribe la asignacion real."""
    base_url = ext["base_url"]
    embed_url = f"{base_url}#account_id={account_id}" if ext["con_account_id"] else base_url
    payload = {
        "userParams": {
            "queryParams": {"length": 0},
            "headersParams": {"0": staff_token, "length": 1},
            "cookiesParams": {"length": 0},
            "bodyParams": {"0": account_id, "1": user_ids, "2": label, "3": embed_url, "length": 4},
            "openAPIParamsParams": {"length": 0},
            "openAPIRequestBodyParams": None,
        },
        "password": "",
        "environment": "production",
        "queryType": "RESTQuery",
        "frontendVersion": "1",
        "releaseVersion": None,
        "includeQueryExecutionMetadata": True,
        "streamResponse": False,
    }
    try:
        r = requests.post(
            f"{RETOOL_EXTENSIONS_URL}/query?queryName=embedear",
            json=payload,
            timeout=RETOOL_EXTENSIONS_TIMEOUT,
        )
    except requests.exceptions.RequestException as e:
        return False, None, f"Error de conexion: {e}", payload
    try:
        data = r.json()
    except ValueError:
        return False, None, f"HTTP {r.status_code}: respuesta no es JSON ({r.text[:300]})", payload
    ok = r.status_code == 200 and not data.get("error")
    return ok, data, "" if ok else f"HTTP {r.status_code}", payload


def _payload_enmascarado(payload):
    p = copy.deepcopy(payload)
    p["userParams"]["headersParams"]["0"] = "***"
    return p


def pagina_asignar_extensiones_lvp():
    render_header(
        "Asignar Extensiones Liverpool",
        "Asigna extensiones (apps embebidas) a usuarios de una cuenta Liverpool",
    )

    render_guide(
        steps=[
            "<strong>Cuenta</strong> — Elige la tienda Liverpool donde asignar.",
            "<strong>Usuarios</strong> — Carga el listado de usuarios de la cuenta y selecciona a quienes se les asignara.",
            "<strong>Label</strong> — Escribe el nombre con el que se mostrara la extension asignada.",
            "<strong>Extension(es)</strong> — Selecciona una o varias extensiones del catalogo a asignar.",
            "<strong>Asignar</strong> — Se hace una solicitud por cada extension seleccionada, incluyendo a todos los usuarios elegidos.",
        ],
        tip="Esta herramienta escribe directamente en la plataforma (asigna acceso real a los usuarios). Revisa bien la seleccion antes de confirmar.",
    )

    cuentas = _cargar_cuentas()
    if not cuentas:
        st.error("No se encontro el archivo `cuentas.csv`.")
        st.stop()

    staff_token = _staff_token()
    if not staff_token:
        st.error("Falta configurar `[api_config] checkout_token` en secrets.")
        st.stop()

    render_label("Paso 1 · Cuenta Liverpool")
    cuenta_nombre = st.selectbox(
        "Cuenta", list(cuentas.keys()), label_visibility="collapsed", key="ael_cuenta",
    )
    account_id = cuentas[cuenta_nombre]
    render_cuenta_badge(f"Cuenta seleccionada: <strong>{cuenta_nombre}</strong> (ID: {account_id})")

    if st.session_state.get("ael_account_cargada") != account_id:
        st.session_state.pop("ael_usuarios", None)
        st.session_state["ael_account_cargada"] = account_id

    render_label("Paso 2 · Usuarios de la cuenta")
    if st.button("Cargar usuarios", key="ael_btn_usuarios"):
        with st.spinner("Consultando usuarios..."):
            usuarios, err = _listar_usuarios(account_id)
        if err:
            st.error(f"Error al cargar usuarios: {err}")
        else:
            st.session_state["ael_usuarios"] = usuarios

    usuarios = st.session_state.get("ael_usuarios")
    if usuarios is None:
        render_tip("Carga los usuarios de la cuenta para continuar.")
        st.stop()
    if not usuarios:
        render_tip("Esta cuenta no tiene usuarios.", warning=True)
        st.stop()

    opciones_usuarios = [f"{u['username']} (#{u['id']})" for u in usuarios]
    sel_usuarios = st.multiselect(
        "Usuarios a los que asignar", opciones_usuarios, key="ael_sel_usuarios",
    )
    usuarios_elegidos = [usuarios[i] for i, o in enumerate(opciones_usuarios) if o in sel_usuarios]

    render_label("Paso 3 · Label")
    label = st.text_input(
        "Escribir label", key="ael_label", placeholder="Ingresar nombre del retool...",
        label_visibility="collapsed",
    )

    render_label("Paso 4 · Extension(es)")
    opciones_ext = [e["label"] for e in CATALOGO_EXTENSIONES]
    sel_ext = st.multiselect(
        "Extensiones a asignar", opciones_ext, key="ael_sel_ext",
    )
    extensiones_elegidas = [e for e in CATALOGO_EXTENSIONES if e["label"] in sel_ext]

    if not usuarios_elegidos or not extensiones_elegidas or not label.strip():
        render_tip("Selecciona al menos un usuario, una extension y escribe un label para continuar.")
        st.stop()

    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(render_stat(len(usuarios_elegidos), "usuario(s) seleccionados"), unsafe_allow_html=True)
    with col2:
        st.markdown(render_stat(len(extensiones_elegidas), "extension(es) seleccionadas"), unsafe_allow_html=True)
    render_tip(
        f"Se haran {len(extensiones_elegidas)} solicitud(es) (una por extension), cada una incluyendo a los "
        f"{len(usuarios_elegidos)} usuario(s) seleccionados con el label <strong>{label.strip()}</strong>."
    )

    confirmar = st.checkbox(
        f"Confirmo que quiero asignar {len(extensiones_elegidas)} extension(es) a {len(usuarios_elegidos)} usuario(s)",
        key="ael_confirmar",
    )
    if not confirmar or not st.button("Asignar extensiones", type="primary", key="ael_btn_asignar"):
        st.stop()

    user_ids = [u["id"] for u in usuarios_elegidos]
    total = len(extensiones_elegidas)
    barra, contador, _ = create_progress_tracker(total, "Asignando extensiones...")
    exitosos = 0

    for i, ext in enumerate(extensiones_elegidas):
        ok, data, err, payload = _asignar_extension(account_id, user_ids, label.strip(), ext, staff_token)
        with st.expander(f"{'✓' if ok else '✗'} {ext['label']}", expanded=not ok):
            st.markdown("**Request:**")
            st.json(_payload_enmascarado(payload))
            st.markdown("**Response:**")
            st.json(data if data is not None else {"error": err})
        if ok:
            exitosos += 1
        update_progress(barra, contador, i + 1, total)
        if i + 1 < total:
            time.sleep(EXTENSIONES_ASIGNAR_DELAY)

    finish_progress(barra)

    if exitosos == total:
        st.success(f"Todas las extensiones asignadas correctamente ({exitosos}/{total})")
    elif exitosos > 0:
        st.warning(f"{exitosos} de {total} extensiones asignadas.")
    else:
        st.error("No se pudo asignar ninguna extension. Revisa los errores arriba.")
