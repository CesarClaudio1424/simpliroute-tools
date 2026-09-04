import re
import time
import unicodedata
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import pandas as pd
import requests
import streamlit as st

from config import API_BASE, REQUEST_TIMEOUT
from utils import (
    render_header, render_guide, render_label, render_stat,
    render_tip, render_error_item, render_cuenta_badge,
)
from account_lookup import campo_token

API_VEHICLES = f"{API_BASE}/routes/vehicles/"
API_FLEETS = f"{API_BASE}/fleets/"
API_DRIVERS = f"{API_BASE}/accounts/drivers/"
API_ZONES = f"{API_BASE}/zones/"
API_SKILLS = f"{API_BASE}/routes/skills/"

MAX_PAGINAS = 50
MAX_PAGINAS_OPERACION = 25
PAGE_SIZE = 100
EXPORT_ROW_LIMIT = 20000
MAX_ASIGNACIONES = 100
AGENDA_MAX_DIAS = 31
AGENDA_WORKERS = 6
AGENDA_TIMEOUT_REQUEST = 8
AGENDA_PRESUPUESTO_TOTAL = 50

ESTADOS_ACTIVOS = {"active", "activo"}
ESTADOS_INACTIVOS = {"inactive", "blocked", "disabled", "inactivo", "bloqueado"}

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.IGNORECASE)
HORA_RE = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$")

FINDING_LABELS = {
    "MISSING_LICENSE_PLATE": ("warning", "Sin placa"),
    "DUPLICATE_LICENSE_PLATE": ("inconsistency", "Placa duplicada"),
    "DUPLICATE_REFERENCE_ID": ("inconsistency", "Reference duplicado"),
    "WITHOUT_FLEET": ("warning", "Sin flota"),
    "WITHOUT_DEFAULT_DRIVER": ("info", "Sin conductor predeterminado"),
    "DEFAULT_DRIVER_NOT_FOUND": ("inconsistency", "Conductor predeterminado no encontrado"),
    "NEGATIVE_CAPACITY": ("inconsistency", "Capacidad negativa"),
    "MIN_LOAD_EXCEEDS_CAPACITY": ("inconsistency", "Carga minima excede capacidad"),
    "INVALID_MAX_VISIT": ("inconsistency", "max_visit invalido"),
    "INCOMPLETE_SHIFT": ("warning", "Jornada incompleta"),
    "INCOMPLETE_REST": ("warning", "Descanso incompleto"),
    "MISSING_COORDINATES": ("warning", "Sin coordenadas"),
    "INACTIVE_VEHICLE": ("warning", "Vehiculo inactivo"),
    "INACTIVE_IN_OPERATION": ("inconsistency", "Vehiculo inactivo con actividad hoy"),
}


# --- helpers genericos ---

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


def _get_all(session, url, max_paginas=MAX_PAGINAS):
    resultados = []
    pagina = 0
    try:
        while url:
            if pagina >= max_paginas:
                return resultados, f"Se supero el limite de {max_paginas} paginas."
            r = session.get(url, timeout=REQUEST_TIMEOUT)
            if r.status_code != 200:
                return resultados, f"HTTP {r.status_code}: {r.text[:300]}"
            data = r.json()
            if isinstance(data, list):
                resultados.extend(data)
                url = None
            else:
                resultados.extend(data.get("results", []))
                url = data.get("next")
            pagina += 1
    except requests.exceptions.RequestException as e:
        return resultados, str(e)
    return resultados, None


def _sin_acentos(s):
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


def _normalizar_busqueda(s):
    s = _sin_acentos(str(s or "").strip().lower())
    return re.sub(r"[-_\s]+", " ", s).strip()


def _normalizar_identificador(s):
    s = _sin_acentos(str(s or "").lower())
    return re.sub(r"[^a-z0-9]", "", s)


def _normalizar_estado(status):
    if not isinstance(status, str):
        return ""
    s = _sin_acentos(status.strip().lower())
    return s.replace("-", "").replace("_", "")


