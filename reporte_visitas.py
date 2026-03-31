import streamlit as st
import requests
from datetime import datetime, timedelta
import time

API_VISITS_BASE = "https://api.simpliroute.com/v1/reports/visits"
API_ROUTES_BASE = "https://api-gateway.simpliroute.com/v1/reports/routes"


def dividir_rango_por_dias(inicio, final, dias):
    rangos = []
    while inicio <= final:
        fin_intervalo = inicio + timedelta(days=dias - 1)
        if fin_intervalo > final:
            fin_intervalo = final
        rangos.append((inicio.strftime("%Y-%m-%d"), fin_intervalo.strftime("%Y-%m-%d")))
        inicio = fin_intervalo + timedelta(days=1)
    return rangos


def dividir_rango_por_mes(inicio, final):
    rangos = []
    while inicio <= final:
        siguiente_mes = inicio.replace(day=28) + timedelta(days=4)
        ultimo_dia_mes = siguiente_mes - timedelta(days=siguiente_mes.day)
        fin_mes = min(ultimo_dia_mes, final)
        rangos.append((inicio.strftime("%Y-%m-%d"), fin_mes.strftime("%Y-%m-%d")))
        inicio = fin_mes + timedelta(days=1)
    return rangos


def enviar_reporte(base_url, headers, inicio, final, correo):
    url = f"{base_url}/from/{inicio}/to/{final}/?email={correo}"
    response = requests.get(url, headers=headers)
    return response.status_code, response.text


