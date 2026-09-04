---
name: project-repo-colega-brandon
description: Clon nuevo en c:\Proyectos\repo con remotes hacia el repo del colega Brandon y hacia pruebassimpli
metadata:
  type: project
---

Se creo un clon independiente en `c:\Proyectos\repo` (2026-09-03), separado del repo de trabajo habitual en `c:\Proyectos\Edicion`. Remotes configurados:
- `pruebas` -> `https://github.com/CesarClaudio1424/pruebassimpli.git` (renombrado desde `origin` original del clone)
- `origin` -> `https://github.com/brandonvargas-simpli/simpliroute-tools.git` (repo del colega Brandon)

**Por que importa:** es parte del esquema de colaboracion con el colega descrito en [[project_memoria_skills_versionados]] — mismo contexto/memoria compartido via `.claude/`, pero cada quien con su propio clon local y sus propios remotes.

**Como aplicar:**
- Este clon (`c:\Proyectos\repo`) es distinto del repo principal `c:\Proyectos\Edicion` (que tiene sus propios remotes `origin`=simpliroute-tools produccion CesarClaudio1424 y `pruebas`=pruebassimpli). No confundir cual `origin` es cual segun la carpeta.
- Clonar/hacer fetch requiere el workaround TLS: `git -c http.sslBackend=schannel ...` con sandbox deshabilitado (ver [[reference_tls_workaround_entorno]]).
- Regla de push sigue aplicando aqui tambien: nunca push a `origin` (en este clon, el repo de Brandon) sin instruccion explicita del usuario en el momento.
- **Ojo:** el `master` local de este clon sigue a `pruebas`, no a `origin` — es esencialmente una copia de nuestro propio codigo, NO el proyecto real de Brandon. El codigo real de Brandon (una reescritura completa en Next.js/Supabase) esta en `origin/main`; hay que hacer `git fetch origin` primero (no aparece hasta hacerlo). Detalle completo en [[project_migracion_nextjs_brandon]].
