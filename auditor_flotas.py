import re
import unicodedata
from collections import defaultdict
from datetime import datetime

import pandas as pd
import requests
import streamlit as st

from config import API_BASE, REQUEST_TIMEOUT
from utils import (
    render_header, render_guide, render_label, render_stat,
    render_tip, render_error_item, render_cuenta_badge,
)
from account_lookup import campo_token

API_FLEETS = f"{API_BASE}/fleets/"
API_VEHICLES = f"{API_BASE}/routes/vehicles/"
API_DRIVERS = f"{API_BASE}/accounts/drivers/"

MAX_PAGINAS = 50
FINDING_SAMPLE_LIMIT = 50
EXPORT_ROW_LIMIT = 20000

ESTADOS_ACTIVOS = {"active", "activo"}
ESTADOS_INACTIVOS = {"inactive", "blocked", "disabled", "inactivo", "bloqueado"}

# severity: "inconsistency" pesa mas que "warning" en la salud de una flota
FINDING_DEFS = {
    "ORPHAN_VEHICLE_REFERENCE": {
        "severity": "inconsistency", "title": "Vehiculo referenciado no existe",
        "description": "La flota referencia un vehiculo que no existe (o no tiene nombre) en /routes/vehicles/.",
    },
    "DELETED_VEHICLE_ASSIGNED": {
        "severity": "inconsistency", "title": "Vehiculo eliminado asignado",
        "description": "La flota tiene asignado un vehiculo marcado como eliminado (deleted=true).",
    },
    "DUPLICATE_VEHICLE_RELATION": {
        "severity": "inconsistency", "title": "Vehiculo duplicado en la flota",
        "description": "El mismo vehiculo aparece mas de una vez en el array vehicles de la flota.",
    },
    "INACTIVE_VEHICLE_ASSIGNED": {
        "severity": "warning", "title": "Vehiculo inactivo asignado",
        "description": "La flota tiene asignado un vehiculo con estado inactivo/bloqueado.",
    },
    "VEHICLE_WITHOUT_FLEET": {
        "severity": "warning", "title": "Vehiculo sin flota",
        "description": "El vehiculo existe pero no esta asignado a ninguna flota.",
    },
    "VEHICLE_IN_MULTIPLE_FLEETS": {
        "severity": "warning", "title": "Vehiculo en varias flotas",
        "description": "El vehiculo esta asignado a mas de una flota al mismo tiempo.",
    },
    "EMPTY_FLEET": {
        "severity": "warning", "title": "Flota vacia",
        "description": "La flota no tiene ningun vehiculo asignado (tras deduplicar).",
    },
    "UNRESOLVED_USER_REFERENCE": {
        "severity": "warning", "title": "Usuario no encontrado",
        "description": "La flota referencia un usuario que no aparece en /accounts/drivers/.",
    },
    "DUPLICATE_USER_RELATION": {
        "severity": "warning", "title": "Usuario duplicado en la flota",
        "description": "El mismo usuario aparece mas de una vez en el array users de la flota.",
    },
}

SALUD_LABELS = {"healthy": "Sana", "warning": "Advertencia", "inconsistency": "Inconsistencia"}


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


def _get_all(session, url):
    resultados = []
    pagina = 0
    try:
        while url and pagina < MAX_PAGINAS:
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


def _unicos(lst):
    vistos = set()
    out = []
    for x in lst:
        if x not in vistos:
            vistos.add(x)
            out.append(x)
    return out


def _duplicados(lst):
    conteo = {}
    dups = []
    for x in lst:
        conteo[x] = conteo.get(x, 0) + 1
        if conteo[x] > 1:
            dups.append(x)
    return dups


def _display_name(obj, fallback):
    for campo in ("name", "skill", "username", "title"):
        val = obj.get(campo)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return fallback


def _lifecycle_vehiculo(vehiculo):
    if vehiculo.get("deleted") is True:
        return "deleted"
    estado = _normalizar_estado(vehiculo.get("status"))
    if estado in ESTADOS_ACTIVOS:
        return "active"
    if estado in ESTADOS_INACTIVOS:
        return "inactive"
    return "unknown"


