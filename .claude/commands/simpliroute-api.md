# SimpliRoute API - Referencia completa

Usa esta documentacion como referencia al trabajar con la API de SimpliRoute. Consulta los endpoints, parametros, modelos de datos y ejemplos segun lo que necesite el usuario.

---

## Informacion General

- **Base URL principal:** `https://api.simpliroute.com/v1/`
- **Base URL mobile:** `https://api-mobile.simpliroute.com/v1/`
- **Base URL tracking:** `https://api-track.simpliroute.com/v1/`
- **Base URL gateway:** `https://api-gateway.simpliroute.com/v1/`
- **Optimizador:** `https://optimizator.simpliroute.com/`
- **OSRM:** `https://osrm.simpliroute.com/`
- **Geocoder:** `https://us-central1-geocoding-265816.cloudfunctions.net/geocoder_prod`
- **Formato:** JSON
- **CORS:** Habilitado
- **Auth:** `Authorization: Token {API_TOKEN}`
- **Obtener token:** https://app2.simpliroute.com/#/uprofile/info

### Headers requeridos
```
Authorization: Token {API_TOKEN}
Content-Type: application/json
```

### Formato de fechas
- Fecha: `YYYY-MM-DD`
- Hora: `HH:mm:ss`
- Timestamp: ISO 8601 (`2024-01-15T14:30:00Z`)

### Codigos HTTP
| Codigo | Significado |
|--------|------------|
| 200 | OK |
| 201 | Created |
| 204 | No Content (DELETE exitoso) |
| 400 | Bad Request |
| 401 | Unauthorized |
| 404 | Not Found |
| 409 | Conflict |
| 500 | Internal Server Error |

---

## 1. CUENTAS (Accounts)

### 1.1 Registro
- **POST** `/v1/accounts/register/`
```json
{"username":"abcadmin","email":"admin@abc.com","name":"ABC Admin","password":"admin","account":{"name":"Account ABC","country":"CL"}}
```

### 1.2 Leer usuario actual
- **GET** `/v1/accounts/me`

### 1.3 Actualizar usuario
- **PUT** `/v1/accounts/users/{user_id}/`
```json
{"username":"user1","name":"Nombre","phone":"+56","is_owner":false,"is_admin":false,"is_driver":false,"is_codriver":false,"is_router_jr":false,"is_monitor":true,"is_coordinator":false,"is_router":false,"is_staff":false,"old_id":null}
```

### 1.4 Actualizar cuenta
- **PUT** `/v1/accounts/account/`
```json
{"name":"ACME Inc.","country":"CL"}
```

### 1.5 Validar token API
- **GET** `/v1/accounts/api-token/{token}/validate/`

### 1.6 Verificar si usuario existe
- **GET** `/v1/accounts/user-exist/?username={username}`

### 1.7 Version mobile
- **PUT** `/v1/accounts/mobile-version/`
```json
{"app_version":"1.0.0"}
```

### 1.8 Configuracion de cuenta
- **POST** `/v1/accounts/{account_id}/configs/`
```json
{"key":"geocoder_provider","value":"google"}
```
Keys conocidas: `disable_edit_for_active_and_finished_routes`, `enable_safety_mode`, `avoid_edit_checkout_after_route_finished`, `geocoder_provider`

---

## 2. ADMINS

| Operacion | Metodo | Endpoint |
|-----------|--------|----------|
| Listar | GET | `/v1/accounts/admins/` |
| Crear | POST | `/v1/accounts/admins/` |
| Leer | GET | `/v1/accounts/admins/{id}/` |
| Actualizar | PUT | `/v1/accounts/admins/{id}/` |
| Eliminar | DELETE | `/v1/accounts/admins/{id}/` |

```json
{"username":"admin2","name":"Admin 2","phone":"","email":"","is_admin":true,"password":"admin"}
```

---

## 3. USUARIOS / CONDUCTORES (Users/Drivers)

| Operacion | Metodo | Endpoint |
|-----------|--------|----------|
| Listar usuarios | GET | `/v1/accounts/users/` |
| Listar conductores | GET | `/v1/accounts/drivers/` |
| Crear usuario | POST | `/v1/accounts/users/` |
| Leer usuario | GET | `/v1/accounts/users/{id}/` |
| Actualizar usuario | PUT | `/v1/accounts/users/{id}/` |
| Actualizar conductor | PUT | `/v1/accounts/drivers/` |
| Eliminar conductor | DELETE | `/v1/accounts/drivers/{id}/` |
| Soft-delete usuario | PUT | `/v1/accounts/users/{id}/` con `"status":"deleted"` |

**Roles disponibles (boolean):** `is_owner`, `is_admin`, `is_driver`, `is_codriver`, `is_router_jr`, `is_monitor`, `is_coordinator`, `is_router`, `is_staff`

**Crear usuario:**
```json
{"username":"driver4","name":"Driver 4","phone":"+56967258465","email":"user@mail.com","is_admin":false,"password":"driver","is_driver":true}
```

---

## 4. AUTENTICACION

### 4.1 Resetear password
- **POST** `/v1/auth/password/reset/`
```json
{"email":"user@example.com"}
```

