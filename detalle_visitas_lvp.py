import io
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

import pandas as pd
import requests
import streamlit as st

from config import API_BASE, REQUEST_TIMEOUT
from utils import render_header, render_guide, render_label, render_stat

MAX_WORKERS = 10
ALIAS_CUENTA = {"MEXICALI": "MEXICALLI"}  # cuentas.csv tiene "Mexicalli" (typo, doble L)

COLUMNAS = [
    "Cuenta", "Fecha de planeacion", "ID de visita",
    "Nombre del CR", "Numero de CR", "SKU", "Reference",
    "ID de Transaccion", "Operacion", "UniNegocio",
    "Estatus actual de la orden", "Fecha y hora del estatus en SimpliRoute",
    "Nombre del plan", "Fecha de planeacion (entrega)",
    "Ruta / Unidad", "ID de Ruta", "Error",
]


def _norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    s = s.upper().strip()
    return re.sub(r"^LIVERPOOL\s+", "", s)


@st.cache_data
def _cargar_cuentas():
    df = pd.read_csv("cuentas.csv", encoding="latin-1")
    por_nombre, por_id = {}, {}
    for nombre, id_, token in zip(df.nombre, df.id, df.token):
        info = {"nombre": nombre, "id": str(id_), "token": str(token)}
        por_nombre.setdefault(_norm(nombre), info)
        por_id.setdefault(str(id_), info)
    return por_nombre, por_id


def _resolver_cuenta(valor, por_nombre, por_id):
    valor = str(valor).strip()
    if not valor or valor.lower() == "nan":
        return None
    if valor.isdigit() and valor in por_id:
        return por_id[valor]
    key = _norm(valor)
    key = ALIAS_CUENTA.get(key, key)
    return por_nombre.get(key)


def _parse_fecha(valor):
    ts = pd.to_datetime(valor, dayfirst=True, errors="coerce")
    if pd.isna(ts):
        return None
    return ts.strftime("%Y-%m-%d")


def _headers(token):
    return {"Authorization": f"Token {token}", "Content-Type": "application/json"}


def _get(url, token):
    """GET con 1 reintento (se observan fallos SSL transitorios ocasionales en el entorno)."""
    for intento in range(2):
        try:
            return requests.get(url, headers=_headers(token), timeout=REQUEST_TIMEOUT)
        except requests.exceptions.RequestException:
            if intento == 1:
                return None


def _get_lista(url, token):
    items = []
    while url:
        r = _get(url, token)
        if r is None or r.status_code != 200:
            break
        data = r.json()
        if isinstance(data, list):
            items.extend(data)
            break
        items.extend(data.get("results", []))
        url = data.get("next")
    return items


def _fetch_combo(token, fecha):
    """Trae visitas, rutas (-> plan) y planes (-> nombre) de una cuenta+fecha."""
    visitas = _get_lista(f"{API_BASE}/routes/visits/?planned_date={fecha}", token)
    rutas = _get_lista(f"{API_BASE}/routes/routes/?planned_date={fecha}", token)
    planes = _get_lista(f"{API_BASE}/routes/plans/?start_date={fecha}&end_date={fecha}", token)
    return visitas, rutas, planes


def _fetch_individual(vid, token):
    r = _get(f"{API_BASE}/routes/visits/{vid}", token)
    return r.json() if r is not None and r.status_code == 200 else None


def _fetch_ruta(route_id, token):
    r = _get(f"{API_BASE}/routes/routes/{route_id}/", token)
    return r.json() if r is not None and r.status_code == 200 else None


def _fetch_plan(plan_id, token):
    r = _get(f"{API_BASE}/routes/plans/{plan_id}/", token)
    return r.json() if r is not None and r.status_code == 200 else None


def _fila_vacia(cuenta_valor, fecha, vid, error):
    fila = {c: "" for c in COLUMNAS}
    fila.update({"Cuenta": cuenta_valor, "Fecha de planeacion": fecha or "", "ID de visita": vid, "Error": error})
    return fila


