import json
import math
import re
from collections import defaultdict
import requests
import streamlit as st
from config import API_BASE, REQUEST_TIMEOUT, MAX_SMALLINT_FIELD
from utils import (
    render_header, render_guide, render_label, render_stat,
    render_tip, render_cuenta_badge, render_error_item,
)
from account_lookup import campo_token

MARGEN_CAPACIDAD = 1.2  # 20% de holgura sobre la carga asignada

_CAMPOS_CARGA = [
    ("Carga 1", "total_load", "total_load_percentage", "capacity"),
    ("Carga 2", "total_load_2", "total_load_2_percentage", "capacity_2"),
    ("Carga 3", "total_load_3", "total_load_3_percentage", "capacity_3"),
]
_CAMPO_CAP_POR_LABEL = {label: campo_cap for label, _, _, campo_cap in _CAMPOS_CARGA}


def _capacidad_sugerida(carga_asignada):
    return math.ceil(carga_asignada * MARGEN_CAPACIDAD)


def _extraer_json_de_texto(texto):
    """Si el contenido es un comando curl (Copy as cURL del navegador), extrae el JSON de --data/--data-raw."""
    texto = texto.strip()
    if texto.lower().startswith("curl"):
        m = re.search(r"--data(?:-raw)?\s+'(.*)'\s*$", texto, re.DOTALL)
        if m:
            # bash escapa comillas simples internas (ej. en nombres de clientes) como '\''
            return m.group(1).replace("'\\''", "'")
    return texto


def _headers(token):
    return {"Authorization": f"Token {token}", "Content-Type": "application/json"}


