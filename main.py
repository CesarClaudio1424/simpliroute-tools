import streamlit as st
import requests
import csv
import io
import time
from datetime import datetime
import pandas as pd

st.set_page_config(
    page_title="Edicion Masiva de Visitas",
    page_icon="🚚",
    layout="centered",
)

# --- Tema ---
if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = False

dark = st.session_state.dark_mode

THEME = {
    "bg": "#0e1117" if dark else "#f5f7fb",
    "text": "#e0e0e0" if dark else "#1a1a1a",
    "label": "#7b8cff" if dark else "#2A2BA1",
    "input_border": "#3a3f4b" if dark else "#e0e3ea",
    "input_bg": "#1a1e2a" if dark else "white",
    "input_text": "#e0e0e0" if dark else "#1a1a1a",
    "uploader_border": "#3a3f4b" if dark else "#d0d5dd",
}

# --- Estilos SimpliRoute ---
st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    html, body, [class*="st-"] {{
        font-family: 'Inter', sans-serif;
    }}

    #MainMenu, header, footer {{visibility: hidden;}}

    .stApp {{
        background: {THEME["bg"]};
        color: {THEME["text"]};
    }}

    .block-container {{
        padding-top: 1rem !important;
        padding-bottom: 1rem !important;
    }}

    /* Header */
    .sr-header {{
        background: linear-gradient(135deg, #2A2BA1 0%, #1a1b6b 100%);
        padding: 1.5rem 2rem 1.2rem 2rem;
        border-radius: 0.8rem;
        text-align: center;
        margin-bottom: 1rem;
    }}
    .sr-header h1 {{
        color: white;
        font-size: 1.5rem;
        font-weight: 700;
        margin: 0;
        letter-spacing: -0.02em;
    }}
    .sr-header p {{
        color: rgba(255,255,255,0.7);
        font-size: 0.85rem;
        margin: 0.2rem 0 0 0;
    }}

    /* Cuenta badge */
    .sr-cuenta {{
        background: linear-gradient(135deg, #29AB55 0%, #1e8a42 100%);
        color: white;
        padding: 0.5rem 1rem;
        border-radius: 0.5rem;
        font-size: 0.85rem;
        font-weight: 500;
        margin-bottom: 0.5rem;
    }}

    /* Stat box */
    .sr-stat {{
        background: linear-gradient(135deg, #369CFF 0%, #2A2BA1 100%);
        color: white;
        padding: 0.8rem 1rem;
        border-radius: 0.6rem;
        text-align: center;
        margin-bottom: 0.5rem;
    }}
    .sr-stat-number {{
        font-size: 1.6rem;
        font-weight: 700;
        line-height: 1;
    }}
    .sr-stat-label {{
        font-size: 0.75rem;
        opacity: 0.85;
        margin-top: 0.15rem;
    }}

    /* Label mini */
    .sr-label {{
        font-size: 0.7rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: {THEME["label"]};
        margin-bottom: 0.3rem;
    }}

    /* Solo boton primario con gradiente */
    button[data-testid="stBaseButton-primary"] {{
        background: linear-gradient(135deg, #2A2BA1 0%, #1a1b6b 100%) !important;
        color: white !important;
        border: none !important;
        border-radius: 0.5rem !important;
        padding: 0.6rem 2rem !important;
        font-weight: 600 !important;
        font-size: 0.9rem !important;
        transition: all 0.2s ease !important;
        width: 100% !important;
    }}
    button[data-testid="stBaseButton-primary"]:hover {{
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 12px rgba(42, 43, 161, 0.35) !important;
    }}

    /* Boton toggle tema (solo el del key theme_toggle) */
    [data-testid="stElementToolbarButton"],
    div[data-testid="stVerticalBlock"] > div:first-child button[data-testid="stBaseButton-secondary"][kind="secondary"] {{
        /* fallback: no tocar secondary globalmente */
    }}
    #theme_toggle_btn button[data-testid="stBaseButton-secondary"],
    .stColumn:last-child > div > div > div > button[data-testid="stBaseButton-secondary"] {{
        background: {"rgba(255,255,255,0.1)" if dark else "rgba(42,43,161,0.08)"} !important;
        border: none !important;
        border-radius: 50% !important;
        width: 1.8rem !important;
        height: 1.8rem !important;
        min-height: 0 !important;
        padding: 0 !important;
        font-size: 0.8rem !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    }}
    .stColumn:last-child > div > div > div > button[data-testid="stBaseButton-secondary"]:hover {{
        background: {"rgba(255,255,255,0.2)" if dark else "rgba(42,43,161,0.15)"} !important;
        transform: none !important;
        box-shadow: none !important;
    }}

    /* Boton descargar plantilla */
    .stDownloadButton > button {{
        background: {"rgba(255,255,255,0.06)" if dark else "rgba(42,43,161,0.06)"} !important;
        border: 1.5px dashed {"#3a3f4b" if dark else "#b0b5dd"} !important;
        border-radius: 0.5rem !important;
        padding: 0.5rem 1.2rem !important;
        font-size: 0.82rem !important;
        font-weight: 500 !important;
        color: {THEME["label"]} !important;
        width: 100% !important;
        min-height: 2.4rem !important;
    }}
    .stDownloadButton > button:hover {{
        background: {"rgba(255,255,255,0.1)" if dark else "rgba(42,43,161,0.12)"} !important;
        border-color: #2A2BA1 !important;
    }}

    /* Input fields */
    .stTextInput > div > div > input {{
        border-radius: 0.5rem !important;
        border: 1.5px solid {THEME["input_border"]} !important;
        background: {THEME["input_bg"]} !important;
        color: {THEME["input_text"]} !important;
        padding: 0.6rem 0.8rem !important;
        font-size: 0.9rem !important;
    }}
    .stTextInput > div > div > input:focus {{
        border-color: #2A2BA1 !important;
        box-shadow: 0 0 0 3px rgba(42, 43, 161, 0.15) !important;
    }}

    /* File uploader */
    .stFileUploader > div {{
        border-radius: 0.6rem !important;
        border: 2px dashed {THEME["uploader_border"]} !important;
    }}

    /* Progress bar */
    .stProgress > div > div > div {{
        background: linear-gradient(90deg, #2A2BA1, #369CFF) !important;
        border-radius: 1rem !important;
    }}

    /* Expander */
    .streamlit-expanderHeader {{
        font-size: 0.85rem !important;
        font-weight: 500 !important;
        color: {THEME["label"]} !important;
    }}

    .stElementContainer {{
        margin-bottom: 0.3rem !important;
    }}

    a {{ color: {THEME["label"]} !important; }}

    /* Guia pasos */
    .sr-guide {{
        background: {"#1a1e2a" if dark else "#f0f2ff"};
        border: 1px solid {"#2a2f3f" if dark else "#d0d5ff"};
        border-radius: 0.6rem;
        padding: 1rem 1.2rem;
        margin-bottom: 0.8rem;
    }}
    .sr-guide h4 {{
        color: {THEME["label"]};
        margin: 0 0 0.5rem 0;
        font-size: 0.9rem;
    }}
    .sr-step {{
        display: flex;
        align-items: flex-start;
        gap: 0.6rem;
        margin-bottom: 0.5rem;
    }}
    .sr-step-num {{
        background: linear-gradient(135deg, #2A2BA1 0%, #369CFF 100%);
        color: white;
        width: 1.4rem;
        height: 1.4rem;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 0.7rem;
        font-weight: 700;
        flex-shrink: 0;
        margin-top: 0.1rem;
    }}
    .sr-step-text {{
        font-size: 0.82rem;
        color: {THEME["text"]};
        line-height: 1.4;
    }}
    .sr-step-text strong {{
        color: {THEME["label"]};
    }}

    /* Tabla campos */
    .sr-fields-table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 0.78rem;
        margin-top: 0.5rem;
    }}
    .sr-fields-table th {{
        background: {"#252a3a" if dark else "#e8ebff"};
        color: {THEME["label"]};
        padding: 0.4rem 0.6rem;
        text-align: left;
        font-weight: 600;
        border-bottom: 2px solid {"#3a3f4b" if dark else "#c0c5dd"};
    }}
    .sr-fields-table td {{
        padding: 0.35rem 0.6rem;
        border-bottom: 1px solid {"#2a2f3f" if dark else "#e0e3ea"};
        color: {THEME["text"]};
    }}
    .sr-fields-table tr:hover td {{
        background: {"#1e2233" if dark else "#f5f7ff"};
    }}
    .sr-tag {{
        display: inline-block;
        padding: 0.1rem 0.4rem;
        border-radius: 0.25rem;
        font-size: 0.7rem;
        font-weight: 600;
    }}
    .sr-tag-req {{
        background: #29AB5520;
        color: #29AB55;
    }}
    .sr-tag-opt {{
        background: {"#369CFF20" if dark else "#369CFF15"};
        color: #369CFF;
    }}

    /* Tip box */
    .sr-tip {{
        background: {"#1a2a1e" if dark else "#edf7f0"};
        border-left: 3px solid #29AB55;
        padding: 0.5rem 0.8rem;
        border-radius: 0 0.4rem 0.4rem 0;
        font-size: 0.8rem;
        color: {THEME["text"]};
        margin: 0.5rem 0;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

API_BASE = "https://api.simpliroute.com/v1"

# --- Plantilla CSV de ejemplo ---
PLANTILLA_CAMPOS = [
    {"columna": "id", "tipo": "integer", "req": True, "desc": "ID de la visita en SimpliRoute", "ejemplo": "200189436"},
    {"columna": "title", "tipo": "string", "req": False, "desc": "Nombre / identificador de la entrega", "ejemplo": "Pedido #1234"},
    {"columna": "address", "tipo": "string", "req": False, "desc": "Direccion (formato Google Maps)", "ejemplo": "Av. Providencia 1234, Santiago"},
    {"columna": "planned_date", "tipo": "date", "req": False, "desc": "Fecha planificada (dd/mm/yyyy)", "ejemplo": "15/04/2026"},
    {"columna": "contact_name", "tipo": "string", "req": False, "desc": "Nombre del receptor", "ejemplo": "Juan Perez"},
    {"columna": "contact_phone", "tipo": "string", "req": False, "desc": "Telefono del receptor", "ejemplo": "+56912345678"},
    {"columna": "contact_email", "tipo": "string", "req": False, "desc": "Email del receptor", "ejemplo": "[email protected]"},
    {"columna": "reference", "tipo": "string", "req": False, "desc": "ID interno / numero de orden", "ejemplo": "ORD-5678"},
    {"columna": "notes", "tipo": "string", "req": False, "desc": "Notas para el conductor", "ejemplo": "Dejar en conserjeria"},
    {"columna": "load", "tipo": "number", "req": False, "desc": "Carga principal", "ejemplo": "10"},
    {"columna": "load_2", "tipo": "number", "req": False, "desc": "Carga secundaria", "ejemplo": "5"},
    {"columna": "load_3", "tipo": "number", "req": False, "desc": "Carga terciaria", "ejemplo": "2"},
    {"columna": "window_start", "tipo": "time", "req": False, "desc": "Inicio ventana horaria (HH:mm:ss)", "ejemplo": "09:00:00"},
    {"columna": "window_end", "tipo": "time", "req": False, "desc": "Fin ventana horaria (HH:mm:ss)", "ejemplo": "18:00:00"},
    {"columna": "duration", "tipo": "time", "req": False, "desc": "Tiempo de servicio (HH:mm:ss)", "ejemplo": "00:15:00"},
    {"columna": "latitude", "tipo": "float", "req": False, "desc": "Latitud del destino", "ejemplo": "-33.413433"},
    {"columna": "longitude", "tipo": "float", "req": False, "desc": "Longitud del destino", "ejemplo": "-70.585503"},
    {"columna": "priority_level", "tipo": "integer", "req": False, "desc": "Nivel de prioridad (1-5)", "ejemplo": "3"},
]


def generar_csv_plantilla():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([c["columna"] for c in PLANTILLA_CAMPOS])
    writer.writerow([c["ejemplo"] for c in PLANTILLA_CAMPOS])
    writer.writerow(["200189437", "Pedido #5678", "Los Leones 2345, Providencia", "16/04/2026",
                      "Maria Lopez", "+56987654321", "[email protected]", "ORD-9012",
                      "Llamar antes", "5", "", "", "10:00:00", "14:00:00", "00:10:00",
                      "-33.421958", "-70.607270", "1"])
    return output.getvalue()


def validar_cuenta(token):
    headers = {"Authorization": f"Token {token}", "Content-Type": "application/json"}
    response = requests.get(f"{API_BASE}/accounts/me/", headers=headers)
    if response.status_code == 200:
        nombre = response.json().get("account", {}).get("name", "Sin nombre")
        return True, nombre
    return False, None


def enviar_visitas(bloque, token):
    headers = {"Authorization": f"Token {token}", "Content-Type": "application/json"}
    response = requests.put(f"{API_BASE}/routes/visits/", headers=headers, json=bloque)
    time.sleep(0.5)
    return response.status_code, response.text


def convertir_fecha(fecha_str):
    try:
        return datetime.strptime(fecha_str, "%d/%m/%Y").strftime("%Y-%m-%d")
    except ValueError:
        return fecha_str


def leer_csv(archivo):
    contenido = archivo.read().decode("ISO-8859-1")
    lector = csv.DictReader(io.StringIO(contenido))
    return list(lector)


def calcular_tamano_bloque(total):
    bloque = total // 5
    if bloque >= 500:
        return 500
    if bloque < 1:
        return 1
    return bloque


# --- UI ---

# Toggle tema (esquina derecha)
_, toggle_col = st.columns([20, 1])
with toggle_col:
    icon = "☀️" if dark else "🌙"
    if st.button(icon, key="theme_toggle"):
        st.session_state.dark_mode = not dark
        st.rerun()

# Header
st.markdown(
    """
    <div class="sr-header">
        <h1>Edicion Masiva de Visitas</h1>
        <p>SimpliRoute Tools</p>
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
                <div class="sr-step-text"><strong>Ingresa el token de API</strong> — El token de la cuenta donde estan las visitas. Puedes obtenerlo desde <a href="https://simpliroute.tryretool.com/embedded/public/a11dd57d-c962-441f-b27a-e1ede0a85645" target="_blank">esta herramienta</a>.</div>
            </div>
            <div class="sr-step">
                <div class="sr-step-num">2</div>
                <div class="sr-step-text"><strong>Prepara tu archivo CSV</strong> — Debe tener una columna <code>id</code> (obligatoria) con el ID de cada visita, mas las columnas de los campos que quieras editar. Descarga la plantilla de ejemplo mas abajo.</div>
            </div>
            <div class="sr-step">
                <div class="sr-step-num">3</div>
                <div class="sr-step-text"><strong>Sube el CSV</strong> — La app mostrara una vista previa de los datos cargados para que verifiques antes de procesar.</div>
            </div>
            <div class="sr-step">
                <div class="sr-step-num">4</div>
                <div class="sr-step-text"><strong>Procesa la edicion</strong> — Los datos se envian a SimpliRoute en bloques. Veras el progreso en tiempo real y un resumen al finalizar.</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <div class="sr-tip">
            <strong>💡 Tip:</strong> Solo incluye en el CSV las columnas que necesitas modificar. No es necesario enviar todos los campos — basta con <code>id</code> + los campos a editar.
        </div>
        """,
        unsafe_allow_html=True,
    )

# --- Paso 1: Autenticacion ---
st.markdown('<div class="sr-label">Paso 1 · Token de API</div>', unsafe_allow_html=True)
token = st.text_input("Token", type="password", label_visibility="collapsed", placeholder="Ingresa el token de API")

if token:
    token = token.strip()
    valido, cuenta = validar_cuenta(token)
    if valido:
        st.markdown(
            f'<div class="sr-cuenta">✓ Conectado a: <strong>{cuenta}</strong></div>',
            unsafe_allow_html=True,
        )
    else:
        st.error("Token invalido. Revisa tu token de API.")
        st.stop()
else:
    st.markdown(
        f"""
        <div class="sr-tip">
            Ingresa el token de API de la cuenta a la que pertenecen las visitas. Puedes obtenerlo desde
            <a href="https://simpliroute.tryretool.com/embedded/public/a11dd57d-c962-441f-b27a-e1ede0a85645" target="_blank"><strong>esta herramienta</strong></a>.
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()

# --- Paso 2: Archivo CSV ---
st.markdown('<div class="sr-label">Paso 2 · Archivo CSV</div>', unsafe_allow_html=True)

with st.expander("📋 Formato del CSV y campos disponibles"):
    st.markdown(
        """
        <div class="sr-tip">
            <strong>Importante:</strong> La columna <code>id</code> es <strong>obligatoria</strong> — identifica que visita se va a editar.
            Ademas necesitas al menos una columna mas con el campo que quieras modificar. Las fechas deben ir en formato <code>dd/mm/yyyy</code>.
        </div>
        """,
        unsafe_allow_html=True,
    )
    filas_html = ""
    for campo in PLANTILLA_CAMPOS:
        tag = '<span class="sr-tag sr-tag-req">obligatorio</span>' if campo["req"] else '<span class="sr-tag sr-tag-opt">opcional</span>'
        filas_html += f'<tr><td><code>{campo["columna"]}</code></td><td>{campo["tipo"]}</td><td>{tag}</td><td>{campo["desc"]}</td><td><code>{campo["ejemplo"]}</code></td></tr>'

    st.markdown(
        f"""
        <table class="sr-fields-table">
            <thead><tr><th>Columna</th><th>Tipo</th><th></th><th>Descripcion</th><th>Ejemplo</th></tr></thead>
            <tbody>{filas_html}</tbody>
        </table>
        """,
        unsafe_allow_html=True,
    )

# Descarga de plantilla
st.download_button(
    label="⬇ Descargar plantilla CSV de ejemplo",
    data=generar_csv_plantilla(),
    file_name="plantilla_edicion_visitas.csv",
    mime="text/csv",
)

archivo = st.file_uploader(
    "CSV",
    type=["csv"],
    label_visibility="collapsed",
    help="Sube un archivo CSV con columna 'id' y los campos a editar",
)

if not archivo:
    st.markdown(
        """
        <div class="sr-tip">
            Sube un archivo <strong>.csv</strong> con los datos de las visitas a editar. Puedes descargar la plantilla de ejemplo como referencia.
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()

data = leer_csv(archivo)

if not data:
    st.error("El archivo CSV esta vacio o no se pudo leer.")
    st.stop()

# Validar que exista columna id + al menos un campo a editar
columnas = list(data[0].keys()) if data else []
if "id" not in columnas:
    st.error("El CSV debe tener una columna **id** para identificar las visitas a editar.")
    st.stop()
if len(columnas) < 2:
    st.error("El CSV debe tener al menos una columna ademas de **id** con los datos a editar.")
    st.stop()

# --- Paso 3: Preview y procesamiento ---
st.markdown('<div class="sr-label">Paso 3 · Revisar y procesar</div>', unsafe_allow_html=True)

# Stats
col_stat, col_cols = st.columns(2)
with col_stat:
    st.markdown(
        f"""
        <div class="sr-stat">
            <div class="sr-stat-number">{len(data):,}</div>
            <div class="sr-stat-label">visitas cargadas</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with col_cols:
    st.markdown(
        f"""
        <div class="sr-stat">
            <div class="sr-stat-number">{len(columnas)}</div>
            <div class="sr-stat-label">campos a editar</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown(
    f'<div style="font-size:0.78rem; color:{THEME["label"]}; margin-bottom:0.3rem;">Columnas detectadas: <code>{", ".join(columnas)}</code></div>',
    unsafe_allow_html=True,
)

with st.expander("Vista previa (primeras 20 filas)"):
    st.dataframe(pd.DataFrame(data[:20]), use_container_width=True)

if not st.button("Procesar edicion", type="primary"):
    st.stop()

# Convertir fechas
for registro in data:
    if "planned_date" in registro:
        registro["planned_date"] = convertir_fecha(registro["planned_date"])

total = len(data)
block_size = calcular_tamano_bloque(total)
editadas = 0
errores = []

barra = st.progress(0, text="Procesando...")
estado = st.empty()

for i in range(0, total, block_size):
    bloque = data[i : i + block_size]
    codigo, respuesta = enviar_visitas(bloque, token)

    if codigo == 200:
        editadas += len(bloque)
    else:
        errores.append(
            {"bloque": i // block_size + 1, "codigo": codigo, "detalle": respuesta}
        )

    progreso = min((i + block_size) / total, 1.0)
    barra.progress(progreso, text=f"{editadas}/{total} visitas editadas")

barra.progress(1.0, text="Finalizado")

if editadas > 0:
    estado.success(f"{editadas} visitas editadas correctamente")

if errores:
    st.error(f"{len(errores)} bloque(s) con error")
    for err in errores:
        st.warning(
            f"Bloque {err['bloque']} (HTTP {err['codigo']}): {err['detalle'][:200]}"
        )