### 4.2 Confirmar reset
- **POST** `/v1/auth/password/reset/confirm/`
```json
{"uid":"MQ","token":"49o-5831cd4014d838467a3f","new_password":"user"}
```

---

## 5. VISITAS (Visits)

### 5.1 Crear Visita(s)
- **POST** `/v1/routes/visits/`
- Acepta un objeto (1 visita) o array (multiples)

**Parametros requeridos:**
| Parametro | Tipo | Descripcion |
|-----------|------|-------------|
| title | string | Nombre/identificador de la entrega |
| address | string | Direccion en formato Google Maps |
| planned_date | date (YYYY-MM-DD) | Fecha de entrega planificada |

**Parametros opcionales:**
| Parametro | Tipo | Descripcion |
|-----------|------|-------------|
| latitude | float | Latitud del destino |
| longitude | float | Longitud del destino |
| load | double | Carga 1 |
| load_2 | double | Carga 2 |
| load_3 | double | Carga 3 |
| window_start | time (HH:mm:ss) | Inicio ventana de tiempo |
| window_end | time (HH:mm:ss) | Fin ventana de tiempo |
| window_start_2 | time | Inicio ventana alternativa |
| window_end_2 | time | Fin ventana alternativa |
| duration | time (HH:mm:ss) | Tiempo de servicio |
| contact_name | string | Nombre del receptor |
| contact_phone | string | Telefono del receptor |
| contact_email | string | Email del receptor |
| reference | string | ID interno / numero de orden |
| notes | string | Notas para el conductor |
| skills_required | array(int) | IDs de habilidades requeridas |
| skills_optional | array(int) | IDs de habilidades opcionales |
| tags | array(int) | IDs de etiquetas |
| priority_level | int | Nivel de prioridad (1-5) |
| items | array(object) | Articulos a entregar |

```json
[{"title":"Entrega 1","address":"Av. Principal 123","load":39,"load_2":100,"window_start":"09:00:00","window_end":"18:00:00","duration":"00:10:00","contact_name":"Juan Perez","reference":"REF001","planned_date":"2024-06-30","items":[{"title":"Producto A","load":15,"load_3":0.5,"reference":"SKU001","quantity_planned":1}]}]
```

### 5.2 Obtener Visita por ID
- **GET** `/v1/routes/visits/{visit_id}`

### 5.3 Obtener Visitas por Fecha
- **GET** `/v1/routes/visits/?planned_date={YYYY-MM-DD}`

### 5.4 Obtener Visitas por Ruta
- **GET** `/v1/routes/visits/?route={route_uuid}`

### 5.5 Buscar por Reference
- **GET** `/v1/routes/visits/reference/{reference}/`
- Respuesta paginada: `{count, results: [...]}`

### 5.6 Visitas Paginadas con Filtros
- **GET** `/v1/routes/visits/paginated/?page=1&page_size=500&planned_date=YYYY-MM-DD&status=pending&visit_types=27513`

### 5.7 Informacion Detallada
- **GET** `/v1/plans/visits/{visit_id}/detail`
- Incluye: checkout_comment, pictures, vehicle_name, driver_name, order

### 5.8 Historial de Visita
- **GET** `/v1/routes/visits/{visit_id}/history/`
- Con filtro checkout: `?checkout=` (solo con checkout_time no null)

### 5.9 Actualizar Visita Individual
- **PUT** `/v1/routes/visits/{visit_id}`

### 5.10 Actualizar Visitas en Bulk
- **PUT** `/v1/routes/visits/`
```json
[{"id":"431037684","address":"Av. Larrain 5862","title":"Visita 1","load_3":"9900"}]
```

### 5.11 Actualizar Parcial (PATCH)
- **PATCH** `/v1/routes/visits/`
```json
[{"id":149774255,"route_id":null,"planned_date":null},{"id":149774252,"route_id":null,"planned_date":null}]
```

### 5.12 Eliminar Visita
- **DELETE** `/v1/routes/visits/{visit_id}/`

### 5.13 Eliminar Multiples Visitas
- **POST** `/v1/bulk/delete/visits/`
```json
{"visits":[462783899,462783900,462783901]}
```

### 5.14 Checkout Individual (v3)
- **POST** `/v1/mobile/visit/{visit_id}/checkout/`
```json
{"status":"completed","checkout_time":"2024-04-24 13:24:53","checkout_latitude":-12.105513,"checkout_longitude":-76.965618,"checkout_comment":"OK"}
```
Status: `pending`, `completed`, `failed`

### 5.15 Checkout Multiple
- **POST** `https://api-mobile.simpliroute.com/v1/mobile/visit/multiple/checkout`
```json
{"checkout_comment":"","checkout_latitude":"18.642840","checkout_longitude":"-91.828534","checkout_observation":"","checkout_time":"2022-03-02T18:40:34.676Z","has_alert":"False","status":"completed","visits":[148926640]}
```

### 5.16 Checkout Notify
- **POST** `https://api-mobile.simpliroute.com/v1/mobile/visit/multiple/checkout/notify`
```json
{"checkout_time":"2021-11-24T16:16:55.316Z","visits":[129306649]}
```

### 5.17 On Its Way
- **PATCH** `https://api-mobile.simpliroute.com/v1/mobile/visit/`
```json
{"filter":{"ids":[407552458]},"data":{"on_its_way":"2024-04-24T19:30:48.743Z"}}
```

