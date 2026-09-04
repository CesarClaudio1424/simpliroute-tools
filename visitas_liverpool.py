import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote

import pandas as pd
import requests
import streamlit as st

from config import API_BASE, REQUEST_TIMEOUT
from utils import (
    render_header, render_guide, render_label, render_tip,
    render_error_item, render_stat,
    create_progress_tracker, update_progress, finish_progress,
)

LPV_WORKERS = 10
LPV_MAX_IDENTIFICADORES = 100
LPV_MAX_LARGO_IDENTIFICADOR = 254
LPV_MAX_PAGINAS_REFERENCE = 25
LPV_EXCLUIDAS = {"liverpool", "bodegas liverpool", "bodegas liverpool sa de cv"}
LPV_TODAS = "Todas las cuentas Liverpool"

_MATCH_LABEL = {"id": "ID", "reference": "Reference"}


def _normalizar_nombre(nombre):
    nfkd = unicodedata.normalize("NFKD", str(nombre).strip())
    sin_acentos = "".join(c for c in nfkd if not unicodedata.combining(c))
    return " ".join(sin_acentos.lower().split()).rstrip(".")


@st.cache_data
def _cargar_cuentas():
    try:
        df = pd.read_csv("cuentas.csv", encoding="latin-1")
    except FileNotFoundError:
        return {}
    cuentas = {}
    for nombre, id_, token in zip(df.nombre, df.id, df.token):
        if _normalizar_nombre(nombre) in LPV_EXCLUIDAS:
            continue
        cuentas[str(nombre)] = {"id": str(id_), "token": str(token)}
    return cuentas


def _headers(token):
    return {"Authorization": f"Token {token}", "Content-Type": "application/json"}


def _normalizar_identificadores(texto):
    vistos = set()
    valores = []
    for linea in re.split(r"[\n,]+", texto or ""):
        val = linea.strip()
        if not val or val in vistos or len(val) > LPV_MAX_LARGO_IDENTIFICADOR:
            continue
        vistos.add(val)
        valores.append(val)
    return valores


def _buscar_por_id(visit_id_str, token):
    url = f"{API_BASE}/routes/visits/{visit_id_str}/"
    try:
        r = requests.get(url, headers=_headers(token), timeout=REQUEST_TIMEOUT)
    except requests.exceptions.RequestException as e:
        return None, str(e)
    if r.status_code == 200:
        data = r.json()
        # el upstream a veces normaliza el id solicitado; solo se acepta un match exacto
        if str(data.get("id")) == visit_id_str:
            return data, None
        return None, None
    if r.status_code >= 500:
        return None, f"HTTP {r.status_code}"
    return None, None


def _buscar_por_reference(reference, token):
    url = f"{API_BASE}/routes/visits/reference/{quote(reference, safe='')}/"
    resultados = []
    paginas = 0
    while url and paginas < LPV_MAX_PAGINAS_REFERENCE:
        try:
            r = requests.get(url, headers=_headers(token), timeout=REQUEST_TIMEOUT)
        except requests.exceptions.RequestException as e:
            return resultados, str(e)
        if r.status_code >= 500:
            return resultados, f"HTTP {r.status_code}"
        if r.status_code != 200:
            return resultados, None
        data = r.json()
        if isinstance(data, dict) and "results" in data:
            resultados.extend(data.get("results") or [])
            url = data.get("next")
        elif isinstance(data, list):
            resultados.extend(data)
            url = None
        elif isinstance(data, dict) and data.get("id"):
            resultados.append(data)
            url = None
        else:
            url = None
        paginas += 1
    return resultados, None


def _resolver_query(query, token):
    """Prueba query como ID (solo si es puramente numerico) y como Reference (siempre).
    Devuelve (lista de {visita, matched_by, collision}, error de red/5xx si alguna rama fallo)."""
    id_candidate, id_err = (None, None)
    if re.fullmatch(r"\d+", query):
        id_candidate, id_err = _buscar_por_id(query.lstrip("0") or "0", token)

    ref_candidates, ref_err = _buscar_por_reference(query, token)

    resultados = []
    ref_ids = {str(v.get("id")) for v in ref_candidates}

    if id_candidate:
        vid = str(id_candidate.get("id"))
        if vid in ref_ids:
            resultados.append({"visita": id_candidate, "matched_by": ["id", "reference"], "collision": False})
            ref_candidates = [v for v in ref_candidates if str(v.get("id")) != vid]
        else:
            resultados.append({"visita": id_candidate, "matched_by": ["id"], "collision": bool(ref_candidates)})

    for v in ref_candidates:
        resultados.append({"visita": v, "matched_by": ["reference"], "collision": bool(id_candidate)})

    return resultados, (id_err or ref_err)


