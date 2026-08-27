import psycopg2
import psycopg2.extras
import streamlit as st
from config import EXTENSIONES_QUERY_LIMIT, EXTENSIONES_MIN_SEARCH_LEN
from utils import render_header, render_guide, render_label, render_tip, render_stat

QUERY_EXTENSIONES = """
select
    ee.label
  , eu.account_id_id as account_id
  , aa.name as account_name
  , au.name as user_name
  , eu.user_id_id as user_id
  , ee.urls
from extensions_extensions ee
join extensions_userextensions eu on eu.extension_url_id = ee.id
join accounts_account aa on aa.id = eu.account_id_id
join accounts_user au on au.id = eu.user_id_id
where aa.name ilike %s
order by aa.name, au.name
limit %s
"""


def _get_readonly_connection():
    try:
        cfg = st.secrets["readonly_bi"]
        return psycopg2.connect(
            host=cfg["host"],
            port=cfg["port"],
            dbname=cfg["dbname"],
            user=cfg["user"],
            password=cfg["password"],
            connect_timeout=10,
        )
    except KeyError:
        st.error("Faltan credenciales en secrets. Agregar [readonly_bi] con host, port, dbname, user y password.")
        st.stop()
    except psycopg2.OperationalError as e:
        st.error(f"No se pudo conectar a la base de datos: {e}")
        st.stop()


def _buscar_extensiones(account_name: str) -> tuple[list[dict], str]:
    """SELECT sobre extensions_extensions/extensions_userextensions filtrado por nombre de cuenta (ILIKE)."""
    conn = _get_readonly_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(QUERY_EXTENSIONES, (f"%{account_name}%", EXTENSIONES_QUERY_LIMIT))
            return [dict(row) for row in cur.fetchall()], ""
    except psycopg2.Error as e:
        return [], str(e)
    finally:
        conn.close()


def pagina_consulta_extensiones():
    render_header("Consulta Extensiones", "Busca que usuarios tienen una extension (app embebida) asignada, por nombre de cuenta")

    render_guide(
        steps=[
            "<strong>Nombre de cuenta</strong> — Escribe parte del nombre de la cuenta SimpliRoute a buscar.",
            "<strong>Buscar</strong> — Se consulta la base de datos interna (solo lectura) y se listan las extensiones asignadas.",
        ],
        tip="Esta consulta cruza <em>todas</em> las cuentas de SimpliRoute, no solo una — es informacion interna sensible, usar con criterio.",
    )

    render_label("Nombre de cuenta")
    account_name = st.text_input(
        "Nombre de cuenta", placeholder="Liverpool, Cencosud, eleva...",
        label_visibility="collapsed", key="ce_account_name",
    )

    if not account_name or len(account_name.strip()) < EXTENSIONES_MIN_SEARCH_LEN:
        render_tip(f"Escribe al menos {EXTENSIONES_MIN_SEARCH_LEN} caracteres del nombre de la cuenta.")
        st.stop()

    if not st.button("Buscar", type="primary", key="ce_btn_buscar"):
        st.stop()

    with st.spinner("Consultando..."):
        resultados, err = _buscar_extensiones(account_name.strip())

    if err:
        st.error(f"Error al consultar: {err}")
        st.stop()

    if not resultados:
        render_tip("No se encontraron extensiones para ese nombre de cuenta.")
        st.stop()

    st.markdown(render_stat(len(resultados), "resultado(s)"), unsafe_allow_html=True)
    if len(resultados) == EXTENSIONES_QUERY_LIMIT:
        render_tip(f"Se alcanzo el limite de {EXTENSIONES_QUERY_LIMIT} filas — refina la busqueda para ver todos los resultados.", warning=True)

    st.dataframe(resultados, use_container_width=True, hide_index=True)
