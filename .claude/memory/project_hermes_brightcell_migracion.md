---
name: project-hermes-brightcell-migracion
description: El middleware Likewise viejo fue retirado por Brandon; Exclusiones ahora usa el gateway Hermes/Brightcell
metadata:
  type: project
---

El equipo de Brandon retiro por completo el middleware Likewise viejo (`us-central1-likewizemiddleware-{telefonica,omni,biobio,entel}.cloudfunctions.net`) el 2026-09-03 (`refactor(brightcell): retire Likewise runtime path`), reemplazandolo por un gateway nuevo llamado **Hermes**: `POST https://connect.simpliroute.com/brightcell/reprocess`, auth `Authorization: ApiKey <clave-por-cuenta>` (una clave JWT distinta por cuenta: Telefonica/Entel/Omnicanalidad/Biobio).

**Por que importa:** nuestra herramienta "Webhooks Likewise" era la unica parte de nuestro stack que todavia dependia del middleware viejo (las Exclusiones). Si esa infraestructura compartida se apaga, dejariamos de poder excluir visitas sin aviso. Ya migramos esto — ver commit `c4a9c49` en pruebas.

**Mecanismo Hermes (distinto al middleware viejo):**
- El "ID" que pega el usuario debe **resolverse primero** contra SimpliRoute (`GET /v1/routes/visits/reference/{reference}/`) para obtener el ID interno real — Hermes exige el ID resuelto, no el reference crudo que aceptaba el middleware viejo directamente.
- Payload Hermes: `{"action": "exclude_visits", "ids": [<IDs SimpliRoute, enteros>]}`. Respuesta: `{"results": [{"id", "status": "ok"|"error", "error"?, "visits_reprocessed"?}]}`.
- La limpieza opcional en SimpliRoute (quitar ruta + `planned_date=2020-01-01`) usa `PATCH /v1/routes/visits/` (payload minimo, sin title/address) y **solo debe aplicarse a los IDs que Hermes confirmo** (`status: "ok"`), nunca a todo lo solicitado a ciegas — ya no hace falta buscar por rango de fechas, se sabe el ID exacto desde la resolucion.
- Claves Hermes guardadas en secrets `[brightcell_hermes]` (telefonica/entel/omnicanalidad/biobio) — recibidas directo del usuario en el chat 2026-09-03, no las pidas de nuevo salvo rotacion.

**Como aplicar:**
- Implementado en `webhook.py` (`resolver_visita_por_reference`, `excluir_visitas_hermes`, `limpiar_visitas_hermes`, `procesar_exclusion_hermes`) y `pagina_webhooks.py`. Subido a pruebas (commit c4a9c49), **sin probar en vivo** — el usuario dijo que lo prueba el mismo con un reference real antes de confiar en el flujo (toca cuentas reales de produccion: Telefonica/Entel/Omnicanalidad/Biobio).
- Si el usuario reporta que "Procesar webhooks" con Exclusiones falla, revisar primero si la clave Hermes de esa cuenta especifica esta bien copiada en secrets, y si el reference realmente existe en esa cuenta (sino cae en "sin_resolver").
- Ver tambien [[project_migracion_nextjs_brandon]] para el contexto general de la migracion de Brandon.
