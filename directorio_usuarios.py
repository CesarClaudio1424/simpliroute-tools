import csv
import io
import math
import re
import unicodedata
import pandas as pd
import requests
import streamlit as st
from config import API_BASE, API_GATEWAY_BASE, REQUEST_TIMEOUT
from utils import render_header, render_guide, render_label, render_tip, render_cuenta_badge
from account_lookup import campo_token

MAX_USER_SNAPSHOT_ROWS = 20000
USERS_LOAD_TIMEOUT = 120
FLEETS_MAX_PAGES = 50

ROLE_COLS = [
    ("is_owner", "Propietario"),
    ("is_admin", "Administrador"),
    ("is_driver", "Conductor"),
    ("is_router_jr", "Ruteador Jr"),
    ("is_monitor", "Monitor"),
    ("is_coordinator", "Coordinador"),
    ("is_router", "Ruteador"),
    ("is_staff", "Staff"),
]

SORT_COLUMNS = {
    "Usuario": ("username", False),
    "Contacto": ("email", False),
    "Roles": ("roles_label", False),
    "Modificado": ("modified", True),
    "Ultimo acceso": ("last_login", True),
}


def _headers(token):
    return {"Authorization": f"Token {token}", "Content-Type": "application/json"}


def _limpiar_token(token):
    token = (token or "").strip()
    for prefijo in ("token ", "bearer "):
        if token.lower().startswith(prefijo):
            token = token[len(prefijo):].strip()
            break
    return token


