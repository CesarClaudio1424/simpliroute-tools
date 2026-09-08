import copy
import time

import pandas as pd
import psycopg2
import psycopg2.extras
import requests
import streamlit as st

from config import RETOOL_EXTENSIONS_URL, RETOOL_EXTENSIONS_TIMEOUT, EXTENSIONES_ASIGNAR_DELAY
from utils import (
    render_header, render_guide, render_label, render_tip,
    render_cuenta_badge, render_stat,
    create_progress_tracker, update_progress, finish_progress,
)


@st.cache_data
def _cargar_cuentas():
    try:
        df = pd.read_csv("cuentas.csv", encoding="latin-1")
    except FileNotFoundError:
        return {}
    return {str(nombre): int(id_) for nombre, id_ in zip(df.nombre, df.id)}


def _staff_token():
    try:
        return st.secrets["extensiones_lvp"]["staff_token"]
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


def _get_readonly_connection():
    try:
        cfg = st.secrets["readonly_bi"]
        return psycopg2.connect(
            host=cfg["host"],
            port=cfg["port"],
            dbname=cfg["dbname"],
            user=cfg["user"],
            password=cfg["password"],
            connect_timeout=10,
        )
    except KeyError:
        st.error("Faltan credenciales en secrets. Agregar [readonly_bi] con host, port, dbname, user y password.")
        st.stop()
    except psycopg2.OperationalError as e:
        st.error(f"No se pudo conectar a la base de datos: {e}")
        st.stop()


def _listar_catalogo_extensiones() -> tuple[list[dict], str]:
    """Catalogo completo de extensions_extensions (sin filtro de cuenta): id, label, urls."""
    conn = _get_readonly_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id, label, urls FROM extensions_extensions ORDER BY label")
            return [dict(row) for row in cur.fetchall()], ""
    except psycopg2.Error as e:
        return [], str(e)
    finally:
        conn.close()


def _asignar_extension(account_id: int, user_ids: list[int], label: str, base_url: str, staff_token: str):
    """queryName=embedear (RESTQuery) del mismo endpoint Retool. Escribe la asignacion real."""
    embed_url = f"{base_url.split('#')[0]}#account_id={account_id}"
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
            "<strong>Extension(es)</strong> — Carga el catalogo y selecciona una o varias extensiones a asignar.",
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
        st.error("Falta configurar `[extensiones_lvp] staff_token` en secrets.")
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
    if st.button("Cargar catalogo de extensiones", key="ael_btn_catalogo"):
        with st.spinner("Consultando catalogo..."):
            catalogo, err = _listar_catalogo_extensiones()
        if err:
            st.error(f"Error al cargar catalogo: {err}")
        else:
            st.session_state["ael_catalogo"] = catalogo

    catalogo = st.session_state.get("ael_catalogo")
    if catalogo is None:
        render_tip("Carga el catalogo de extensiones para continuar.")
        st.stop()
    if not catalogo:
        render_tip("No hay extensiones registradas en el catalogo.", warning=True)
        st.stop()

    opciones_ext = [f"{e['label']} (#{e['id']})" for e in catalogo]
    sel_ext = st.multiselect(
        "Extensiones a asignar", opciones_ext, key="ael_sel_ext",
    )
    extensiones_elegidas = [catalogo[i] for i, o in enumerate(opciones_ext) if o in sel_ext]

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
        ok, data, err, payload = _asignar_extension(account_id, user_ids, label.strip(), ext["urls"], staff_token)
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
