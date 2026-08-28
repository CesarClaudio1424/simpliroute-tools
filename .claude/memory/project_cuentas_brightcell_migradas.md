---
name: cuentas-brightcell-migradas
description: "Las 4 cuentas \"Likewise\" en produccion fueron renombradas/migradas a marca Brightcell"
metadata: 
  node_type: memory
  type: project
  originSessionId: 7c7f850b-6188-44c6-b8f4-b31e892f38c7
  modified: 2026-08-19T22:41:07.792Z
---

Las cuentas de produccion que en el codigo (`webhook.py`, tool "Webhooks Likewise") se identifican como Likewise ahora se llaman **Brightcell** en produccion, mismos `account_id`:

- Brightcell TELEFONICA — account_id 15289
- Brightcell DELIVERY OMNICANALIDAD — account_id 32597
- Brightcell BIOBIO — account_id 70696
- Brightcell ENTEL — account_id 28920

**Why:** el usuario informo la migracion de marca (2026-08-19) al revisar `envio.txt` (Postman collection "Brightcell — Reproceso manual", endpoint `POST {{base_url}}/brightcell/reprocess` con acciones route_started, create_plan, route_checkout, visit_checkout, exclude_visits — usado para reprocesar manualmente cuando un webhook nativo fallo; reconsulta estado en Icarus y reejecuta la logica de negocio).

**How to apply:** el flujo operativo para reenviar Creacion/Inicio/Checkout de una ruta sigue siendo el mismo documentado en CLAUDE.md (`enviar_route_webhook` / `procesar_checkout` en `webhook.py`, endpoints nativos SimpliRoute `send-route-webhooks`/`send-webhooks`) — la migracion es de nombre de cuenta/marca, no de mecanismo de webhook. El endpoint `brightcell/reprocess` de `envio.txt` es una via alterna de soporte (para cuando el webhook normal fallo), no reemplaza el flujo principal de la app. No hay URL de produccion confirmada para ese endpoint (el collection solo trae localhost/QA).