def _construir_flotas(fleets_raw):
    vistos = set()
    flotas = {}
    orden = []
    for f in fleets_raw:
        fid = _integer_identifier(f.get("id"))
        if fid is None or fid in vistos:
            continue
        vistos.add(fid)
        veh_raw = _integer_ids_from_array(f.get("vehicles"))
        usr_raw = _integer_ids_from_array(f.get("users"))
        flotas[fid] = {
            "id": fid,
            "name": _display_name(f, f"Flota {fid}"),
            "raw": f,
            "vehicle_ids_raw": veh_raw,
            "vehicle_ids_unique": _unicos(veh_raw),
            "user_ids_raw": usr_raw,
            "user_ids_unique": _unicos(usr_raw),
        }
        orden.append(fid)
    return flotas, orden


def _construir_vehiculos(vehicles_raw):
    vistos = set()
    vehiculos = {}
    for v in vehicles_raw:
        vid = _integer_identifier(v.get("id"))
        if vid is None or vid in vistos:
            continue
        vistos.add(vid)
        nombre = v.get("name")
        if not isinstance(nombre, str) or not nombre.strip():
            continue
        vehiculos[vid] = v
    return vehiculos


def _construir_drivers(drivers_raw):
    ids = set()
    for d in drivers_raw:
        did = _integer_identifier(d.get("id"))
        if did is not None:
            ids.add(did)
    return ids


