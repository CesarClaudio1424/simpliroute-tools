---
name: reference-account-lookup-retool
description: Endpoint Retool para buscar cuentas SimpliRoute por nombre y resolver su token; implementado en account_lookup.py
metadata:
  type: reference
---

Existe un endpoint Retool publico que expone dos queries SQL sobre la BD de SimpliRoute, usado originalmente por Brandon (ver [[project_migracion_nextjs_brandon]]) para su feature de "busqueda de cuenta":

- URL base: `https://simpliroute.tryretool.com/api/public/76dab1ca-e7a8-4133-a8b3-692d49307567`
- `POST {base}/query?queryName=clients_by_country` — catalogo de cuentas activas/trialing de un pais (`CL`, `MX`, `PE`, `AR`, `BR`, `CO`). Body: `{"userParams":{"queryParams":{"0":false,"1":[...paises],"2":pais,"length":3}, ...overrideParams vacios...}, "password":"", "environment":"production", "queryType":"SqlQuery", "frontendVersion":"1", "releaseVersion":null, "includeQueryExecutionMetadata":true, "streamResponse":false}`. Respuesta columnar `queryData.{id,name,country,status}`.
- `POST {base}/query?queryName=GetToken` — token de una cuenta por `account_id`. Body con `queryParams: {"0": account_id, "length": 1}`. Respuesta `queryData.key` (lista con 0 o 1 elemento).

**Confirmado 2026-09-03** contra la cuenta real Liverpool La Paz (id 12494): el `key` devuelto coincidio exacto con el token ya conocido de esa cuenta. No hace falta ningun token/HMAC propio de Brandon — el endpoint responde igual desde cualquier lado (es infraestructura Retool de Simpli, no de su app). Nota: cuentas internas/personales (ej. la cuenta de pruebas de Cesar, 56065) devuelven `key: []` — la query solo resuelve token para cuentas reales de cliente.

**Actualizacion 2026-09-03 (tarde):** se agregaron dos mejoras:
1. **Prelistado al escribir** — ya no hace falta click en "Cargar cuentas"/"Buscar": basta escribir >=2 letras y confirmar (Enter/blur) para que aparezcan resultados automaticamente. Cache por pais en `session_state["sidebar_al_cache_{pais}"]`.
2. **Pais "Otros"** — el dropdown original de Brandon tiene una opcion "Otros paises" para cuentas fuera de CL/MX/PE/AR/BR/CO. Esa opcion **no** usa Retool (la query `clients_by_country` de Brandon solo acepta los 6 paises primarios por su propio schema) — usa un endpoint real de SimpliRoute: `GET https://api.simpliroute.com/v1/accounts/admin-portal/accounts/` con params `search`, `status`, `page`, `page_size` (sin `region` para incluir todos, filtrando localmente los que no son de los 6 paises principales). Este endpoint exige un **Staff Token interno de SimpliRoute** (401/403 si no es valido o no tiene permisos) — Cesar SI tiene uno propio, guardado en secrets `[account_lookup] staff_token`. Implementado en `buscar_cuentas_otros()` en account_lookup.py. Probado en vivo: devuelve cuentas reales (Aje Bolivia, Aje Honduras, Arca Continental Ecuador, etc.) y el token se resuelve y valida igual que las demas.

**Sensibilidad del Staff Token:** es una credencial mucho mas amplia que un token de cuenta normal — da acceso al directorio Admin Portal de TODAS las cuentas de SimpliRoute globalmente. Por diseño solo se usa cuando el pais seleccionado es "Otros" (nunca para los 6 paises primarios, que siguen usando Retool). Vive unicamente en `.streamlit/secrets.toml` (gitignoreado) — falta agregarlo tambien en el secrets management de Streamlit Cloud para que funcione en la app desplegada (`pruebas`), ya que `secrets.toml` local no viaja con el deploy.

**Como aplicar (arquitectura final, 2026-09-03):**
- `account_lookup.py` tiene las funciones nucleo: `buscar_cuentas(country)`, `resolver_token(account_id)`, `validar_token_cuenta(token)` (valida contra `GET /accounts/me/`).
- El buscador vive UNA sola vez, global, en la barra lateral: `render_sidebar_cuenta_activa()` (llamado desde `main.py`). Busca cuenta por pais+nombre, resuelve y valida el token, y lo guarda en `st.session_state["cuenta_activa"] = {"token", "name", "id"}` — el token NUNCA se muestra en ningun lado, solo el nombre de la cuenta ("🟢 Cuenta activa: X"). Boton "Quitar cuenta activa" limpia el estado.
- Cada pagina con token manual llama `campo_token(key_prefix, placeholder=...)` en vez de crear su propio `st.text_input`. Si hay cuenta activa global, muestra un tip "✓ Usando la cuenta activa..." y devuelve el token oculto; si no, cae al `st.text_input(type="password", key=f"{key_prefix}_token")` de siempre (comportamiento identico al original, mismo nombre de key).
- Conectado en las 6 paginas con token manual: `edicion.py` (key "edicion"), `reporte_visitas.py` ("rep"), `zonas_kml.py` ("kml"), `motivos_rechazo.py` ("mr"), `eventos_ruta.py` ("ev"), `cambiar_fecha_plan.py` (3 tabs: "cfp", "cfr", "cfv").
- Probado en navegador (Playwright) end-to-end: buscar cuenta -> cuenta activa oculta se propaga a todas las paginas -> "Quitar cuenta activa" revierte a entrada manual en cada una. Sin errores de consola.
- Diseño pedido explicitamente por el usuario: "si tu no lo buscas tienes que ponerlo manual, pero si lo buscas no lo expone, solo te dice que cuenta editaras".
