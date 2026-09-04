---
name: reference-simpliroute-events-register-quirks
description: Comportamientos no obvios de POST /v1/events/register/ (ROUTE_STARTED/ROUTE_FINISHED) descubiertos al reparar una ruta con fin sin inicio
metadata:
  type: reference
---

Al usar `POST https://api-mobile.simpliroute.com/v1/events/register/` (la herramienta **Eventos de Ruta**, `eventos_ruta.py`) para reparar rutas con datos inconsistentes, dos comportamientos a tener en cuenta:

1. **Registrar `ROUTE_STARTED` en una ruta que ya estaba `finished` resetea el `status` a `started`**, aunque el `end_time` existente no se borra. Si el objetivo es solo rellenar un `start_time` faltante, hay que reenviar despues un `ROUTE_FINISHED` para devolver el status a `finished`.

2. **Reenviar `ROUTE_FINISHED` con el `date_time` EXACTAMENTE igual al `end_time` que la ruta ya tenia es tratado como evento duplicado**: la API responde HTTP 200 pero con body literal `"200"` (content-length 3, no el JSON normal) y el `status` NO transiciona a `finished`. Hay que reenviar el evento con el `date_time` desplazado al menos ~1 segundo respecto al valor existente — ahi si responde `{"data":"Event registered."}` (content-length 28) y el status pasa a `finished` correctamente.

**Como aplicar:** al detectar una ruta con `end_time` presente pero `start_time` nulo (fin sin inicio), el flujo seguro es: (a) POST ROUTE_STARTED con la hora de inicio deseada, (b) verificar que el status quedo en `started`, (c) POST ROUTE_FINISHED con el `end_time` original +1 segundo (no el valor exacto) para forzar la transicion de vuelta a `finished`, (d) verificar status final. Ver tambien [[reference_simpliroute_trailing_slash]] para otras rarezas de la API de SimpliRoute.