### 5.18 Extra Field Values
- **POST** `/v1/routes/visits/{visit_id}/extra-field-values`
```json
{"json":"{\"monto_recogido\":\"555\",\"nombre_recibe\":\"Alonso\"}"}
```

### 5.19 Validacion de Ventanas de Tiempo
- Hora inicio NO puede ser mayor que hora fin
- Ventana NO puede extenderse al dia siguiente
- Ventana 1 NO puede ser posterior a ventana 2
- NO debe haber interseccion entre ventanas
- Error: `"Time error: the time window order is inverted."`

---

## 6. ITEMS DE VISITA

| Operacion | Metodo | Endpoint |
|-----------|--------|----------|
| Crear | POST | `/v1/routes/visits/{visit_id}/items` |
| Listar | GET | `/v1/routes/visits/{visit_id}/items` |
| Editar | PUT | `/v1/routes/visits/{visit_id}/items` |
| Eliminar | DELETE | `/v1/routes/visits/{visit_id}/items/` |

```json
[{"title":"Producto 1","load":3,"load_2":2,"load_3":2,"reference":"2772263","notes":"Nota","quantity_planned":null}]
```

### Items Subtype (Pickup Item Types)
- **GET** `/v1/accounts/pickup-item-types/`
- **PATCH** `/v1/accounts/pickup-item-types/`
```json
[{"id":76,"name":"CM DUAL","subtypes":[{"id":398,"name":"Tarjetas"},{"id":399,"name":"Fuentes"}]}]
```

---

## 7. FOTOS DE VISITA

| Operacion | Metodo | Endpoint |
|-----------|--------|----------|
| Subir foto individual | POST | `/v1/routes/visits/{visit_id}/pictures` (formdata: image) |
| Subir fotos multiple | POST | `/v1/routes/visits/multiple/pictures` (formdata: visits, image) |
| Eliminar fotos multiple | DELETE | `/v1/routes/visits/multiple/pictures` |

### Reporte de Imagenes
- **POST** `/v1/reports/visit-images/`
```json
{"fromDate":"2021-05-31","toDate":"2021-05-31","startTime":"08:00","endTime":"22:00","email":"user@mail.com","accountId":11236,"pictureName":"Reference"}
```

---

## 8. CAMPOS EXTRA (Extra Fields)

### v1 - Lectura
- **GET** `/v1/accounts/extra-fields/`

### v2 - CRUD completo

| Operacion | Metodo | Endpoint |
|-----------|--------|----------|
| Listar | GET | `/v2/accounts/extra-fields/` |
| Crear | POST | `/v2/accounts/extra-fields/` |
| Editar | PUT | `/v2/accounts/extra-fields/{id}/` |
| Eliminar | DELETE | `/v2/accounts/extra-fields/{id}/` |
| Opciones | PATCH | `/v2/accounts/extra-fields/{id}/` |

**Crear:**
```json
{"label":"campo_nuevo","key":"campo_nuevo","order":1,"enable":true,"type":"STX","is_alert":false,"is_read":false,"is_write":true,"is_mandatory":true,"checkout_type":"OK","options":[]}
```

**Actualizar opciones:**
```json
{"options":[{"value":"opcion1","options":[]},{"value":"opcion2","options":[]}]}
```

**Campos:** id, label, key, order, enable, type (STX=short text), checkout_type (S&F=success&fail, OK=success only), is_alert, is_read, is_write, is_mandatory, visit_types

---

## 9. OBSERVACIONES (Observations)

| Operacion | Metodo | Endpoint |
|-----------|--------|----------|
| Listar | GET | `/v1/routes/observations/` |
| Listar filtrado | GET | `/v1/routes/observations/?label=Label 1` |
| Agrupadas | GET | `/routes/observations-grouped/` |
| Crear | POST | `/v1/routes/observations/` |
| Leer | GET | `/v1/routes/observations/{uuid}` |
| Actualizar | PUT | `/v1/routes/observations/{uuid}/` |
| Eliminar | DELETE | `/v1/routes/observations/{uuid}/` |

```json
{"type":"failed","label":"Cliente ausente"}
```
Tipos: `completed`, `failed`

---

## 10. TAGS (Etiquetas)
- **GET** `/v1/routes/tags`
```json
[{"id":4185,"label":"pickup","color":"#472929"}]
```

---

## 11. VISIT TYPES (Tipos de Visita)
- **GET** `/v1/accounts/visit-types/`
- **POST** `/v1/accounts/visit-types/`
```json
{"label":"Tipo_nuevo","key":"tipo_nuevo"}
```

---

## 12. PLANES (Plans)

### 12.1 Listar Planes
- **GET** `/v1/routes/plans/`
- Filtro por fecha: `?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD`

### 12.2 Leer Plan
- **GET** `/v1/routes/plans/{uuid}/`

### 12.3 Resumen de Plan
- **GET** `/v1/routes/plans/plan/{uuid}/summary`

### 12.4 Crear Plan (v1)
- **POST** `/v1/plans/create-plan/`

