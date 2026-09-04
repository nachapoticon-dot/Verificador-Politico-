@AGENTS.md

## Específico de Claude Code

Entra en plan mode antes de tocar `verificador/veredicto.py`, `prompts.py` o
`agent.py`: son el contrato entre el modelo y la interfaz, y un cambio ahí
rompe tests en cascada. El resto del código admite edición directa.

No declares que algo funciona sin pegar la salida del comando que lo demuestra.
Este proyecto ya tuvo un test que afirmaba como correcto un comportamiento roto
(`test_traza.py` consagrando que `informativo` se convirtiera en
`sin_evidencia`) y una caída total que ninguna prueba detectó.

Ejecuta el código para comprobar lo que afirmas. Los cinco defectos serios de
la última tanda —claves paraguas que colaban la oficina de prensa de un
gobierno como fuente oficial, `OverflowError` con `max_resultados: Infinity`,
dos fuentes desinformadoras llevando la solidez al techo— salieron todos de
revisores que llamaron a la función, no de revisores que la leyeron.

## Faro va a salir a internet

Todavía no hay fecha, pero el destino es una URL pública, así que **cada
decisión de diseño debería preguntarse si sobrevive fuera de este portátil**.
El análisis completo está en `docs/despliegue.md`; lo que hay que tener en la
cabeza al escribir código hoy:

**No añadas más estado de proceso.** La caché de lecturas, el semáforo de 4 y
el hilo propietario de Chromium ya asumen que hay una sola instancia. Son
decisiones correctas hoy y deuda el día que haya dos réplicas. Si necesitas
estado nuevo, piensa antes si puede vivir fuera del proceso.

**No des por hecho el disco.** Escribir en el sistema de ficheros local
(`data/propuestas.jsonl` ya lo hace) se pierde en cada despliegue de un
contenedor.

**Cuidado con lo que cuesta y con lo que tarda.** Hoy no hay autenticación ni
límite por IP: una URL pública sin puerta es una factura abierta. Y el tope de
petición son 120 s, mientras el diseño quiere 180 s para "A fondo" — cualquier
cosa que alargue una consulta acerca ese techo.

**La búsqueda es el eslabón frágil.** `ddgs` raspa DuckDuckGo sin clave; desde
un centro de datos eso se bloquea mucho antes que desde casa, y sin búsqueda no
hay evidencia y todas las respuestas salen con aviso. Si tocas `search.py`, deja
la puerta abierta a cambiar de buscador sin cirugía.
