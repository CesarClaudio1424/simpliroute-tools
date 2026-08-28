Revisa un curl (o pegado de headers+body) de creacion/edicion de plan de SimpliRoute que fallo al guardar, diagnostica cual de los problemas conocidos es, aplica la correccion (capacidad de vehiculo, o plan duplicado) y opcionalmente reenvia el request.

## Cuando usar
- El usuario pega o referencia un archivo `.txt`/`.json` con un request de `create-plan` o `edit-plan` que SimpliRoute rechazo al guardar.
- Puede venir como curl completo ("Copy as cURL") o como un pegado suelto de headers + body (sin `curl` ni URL) — ver paso 1.

## Paso 1 — Extraer datos del archivo
El archivo puede pesar cientos de KB — no usar Read directo del archivo completo, usar un script Python/regex vía Bash.

**Formato curl** (`curl 'url' -H '...' --data(-raw) '...' --compressed`):
- Token: `-H 'authorization: Token ([a-f0-9]+)'` (case-insensitive).
- URL: primer argumento de `curl '...'`.
- Payload: `--data(?:-raw)?\s+'(.*)'\s*(?:--compressed\s*)?$` con `re.DOTALL`, luego reemplazar `'\''` por `'` (asi escapa bash las comillas simples internas).
- Ojo: el curl casi siempre termina en `--compressed` (u otras flags) despues del `--data`, el regex no puede anclar solo a `'$` o falla.

**Formato headers+body pegado** (sin `curl`, luego lineas en blanco y el JSON crudo). Los headers de la primera linea pueden venir de dos formas:
- Como texto separado por coma, a veces con basura tipo `[object Object]`: buscar `Authorization: Token ([a-f0-9]+)` con regex en cualquier parte del texto.
- Como JSON valido (`{"accept":"...","authorization":"Token ...","content-type":"...","x-source-detail":"apollo-web"}`): parsear esa primera linea con `json.loads` y leer la key `authorization`.
- Body: desde el primer `{` **despues de la primera linea** hasta el final (`texto[texto.find("{", len(primera_linea)):].strip()`) — si los headers ya vinieron en JSON, no buscar el primer `{` del archivo completo o va a matchear el de los headers.
- **No suele incluir la URL ni el metodo.** Si el usuario no lo aclara, preguntar que endpoint era (create-plan vs edit-plan vs update) antes de reenviar nada — no asumir. Si el usuario confirma "se mando como create" y el plan no existe aun (ver Problema B), usar `POST https://api.simpliroute.com/v1/plans/create-plan/`.

**Entorno**: las llamadas HTTPS desde Python en esta maquina pueden fallar con `CERTIFICATE_VERIFY_FAILED` (inspeccion TLS corporativa). Si pasa, agregar al inicio del script `import truststore; truststore.inject_into_ssl()` y correr el Bash con `dangerouslyDisableSandbox: true`.

**Headers**: no asumir que solo importan `Authorization` y `Content-Type`. Extraer TODOS los headers `-H` del curl (`re.findall(r"-H\s+'([^:]+):\s*(.*?)'", texto)`) y reenviarlos igual en cualquier request (GET/DELETE/POST) contra esa cuenta. Algunas cuentas usan headers adicionales como `Related-Account` (sub-cuentas relacionadas) que son necesarios para que el request opere sobre la cuenta correcta.

## Paso 2 — Diagnosticar cual problema es
Los problemas conocidos (ver casos abajo) no son excluyentes, revisar ambos:

### Problema A: porcentaje de carga fuera de rango (smallint overflow)
- SimpliRoute calcula `total_load_percentage`, `total_load_2_percentage`, `total_load_3_percentage` por ruta como `round(carga_asignada / capacidad_vehiculo * 100)`.
- Si la capacidad del vehiculo esta mal configurada (0, 1, o muy baja) el porcentaje se dispara y supera `MAX_SMALLINT_FIELD = 32767` (config.py), el limite de un campo smallint en el backend, lo que bloquea el guardado del plan (error claro, mencionando el campo).
- La herramienta equivalente en la app es `validador_plan.py` ("Validador de Plan"): ahi el usuario sube el JSON manualmente y la app cruza contra la API de vehiculos.
- Deteccion: parsear el JSON, iterar `routes[]`, revisar los tres campos de porcentaje contra `MAX_SMALLINT_FIELD`. Para cada ruta con problema, `GET /v1/routes/vehicles/` (con el token del request) y buscar el vehiculo por el `vehicle` id de la ruta — **el campo `vehicle` de la ruta puede venir como string mientras el `id` de la API es int; normalizar tipo (`str(...)`) antes de comparar o el match falla en falso "no encontrado".**
- Capacidad sugerida = `ceil(carga_asignada * 1.2)` (20% de holgura); nunca bajar la capacidad si la configurada ya es mayor.
- Correccion: `PUT /v1/routes/vehicles/{id}/` con el objeto completo del vehiculo (`dict(vehiculo) | {campo_capacidad: nuevo_valor}`) — la API espera el objeto entero, no solo el campo cambiado. Luego recalcular `total_load_X_percentage = round(carga / capacidad_nueva * 100)` en el JSON del plan.