**Parametros del plan:**
| Parametro | Tipo | Requerido | Descripcion |
|-----------|------|----------|-------------|
| name | string | Si | Nombre unico del plan |
| start_date | date | Si | Fecha inicio |
| end_date | date | Si | Fecha fin (debe = start_date) |
| routes | array | Si | Rutas con asignaciones |

**Parametros de ruta (dentro de routes):**
| Parametro | Tipo | Requerido | Descripcion |
|-----------|------|----------|-------------|
| driver | integer | Si | ID del conductor |
| vehicle | integer | Si | ID del vehiculo |
| planned_date | date | Si | Debe coincidir con plan |
| estimated_time_start | time | Si | Hora inicio |
| estimated_time_end | time | Si | Hora fin |
| total_load | double | No | Carga total |
| location_start_address | string | No | Direccion inicio |
| location_start_latitude | float | No | Latitud inicio |
| location_start_longitude | float | No | Longitud inicio |
| location_end_address | string | No | Direccion fin |
| location_end_latitude | float | No | Latitud fin |
| location_end_longitude | float | No | Longitud fin |
| visits | array | Si | Visitas en la ruta |

**Parametros de visita (dentro de visits de ruta):**
| Parametro | Tipo | Requerido |
|-----------|------|----------|
| title | string | Si |
| address | string | Si |
| order | integer | Si |
| planned_date | date | Si |
| estimated_time_arrival | time | Si |
| estimated_time_departure | time | Si |
| latitude, longitude | float | No |
| load, duration, window_start, window_end | varies | No |
| contact_name, contact_email, notes | string | No |

```json
{"name":"Plan API 2024-01-15","start_date":"2024-01-15","end_date":"2024-01-15","routes":[{"driver":"183371","vehicle":"288202","planned_date":"2024-01-15","estimated_time_start":"08:00:00","estimated_time_end":"17:00:00","location_start_address":"Av. Principal 100","location_start_latitude":-33.45,"location_start_longitude":-70.65,"location_end_address":"Av. Principal 100","location_end_latitude":-33.45,"location_end_longitude":-70.65,"visits":[{"title":"Order 1234","address":"Calle 1, Santiago","latitude":-33.41,"longitude":-70.58,"order":1,"load":1,"duration":"00:10:00","planned_date":"2024-01-15","estimated_time_arrival":"08:10","estimated_time_departure":"08:20"}]}]}
```

### 12.5 Editar Plan (v2)
- **POST** `/v2/plans/edit-plan/`
- Misma estructura que crear, con `plan_metadata` y `routing_options`

### 12.6 Actualizar Plan
- **PUT** `/v1/routes/plans/{uuid}/`

### 12.7 Eliminar Plan
- **DELETE** `/v1/routes/plans/{uuid}/`

---

## 13. RUTAS (Routes)

### 13.1 Listar Rutas
- **GET** `/v1/routes/routes/`
- Filtro: `?planned_date=YYYY-MM-DD`

### 13.2 Crear Ruta
- **POST** `/v1/routes/routes/`
```json
[{"vehicle":2032,"driver":null,"plan":"uuid","planned_date":"2024-01-15","estimated_time_start":"08:00:00","estimated_time_end":"17:00:00","status":"pending","total_load":2086,"location_start_address":"Calle 1","location_start_latitude":"-33.43","location_start_longitude":"-70.64","location_end_address":"Calle 2","location_end_latitude":"-33.42","location_end_longitude":"-70.60","reference":"my reference"}]
```

### 13.3 Leer Ruta
- **GET** `/v1/routes/routes/{uuid}/`

### 13.4 Actualizar Ruta
- **PUT** `/v1/routes/routes/{uuid}/`
- Body: objeto ruta completo con todos los campos

### 13.5 Actualizar Reference
- **PATCH** `/v1/routes/routes/{route_id}/`
```json
{"reference":"my own reference"}
```

### 13.6 Eliminar Ruta
- **DELETE** `/v1/routes/routes/{uuid}/`

### 13.7 Vehiculos con Rutas por Fecha
- **GET** `/v1/plans/{YYYY-MM-DD}/vehicles/`
```json
[{"color":"#FFCC33","routes":[{"plan_id":"uuid","id":"uuid"}],"driver":{"id":742,"name":"Conductor Demo"},"name":"Mi auto","id":287}]
```

### 13.8 Visitas de una Ruta (por plan_id)
- **GET** `/v1/plans/routes/{plan_id}/visits/`

### 13.9 Iniciar/Finalizar Ruta (via eventos)
- **POST** `https://api-mobile.simpliroute.com/v1/events/register/`
```json
{"date_time":"2024-01-15T14:00:00.000Z","latitude":19.53,"longitude":-99.17,"route_id":"uuid","type":"ROUTE_STARTED"}
```
Tipos: `ROUTE_STARTED`, `ROUTE_FINISHED`

---

## 14. PROPIEDADES DE RUTA (Route Properties)

| Operacion | Metodo | Endpoint |
|-----------|--------|----------|
| Obtener | GET | `/v1/routes/routes-properties/{route_id}` |
| Crear | POST | `/v1/routes/routes-properties/` |
| Actualizar (PUT) | PUT | `/v1/routes/routes-properties/{route_id}` |
| Actualizar (PATCH) | PATCH | `/v1/routes/routes-properties/{route_id}` |
| Eliminar | DELETE | `/v1/routes/routes-properties/{route_id}` |
| Busqueda masiva | POST | `/v1/routes/routes-properties/bulk-search/` |