def _construir_snapshot(fleets_raw, vehicles_raw, drivers_raw, drivers_ok):
    flotas, orden_flotas = _construir_flotas(fleets_raw)
    vehiculos = _construir_vehiculos(vehicles_raw)
    drivers_ids = _construir_drivers(drivers_raw) if drivers_ok else set()

    occurrences = defaultdict(list)
    vehiculo_a_flotas = defaultdict(list)

    def _add(code, key, label, fleet_ids=(), vehicle_ids=(), user_ids=()):
        occurrences[code].append({
            "key": key, "label": label,
            "fleetIds": list(fleet_ids), "vehicleIds": list(vehicle_ids), "userIds": list(user_ids),
        })

    for fid in orden_flotas:
        f = flotas[fid]
        fname = f["name"]

        for vid in f["vehicle_ids_unique"]:
            vehiculo = vehiculos.get(vid)
            if vehiculo is None:
                _add("ORPHAN_VEHICLE_REFERENCE", f"fleet:{fid}:vehicle:{vid}",
                     f"Vehiculo {vid} · {fname}", fleet_ids=[fid], vehicle_ids=[vid])
                continue
            vehiculo_a_flotas[vid].append(fid)
            lifecycle = _lifecycle_vehiculo(vehiculo)
            vnombre = vehiculo.get("name")
            if lifecycle == "deleted":
                _add("DELETED_VEHICLE_ASSIGNED", f"fleet:{fid}:vehicle:{vid}:deleted",
                     f"{vnombre} (eliminado) · {fname}", fleet_ids=[fid], vehicle_ids=[vid])
            elif lifecycle == "inactive":
                _add("INACTIVE_VEHICLE_ASSIGNED", f"fleet:{fid}:vehicle:{vid}:inactivo",
                     f"{vnombre} (inactivo) · {fname}", fleet_ids=[fid], vehicle_ids=[vid])

        for n, vid in enumerate(_duplicados(f["vehicle_ids_raw"])):
            _add("DUPLICATE_VEHICLE_RELATION", f"fleet:{fid}:vehicle:{vid}:dup:{n}",
                 f"Vehiculo {vid} duplicado en {fname}", fleet_ids=[fid], vehicle_ids=[vid])

        if drivers_ok:
            for uid in f["user_ids_unique"]:
                if uid not in drivers_ids:
                    _add("UNRESOLVED_USER_REFERENCE", f"fleet:{fid}:user:{uid}",
                         f"Usuario {uid} no encontrado · {fname}", fleet_ids=[fid], user_ids=[uid])

        for n, uid in enumerate(_duplicados(f["user_ids_raw"])):
            _add("DUPLICATE_USER_RELATION", f"fleet:{fid}:user:{uid}:dup:{n}",
                 f"Usuario {uid} duplicado en {fname}", fleet_ids=[fid], user_ids=[uid])

        if not f["vehicle_ids_unique"]:
            _add("EMPTY_FLEET", f"fleet:{fid}:empty", f"{fname} sin vehiculos", fleet_ids=[fid])

    for vid, vehiculo in vehiculos.items():
        flotas_del_vehiculo = vehiculo_a_flotas.get(vid, [])
        vnombre = vehiculo.get("name")
        if not flotas_del_vehiculo:
            _add("VEHICLE_WITHOUT_FLEET", f"vehicle:{vid}:sin-flota", f"{vnombre} sin flota", vehicle_ids=[vid])
        elif len(flotas_del_vehiculo) > 1:
            _add("VEHICLE_IN_MULTIPLE_FLEETS", f"vehicle:{vid}:multi",
                 f"{vnombre} en {len(flotas_del_vehiculo)} flotas", fleet_ids=flotas_del_vehiculo, vehicle_ids=[vid])

    salud = {fid: "healthy" for fid in flotas}
    flotas_por_hallazgo = defaultdict(set)
    for code, samples in occurrences.items():
        severidad = FINDING_DEFS[code]["severity"]
        for s in samples:
            for fid in s["fleetIds"]:
                flotas_por_hallazgo[code].add(fid)
                if fid not in salud:
                    continue
                if severidad == "inconsistency":
                    salud[fid] = "inconsistency"
                elif salud[fid] == "healthy":
                    salud[fid] = "warning"

    stats_flota = {}
    for fid, f in flotas.items():
        def _contar(code, fid=fid):
            return sum(1 for s in occurrences.get(code, []) if fid in s["fleetIds"])
        stats_flota[fid] = {
            "vehiculos": len(f["vehicle_ids_unique"]),
            "usuarios": len(f["user_ids_unique"]),
            "huerfanos": _contar("ORPHAN_VEHICLE_REFERENCE"),
            "eliminados": _contar("DELETED_VEHICLE_ASSIGNED"),
            "inactivos": _contar("INACTIVE_VEHICLE_ASSIGNED"),
            "dup_vehiculo": _contar("DUPLICATE_VEHICLE_RELATION"),
            "dup_usuario": _contar("DUPLICATE_USER_RELATION"),
            "no_resueltos": _contar("UNRESOLVED_USER_REFERENCE") if drivers_ok else None,
        }

    grupos = []
    orden_severidad = {"inconsistency": 0, "warning": 1}
    for code, meta in FINDING_DEFS.items():
        samples = occurrences.get(code, [])
        if not samples:
            continue
        grupos.append({
            "code": code, "title": meta["title"], "description": meta["description"],
            "severity": meta["severity"], "total": len(samples),
            "samples": samples[:FINDING_SAMPLE_LIMIT],
            "truncated": len(samples) > FINDING_SAMPLE_LIMIT,
        })
    grupos.sort(key=lambda g: (orden_severidad.get(g["severity"], 2), g["title"]))

    resumen = {
        "flotas": len(flotas),
        "saludables": sum(1 for h in salud.values() if h == "healthy"),
        "advertencias": sum(1 for h in salud.values() if h == "warning"),
        "inconsistencias": sum(1 for h in salud.values() if h == "inconsistency"),
        "vehiculos": len(vehiculos),
        "sin_flota": len(occurrences.get("VEHICLE_WITHOUT_FLEET", [])),
        "multi_flota": len(occurrences.get("VEHICLE_IN_MULTIPLE_FLEETS", [])),
        "huerfanas": len(occurrences.get("ORPHAN_VEHICLE_REFERENCE", [])),
        "no_resueltos": len(occurrences.get("UNRESOLVED_USER_REFERENCE", [])) if drivers_ok else None,
    }

    return {
        "flotas": flotas, "vehiculos": vehiculos, "drivers_ok": drivers_ok, "drivers_ids": drivers_ids,
        "occurrences": dict(occurrences), "grupos": grupos, "salud": salud,
        "stats_flota": stats_flota, "flotas_por_hallazgo": dict(flotas_por_hallazgo), "resumen": resumen,
    }


