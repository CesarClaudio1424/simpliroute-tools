import time
from collections import defaultdict
import streamlit as st
import requests
from config import API_BASE, REQUEST_TIMEOUT, MAX_RETRIES, RETRY_BASE_DELAY
from utils import (
    render_header, render_guide, render_stat, render_label,
    render_tip, render_error_item,
    create_progress_tracker, update_progress, finish_progress,
)


def eliminar_items(token, visit_id, item_ids):
    headers = {
        "Authorization": f"Token {token}",
        "Content-Type": "application/json",
    }
    url = f"{API_BASE}/routes/visits/{visit_id}/items/"
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = requests.delete(url, headers=headers, json=item_ids, timeout=REQUEST_TIMEOUT)
            if response.status_code in (200, 204):
                return True, ""
            if response.status_code >= 500 and attempt < MAX_RETRIES:
                time.sleep(RETRY_BASE_DELAY * (2 ** attempt))
                continue
            return False, f"HTTP {response.status_code}: {response.text}"
        except requests.exceptions.RequestException as e:
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BASE_DELAY * (2 ** attempt))
                continue
            return False, f"Error de conexion: {str(e)}"
    return False, "Reintentos agotados"


def pagina_eliminacion_items():
    render_header("Eliminacion de Items", "Elimina items de visitas via API SimpliRoute")

    render_guide(
        steps=[
            '<strong>Ingresa tu token</strong> — Token de API de SimpliRoute.',
            '<strong>Pega los datos</strong> — Formato: <code>visit_id [tab] item_id</code>, uno por linea.',
            '<strong>Procesa</strong> — Los items se agrupan por visita y se envia un DELETE por cada una.',
        ],
        tip='Puedes copiar directamente desde una hoja de calculo. Los items de la misma visita se envian en un solo request.',
    )

    # --- Token ---
    render_label("Token de API")
    token = st.text_input("Token", type="password", label_visibility="collapsed")

    if not token or not token.strip():
        render_tip("Ingresa tu token de API de SimpliRoute para continuar.")
        st.stop()

    # --- Datos ---
    render_label("Datos (visit_id [tab] item_id)")

    datos_input = st.text_area(
        "Datos",
        placeholder="750012931\t98765\n750012931\t98766\n750012932\t98770",
        label_visibility="collapsed",
        height=200,
    )

    if not datos_input or not datos_input.strip():
        render_tip("Pega los datos a procesar. Cada linea debe tener dos campos separados por tabulador: visit_id e item_id.")
        st.stop()

    lineas = [line.strip() for line in datos_input.strip().split("\n") if line.strip()]
    errores_formato = []
    items_por_visita = defaultdict(list)

    for i, linea in enumerate(lineas):
        campos = linea.split("\t")
        if len(campos) < 2:
            errores_formato.append(f"Linea {i + 1}: formato incorrecto ({linea[:50]})")
            continue
        visit_id = campos[0].strip()
        item_id = campos[1].strip()

        if not visit_id.isdigit():
            errores_formato.append(f"Linea {i + 1}: visit_id '{visit_id}' no es numerico")
            continue
        if not item_id.isdigit():
            errores_formato.append(f"Linea {i + 1}: item_id '{item_id}' no es numerico")
            continue

        items_por_visita[visit_id].append(int(item_id))

    if errores_formato:
        for err in errores_formato:
            render_error_item(err)

    if not items_por_visita:
        render_tip(
            "<strong>⚠️ Atencion:</strong> No se encontraron filas validas. Verifica que los datos esten separados por tabulador.",
            warning=True,
        )
        st.stop()

    total_items = sum(len(ids) for ids in items_por_visita.values())
    total_visitas = len(items_por_visita)

    col_stat1, col_stat2 = st.columns(2)
    with col_stat1:
        st.markdown(render_stat(total_items, "items a eliminar"), unsafe_allow_html=True)
    with col_stat2:
        st.markdown(render_stat(total_visitas, "visitas afectadas"), unsafe_allow_html=True)

    if not st.button("Eliminar items", type="primary", key="btn_eliminar_items"):
        st.stop()

    # --- Procesamiento ---
    exitosos = 0
    fallidos = []

    barra, contador, contenedor_errores = create_progress_tracker(total_visitas, "Eliminando items...")

    for i, (visit_id, item_ids) in enumerate(items_por_visita.items()):
        ok, detalle = eliminar_items(token.strip(), visit_id, item_ids)
        procesados = i + 1

        if ok:
            exitosos += len(item_ids)
        else:
            fallidos.append((visit_id, item_ids, detalle))
            with contenedor_errores:
                render_error_item(f"Visita {visit_id} ({len(item_ids)} items) — {detalle}")

        update_progress(barra, contador, procesados, total_visitas, "Eliminando items...")

    finish_progress(barra)

    items_fallidos = sum(len(ids) for _, ids, _ in fallidos)
    if exitosos > 0:
        st.success(f"{exitosos} items eliminados correctamente de {total_visitas - len(fallidos)} visitas")
    if fallidos:
        st.error(f"{items_fallidos} items fallaron en {len(fallidos)} visitas")
