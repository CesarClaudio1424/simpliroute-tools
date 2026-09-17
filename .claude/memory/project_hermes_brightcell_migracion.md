---
name: project-hermes-brightcell-migracion
description: El middleware Likewise viejo fue retirado por Brandon; Exclusiones ahora usa el gateway Hermes/Brightcell
metadata: 
  node_type: memory
  type: project
  originSessionId: ffe1357c-f851-40a2-8992-d9191bd57609
  modified: 2026-09-16T01:30:29.212Z
---

El equipo de Brandon retiro por completo el middleware Likewise viejo (`us-central1-likewizemiddleware-{telefonica,omni,biobio,entel}.cloudfunctions.net`) el 2026-09-03 (`refactor(brightcell): retire Likewise runtime path`), reemplazandolo por un gateway nuevo llamado **Hermes**: `POST https://connect.simpliroute.com/brightcell/reprocess`, auth `Authorization: ApiKey <clave-por-cuenta>` (una clave JWT distinta por cuenta: Telefonica/Entel/Omnicanalidad/Biobio).

**Por que importa:** nuestra herramienta "Webhooks Likewise" era la unica parte de nuestro stack que todavia dependia del middleware viejo (las Exclusiones). Si esa infraestructura compartida se apaga, dejariamos de poder excluir visitas sin aviso. Ya migramos esto — ver commit `c4a9c49` en pruebas.

**Mecanismo Hermes (distinto al middleware viejo):**
- El "ID" que pega el usuario debe **resolverse primero** contra SimpliRoute (`GET /v1/routes/visits/reference/{reference}/`) para obtener el ID interno real — Hermes exige el ID resuelto, no el reference crudo que aceptaba el middleware viejo directamente.
- Payload Hermes: `{"action": "exclude_visits", "ids": [<IDs SimpliRoute, enteros>]}`. Respuesta: `{"results": [{"id", "status": "ok"|"error", "error"?, "visits_reprocessed"?}]}`.
- La limpieza opcional en SimpliRoute (quitar ruta + `planned_date=2020-01-01`) usa `PATCH /v1/routes/visits/` (payload minimo, sin title/address) y **solo debe aplicarse a los IDs que Hermes confirmo** (`status: "ok"`), nunca a todo lo solicitado a ciegas — ya no hace falta buscar por rango de fechas, se sabe el ID exacto desde la resolucion.
- Claves Hermes guardadas en secrets `[brightcell_hermes]` (telefonica/entel/omnicanalidad/biobio) — recibidas directo del usuario en el chat 2026-09-03, no las pidas de nuevo salvo rotacion.

**Como aplicar:**
- Implementado en `webhook.py` (`resolver_visita_por_reference`, `excluir_visitas_hermes`, `limpiar_visitas_hermes`, `procesar_exclusion_hermes`) y `pagina_webhooks.py`. Subido a pruebas (commit c4a9c49). Portado tambien al backend del droplet (`webhooks_likewise.py`, ver [[project_migracion_droplet_personal]]).
- Si el usuario reporta que "Procesar webhooks" con Exclusiones falla, revisar primero si la clave Hermes de esa cuenta especifica esta bien copiada en secrets, y si el reference realmente existe en esa cuenta (sino cae en "sin_resolver").
- Ver tambien [[project_migracion_nextjs_brandon]] para el contexto general de la migracion de Brandon.

**Exclusiones (`exclude_visits`) roto del lado de Hermes (reportado por Cesar, 2026-09-16):** al probarlo, Hermes devuelve una alerta indicando que no se puede eliminar/excluir por **falta de endpoint** — no es un bug de nuestro codigo (la doc de Notion, el payload y el auth ya estan confirmados correctos, ver la comparacion hecha en [[project_migracion_droplet_personal]]). Es un problema del lado del equipo de Hermes/Brightcell, pendiente de que ellos lo reparen. **No asumir que Exclusiones funciona hasta que Cesar confirme que el equipo de Hermes arreglo el endpoint** — reintentar la prueba periodicamente no tiene sentido, es un problema externo, no de reintentos.

**Fallback agregado (2026-09-16):** a pedido de Cesar, la limpieza en SimpliRoute ("Tambien eliminar visitas de SimpliRoute") ya NO depende de que Hermes confirme la exclusion. `procesar_exclusion_hermes` ahora tambien devuelve `resueltos` (todos los IDs que se lograron resolver por reference, haya o no confirmado Hermes); si `confirmados` viene vacio, el frontend limpia igual usando `resueltos`. Se agrego un aviso visible en la pagina (⚠️ endpoint de Hermes reportado como faltante) y una nota aclarando que la limpieza se aplico via fallback cuando corresponde. Deploy hecho y verificado (backend + frontend).

**Correccion importante (2026-09-17):** la entrada anterior decia que "Creacion/Inicio/Checkout ya se probaron en vivo y funcionan bien" via el webhook nativo de SimpliRoute (`route_created`/`route_started`/`send-webhooks`) — **eso quedo superado**. Cesar paso 3 curls reales confirmando que esas 3 acciones **tambien** van por Hermes, con sus propios `action`: `create_plan` (Creacion), `route_started` (Inicio), `route_checkout` (Checkout) — mismo endpoint/auth que `exclude_visits`, un POST por ruta con `{"action", "ids": [route_id]}`. Ya no se usa el webhook nativo para nada de esta herramienta. Implementado en `webhook.py`/`pagina_webhooks.py` (funcion nueva `accion_ruta_hermes`, reemplaza a `enviar_route_webhook`/`procesar_checkout`/`obtener_planned_date`, que se eliminaron) y en `webhooks_likewise.py`/`main.py`/`WebhooksLikewise.tsx` del droplet (endpoint unificado `/api/webhooks-likewise/route-action`, reemplaza a `/route-webhook` + `/checkout`). Checkout ya no necesita el `GET planned_date` previo ni `account_id` (Hermes `route_checkout` solo pide el route_id). Pendiente que Cesar pruebe en vivo con una ruta real (no se ejecuto ningun curl real de verificacion, ver [[feedback_diagnostico_en_endpoints_de_escritura]]).
