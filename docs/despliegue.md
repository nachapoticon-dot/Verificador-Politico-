# Sacar Faro a internet

Notas de lo que hay que resolver antes de poner Faro en una URL pública. No es
un plan todavía: es el mapa de las minas, sacado de leer el código que hay hoy.

Faro está escrito como aplicación local de un solo proceso, y varias decisiones
buenas para eso son incompatibles con un despliegue. Ninguna es fatal; todas hay
que verlas antes, no después.

## Lo que de verdad bloquea

**Cualquiera puede gastarte el saldo.** `POST /api/verificar` no pide nada:
ni clave, ni sesión, ni límite por IP. Lo único que hay es un semáforo de 4
consultas simultáneas (`server.py`), que protege el proceso pero no la cartera.
Cada consulta cuesta tokens, y "A fondo" costará bastante más cuando exista el
pipeline de razonamiento. Una URL pública sin puerta es una factura abierta al
primer bot que la encuentre. Esto no es dificultad técnica, es exposición: hay
que decidir si Faro es público con límites, o privado con invitación.

**DuckDuckGo desde un centro de datos.** `ddgs` no usa una API con clave:
raspa. Desde una IP residencial aguanta; desde el rango de un proveedor de
nube te bloquean o te limitan mucho antes, y ahí se cae **toda** la cadena de
evidencia — sin búsqueda no hay fuentes, sin fuentes la solidez es 0 y todas
las respuestas salen con aviso. Probablemente sea lo primero que se rompa en
producción, y no lo va a avisar ningún test porque la suite es hermética.
Alternativas a valorar: una API de búsqueda de pago (Brave, Serper, Tavily),
un proxy residencial, o aceptar el bloqueo y apoyarse más en lectura directa.

**Chromium tiene que caber.** `search.py` lanza un navegador real como
respaldo cuando `httpx` no basta. Eso pide alrededor de 1 GB de memoria y un
sistema de ficheros de verdad, así que descarta la mayoría de plataformas
serverless. Va en un contenedor, no en una función.

## Lo que se rompe al escalar a más de un proceso

Tres cosas asumen que hay exactamente una instancia:

- La **caché de lecturas** es un `dict` en memoria (64 entradas, 15 min). Con
  dos réplicas se duplican las descargas y el ahorro desaparece.
- El **semáforo de 4** es por proceso. Dos réplicas son 8 consultas
  simultáneas contra el proveedor, no 4.
- El **hilo propietario de Playwright** es por proceso: cada réplica levanta
  su propio Chromium, con su propio gigabyte.

Mientras Faro sea una instancia, nada de esto importa. En cuanto haya dos, la
caché quiere ser Redis y el límite quiere vivir fuera del proceso.

## Detalles que muerden

**La duración de una petición.** Hoy el tope son 120 s (`server.py`), y el
diseño quiere 180 s para "A fondo". Vercel, Netlify y compañía cortan mucho
antes. Hace falta una plataforma que permita respuestas largas y en streaming:
Fly.io, Railway, Render o un VPS pequeño.

**El SSE no puede ir en búfer.** El servidor ya manda `X-Accel-Buffering: no`,
pero un CDN o un proxy intermedio puede acumular igual y entregar la respuesta
de golpe al final — que es exactamente perder la razón de ser del streaming.
Hay que comprobarlo en la plataforma concreta, no darlo por hecho.

**El disco es efímero.** `fuentes.capturar_propuestas` escribe
`data/propuestas.jsonl` en local. En un contenedor que se recrea, esa cola de
curación se pierde en cada despliegue. O se monta un volumen, o se manda a otro
sitio, o se asume que se pierde.

**La clave no puede venir de donde viene.** `config.py` la busca, como último
recurso, en el `.env.local` del proyecto EdifcIA. Es una comodidad de desarrollo
local que no debe existir en producción: allí solo variable de entorno.

## Por dónde iría

Un contenedor en una plataforma que admita peticiones largas y streaming, con
una puerta delante. En ese orden: primero resolver el acceso y el buscador,
porque sin eso lo demás no importa; después el contenedor; y dejar el escalado
a varias réplicas para cuando haga falta de verdad, que probablemente sea nunca.

Antes de nada conviene medir cuánto cuesta una consulta real de cada preset.
Sin ese número no se puede decidir si Faro es público, y es fácil de obtener:
la API devuelve el uso de tokens en cada respuesta.