def _obtener_recurso(url, token):
    try:
        r = requests.get(url, headers=_headers(token), timeout=REQUEST_TIMEOUT)
    except requests.exceptions.RequestException as e:
        return None, str(e)
    if r.status_code == 200:
        return r.json(), None
    if r.status_code == 404:
        return None, None
    return None, f"HTTP {r.status_code}"


def _mostrar_detalle(fila):
    token = fila["_token"]
    with st.container(border=True):
        st.markdown(f"**Visita {fila['visit_id']}** · cuenta {fila['cuenta']}")
        st.json(fila["_visita_raw"])

        if not fila["_route_id"]:
            render_tip("Esta visita no tiene ruta asignada.")
            return

        ruta, err_ruta = _obtener_recurso(f"{API_BASE}/routes/routes/{fila['_route_id']}/", token)
        if err_ruta:
            render_error_item(f"No se pudo obtener la ruta: {err_ruta}")
            return
        if not ruta:
            render_tip("No se encontro la ruta asociada.")
            return

        st.markdown("**Ruta:**")
        st.json(ruta)

        plan_id = ruta.get("plan")
        if plan_id:
            plan, err_plan = _obtener_recurso(f"{API_BASE}/routes/plans/{plan_id}/", token)
            if err_plan:
                render_error_item(f"No se pudo obtener el plan: {err_plan}")
            elif plan:
                st.markdown("**Plan:**")
                st.json(plan)


