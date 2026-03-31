import streamlit as st
import requests
import json
import pandas as pd

API_BASE = "https://api.simpliroute.com/v1"

CONFIGS = [
    {"key": "disable_edit_for_active_and_finished_routes", "label": "Deshabilitar edicion de rutas activas y finalizadas"},
    {"key": "enable_safety_mode", "label": "Habilitar modo de seguridad"},
    {"key": "avoid_edit_checkout_after_route_finished", "label": "Evitar edicion de checkout despues de ruta finalizada"},
]


@st.cache_data
def cargar_cuentas():
    try:
        df = pd.read_csv("cuentas.csv")
        return pd.Series(df.id.astype(str).values, index=df.nombre).to_dict()
    except FileNotFoundError:
        return None


def actualizar_config(account_id, key, value, token):
    url = f"{API_BASE}/accounts/{account_id}/configs/"
    headers = {"Authorization": f"Token {token}", "Content-Type": "application/json"}
    payload = {"key": key, "value": value}
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    return response.status_code


def pagina_bloqueo_lvp():
    # Header
    st.markdown(
        """
        <div class="sr-header">
            <h1>Bloqueo de Ediciones LVP</h1>
            <p>Configuracion de seguridad para cuentas Liverpool</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --- Token desde secrets ---
    try:
        token = st.secrets.api_config.auth_token
    except (AttributeError, KeyError):
        st.error("No se encontro `auth_token` en `.streamlit/secrets.toml`. Configura `[api_config]` con `auth_token`.")
        st.stop()

    # --- Guia de uso ---
    with st.expander("📖 ¿Como funciona? — Guia rapida", expanded=False):
        st.markdown(
            """
            <div class="sr-guide">
                <div class="sr-step">
                    <div class="sr-step-num">1</div>
                    <div class="sr-step-text"><strong>Selecciona la cuenta</strong> — Elige la tienda Liverpool a configurar del listado.</div>
                </div>
                <div class="sr-step">
                    <div class="sr-step-num">2</div>
                    <div class="sr-step-text"><strong>Elige el valor</strong> — <code>True</code> para activar el bloqueo, <code>False</code> para desactivarlo.</div>
                </div>
                <div class="sr-step">
                    <div class="sr-step-num">3</div>
                    <div class="sr-step-text"><strong>Actualiza</strong> — Se envian tres configuraciones: bloqueo de edicion, modo de seguridad y bloqueo de checkout post-finalizacion.</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            """
            <div class="sr-tip">
                <strong>💡 Tip:</strong> Las tres configuraciones se aplican con el mismo valor. Al activar (<code>True</code>), los conductores no podran editar rutas activas ni finalizadas, ni modificar checkouts.
            </div>
            """,
            unsafe_allow_html=True,
        )

    # --- Cargar cuentas ---
    cuentas = cargar_cuentas()
    if cuentas is None:
        st.error("No se encontro el archivo `cuentas.csv`.")
        st.stop()

    # --- Paso 1: Cuenta ---
    st.markdown('<div class="sr-label">Paso 1 · Cuenta Liverpool</div>', unsafe_allow_html=True)
    cuenta_nombre = st.selectbox(
        "Cuenta",
        list(cuentas.keys()),
        label_visibility="collapsed",
    )

    st.markdown(
        f'<div class="sr-cuenta">Cuenta seleccionada: <strong>{cuenta_nombre}</strong> (ID: {cuentas[cuenta_nombre]})</div>',
        unsafe_allow_html=True,
    )

    # --- Paso 2: Valor ---
    st.markdown('<div class="sr-label">Paso 2 · Valor</div>', unsafe_allow_html=True)
    valor = st.radio(
        "Valor",
        ("True", "False"),
        horizontal=True,
        label_visibility="collapsed",
    )

    # Stats
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            f"""
            <div class="sr-stat">
                <div class="sr-stat-number">{len(CONFIGS)}</div>
                <div class="sr-stat-label">configuraciones a aplicar</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col2:
        estado = "Activar bloqueo" if valor == "True" else "Desactivar bloqueo"
        color = "#29AB55" if valor == "True" else "#d32f2f"
        st.markdown(
            f"""
            <div class="sr-stat" style="background: linear-gradient(135deg, {color} 0%, {color}cc 100%);">
                <div class="sr-stat-number" style="font-size:1.1rem;">{estado}</div>
                <div class="sr-stat-label">valor: {valor}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if not st.button(f"Actualizar configuraciones", type="primary", key="btn_bloqueo"):
        st.stop()

    # --- Procesamiento ---
    account_id = cuentas[cuenta_nombre]
    exitosos = 0
    errores = []

    barra = st.progress(0, text="Aplicando configuraciones...")

    for i, config in enumerate(CONFIGS):
        status = actualizar_config(account_id, config["key"], valor, token)
        procesados = i + 1

        if 200 <= status < 300:
            exitosos += 1
        else:
            errores.append({"config": config["label"], "codigo": status})

        barra.progress(procesados / len(CONFIGS), text=f"{procesados}/{len(CONFIGS)} configuraciones aplicadas")

    barra.progress(1.0, text="Finalizado")

    if exitosos > 0:
        st.success(f"{exitosos} de {len(CONFIGS)} configuraciones aplicadas correctamente a {cuenta_nombre}")

    if errores:
        st.error(f"{len(errores)} configuracion(es) con error")
        for err in errores:
            st.markdown(
                f'<div class="sr-result sr-result-err">✗ {err["config"]} — HTTP {err["codigo"]}</div>',
                unsafe_allow_html=True,
            )