def _cargar_snapshot(token):
    session = requests.Session()
    session.headers.update(_headers(token))

    fleets_raw, err = _get_all(session, API_FLEETS)
    if err:
        return None, f"No se pudo obtener /fleets/: {err}"

    vehicles_raw, err = _get_all(session, API_VEHICLES)
    if err:
        return None, f"No se pudo obtener /routes/vehicles/: {err}"

    drivers_raw, drivers_err = _get_all(session, API_DRIVERS)
    drivers_ok = drivers_err is None
    warning = {"source": "Usuarios", "message": "No fue posible consultar esta fuente."} if not drivers_ok else None

    snapshot = _construir_snapshot(fleets_raw, vehicles_raw, drivers_raw, drivers_ok)
    snapshot["warning"] = warning
    snapshot["built_at"] = datetime.now().strftime("%d/%m/%Y %H:%M")
    return snapshot, None


def _dataset_hallazgos(occurrences, fleet_id=None, finding_code=None):
    filas = []
    for code, meta in FINDING_DEFS.items():
        if finding_code and code != finding_code:
            continue
        for s in occurrences.get(code, []):
            if fleet_id is not None and fleet_id not in s["fleetIds"]:
                continue
            filas.append({
                "severity": meta["severity"], "code": code, "title": meta["title"],
                "description": meta["description"], "label": s["label"],
                "fleet_ids": ";".join(str(x) for x in s["fleetIds"]),
                "vehicle_ids": ";".join(str(x) for x in s["vehicleIds"]),
                "user_ids": ";".join(str(x) for x in s["userIds"]),
            })
    return filas


def _dataset_relaciones(flotas, vehiculos, fleet_filter=None):
    filas = []
    universo = {fleet_filter: flotas[fleet_filter]} if fleet_filter is not None else flotas
    for fid, f in universo.items():
        conteo_raw = {}
        for vid in f["vehicle_ids_raw"]:
            conteo_raw[vid] = conteo_raw.get(vid, 0) + 1
        for vid in f["vehicle_ids_unique"]:
            vehiculo = vehiculos.get(vid)
            if vehiculo is None:
                status = "orphan"
            elif conteo_raw.get(vid, 0) > 1:
                status = "duplicate"
            else:
                status = "assigned"
            filas.append({
                "fleet_id": fid, "fleet_name": f["name"], "vehicle_id": vid,
                "vehicle_name": vehiculo.get("name") if vehiculo else "",
                "relation_status": status,
            })

    if fleet_filter is None:
        asignados = {vid for f in flotas.values() for vid in f["vehicle_ids_unique"]}
        for vid, vehiculo in vehiculos.items():
            if vid in asignados or _lifecycle_vehiculo(vehiculo) != "active":
                continue
            filas.append({
                "fleet_id": "", "fleet_name": "", "vehicle_id": vid,
                "vehicle_name": vehiculo.get("name"), "relation_status": "unassigned",
            })
    return filas


def _seccion_exportar(snapshot, fleet_id, finding_code):
    col1, col2 = st.columns(2)
    with col1:
        filas = _dataset_hallazgos(snapshot["occurrences"], fleet_id=fleet_id, finding_code=finding_code)
        if len(filas) > EXPORT_ROW_LIMIT:
            st.error(f"Hay {len(filas)} hallazgos, supera el limite de exportacion ({EXPORT_ROW_LIMIT}). Filtra por flota o tipo de hallazgo.")
        else:
            csv_bytes = pd.DataFrame(filas).to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "Descargar Hallazgos CSV", data=csv_bytes,
                file_name="simpliroute-hallazgos-flotas.csv", mime="text/csv",
                key=f"af_export_hallazgos_{fleet_id}_{finding_code}",
                disabled=not filas, use_container_width=True,
            )
    with col2:
        filas_r = _dataset_relaciones(snapshot["flotas"], snapshot["vehiculos"], fleet_filter=fleet_id)
        if len(filas_r) > EXPORT_ROW_LIMIT:
            st.error(f"Hay {len(filas_r)} relaciones, supera el limite de exportacion ({EXPORT_ROW_LIMIT}). Filtra por flota.")
        else:
            csv_bytes_r = pd.DataFrame(filas_r).to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "Descargar Relaciones CSV", data=csv_bytes_r,
                file_name="simpliroute-relaciones-flotas.csv", mime="text/csv",
                key=f"af_export_relaciones_{fleet_id}",
                disabled=not filas_r, use_container_width=True,
            )