```json
{"route":"uuid","color":"#0000FF","is_start_blocked":false}
```
Bulk search: `{"route_ids":["uuid1","uuid2"]}`

---

## 15. VEHICULOS (Vehicles)

| Operacion | Metodo | Endpoint |
|-----------|--------|----------|
| Listar | GET | `/v1/routes/vehicles/` |
| Buscar | GET | `/v1/routes/vehicles/?name=Vehiculo1` |
| Crear | POST | `/v1/routes/vehicles/` |
| Leer | GET | `/v1/routes/vehicles/{id}/` |
| Actualizar | PUT | `/v1/routes/vehicles/{id}/` |
| Eliminar | DELETE | `/v1/routes/vehicles/{id}/` |
| Soft-delete | PUT | `/v1/routes/vehicles/{id}/` con `"deleted":"true"` |
| Disponibilidad | GET | `/v1/plans/vehicles/availability/?start={ts}&end={ts}` |
| Disponibilidad (flota) | GET | `/v1/plans/vehicles/availability/?start={ts}&end={ts}&fleet={id}` |

**Parametros requeridos:** name, capacity, location_start_latitude, location_start_longitude, location_start_address, location_end_latitude, location_end_longitude, location_end_address

**Parametros opcionales:** capacity_2, capacity_3, default_driver, skills, cost, shift_start, shift_end, reference_id, license_plate, min_load, min_load_2, min_load_3, max_visit, max_time, rest_time_start, rest_time_end, rest_time_duration, codrivers, color

```json
{"name":"Camion-1","capacity":1000,"location_start_address":"Calle 1","location_start_latitude":"-33.45","location_start_longitude":"-70.65","location_end_address":"Calle 1","location_end_latitude":"-33.45","location_end_longitude":"-70.65","capacity_2":"1","capacity_3":"1","reference_id":"12AB","license_plate":"ABCD","max_visit":10}
```

---

## 16. HABILIDADES (Skills)

| Operacion | Metodo | Endpoint |
|-----------|--------|----------|
| Listar | GET | `/v1/routes/skills/` |
| Crear | POST | `/v1/routes/skills/` |
| Leer | GET | `/v1/routes/tag/{id}` |
| Actualizar | PUT | `/v1/routes/skills/{id}/` |
| Eliminar | DELETE | `/v1/routes/skills/{id}` |

```json
{"skill":"refrigerado"}
```

---

## 17. CLIENTES (Clients)

| Operacion | Metodo | Endpoint |
|-----------|--------|----------|
| Listar | GET | `/v1/accounts/clients/` |
| Buscar por key | GET | `/v1/accounts/clients/?key={client_key}` |
| Crear | POST | `/v1/accounts/clients/` |
| Actualizar | PUT | `/v1/accounts/clients/` (array con id) |
| Eliminar individual | DELETE | `/v1/accounts/clients/{client_id}/` |
| Eliminar multiples | DELETE | `/v1/accounts/clients/` body: `[id1, id2]` |

**Parametros:** key (req), title (req), address, latitude, longitude, load, load_2, load_3, window_start, window_end, window_start_2, window_end_2, duration, contact_name, contact_phone, contact_email, notes, priority_level, skills_required, skills_optional, tags, custom_properties

```json
[{"key":"123456","title":"Cliente 1","address":"Calle 123","latitude":-33.41,"longitude":-70.58,"load":5,"duration":"00:15:00","contact_name":"Juan","priority_level":3}]
```

### Propiedades Personalizadas
- **POST** `/v1/planner/client-properties/`
```json
{"label":"price","type":"int"}
```
Tipos: `str`, `int`, `float`, `bool`

Uso en cliente: `"custom_properties":{"price":100,"currency":"USD"}`

### ForceField - Programacion de Visitas (addon `territory_planner`)
**sales_visit_scheduled:** `{"period":7,"interval":4,"frequency":2}` (period: 7=semanal, 14=bisemanal, 28=mensual)
**scheduled_visit_days:** `{"any_week":["Monday","Tuesday"],"week_1":["Monday"],...}`

---

## 18. ZONAS (Zones)

| Operacion | Metodo | Endpoint |
|-----------|--------|----------|
| Listar | GET | `/v1/zones/` |
| Crear | POST | `/v1/zones/` |
| Eliminar | DELETE | `/v1/zones/{id}` (sin trailing slash; 204 o 200 = exito) |

Requiere addon `zones`

```json
{"name":"ZONA-1","coordinates":"[{'lat':'19.4','lng':'-99.1'},{'lat':'19.5','lng':'-99.2'}]","vehicles":[],"schedules":["Monday","Tuesday","Wednesday","Thursday","Friday"]}
```

---

## 19. FLOTAS (Fleets)

| Operacion | Metodo | Endpoint |
|-----------|--------|----------|
| Listar | GET | `/v1/fleets/` |
| Crear | POST | `/v1/fleets/` |

Requiere addon `fleets`

```json
{"name":"Almacen A","vehicles":[404639,297117],"users":[185434,183371]}
```

---

## 20. ADDONS

