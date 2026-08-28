---
name: project-memoria-skills-versionados
description: ".claude/commands, .claude/skills y .claude/memory ahora se versionan en git para compartir contexto con un colega"
metadata: 
  node_type: memory
  type: project
  originSessionId: 7e965f0d-229f-4493-af9c-505816a8c921
  modified: 2026-08-28T00:14:55.476Z
---

Cesar quiere trabajar el repo simpliroute-tools/pruebassimpli en colaboracion con un colega desde otra computadora, usando la misma cuenta de Claude. Como parte de ese plan (2026-08-27) se ajusto `.gitignore`: en vez de excluir toda `.claude/`, ahora excluye `.claude/*` y desbloquea explicitamente `.claude/commands/`, `.claude/skills/` y `.claude/memory/`. `.claude/settings.json` y `.claude/settings.local.json` siguen ignorados (tienen tokens reales, ver [[reference_claude_settings_tokens_acumulados]]).

Se copio el contenido de memoria (`MEMORY.md` + memory/*.md, incluido `user_test_token.md` con un token real — Cesar decidio explicitamente sincronizarlo tal cual por ser una cuenta de pruebas de bajo riesgo) a `.claude/memory/` dentro del repo, y se configuro `autoMemoryDirectory` en `.claude/settings.local.json` (local, no versionado) apuntando a esa carpeta.

**Por que importa:** el objetivo es que el contexto/memoria de Claude sea el mismo sin importar desde que maquina se trabaje, sin exponer secretos en el repo publico ni compartir credenciales de sesion.

**Como aplicar:**
- El setting `autoMemoryDirectory` **no viaja con git** (vive en settings.local.json) — cada persona (Cesar en otra maquina, o el colega al clonar) debe configurarlo el mismo en su propio settings.local.json apuntando a la ruta absoluta de `.claude/memory` en su clon.
- Este mecanismo (`autoMemoryDirectory`) fue reportado por un agente de investigacion pero **no se verifico en vivo dentro de esta sesion** (requiere reiniciar Claude Code para confirmar que efectivamente lee/escribe memoria desde la nueva ruta). Verificar tras reiniciar antes de asumir que funciona.
- Se decidio NO compartir el historial crudo de conversaciones (transcripts completos) via git — solo esta memoria curada. Ver tambien [[reference_datamart_mcp]] para el estilo de las memorias de referencia existentes.
- Origin (simpliroute-tools) y pruebas (pruebassimpli) son el mismo repo local con dos remotes que divergieron; no se hizo (ni hace falta) un merge de historiales tipo repos-independientes.