def _vista_auditoria_global(snapshot):
    resumen = snapshot["resumen"]

    render_label("Auditoria global")
    fila1 = st.columns(4)
    for c, (n, l) in zip(fila1, [
        (resumen["flotas"], "Flotas"), (resumen["saludables"], "Saludables"),
        (resumen["advertencias"], "Advertencias"), (resumen["inconsistencias"], "Inconsistencias"),
    ]):
        with c:
            st.markdown(render_stat(n, l), unsafe_allow_html=True)

    fila2 = st.columns(4)
    for c, (n, l) in zip(fila2, [
        (resumen["vehiculos"], "Vehiculos"), (resumen["sin_flota"], "Sin flota"),
        (resumen["multi_flota"], "En varias flotas"), (resumen["huerfanas"], "Referencias huerfanas"),
    ]):
        with c:
            st.markdown(render_stat(n, l), unsafe_allow_html=True)

    st.markdown("&nbsp;", unsafe_allow_html=True)

    grupos = snapshot["grupos"]
    codigos_presentes = {g["code"]: g["title"] for g in grupos}

    render_label("Filtros")
    col_f1, col_f2, col_f3 = st.columns([2, 1, 1])
    with col_f1:
        query = st.text_input(
            "Buscar flota", key="af_filtro_texto",
            placeholder="Nombre, ID o placa...", label_visibility="collapsed",
        )
    with col_f2:
        salud_sel = st.selectbox("Salud", ["Todas", "Sana", "Advertencia", "Inconsistencia"], key="af_filtro_salud")
    with col_f3:
        opciones_hallazgo = ["Todos"] + list(codigos_presentes.keys())
        hallazgo_sel = st.selectbox(
            "Hallazgo", opciones_hallazgo, key="af_filtro_hallazgo",
            format_func=lambda c: "Todos" if c == "Todos" else codigos_presentes[c],
        )

    salud_map = {"Sana": "healthy", "Advertencia": "warning", "Inconsistencia": "inconsistency"}
    salud_filtro = salud_map.get(salud_sel)
    hallazgo_filtro = None if hallazgo_sel == "Todos" else hallazgo_sel

    render_label("Hallazgos")
    grupos_vista = [g for g in grupos if hallazgo_filtro is None or g["code"] == hallazgo_filtro]
    if not grupos_vista:
        render_tip("No hay hallazgos para el filtro seleccionado." if hallazgo_filtro else "No hay hallazgos — todas las flotas estan sanas.")
    for g in grupos_vista:
        icono = "🔴" if g["severity"] == "inconsistency" else "🟡"
        with st.expander(f"{icono} {g['title']} — {g['total']} caso(s)"):
            st.caption(g["description"])
            for s in g["samples"]:
                st.markdown(f"- {s['label']}")
            if g["truncated"]:
                st.caption(f"Mostrando {len(g['samples'])} de {g['total']} — el resto solo esta en la exportacion CSV.")

    render_label("Directorio de flotas")
    filas = []
    for fid, f in snapshot["flotas"].items():
        salud = snapshot["salud"][fid]
        if salud_filtro and salud != salud_filtro:
            continue
        if hallazgo_filtro and fid not in snapshot["flotas_por_hallazgo"].get(hallazgo_filtro, set()):
            continue
        if query and query.strip():
            texto_norm = _normalizar_busqueda(f"{f['name']} {fid}")
            ident_norm = _normalizar_identificador(f"{f['name']}{fid}")
            q_texto, q_ident = _normalizar_busqueda(query), _normalizar_identificador(query)
            if q_texto not in texto_norm and q_ident not in ident_norm:
                continue
        st_ = snapshot["stats_flota"][fid]
        filas.append({
            "_fleet_id": fid,
            "Flota": f["name"], "Salud": SALUD_LABELS[salud],
            "Vehiculos": st_["vehiculos"], "Usuarios": st_["usuarios"],
            "Eliminados": st_["eliminados"], "Inactivos": st_["inactivos"],
            "Huerfanos": st_["huerfanos"],
            "No resueltos": st_["no_resueltos"] if st_["no_resueltos"] is not None else "N/D",
        })

    if not filas:
        render_tip("Ningun resultado con los filtros actuales.")
    else:
        df = pd.DataFrame(filas)
        event = st.dataframe(
            df.drop(columns=["_fleet_id"]),
            on_select="rerun", selection_mode="single-row",
            use_container_width=True, hide_index=True, key="af_directorio",
        )
        if event.selection.rows:
            st.session_state["af_selected_fleet_id"] = filas[event.selection.rows[0]]["_fleet_id"]

    st.markdown("&nbsp;", unsafe_allow_html=True)
    render_label("Exportar")
    _seccion_exportar(snapshot, fleet_id=None, finding_code=hallazgo_filtro)