def pagina_visitas_liverpool():
    cuentas = _cargar_cuentas()

    render_header(
        "Visitas Liverpool",
        "Busca un LP, OV, Visit ID o Reference en una o todas las cuentas Liverpool",
    )

    render_guide(
        steps=[
            f"<strong>Elige el alcance</strong> — Una cuenta especifica o las {len(cuentas)} cuentas Liverpool a la vez.",
            "<strong>Pega los identificadores</strong> — LP, OV, Visit ID o Reference (hasta 100), uno por linea. Se prueban siempre como Reference, y ademas como ID si son puramente numericos.",
            "<strong>Buscar</strong> — Se consulta cada cuenta en paralelo. Si el mismo valor matchea una visita distinta por ID y por Reference, se marca como colision.",
            "<strong>Revisa la cobertura</strong> — Si alguna cuenta fallo al consultarse, el resultado queda marcado como parcial: nunca se afirma 'no encontrado' con cobertura incompleta.",
            "<strong>Selecciona una fila</strong> — Para ver el detalle completo de la ruta y el plan asociados.",
        ],
        tip="LP y OV son alias del campo <code>reference</code> en SimpliRoute — no existen como campos separados.",
    )

    if not cuentas:
        st.error("No se encontro el archivo `cuentas.csv`.")
        st.stop()

    render_label("Paso 1 · Alcance de la busqueda")
    alcance = st.selectbox(
        "Alcance",
        [LPV_TODAS] + sorted(cuentas.keys()),
        label_visibility="collapsed",
        key="lpv_alcance",
    )

    render_label("Paso 2 · Identificadores (uno por linea)")
    texto = st.text_area(
        "Identificadores",
        placeholder="9769647547\nLP-00123",
        height=180,
        label_visibility="collapsed",
        key="lpv_identificadores",
    )

    identificadores = _normalizar_identificadores(texto)
    if len(identificadores) > LPV_MAX_IDENTIFICADORES:
        render_tip(
            f"Maximo {LPV_MAX_IDENTIFICADORES} identificadores por busqueda. Se tomaran los primeros {LPV_MAX_IDENTIFICADORES}.",
            warning=True,
        )
        identificadores = identificadores[:LPV_MAX_IDENTIFICADORES]

    if identificadores:
        st.markdown(render_stat(len(identificadores), "identificador(es) a buscar"), unsafe_allow_html=True)

    if st.button("Buscar", type="primary", key="lpv_btn_buscar"):
        if not identificadores:
            st.warning("Pega al menos un identificador.")
        else:
            cuentas_a_buscar = dict(cuentas) if alcance == LPV_TODAS else {alcance: cuentas[alcance]}
            total_tareas = len(cuentas_a_buscar) * len(identificadores)

            barra, contador, _ = create_progress_tracker(total_tareas, "Buscando...")
            filas = []
            cuentas_con_error = set()
            procesados = 0

            with ThreadPoolExecutor(max_workers=LPV_WORKERS) as ex:
                futures = {
                    ex.submit(_resolver_query, query, info["token"]): (nombre, info["id"], info["token"], query)
                    for nombre, info in cuentas_a_buscar.items()
                    for query in identificadores
                }
                for fut in as_completed(futures):
                    nombre, account_id, token, query = futures[fut]
                    resultados, error = fut.result()
                    procesados += 1
                    if error:
                        cuentas_con_error.add(nombre)
                    for r in resultados:
                        v = r["visita"]
                        ruta = v.get("route")
                        if isinstance(ruta, dict):
                            ruta_id, ruta_display = ruta.get("id"), ruta.get("name") or ruta.get("id") or ""
                        else:
                            ruta_id, ruta_display = ruta, (ruta or "")
                        filas.append({
                            "cuenta": nombre,
                            "account_id": account_id,
                            "valor_buscado": query,
                            "visit_id": v.get("id"),
                            "coincidio_por": " + ".join(_MATCH_LABEL[m] for m in r["matched_by"]),
                            "titulo": v.get("title", ""),
                            "direccion": v.get("address", ""),
                            "planned_date": v.get("planned_date", ""),
                            "route": ruta_display,
                            "colision": r["collision"],
                            "_token": token,
                            "_route_id": ruta_id,
                            "_visita_raw": v,
                        })
                    update_progress(barra, contador, procesados, total_tareas, "Buscando...")

            finish_progress(barra)
            st.session_state.lpv_filas = filas
            st.session_state.lpv_cuentas_con_error = cuentas_con_error
            st.session_state.lpv_total_cuentas = len(cuentas_a_buscar)

    if "lpv_filas" not in st.session_state:
        st.stop()

    filas = st.session_state.lpv_filas
    cuentas_con_error = st.session_state.lpv_cuentas_con_error
    total_cuentas = st.session_state.lpv_total_cuentas

    render_label("Resultados")

    if cuentas_con_error:
        render_tip(
            f"<strong>Cobertura parcial:</strong> {len(cuentas_con_error)} de {total_cuentas} cuenta(s) fallaron al "
            f"consultarse ({', '.join(sorted(cuentas_con_error))}). El resultado no es concluyente — no se puede "
            f"afirmar que no existan mas visitas.",
            warning=True,
        )

    if not filas:
        if not cuentas_con_error:
            render_tip("No se encontraron visitas con estos identificadores en la(s) cuenta(s) consultada(s).")
        st.stop()

    n_colisiones = sum(1 for f in filas if f["colision"])
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(render_stat(len(filas), "coincidencia(s)"), unsafe_allow_html=True)
    with col2:
        st.markdown(render_stat(n_colisiones, "en colision"), unsafe_allow_html=True)
    with col3:
        st.markdown(render_stat(len(cuentas_con_error), "cuenta(s) con error"), unsafe_allow_html=True)

    if n_colisiones:
        render_tip(
            f"{n_colisiones} coincidencia(s) marcada(s) como colision: el mismo identificador matcheo visitas "
            f"distintas por ID y por Reference. Revisa cual es la correcta antes de actuar sobre ella.",
            warning=True,
        )

    df = pd.DataFrame([
        {
            "Cuenta": f["cuenta"],
            "Valor buscado": f["valor_buscado"],
            "Visit ID": f["visit_id"],
            "Coincidio por": f["coincidio_por"],
            "Titulo": f["titulo"],
            "Direccion": f["direccion"],
            "Fecha": f["planned_date"],
            "Ruta": f["route"],
            "Colision": "⚠ Si" if f["colision"] else "",
        }
        for f in filas
    ])

    event = st.dataframe(
        df,
        on_select="rerun",
        selection_mode="single-row",
        use_container_width=True,
        hide_index=True,
        key="lpv_tabla",
    )

    if event.selection.rows:
        _mostrar_detalle(filas[event.selection.rows[0]])