| Operacion | Metodo | Endpoint |
|-----------|--------|----------|
| Listar | GET | `/v1/addons/addons/` |
| Leer propiedad | GET | `/v1/addons/{key}/` |
| Crear (admin) | POST | `/admin/addons/addon/add/` |

---

## 21. WEBHOOKS

### CRUD
| Operacion | Metodo | Endpoint |
|-----------|--------|----------|
| Listar | GET | `/v1/addons/webhooks` |
| Crear | POST | `/v1/addons/webhooks` |
| Actualizar | PUT | `/v1/addons/webhooks` |
| Eliminar | DELETE | `/v1/addons/webhooks` body: `{"webhook":"plan_created"}` |

**Eventos:** `plan_created`, `plan_edited`, `route_created`, `route_edited`, `route_started`, `route_finished`, `on_its_way`, `visit_checkout`, `visit_checkout_detailed`

```json
{"webhook":"plan_created","url":"https://mi-webhook.com","headers":{"Content-Type":"application/json","Authorization":"Token abc123"}}
```

Reintentos: 3 intentos max, cada 30 segundos. Receptor debe responder 200.

### Send Webhooks (forzar envio)
- **POST** `/v1/mobile/send-webhooks`
```json
{"account_ids":[11374],"planned_date":"2024-01-15","hours_back":48}
```
Con rango horario:
```json
{"account_ids":[39545],"planned_date":"2024-02-07","hours_back_start":10,"hours_back_end":0}
```
Con rutas/visitas especificas:
```json
{"account_ids":[11374],"planned_date":"2024-01-15","route_ids":[123],"visit_ids":[456]}
```

### Payloads de Webhooks

**Plan Creado:**
```json
{"account_id":295,"id":"uuid","start_date":"2024-01-15","end_date":"2024-01-15","reset_day":1,"route_ids":["uuid"],"fleet_id":647}
```

**Plan Editado:** Incluye account, routes con visits, driver, vehicle.

**Ruta Creada:**
```json
{"id":"uuid","planned_date":"2024-01-15","plan":{"id":"uuid","name":"15-01-2024"},"driver":{"id":118553,"name":"Driver 1"},"route_start":{"lat":"-33.44","lon":"-70.65","address":"Calle 1","estimated_time_start":"09:42:00"},"route_end":{"lat":"-33.44","lon":"-70.65","address":"Calle 1","estimated_time_end":"10:08:00"},"visit_ids":[370679703],"vehicle":{"id":266603,"name":"VEH1","reference":"XXX333"},"timestamp":"2024-01-30 15:14:45","status":"created"}
```

---

## 22. DIRECTORIO - DIRECCIONES (Addresses)

| Operacion | Metodo | Endpoint |
|-----------|--------|----------|
| Listar | GET | `/v1/directory/addresses/` |
| Buscar por direccion | GET | `/v1/directory/addresses/?address=...` |
| Buscar | GET | `/v1/directory/addresses/?search=Pasaje` |
| Crear | POST | `/v1/directory/addresses/` |
| Leer | GET | `/v1/directory/addresses/{uuid}` |
| Actualizar | PUT | `/v1/directory/addresses/{uuid}/` |
| Eliminar | DELETE | `/v1/directory/addresses/{uuid}` |

```json
{"address":"Santiago","latitude":"-33.439328","longitude":"-70.664746"}
```

---

## 23. GEOCODIFICACION

### SimpliRoute Geocode
- **POST** `/v1/directory/geocode/`
- Individual: `{"address":"Calle 123, Santiago"}`
- Batch: `[{"address":"Calle 1"},{"address":"Calle 2"}]`

### Nuevo Geocoder (Cloud Function)
- **POST** `https://us-central1-geocoding-265816.cloudfunctions.net/geocoder_prod`
```json
{"country":"CL","qualityLevel":1,"addresses":{"id-1":{"rawAddress":"Malaga 50, las condes"}}}
```
Response:
```json
{"id-1":{"rawAddress":"Malaga 50, las condes","cleanedAddress":"...","georeferenceInaccuracy":"no alert","latitude":-33.41,"longitude":-70.58,"provider":"google","streetName":"Malaga","administrativeArea":"Las Condes","locality":"Las Condes"}}
```

---

## 24. TRACKING - UBICACIONES GPS

### Por conductor
- **GET** `https://api-track.simpliroute.com/v1/tracking/locations/{YYYY-MM-DD}/?driver_id={id}`

### Por vehiculo
- **GET** `https://api-track.simpliroute.com/v1/tracking/locations/{YYYY-MM-DD}/?vehicle_id={id}`

Response:
```json
[{"timestamp":"2024-01-15T14:30:00Z","latitude":"-33.43","longitude":"-70.64","activity_type":"...","type":"simpli","id":123,"accuracy":0,"alerts":[]}]
```

### Enviar GPS externo
- **POST** `https://9zyupks8yg.execute-api.us-west-2.amazonaws.com/prod/track/`
- Auth: `ApiKey` header
```json
[{"latitude":-33.48,"longitude":-70.88,"timestamp":"2024-01-15 12:10:00","vehicleId":"120428","providerName":"TEST"}]
```

---

## 25. EVENTOS

