import time
import requests
import streamlit as st
from config import API_BASE, REQUEST_TIMEOUT, OBSERVATION_DELAY
from utils import render_header, render_guide, render_label, render_tip, render_stat
from account_lookup import campo_token

OBSERVATIONS_URL = f"{API_BASE}/routes/observations/"


def _listar_motivos(token: str) -> tuple[list[dict], str]:
    """GET /v1/routes/observations/ — returns (lista de {id, label} tipo failed, error_msg)."""
    headers = {"Authorization": f"Token {token}"}
    try:
        resp = requests.get(OBSERVATIONS_URL, headers=headers, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict):
                data = data.get("results", [])
            return [
                {"id": o["id"], "label": o.get("label", str(o["id"]))}
                for o in data if o.get("type") == "failed"
            ], ""
        return [], f"HTTP {resp.status_code}: {resp.text[:200]}"
    except requests.exceptions.RequestException as e:
        return [], f"Error de conexion: {e}"


def _crear_motivo(token: str, label: str) -> tuple[bool, str]:
    """POST /v1/routes/observations/ con type=failed."""
    headers = {
        "Authorization": f"Token {token}",
        "Content-Type": "application/json",
    }
    payload = {"type": "failed", "label": label}
    try:
        resp = requests.post(OBSERVATIONS_URL, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
        if resp.status_code in (200, 201):
            return True, ""
        return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
    except requests.exceptions.RequestException as e:
        return False, f"Error de conexion: {e}"


def _eliminar_motivo_api(token: str, motivo_id) -> tuple[bool, str]:
    """DELETE /v1/routes/observations/{id} (sin trailing slash)."""
    url = f"{API_BASE}/routes/observations/{motivo_id}"
    headers = {"Authorization": f"Token {token}"}
    try:
        resp = requests.delete(url, headers=headers, timeout=REQUEST_TIMEOUT)
        if resp.status_code in (200, 204):
            return True, ""
        return False, f"HTTP {resp.status_code}: {resp.text[:300]}"
    except requests.exceptions.RequestException as e:
        return False, f"Error de conexion: {e}"


def pagina_motivos_rechazo():
    render_header("Motivos de Rechazo", "Crea o elimina motivos de rechazo (checkout fallido) de una cuenta SimpliRoute")

    render_guide(
        steps=[
            "<strong>Token</strong> — Ingresa el token de la cuenta donde operar.",
            "<strong>Elige el modo</strong> — <em>Crear motivos</em> para agregar nuevos, o <em>Ver y eliminar</em> para gestionar los existentes.",
            "<strong>Crear:</strong> Pega un motivo por linea y confirma.",
            "<strong>Ver y eliminar:</strong> Carga los motivos de la cuenta, selecciona los que quieres borrar y confirma.",
        ],
        tip="Estos motivos son las <em>Observations</em> de tipo <code>failed</code> de SimpliRoute — se usan al hacer checkout fallido de una visita (campo checkout_observation).",
    )

    render_label("Token de API")
    token = campo_token("mr", placeholder="5d1fe9e...")
    if not token:
        render_tip("Ingresa el token de la cuenta SimpliRoute donde se gestionaran los motivos.")
        st.stop()

    modo = st.radio(
        "Accion",
        ["Crear motivos", "Ver y eliminar motivos existentes"],
        horizontal=True,
        label_visibility="collapsed",
        key="mr_modo",
    )

    # Clear cached state if token or mode changed
    if st.session_state.get("_mr_token") != token:
        for k in ("_mr_lista", "_mr_del_active", "_mr_del_queue", "_mr_del_total", "_mr_del_done", "_mr_del_errors"):
            st.session_state.pop(k, None)
        st.session_state["_mr_token"] = token

    st.markdown("---")

    if modo == "Ver y eliminar motivos existentes":
        if not st.session_state.get("_mr_del_active"):
            if st.button("Leer motivos de la cuenta", key="mr_btn_cargar"):
                lista, err = _listar_motivos(token)
                if err:
                    st.error(f"Error al cargar motivos: {err}")
                else:
                    st.session_state["_mr_lista"] = lista

            lista = st.session_state.get("_mr_lista")
            if lista is not None:
                if not lista:
                    render_tip("La cuenta no tiene motivos de rechazo registrados.")
                else:
                    st.markdown(render_stat(len(lista), "motivos en la cuenta"), unsafe_allow_html=True)
                    opciones = [f"{m['label']} (#{m['id']})" for m in lista]
                    seleccion = st.multiselect("Motivos a eliminar", opciones, default=opciones, key="mr_sel")
                    a_eliminar = [lista[i] for i, opt in enumerate(opciones) if opt in seleccion]

                    if a_eliminar:
                        confirmar = st.checkbox(
                            f"Confirmo que quiero eliminar {len(a_eliminar)} motivo(s)",
                            key="mr_confirmar_del",
                        )
                        if confirmar and st.button("Eliminar motivos seleccionados", type="primary", key="mr_btn_eliminar"):
                            st.session_state["_mr_del_active"] = True
                            st.session_state["_mr_del_queue"] = a_eliminar
                            st.session_state["_mr_del_total"] = len(a_eliminar)
                            st.session_state["_mr_del_done"] = 0
                            st.session_state["_mr_del_errors"] = []
                            st.rerun()
        else:
            queue = st.session_state.get("_mr_del_queue", [])
            total = st.session_state["_mr_del_total"]
            procesados = total - len(queue)
            errores: list[dict] = st.session_state["_mr_del_errors"]

            st.progress(min(procesados / total, 1.0), text="Eliminando motivos...")
            col_stat, col_cancel = st.columns([4, 1])
            with col_stat:
                st.markdown(render_stat(f"{procesados}/{total}", "procesados"), unsafe_allow_html=True)
            with col_cancel:
                st.markdown('<div style="padding-top:1.4rem;"></div>', unsafe_allow_html=True)
                if queue and st.button("Cancelar", key="mr_btn_cancelar", use_container_width=True):
                    st.session_state["_mr_del_active"] = False
                    st.session_state.pop("_mr_del_queue", None)
                    done_so_far = st.session_state.get("_mr_del_done", 0)
                    st.warning(f"Proceso cancelado. {done_so_far} motivo(s) eliminados antes de cancelar.")
                    st.stop()

            for err_item in errores:
                with st.expander(f"✗ {err_item['label']}", expanded=True):
                    st.code(err_item["detail"], language=None)

            if queue:
                siguiente = queue[0]
                ok, detalle = _eliminar_motivo_api(token, siguiente["id"])
                if ok:
                    st.session_state["_mr_del_done"] += 1
                else:
                    st.session_state["_mr_del_errors"].append({
                        "label": f"Motivo «{siguiente['label']}» (#{siguiente['id']})",
                        "detail": detalle,
                    })
                st.session_state["_mr_del_queue"] = queue[1:]
                time.sleep(OBSERVATION_DELAY)
                st.rerun()
            else:
                st.session_state["_mr_del_active"] = False
                exitosos = st.session_state["_mr_del_done"]
                st.session_state.pop("_mr_lista", None)
                if exitosos == total:
                    st.success(f"Todos los motivos eliminados ({exitosos}/{total})")
                elif exitosos > 0:
                    st.warning(f"{exitosos} de {total} motivos eliminados.")
                else:
                    st.error("No se pudo eliminar ningun motivo.")
        return

    # --- Modo Crear ---
    render_label("Motivos a crear (uno por linea)")
    texto = st.text_area(
        "Motivos", placeholder="Cliente ausente\nDireccion incorrecta\nRechazo de mercancia",
        label_visibility="collapsed", height=150, key="mr_texto",
    )

    if not texto or not texto.strip():
        render_tip("Pega un motivo de rechazo por linea.")
        st.stop()

    labels = [l.strip() for l in texto.strip().split("\n") if l.strip()]
    labels_dup = list(dict.fromkeys(l for l in labels if labels.count(l) > 1))

    st.markdown(render_stat(len(labels), "motivos a crear"), unsafe_allow_html=True)
    if labels_dup:
        render_tip(f"<strong>⚠️ Atencion:</strong> Motivos duplicados en la lista: {labels_dup}.", warning=True)

    if st.session_state.get("_mr_crear_active"):
        queue = st.session_state.get("_mr_crear_queue", [])
        total = st.session_state["_mr_crear_total"]
        procesados = total - len(queue)
        errores: list[dict] = st.session_state["_mr_crear_errors"]

        st.progress(min(procesados / total, 1.0), text="Creando motivos...")
        col_stat, col_cancel = st.columns([4, 1])
        with col_stat:
            st.markdown(render_stat(f"{procesados}/{total}", "creados"), unsafe_allow_html=True)
        with col_cancel:
            st.markdown('<div style="padding-top:1.4rem;"></div>', unsafe_allow_html=True)
            if queue and st.button("Cancelar", key="mr_btn_cancelar_crear", use_container_width=True):
                st.session_state["_mr_crear_active"] = False
                st.session_state.pop("_mr_crear_queue", None)
                done = st.session_state.get("_mr_crear_done", 0)
                st.warning(f"Proceso cancelado. {done} motivo(s) creados antes de cancelar.")
                st.stop()

        for err_item in errores:
            with st.expander(f"✗ {err_item['label']}", expanded=True):
                st.code(err_item["detail"], language=None)

        if queue:
            siguiente = queue[0]
            ok, detalle = _crear_motivo(token, siguiente)
            if ok:
                st.session_state["_mr_crear_done"] += 1
            else:
                st.session_state["_mr_crear_errors"].append({"label": f"Motivo «{siguiente}»", "detail": detalle})
            st.session_state["_mr_crear_queue"] = queue[1:]
            time.sleep(OBSERVATION_DELAY)
            st.rerun()
        else:
            st.session_state["_mr_crear_active"] = False
            exitosos = st.session_state["_mr_crear_done"]
            if exitosos == total:
                st.success(f"Todos los motivos creados correctamente ({exitosos}/{total})")
            elif exitosos > 0:
                st.warning(f"{exitosos} de {total} motivos creados.")
            else:
                st.error("No se pudo crear ningun motivo. Revisa el token y los errores.")
    else:
        if st.button("Crear motivos en SimpliRoute", type="primary", key="mr_btn_crear"):
            st.session_state["_mr_crear_active"] = True
            st.session_state["_mr_crear_queue"] = labels
            st.session_state["_mr_crear_total"] = len(labels)
            st.session_state["_mr_crear_done"] = 0
            st.session_state["_mr_crear_errors"] = []
            st.rerun()
