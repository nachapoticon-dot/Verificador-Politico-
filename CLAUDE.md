@AGENTS.md

## Específico de Claude Code

Entra en plan mode antes de tocar `verificador/veredicto.py`, `prompts.py` o
`agent.py`: son el contrato entre el modelo y la interfaz, y un cambio ahí
rompe tests en cascada. El resto del código admite edición directa.

No declares que algo funciona sin pegar la salida del comando que lo demuestra.
Este proyecto ya tuvo un test que afirmaba como correcto un comportamiento roto
(`test_traza.py` consagrando que `informativo` se convirtiera en
`sin_evidencia`) y una caída total que ninguna prueba detectó.
