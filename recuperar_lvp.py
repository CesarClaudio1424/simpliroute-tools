import streamlit as st
import requests
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import API_BASE, REQUEST_TIMEOUT
from utils import (
    render_header, render_guide, render_label, render_stat,
    render_error_item, load_secret, create_progress_tracker,
    update_progress, finish_progress,
)

FALLBACK_DAYS = 30


def _headers(token):
    return {"Authorization": f"Token {token}", "Content-Type": "application/json"}


def buscar_por_reference(reference, token):
    url = f"{API_BASE}/routes/visits/reference/{reference}"
    try:
        r = requests.get(url, headers=_headers(token), timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                return data[0] if data else None
            if isinstance(data, dict) and data.get("id"):
                return data
    except requests.exceptions.RequestException:
        pass
    return None


def _buscar_en_fecha(fecha_str, reference, token):
    url = f"{API_BASE}/routes/visits/?planned_date={fecha_str}"
    try:
        r = requests.get(url, headers=_headers(token), timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            for v in (r.json() or []):
                if str(v.get("reference", "")) == str(reference):
                    return v
    except requests.exceptions.RequestException:
        pass
    return None


def buscar_por_fechas(reference, token):
    hoy = date.today()
    fechas = [
        (hoy + timedelta(days=d)).strftime("%Y-%m-%d")
        for d in range(-FALLBACK_DAYS, FALLBACK_DAYS + 1)
    ]
    executor = ThreadPoolExecutor(max_workers=10)
    futures = {executor.submit(_buscar_en_fecha, f, reference, token): f for f in fechas}
    resultado = None
    for future in as_completed(futures):
        r = future.result()
        if r:
            resultado = r
            break
    executor.shutdown(wait=False)
    return resultado


def obtener_ruta_id(vehiculo_nombre, fecha_str, token):
    url = f"{API_BASE}/plans/{fecha_str}/vehicles/"
    try:
        r = requests.get(url, headers=_headers(token), timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            for v in (r.json() or []):
                if v.get("name", "").strip().lower() == vehiculo_nombre.strip().lower():
                    rutas = v.get("routes", [])
                    if rutas:
                        return rutas[0]["id"]
    except requests.exceptions.RequestException:
        pass
    return None


def asignar_visita(visit_id, route_id, planned_date, token):
    url = f"{API_BASE}/routes/visits/{visit_id}"
    try:
        r = requests.put(
            url,
            headers=_headers(token),
            json={"route": route_id, "planned_date": planned_date},
            timeout=REQUEST_TIMEOUT,
        )
        return r.status_code
    except requests.exceptions.RequestException:
        return 0


def pagina_recuperar_lvp():
    render_header(
        "Recuperar Visitas LVP",
        "Busca y asigna visitas Liverpool a su ruta y fecha correspondiente",
    )

    token = load_secret(
        "auth_token",
        "No se encontro `auth_token` en `.streamlit/secrets.toml`. Configura `[api_config]` con `auth_token`.",
    )

    render_guide(
        steps=[
            "<strong>Agrega filas</strong> — Ingresa la referencia de la visita, el nombre del vehiculo destino y la fecha de la ruta.",
            "<strong>Busqueda automatica</strong> — Se busca primero por referencia directa. Si no se encuentra, se busca en un rango de \u00b130 dias en paralelo.",
            "<strong>Asignacion</strong> — La visita encontrada se asigna a la ruta del vehiculo en la fecha indicada via PUT.",
        ],
        tip="El nombre del vehiculo debe coincidir (sin importar mayusculas/minusculas) con el registrado en SimpliRoute.",
    )

    # --- Session state ---
    if "recuperar_filas" not in st.session_state:
        st.session_state.recuperar_filas = [
            {"reference": "", "vehiculo": "", "fecha": date.today()}
        ]

    # --- Cabecera de columnas ---
    render_label("Visitas a recuperar")
    h1, h2, h3, _ = st.columns([3, 3, 2, 1])
    h1.markdown('<div class="sr-label" style="margin-bottom:0.2rem;">Referencia</div>', unsafe_allow_html=True)
    h2.markdown('<div class="sr-label" style="margin-bottom:0.2rem;">Vehiculo</div>', unsafe_allow_html=True)
    h3.markdown('<div class="sr-label" style="margin-bottom:0.2rem;">Fecha</div>', unsafe_allow_html=True)

    # --- Filas dinamicas ---
    for i, fila in enumerate(st.session_state.recuperar_filas):
        col1, col2, col3, col4 = st.columns([3, 3, 2, 1])
        with col1:
            st.session_state.recuperar_filas[i]["reference"] = st.text_input(
                "Referencia",
                value=fila["reference"],
                key=f"ref_{i}",
                placeholder="Ej: 9613078790",
                label_visibility="collapsed",
            )
        with col2:
            st.session_state.recuperar_filas[i]["vehiculo"] = st.text_input(
                "Vehiculo",
                value=fila["vehiculo"],
                key=f"veh_{i}",
                placeholder="Ej: CAMION-01",
                label_visibility="collapsed",
            )
        with col3:
            st.session_state.recuperar_filas[i]["fecha"] = st.date_input(
                "Fecha",
                value=fila["fecha"],
                key=f"fecha_{i}",
                format="DD/MM/YYYY",
                label_visibility="collapsed",
            )
        with col4:
            if len(st.session_state.recuperar_filas) > 1:
                if st.button("\u2715", key=f"del_{i}", use_container_width=True):
                    st.session_state.recuperar_filas.pop(i)
                    st.rerun()

    if st.button("+ Agregar fila", key="btn_agregar"):
        st.session_state.recuperar_filas.append(
            {"reference": "", "vehiculo": "", "fecha": date.today()}
        )
        st.rerun()

    st.markdown("---")

    filas_validas = [
        f for f in st.session_state.recuperar_filas
        if f["reference"].strip() and f["vehiculo"].strip()
    ]
    st.markdown(render_stat(len(filas_validas), "visitas a procesar"), unsafe_allow_html=True)

    if not st.button("Recuperar visitas", type="primary", key="btn_recuperar"):
        st.stop()

    if not filas_validas:
        st.warning("Ingresa al menos una referencia y vehiculo.")
        st.stop()

    # --- Procesamiento ---
    total = len(filas_validas)
    exitosos = 0

    barra, contador, contenedor_errores = create_progress_tracker(total, "Procesando visitas...")

    for i, fila in enumerate(filas_validas):
        reference = fila["reference"].strip()
        vehiculo = fila["vehiculo"].strip()
        fecha_str = fila["fecha"].strftime("%Y-%m-%d")
        fecha_display = fila["fecha"].strftime("%d/%m/%Y")

        # 1. Buscar visita por reference, con fallback por fechas
        visita = buscar_por_reference(reference, token)
        if not visita:
            visita = buscar_por_fechas(reference, token)

        if not visita:
            with contenedor_errores:
                render_error_item(f"Ref {reference} — No encontrada en SimpliRoute")
            update_progress(barra, contador, i + 1, total)
            continue

        # 2. Obtener route_id del vehiculo en la fecha
        route_id = obtener_ruta_id(vehiculo, fecha_str, token)
        if not route_id:
            with contenedor_errores:
                render_error_item(f"Ref {reference} — Vehiculo '{vehiculo}' sin ruta el {fecha_display}")
            update_progress(barra, contador, i + 1, total)
            continue

        # 3. Asignar visita a la ruta
        status = asignar_visita(visita["id"], route_id, fecha_str, token)
        if 200 <= status < 300:
            exitosos += 1
        else:
            with contenedor_errores:
                render_error_item(f"Ref {reference} — Error al asignar (HTTP {status})")

        update_progress(barra, contador, i + 1, total)

    finish_progress(barra)

    if exitosos > 0:
        st.success(f"{exitosos} de {total} visitas recuperadas correctamente")
    if exitosos < total:
        st.error(f"{total - exitosos} visita(s) con error")