- **POST** `https://api-mobile.simpliroute.com/v1/events/register/`
```json
{"date_time":"2024-01-15T14:00:00.000Z","latitude":19.53,"longitude":-99.17,"route_id":"uuid","type":"ROUTE_STARTED"}
```
Tipos: `ROUTE_STARTED`, `ROUTE_FINISHED`

### Logout
- **POST** `https://api-mobile.simpliroute.com/v1/auth/last-logout/`
```json
{"auth_token":"..."}
```

---

## 26. OSRM (Motor de Ruteo)

| Operacion | Metodo | Endpoint |
|-----------|--------|----------|
| Tabla distancias (GET) | GET | `https://osrm.simpliroute.com/table?loc=lat,lng&loc=lat,lng` |
| Tabla distancias (POST) | POST | `https://osrm.simpliroute.com/table` (form: loc=lat,lng) |
| Ruta via puntos | GET | `https://osrm.simpliroute.com/viaroute?loc=lat,lng&loc=lat,lng&uturns=false` |

---

## 27. OPTIMIZACION (VRP)

- **POST** `https://optimizator.simpliroute.com/vrp/optimize/sync/`

**Vehiculos:**
| Campo | Tipo | Descripcion |
|-------|------|-------------|
| ident | string | Identificador |
| location_start | object | {ident, lat, lon} |
| location_end | object | {ident, lat, lon} |
| capacity | double | Capacidad 1 |
| capacity_2 | double | Capacidad 2 |
| capacity_3 | double | Capacidad 3 |
| shift_start | time | Inicio jornada |
| shift_end | time | Fin jornada |
| max_tour_duration | time | Duracion max |
| skills | array | Habilidades |
| zones | array | Zonas asignadas |
| cost | double | Costo |
| min_load/2/3 | double | Carga minima |
| max_visit | int | Max visitas |
| rest_time_start/end/duration | time | Descanso |
| open_start | bool | Inicio abierto |

**Nodos (visitas):**
| Campo | Tipo | Descripcion |
|-------|------|-------------|
| ident | string | Identificador |
| lat, lon | float | Coordenadas |
| duration | int | Minutos servicio |
| load/load_2/load_3 | double | Cargas |
| window_start/end | time | Ventana horaria |
| window_start_2/end_2 | time | Ventana alternativa |
| skills_required | array | Hab. requeridas |
| skills_optional | array | Hab. opcionales |
| priority_level | int | Prioridad |
| zones | array | Zonas |
| group | string | Grupo |

**Opciones globales:** balance, all_vehicles, join, open_ended, fmv, fmb, single_tour, beauty, use_euclidean_distance, autoZone, country, longRoutes, enable_graphs, auto_reorder, intensive_intra, open_routes_logic, vehicle_capacities_increment, vehicle_journey_extention, enable_rest_time, enable_soft_window, load_balance, time_balance, visit_joiner, wave_routing, start_time

---

## 28. COMENTARIOS (via api-gateway)

| Operacion | Metodo | Endpoint |
|-----------|--------|----------|
| Listar | GET | `https://api-gateway.simpliroute.com/v1/visits/{visit_id}/comments/` |
| Crear | POST | `https://api-gateway.simpliroute.com/v1/visits/{visit_id}/comments/` |
| Editar | PATCH | `https://api-gateway.simpliroute.com/v1/visits/{visit_id}/comments/{comment_uuid}` |
| Eliminar | DELETE | `https://api-gateway.simpliroute.com/v1/visits/{visit_id}/comments/` |

```json
{"content":"Esto es un comentario"}
```
Eliminar: `{"ids":["uuid1","uuid2"]}`

---

## 29. FACTURAS (Invoices)

- **GET** `/v1/accounting/invoices/?visit_id={visit_id}`
- **POST** `/v1/accounting/invoices/`
```json
{"reference":6593873,"currency":"CLP","visit":406027294,"type":"bill","status":"pending","payment_method":"credit","payment_method_details":"Credito a 60 dias","items":[{"title":"Producto","sku":"1111","unit_price":22368,"planned_units":1,"type":"CAJ","reference":12345678}]}
```

---

## 30. DELIVERY ISSUES

| Operacion | Metodo | Endpoint |
|-----------|--------|----------|
| Listar | GET | `/v1/accounting/invoices/delivery-issues/` |
| Crear | POST | `/v1/accounting/invoices/delivery-issues/` |
| Editar | PATCH | `/v1/accounting/invoices/delivery-issues/{id}/` |
| Eliminar | DELETE | `/v1/accounting/invoices/delivery-issues/{id}/` |

```json
{"is_removed":false,"title":"Cliente No Solicita Pedido","type":"item","description":"Cliente","reference":null}
```

---

## 31. DASHBOARD

- **GET** `/v1/dashboards/visit-checkouts/year/{YYYY}/month/{MM}/`
- **GET** `/v1/dashboards/visit-totals/year/{YYYY}/month/{MM}/`

---

## 32. EXTENSIONS
- **POST** `/v1/extensions/add/`
```json
{"account":78139,"users":[287568,290467],"label":"Reporte de Visitas","url":"https://app.retool.com/embedded/..."}
```

---

## 33. REPORTES

### Reporte de Visitas (por email)
- **GET** `/v1/reports/visits/from/{start}/to/{end}/?email={email}`

