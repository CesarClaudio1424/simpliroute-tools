import xml.etree.ElementTree as ET
import requests
import streamlit as st
from config import REQUEST_TIMEOUT
from utils import (
    render_header, render_guide, render_label, render_tip,
    render_error_item, create_progress_tracker, update_progress, finish_progress,
    render_stat,
)

# KML namespaces to try
_KML_NS = [
    "http://www.opengis.net/kml/2.2",
    "http://earth.google.com/kml/2.2",
    "http://earth.google.com/kml/2.1",
    "",
]


def _find(element, tag, namespaces):
    for ns in namespaces:
        prefix = f"{{{ns}}}" if ns else ""
        found = element.find(f".//{prefix}{tag}")
        if found is not None:
            return found
    return None


def _findall(element, tag, namespaces):
    results = []
    for ns in namespaces:
        prefix = f"{{{ns}}}" if ns else ""
        results.extend(element.findall(f".//{prefix}{tag}"))
    return results


def _parse_kml_bytes(content: bytes) -> list[dict]:
    """Parse KML content and return list of zone dicts with kml_name, attrs, coords."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        raise ValueError(f"KML invalido: {e}")

    # Detect namespace from root tag
    ns_used = ""
    if root.tag.startswith("{"):
        ns_used = root.tag[1:root.tag.index("}")]
    ns_list = [ns_used] + [n for n in _KML_NS if n != ns_used]

    placemarks = _findall(root, "Placemark", ns_list)
    zones = []

    for pm in placemarks:
        # Name
        name_el = _find(pm, "name", ns_list)
        kml_name = (name_el.text or "").strip() if name_el is not None else ""

        # Extended attributes (Data or SimpleData)
        attrs = {}
        for data_el in _findall(pm, "Data", ns_list):
            key = data_el.get("name", "")
            val_el = _find(data_el, "value", ns_list)
            if key and val_el is not None and val_el.text:
                attrs[key] = val_el.text.strip()
        for sd_el in _findall(pm, "SimpleData", ns_list):
            key = sd_el.get("name", "")
            if key and sd_el.text:
                attrs[key] = sd_el.text.strip()

        # Coordinates (Polygon or LineString or Point — only Polygon makes sense for zones)
        coords_el = _find(pm, "coordinates", ns_list)
        if coords_el is None or not coords_el.text:
            continue

        coords = []
        for point in coords_el.text.strip().split():
            parts = point.split(",")
            if len(parts) >= 2:
                try:
                    lng = str(float(parts[0]))
                    lat = str(float(parts[1]))
                    coords.append({"lat": lat, "lng": lng})
                except ValueError:
                    continue

        if len(coords) < 3:
            continue

        zones.append({"kml_name": kml_name, "attrs": attrs, "coords": coords})

    return zones


def _format_coordinates(coords: list[dict]) -> str:
    """Convert list of {lat, lng} dicts to SimpliRoute coordinates string."""
    parts = [f"{{'lat': '{c['lat']}','lng': '{c['lng']}'}}" for c in coords]
    return "[" + ",".join(parts) + "]"


def _apply_name_template(zone: dict, template: str, index: int) -> str:
    """Apply naming template to a zone. Supports {field} placeholders and {n} for index."""
    name = template
    for key, val in zone["attrs"].items():
        name = name.replace(f"{{{key}}}", val)
    name = name.replace("{kml_name}", zone["kml_name"])
    name = name.replace("{n}", str(index))
    return name.strip() or f"Zona {index}"


def _crear_zona(token: str, name: str, coordinates: str) -> tuple[bool, str]:
    """POST a single zone to SimpliRoute."""
    headers = {
        "Authorization": f"Token {token}",
        "Content-Type": "application/json;charset=UTF-8",
        "accept": "application/json, text/plain, */*",
    }
    payload = {"name": name, "coordinates": coordinates, "vehicles": []}
    try:
        resp = requests.post(
            "https://api.simpliroute.com/v1/zones/",
            headers=headers,
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code in (200, 201):
            return True, ""
        return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
    except requests.exceptions.RequestException as e:
        return False, f"Error de conexion: {e}"


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

def pagina_zonas_kml():
    render_header("Zonas KML", "Carga poligonos desde archivos KML y crealos como zonas en SimpliRoute")

    render_guide(
        steps=[
            "<strong>Token</strong> — Ingresa el token de la cuenta donde se crearan las zonas.",
            "<strong>Sube el KML</strong> — Exporta el archivo desde Google My Maps u otra herramienta. Puede tener multiples poligonos.",
            "<strong>Configura el nombre</strong> — Usa los atributos del KML (ej. <code>{Zona} - {Ruta}</code>) o elige nombres genericos secuenciales.",
            "<strong>Revisa el preview</strong> — Confirma los nombres y cantidad de puntos antes de enviar.",
            "<strong>Crea las zonas</strong> — Se envian una por una a la API. Solo se muestran los errores.",
        ],
        tip="El archivo KML puede venir de Google My Maps (Exportar capa > KML). Cada poligono del KML se convierte en una zona de SimpliRoute.",
    )

    # --- Token ---
    render_label("Token de API")
    token = st.text_input("Token", type="password", placeholder="5d1fe9e...", label_visibility="collapsed", key="kml_token")
    if not token:
        render_tip("Ingresa el token de la cuenta SimpliRoute donde se crearan las zonas.")
        st.stop()

    # --- Upload KML ---
    render_label("Archivo KML")
    kml_file = st.file_uploader("Subir KML", type=["kml"], label_visibility="collapsed", key="kml_file")
    if kml_file is None:
        render_tip("Sube un archivo KML. Puede tener multiples poligonos (uno por Placemark).")
        st.stop()

    try:
        zones = _parse_kml_bytes(kml_file.read())
    except ValueError as e:
        st.error(str(e))
        st.stop()

    if not zones:
        st.warning("No se encontraron poligonos validos en el KML. Verifica que el archivo tenga Placemarks con coordenadas de poligono.")
        st.stop()

    # Collect all attribute keys present in this KML
    all_attr_keys = []
    seen = set()
    for z in zones:
        for k in z["attrs"]:
            if k not in seen:
                all_attr_keys.append(k)
                seen.add(k)

    st.markdown(
        render_stat(len(zones), "poligonos encontrados"),
        unsafe_allow_html=True,
    )

    # --- Name configuration ---
    st.markdown("---")
    render_label("Configuracion de nombres")

    modo_nombre = st.radio(
        "Modo de nombre",
        ["Usar atributos del KML", "Nombre generico secuencial"],
        horizontal=True,
        label_visibility="collapsed",
        key="kml_modo_nombre",
    )

    if modo_nombre == "Usar atributos del KML":
        if all_attr_keys:
            campos_disponibles = ", ".join(f"`{{{k}}}`" for k in all_attr_keys)
            if "kml_name" not in seen:
                campos_disponibles += ", `{kml_name}`"
            render_tip(f"Campos disponibles: {campos_disponibles}. Usa `{{n}}` para el numero de secuencia.")
        else:
            render_tip("El KML no tiene atributos extendidos. Solo puedes usar `{kml_name}` (nombre del Placemark) y `{n}` (numero de secuencia).")

        template = st.text_input(
            "Plantilla de nombre",
            value="{kml_name}" if not all_attr_keys else (f"{{{all_attr_keys[0]}}}" if len(all_attr_keys) == 1 else f"{{{all_attr_keys[0]}}} - {{{all_attr_keys[1]}}}"),
            placeholder="{Zona} - {Ruta}",
            label_visibility="collapsed",
            key="kml_template",
        )

        nombres_finales = [_apply_name_template(z, template, i + 1) for i, z in enumerate(zones)]

    else:
        col_pref, col_start = st.columns([3, 1])
        with col_pref:
            prefijo = st.text_input("Prefijo", value="Zona", label_visibility="visible", key="kml_prefijo")
        with col_start:
            inicio = st.number_input("Inicio", value=1, min_value=1, step=1, label_visibility="visible", key="kml_inicio")

        nombres_finales = [f"{prefijo} {i + int(inicio)}" for i in range(len(zones))]

    # --- Preview ---
    st.markdown("---")
    render_label("Preview de zonas")

    preview_data = []
    for i, (z, nombre) in enumerate(zip(zones, nombres_finales)):
        preview_data.append({
            "N°": i + 1,
            "Nombre": nombre,
            "Puntos": len(z["coords"]),
            "Atributos": ", ".join(f"{k}: {v}" for k, v in z["attrs"].items()) if z["attrs"] else z["kml_name"],
        })

    st.dataframe(preview_data, use_container_width=True, hide_index=True)

    # Check for duplicate or empty names
    nombres_vacios = [i + 1 for i, n in enumerate(nombres_finales) if not n.strip()]
    nombres_duplicados = [n for n in nombres_finales if nombres_finales.count(n) > 1]

    if nombres_vacios:
        render_tip(f"<strong>⚠️ Atencion:</strong> Las zonas {nombres_vacios} tienen nombre vacio. Ajusta la plantilla.", warning=True)
    if nombres_duplicados:
        uniq_dup = list(dict.fromkeys(nombres_duplicados))
        render_tip(f"<strong>⚠️ Atencion:</strong> Hay nombres duplicados: {uniq_dup}. SimpliRoute puede rechazarlos.", warning=True)

    # --- Crear zonas ---
    st.markdown("---")
    if not st.button("Crear zonas en SimpliRoute", type="primary", key="btn_crear_zonas"):
        st.stop()

    total = len(zones)
    exitosos = 0
    barra, contador, contenedor_errores = create_progress_tracker(total, "Creando zonas...")

    for i, (z, nombre) in enumerate(zip(zones, nombres_finales)):
        coords_str = _format_coordinates(z["coords"])
        ok, detalle = _crear_zona(token, nombre, coords_str)
        procesados = i + 1

        if ok:
            exitosos += 1
        else:
            with contenedor_errores:
                render_error_item(f"Zona {procesados} «{nombre}» — {detalle}")

        update_progress(barra, contador, procesados, total, "Creando zonas...")

    finish_progress(barra)

    if exitosos == total:
        st.success(f"Todas las zonas creadas correctamente ({exitosos}/{total})")
    elif exitosos > 0:
        st.warning(f"{exitosos} de {total} zonas creadas. Revisa los errores arriba.")
    else:
        st.error(f"No se pudo crear ninguna zona. Revisa el token y los errores.")