def _vista_detalle_flota(snapshot, fleet_id):
    f = snapshot["flotas"][fleet_id]
    st_ = snapshot["stats_flota"][fleet_id]
    salud = snapshot["salud"][fleet_id]

    render_label(f"Detalle de flota — {f['name']}")
    if st.button("Cerrar detalle", key="af_cerrar_detalle"):
        st.session_state.pop("af_selected_fleet_id", None)
        st.rerun()

    render_cuenta_badge(f"ID: {fleet_id} · Salud: <strong>{SALUD_LABELS[salud]}</strong>")

    cols = st.columns(4)
    with cols[0]:
        st.markdown(render_stat(st_["vehiculos"], "Vehiculos"), unsafe_allow_html=True)
    with cols[1]:
        st.markdown(render_stat(st_["usuarios"], "Usuarios"), unsafe_allow_html=True)
    with cols[2]:
        st.markdown(render_stat(st_["huerfanos"], "Huerfanos"), unsafe_allow_html=True)
    with cols[3]:
        nr = st_["no_resueltos"]
        st.markdown(render_stat(nr if nr is not None else "N/D", "Usuarios no resueltos"), unsafe_allow_html=True)

    render_label("Vehiculos relacionados")
    col_v1, col_v2 = st.columns([2, 1])
    with col_v1:
        filtro_v = st.text_input(
            "Buscar vehiculo", key="af_detalle_filtro_veh",
            placeholder="Nombre, ID o placa...", label_visibility="collapsed",
        )
    with col_v2:
        filtro_estado = st.selectbox(
            "Estado", ["Todos", "active", "inactive", "deleted", "unknown", "huerfano"],
            key="af_detalle_filtro_estado",
        )

    filas_v = []
    for vid in f["vehicle_ids_unique"]:
        vehiculo = snapshot["vehiculos"].get(vid)
        if vehiculo is None:
            estado, nombre_v, placa = "huerfano", "(no existe)", ""
        else:
            estado = _lifecycle_vehiculo(vehiculo)
            nombre_v = vehiculo.get("name", "")
            placa = vehiculo.get("license_plate", "")
        if filtro_estado != "Todos" and estado != filtro_estado:
            continue
        if filtro_v and filtro_v.strip():
            texto = _normalizar_busqueda(f"{nombre_v} {placa} {vid}")
            ident = _normalizar_identificador(f"{nombre_v}{placa}{vid}")
            q, qi = _normalizar_busqueda(filtro_v), _normalizar_identificador(filtro_v)
            if q not in texto and qi not in ident:
                continue
        filas_v.append({"ID": vid, "Nombre": nombre_v, "Placa": placa, "Estado": estado})

    if filas_v:
        st.dataframe(pd.DataFrame(filas_v), use_container_width=True, hide_index=True)
    else:
        render_tip("Sin vehiculos para mostrar con los filtros actuales.")

    render_label("Usuarios relacionados")
    if not snapshot["drivers_ok"]:
        render_tip("La fuente de usuarios no se pudo consultar — no se puede verificar cuales existen.", warning=True)

    filas_u = []
    for uid in f["user_ids_unique"]:
        if not snapshot["drivers_ok"]:
            estado_u = "No verificado"
        elif uid in snapshot["drivers_ids"]:
            estado_u = "Existe"
        else:
            estado_u = "No encontrado"
        filas_u.append({"ID de usuario": uid, "Estado": estado_u})

    if filas_u:
        st.dataframe(pd.DataFrame(filas_u), use_container_width=True, hide_index=True)
    else:
        render_tip("La flota no tiene usuarios asignados.")

    render_label("Hallazgos de esta flota")
    grupos_flota = [g for g in snapshot["grupos"] if fleet_id in snapshot["flotas_por_hallazgo"].get(g["code"], set())]
    if not grupos_flota:
        render_tip("Esta flota no tiene hallazgos.")
    for g in grupos_flota:
        muestras = [s for s in g["samples"] if fleet_id in s["fleetIds"]]
        with st.expander(f"{g['title']} — {len(muestras)} caso(s) en esta flota"):
            for s in muestras:
                st.markdown(f"- {s['label']}")

    with st.expander("Ver JSON crudo de la flota"):
        st.json(f["raw"])

    st.markdown("&nbsp;", unsafe_allow_html=True)
    render_label("Exportar (acotado a esta flota)")
    _seccion_exportar(snapshot, fleet_id=fleet_id, finding_code=None)


