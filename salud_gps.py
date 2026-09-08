import re
import unicodedata
import pandas as pd
import streamlit as st
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from config import API_BASE, REQUEST_TIMEOUT
from utils import (
    render_header, render_guide, render_label, render_tip,
    render_stat, render_error_item, render_cuenta_badge,
)
from account_lookup import campo_token

API_TRACK_BASE = "https://api-track.simpliroute.com/v1"
VEHICLE_MAX_PAGES = 50
TRACKING_CONCURRENCY = 2
MAX_MATCHES = 100
MAX_RANGE_DAYS = 7
GAP_MIN_DEFAULT = 15
GAP_MIN_MIN = 5
GAP_MIN_MAX = 120
TIMESTAMP_KEYS = ["timestamp", "date_time", "datetime", "recorded_at", "gps_date", "created", "date", "time"]


def _headers(token):
    return {"Authorization": f"Token {token}", "Content-Type": "application/json"}


def _validar_cuenta(token):
    try:
        r = requests.get(f"{API_BASE}/accounts/me/", headers=_headers(token), timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            return True, r.json().get("account", {}).get("name", "Sin nombre"), None
        return False, None, f"HTTP {r.status_code}: {r.text[:200]}"
    except requests.exceptions.RequestException as e:
        return False, None, str(e)


# ── Busqueda de vehiculo ──────────────────────────────────────────────────────

def _normalize_text(s):
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[-_\s]+", " ", s.lower()).strip()
    return s


def _normalize_identifier(s):
    return re.sub(r"[^a-z0-9]", "", _normalize_text(s))


def _to_vehicle_match(v):
    vid = v.get("id")
    name = v.get("name")
    if not isinstance(vid, int) or isinstance(vid, bool) or not name or not str(name).strip():
        return None
    return {
        "id": vid,
        "name": str(name).strip(),
        "license_plate": str(v.get("license_plate") or ""),
        "reference_id": str(v.get("reference_id") or ""),
    }


def listar_vehiculos(token):
    vehiculos = []
    url = f"{API_BASE}/routes/vehicles/"
    for _ in range(VEHICLE_MAX_PAGES):
        if not url:
            break
        try:
            r = requests.get(url, headers=_headers(token), timeout=REQUEST_TIMEOUT)
        except requests.exceptions.RequestException as e:
            return vehiculos, str(e)
        if r.status_code != 200:
            return vehiculos, f"HTTP {r.status_code}"
        data = r.json()
        if isinstance(data, list):
            vehiculos.extend(data)
            break
        vehiculos.extend(data.get("results", []))
        url = data.get("next")
    return vehiculos, None


def _rank_vehiculo(v, query_norm, ident_norm):
    ids_norm = [_normalize_identifier(str(v["id"])), _normalize_identifier(v["license_plate"]), _normalize_identifier(v["reference_id"])]
    name_norm = _normalize_text(v["name"])
    if ident_norm and ident_norm in ids_norm:
        return 0
    if query_norm and name_norm == query_norm:
        return 1
    if ident_norm and any(i.startswith(ident_norm) for i in ids_norm if i):
        return 2
    if query_norm and name_norm.startswith(query_norm):
        return 3
    return 4


def _matches_vehiculo(v, query_norm, ident_norm):
    name_norm = _normalize_text(v["name"])
    if query_norm and query_norm in name_norm:
        return True
    if ident_norm:
        for raw in (str(v["id"]), v["license_plate"], v["reference_id"]):
            if ident_norm and ident_norm in _normalize_identifier(raw):
                return True
    return False


def buscar_vehiculos(vehiculos, query):
    matches = [m for m in (_to_vehicle_match(v) for v in vehiculos) if m]
    query_norm = _normalize_text(query)
    ident_norm = _normalize_identifier(query)
    filtrados = [v for v in matches if _matches_vehiculo(v, query_norm, ident_norm)]
    filtrados.sort(key=lambda v: (_rank_vehiculo(v, query_norm, ident_norm), _normalize_text(v["name"]), v["id"]))
    total = len(filtrados)
    return filtrados[:MAX_MATCHES], total, total > MAX_MATCHES


# ── Tracking GPS ──────────────────────────────────────────────────────────────

def _parse_timestamp(point):
    for key in TIMESTAMP_KEYS:
        val = point.get(key)
        if val is None or isinstance(val, bool):
            continue
        if isinstance(val, (int, float)):
            ms = val * 1000 if val < 10_000_000_000 else val
            try:
                return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
            except (ValueError, OverflowError, OSError):
                continue
        if isinstance(val, str):
            ts = pd.to_datetime(val, utc=True, errors="coerce")
            if pd.notna(ts):
                return ts.to_pydatetime()
    return None


def _parse_coord(point, direct_keys, nested_keys):
    for key in direct_keys:
        val = point.get(key)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                pass
    loc = point.get("location")
    if isinstance(loc, dict):
        for key in nested_keys:
            val = loc.get(key)
            if val is not None:
                try:
                    return float(val)
                except (TypeError, ValueError):
                    pass
    return None


def _extraer_puntos(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("results", "locations", "data", "points"):
            val = data.get(key)
            if isinstance(val, list):
                return val
    return None


def _consultar_tracking(fecha_str, vehicle_id, token):
    """Prueba primero el dominio de tracking dedicado; api.simpliroute.com queda como
    fallback por si el path esta tambien expuesto ahi (ver ficha tecnica)."""
    last_err = None
    for base in (API_TRACK_BASE, API_BASE):
        url = f"{base}/tracking/locations/{fecha_str}/"
        try:
            r = requests.get(url, headers=_headers(token), params={"vehicle_id": vehicle_id}, timeout=REQUEST_TIMEOUT)
        except requests.exceptions.RequestException as e:
            last_err = str(e)
            continue
        if r.status_code == 200:
            try:
                return r.json(), None
            except ValueError:
                last_err = "Respuesta no es JSON valido"
                continue
        last_err = f"HTTP {r.status_code}"
    return None, last_err


def _median(values):
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def _dia_vacio(fecha_str):
    return {
        "date": fecha_str, "available": False, "point_count": 0,
        "first_point_at": None, "last_point_at": None,
        "mean_interval": None, "median_interval": None,
        "invalid_coordinates": 0, "invalid_timestamps": 0,
        "gaps": [], "intervals": [],
    }


def _analizar_dia(fecha_str, vehicle_id, token, gap_minutes):
    data, err = _consultar_tracking(fecha_str, vehicle_id, token)
    if err:
        return _dia_vacio(fecha_str), err

    puntos = _extraer_puntos(data)
    if puntos is None:
        return _dia_vacio(fecha_str), "Respuesta invalida (formato no reconocido)"

    timestamps = []
    invalid_coords = 0
    invalid_ts = 0
    for p in puntos:
        if not isinstance(p, dict):
            invalid_coords += 1
            invalid_ts += 1
            continue
        ts = _parse_timestamp(p)
        lat = _parse_coord(p, ("latitude", "lat"), ("latitude", "lat"))
        lon = _parse_coord(p, ("longitude", "lng", "lon"), ("longitude", "lng", "lon"))
        coord_ok = lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180
        if not coord_ok:
            invalid_coords += 1
        if ts is None:
            invalid_ts += 1
        else:
            timestamps.append(ts)

    timestamps.sort()
    intervals = []
    gaps = []
    for i in range(1, len(timestamps)):
        minutes = (timestamps[i] - timestamps[i - 1]).total_seconds() / 60
        intervals.append(minutes)
        if minutes > gap_minutes:
            gaps.append({"start": timestamps[i - 1], "end": timestamps[i], "minutes": round(minutes, 2)})

    return {
        "date": fecha_str,
        "available": True,
        "point_count": len(puntos),
        "first_point_at": timestamps[0] if timestamps else None,
        "last_point_at": timestamps[-1] if timestamps else None,
        "mean_interval": round(sum(intervals) / len(intervals), 2) if intervals else None,
        "median_interval": round(_median(intervals), 2) if intervals else None,
        "invalid_coordinates": invalid_coords,
        "invalid_timestamps": invalid_ts,
        "gaps": gaps,
        "intervals": intervals,
    }, None


def _agregar_resultado(dias):
    disponibles = [d for d in dias if d["available"]]
    firsts = [d["first_point_at"] for d in disponibles if d["first_point_at"]]
    lasts = [d["last_point_at"] for d in disponibles if d["last_point_at"]]
    all_intervals = [m for d in disponibles for m in d["intervals"]]
    gaps_global = [g for d in disponibles for g in d["gaps"]]
    total_points = sum(d["point_count"] for d in disponibles)

    if total_points == 0:
        reception_status = "no_data"
    elif gaps_global:
        reception_status = "interruptions"
    else:
        reception_status = "observed"

    return {
        "status": "partial" if any(not d["available"] for d in dias) else "complete",
        "reception_status": reception_status,
        "point_count": total_points,
        "first_point_at": min(firsts) if firsts else None,
        "last_point_at": max(lasts) if lasts else None,
        "mean_interval": round(sum(all_intervals) / len(all_intervals), 2) if all_intervals else None,
        "median_interval": round(_median(all_intervals), 2) if all_intervals else None,
        "invalid_coordinates": sum(d["invalid_coordinates"] for d in disponibles),
        "invalid_timestamps": sum(d["invalid_timestamps"] for d in disponibles),
        "days_without_data": [d["date"] for d in disponibles if d["point_count"] == 0],
        "gaps": gaps_global,
        "days": dias,
    }


def analizar_vehiculo(token, vehicle_id, fecha_inicio, fecha_fin, gap_minutes):
    fechas = []
    d = fecha_inicio
    while d <= fecha_fin:
        fechas.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)

    dias = [None] * len(fechas)
    warnings = []
    with ThreadPoolExecutor(max_workers=TRACKING_CONCURRENCY) as ex:
        futures = {ex.submit(_analizar_dia, f, vehicle_id, token, gap_minutes): i for i, f in enumerate(fechas)}
        for fut in as_completed(futures):
            i = futures[fut]
            dia, err = fut.result()
            dias[i] = dia
            if err:
                warnings.append(f"No fue posible consultar Tracking {fechas[i]}. ({err})")

    resultado = _agregar_resultado(dias)
    resultado["warnings"] = warnings
    return resultado


# ── UI de resultados ──────────────────────────────────────────────────────────

def _fmt_ts(ts):
    return f"{ts.strftime('%d/%m/%Y %H:%M:%S')} UTC" if ts else "—"


def _render_resultado(resultado):
    status_map = {
        "observed": ("🟢", "Recepcion observada", "#e8f5e9", "#2e7d32"),
        "interruptions": ("🟡", "Recepcion con interrupciones", "#fff8e1", "#f57f17"),
        "no_data": ("⚪", "Sin datos observados", "#f5f5f5", "#616161"),
    }
    icon, label, bg, fg = status_map[resultado["reception_status"]]
    st.markdown(
        f'<div style="background:{bg};color:{fg};padding:0.8rem 1rem;border-radius:8px;font-weight:600;">{icon} {label}</div>',
        unsafe_allow_html=True,
    )
    if resultado["status"] == "partial":
        render_tip("Resultado parcial: uno o mas dias no pudieron consultarse (ver advertencias abajo).", warning=True)

    st.markdown("<div style='height:0.6rem'></div>", unsafe_allow_html=True)
    cols = st.columns(4)
    for col, (num, lbl) in zip(cols, [
        (resultado["point_count"], "Puntos"),
        (_fmt_ts(resultado["first_point_at"]), "Primer punto"),
        (_fmt_ts(resultado["last_point_at"]), "Ultimo punto"),
        (len(resultado["gaps"]), "Interrupciones"),
    ]):
        with col:
            st.markdown(render_stat(num, lbl), unsafe_allow_html=True)

    cols2 = st.columns(4)
    for col, (num, lbl) in zip(cols2, [
        (f"{resultado['mean_interval']} min" if resultado["mean_interval"] is not None else "—", "Intervalo medio"),
        (f"{resultado['median_interval']} min" if resultado["median_interval"] is not None else "—", "Intervalo mediano"),
        (resultado["invalid_coordinates"], "Coordenadas invalidas"),
        (len(resultado["days_without_data"]), "Dias sin datos"),
    ]):
        with col:
            st.markdown(render_stat(num, lbl), unsafe_allow_html=True)

    render_label("Detalle por dia")
    df = pd.DataFrame([
        {
            "Dia": d["date"],
            "Estado": "No disponible" if not d["available"] else ("Sin datos" if d["point_count"] == 0 else "Recibido"),
            "Puntos": d["point_count"],
            "Primero": _fmt_ts(d["first_point_at"]),
            "Ultimo": _fmt_ts(d["last_point_at"]),
            "Mediana (min)": d["median_interval"] if d["median_interval"] is not None else "—",
            "Cortes": len(d["gaps"]),
        }
        for d in resultado["days"]
    ])
    st.dataframe(df, use_container_width=True, hide_index=True)

    if resultado["warnings"]:
        with st.expander(f"Advertencias ({len(resultado['warnings'])})", expanded=True):
            for w in resultado["warnings"]:
                render_error_item(w)

    st.download_button(
        "Descargar detalle (CSV)",
        data=df.to_csv(index=False).encode("utf-8-sig"),
        file_name="salud_gps_detalle.csv",
        mime="text/csv",
        key="gh_descargar_csv",
    )

    render_tip(
        "Este analisis demuestra recepcion observada de tracking. No confirma la configuracion "
        "contractual ni el estado del proveedor GPS."
    )


# ── Entry point ───────────────────────────────────────────────────────────────

def pagina_salud_gps():
    render_header("Salud GPS", "Diagnostica la recepcion de tracking GPS de un vehiculo")
    render_guide(
        steps=[
            "<strong>Ingresa el token</strong> — Token de la cuenta donde esta el vehiculo.",
            "<strong>Busca el vehiculo</strong> — Por nombre, placa, ID o referencia (minimo 2 caracteres).",
            "<strong>Selecciona el vehiculo</strong> — En la tabla de coincidencias.",
            "<strong>Configura el analisis</strong> — Un dia o rango (maximo 7 dias) y umbral de interrupcion en minutos.",
            "<strong>Analiza</strong> — Se descarga el tracking GPS de cada dia y se calculan las metricas de recepcion.",
        ],
        tip="Es una herramienta de solo lectura: no modifica nada en SimpliRoute.",
    )

    render_label("Paso 1 · Token de API")
    token = campo_token("gh", placeholder="Token de API")
    if not token or not token.strip():
        render_tip("Ingresa el token de API de la cuenta.")
        st.stop()
    token = token.strip()

    valido, cuenta, detalle = _validar_cuenta(token)
    if not valido:
        st.error(f"Token invalido. Revisa tu token de API.\n\n{detalle}")
        st.stop()
    render_cuenta_badge(f"✓ Conectado a: <strong>{cuenta}</strong>")

    render_label("Paso 2 · Buscar vehiculo")
    query = st.text_input(
        "Buscar vehiculo", placeholder="Ej. nombre, placa, ID o referencia",
        label_visibility="collapsed", key="gh_query",
    )
    puede_buscar = len(query.strip()) >= 2
    if st.button("Buscar", key="gh_buscar", disabled=not puede_buscar):
        st.session_state.pop("gh_vehiculo_sel", None)
        st.session_state.pop("gh_resultado", None)
        with st.spinner("Consultando vehiculos..."):
            vehiculos, err = listar_vehiculos(token)
        if err:
            st.error(f"Error al consultar vehiculos: {err}")
            st.session_state.pop("gh_matches", None)
        else:
            matches, total, truncated = buscar_vehiculos(vehiculos, query.strip())
            st.session_state.gh_matches = matches
            st.session_state.gh_matches_total = total
            st.session_state.gh_matches_truncated = truncated
    elif query.strip() and not puede_buscar:
        render_tip("Ingresa al menos 2 caracteres para buscar.")

    if "gh_matches" not in st.session_state:
        st.stop()

    matches = st.session_state.gh_matches
    total = st.session_state.gh_matches_total
    truncated = st.session_state.gh_matches_truncated

    st.markdown(render_stat(total, "vehiculo(s) encontrado(s)"), unsafe_allow_html=True)
    if not matches:
        render_tip("No se encontraron vehiculos con ese criterio.")
        st.stop()
    if truncated:
        render_tip(f"Mostrando {MAX_MATCHES} de {total} coincidencias. Refina la busqueda para acotar.", warning=True)

    df_match = pd.DataFrame([
        {"ID": v["id"], "Nombre": v["name"], "Placa": v["license_plate"] or "—", "Referencia": v["reference_id"] or "—"}
        for v in matches
    ])
    event = st.dataframe(
        df_match, use_container_width=True, hide_index=True,
        on_select="rerun", selection_mode="single-row", key="gh_tabla_vehiculos",
    )
    if event.selection.rows:
        nuevo = matches[event.selection.rows[0]]
        anterior = st.session_state.get("gh_vehiculo_sel")
        if not anterior or anterior["id"] != nuevo["id"]:
            st.session_state.pop("gh_resultado", None)
        st.session_state.gh_vehiculo_sel = nuevo

    vehiculo = st.session_state.get("gh_vehiculo_sel")
    if not vehiculo:
        render_tip("Selecciona un vehiculo de la tabla para continuar.")
        st.stop()

    render_cuenta_badge(f"Vehiculo seleccionado: <strong>{vehiculo['name']}</strong> (ID {vehiculo['id']})")

    render_label("Paso 3 · Configurar analisis")
    modo = st.radio("Modo", ["Un dia", "Rango"], key="gh_modo", horizontal=True)
    col1, col2 = st.columns(2)
    with col1:
        fecha_inicio = st.date_input("Fecha inicio", value=date.today(), format="DD/MM/YYYY", key="gh_fecha_inicio")
    if modo == "Rango":
        with col2:
            fecha_fin = st.date_input("Fecha fin", value=date.today(), format="DD/MM/YYYY", key="gh_fecha_fin")
    else:
        fecha_fin = fecha_inicio

    gap_minutes = st.number_input(
        "Interrupcion minima (min)", min_value=GAP_MIN_MIN, max_value=GAP_MIN_MAX,
        value=GAP_MIN_DEFAULT, step=1, key="gh_gap",
    )

    if fecha_fin < fecha_inicio:
        render_tip("La fecha fin no puede ser anterior a la fecha inicio.", warning=True)
        st.stop()
    if (fecha_fin - fecha_inicio).days + 1 > MAX_RANGE_DAYS:
        render_tip("El rango de tracking no puede superar 7 dias.", warning=True)
        st.stop()

    if st.button("Analizar", type="primary", key="gh_analizar"):
        with st.spinner("Verificando vehiculo..."):
            vehiculos_actuales, err = listar_vehiculos(token)
        if err:
            st.error(f"Error al verificar el vehiculo: {err}")
            st.stop()
        ids_actuales = {m["id"] for m in (_to_vehicle_match(v) for v in vehiculos_actuales) if m}
        if vehiculo["id"] not in ids_actuales:
            st.error("No se encontro el vehiculo seleccionado.")
            st.session_state.pop("gh_resultado", None)
            st.stop()
        with st.spinner("Consultando tracking..."):
            resultado = analizar_vehiculo(token, vehiculo["id"], fecha_inicio, fecha_fin, int(gap_minutes))
        st.session_state.gh_resultado = resultado

    if "gh_resultado" not in st.session_state:
        st.stop()

    render_label("Resultado")
    _render_resultado(st.session_state.gh_resultado)
