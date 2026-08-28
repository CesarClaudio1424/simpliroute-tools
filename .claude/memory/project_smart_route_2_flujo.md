---
name: smart-route-2-asignacion-post-ruteo
description: Smart Route 2 (Unilever) migra a asignacion de vehiculos DESPUES del ruteo libre; maestro y Excel de planeacion quedan como legacy
metadata: 
  node_type: memory
  type: project
  originSessionId: 2c1a3bc8-d9fb-41ac-8245-2fbb502e0fdc
---

Decision de diseño (2026-06-12, tab "Asignar vehículos al plan" en `asignacion_fija_uni_2.py`): en vez de forzar ruta fija con habilidades antes del ruteo, se rutea libre en Simpli (vehiculos genericos) y despues se asigna vehiculo/conductor por % de match (greedy 1:1) contra `smart_route_planeacion.habilidad_1`.

**Why:** el manejo de archivos (planeacion, maestro, salidas A/B, habilidades) volvia la operacion muy compleja; el plan creado en Simpli ya trae ventanas, tiempos, coords y clientes nuevos correctos.

**How to apply:**
- El cliente de cada visita viaja en el campo `notes` (confirmado por Cesar; no usar `reference`, que es el pedido).
- Rutas con vehiculo especial (1001FM/1001EV) o ya fijo no se tocan; unidades homologadas en capacidad (swap seguro).
- Las especiales se asignan en Simpli via RUTA FIJA (no habilidades): antes de rutear hay que importar el archivo de ruta fija con sus clientes. La pagina lo genera (solo Monterrey, expander antes de la fecha) desde el Monitoreo hoja BD col H, con ventanas/coords historicas de smart_maestro_clientes + smart_route_planeacion.
- `smart_route_planeacion` sobrevive solo como memoria de habilidades y se auto-mantiene con el boton "Actualizar habilidades desde el plan" (upsert crea clientes nuevos solo). Ya NO se sube el Excel de planeacion.
- 2026-06-12: la pagina quedo reducida a UNA sola funcion (Asignar vehiculos al plan + feedback); se borraron de `asignacion_fija_uni_2.py` los tabs de planeacion, maestro, generar archivos (incluido el modo ruteo libre) y actualizar datos Simpli. Las visitas nacen en Simpli con datos correctos (incluso clientes nuevos); solo se asigna vehiculo+conductor via PUT de ruta con objeto completo. El respaldo del proceso viejo es `asignacion_fija_uni.py` (v1).
- El pool de match se declara igual que en el flujo viejo: listado de vehiculos activos en Tlahuac, numero de rutas (primeras N de RUTAS_MONTERREY) en Monterrey; se intersecta con la flota de la API.