def pagina_auditor_flotas():
    render_header(
        "Auditor de Flotas",
        "Detecta inconsistencias entre flotas, vehiculos y usuarios (solo lectura, addon fleets)",
    )

    render_guide(
        steps=[
            "<strong>Ingresa el token</strong> — Token de API de la cuenta. Se valida contra <code>/accounts/me/</code>.",
            "<strong>Cargar auditoria</strong> — Descarga flotas, vehiculos y usuarios y cruza las relaciones en memoria.",
            "<strong>Revisa los hallazgos</strong> — 9 tipos de inconsistencias agrupadas, con filtros por texto, salud o tipo.",
            "<strong>Detalle por flota</strong> — Selecciona una fila del directorio para ver sus vehiculos, usuarios y hallazgos.",
            "<strong>Exporta</strong> — Descarga los hallazgos o las relaciones crudas en CSV.",
        ],
        tip="Es 100% de lectura: no modifica nada en SimpliRoute. Si /accounts/drivers/ falla, la auditoria sigue en modo parcial (sin verificar usuarios).",
    )

    render_label("Token de API")
    token = campo_token("af", placeholder="Token de API SimpliRoute")
    if not token or not token.strip():
        render_tip("Ingresa el token de la cuenta para continuar.")
        st.stop()
    token = token.strip()

    if st.session_state.get("af_last_token") != token:
        st.session_state.pop("af_snapshot", None)
        st.session_state.pop("af_selected_fleet_id", None)
        st.session_state["af_last_token"] = token

    ok_cuenta, nombre_cuenta, detalle = _validar_cuenta(token)
    if not ok_cuenta:
        st.error(f"Token invalido o sin acceso a la cuenta.\n\n{detalle}")
        st.stop()
    render_cuenta_badge(f"Cuenta: {nombre_cuenta}")

    if st.button("Cargar / Actualizar auditoria", type="primary", key="af_btn_cargar"):
        with st.spinner("Descargando flotas, vehiculos y usuarios..."):
            snapshot, error = _cargar_snapshot(token)
        if error:
            render_error_item(error)
        else:
            st.session_state["af_snapshot"] = snapshot
            st.session_state.pop("af_selected_fleet_id", None)

    snapshot = st.session_state.get("af_snapshot")
    if not snapshot:
        render_tip('Pulsa "Cargar / Actualizar auditoria" para comenzar.')
        st.stop()

    st.caption(f"Ultima actualizacion: {snapshot['built_at']}")

    if snapshot["warning"]:
        render_tip(
            f"<strong>Advertencia:</strong> {snapshot['warning']['message']} (fuente: {snapshot['warning']['source']}). "
            "Los hallazgos de usuarios no resueltos no estaran disponibles.",
            warning=True,
        )

    _vista_auditoria_global(snapshot)

    fleet_id_sel = st.session_state.get("af_selected_fleet_id")
    if fleet_id_sel is not None and fleet_id_sel in snapshot["flotas"]:
        st.markdown("---")
        _vista_detalle_flota(snapshot, fleet_id_sel)
