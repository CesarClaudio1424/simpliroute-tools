import time
import requests
import streamlit as st
from config import API_BASE, REQUEST_TIMEOUT, VISIT_TYPE_DELAY
from utils import render_header, render_guide, render_label, render_tip, render_stat
from account_lookup import campo_token

VISIT_TYPES_URL = f"{API_BASE}/accounts/visit-types/"


def _listar_tipos(token: str) -> tuple[list[dict], str]:
    """GET /v1/accounts/visit-types/ — returns (lista de {id, label, key}, error_msg)."""
    headers = {"Authorization": f"Token {token}"}
    try:
        resp = requests.get(VISIT_TYPES_URL, headers=headers, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict):
                data = data.get("results", [])
            return [{"id": t["id"], "label": t.get("label", str(t["id"])), "key": t.get("key", "")} for t in data], ""
        return [], f"HTTP {resp.status_code}: {resp.text[:200]}"
    except requests.exceptions.RequestException as e:
        return [], f"Error de conexion: {e}"


def _crear_tipo(token: str, label: str) -> tuple[bool, str]:
    """POST /v1/accounts/visit-types/. La API normaliza el key (quita guiones), asi que basta enviar
    una version en minusculas — no hay que replicar la normalizacion exacta del servidor."""
    headers = {
        "Authorization": f"Token {token}",
        "Content-Type": "application/json",
    }
    key = label.strip().lower().replace(" ", "_")
    payload = {"label": label, "key": key}
    try:
        resp = requests.post(VISIT_TYPES_URL, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
        if resp.status_code in (200, 201):
            return True, ""
        return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
    except requests.exceptions.RequestException as e:
        return False, f"Error de conexion: {e}"


def _eliminar_tipo_api(token: str, tipo_id) -> tuple[bool, str]:
    """DELETE /v1/accounts/visit-types/{id}/ — requiere trailing slash (sin ella responde 301)."""
    url = f"{VISIT_TYPES_URL}{tipo_id}/"
    headers = {"Authorization": f"Token {token}"}
    try:
        resp = requests.delete(url, headers=headers, timeout=REQUEST_TIMEOUT)
        if resp.status_code in (200, 204):
            return True, ""
        return False, f"HTTP {resp.status_code}: {resp.text[:300]}"
    except requests.exceptions.RequestException as e:
        return False, f"Error de conexion: {e}"


def pagina_tipos_visita():
    render_header("Tipos de Visita", "Crea o elimina tipos de visita (visit types) de una cuenta SimpliRoute")

    render_guide(
        steps=[
            "<strong>Token</strong> — Ingresa el token de la cuenta donde operar.",
            "<strong>Elige el modo</strong> — <em>Crear tipos</em> para agregar nuevos, o <em>Ver y eliminar</em> para gestionar los existentes.",
            "<strong>Crear:</strong> Pega un tipo por linea y confirma.",
            "<strong>Ver y eliminar:</strong> Carga los tipos de la cuenta, selecciona los que quieres borrar y confirma.",
        ],
        tip="El <code>key</code> se genera automaticamente en minusculas a partir del label. La API de SimpliRoute normaliza el key por su cuenta (por ejemplo, quita guiones), asi que el key final puede diferir del enviado.",
    )

    render_label("Token de API")
    token = campo_token("tv", placeholder="5d1fe9e...")
    if not token:
        render_tip("Ingresa el token de la cuenta SimpliRoute donde se gestionaran los tipos de visita.")
        st.stop()

    modo = st.radio(
        "Accion",
        ["Crear tipos", "Ver y eliminar tipos existentes"],
        horizontal=True,
        label_visibility="collapsed",
        key="tv_modo",
    )

    # Clear cached state if token or mode changed
    if st.session_state.get("_tv_token") != token:
        for k in ("_tv_lista", "_tv_del_active", "_tv_del_queue", "_tv_del_total", "_tv_del_done", "_tv_del_errors"):
            st.session_state.pop(k, None)
        st.session_state["_tv_token"] = token

    st.markdown("---")

    if modo == "Ver y eliminar tipos existentes":
        if not st.session_state.get("_tv_del_active"):
            if st.button("Leer tipos de la cuenta", key="tv_btn_cargar"):
                lista, err = _listar_tipos(token)
                if err:
                    st.error(f"Error al cargar tipos de visita: {err}")
                else:
                    st.session_state["_tv_lista"] = lista

            lista = st.session_state.get("_tv_lista")
            if lista is not None:
                if not lista:
                    render_tip("La cuenta no tiene tipos de visita registrados.")
                else:
                    st.markdown(render_stat(len(lista), "tipos en la cuenta"), unsafe_allow_html=True)
                    opciones = [f"{t['label']} ({t['key']}) (#{t['id']})" for t in lista]
                    seleccion = st.multiselect("Tipos a eliminar", opciones, default=opciones, key="tv_sel")
                    a_eliminar = [lista[i] for i, opt in enumerate(opciones) if opt in seleccion]

                    if a_eliminar:
                        confirmar = st.checkbox(
                            f"Confirmo que quiero eliminar {len(a_eliminar)} tipo(s)",
                            key="tv_confirmar_del",
                        )
                        if confirmar and st.button("Eliminar tipos seleccionados", type="primary", key="tv_btn_eliminar"):
                            st.session_state["_tv_del_active"] = True
                            st.session_state["_tv_del_queue"] = a_eliminar
                            st.session_state["_tv_del_total"] = len(a_eliminar)
                            st.session_state["_tv_del_done"] = 0
                            st.session_state["_tv_del_errors"] = []
                            st.rerun()
        else:
            queue = st.session_state.get("_tv_del_queue", [])
            total = st.session_state["_tv_del_total"]
            procesados = total - len(queue)
            errores: list[dict] = st.session_state["_tv_del_errors"]

            st.progress(min(procesados / total, 1.0), text="Eliminando tipos...")
            col_stat, col_cancel = st.columns([4, 1])
            with col_stat:
                st.markdown(render_stat(f"{procesados}/{total}", "procesados"), unsafe_allow_html=True)
            with col_cancel:
                st.markdown('<div style="padding-top:1.4rem;"></div>', unsafe_allow_html=True)
                if queue and st.button("Cancelar", key="tv_btn_cancelar", use_container_width=True):
                    st.session_state["_tv_del_active"] = False
                    st.session_state.pop("_tv_del_queue", None)
                    done_so_far = st.session_state.get("_tv_del_done", 0)
                    st.warning(f"Proceso cancelado. {done_so_far} tipo(s) eliminados antes de cancelar.")
                    st.stop()

            for err_item in errores:
                with st.expander(f"✗ {err_item['label']}", expanded=True):
                    st.code(err_item["detail"], language=None)

            if queue:
                siguiente = queue[0]
                ok, detalle = _eliminar_tipo_api(token, siguiente["id"])
                if ok:
                    st.session_state["_tv_del_done"] += 1
                else:
                    st.session_state["_tv_del_errors"].append({
                        "label": f"Tipo «{siguiente['label']}» (#{siguiente['id']})",
                        "detail": detalle,
                    })
                st.session_state["_tv_del_queue"] = queue[1:]
                time.sleep(VISIT_TYPE_DELAY)
                st.rerun()
            else:
                st.session_state["_tv_del_active"] = False
                exitosos = st.session_state["_tv_del_done"]
                st.session_state.pop("_tv_lista", None)
                if exitosos == total:
                    st.success(f"Todos los tipos eliminados ({exitosos}/{total})")
                elif exitosos > 0:
                    st.warning(f"{exitosos} de {total} tipos eliminados.")
                else:
                    st.error("No se pudo eliminar ningun tipo.")
        return

    # --- Modo Crear ---
    render_label("Tipos a crear (uno por linea)")
    texto = st.text_area(
        "Tipos", placeholder="AASS\nAASS-NOCHE\nHORECA",
        label_visibility="collapsed", height=150, key="tv_texto",
    )

    if not texto or not texto.strip():
        render_tip("Pega un tipo de visita por linea.")
        st.stop()

    labels = [l.strip() for l in texto.strip().split("\n") if l.strip()]
    labels_dup = list(dict.fromkeys(l for l in labels if labels.count(l) > 1))

    st.markdown(render_stat(len(labels), "tipos a crear"), unsafe_allow_html=True)
    if labels_dup:
        render_tip(f"<strong>⚠️ Atencion:</strong> Tipos duplicados en la lista: {labels_dup}.", warning=True)

    if st.session_state.get("_tv_crear_active"):
        queue = st.session_state.get("_tv_crear_queue", [])
        total = st.session_state["_tv_crear_total"]
        procesados = total - len(queue)
        errores: list[dict] = st.session_state["_tv_crear_errors"]

        st.progress(min(procesados / total, 1.0), text="Creando tipos...")
        col_stat, col_cancel = st.columns([4, 1])
        with col_stat:
            st.markdown(render_stat(f"{procesados}/{total}", "creados"), unsafe_allow_html=True)
        with col_cancel:
            st.markdown('<div style="padding-top:1.4rem;"></div>', unsafe_allow_html=True)
            if queue and st.button("Cancelar", key="tv_btn_cancelar_crear", use_container_width=True):
                st.session_state["_tv_crear_active"] = False
                st.session_state.pop("_tv_crear_queue", None)
                done = st.session_state.get("_tv_crear_done", 0)
                st.warning(f"Proceso cancelado. {done} tipo(s) creados antes de cancelar.")
                st.stop()

        for err_item in errores:
            with st.expander(f"✗ {err_item['label']}", expanded=True):
                st.code(err_item["detail"], language=None)

        if queue:
            siguiente = queue[0]
            ok, detalle = _crear_tipo(token, siguiente)
            if ok:
                st.session_state["_tv_crear_done"] += 1
            else:
                st.session_state["_tv_crear_errors"].append({"label": f"Tipo «{siguiente}»", "detail": detalle})
            st.session_state["_tv_crear_queue"] = queue[1:]
            time.sleep(VISIT_TYPE_DELAY)
            st.rerun()
        else:
            st.session_state["_tv_crear_active"] = False
            exitosos = st.session_state["_tv_crear_done"]
            if exitosos == total:
                st.success(f"Todos los tipos creados correctamente ({exitosos}/{total})")
            elif exitosos > 0:
                st.warning(f"{exitosos} de {total} tipos creados.")
            else:
                st.error("No se pudo crear ningun tipo. Revisa el token y los errores.")
    else:
        if st.button("Crear tipos en SimpliRoute", type="primary", key="tv_btn_crear"):
            st.session_state["_tv_crear_active"] = True
            st.session_state["_tv_crear_queue"] = labels
            st.session_state["_tv_crear_total"] = len(labels)
            st.session_state["_tv_crear_done"] = 0
            st.session_state["_tv_crear_errors"] = []
            st.rerun()