### Problema B: create-plan con un `id` de plan que ya existe → 500 generico
- Sintoma: la respuesta es un **HTML de error 500** sin mensaje util (`Server Error (500)`), no un 400 con detalle. El JSON del request no tiene ningun campo fuera de rango (revisar con Problema A primero para descartarlo).
- Causa: el body tiene un `id` de plan a nivel raiz que **ya existe** en la cuenta (el plan ya fue creado/guardado antes, a veces con `status: "completed"`). Al reenviar `create-plan` con ese mismo `id`, el backend choca contra la restriccion de unicidad y explota sin manejar el error.
- Confirmar la hipotesis: `GET /v1/routes/plans/{id}/` con el token del request — si devuelve 200 con datos, el plan ya existe.
- Es normal en este payload que las **visitas ya tengan `id` real** (son visitas existentes) pero las **rutas tengan `id: null`** (son rutas nuevas para re-rutear esas visitas) — eso no es el problema, es la forma esperada de un `create-plan` que reutiliza visitas.
- **Antes de corregir, preguntar la intencion al usuario** (no asumir): ¿reemplazar el plan existente (borrarlo y crear el nuevo con la ultima edicion) o dejarlo intacto y crear uno aparte? Son acciones con consecuencias distintas sobre datos reales.
- Correccion cuando la intencion es "que quede la ultima edicion" (reemplazar):
  1. Confirmar con el usuario antes de borrar — es una accion destructiva sobre datos reales.
  2. `DELETE /v1/routes/plans/{id}/` sobre el plan viejo.
  3. En el JSON del request, **eliminar el campo `id` de nivel raiz del plan** (asi el backend genera uno nuevo al crear).
  4. Reenviar como `create-plan` con el JSON editado.
  5. Verificar: la respuesta trae un `id` nuevo (distinto al borrado) y la cantidad de rutas coincide con las del request.

### Problema C: coordenada con mas de 9 digitos totales → error de validacion claro
- Sintoma: la respuesta es un JSON de error legible (no un 500), del tipo `{"latitude":["Asegúrese de que no haya más de 9 dígitos en total."]}` (o el mismo mensaje para `longitude`). Este es el caso mas facil de diagnosticar porque el error ya dice el campo.
- Causa: algun campo `latitude`/`longitude` en el payload tiene mas decimales de lo normal (el resto del plan usa 6 decimales; el campo problematico traia 7-8), y el total de digitos (parte entera + decimales, sin contar el signo ni el punto) supera 9.
- El campo no siempre esta en una visita o en `location_start/end_latitude` de la ruta — tambien puede estar en `routes[].events[]` (eventos tipo `rest_time` con su propio `latitude`/`longitude`), que es facil de pasar por alto.
- Deteccion: recorrer todo el JSON recursivamente buscando keys que contengan `latitude`/`longitude`, contar solo los digitos del valor (`len(re.sub(r"[^0-9]", "", str(valor)))`) y marcar los que superen 9.
- Correccion: redondear el valor a 6 decimales (`round(valor, 6)`), igual que el resto de coordenadas del plan.

## Paso 3 — Reconstruir el archivo corregido
- Si el archivo original era curl: mismo prefijo (`curl 'url' -H ... --data(-raw) '`) + JSON corregido (compacto, `json.dumps(..., separators=(',',':'))`, igual de formato que el original) + comillas simples escapadas (`'` -> `'\''`) + sufijo original (ej. `--compressed`).
- Guardar el resultado en un archivo **nuevo** (no sobreescribir el original del usuario) — ej. `plan_corregido.txt` junto al original.
- Verificar el roundtrip: volver a extraer el JSON del archivo reconstruido y confirmar que parsea y que el campo quedo corregido.

## Paso 4 — Ejecutar
- Ejecutar (POST/DELETE reales) **solo si el usuario lo pide explicitamente** ("ejecutalo", "mandalo", "borralo", etc.) — modifica datos reales de la cuenta.
- Reportar resultado: status code, `plan id`, cantidad de rutas, y cualquier error del response.

## Casos resueltos (ir agregando)
- 2026-08-18 — Problema A: vehiculo con `capacity_3 = 1`, carga asignada 452 → `total_load_3_percentage = 45200` (>32767). Se corrigio `capacity_3` a 543 (452*1.2 redondeado arriba) y el porcentaje recalculado quedo en 83. Plan creado con `POST /v1/plans/create-plan/`, 21 rutas, HTTP 200.
- 2026-08-19 — Problema A: el campo `vehicle` de la ruta viene como **string** (`"728268"`), pero `GET /v1/routes/vehicles/` devuelve `id` como **int** — sin normalizar tipo el match falla. Caso: `capacity = 7.5`, carga 3414.28 → `total_load_percentage = 45524`. Se corrigio `capacity` a 4098, porcentaje recalculado quedo en 83. Plan creado, 23 rutas, HTTP 200.
- 2026-08-20 — Problema B: archivo pegado sin formato curl (headers sueltos + body, sin URL). Plan `ec5d5b45-89ec-4c4b-a275-aefe9abd3109` ya existia (status `completed`, 31 rutas, 861 visitas con id real) y se reenvio `create-plan` con el mismo `id` → 500 HTML generico. Confirmado con `GET /v1/routes/plans/{id}/`. Resolucion acordada: borrar el plan viejo, quitar el `id` del JSON, reenviar create-plan para que quede la ultima edicion.
- 2026-08-24 — Problema C: headers en formato JSON (`{"accept":...,"authorization":"Token ...",...}`) + body. Evento `rest_time` en `routes[1].events[0]` con `latitude: 19.21553425` (8 decimales, 10 digitos totales) → error `{"latitude":["Asegúrese de que no haya más de 9 dígitos en total."]}`. Se redondeo a `19.215534` (6 decimales) y se reenvio create-plan, plan creado con el mismo id (no existia previamente), 2 rutas, HTTP 200. Tambien: en esta maquina las llamadas requests fallaron con `CERTIFICATE_VERIFY_FAILED` hasta agregar `truststore.inject_into_ssl()` + `dangerouslyDisableSandbox: true`.
