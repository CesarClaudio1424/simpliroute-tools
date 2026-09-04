import streamlit as st
import webhook
from utils import (
    render_header, render_guide, render_stat, render_label,
    render_tip, render_error_item, render_cuenta_badge,
    create_progress_tracker, update_progress, finish_progress,
    scroll_to_bottom, load_secret,
)


def pagina_webhooks():
    render_header("Procesamiento de Webhooks Likewise", "Automatizacion de rutas y visitas")

    render_guide(
        steps=[
            '<strong>Selecciona la cuenta</strong> — Elige la empresa Likewise a la que quieres enviar los webhooks.',
            '<strong>Elige las acciones</strong> — Puedes ejecutar Creacion, Inicio de ruta, Checkout, o Exclusion de visitas. No puedes mezclar Exclusiones con las demas.',
            '<strong>Ingresa los datos</strong> — Creacion/Inicio/Checkout: <code>route_id</code> (UUID) de SimpliRoute. Exclusiones: IDs de visita. Uno por linea.',
            '<strong>Procesa</strong> — Las rutas se envian una a una. Las exclusiones se envian todas en un solo request.',
        ],
        tip='Creacion, Inicio y Checkout reenvian el webhook nativo de SimpliRoute (igual que la pestaña Rutas de Reenvio de Webhooks / Checkout General). Exclusiones va al gateway Hermes/Brightcell: primero resuelve cada ID contra SimpliRoute (reference), luego excluye en Hermes.',
    )

    # --- Paso 1: Cuenta ---
    render_label("Paso 1 · Cuenta")
    cuenta = st.radio(
        "Cuenta",
        list(webhook.ACCOUNT_TOKENS.keys()),
        horizontal=True,
        label_visibility="collapsed",
    )

    render_cuenta_badge(f"Cuenta seleccionada: <strong>{cuenta}</strong>")

    # --- Paso 2: Acciones ---
    render_label("Paso 2 · Acciones")

    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        creacion = st.checkbox("Creacion", key="wh_creacion")
    with col_b:
        inicio = st.checkbox("Inicio", key="wh_inicio")
    with col_c:
        checkout = st.checkbox("Checkout", key="wh_checkout")
    with col_d:
        exclusion = st.checkbox("Exclusiones", key="wh_exclusion")

    if exclusion and (creacion or inicio or checkout):
        render_tip(
            "<strong>⚠️ Atencion:</strong> No puedes mezclar Exclusiones con las demas acciones. Desmarca una de las opciones.",
            warning=True,
        )
        st.stop()

    if not (creacion or inicio or checkout or exclusion):
        render_tip("Selecciona al menos una accion para continuar.")
        st.stop()

    # --- Paso 3: Datos ---
    render_label("Paso 3 · Rutas o visitas")

    placeholder = "Ingresa los IDs de visita (uno por linea)" if exclusion else "Ingresa los route_id (UUID) de las rutas, uno por linea"
    rutas_input = st.text_area(
        "Datos",
        placeholder=placeholder,
        label_visibility="collapsed",
        height=150,
    )

    if not rutas_input or not rutas_input.strip():
        render_tip(f'Ingresa {"los IDs de visita" if exclusion else "los route_id (UUID)"} a procesar, uno por linea.')
        st.stop()

    items = [line.strip() for line in rutas_input.strip().split("\n") if line.strip()]

    # --- Paso opcional: eliminar de SimpliRoute ---
    eliminar_sr = False
    if exclusion:
        st.divider()
        eliminar_sr = st.checkbox(
            "Tambien eliminar visitas de SimpliRoute",
            help="Quita la ruta y mueve la fecha a 2020-01-01, solo para las visitas que Hermes confirme excluidas",
            key="wh_eliminar_sr",
        )

    acciones_sel = []
    if creacion:
        acciones_sel.append("Creacion")
    if inicio:
        acciones_sel.append("Inicio")
    if checkout:
        acciones_sel.append("Checkout")
    if exclusion:
        acciones_sel.append("Exclusiones")

    col_stat1, col_stat2 = st.columns(2)
    with col_stat1:
        st.markdown(
            render_stat(len(items), f'{"visitas" if exclusion else "rutas"} a procesar'),
            unsafe_allow_html=True,
        )
    with col_stat2:
        st.markdown(
            render_stat(len(acciones_sel), f'{"accion" if len(acciones_sel) == 1 else "acciones"}: {", ".join(acciones_sel)}'),
            unsafe_allow_html=True,
        )

    if not st.button("Procesar webhooks", type="primary", key="btn_webhooks"):
        st.stop()

    # --- Procesamiento ---
    if exclusion:
        token_key = webhook.ACCOUNT_TOKENS[cuenta]
        token = load_secret(token_key, f"Token de {cuenta} no encontrado en secrets (api_config.{token_key})")
        api_key = webhook.obtener_hermes_api_key(cuenta)
        if not api_key:
            st.error(f"Falta la clave Hermes de {cuenta} en secrets ([brightcell_hermes].{webhook.HERMES_KEYS[cuenta]}).")
            st.stop()

        barra = st.progress(0, text="Resolviendo referencias y excluyendo via Hermes...")
        detalle, sin_resolver, confirmados = webhook.procesar_exclusion_hermes(token, api_key, items)
        barra.progress(1.0, text="Finalizado")

        if confirmados:
            st.success(f"{len(confirmados)} visita(s) excluidas correctamente en Hermes")

        rechazados = [d for d in detalle if d["status"] != "ok"]
        if rechazados:
            render_error_item(f"{len(rechazados)} visita(s) rechazadas por Hermes")
            with st.expander("Detalle de rechazos Hermes"):
                st.json(rechazados)

        if sin_resolver:
            render_error_item(f"{len(sin_resolver)} referencia(s) no se encontraron en SimpliRoute")
            with st.expander("Detalle de referencias no resueltas"):
                st.json(sin_resolver)

        # --- Limpieza opcional en SimpliRoute (solo lo confirmado por Hermes) ---
        if eliminar_sr and confirmados:
            st.divider()
            render_label("Limpieza en SimpliRoute")

            ok_l, status_l, body_l = webhook.limpiar_visitas_hermes(token, confirmados)
            if ok_l:
                st.success(f"{len(confirmados)} visita(s) limpiadas en SimpliRoute")
            else:
                render_error_item(f"No se pudieron limpiar las visitas (HTTP {status_l})")
                if body_l:
                    with st.expander("Detalle del error"):
                        st.code(body_l[:500])
        scroll_to_bottom()
    else:
        token_post = load_secret("checkout_token", "Token `checkout_token` no encontrado en secrets (api_config.checkout_token)")
        token_key = webhook.ACCOUNT_TOKENS[cuenta]
        token_get = load_secret(token_key, f"Token de {cuenta} no encontrado en secrets (api_config.{token_key})")
        account_id = webhook.ACCOUNT_IDS[cuenta]

        operaciones = []
        if creacion:
            for item in items:
                operaciones.append(("Creacion", item))
        if inicio:
            for item in items:
                operaciones.append(("Inicio", item))
        if checkout:
            for item in items:
                operaciones.append(("Checkout", item))

        total = len(operaciones)
        exitosos = 0
        fallidos = []

        barra, contador, contenedor_errores = create_progress_tracker(total, "Procesando webhooks...")

        for i, (accion, item) in enumerate(operaciones):
            if accion == "Creacion":
                ok, detalle = webhook.enviar_route_webhook(token_post, item, "route_created")
            elif accion == "Inicio":
                ok, detalle = webhook.enviar_route_webhook(token_post, item, "route_started")
            else:
                ok, detalle = webhook.procesar_checkout(token_get, token_post, account_id, item)
            procesados = i + 1

            if ok:
                exitosos += 1
            else:
                fallidos.append((accion, item, detalle))
                with contenedor_errores:
                    render_error_item(f"{accion}: ruta {item} — {detalle}")

            update_progress(barra, contador, procesados, total, "Procesando webhooks...")

        finish_progress(barra)

        if exitosos > 0:
            st.success(f"{exitosos} de {total} procesados correctamente")
        if fallidos:
            st.error(f"{len(fallidos)} de {total} fallaron")
        scroll_to_bottom()
