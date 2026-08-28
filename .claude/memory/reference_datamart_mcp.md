---
name: reference-datamart-mcp
description: "Conector MCP datamart-mcp-prod para consultas de solo lectura a datos operacionales de SimpliRoute (entregas, rutas, vehiculos, config de cuentas)"
metadata: 
  node_type: memory
  type: reference
  originSessionId: c7543105-62de-4014-8295-30d47211cdb8
  modified: 2026-08-18T05:39:02.947Z
---

**Que es:** `datamart-mcp-prod` es un conector MCP interno de SimpliRoute (uso exclusivo staff) que da acceso de **solo lectura** a datos operacionales: entregas/visitas, rutas, vehiculos, configuracion de cuentas (campos personalizados, webhooks). Se le pregunta en lenguaje natural (sin SQL, sin backoffice) y responde con datos reales, siempre indicando cuenta y rango de fechas usado. Historico disponible desde el 1 de enero del año pasado. Todas las consultas quedan registradas (quien, que, sobre que cliente).

**URL:** `https://datamart-mcp-prod.simpliroute.com/mcp`

**Como se conecta en Claude Code (CLI/VS Code):** No requiere `claude mcp add` manual — ya esta publicado en el directorio de conectores de la organizacion en claude.ai, y por eso aparece automaticamente en `claude mcp list` de cualquier sesion de Claude Code de un usuario con acceso, con el prefijo `claude.ai datamart-mcp-prod`. Solo falta autorizarlo:
1. En claude.ai (web), boton `+` → Conectores → Explorar conectores → buscar `datamart`.
2. Conectar `datamart-mcp-prod` → login con cuenta corporativa (@simpliroute.com o @simplit-solutions.com).
3. Verificar con `claude mcp list` en terminal: debe mostrar `✓ Connected` (antes muestra `! Needs authentication`).

La autorizacion se gestiona **solo desde claude.ai** (connector settings), no desde `claude mcp add` local — es un conector centralizado a nivel de cuenta/organizacion, no uno agregado manualmente al proyecto.

**Estado al 2026-08-17:** confirmado funcionando en una sesion nueva. Las tools (`my_accounts`, `search_accounts`, `query`, `aggregate`, `fleet_overview`, `describe_view`, `list_views`, `list_extra_fields`, `feature_adoption`, `count_accounts`, `configuration`, `server_info`) cargan via ToolSearch (`select:mcp__claude_ai_datamart-mcp-prod__...`) y `my_accounts` respondio correctamente (`bounded: false` — sesion sin cuenta fija, se resuelve cualquiera con `search_accounts`). El problema anterior (no aparecian en la misma sesion donde se autorizo) si era por lista de tools fijada al iniciar conversacion; se resuelve con sesion nueva.

**Reglas de uso (del propio MCP):** son respuestas para gente que opera entregas, no para ingenieros — al hablar con el usuario, nombrar cuentas por su nombre y fechas claras, nunca mencionar tools/tokens/sesiones/scopes internos. Si una cuenta esta fuera de alcance, decir que no se puede responder y parar (no especular si existe, no sugerir cambiar tokens/permisos). Resultado vacio = sin filas en esas fechas, no prueba de que algo no paso.

**No confundir con:** existe otro conector separado llamado `claude.ai Simpliroute` que apunta a `https://bigquery.googleapis.com/mcp` — es acceso directo a BigQuery, algo distinto a datamart-mcp-prod.

**Fuente:** PDF de la guia interna `datamart-mcp` (Descargas de Cesar, `d7030193-69c0-4e3d-98cd-7cc732459475_datamart-mcp.pdf`).