def _integer_identifier(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _integer_ids_from_array(arr):
    ids = []
    if not isinstance(arr, list):
        return ids
    for item in arr:
        val = _integer_identifier(item.get("id")) if isinstance(item, dict) else _integer_identifier(item)
        if val is not None:
            ids.append(val)
    return ids


def _lifecycle_vehiculo(vehiculo):
    if vehiculo.get("deleted") is True:
        return "deleted"
    estado = _normalizar_estado(vehiculo.get("status"))
    if estado in ESTADOS_ACTIVOS:
        return "active"
    if estado in ESTADOS_INACTIVOS:
        return "inactive"
    return "unknown"


def _vehiculo_valido(v):
    vid = _integer_identifier(v.get("id"))
    nombre = v.get("name")
    return vid is not None and isinstance(nombre, str) and nombre.strip() != ""


def _num(v):
    if isinstance(v, bool) or v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# --- construccion del contexto (join vehiculos <-> flotas <-> conductores <-> habilidades) ---

def _cargar_fuente(session, url, max_paginas=MAX_PAGINAS):
    raw, err = _get_all(session, url, max_paginas)
    return raw, err is None, err


def _construir_contexto(token, fecha_operativa):
    session = requests.Session()
    session.headers.update(_headers(token))
    advertencias = []

    vehicles_raw, err = _get_all(session, API_VEHICLES)
    if err:
        return None, [f"No se pudo obtener /routes/vehicles/: {err}"]

    fleets_raw, fleets_ok, err = _cargar_fuente(session, API_FLEETS)
    if not fleets_ok:
        advertencias.append(f"Flotas: {err}")

    drivers_raw, drivers_ok, err = _cargar_fuente(session, API_DRIVERS)
    if not drivers_ok:
        advertencias.append(f"Conductores: {err}")

    skills_raw, skills_ok, err = _cargar_fuente(session, API_SKILLS)
    if not skills_ok:
        advertencias.append(f"Habilidades: {err}")

    operational_by_vid = {}
    operational_ok = fecha_operativa is None
    if fecha_operativa is not None:
        op_raw, operational_ok, err = _cargar_fuente(
            session, f"{API_BASE}/plans/{fecha_operativa}/vehicles/", MAX_PAGINAS_OPERACION,
        )
        if not operational_ok:
            advertencias.append(f"Operacion del dia: {err}")
        else:
            for entry in op_raw:
                vid = _integer_identifier(entry.get("id"))
                if vid is not None and vid not in operational_by_vid:
                    operational_by_vid[vid] = entry

    vehiculos = {}
    for v in vehicles_raw:
        if not _vehiculo_valido(v):
            continue
        vid = _integer_identifier(v["id"])
        if vid not in vehiculos:
            vehiculos[vid] = v

    fleets_by_id = {}
    vehiculo_a_flotas = defaultdict(list)
    if fleets_ok:
        for f in fleets_raw:
            fid = _integer_identifier(f.get("id"))
            if fid is None or fid in fleets_by_id:
                continue
            fleets_by_id[fid] = f
            for vid in _integer_ids_from_array(f.get("vehicles")):
                if vid in vehiculos:
                    vehiculo_a_flotas[vid].append(fid)

    drivers_by_id = {}
    if drivers_ok:
        for d in drivers_raw:
            did = _integer_identifier(d.get("id"))
            if did is not None and did not in drivers_by_id:
                drivers_by_id[did] = d

    skills_by_id = {}
    if skills_ok:
        for sk in skills_raw:
            sid = _integer_identifier(sk.get("id"))
            if sid is not None and sid not in skills_by_id:
                skills_by_id[sid] = sk

    # duplicados de placa/reference normalizados
    placa_grupos = defaultdict(list)
    reference_grupos = defaultdict(list)
    for vid, v in vehiculos.items():
        placa_norm = _normalizar_identificador(v.get("license_plate"))
        if placa_norm:
            placa_grupos[placa_norm].append(vid)
        ref_norm = _normalizar_identificador(v.get("reference_id"))
        if ref_norm:
            reference_grupos[ref_norm].append(vid)
    placas_duplicadas = {vid: [o for o in g if o != vid] for g in placa_grupos.values() if len(g) > 1 for vid in g}
    references_duplicados = {vid: [o for o in g if o != vid] for g in reference_grupos.values() if len(g) > 1 for vid in g}

    return {
        "vehiculos": vehiculos,
        "fleets_ok": fleets_ok, "fleets_by_id": fleets_by_id, "vehiculo_a_flotas": dict(vehiculo_a_flotas),
        "drivers_ok": drivers_ok, "drivers_by_id": drivers_by_id,
        "skills_ok": skills_ok, "skills_by_id": skills_by_id,
        "operational_ok": operational_ok, "operational_by_vid": operational_by_vid,
        "placas_duplicadas": placas_duplicadas, "references_duplicados": references_duplicados,
        "fecha_operativa": fecha_operativa,
        "built_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
    }, advertencias


def _resumen_contexto(ctx):
    activos = inactivos = eliminados = 0
    sin_flota = multi_flota = 0
    sin_habilidades = sin_conductor = 0
    placa_dup = ref_dup = 0

    for vid, v in ctx["vehiculos"].items():
        lc = _lifecycle_vehiculo(v)
        if lc == "active":
            activos += 1
        elif lc == "inactive":
            inactivos += 1
        elif lc == "deleted":
            eliminados += 1
        if ctx["skills_ok"] and not _integer_ids_from_array(v.get("skills")):
            sin_habilidades += 1
        if not v.get("default_driver"):
            sin_conductor += 1
        if vid in ctx["placas_duplicadas"]:
            placa_dup += 1
        if vid in ctx["references_duplicados"]:
            ref_dup += 1

    if ctx["fleets_ok"]:
        for vid in ctx["vehiculos"]:
            n = len(ctx["vehiculo_a_flotas"].get(vid, []))
            if n == 0:
                sin_flota += 1
            elif n > 1:
                multi_flota += 1
    else:
        sin_flota = multi_flota = None

    return {
        "total": len(ctx["vehiculos"]), "activos": activos, "inactivos": inactivos, "eliminados": eliminados,
        "sin_flota": sin_flota, "multi_flota": multi_flota,
        "sin_habilidades": sin_habilidades if ctx["skills_ok"] else None,
        "sin_conductor": sin_conductor,
        "placa_duplicada": placa_dup, "reference_duplicado": ref_dup,
    }


def _filtrar_vehiculos(ctx, texto, estado, flota_id, skill_id, config_faltante, calidad):
    filas = []
    for vid, v in ctx["vehiculos"].items():
        lc = _lifecycle_vehiculo(v)
        if estado != "Todos" and lc != estado:
            continue

        flotas_v = ctx["vehiculo_a_flotas"].get(vid, [])
        if flota_id == "sin_flota":
            if not ctx["fleets_ok"] or flotas_v:
                continue
        elif flota_id not in (None, "Todos"):
            if not ctx["fleets_ok"] or int(flota_id) not in flotas_v:
                continue

        skills_v = _integer_ids_from_array(v.get("skills"))
        if skill_id not in (None, "Todos"):
            if not ctx["skills_ok"] or int(skill_id) not in skills_v:
                continue

        if config_faltante == "sin_flota" and (not ctx["fleets_ok"] or flotas_v):
            continue
        if config_faltante == "multi_flota" and (not ctx["fleets_ok"] or len(flotas_v) <= 1):
            continue
        if config_faltante == "sin_conductor" and v.get("default_driver"):
            continue
        if config_faltante == "sin_habilidades" and (not ctx["skills_ok"] or skills_v):
            continue

        if calidad == "placa_duplicada" and vid not in ctx["placas_duplicadas"]:
            continue
        if calidad == "reference_duplicado" and vid not in ctx["references_duplicados"]:
            continue
        if calidad == "sin_placa" and str(v.get("license_plate") or "").strip():
            continue

        if texto and texto.strip():
            campos = f"{v.get('name')} {v.get('license_plate')} {v.get('reference_id')} {vid}"
            q_texto, q_ident = _normalizar_busqueda(texto), _normalizar_identificador(texto)
            if q_texto not in _normalizar_busqueda(campos) and q_ident not in _normalizar_identificador(campos):
                continue

        op = ctx["operational_by_vid"].get(vid) if ctx["fecha_operativa"] else None
        filas.append({
            "id": vid, "nombre": v.get("name", ""), "placa": v.get("license_plate", ""),
            "reference": v.get("reference_id", ""), "estado": lc,
            "flotas": len(flotas_v) if ctx["fleets_ok"] else None,
            "habilidades": len(skills_v) if ctx["skills_ok"] else None,
            "conductor": bool(v.get("default_driver")),
            "jornada": f"{v.get('shift_start') or '—'} - {v.get('shift_end') or '—'}",
            "carga": v.get("capacity"),
            "rutas_hoy": len(op.get("routes", [])) if op else (None if ctx["fecha_operativa"] else "—"),
        })

    filas.sort(key=lambda f: (_normalizar_busqueda(f["nombre"]), f["id"]))
    return filas


def _findings_vehiculo(ctx, vid, v):
    findings = []

    def _add(code, evidencia=None):
        severidad, titulo = FINDING_LABELS[code]
        findings.append({"code": code, "severity": severidad, "title": titulo, "evidence": evidencia})

    if not str(v.get("license_plate") or "").strip():
        _add("MISSING_LICENSE_PLATE")
    if vid in ctx["placas_duplicadas"]:
        _add("DUPLICATE_LICENSE_PLATE", ctx["placas_duplicadas"][vid])
    if vid in ctx["references_duplicados"]:
        _add("DUPLICATE_REFERENCE_ID", ctx["references_duplicados"][vid])

    if ctx["fleets_ok"] and not ctx["vehiculo_a_flotas"].get(vid):
        _add("WITHOUT_FLEET")

    default_driver_raw = v.get("default_driver")
    default_driver_id = _integer_identifier(
        default_driver_raw.get("id") if isinstance(default_driver_raw, dict) else default_driver_raw
    )
    if not default_driver_id:
        _add("WITHOUT_DEFAULT_DRIVER")
    elif ctx["drivers_ok"] and default_driver_id not in ctx["drivers_by_id"] and not isinstance(default_driver_raw, dict):
        _add("DEFAULT_DRIVER_NOT_FOUND")

    capacidades = [_num(v.get(k)) for k in ("capacity", "capacity_2", "capacity_3")]
    minimos = [_num(v.get(k)) for k in ("min_load", "min_load_2", "min_load_3")]
    if any(c is not None and c < 0 for c in capacidades) or any(m is not None and m < 0 for m in minimos):
        _add("NEGATIVE_CAPACITY")
    else:
        for cap, mn in zip(capacidades, minimos):
            if cap is not None and mn is not None and mn > cap:
                _add("MIN_LOAD_EXCEEDS_CAPACITY", {"capacity": cap, "min_load": mn})
                break

    max_visit = _num(v.get("max_visit"))
    if max_visit is not None and max_visit < 0:
        _add("INVALID_MAX_VISIT")

    tiene_inicio, tiene_fin = bool(v.get("shift_start")), bool(v.get("shift_end"))
    if tiene_inicio != tiene_fin:
        _add("INCOMPLETE_SHIFT")

    rest_fields = [v.get("rest_time_start"), v.get("rest_time_end"), v.get("rest_time_duration")]
    n_rest = sum(1 for r in rest_fields if r)
    if n_rest in (1, 2):
        _add("INCOMPLETE_REST")

    falta_inicio = not v.get("location_start_latitude") or not v.get("location_start_longitude")
    falta_fin = not v.get("location_end_latitude") or not v.get("location_end_longitude")
    if falta_inicio or falta_fin:
        _add("MISSING_COORDINATES")

    lc = _lifecycle_vehiculo(v)
    op = ctx["operational_by_vid"].get(vid) if ctx["fecha_operativa"] else None
    if lc in ("inactive", "deleted"):
        if op and op.get("routes"):
            _add("INACTIVE_IN_OPERATION")
        else:
            _add("INACTIVE_VEHICLE")

    return findings


# --- Agenda de Vehiculos ---

def _comparar_horario(inicio_ruta, fin_ruta, inicio_pedido, fin_pedido):
    if not inicio_pedido or not fin_pedido:
        return "not_requested"

    def _minutos(hhmm):
        m = HORA_RE.match(str(hhmm or ""))
        if not m:
            return None
        h, mi = int(m.group(1)), int(m.group(2))
        return h * 60 + mi

    ir, fr = _minutos(inicio_ruta), _minutos(fin_ruta)
    ip, fp = _minutos(inicio_pedido), _minutos(fin_pedido)
    if ir is None or fr is None or ip is None or fp is None:
        return "unknown"
    if fr <= ir:
        fr += 24 * 60
    if fp <= ip:
        fp += 24 * 60
    return "overlap" if (ir < fp and fr > ip) else "no_overlap"


def _rango_fechas(inicio, fin):
    dias = []
    d = inicio
    while d <= fin:
        dias.append(d)
        d += timedelta(days=1)
    return dias


def _consultar_dia(session, fecha_str):
    try:
        r = session.get(f"{API_BASE}/plans/{fecha_str}/vehicles/", timeout=AGENDA_TIMEOUT_REQUEST)
        if r.status_code != 200:
            return fecha_str, None, f"HTTP {r.status_code}"
        return fecha_str, r.json(), None
    except requests.exceptions.RequestException as e:
        return fecha_str, None, str(e)


def _buscar_agenda(token, vehicle_id, dias, hora_inicio, hora_fin):
    session = requests.Session()
    session.headers.update(_headers(token))

    cobertura = {}
    asignaciones = {}
    inicio_reloj = time.monotonic()

    with ThreadPoolExecutor(max_workers=AGENDA_WORKERS) as ex:
        futuros = {ex.submit(_consultar_dia, session, d.strftime("%Y-%m-%d")): d for d in dias}
        for fut in as_completed(futuros):
            if time.monotonic() - inicio_reloj > AGENDA_PRESUPUESTO_TOTAL:
                fecha_str = futuros[fut].strftime("%Y-%m-%d")
                cobertura[fecha_str] = "unknown"
                continue
            fecha_str, data, err = fut.result()
            if err or data is None:
                cobertura[fecha_str] = "unknown"
                continue

            entradas = data if isinstance(data, list) else data.get("results", [])
            entrada_vehiculo = None
            for entry in entradas:
                if _integer_identifier(entry.get("id")) == vehicle_id:
                    entrada_vehiculo = entry
                    break

            if entrada_vehiculo is None:
                cobertura[fecha_str] = "sin_programacion"
                continue

            rutas = entrada_vehiculo.get("routes") or []
            hubo_ruta = False
            for ruta in rutas:
                rid = ruta.get("id")
                if not isinstance(rid, str) or not UUID_RE.match(rid):
                    continue
                hubo_ruta = True
                if rid not in asignaciones:
                    driver = entrada_vehiculo.get("driver") or {}
                    asignaciones[rid] = {
                        "route_id": rid, "fecha": fecha_str,
                        "plan_id": ruta.get("plan_id"), "plan_nombre": None,
                        "driver_id": _integer_identifier(driver.get("id")) if isinstance(driver, dict) else None,
                        "driver_nombre": driver.get("name") if isinstance(driver, dict) else None,
                        "estimado_inicio": None, "estimado_fin": None, "overlap": "not_requested",
                        "route_vehicle_mismatch": False,
                    }
            cobertura[fecha_str] = "con_programacion" if hubo_ruta else "sin_programacion"

    if len(asignaciones) > MAX_ASIGNACIONES:
        return None, cobertura, f"Se encontraron mas de {MAX_ASIGNACIONES} rutas unicas en el rango — acota el periodo."

    planes_nombres = {}
    for rid, asign in asignaciones.items():
        necesita_detalle = hora_inicio and hora_fin or not asign["plan_id"]
        if not necesita_detalle:
            continue
        try:
            r = session.get(f"{API_BASE}/routes/routes/{rid}/", timeout=REQUEST_TIMEOUT)
            if r.status_code != 200:
                continue
            ruta_detalle = r.json()
        except requests.exceptions.RequestException:
            continue

        if _integer_identifier(ruta_detalle.get("vehicle")) != vehicle_id:
            asign["route_vehicle_mismatch"] = True
            continue

        asign["plan_id"] = asign["plan_id"] or ruta_detalle.get("plan")
        asign["estimado_inicio"] = ruta_detalle.get("estimated_time_start")
        asign["estimado_fin"] = ruta_detalle.get("estimated_time_end")
        asign["overlap"] = _comparar_horario(asign["estimado_inicio"], asign["estimado_fin"], hora_inicio, hora_fin)

    for rid, asign in asignaciones.items():
        pid = asign["plan_id"]
        if not pid:
            continue
        if pid not in planes_nombres:
            try:
                r = session.get(f"{API_BASE}/routes/plans/{pid}/", timeout=REQUEST_TIMEOUT)
                planes_nombres[pid] = r.json().get("name") if r.status_code == 200 else None
            except requests.exceptions.RequestException:
                planes_nombres[pid] = None
        asign["plan_nombre"] = planes_nombres.get(pid)

    return list(asignaciones.values()), cobertura, None


# --- UI: Inventario / Inspector 360 ---

def _tab_inventario():
    render_guide(
        steps=[
            "<strong>Ingresa el token</strong> — Se valida contra <code>/accounts/me/</code>.",
            "<strong>Cargar inventario</strong> — Descarga vehiculos, flotas, conductores y habilidades.",
            "<strong>Filtra</strong> — Por texto, estado, flota, habilidad, configuracion faltante o calidad de identificadores.",
            "<strong>Selecciona una fila</strong> — Abre el Inspector 360 con hallazgos y relaciones del vehiculo.",
            "<strong>Exporta</strong> — Descarga el resultado filtrado (sin paginar) a CSV.",
        ],
        tip="Instantanea al momento de la consulta — no representa historial. Si una fuente falla, los conteos que dependen de ella se muestran como \"—\", nunca como 0.",
    )

    render_label("Token de API")
    token = campo_token("iv", placeholder="Token de API SimpliRoute")
    if not token or not token.strip():
        render_tip("Ingresa el token de la cuenta para continuar.")
        return
    token = token.strip()

    if st.session_state.get("iv_last_token") != token:
        st.session_state.pop("iv_ctx", None)
        st.session_state.pop("iv_selected_id", None)
        st.session_state["iv_last_token"] = token

    ok_cuenta, nombre_cuenta = _validar_cuenta(token)
    if not ok_cuenta:
        st.error("Token invalido o sin acceso a la cuenta.")
        return
    render_cuenta_badge(f"Cuenta: {nombre_cuenta}")

    render_label("Fecha operativa (opcional)")
    fecha_op = st.date_input("Fecha operativa", value=None, key="iv_fecha_operativa", label_visibility="collapsed")

    if st.button("Cargar / Actualizar inventario", type="primary", key="iv_btn_cargar"):
        fecha_str = fecha_op.strftime("%Y-%m-%d") if fecha_op else None
        with st.spinner("Descargando vehiculos, flotas, conductores y habilidades..."):
            ctx, advertencias = _construir_contexto(token, fecha_str)
        if ctx is None:
            for a in advertencias:
                render_error_item(a)
        else:
            st.session_state["iv_ctx"] = ctx
            st.session_state["iv_advertencias"] = advertencias
            st.session_state.pop("iv_selected_id", None)

    ctx = st.session_state.get("iv_ctx")
    if not ctx:
        render_tip('Pulsa "Cargar / Actualizar inventario" para comenzar.')
        return

    st.caption(f"Ultima actualizacion: {ctx['built_at']}")
    for a in st.session_state.get("iv_advertencias", []):
        render_tip(f"<strong>Fuente parcial:</strong> {a}", warning=True)

    resumen = _resumen_contexto(ctx)
    fila1 = st.columns(4)
    for c, (n, l) in zip(fila1, [
        (resumen["total"], "Vehiculos"), (resumen["activos"], "Activos"),
        (resumen["inactivos"], "Inactivos"), (resumen["eliminados"], "Eliminados"),
    ]):
        with c:
            st.markdown(render_stat(n, l), unsafe_allow_html=True)
    fila2 = st.columns(4)
    for c, (n, l) in zip(fila2, [
        (resumen["sin_flota"] if resumen["sin_flota"] is not None else "—", "Sin flota"),
        (resumen["multi_flota"] if resumen["multi_flota"] is not None else "—", "En varias flotas"),
        (resumen["placa_duplicada"], "Placa duplicada"),
        (resumen["reference_duplicado"], "Reference duplicado"),
    ]):
        with c:
            st.markdown(render_stat(n, l), unsafe_allow_html=True)

    render_label("Filtros")
    col1, col2, col3 = st.columns(3)
    with col1:
        texto = st.text_input("Buscar", key="iv_filtro_texto", placeholder="Nombre, placa, reference o ID...")
    with col2:
        estado = st.selectbox("Estado", ["Todos", "active", "inactive", "deleted", "unknown"], key="iv_filtro_estado")
    with col3:
        opciones_flota = ["Todos", "sin_flota"] + (list(ctx["fleets_by_id"].keys()) if ctx["fleets_ok"] else [])
        flota_sel = st.selectbox(
            "Flota", opciones_flota, key="iv_filtro_flota",
            format_func=lambda f: {"Todos": "Todos", "sin_flota": "Sin flota"}.get(
                f, ctx["fleets_by_id"].get(f, {}).get("name", f"Flota {f}") if isinstance(f, int) else f,
            ),
        )

    col4, col5 = st.columns(2)
    with col4:
        opciones_skill = ["Todos"] + (list(ctx["skills_by_id"].keys()) if ctx["skills_ok"] else [])
        skill_sel = st.selectbox(
            "Habilidad", opciones_skill, key="iv_filtro_skill",
            format_func=lambda s: "Todos" if s == "Todos" else ctx["skills_by_id"].get(s, {}).get("name", f"Habilidad {s}"),
        )
    with col5:
        calidad_sel = st.selectbox(
            "Calidad de identificadores", ["Todos", "placa_duplicada", "reference_duplicado", "sin_placa"],
            key="iv_filtro_calidad",
            format_func=lambda c: {
                "Todos": "Todos", "placa_duplicada": "Placa duplicada",
                "reference_duplicado": "Reference duplicado", "sin_placa": "Sin placa",
            }[c],
        )
    config_sel = st.selectbox(
        "Configuracion faltante", ["Todos", "sin_flota", "multi_flota", "sin_conductor", "sin_habilidades"],
        key="iv_filtro_config",
        format_func=lambda c: {
            "Todos": "Todos", "sin_flota": "Sin flota", "multi_flota": "En varias flotas",
            "sin_conductor": "Sin conductor predeterminado", "sin_habilidades": "Sin habilidades",
        }[c],
    )

    filas = _filtrar_vehiculos(ctx, texto, estado, flota_sel, skill_sel, config_sel, calidad_sel)

    render_label(f"Resultado — {len(filas)} vehiculo(s)")
    if not filas:
        render_tip("Ningun vehiculo coincide con los filtros actuales.")
    else:
        pagina_key = "iv_pagina"
        total_paginas = max(1, (len(filas) + PAGE_SIZE - 1) // PAGE_SIZE)
        pagina_actual = min(st.session_state.get(pagina_key, 0), total_paginas - 1)

        col_prev, col_info, col_next = st.columns([1, 2, 1])
        with col_prev:
            if st.button("← Anterior", disabled=pagina_actual <= 0, key="iv_prev"):
                st.session_state[pagina_key] = pagina_actual - 1
                st.rerun()
        with col_info:
            st.markdown(f"<div style='text-align:center;'>Pagina {pagina_actual + 1} de {total_paginas}</div>", unsafe_allow_html=True)
        with col_next:
            if st.button("Siguiente →", disabled=pagina_actual >= total_paginas - 1, key="iv_next"):
                st.session_state[pagina_key] = pagina_actual + 1
                st.rerun()

        pagina_filas = filas[pagina_actual * PAGE_SIZE:(pagina_actual + 1) * PAGE_SIZE]
        df = pd.DataFrame([{
            "_id": f["id"], "Nombre": f["nombre"], "Placa": f["placa"], "Reference": f["reference"],
            "Estado": f["estado"], "Flotas": f["flotas"] if f["flotas"] is not None else "—",
            "Habilidades": f["habilidades"] if f["habilidades"] is not None else "—",
            "Conductor": "Si" if f["conductor"] else "No", "Jornada": f["jornada"],
            "Carga": f["carga"] if f["carga"] is not None else "—",
            "Rutas hoy": f["rutas_hoy"] if f["rutas_hoy"] is not None else "—",
        } for f in pagina_filas])
        event = st.dataframe(
            df.drop(columns=["_id"]), on_select="rerun", selection_mode="single-row",
            use_container_width=True, hide_index=True, key="iv_tabla",
        )
        if event.selection.rows:
            st.session_state["iv_selected_id"] = pagina_filas[event.selection.rows[0]]["id"]

        st.markdown("&nbsp;", unsafe_allow_html=True)
        if len(filas) > EXPORT_ROW_LIMIT:
            st.error(f"El resultado tiene {len(filas)} filas, supera el limite de exportacion ({EXPORT_ROW_LIMIT}). Acota los filtros.")
        else:
            columnas = [
                "ID", "Nombre", "Placa", "Reference", "Estado", "Flotas", "Habilidades",
                "Conductor predeterminado", "Jornada", "Carga", "Rutas hoy",
            ]
            filas_export = [{
                "ID": f["id"], "Nombre": f["nombre"], "Placa": f["placa"], "Reference": f["reference"],
                "Estado": f["estado"], "Flotas": f["flotas"] if f["flotas"] is not None else "N/D",
                "Habilidades": f["habilidades"] if f["habilidades"] is not None else "N/D",
                "Conductor predeterminado": "Si" if f["conductor"] else "No", "Jornada": f["jornada"],
                "Carga": f["carga"] if f["carga"] is not None else "", "Rutas hoy": f["rutas_hoy"] if f["rutas_hoy"] is not None else "N/D",
            } for f in filas]
            csv_bytes = pd.DataFrame(filas_export, columns=columnas).to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "Exportar CSV", data=csv_bytes, file_name="simpliroute-inventario-vehiculos.csv",
                mime="text/csv", key="iv_export",
            )

    vid_sel = st.session_state.get("iv_selected_id")
    if vid_sel is not None and vid_sel in ctx["vehiculos"]:
        st.markdown("---")
        _detalle_360(ctx, vid_sel)


def _detalle_360(ctx, vid):
    v = ctx["vehiculos"][vid]
    render_label(f"Inspector 360 — {v.get('name', vid)}")
    if st.button("Cerrar detalle", key="iv_cerrar_detalle"):
        st.session_state.pop("iv_selected_id", None)
        st.rerun()

    cols = st.columns(4)
    flotas_v = ctx["vehiculo_a_flotas"].get(vid, [])
    nombres_flotas = ", ".join(ctx["fleets_by_id"].get(f, {}).get("name", str(f)) for f in flotas_v) or "Sin flota"
    with cols[0]:
        st.markdown(render_stat(len(flotas_v) if ctx["fleets_ok"] else "—", "Flotas"), unsafe_allow_html=True)
    with cols[1]:
        default_driver_raw = v.get("default_driver")
        did = _integer_identifier(default_driver_raw.get("id") if isinstance(default_driver_raw, dict) else default_driver_raw)
        conductor_nombre = "Sin asignar"
        if did:
            conductor_nombre = ctx["drivers_by_id"].get(did, {}).get("name") or (
                default_driver_raw.get("name") if isinstance(default_driver_raw, dict) else f"ID {did}"
            )
        st.markdown(render_stat(conductor_nombre, "Conductor predeterminado", number_style="font-size:1rem;"), unsafe_allow_html=True)
    with cols[2]:
        skills_v = _integer_ids_from_array(v.get("skills"))
        st.markdown(render_stat(len(skills_v) if ctx["skills_ok"] else "—", "Habilidades"), unsafe_allow_html=True)
    with cols[3]:
        op = ctx["operational_by_vid"].get(vid) if ctx["fecha_operativa"] else None
        rutas_hoy = len(op.get("routes", [])) if op else ("—" if not ctx["fecha_operativa"] else 0)
        st.markdown(render_stat(rutas_hoy, "Rutas hoy"), unsafe_allow_html=True)

    st.caption(f"Flotas: {nombres_flotas}")

    render_label("Hallazgos")
    findings = _findings_vehiculo(ctx, vid, v)
    if not findings:
        render_tip("Sin hallazgos para este vehiculo.")
    for f in findings:
        icono = {"inconsistency": "🔴", "warning": "🟡", "info": "🔵"}[f["severity"]]
        texto = f"{icono} {f['title']}"
        if f["evidence"]:
            texto += f" — {f['evidence']}"
        if f["severity"] == "inconsistency":
            st.error(texto)
        elif f["severity"] == "warning":
            st.warning(texto)
        else:
            st.info(texto)

    with st.expander("Ver JSON crudo del vehiculo"):
        st.json(v)

    st.caption("Instantanea al momento de la consulta. No representa historial.")


# --- UI: Agenda de Vehiculos ---

def _tab_agenda():
    render_guide(
        steps=[
            "<strong>Buscar vehiculo</strong> — Escribe al menos 2 caracteres (nombre, placa, reference o ID).",
            "<strong>Elige el rango</strong> — Un dia o hasta 31 dias; opcionalmente compara contra un horario.",
            "<strong>Consultar</strong> — Se revisa dia por dia (en paralelo) en que rutas aparece el vehiculo.",
            "<strong>Detalle</strong> — Selecciona una asignacion para ver la ruta y el plan completos.",
        ],
        tip="Un dia sin programacion observada no es lo mismo que un dia que no se pudo consultar — se muestran por separado.",
    )

    render_label("Token de API")
    token = campo_token("veh", placeholder="Token de API SimpliRoute")
    if not token or not token.strip():
        render_tip("Ingresa el token de la cuenta para continuar.")
        return
    token = token.strip()

    ok_cuenta, nombre_cuenta = _validar_cuenta(token)
    if not ok_cuenta:
        st.error("Token invalido o sin acceso a la cuenta.")
        return
    render_cuenta_badge(f"Cuenta: {nombre_cuenta}")

    render_label("Paso 1 · Buscar vehiculo")
    query = st.text_input("Buscar vehiculo", key="veh_query", placeholder="Nombre, placa, reference o ID...", label_visibility="collapsed")

    if len(query.strip()) >= 2:
        cache_key = f"veh_catalogo_{token[:12]}"
        if cache_key not in st.session_state:
            session = requests.Session()
            session.headers.update(_headers(token))
            vehicles_raw, err = _get_all(session, API_VEHICLES)
            if err:
                st.error(f"No se pudo consultar vehiculos: {err}")
                st.session_state[cache_key] = []
            else:
                st.session_state[cache_key] = [v for v in vehicles_raw if _vehiculo_valido(v)]

        catalogo = st.session_state.get(cache_key, [])
        q_texto, q_ident = _normalizar_busqueda(query), _normalizar_identificador(query)

        def _rank(v):
            campos_ident = _normalizar_identificador(f"{v.get('id')}{v.get('license_plate')}{v.get('reference_id')}")
            nombre_norm = _normalizar_busqueda(v.get("name"))
            if q_ident and q_ident == campos_ident:
                return 0
            if q_texto == nombre_norm:
                return 1
            if campos_ident.startswith(q_ident) and q_ident:
                return 2
            if nombre_norm.startswith(q_texto):
                return 3
            return 4

        coincidencias = [v for v in catalogo if q_texto in _normalizar_busqueda(
            f"{v.get('name')} {v.get('license_plate')} {v.get('reference_id')} {v.get('id')}"
        )]
        coincidencias.sort(key=_rank)

        for v in coincidencias[:15]:
            label = f"{v.get('name')} · {v.get('license_plate') or 's/placa'} (#{v.get('id')})"
            if st.button(label, key=f"veh_pick_{v.get('id')}", use_container_width=True):
                st.session_state["veh_selected"] = v
                st.session_state.pop("veh_resultado", None)
                st.rerun()

    vehiculo_sel = st.session_state.get("veh_selected")
    if not vehiculo_sel:
        render_tip("Busca y selecciona un vehiculo para continuar.")
        return

    render_cuenta_badge(f"Vehiculo seleccionado: <strong>{vehiculo_sel.get('name')}</strong> (#{vehiculo_sel.get('id')})")

    render_label("Paso 2 · Fecha y horario")
    modo = st.radio("Modo", ["Un dia", "Rango"], horizontal=True, key="veh_modo", label_visibility="collapsed")
    if modo == "Un dia":
        fecha_unica = st.date_input("Fecha", key="veh_fecha_unica")
        inicio_rango, fin_rango = fecha_unica, fecha_unica
    else:
        col_a, col_b = st.columns(2)
        with col_a:
            inicio_rango = st.date_input("Desde", key="veh_desde")
        with col_b:
            fin_rango = st.date_input("Hasta", key="veh_hasta")

    comparar_horario = st.checkbox("Comparar contra un horario", key="veh_comparar_horario")
    hora_inicio = hora_fin = None
    if comparar_horario:
        col_h1, col_h2 = st.columns(2)
        with col_h1:
            hora_inicio = st.time_input("Hora inicial", key="veh_hora_inicio")
        with col_h2:
            hora_fin = st.time_input("Hora final", key="veh_hora_fin")

    if inicio_rango > fin_rango:
        render_tip("<strong>⚠️ Atencion:</strong> la fecha inicial no puede ser posterior a la final.", warning=True)
        return
    if (fin_rango - inicio_rango).days + 1 > AGENDA_MAX_DIAS:
        render_tip(f"<strong>⚠️ Atencion:</strong> el rango no puede superar {AGENDA_MAX_DIAS} dias.", warning=True)
        return

    if st.button("Consultar agenda", type="primary", key="veh_btn_consultar"):
        dias = _rango_fechas(inicio_rango, fin_rango)
        hi = hora_inicio.strftime("%H:%M") if hora_inicio else None
        hf = hora_fin.strftime("%H:%M") if hora_fin else None
        with st.spinner(f"Consultando {len(dias)} dia(s)..."):
            asignaciones, cobertura, error = _buscar_agenda(token, vehiculo_sel["id"], dias, hi, hf)
        if error:
            render_error_item(error)
        else:
            st.session_state["veh_resultado"] = {"asignaciones": asignaciones, "cobertura": cobertura}

    resultado = st.session_state.get("veh_resultado")
    if not resultado:
        return

    asignaciones, cobertura = resultado["asignaciones"], resultado["cobertura"]
    con_prog = sum(1 for v in cobertura.values() if v == "con_programacion")
    sin_prog = sum(1 for v in cobertura.values() if v == "sin_programacion")
    desconocidos = sum(1 for v in cobertura.values() if v == "unknown")
    planes_unicos = len({a["plan_id"] for a in asignaciones if a["plan_id"]})
    coincidencias = sum(1 for a in asignaciones if a["overlap"] == "overlap")
    indeterminados = sum(1 for a in asignaciones if a["overlap"] == "unknown")

    render_label("Resumen")
    fila1 = st.columns(4)
    for c, (n, l) in zip(fila1, [
        (len(cobertura), "Dias respondidos"), (con_prog, "Con programacion"),
        (sin_prog, "Sin programacion observada"), (desconocidos, "Desconocidos"),
    ]):
        with c:
            st.markdown(render_stat(n, l), unsafe_allow_html=True)
    fila2 = st.columns(4)
    for c, (n, l) in zip(fila2, [
        (planes_unicos, "Planes unicos"), (len(asignaciones), "Rutas unicas"),
        (coincidencias, "Coincidencias horarias"), (indeterminados, "Horarios indeterminados"),
    ]):
        with c:
            st.markdown(render_stat(n, l), unsafe_allow_html=True)

    render_label("Cobertura por dia")
    cols_cob = st.columns(min(7, max(1, len(cobertura))))
    iconos = {"con_programacion": "🟢", "sin_programacion": "⚪", "unknown": "❓"}
    for i, (fecha_str, estado_dia) in enumerate(sorted(cobertura.items())):
        with cols_cob[i % len(cols_cob)]:
            st.markdown(f"{iconos[estado_dia]} {fecha_str}")

    render_label("Asignaciones")
    if not asignaciones:
        render_tip("El vehiculo no aparece en ninguna ruta del periodo consultado.")
    else:
        overlap_labels = {"not_requested": "No solicitado", "overlap": "Coincide", "no_overlap": "No coincide", "unknown": "Indeterminado"}
        df = pd.DataFrame([{
            "_route_id": a["route_id"],
            "Fecha": a["fecha"], "Plan": a["plan_nombre"] or (a["plan_id"] or "—"),
            "Ruta": a["route_id"][:8], "Conductor": a["driver_nombre"] or "—",
            "Estimado": f"{a['estimado_inicio'] or '—'} - {a['estimado_fin'] or '—'}",
            "Estado": "No coincide con vehiculo" if a["route_vehicle_mismatch"] else "OK",
            "Horario": overlap_labels[a["overlap"]],
        } for a in asignaciones])
        event = st.dataframe(
            df.drop(columns=["_route_id"]), on_select="rerun", selection_mode="single-row",
            use_container_width=True, hide_index=True, key="veh_tabla_asignaciones",
        )
        if event.selection.rows:
            st.session_state["veh_selected_route"] = df.iloc[event.selection.rows[0]]["_route_id"]

    route_id_sel = st.session_state.get("veh_selected_route")
    if route_id_sel:
        st.markdown("---")
        render_label("Detalle de la asignacion")
        session = requests.Session()
        session.headers.update(_headers(token))
        try:
            r = session.get(f"{API_BASE}/routes/routes/{route_id_sel}/", timeout=REQUEST_TIMEOUT)
        except requests.exceptions.RequestException as e:
            st.error(f"Error de conexion: {e}")
            r = None
        if r is not None and r.status_code == 200:
            ruta = r.json()
            if _integer_identifier(ruta.get("vehicle")) != vehiculo_sel["id"]:
                st.error("Esta ruta ya no corresponde al vehiculo seleccionado.")
            else:
                with st.expander("Ruta (JSON)", expanded=True):
                    st.json(ruta)
                plan_id = ruta.get("plan")
                if plan_id:
                    try:
                        rp = session.get(f"{API_BASE}/routes/plans/{plan_id}/", timeout=REQUEST_TIMEOUT)
                        if rp.status_code == 200:
                            with st.expander("Plan (JSON)"):
                                st.json(rp.json())
                    except requests.exceptions.RequestException:
                        render_tip("No se pudo consultar el plan.", warning=True)
        elif r is not None:
            st.error(f"No se pudo consultar la ruta (HTTP {r.status_code}).")


def pagina_inspector_vehiculos():
    render_header("Inspector de Vehiculos", "Inventario correlacionado, Inspector 360 y Agenda por vehiculo (solo lectura)")

    tab_inventario, tab_agenda = st.tabs(["Inventario / Inspector 360", "Agenda de Vehiculos"])
    with tab_inventario:
        _tab_inventario()
    with tab_agenda:
        _tab_agenda()
