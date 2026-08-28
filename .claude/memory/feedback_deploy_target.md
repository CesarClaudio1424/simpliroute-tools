---
name: Confirmar antes de deploy
description: Siempre pedir confirmacion explicita antes de hacer push, incluso si el usuario especifica destino
type: feedback
---

Siempre pedir confirmación explícita antes de hacer push a cualquier repo, incluso cuando el usuario especifica el destino.

**Why:** El usuario quiere revisar y aprobar cada deploy antes de que se ejecute — no asumir que "deploya" significa hacerlo de inmediato.
**How to apply:** Después de hacer commit, mostrar un resumen de lo que se va a pushear y a dónde (pruebas, producción o ambos), y esperar confirmación antes de ejecutar `git push`.