### Reporte de Rutas (descarga xlsx)
- **GET** `/v1/reports/routes/from/{start}/to/{end}/?start_time=00:00&end_time=23:59`
- Base: `https://api-gateway.simpliroute.com` o `https://api.simpliroute.com`

### Reporte de Imagenes
- **POST** `/v1/reports/visit-images/` (ver seccion Fotos)

---

## MODELOS DE DATOS

### Visit Object
| Campo | Tipo | Descripcion |
|-------|------|-------------|
| id | integer | ID unico |
| order | integer | Orden en la ruta |
| tracking_id | string | Codigo seguimiento |
| status | string | `pending`, `partial`, `completed`, `failed`, `canceled` |
| title | string | Nombre entrega |
| address | string | Direccion |
| latitude, longitude | float | Coordenadas |
| load, load_2, load_3 | double | Cargas |
| window_start, window_end | time | Ventana 1 |
| window_start_2, window_end_2 | time | Ventana 2 |
| duration | time | Tiempo servicio |
| contact_name, contact_phone, contact_email | string | Contacto |
| reference | string | Referencia interna |
| notes | string | Notas |
| skills_required, skills_optional | array | Habilidades |
| tags | array | Etiquetas |
| planned_date | date | Fecha planificada |
| route | UUID | ID ruta |
| estimated_time_arrival, estimated_time_departure | time | ETAs |
| checkin_time, checkout_time | timestamp | Tiempos reales |
| checkout_latitude, checkout_longitude | float | Coords cierre |
| checkout_comment | string | Comentario cierre |
| checkout_observation | UUID | ID observacion |
| signature | string | URL firma |
| pictures | array(URL) | URLs fotos |
| created, modified | timestamp | Timestamps |
| priority | boolean | Es prioritaria |
| priority_level | integer | Nivel (1-5) |
| has_alert | boolean | Tiene alerta |
| extra_field_values | object | Campos extra |
| fleet | integer | ID flota |
| items | array | Articulos |
| on_its_way | timestamp | "En camino" |

### Route Object
| Campo | Tipo | Descripcion |
|-------|------|-------------|
| id | UUID | ID unico |
| vehicle | integer | ID vehiculo |
| driver | integer | ID conductor |
| plan | UUID | ID plan |
| status | string | `pending`, `started`, `finished` |
| planned_date | date | Fecha |
| estimated_time_start, estimated_time_end | time | ETAs |
| total_duration | time | Duracion total |
| total_distance | integer | Distancia (metros) |
| total_load, total_load_2, total_load_3 | double | Cargas totales |
| total_load_percentage, total_load_2_percentage, total_load_3_percentage | double | % capacidad |
| location_start_address, location_start_latitude, location_start_longitude | string/float | Inicio |
| location_end_address, location_end_latitude, location_end_longitude | string/float | Fin |
| start_time, end_time | timestamp | Tiempos reales |
| comment | string | Comentario |
| created, modified | timestamp | Timestamps |
| total_visits | integer | Numero visitas |
| is_revised | boolean | Revisada |
| reference | string | Referencia |

### Vehicle Object
| Campo | Tipo | Descripcion |
|-------|------|-------------|
| id | integer | ID unico |
| name | string | Nombre |
| capacity, capacity_2, capacity_3 | double | Capacidades |
| default_driver | integer | Conductor default |
| location_start_address/latitude/longitude | string/float | Almacen inicio |
| location_end_address/latitude/longitude | string/float | Almacen fin |
| skills | array | Habilidades |
| shift_start, shift_end | time | Jornada |
| cost | double | Costo operativo |
| reference_id | string | Placa/patente |
| license_plate | string | Numero placa |
| min_load, min_load_2, min_load_3 | double | Cargas minimas |
| max_visit | integer | Max visitas |
| max_time | time | Tiempo max |
| color | string | Color hex |
| status | string | `active`, `inactive` |
| deleted | boolean | Eliminado |

### Client Object
| Campo | Tipo | Descripcion |
|-------|------|-------------|
| id | integer | ID unico |
| key | string | Identificador externo |
| title | string | Nombre |
| address, latitude, longitude | string/float | Ubicacion |
| load, load_2, load_3 | double | Cargas default |
| window_start, window_end | time | Ventana |
| duration | time | Duracion servicio |
| contact_name, contact_phone, contact_email | string | Contacto |
| notes | string | Notas |
| priority_level | integer | Prioridad (1-5) |
| custom_properties | object | Props personalizadas |

### Item Object
| Campo | Tipo | Descripcion |
|-------|------|-------------|
| id | integer | ID unico |
| title | string | Nombre |
| status | string | `pending`, `failed`, `completed` |
| load, load_2, load_3 | double | Cargas |
| reference | string | Identificador |
| visit | integer | ID visita |
| notes | string | Notas |
| quantity_planned, quantity_delivered | float | Cantidades |

### Plan Object
| Campo | Tipo | Descripcion |
|-------|------|-------------|
| id | UUID | ID unico |
| name | string | Nombre |
| start_date, end_date | date | Fechas |
| reset_day | integer | Dia reinicio (1-7, 100=no) |
| is_cluster | boolean | Es cluster |
| routes | array(UUID) | IDs rutas |
| fleet_id | integer | ID flota |
