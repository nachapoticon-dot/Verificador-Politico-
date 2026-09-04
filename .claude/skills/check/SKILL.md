---
name: check
description: Ejecuta la puerta de verificación completa de Faro — pytest del backend y contratos SSE, lint y build del frontend. Úsalo antes de dar por terminado cualquier cambio.
disable-model-invocation: true
allowed-tools: Bash
---

Corre las dos puertas, en este orden, y no te detengas en la primera que falle:
necesitas el cuadro completo.

```bash
.venv/bin/python -m pytest -q
cd frontend && npm run check
```

`npm run check` encadena los contratos SSE, oxlint y el build de producción.

Si `npm install` nunca se corrió en esta máquina, `frontend/node_modules` no
existe y `npm run check` falla por ahí, no por el código. Instala primero.

**Estado esperado: todo verde.**

Al terminar, pega la salida real de ambos comandos. No resumas "todo bien" sin
mostrarla: en este proyecto ya hubo una caída total que ninguna prueba detectó y
un test que afirmaba como correcto un comportamiento roto.

Si algo falla, arréglalo y vuelve a correr las dos puertas enteras.