def _validar_cuenta(token):
    try:
        r = requests.get(f"{API_BASE}/accounts/me/", headers=_headers(token), timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            return True, r.json().get("account", {}).get("name", "Sin nombre")
    except requests.exceptions.RequestException:
        pass
    return False, None


def _normalizar(texto):
    texto = str(texto or "")
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.lower()
    texto = re.sub(r"[-\s]+", " ", texto).strip()
    return texto


def _formatear_fecha(valor):
    if not valor:
        return ""
    ts = pd.to_datetime(valor, errors="coerce")
    if pd.isna(ts):
        return ""
    return ts.strftime("%d/%m/%Y %H:%M")


def _preparar_df(filas):
    registros = []
    for row in filas:
        reg = {
            "id": row.get("id"),
            "old_id": str(row.get("old_id")) if row.get("old_id") is not None else "",
            "username": row.get("username") or "",
            "name": row.get("name") or "",
            "email": row.get("email") or "",
            "phone": row.get("phone") or "",
            "status": row.get("status") or "",
            "created": row.get("created"),
            "modified": row.get("modified"),
            "last_login": row.get("last_login"),
        }
        for col, _ in ROLE_COLS:
            reg[col] = row.get(col) is True
        reg["roles_label"] = ", ".join(lbl for col, lbl in ROLE_COLS if reg[col]) or "Sin roles activos"
        reg["_modified_fmt"] = _formatear_fecha(reg["modified"])
        reg["_last_login_fmt"] = _formatear_fecha(reg["last_login"])
        reg["_phone_digits"] = re.sub(r"\D", "", reg["phone"])
        campos_busqueda = [
            str(reg["id"]), reg["old_id"], reg["username"], reg["name"], reg["email"],
            reg["phone"], reg["roles_label"], reg["modified"] or "", reg["last_login"] or "",
            reg["_modified_fmt"], reg["_last_login_fmt"],
        ]
        reg["_search_blob"] = [_normalizar(c) for c in campos_busqueda if c]
        registros.append(reg)
    return pd.DataFrame(registros)


def _cargar_usuarios(token):
    url = f"{API_GATEWAY_BASE}/accounts/users/"
    try:
        r = requests.get(url, headers=_headers(token), timeout=USERS_LOAD_TIMEOUT)
    except requests.exceptions.RequestException as e:
        return None, None, f"Error de conexion al listar usuarios: {e}"
    if r.status_code != 200:
        return None, None, f"HTTP {r.status_code} al listar usuarios: {r.text[:300]}"
    try:
        data = r.json()
    except ValueError:
        return None, None, "La respuesta de la API no es JSON valido."
    if not isinstance(data, list):
        return None, None, "La API no devolvio un array plano de usuarios (formato inesperado)."

    for row in data:
        status = row.get("status") if isinstance(row, dict) else None
        if not isinstance(status, str) or not status.strip():
            return None, None, (
                "Se encontro un registro con 'status' vacio, ausente o invalido. "
                "Se aborta la carga para no ocultar datos corruptos."
            )

    activos = [row for row in data if row["status"].strip().lower() == "active"]

    vistos = set()
    invalidos = 0
    duplicados = 0
    filas = []
    for row in activos:
        uid = row.get("id")
        if not isinstance(uid, int) or isinstance(uid, bool) or uid <= 0:
            invalidos += 1
            continue
        if uid in vistos:
            duplicados += 1
            continue
        vistos.add(uid)
        filas.append(row)

    if len(filas) > MAX_USER_SNAPSHOT_ROWS:
        return None, None, (
            f"Se encontraron {len(filas)} usuarios activos, supera el limite de "
            f"{MAX_USER_SNAPSHOT_ROWS}. No se cargo el listado."
        )

    df = _preparar_df(filas)
    return df, {"invalidos": invalidos, "duplicados": duplicados}, None


def _obtener_usuario(token, user_id):
    url = f"{API_GATEWAY_BASE}/accounts/users/{user_id}/"
    try:
        r = requests.get(url, headers=_headers(token), timeout=REQUEST_TIMEOUT)
    except requests.exceptions.RequestException as e:
        return None, f"Error de conexion: {e}"
    if r.status_code != 200:
        return None, f"HTTP {r.status_code} al consultar el usuario."
    try:
        return r.json(), None
    except ValueError:
        return None, "Respuesta invalida de la API."


def _listar_flotas(token):
    url = f"{API_BASE}/fleets/"
    flotas = []
    for _ in range(FLEETS_MAX_PAGES):
        r = requests.get(url, headers=_headers(token), timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list):
            flotas.extend(data)
            break
        flotas.extend(data.get("results", []))
        url = data.get("next")
        if not url:
            break
    return flotas


def _rank_campo(valor, query_norm):
    if not valor or not query_norm:
        return None
    if valor == query_norm:
        return 0
    if valor.startswith(query_norm):
        return 1
    if query_norm in valor:
        return 2
    return None


def _ordenar_por_columna(df, columna, ascendente):
    campo, es_fecha = SORT_COLUMNS[columna]

    def es_nulo(v):
        return v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == ""

    mascara_nula = df[campo].apply(es_nulo)
    con_valor = df[~mascara_nula].copy()
    sin_valor = df[mascara_nula].copy()

    if es_fecha:
        parsed = pd.to_datetime(con_valor[campo], errors="coerce")
        if parsed.notna().all():
            con_valor = con_valor.assign(_clave=parsed)
        else:
            con_valor = con_valor.assign(_clave=con_valor[campo].astype(str).str.lower())
    else:
        con_valor = con_valor.assign(_clave=con_valor[campo].astype(str).str.lower())

    con_valor = con_valor.sort_values(by=["_clave", "id"], ascending=[ascendente, True]).drop(columns=["_clave"])
    sin_valor = sin_valor.sort_values(by="id", ascending=True)
    return pd.concat([con_valor, sin_valor], ignore_index=True)


def _filtrar_y_ordenar(df, query, orden_sel, ascendente):
    query = (query or "").strip()

    if query:
        q_norm = _normalizar(query)
        q_digitos = re.sub(r"\D", "", query)
        usar_digitos = len(q_digitos) >= 3
        ranks = []
        for blob, phone_dig in zip(df["_search_blob"], df["_phone_digits"]):
            mejor = None
            for campo in blob:
                r = _rank_campo(campo, q_norm)
                if r is not None and (mejor is None or r < mejor):
                    mejor = r
                if mejor == 0:
                    break
            if usar_digitos and phone_dig and mejor != 0:
                r = _rank_campo(phone_dig, q_digitos)
                if r is not None and (mejor is None or r < mejor):
                    mejor = r
            ranks.append(mejor)
        filtrado = df.assign(_rank=ranks)
        filtrado = filtrado[filtrado["_rank"].notna()]
    else:
        filtrado = df.assign(_rank=0)

    if orden_sel != "Relevancia":
        filtrado = _ordenar_por_columna(filtrado.drop(columns=["_rank"]), orden_sel, ascendente)
    elif query:
        filtrado = filtrado.sort_values(by=["_rank", "id"], ascending=[True, True]).drop(columns=["_rank"])
    else:
        filtrado = filtrado.sort_values(
            by="username", key=lambda s: s.str.lower(), ascending=True
        ).drop(columns=["_rank"])

    return filtrado.reset_index(drop=True)


def _sanitizar_csv(valor):
    s = "" if valor is None else str(valor)
    if re.match(r"^[ \t]*[=+\-@]", s):
        return "'" + s
    return s


def _generar_csv(filtrado):
    buffer = io.StringIO()
    writer = csv.writer(buffer, quoting=csv.QUOTE_ALL)
    writer.writerow(["ID", "ID anterior", "Usuario", "Nombre", "Email", "Telefono", "Roles", "Modificado", "Ultimo acceso"])
    for _, row in filtrado.iterrows():
        writer.writerow([
            _sanitizar_csv(row["id"]),
            _sanitizar_csv(row["old_id"]),
            _sanitizar_csv(row["username"]),
            _sanitizar_csv(row["name"]),
            _sanitizar_csv(row["email"]),
            _sanitizar_csv(row["phone"]),
            _sanitizar_csv(row["roles_label"]),
            _sanitizar_csv(row["_modified_fmt"]),
            _sanitizar_csv(row["_last_login_fmt"]),
        ])
    return buffer.getvalue().encode("utf-8-sig")


def _formato_contacto(row):
    partes = [row["name"], row["email"], row["phone"]]
    return " · ".join(p for p in partes if p) or "—"


def _render_detalle(token, user_id):
    with st.spinner("Consultando detalle..."):
        record, err = _obtener_usuario(token, user_id)

    if err:
        st.error(err)
        return
    if not isinstance(record.get("status"), str) or record["status"].strip().lower() != "active":
        st.error("El usuario ya no esta activo.")
        return

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown(
            f"**Usuario:** {record.get('username') or '—'}  \n"
            f"**Nombre:** {record.get('name') or '—'}  \n"
            f"**Email:** {record.get('email') or '—'}  \n"
            f"**Telefono:** {record.get('phone') or '—'}"
        )
    with col_b:
        old_id = record.get("old_id")
        st.markdown(
            f"**ID:** {record.get('id')}  \n"
            f"**ID anterior:** {str(old_id) if old_id is not None else '—'}  \n"
            f"**Modificado:** {_formatear_fecha(record.get('modified')) or '—'}  \n"
            f"**Ultimo acceso:** {_formatear_fecha(record.get('last_login')) or '—'}"
        )

    st.markdown("**Roles:**")
    chips = "".join(
        f'<span style="display:inline-block;padding:0.2rem 0.7rem;margin:0.15rem 0.3rem 0.15rem 0;'
        f'border-radius:999px;background:#2A2BA1;color:#fff;font-size:0.82rem;">{lbl}</span>'
        for col, lbl in ROLE_COLS if record.get(col) is True
    )
    st.markdown(chips if chips else "Sin roles activos", unsafe_allow_html=True)

    try:
        todas_flotas = _listar_flotas(token)
        flotas_ok = True
    except (requests.exceptions.RequestException, ValueError):
        todas_flotas = []
        flotas_ok = False

    if not flotas_ok:
        st.warning("No se pudo consultar las flotas de la cuenta; no se puede confirmar si este usuario pertenece a alguna.")
    else:
        vistas = {}
        for f in todas_flotas:
            fid = f.get("id")
            if fid is None or fid in vistas:
                continue
            if user_id in (f.get("users") or []):
                vistas[fid] = f.get("name") or f"Flota {fid}"
        flotas_usuario = sorted(vistas.values(), key=lambda s: s.lower())
        total_cuenta = len({f.get("id") for f in todas_flotas if f.get("id") is not None})
        if flotas_usuario:
            st.markdown(f"**Flotas:** {', '.join(flotas_usuario)} ({len(flotas_usuario)}/{total_cuenta})")
        else:
            st.info(f"Este usuario no pertenece a ninguna flota (0/{total_cuenta}).")

    with st.expander("Ver registro completo (JSON)"):
        st.json(record)


def pagina_directorio_usuarios():
    render_header(
        "Directorio de Usuarios",
        "Consulta, busca y exporta el listado de usuarios activos de la cuenta",
    )

    render_guide(
        steps=[
            "<strong>Ingresa el token</strong> — Token de API de la cuenta a consultar.",
            "<strong>Carga usuarios</strong> — Descarga un snapshot completo de todos los usuarios activos (puede tardar unos segundos).",
            "<strong>Busca y ordena</strong> — Todo ocurre en memoria: por ID, usuario, nombre, email, telefono o rol.",
            "<strong>Exporta a CSV</strong> — Descarga todas las coincidencias de tu busqueda actual, no solo la pagina visible.",
            "<strong>Ve el detalle</strong> — Selecciona un usuario en la tabla para ver sus roles y flotas.",
        ],
        tip="El listado es un snapshot: si un usuario cambia despues de cargarlo, usa 'Recargar usuarios' para refrescarlo.",
    )

    render_label("Token de API")
    token = campo_token("du", placeholder="Token de API")
    if not token or not token.strip():
        render_tip("Ingresa el token de API de la cuenta.")
        st.stop()
    token = _limpiar_token(token)

    valido, cuenta = _validar_cuenta(token)
    if not valido:
        st.error("Token invalido. Revisa tu token de API.")
        st.stop()
    render_cuenta_badge(f"Conectado a: <strong>{cuenta}</strong>")

    if st.session_state.get("du_token_cargado") != token:
        st.session_state.pop("du_df", None)

    label_btn = "Recargar usuarios" if "du_df" in st.session_state else "Cargar usuarios"
    if st.button(label_btn, key="du_btn_cargar", type="primary"):
        with st.spinner("Descargando usuarios..."):
            df, descartes, error = _cargar_usuarios(token)
        if error:
            st.error(error)
            st.session_state.pop("du_df", None)
        else:
            st.session_state.du_df = df
            st.session_state.du_descartes = descartes
            st.session_state.du_token_cargado = token
            st.session_state.du_page = 1
            st.session_state.pop("du_detalle_id", None)

    if "du_df" not in st.session_state:
        st.stop()

    df = st.session_state.du_df
    descartes = st.session_state.du_descartes
    if descartes["invalidos"] or descartes["duplicados"]:
        render_tip(
            f"Se descartaron {descartes['invalidos']} registro(s) con id invalido y "
            f"{descartes['duplicados']} duplicado(s) al cargar el snapshot.",
            warning=True,
        )

    render_label(f"Usuarios cargados: {len(df)} (total del snapshot)")

    if df.empty:
        render_tip("No hay usuarios activos en esta cuenta.")
        st.stop()

    col_q, col_orden, col_dir = st.columns([3, 2, 1])
    with col_q:
        query = st.text_input(
            "Buscar", key="du_query",
            placeholder="ID, usuario, nombre, email, telefono o rol...",
            label_visibility="collapsed",
        )
    with col_orden:
        orden_sel = st.selectbox(
            "Ordenar por", ["Relevancia"] + list(SORT_COLUMNS.keys()),
            key="du_orden", label_visibility="collapsed",
        )
    with col_dir:
        st.session_state.setdefault("du_asc", True)
        etiqueta_dir = "↑ Asc" if st.session_state.du_asc else "↓ Desc"
        if st.button(etiqueta_dir, key="du_dir_btn", use_container_width=True):
            st.session_state.du_asc = not st.session_state.du_asc
            st.rerun()

    filtrado = _filtrar_y_ordenar(df, query, orden_sel, st.session_state.du_asc)

    cols_metric = st.columns(6)
    metricas = [
        ("Usuarios activos", len(filtrado)),
        ("Administradores", int(filtrado["is_admin"].sum())),
        ("Conductores", int(filtrado["is_driver"].sum())),
        ("Monitores", int(filtrado["is_monitor"].sum())),
        ("Ruteadores", int(filtrado["is_router"].sum())),
        ("Coordinadores", int(filtrado["is_coordinator"].sum())),
    ]
    for c, (label, valor) in zip(cols_metric, metricas):
        c.metric(label, valor)

    if filtrado.empty:
        render_tip("Sin coincidencias para esa busqueda.")
        st.stop()

    col_ps, col_export = st.columns([1, 2])
    with col_ps:
        page_size = st.selectbox("Por pagina", [25, 50, 100], key="du_page_size")
    with col_export:
        st.download_button(
            "Exportar CSV (todas las coincidencias)",
            data=_generar_csv(filtrado),
            file_name="directorio_usuarios.csv",
            mime="text/csv",
            key="du_export_csv",
        )

    total_paginas = max(1, math.ceil(len(filtrado) / page_size))
    st.session_state.setdefault("du_page", 1)
    st.session_state.du_page = min(max(st.session_state.du_page, 1), total_paginas)

    col_prev, col_info, col_next = st.columns([1, 2, 1])
    with col_prev:
        if st.button("< Anterior", key="du_prev", disabled=st.session_state.du_page <= 1, use_container_width=True):
            st.session_state.du_page -= 1
            st.rerun()
    with col_info:
        st.markdown(
            f"<div style='text-align:center;padding-top:0.4rem;'>Pagina {st.session_state.du_page} de {total_paginas}</div>",
            unsafe_allow_html=True,
        )
    with col_next:
        if st.button("Siguiente >", key="du_next", disabled=st.session_state.du_page >= total_paginas, use_container_width=True):
            st.session_state.du_page += 1
            st.rerun()

    inicio = (st.session_state.du_page - 1) * page_size
    pagina_df = filtrado.iloc[inicio:inicio + page_size].reset_index(drop=True)

    display_df = pd.DataFrame({
        "ID": pagina_df["id"],
        "Usuario": pagina_df["username"],
        "Contacto": pagina_df.apply(_formato_contacto, axis=1),
        "Roles": pagina_df["roles_label"],
        "Modificado": pagina_df["_modified_fmt"],
        "Ultimo acceso": pagina_df["_last_login_fmt"],
    })

    evento = st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="du_tabla",
    )
    if evento.selection.rows:
        st.session_state.du_detalle_id = int(pagina_df.iloc[evento.selection.rows[0]]["id"])

    render_label("Detalle de usuario")
    detalle_id = st.session_state.get("du_detalle_id")
    if not detalle_id:
        render_tip("Selecciona un usuario en la tabla para ver su detalle.")
    else:
        _render_detalle(token, detalle_id)
