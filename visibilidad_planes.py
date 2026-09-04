import pandas as pd
import requests
import streamlit as st
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from config import API_BASE, API_GATEWAY_BASE, REQUEST_TIMEOUT
from utils import render_header, render_guide, render_label, render_tip, render_stat, render_cuenta_badge
from account_lookup import campo_token

VP_MAX_PAGES_FLEETS = 50
VP_MAX_PAGES_VEHICLES = 25
VP_MAX_PAGES_PLANS = 100
VP_MAX_PAGES_USERS = 50
VP_OPTIONAL_WORKERS = 6

LIMITACION_BASE = "El diagnostico usa relaciones actuales de la API publica; no reconstruye permisos ni historial."


def _headers(token):
    return {"Authorization": f"Token {token}"}


def _validar_cuenta(token):
    try:
        r = requests.get(f"{API_BASE}/accounts/me/", headers=_headers(token), timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            return True, r.json().get("account", {}).get("name", "Sin nombre")
    except requests.exceptions.RequestException:
        pass
    return False, None


def _parse_id_positivo(texto):
    s = (texto or "").strip()
    if not s.isdigit():
        return None
    v = int(s)
    return v if v > 0 else None


# ── Llamadas API ──────────────────────────────────────────────────────────────

def _get_paginated(url, headers, max_pages):
    """Returns (items, ok). ok=False si la fuente fallo o se excedio el limite de paginas."""
    items = []
    page_url = url
    pages = 0
    try:
        while page_url:
            if pages >= max_pages:
                return items, False
            r = requests.get(page_url, headers=headers, timeout=REQUEST_TIMEOUT)
            if r.status_code != 200:
                return items, False
            data = r.json()
            if isinstance(data, list):
                items.extend(data)
                break
            items.extend(data.get("results", []))
            page_url = data.get("next")
            pages += 1
        return items, True
    except requests.exceptions.RequestException:
        return items, False


def listar_fleets(token):
    return _get_paginated(f"{API_BASE}/fleets/", _headers(token), VP_MAX_PAGES_FLEETS)


def listar_vehiculos_fecha(token, fecha):
    return _get_paginated(f"{API_BASE}/plans/{fecha}/vehicles/", _headers(token), VP_MAX_PAGES_VEHICLES)


def listar_planes_dia(token, fecha):
    url = f"{API_BASE}/routes/plans/?start_date={fecha}&end_date={fecha}"
    return _get_paginated(url, _headers(token), VP_MAX_PAGES_PLANS)


def listar_usuarios_directorio(token):
    usuarios, ok = _get_paginated(f"{API_GATEWAY_BASE}/accounts/users/", _headers(token), VP_MAX_PAGES_USERS)
    if not ok:
        return [], False
    activos = []
    for u in usuarios:
        status = u.get("status")
        if not isinstance(status, str):
            return [], False
        if status == "active":
            activos.append(u)
    return activos, True


def obtener_driver(token, user_id):
    url = f"{API_BASE}/accounts/drivers/{user_id}/"
    try:
        r = requests.get(url, headers=_headers(token), timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            return r.json()
    except requests.exceptions.RequestException:
        pass
    return None


# ── Algoritmo de diagnostico ──────────────────────────────────────────────────

def _build_vehicle_fleet_context(fleets):
    fleet_membership_by_vehicle = {}
    fleets_by_id = {}
    for f in fleets:
        fid = f.get("id")
        fleets_by_id[fid] = {"id": fid, "name": f.get("name", ""), "vehicle_count": len(set(f.get("vehicles") or []))}
        for vid in set(f.get("vehicles") or []):
            fleet_membership_by_vehicle.setdefault(vid, []).append({"id": fid, "name": f.get("name", "")})
    return fleet_membership_by_vehicle, fleets_by_id


def _user_fleets(fleets, user_id):
    if user_id is None:
        return []
    return [{"id": f.get("id"), "name": f.get("name", "")} for f in fleets if user_id in set(f.get("users") or [])]


def _relacion_conductor(v, user_id):
    if "driver" not in v:
        return "unresolved", None
    driver = v.get("driver")
    if driver is None:
        return "unassigned", None
    if not isinstance(driver, dict):
        return "unresolved", None
    driver_id = driver.get("id")
    if not isinstance(driver_id, int):
        return "unresolved", None
    return ("matches" if driver_id == user_id else "different"), driver_id


def _nombre_conductor(directorio, driver_id):
    if driver_id is None:
        return None
    for u in directorio:
        if u.get("id") == driver_id:
            return u.get("name") or u.get("username")
    return None


def _es_admin(perfil):
    roles = perfil.get("roles")
    if isinstance(roles, dict):
        return bool(roles.get("admin"))
    return bool(perfil.get("is_admin"))


def _construir_conclusion(scenario, coverage):
    if coverage == "unresolved":
        return {
            "outcome": "inconclusive",
            "title": "No se puede concluir con la informacion disponible",
            "explanation": "No hay suficiente evidencia actual (perfil o flotas) para afirmar si el usuario comparte o no flota con los vehiculos del plan.",
            "next_step": "Verifica manualmente el perfil del usuario y las flotas involucradas, o reintenta cuando las fuentes opcionales esten disponibles.",
            "limitations": [LIMITACION_BASE],
        }
    if scenario == "missing":
        if coverage == "none":
            return {
                "outcome": "explained_by_fleets",
                "title": "Las flotas actuales explican por que el plan no aparece",
                "explanation": "El usuario no comparte flota con ningun vehiculo resoluble de este plan.",
                "next_step": "Si el usuario deberia ver este plan, agregalo a la flota que cubre los vehiculos correspondientes.",
                "limitations": [LIMITACION_BASE],
            }
        if coverage == "full":
            return {
                "outcome": "not_explained_by_fleets",
                "title": "Las flotas actuales no explican por que el plan no aparece",
                "explanation": "El ID analizado comparte flota con todos los vehiculos resolubles del plan.",
                "next_step": "Revisa la cuenta abierta, la fecha, los filtros, el estado del plan y la sesion del usuario. Si el problema continua, adjunta este diagnostico al escalar el caso.",
                "limitations": [LIMITACION_BASE],
            }
        return {
            "outcome": "partially_explained_by_fleets",
            "title": "Las flotas actuales explican solo parte del plan",
            "explanation": "El usuario comparte flota con algunos vehiculos del plan, pero no con todos.",
            "next_step": "Revisa los vehiculos marcados como 'fuera de flota' o 'sin flota observada' mas abajo.",
            "limitations": [LIMITACION_BASE],
        }
    if coverage in ("full", "partial"):
        return {
            "outcome": "explained_by_fleets",
            "title": "Las flotas actuales explican por que el plan aparece",
            "explanation": "El usuario comparte flota con uno o mas vehiculos resolubles de este plan.",
            "next_step": "Si el usuario no deberia ver este plan, revisa (y ajusta si corresponde) las flotas que comparten sus vehiculos.",
            "limitations": [LIMITACION_BASE],
        }
    return {
        "outcome": "not_explained_by_fleets",
        "title": "Las flotas actuales no explican por que el plan aparece",
        "explanation": "El usuario no comparte flota con ningun vehiculo resoluble de este plan.",
        "next_step": "Revisa la cuenta abierta, la sesion del usuario y si hay otra via de acceso (ej. rol de administrador). Si el problema continua, adjunta este diagnostico al escalar el caso.",
        "limitations": [LIMITACION_BASE],
    }


def _calcular_diagnostico(scenario, plan_id, plan_nombre, fecha, fleets, vehiculos,
                           user_id, perfil_usuario, creador_id, perfil_creador,
                           planes_dia, directorio, warnings):
    fleet_membership_by_vehicle, fleets_by_id = _build_vehicle_fleet_context(fleets)
    user_fleets = _user_fleets(fleets, user_id)
    creador_fleets = _user_fleets(fleets, creador_id) if creador_id else None

    found_in_operation = False
    route_ids_plan = set()
    routes_by_route_id = {}

    for v in vehiculos:
        vehicle_obj = v.get("vehicle") or {}
        vehicle_id = vehicle_obj.get("id")
        vehicle_valido = isinstance(vehicle_id, int) and vehicle_id > 0
        for route in (v.get("routes") or []):
            if route.get("plan_id") != plan_id:
                continue
            rid = route.get("id")
            route_ids_plan.add(rid)
            found_in_operation = True
            routes_by_route_id[rid] = {
                "vehicle_id": vehicle_id if vehicle_valido else None,
                "vehicle_name": v.get("name", "—"),
                "license_plate": vehicle_obj.get("license_plate", ""),
                "reference_id": vehicle_obj.get("reference_id", ""),
                "driver_field": v,
            }

    found_in_plans = False
    plan_name_from_plans = None
    if planes_dia is not None:
        for p in planes_dia:
            if p.get("id") == plan_id:
                found_in_plans = True
                plan_name_from_plans = p.get("name")
                break

    if not found_in_plans and not found_in_operation:
        if planes_dia is None:
            return {"error": "No se pudo consultar Planes y tampoco se encontraron rutas operativas para este plan: no es posible continuar."}
        return {"error": "No se encontro este plan ni en Planes ni en la operacion del dia (PLAN_NOT_FOUND)."}

    vehiculos_agrupados = {}
    rutas_sin_vehiculo = []

    for rid in route_ids_plan:
        info = routes_by_route_id[rid]
        relacion, driver_id_obs = _relacion_conductor(info["driver_field"], user_id)
        registro_ruta = {
            "route_id": rid,
            "driver_relation": relacion,
            "driver_id": driver_id_obs,
            "driver_name": _nombre_conductor(directorio, driver_id_obs),
        }
        vid = info["vehicle_id"]
        if vid is None:
            rutas_sin_vehiculo.append(registro_ruta)
            continue
        if vid not in vehiculos_agrupados:
            vehiculos_agrupados[vid] = {
                "vehicle_id": vid,
                "name": info["vehicle_name"],
                "license_plate": info["license_plate"],
                "reference_id": info["reference_id"],
                "routes": [],
            }
        vehiculos_agrupados[vid]["routes"].append(registro_ruta)

    user_fleet_ids = {f["id"] for f in user_fleets}
    for vid, info in vehiculos_agrupados.items():
        flotas_vehiculo = fleet_membership_by_vehicle.get(vid, [])
        info["flotas"] = flotas_vehiculo
        if not flotas_vehiculo:
            info["assignment"] = "unassigned"
        elif any(f["id"] in user_fleet_ids for f in flotas_vehiculo):
            info["assignment"] = "covered"
        else:
            info["assignment"] = "outside"

    total_vehicles = len(vehiculos_agrupados)
    covered = sum(1 for i in vehiculos_agrupados.values() if i["assignment"] == "covered")
    outside = sum(1 for i in vehiculos_agrupados.values() if i["assignment"] == "outside")
    unassigned_v = sum(1 for i in vehiculos_agrupados.values() if i["assignment"] == "unassigned")
    unresolved_routes = len(rutas_sin_vehiculo)
    total_routes = len(route_ids_plan)

    user_scope_known = (perfil_usuario is not None) or bool(user_fleets)

    if not user_scope_known or total_vehicles == 0:
        coverage_status = "unresolved"
    elif unresolved_routes > 0:
        coverage_status = "partial" if covered > 0 else "unresolved"
    elif covered == total_vehicles:
        coverage_status = "full"
    elif covered > 0:
        coverage_status = "partial"
    elif outside > 0:
        coverage_status = "none"
    else:
        coverage_status = "unresolved"

    todas_las_rutas = [r for grp in vehiculos_agrupados.values() for r in grp["routes"]] + rutas_sin_vehiculo
    matching_route_ids = [r["route_id"] for r in todas_las_rutas if r["driver_relation"] == "matches"]
    matching_vehicle_ids = [vid for vid, grp in vehiculos_agrupados.items() if any(r["driver_relation"] == "matches" for r in grp["routes"])]
    unresolved_driver_route_ids = [r["route_id"] for r in todas_las_rutas if r["driver_relation"] == "unresolved"]

    if total_routes == 0:
        driver_status = "unresolved"
    elif matching_route_ids:
        driver_status = "observed"
    elif all(r["driver_relation"] == "unresolved" for r in todas_las_rutas):
        driver_status = "unresolved"
    else:
        driver_status = "not_observed"

    findings = []
    if perfil_usuario is None and user_fleets:
        findings.append({"code": "USER_IDENTITY_UNRESOLVED", "severity": "info",
                          "text": f"No se pudo resolver el perfil del usuario {user_id} (accounts/drivers), pero su ID aparece en flotas actuales. El diagnostico continua por ID."})
    if perfil_usuario is None and not user_fleets:
        findings.append({"code": "USER_SCOPE_UNRESOLVED", "severity": "warning",
                          "text": f"No se pudo resolver el perfil del usuario {user_id} ni encontrarlo en ninguna flota actual. No se puede afirmar que no tenga flotas — el resultado queda como no concluyente."})
    if coverage_status == "none" and perfil_usuario and _es_admin(perfil_usuario):
        findings.append({"code": "ADMIN_OUTSIDE_TARGET_FLEET", "severity": "info",
                          "text": "El usuario tiene rol de administrador, pero eso no otorga acceso automatico a este plan: no comparte flota con ningun vehiculo resoluble."})
    if unresolved_routes > 0:
        findings.append({"code": "UNRESOLVED_ROUTES", "severity": "warning",
                          "text": f"{unresolved_routes} ruta(s) del plan no tienen un vehiculo resoluble en la operacion del dia; quedan fuera del calculo de cobertura por flota."})
    if not found_in_plans and found_in_operation:
        findings.append({"code": "PLAN_NOT_IN_LISTPLANS", "severity": "info",
                          "text": "El plan no aparece en el listado de Planes (routes/plans) para este dia, pero si se encontraron rutas operativas asociadas a su ID."})
    if driver_status == "observed":
        findings.append({"code": "DRIVER_ASSIGNMENT_OBSERVED", "severity": "info",
                          "text": "El usuario aparece como conductor observado de al menos una ruta de este plan (independiente de la cobertura por flota)."})
    if driver_status == "unresolved" and total_routes > 0:
        findings.append({"code": "DRIVER_ASSIGNMENT_UNRESOLVED", "severity": "warning",
                          "text": "No se pudo determinar el conductor observado en ninguna ruta del plan (campo driver ausente o con formato invalido)."})
    if scenario == "unexpected" and creador_id:
        if perfil_creador is None:
            findings.append({"code": "REPORTED_CREATOR_IDENTITY_UNRESOLVED", "severity": "info",
                              "text": f"No se pudo resolver el perfil del creador reportado {creador_id}. Es un indicio actual, no evidencia historica de creacion."})
        elif not creador_fleets:
            findings.append({"code": "REPORTED_CREATOR_WITHOUT_FLEET", "severity": "info",
                              "text": f"El creador reportado {creador_id} no aparece en ninguna flota actual. Es un indicio actual, no evidencia historica de creacion."})

    related_fleet_ids = {f["id"] for grp in vehiculos_agrupados.values() for f in grp["flotas"]}
    related_fleets = []
    for fid in related_fleet_ids:
        finfo = fleets_by_id.get(fid, {"id": fid, "name": "", "vehicle_count": 0})
        related_fleets.append({"id": fid, "name": finfo["name"], "vehicle_count": finfo["vehicle_count"], "compartida": fid in user_fleet_ids})

    vehiculos_lista = sorted(vehiculos_agrupados.values(), key=lambda i: (i["name"].lower(), i["vehicle_id"]))
    for grp in vehiculos_lista:
        grp["routes"] = sorted(grp["routes"], key=lambda r: str(r["route_id"]))
    rutas_sin_vehiculo = sorted(rutas_sin_vehiculo, key=lambda r: str(r["route_id"]))

    return {
        "plan_id": plan_id,
        "plan_nombre": plan_nombre or plan_name_from_plans or "(sin nombre)",
        "fecha": fecha,
        "scenario": scenario,
        "found_in_plans": found_in_plans,
        "found_in_operation": found_in_operation,
        "user_id": user_id,
        "perfil_usuario": perfil_usuario,
        "user_fleets": user_fleets,
        "creador_id": creador_id,
        "perfil_creador": perfil_creador,
        "creador_fleets": creador_fleets,
        "coverage": {
            "status": coverage_status, "total_routes": total_routes, "unresolved_routes": unresolved_routes,
            "total_vehicles": total_vehicles, "covered_vehicles": covered, "outside_vehicles": outside,
            "unassigned_vehicles": unassigned_v,
        },
        "driver_relation": {
            "status": driver_status, "matching_route_ids": matching_route_ids,
            "matching_vehicle_ids": matching_vehicle_ids, "unresolved_route_ids": unresolved_driver_route_ids,
        },
        "related_fleets": sorted(related_fleets, key=lambda f: f["name"].lower()),
        "vehicles": vehiculos_lista,
        "rutas_sin_vehiculo": rutas_sin_vehiculo,
        "conclusion": _construir_conclusion(scenario, coverage_status),
        "findings": findings,
        "warnings": warnings,
    }


def _diagnosticar(token, scenario, fecha_str, plan_id, plan_nombre, user_id, creador_id):
    with st.spinner("Consultando flotas y vehiculos operativos del dia..."):
        with ThreadPoolExecutor(max_workers=2) as ex:
            fut_fleets = ex.submit(listar_fleets, token)
            fut_vehicles = ex.submit(listar_vehiculos_fecha, token, fecha_str)
            fleets, fleets_ok = fut_fleets.result()
            vehiculos, vehiculos_ok = fut_vehicles.result()

    if not fleets_ok or not vehiculos_ok:
        st.error("No se pudo consultar una fuente obligatoria (flotas o vehiculos operativos del dia). No es posible diagnosticar.")
        return None

    warnings = []
    perfil_usuario = None
    perfil_creador = None
    planes_dia = None
    directorio = st.session_state.get("vp_directorio")
    directorio_ok = st.session_state.get("vp_directorio_ok", False)

    with st.spinner("Consultando fuentes opcionales..."):
        with ThreadPoolExecutor(max_workers=VP_OPTIONAL_WORKERS) as ex:
            futs = {ex.submit(obtener_driver, token, user_id): "usuario",
                    ex.submit(listar_planes_dia, token, fecha_str): "planes"}
            if creador_id:
                futs[ex.submit(obtener_driver, token, creador_id)] = "creador"
            if directorio is None:
                futs[ex.submit(listar_usuarios_directorio, token)] = "directorio"

            for fut in as_completed(futs):
                origen = futs[fut]
                try:
                    if origen == "usuario":
                        perfil_usuario = fut.result()
                        if perfil_usuario is None:
                            warnings.append("No se pudo resolver el perfil del usuario afectado (accounts/drivers).")
                    elif origen == "creador":
                        perfil_creador = fut.result()
                        if perfil_creador is None:
                            warnings.append("No se pudo resolver el perfil del creador reportado (accounts/drivers).")
                    elif origen == "planes":
                        planes_dia, ok = fut.result()
                        if not ok:
                            planes_dia = None
                            warnings.append("No se pudo consultar Planes del dia (routes/plans).")
                    elif origen == "directorio":
                        directorio, directorio_ok = fut.result()
                        st.session_state.vp_directorio = directorio
                        st.session_state.vp_directorio_ok = directorio_ok
                        if not directorio_ok:
                            warnings.append("No se pudo consultar el Directorio de usuarios (accounts/users).")
                except Exception as e:
                    warnings.append(f"Error consultando fuente opcional ({origen}): {e}")

    if directorio is None:
        directorio = []

    resultado = _calcular_diagnostico(
        scenario=scenario, plan_id=plan_id, plan_nombre=plan_nombre, fecha=fecha_str,
        fleets=fleets, vehiculos=vehiculos, user_id=user_id, perfil_usuario=perfil_usuario,
        creador_id=creador_id, perfil_creador=perfil_creador, planes_dia=planes_dia,
        directorio=directorio, warnings=warnings,
    )
    if "error" in resultado:
        st.error(resultado["error"])
        return None
    return resultado


# ── UI ─────────────────────────────────────────────────────────────────────────

def _campo_usuario(token, key_prefix, titulo):
    with st.expander(f"Buscar en el directorio de usuarios (opcional)"):
        query = st.text_input("Nombre, username o ID", key=f"{key_prefix}_q", placeholder="Ej: Juan Perez")
        if st.button("Buscar", key=f"{key_prefix}_buscar_dir"):
            if "vp_directorio" not in st.session_state:
                with st.spinner("Cargando directorio de usuarios..."):
                    usuarios, ok = listar_usuarios_directorio(token)
                st.session_state.vp_directorio = usuarios
                st.session_state.vp_directorio_ok = ok
            if not st.session_state.get("vp_directorio_ok"):
                st.warning("No se pudo cargar el directorio (fuente opcional).")
            directorio = st.session_state.get("vp_directorio", [])
            q = query.strip().lower()
            coincidencias = [
                u for u in directorio
                if not q or q in str(u.get("id", "")).lower() or q in str(u.get("username", "")).lower() or q in str(u.get("name", "")).lower()
            ]
            st.session_state[f"{key_prefix}_matches"] = coincidencias[:30]

        matches = st.session_state.get(f"{key_prefix}_matches", [])
        if matches:
            st.dataframe(
                pd.DataFrame([{"ID": u.get("id"), "Username": u.get("username", ""), "Nombre": u.get("name", "")} for u in matches]),
                use_container_width=True, hide_index=True,
            )

    user_id_str = st.text_input(f"ID de {titulo.lower()}", key=f"{key_prefix}_id", placeholder="Ej: 1234")
    user_id = _parse_id_positivo(user_id_str)
    if user_id_str.strip() and user_id is None:
        st.error("El ID debe ser un numero entero positivo.")
    return user_id


def _coverage_label(status):
    return {"full": "Completa", "partial": "Parcial", "none": "Ninguna", "unresolved": "No concluyente"}.get(status, status)


def _assignment_label(a):
    return {"covered": "comparte flota", "outside": "no comparte flota", "unassigned": "sin flota observada"}.get(a, a)


def _driver_relation_label(rel):
    return {"matches": "coincide con el usuario", "different": "otro conductor", "unassigned": "sin conductor asignado", "unresolved": "no resoluble"}.get(rel, rel)


def _render_resultado(r):
    conclusion = r["conclusion"]
    outcome = conclusion["outcome"]

    render_label("Conclusion")
    caja = {"inconclusive": st.warning, "not_explained_by_fleets": st.error, "partially_explained_by_fleets": st.warning}.get(outcome, st.success)
    caja(f"**{conclusion['title']}**\n\n{conclusion['explanation']}\n\n**Siguiente paso:** {conclusion['next_step']}")
    for lim in conclusion["limitations"]:
        st.caption(f"Limitacion: {lim}")

    render_label("Plan")
    st.markdown(f"**{r['plan_nombre']}** · `{r['plan_id']}` · fecha {r['fecha']}")
    st.caption(f"Encontrado en Planes: {'si' if r['found_in_plans'] else 'no'} · Encontrado en operacion del dia: {'si' if r['found_in_operation'] else 'no'}")

    render_label("Cobertura por flota")
    cov = r["coverage"]
    cols1 = st.columns(3)
    with cols1[0]:
        st.markdown(render_stat(_coverage_label(cov["status"]), "cobertura"), unsafe_allow_html=True)
    with cols1[1]:
        st.markdown(render_stat(cov["total_vehicles"], "vehiculos del plan"), unsafe_allow_html=True)
    with cols1[2]:
        st.markdown(render_stat(cov["covered_vehicles"], "comparten flota"), unsafe_allow_html=True)
    cols2 = st.columns(3)
    with cols2[0]:
        st.markdown(render_stat(cov["outside_vehicles"], "no comparten flota"), unsafe_allow_html=True)
    with cols2[1]:
        st.markdown(render_stat(cov["unassigned_vehicles"], "sin flota observada"), unsafe_allow_html=True)
    with cols2[2]:
        st.markdown(render_stat(cov["unresolved_routes"], "rutas sin vehiculo"), unsafe_allow_html=True)

    render_label("Asignacion como conductor")
    dr = r["driver_relation"]
    if dr["status"] == "observed":
        render_tip(f"El usuario aparece como conductor observado en {len(dr['matching_route_ids'])} ruta(s) de este plan.")
    elif dr["status"] == "not_observed":
        render_tip("El usuario no aparece como conductor observado en ninguna ruta de este plan.")
    else:
        render_tip("No se pudo determinar la asignacion como conductor (sin rutas del plan o datos de conductor no resolubles).", warning=True)

    render_label("Usuario afectado")
    perfil = r["perfil_usuario"]
    if perfil:
        st.markdown(f"ID `{r['user_id']}` · {perfil.get('name', '')} · @{perfil.get('username', '')}")
    else:
        st.markdown(f"ID `{r['user_id']}` (perfil no resuelto)")
    st.caption("Flotas del usuario: " + (", ".join(f["name"] or str(f["id"]) for f in r["user_fleets"]) if r["user_fleets"] else "ninguna flota actual"))

    if r["creador_id"]:
        render_label("Creador reportado")
        perfil_c = r["perfil_creador"]
        if perfil_c:
            st.markdown(f"ID `{r['creador_id']}` · {perfil_c.get('name', '')} · @{perfil_c.get('username', '')}")
        else:
            st.markdown(f"ID `{r['creador_id']}` (perfil no resuelto)")
        st.caption("Flotas del creador: " + (", ".join(f["name"] or str(f["id"]) for f in r["creador_fleets"]) if r["creador_fleets"] else "ninguna flota actual"))

    if r["findings"]:
        render_label("Hallazgos")
        for f in r["findings"]:
            (st.warning if f["severity"] == "warning" else st.info)(f["text"])

    if r["warnings"]:
        render_label("Fuentes con problemas")
        for w in r["warnings"]:
            st.warning(w)

    render_label("Flotas relacionadas")
    if r["related_fleets"]:
        st.dataframe(
            pd.DataFrame([
                {"ID": f["id"], "Nombre": f["name"], "Vehiculos": f["vehicle_count"], "Compartida con el usuario": "si" if f["compartida"] else "no"}
                for f in r["related_fleets"]
            ]),
            use_container_width=True, hide_index=True,
        )
    else:
        st.caption("No se observaron flotas asociadas a los vehiculos de este plan.")

    render_label(f"Vehiculos y rutas ({len(r['vehicles'])})")
    for v in r["vehicles"]:
        icon = {"covered": "✓", "outside": "✗", "unassigned": "?"}.get(v["assignment"], "?")
        with st.expander(f"{icon} {v['name']} · {v['license_plate'] or v['vehicle_id']} — {_assignment_label(v['assignment'])}"):
            st.caption(f"ID vehiculo: {v['vehicle_id']} · Referencia: {v['reference_id'] or '—'}")
            flotas_v = ", ".join(f["name"] or str(f["id"]) for f in v["flotas"]) or "(ninguna)"
            st.caption(f"Flotas del vehiculo: {flotas_v}")
            st.dataframe(
                pd.DataFrame([
                    {"Route ID": rt["route_id"], "Conductor observado": _driver_relation_label(rt["driver_relation"]),
                     "Nombre": rt["driver_name"] or "—", "Driver ID": rt["driver_id"] or "—"}
                    for rt in v["routes"]
                ]),
                use_container_width=True, hide_index=True,
            )

    if r["rutas_sin_vehiculo"]:
        render_label("Rutas sin vehiculo resoluble")
        st.dataframe(
            pd.DataFrame([
                {"Route ID": rt["route_id"], "Conductor observado": _driver_relation_label(rt["driver_relation"]),
                 "Nombre": rt["driver_name"] or "—", "Driver ID": rt["driver_id"] or "—"}
                for rt in r["rutas_sin_vehiculo"]
            ]),
            use_container_width=True, hide_index=True,
        )


def pagina_visibilidad_planes():
    render_header(
        "Visibilidad de Planes",
        "Diagnostica por que un plan aparece o no aparece para un usuario",
    )

    render_guide(
        steps=[
            "<strong>Ingresa el token</strong> y elige el escenario a diagnosticar.",
            "<strong>Busca el plan</strong> por fecha y selecciona el plan a revisar.",
            "<strong>Busca al usuario afectado</strong> (y al creador reportado, si aplica) por ID.",
            "<strong>Compara plan y usuario</strong> — cruza flotas, vehiculos operativos y conductor observado.",
            "<strong>Revisa la conclusion</strong>, los hallazgos y el detalle por vehiculo/ruta.",
        ],
        tip="Es un diagnostico basado en el estado ACTUAL de flotas y rutas operativas — un indicio, no una prueba de permisos ni de historial.",
    )

    render_label("Token de API")
    token = campo_token("vp", placeholder="Token de API")
    if not token or not token.strip():
        render_tip("Ingresa el token de API de la cuenta.")
        st.stop()
    token = token.strip()

    valido, cuenta = _validar_cuenta(token)
    if not valido:
        st.error("Token invalido. Revisa tu token de API.")
        st.stop()
    render_cuenta_badge(f"✓ Conectado a: <strong>{cuenta}</strong>")

    render_label("Paso 1 · Escenario")
    escenario_label = st.radio(
        "Escenario",
        ["No aparece para un usuario", "Aparece para quien no deberia"],
        label_visibility="collapsed",
        key="vp_escenario_radio",
    )
    scenario = "missing" if escenario_label == "No aparece para un usuario" else "unexpected"

    render_label("Paso 2 · Plan a diagnosticar")
    fecha_plan = st.date_input("Fecha del plan", value=date.today(), format="DD/MM/YYYY", key="vp_fecha_plan")
    filtro_plan = st.text_input("Filtrar por nombre (opcional)", key="vp_filtro_plan", placeholder="Ej: Ruta Norte")

    if st.button("Buscar planes del dia", key="vp_buscar_planes"):
        fecha_str = fecha_plan.strftime("%Y-%m-%d")
        with st.spinner("Buscando planes..."):
            planes, ok = listar_planes_dia(token, fecha_str)
        if not ok:
            st.error("No se pudo consultar planes del dia (fuente no disponible).")
        else:
            st.session_state.vp_planes = planes
            st.session_state.vp_planes_fecha = fecha_str
            st.session_state.pop("vp_resultado", None)

    if "vp_planes" not in st.session_state:
        st.stop()

    planes = st.session_state.vp_planes
    if filtro_plan.strip():
        f = filtro_plan.strip().lower()
        planes_filtrados = [p for p in planes if f in str(p.get("name", "")).lower()]
    else:
        planes_filtrados = planes

    if not planes_filtrados:
        render_tip("No se encontraron planes para esa fecha/filtro.")
        st.stop()

    opciones_plan = {f"{p.get('name', '(sin nombre)')} · {p.get('id')}": p for p in planes_filtrados}
    plan_key = st.selectbox("Plan", list(opciones_plan.keys()), key="vp_plan_select")
    plan_sel = opciones_plan[plan_key]

    render_label("Paso 3 · Usuario afectado")
    user_id = _campo_usuario(token, "vp_afectado", "Usuario afectado")
    if user_id is None:
        render_tip("Ingresa el ID numerico del usuario afectado para continuar.")
        st.stop()

    creador_id = None
    if scenario == "unexpected":
        render_label("Paso 4 · Creador reportado (opcional)")
        usar_creador = st.checkbox("Comparar tambien contra un creador reportado", key="vp_usar_creador")
        if usar_creador:
            creador_id = _campo_usuario(token, "vp_creador", "Creador reportado")

    st.markdown("---")
    if st.button("Comparar plan y usuario", type="primary", key="vp_comparar"):
        resultado = _diagnosticar(
            token, scenario, st.session_state.vp_planes_fecha, plan_sel.get("id"), plan_sel.get("name", ""),
            user_id, creador_id,
        )
        if resultado is not None:
            st.session_state.vp_resultado = resultado

    if "vp_resultado" not in st.session_state:
        st.stop()

    _render_resultado(st.session_state.vp_resultado)