def pagina_reporte_visitas():
    # Header
    st.markdown(
        """
        <div class="sr-header">
            <h1>Reporte de Visitas y Rutas</h1>
            <p>Genera reportes por rango de fechas y recibelos por correo</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --- Guia de uso ---
    with st.expander("📖 ¿Como funciona? — Guia rapida", expanded=False):
        st.markdown(
            """
            <div class="sr-guide">
                <div class="sr-step">
                    <div class="sr-step-num">1</div>
                    <div class="sr-step-text"><strong>Selecciona el tipo de reporte</strong> — Visitas o Rutas. Cada uno consulta un endpoint distinto de SimpliRoute.</div>
                </div>
                <div class="sr-step">
                    <div class="sr-step-num">2</div>
                    <div class="sr-step-text"><strong>Ingresa token y correo</strong> — El token de la cuenta y el correo donde recibiras los reportes.</div>
                </div>
                <div class="sr-step">
                    <div class="sr-step-num">3</div>
                    <div class="sr-step-text"><strong>Define el rango de fechas</strong> — Elige fecha de inicio, fecha final y como dividir el rango (semanal, quincenal o mensual).</div>
                </div>
                <div class="sr-step">
                    <div class="sr-step-num">4</div>
                    <div class="sr-step-text"><strong>Genera el reporte</strong> — Se envia una solicitud por cada sub-intervalo. Los reportes llegan a tu correo.</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            """
            <div class="sr-tip">
                <strong>💡 Tip:</strong> Para rangos largos, dividir en intervalos mas cortos evita timeouts y genera reportes mas manejables. Hay una pausa de 3 segundos entre cada solicitud.
            </div>
            """,
            unsafe_allow_html=True,
        )

    # --- Paso 1: Tipo de reporte ---
    st.markdown('<div class="sr-label">Paso 1 · Tipo de reporte</div>', unsafe_allow_html=True)
    tipo_reporte = st.radio(
        "Tipo de reporte",
        ("Visitas", "Rutas"),
        horizontal=True,
        label_visibility="collapsed",
    )

    # --- Paso 2: Token y correo ---
    st.markdown('<div class="sr-label">Paso 2 · Token y correo</div>', unsafe_allow_html=True)
    token = st.text_input("Token", type="password", label_visibility="collapsed", placeholder="Token de API", key="rep_token")

    if not token or not token.strip():
        st.markdown(
            """
            <div class="sr-tip">
                Ingresa el token de API de la cuenta. Puedes obtenerlo desde
                <a href="https://simpliroute.tryretool.com/embedded/public/a11dd57d-c962-441f-b27a-e1ede0a85645" target="_blank"><strong>esta herramienta</strong></a>.
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.stop()

    token = token.strip()

    correo = st.text_input("Correo", label_visibility="collapsed", placeholder="Correo para recibir los reportes", key="rep_correo")

    if not correo or not correo.strip():
        st.markdown(
            """
            <div class="sr-tip">
                Ingresa el correo donde recibiras los reportes.
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.stop()

    correo = correo.strip()

    # --- Paso 3: Fechas e intervalo ---
    st.markdown('<div class="sr-label">Paso 3 · Rango de fechas</div>', unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        fecha_inicio = st.date_input("Fecha de inicio", value=datetime.today() - timedelta(days=7), key="rep_inicio")
    with col2:
        fecha_final = st.date_input("Fecha final", value=datetime.today(), key="rep_final")

    if fecha_inicio > fecha_final:
        st.markdown(
            """
            <div class="sr-tip" style="border-left-color: #d32f2f;">
                <strong>⚠️ Atencion:</strong> La fecha de inicio no puede ser posterior a la fecha final.
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.stop()

    st.markdown('<div class="sr-label">Intervalo de division</div>', unsafe_allow_html=True)
    intervalo = st.radio(
        "Intervalo",
        ("Semanal", "Quincenal", "Mensual"),
        horizontal=True,
        label_visibility="collapsed",
    )

    # Calcular rangos para stats
    if intervalo == "Semanal":
        rangos = dividir_rango_por_dias(fecha_inicio, fecha_final, 7)
    elif intervalo == "Quincenal":
        rangos = dividir_rango_por_dias(fecha_inicio, fecha_final, 15)
    else:
        rangos = dividir_rango_por_mes(fecha_inicio, fecha_final)

    # Stats
    col_stat1, col_stat2 = st.columns(2)
    with col_stat1:
        st.markdown(
            f"""
            <div class="sr-stat">
                <div class="sr-stat-number">{len(rangos)}</div>
                <div class="sr-stat-label">{"solicitud" if len(rangos) == 1 else "solicitudes"} a enviar</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col_stat2:
        st.markdown(
            f"""
            <div class="sr-stat">
                <div class="sr-stat-number">{tipo_reporte}</div>
                <div class="sr-stat-label">tipo de reporte</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if not st.button("Generar reporte", type="primary", key="btn_reporte"):
        st.stop()

    # --- Procesamiento ---
    if tipo_reporte == "Visitas":
        base_url = API_VISITS_BASE
        headers = {
            "authorization": f"Token {token}",
            "origin": "https://app2.simpliroute.com",
            "referer": "https://app2.simpliroute.com/",
            "accept": "application/json",
            "user-agent": "Mozilla/5.0",
        }
    else:
        base_url = API_ROUTES_BASE
        headers = {
            "authorization": f"Token {token}",
            "origin": "https://app3.simpliroute.com",
            "referer": "https://app3.simpliroute.com/",
            "accept": "application/json",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
        }

    total = len(rangos)
    exitosos = 0
    fallidos = []

    col_barra, col_contador = st.columns([5, 1])
    with col_barra:
        barra = st.progress(0, text="Enviando solicitudes...")
    with col_contador:
        contador = st.empty()
        contador.markdown(
            f'<div class="sr-stat" style="padding:0.4rem 0.6rem;"><div class="sr-stat-number" style="font-size:1.1rem;">0/{total}</div></div>',
            unsafe_allow_html=True,
        )

    contenedor_errores = st.container()

    for i, (inicio_rango, final_rango) in enumerate(rangos):
        status, body = enviar_reporte(base_url, headers, inicio_rango, final_rango, correo)
        procesados = i + 1

        if 200 <= status < 300:
            exitosos += 1
        else:
            fallidos.append((inicio_rango, final_rango, status))
            with contenedor_errores:
                st.markdown(
                    f'<div class="sr-result sr-result-err">✗ {inicio_rango} a {final_rango} — HTTP {status}</div>',
                    unsafe_allow_html=True,
                )

        barra.progress(procesados / total, text="Enviando solicitudes...")
        contador.markdown(
            f'<div class="sr-stat" style="padding:0.4rem 0.6rem;"><div class="sr-stat-number" style="font-size:1.1rem;">{procesados}/{total}</div></div>',
            unsafe_allow_html=True,
        )

        if procesados < total:
            time.sleep(3)

    barra.progress(1.0, text="Finalizado")

    if exitosos > 0:
        st.success(f"{exitosos} de {total} reportes solicitados correctamente. Revisa tu correo.")
    if fallidos:
        st.error(f"{len(fallidos)} de {total} solicitudes fallaron")
