---
name: project-migracion-nextjs-brandon
description: Brandon esta reescribiendo simpliroute-tools en Next.js/Supabase; su repo real vive en origin/main del clon en c:\Proyectos\repo, no en master
metadata:
  type: project
---

El colega Brandon (ver [[project_repo_colega_brandon]]) esta migrando esta app (Streamlit/Python) a un stack completamente nuevo: **Next.js 16 + React 19 + TypeScript + Supabase**, repo `brandonvargas-simpli/simpliroute-tools`. Confirmado 2026-09-03 vía `git fetch origin` en `c:\Proyectos\repo` (el `master` local de ese clon sigue a `pruebas`, que es esencialmente nuestro propio codigo — el proyecto real de Brandon esta en `origin/main`, hay que hacer fetch para verlo, no basta con mirar el working tree).

Su propio repo trae `docs/legacy-tool-reports/` — una auditoria de **nuestro repo exacto** (evaluada contra el commit `ecb9f4f`, que es nuestro HEAD de esa fecha) con tabla canonica de migracion:

**Ya migradas y probadas en produccion:** Edicion Masiva de Visitas, Webhooks Likewise, Mover Visitas Likewise, Bloqueo LVP, Reporte Visitas/Rutas, Checkout General, Checkout BAT (absorbida en General), Reenvio Webhooks.

**Pendientes (no existen aun en su app nueva, seguimos siendo la unica fuente):** Eliminacion de Items, Unilever, Zonas KML, Recuperar Visitas LVP, Detalle Visitas LVP, Eliminar Visitas BAT, Eliminar Visitas, Asignacion Fija Uni (1 y 2), Cambio de Fechas, Eventos de Ruta, Flotas, Validador de Plan.

Ademas, su app agrega capacidades que nunca existieron aca: Inspector 360 de vehiculos, Agenda de vehiculos, Inspector de consistencia de rutas (con reasignacion segura de conductor/vehiculo), Auditor de flotas, Directorio de usuarios + Visibilidad de planes, Salud GPS, Visitas Liverpool (busqueda cross-cuenta via Retool), galeria de evidencias de checkout, cierre de sesion movil de conductores, reenvio de webhook contextual desde cualquier listado.

Diferencias de arquitectura/seguridad relevantes: Supabase Auth (sin registro publico), Staff Token personal cifrado en Vault (no token compartido en secrets.toml como aca), feature flags por cada escritura (apagadas por defecto, validadas al boot con `pnpm validate:write-flags`), auditoria append-only con sanitizacion de secretos, idempotencia + readback en cada mutacion, tests con Vitest, CI en GitHub Actions + deploy Vercel con gate de promocion a produccion.

**Por que importa:** el repo de trabajo actual (`pruebassimpli`, este `Edicion`) esta siendo tratado como "legacy" por el equipo de Brandon — 8 de nuestras 21 herramientas ya tienen equivalente migrado y probado en produccion en el stack nuevo. Las 13 restantes (incluye Unilever, Zonas KML, Asignacion Fija Uni, Cambio de Fechas, Eventos de Ruta) siguen dependiendo de este repo.

**Como aplicar:**
- Antes de invertir esfuerzo grande en una de las 8 herramientas ya migradas (Edicion Masiva, Webhooks Likewise, Mover Visitas Likewise, Bloqueo LVP, Reporte Visitas/Rutas, Checkout General/BAT, Reenvio Webhooks), preguntar si tiene sentido seguir iterando aca o si el trabajo deberia ir al repo nuevo — puede ser esfuerzo duplicado.
- Para las 13 pendientes, este repo sigue siendo la fuente autoritativa; no asumir que ya tienen equivalente en el stack nuevo.
- Para revisar el estado real del repo de Brandon en el futuro: `cd c:\Proyectos\repo && git -c http.sslBackend=schannel fetch origin` (ver [[reference_tls_workaround_entorno]]) y mirar `origin/main`, NUNCA el `master` local (que es una copia de `pruebas`).