def _validar_cuenta(token):
    try:
        r = requests.get(f"{API_BASE}/accounts/me/", headers=_headers(token), timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            return True, r.json().get("account", {}).get("name", "Sin nombre")
    except requests.exceptions.RequestException:
        pass
    return False, None


def _obtener_vehiculos(token):
    try:
        r = requests.get(f"{API_BASE}/routes/vehicles/", headers=_headers(token), timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, dict):
                data = data.get("results", [])
            return {v["id"]: v for v in data}
    except requests.exceptions.RequestException:
        pass
    return {}


def _extraer_rutas(data):
    if isinstance(data, dict):
        return data.get("routes", [])
    if isinstance(data, list):
        return data
    return []


def _analizar_rutas(rutas, vehiculos_info):
    problemas = []
    for i, ruta in enumerate(rutas, start=1):
        vehicle_id = ruta.get("vehicle")
        info = vehiculos_info.get(vehicle_id, {})
        for label, campo_valor, campo_pct, campo_cap in _CAMPOS_CARGA:
            pct = ruta.get(campo_pct)
            if isinstance(pct, (int, float)) and pct > MAX_SMALLINT_FIELD:
                carga_asignada = ruta.get(campo_valor)
                capacidad_actual = info.get(campo_cap)
                sugerida = _capacidad_sugerida(carga_asignada)
                if isinstance(capacidad_actual, (int, float)):
                    # nunca sugerir bajar la capacidad (puede que ya la hayan corregido a mano)
                    sugerida = max(sugerida, capacidad_actual)
                problemas.append({
                    "Ruta": i,
                    "Vehiculo": info.get("name", str(vehicle_id)),
                    "ID vehiculo": vehicle_id,
                    "Campo": label,
                    "Carga asignada": carga_asignada,
                    "% calculado": pct,
                    "Capacidad configurada": capacidad_actual if capacidad_actual is not None else "?",
                    "Capacidad sugerida": sugerida,
                    "Fecha": ruta.get("planned_date"),
                })
    return problemas


def _actualizar_capacidades_vehiculo(token, vehicle_id, campos_nuevos, vehiculo_completo):
    payload = dict(vehiculo_completo)
    payload.update(campos_nuevos)
    url = f"{API_BASE}/routes/vehicles/{vehicle_id}/"
    try:
        r = requests.put(url, headers=_headers(token), json=payload, timeout=REQUEST_TIMEOUT)
        if r.status_code in (200, 201):
            return True, ""
        return False, f"HTTP {r.status_code}: {r.text[:300]}"
    except requests.exceptions.RequestException as e:
        return False, f"Error de conexion: {e}"


def pagina_validador_plan():
    render_header("Validador de Plan", "Detecta problemas en un plan antes de guardarlo en SimpliRoute")

    render_guide(
        steps=[
            '<strong>Token</strong> — Ingresa el token de la cuenta a la que pertenece el plan (se usa para cruzar la capacidad configurada de los vehiculos).',
            '<strong>Sube o pega el plan</strong> — El JSON que devuelve SimpliRoute al finalizar/previsualizar el diseño de rutas (se puede capturar desde el network tab del navegador).',
            '<strong>Revisa el resultado</strong> — Se listan las rutas donde <code>total_load_percentage</code>, <code>total_load_2_percentage</code> o <code>total_load_3_percentage</code> superan 32767, el limite que bloquea el guardado del plan.',
            '<strong>Corrige</strong> — El boton <em>Corregir capacidad(es) de vehiculo(s)</em> actualiza en SimpliRoute la capacidad del vehiculo a la carga asignada + 20% de holgura (nunca la reduce si ya es suficiente).',
        ],
        tip='Este error ocurre casi siempre porque la capacidad del vehiculo (<code>capacity</code>, <code>capacity_2</code> o <code>capacity_3</code>) esta en 0 o mal configurada (ej. =1) comparada con la carga real que se le asigno.',
    )

    render_label("Paso 1 · Token")
    token = campo_token("vp", placeholder="Token de API")
    if not token or not token.strip():
        render_tip("Ingresa el token de la cuenta para poder cruzar los vehiculos y sus capacidades.")
        st.stop()

    valido, cuenta = _validar_cuenta(token)
    if not valido:
        st.error("Token invalido. Revisa tu token de API.")
        return
    render_cuenta_badge(f"✓ Conectado a: <strong>{cuenta}</strong>")

    render_label("Paso 2 · Plan a revisar")
    archivo = st.file_uploader(
        "Archivo del plan (JSON)", type=["json", "txt"],
        label_visibility="collapsed", key="vp_file",
    )
    contenido = archivo.read().decode("utf-8") if archivo is not None else ""
    if not contenido.strip():
        contenido = st.text_area("O pega el JSON del plan", height=150, key="vp_texto")

    if not contenido or not contenido.strip():
        render_tip("Sube el archivo JSON del plan o pega su contenido.")
        st.stop()

    try:
        data = json.loads(_extraer_json_de_texto(contenido))
    except json.JSONDecodeError as e:
        st.error(f"El contenido no es JSON valido ni un comando curl reconocible: {e}")
        st.stop()

    rutas = _extraer_rutas(data)
    if not rutas:
        st.warning("No se encontraron rutas (\"routes\") en el archivo.")
        st.stop()

    vehiculos_info = _obtener_vehiculos(token)
    problemas = _analizar_rutas(rutas, vehiculos_info)

    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(render_stat(len(rutas), "rutas analizadas"), unsafe_allow_html=True)
    with col2:
        color = "#d32f2f" if problemas else "#29AB55"
        st.markdown(
            render_stat(
                len(problemas), "problemas encontrados",
                style=f"background: linear-gradient(135deg, {color} 0%, {color}cc 100%);",
            ),
            unsafe_allow_html=True,
        )

    st.markdown("---")

    if not problemas:
        st.success(f"No se encontraron porcentajes de carga por encima de {MAX_SMALLINT_FIELD}. El plan deberia poder guardarse sin este error.")
        return

    st.error(f"{len(problemas)} ruta(s) con porcentaje de carga fuera de rango (> {MAX_SMALLINT_FIELD}). Esto bloquea el guardado del plan en SimpliRoute.")
    st.dataframe(problemas, use_container_width=True, hide_index=True)
    render_tip(
        f"<strong>Capacidad sugerida</strong> = carga asignada + {round((MARGEN_CAPACIDAD - 1) * 100)}% de holgura, redondeada hacia arriba. "
        "Al corregir, se actualiza el vehiculo completo en SimpliRoute con ese valor.",
        warning=True,
    )

    st.markdown("---")
    if st.button("Corregir capacidad(es) de vehiculo(s)", type="primary", key="vp_btn_corregir"):
        fixes = defaultdict(dict)
        for p in problemas:
            vid = p["ID vehiculo"]
            campo_cap = _CAMPO_CAP_POR_LABEL[p["Campo"]]
            fixes[vid][campo_cap] = max(fixes[vid].get(campo_cap, 0), p["Capacidad sugerida"])

        exitosos = 0
        errores = []
        for vid, campos_nuevos in fixes.items():
            vehiculo_completo = vehiculos_info.get(vid)
            if not vehiculo_completo:
                errores.append(f"Vehiculo {vid}: no se encontro en la cuenta (¿se elimino?)")
                continue
            ok, detalle = _actualizar_capacidades_vehiculo(token, vid, campos_nuevos, vehiculo_completo)
            if ok:
                exitosos += 1
            else:
                errores.append(f"Vehiculo {vehiculo_completo.get('name', vid)}: {detalle}")

        if exitosos:
            st.success(f"{exitosos} de {len(fixes)} vehiculo(s) actualizados correctamente. Vuelve a diseñar/guardar el plan en SimpliRoute para que tome las nuevas capacidades.")
        if errores:
            st.error(f"{len(errores)} vehiculo(s) con error al actualizar")
            for err in errores:
                render_error_item(err)