def pagina_detalle_visitas_lvp():
    render_header(
        "Detalle Visitas LVP",
        "Sube cuenta + fecha + ID de visita y obten el reporte completo cruzando todas las cuentas Liverpool",
    )
    render_guide(
        steps=[
            "<strong>Sube el archivo</strong> — CSV o Excel con una columna de cuenta (nombre o ID), una de fecha y una de ID de visita.",
            "<strong>Confirma las columnas</strong> — Indica cual columna corresponde a cada dato si no se detecta bien.",
            "<strong>Procesar</strong> — Se consulta cada cuenta Liverpool por fecha y se cruza por ID de visita (con respaldo de busqueda individual si no aparece).",
            "<strong>Descargar</strong> — Obten el Excel con CR, SKU, transaccion, operacion, UniNegocio, plan, ruta/unidad y estatus.",
        ],
        tip="Si una cuenta o una visita no se encuentra, esa fila queda marcada con el motivo en la columna Error en vez de detener todo el proceso.",
    )

    archivo = st.file_uploader("Archivo (CSV o Excel)", type=["csv", "xlsx", "xls"], key="dvl_archivo")
    if not archivo:
        st.stop()

    try:
        if archivo.name.lower().endswith(".csv"):
            df_in = pd.read_csv(archivo)
        else:
            df_in = pd.read_excel(archivo)
    except Exception as e:
        st.error(f"No se pudo leer el archivo: {e}")
        st.stop()

    if df_in.empty:
        st.warning("El archivo no tiene filas.")
        st.stop()

    render_label("Columnas del archivo")
    cols = list(df_in.columns)
    c1, c2, c3 = st.columns(3)
    with c1:
        col_cuenta = st.selectbox("Cuenta (nombre o ID)", cols, index=0, key="dvl_col_cuenta")
    with c2:
        col_fecha = st.selectbox("Fecha", cols, index=min(1, len(cols) - 1), key="dvl_col_fecha")
    with c3:
        col_id = st.selectbox("ID de visita", cols, index=min(2, len(cols) - 1), key="dvl_col_id")

    st.dataframe(df_in.head(5), use_container_width=True, hide_index=True)

    if not st.button("Procesar archivo", type="primary", key="dvl_procesar"):
        st.stop()

    por_nombre, por_id = _cargar_cuentas()

    filas = []
    for _, row in df_in.iterrows():
        vid = str(row[col_id]).strip()
        if not vid or vid.lower() == "nan":
            continue
        filas.append({
            "vid": vid,
            "cuenta_valor": row[col_cuenta],
            "cuenta": _resolver_cuenta(row[col_cuenta], por_nombre, por_id),
            "fecha": _parse_fecha(row[col_fecha]),
        })

    if not filas:
        st.warning("No se encontraron filas con ID de visita valido.")
        st.stop()

    sin_cuenta = sorted({str(f["cuenta_valor"]) for f in filas if not f["cuenta"]})
    if sin_cuenta:
        st.warning(f"{len(sin_cuenta)} valor(es) de cuenta no coinciden con cuentas.csv: {', '.join(sin_cuenta)}")

    filas_validas = [f for f in filas if f["cuenta"]]
    token_por_cuenta = {f["cuenta"]["nombre"]: f["cuenta"]["token"] for f in filas_validas}

    # --- 1) dumps por (cuenta, fecha) ---
    combos = sorted({(f["cuenta"]["nombre"], f["fecha"]) for f in filas_validas if f["fecha"]})
    visita_por_id, ruta_plan, plan_nombre = {}, {}, {}

    barra = st.progress(0, text=f"Consultando {len(combos)} combinacion(es) cuenta+fecha...")
    if combos:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futs = {
                ex.submit(_fetch_combo, token_por_cuenta[cuenta], fecha): (cuenta, fecha)
                for cuenta, fecha in combos
            }
            done = 0
            for fut in as_completed(futs):
                visitas, rutas, planes = fut.result()
                for v in visitas:
                    visita_por_id[str(v["id"])] = v
                for rt in rutas:
                    ruta_plan[rt["id"]] = rt.get("plan")
                for p in planes:
                    plan_nombre[p["id"]] = p.get("name", "")
                done += 1
                barra.progress(done / len(combos), text=f"Combos cuenta+fecha: {done}/{len(combos)}")

    # --- 2) fallback individual para IDs no resueltos por dump ---
    faltantes = [f for f in filas_validas if f["vid"] not in visita_por_id]
    if faltantes:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futs = {ex.submit(_fetch_individual, f["vid"], f["cuenta"]["token"]): f for f in faltantes}
            done = 0
            for fut in as_completed(futs):
                f = futs[fut]
                v = fut.result()
                if v:
                    visita_por_id[f["vid"]] = v
                done += 1
                barra.progress(done / len(faltantes), text=f"Busqueda individual: {done}/{len(faltantes)}")

    # --- 3) rutas/planes que no vinieron en los dumps (visitas resueltas por fallback) ---
    rutas_faltantes = {
        v["route"]: f["cuenta"]["token"]
        for f in filas_validas
        if (v := visita_por_id.get(f["vid"])) and v.get("route") and v["route"] not in ruta_plan
    }
    if rutas_faltantes:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futs = {ex.submit(_fetch_ruta, rid, tok): rid for rid, tok in rutas_faltantes.items()}
            for fut in as_completed(futs):
                rid = futs[fut]
                rt = fut.result()
                if rt:
                    ruta_plan[rid] = rt.get("plan")

    planes_faltantes = {
        pid: f["cuenta"]["token"]
        for f in filas_validas
        if (v := visita_por_id.get(f["vid"]))
        and (pid := ruta_plan.get(v.get("route")))
        and pid not in plan_nombre
    }
    if planes_faltantes:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futs = {ex.submit(_fetch_plan, pid, tok): pid for pid, tok in planes_faltantes.items()}
            for fut in as_completed(futs):
                pid = futs[fut]
                p = fut.result()
                if p:
                    plan_nombre[pid] = p.get("name", "")

    # --- 4) drivers / vehiculos por cuenta ---
    cuentas_usadas = {f["cuenta"]["nombre"]: f["cuenta"]["token"] for f in filas_validas}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs_d = {c: ex.submit(_get_lista, f"{API_BASE}/accounts/drivers/", tok) for c, tok in cuentas_usadas.items()}
        futs_v = {c: ex.submit(_get_lista, f"{API_BASE}/routes/vehicles/", tok) for c, tok in cuentas_usadas.items()}
    driver_nombre = {c: {d["id"]: d.get("name", "") for d in fut.result()} for c, fut in futs_d.items()}
    vehiculo_nombre = {c: {v["id"]: v.get("name", "") for v in fut.result()} for c, fut in futs_v.items()}

    barra.progress(1.0, text="Armando reporte...")

    # --- 5) armar filas de salida ---
    filas_out = []
    for f in filas:
        vid = f["vid"]
        if not f["cuenta"]:
            filas_out.append(_fila_vacia(f["cuenta_valor"], f["fecha"], vid, "cuenta no encontrada en cuentas.csv"))
            continue
        cuenta_nombre = f["cuenta"]["nombre"]
        v = visita_por_id.get(vid)
        if not v:
            filas_out.append(_fila_vacia(cuenta_nombre, f["fecha"], vid, "visita no encontrada"))
            continue

        efv = v.get("extra_field_values") or {}
        nombre_driver = driver_nombre.get(cuenta_nombre, {}).get(v.get("driver")) or ""
        partes = nombre_driver.split(" ", 1)
        plan_uuid = ruta_plan.get(v.get("route"))

        filas_out.append({
            "Cuenta": cuenta_nombre,
            "Fecha de planeacion": v.get("planned_date", ""),
            "ID de visita": vid,
            "Nombre del CR": partes[1] if len(partes) > 1 else "",
            "Numero de CR": partes[0] if partes else "",
            "SKU": str(efv.get("sku") or ""),
            "Reference": str(v.get("reference") or ""),
            "ID de Transaccion": str(efv.get("id_transaccion") or ""),
            "Operacion": str(efv.get("operacion") or ""),
            "UniNegocio": str(efv.get("uninegocio") or ""),
            "Estatus actual de la orden": v.get("status", ""),
            "Fecha y hora del estatus en SimpliRoute": v.get("modified", ""),
            "Nombre del plan": plan_nombre.get(plan_uuid, ""),
            "Fecha de planeacion (entrega)": v.get("checkout_time") or "",
            "Ruta / Unidad": vehiculo_nombre.get(cuenta_nombre, {}).get(v.get("vehicle")) or "",
            "ID de Ruta": str(v.get("route") or ""),
            "Error": "",
        })

    barra.progress(1.0, text="Completado")
    df_out = pd.DataFrame(filas_out, columns=COLUMNAS)

    con_error = int((df_out["Error"] != "").sum())
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(render_stat(len(df_out) - con_error, "resueltas"), unsafe_allow_html=True)
    with col2:
        st.markdown(
            render_stat(con_error, "con error", style="background: linear-gradient(135deg, #d32f2f 0%, #b71c1c 100%);"),
            unsafe_allow_html=True,
        )

    st.dataframe(df_out, use_container_width=True, hide_index=True)

    buffer = io.BytesIO()
    df_out.to_excel(buffer, index=False)
    st.download_button(
        "Descargar Excel",
        data=buffer.getvalue(),
        file_name="detalle_visitas_lvp.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="dvl_download",
    )
