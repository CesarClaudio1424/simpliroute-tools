---
name: reference_simpliroute_visit_types_key_normalizado
description: POST /v1/accounts/visit-types/ elimina guiones del key enviado
metadata: 
  node_type: memory
  type: reference
  originSessionId: 3684e564-11f1-4bd8-8e06-3d13b33f050b
  modified: 2026-09-18T19:12:47.042Z
---

`POST /v1/accounts/visit-types/` (`{"label": "...", "key": "..."}`) normaliza el `key` server-side quitando guiones (`-`), aunque el label los conserve. Ejemplo real: envie `key: "aass-noche"` con `label: "AASS-NOCHE"` y la API guardo `key: "aassnoche"`.

**Como aplicar:** al crear visit types en bulk, no asumir que el `key` de la respuesta es igual al enviado si tiene guiones — leer siempre el `key` real de la respuesta (incluye `id` ademas de `label`/`key`/`category`) antes de usarlo en otro lugar (ej. asignar `visit_type` a una visita via PUT, ver [[reference_simpliroute_visit_put_quirks]]). Endpoint confirmado con GET/POST en cuenta Los Olivos AJE Peru (account_id 102552, PE).
