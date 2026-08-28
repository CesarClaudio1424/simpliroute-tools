---
name: simpliroute-trailing-slash
description: Detalles de trailing slash en endpoints individuales de SimpliRoute API (PUT/GET por ID)
metadata: 
  node_type: memory
  type: reference
  originSessionId: 453e4f8f-3250-4369-a635-1bdb54a9faff
---

PUT y GET a recursos individuales de SimpliRoute por ID **requieren trailing slash final**, sin el cual la API ignora el body de la request y reporta campos requeridos como faltantes (HTTP 400 con `title required`, `address required`, etc).

**Why:** Caso real en `recuperar_lvp.py` con `PUT /v1/routes/visits/{id}` — sin slash devolvia 400 sobre title/address aunque el body los incluia. Agregar `/` al final resolvio el problema. DRF tipicamente fuerza redireccion al endpoint con slash, pero al hacerlo en metodos no-GET el body se pierde.

**How to apply:** Cuando se construya cualquier URL contra `api.simpliroute.com` que termine en `{id}` (PUT, PATCH, DELETE individual), siempre agregar `/` final. Para endpoints colectivos (`/routes/visits/`, `/routes/plans/`) el slash ya esta presente. El unico endpoint individual en este codebase que NO usa slash es `DELETE /v1/zones/{id}` ([[zonas_kml]]) — confirmado que funciona sin el.
