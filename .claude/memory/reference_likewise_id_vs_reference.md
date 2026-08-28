---
name: reference-likewise-id-vs-reference
description: "En el flujo Likewise (webhooks exclusion y limpieza SR), lo que el usuario llama \"ID de visita\" es en realidad el campo `reference` en SimpliRoute, no el `id` interno"
metadata: 
  node_type: memory
  type: reference
  originSessionId: c7e9684e-d410-4038-9613-43560766e1c9
---

En las cuentas Likewise (Telefonica/Entel/Omnicanalidad/Biobio), el numero que el usuario pega en la herramienta "Webhooks Likewise → Exclusiones" (ej. `21910923`) NO es el `id` interno de SimpliRoute, es el campo `reference`.

- Para el usuario y para Likewise, ese numero es el "ID de la visita".
- En SimpliRoute vive en `reference`.
- El webhook de exclusion lo manda como `{"visits": [int(x), ...]}` — Likewise lo resuelve internamente.
- La limpieza posterior en SimpliRoute (`GET /v1/routes/visits/?planned_date=...` + `PUT`) debe matchear por `v.get("reference")`, no por `v.get("id")`.

**Por que importa:** si cambias el matching a `id` la limpieza nunca encuentra nada porque los `id` internos son distintos a los numeros que pega el usuario.

**Como aplicar:** en cualquier feature que mezcle webhooks Likewise + API SimpliRoute, asumir que los numeros que el usuario maneja son references desde el punto de vista de SimpliRoute. Si una busqueda no encuentra nada, sospechar de fecha incorrecta antes que de mismatch de campo.
