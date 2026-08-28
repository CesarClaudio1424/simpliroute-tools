---
name: reference-simpliroute-reference-case-sensitive
description: "El endpoint GET /v1/routes/visits/reference/{ref}/ de SimpliRoute es sensible a mayusculas/minusculas"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 578268cc-3dcf-4c20-9100-b29f2d4c8621
  modified: 2026-08-16T23:09:32.761Z
---

El endpoint `GET /v1/routes/visits/reference/{ref}/` distingue mayusculas de minusculas. Un reference guardado en SimpliRoute como `P029213728` NO se encuentra si se busca como `p029213728` (devuelve resultados vacios, no error).

**Como aplicar:** al buscar references provenientes de un archivo externo (Excel/CSV de otra cuenta o sistema, ej. Liverpool), si una busqueda inicial da muchos "no encontrados", reintentar siempre con el reference en mayusculas (`.upper()`) antes de concluir que no existen. En una prueba con 7278 references de Liverpool Tacubaya PQ, 5303 dieron "no encontrado" en minusculas pero 5234 de esos SI existian al buscarlos en mayusculas — solo 62 eran realmente inexistentes.

Ver tambien [[reference_simpliroute_trailing_slash]] (el mismo endpoint requiere el `/` final).
