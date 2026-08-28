---
name: reference-claude-settings-tokens-acumulados
description: .claude/settings.json y settings.local.json acumulan tokens de API en texto plano en el allowlist de permisos
metadata: 
  node_type: memory
  type: reference
  originSessionId: 7e965f0d-229f-4493-af9c-505816a8c921
  modified: 2026-08-28T00:14:43.051Z
---

`.claude/settings.json` y `.claude/settings.local.json` (locales, no versionados) acumulan tokens de API de SimpliRoute — y en un caso un Personal Access Token de GitHub — en texto plano, embebidos en los patrones de comandos permitidos (`Bash(curl ... Authorization: Token ...)`) de sesiones de trabajo pasadas.

**Por que importa:** simpliroute-tools y pruebassimpli son repos **publicos**. El `.gitignore` excluye `.claude/*` y solo desbloquea explicitamente `.claude/commands/`, `.claude/skills/` y `.claude/memory/` (ver [[project_memoria_skills_versionados]]). Si esa exclusion se relaja de forma amplia (`git add -f .claude/`, borrar la regla `.claude/*`, etc.) estos archivos se commitean y los tokens quedan expuestos publicamente. Tambien: si se copia la carpeta `.claude/` completa a la maquina de un colega en vez de que cada quien tenga su propio `settings.local.json`, el colega hereda credenciales personales de Cesar sin saberlo.

**Como aplicar:** nunca ampliar las excepciones del `.gitignore` para incluir `settings.json`/`settings.local.json` sin antes limpiar los tokens del allowlist. Ver tambien [[reference_tls_workaround_entorno]] — el PAT de GitHub embebido en la URL del remote esta expirado, pero el patron de fondo (credenciales embebidas en config local) se repite y conviene tenerlo presente.
