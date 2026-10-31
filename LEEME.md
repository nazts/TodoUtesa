# TodoUtesa

App web personal de tareas + pomodoro + seguimiento. Un solo proceso Python, sin
dependencias externas (solo biblioteca estandar), datos en SQLite.

## Arrancar

Windows: doble clic en `Iniciar.bat`.
Linux / VPS / Termux: `sh Iniciar.sh`.

Se abre en `http://127.0.0.1:8630` (si el puerto esta ocupado prueba 8631, 8632...).

## Modulos

| Modulo | Que hace |
|---|---|
| Hoy | Plan del dia, atrasadas y bandeja de tareas sin fecha. Boton "Armar plan" que reparte tus pendientes segun el tiempo que tengas. |
| Tareas | Listado con filtros (pendientes, hoy, semana, atrasadas, hechas, todas) y buscador. Crear, editar, borrar, marcar hecha. |
| Pomodoro | Bloques de 25 / 50 / 15 / 5 ligados a una tarea. Cada bloque guarda minutos reales. |
| Calendario | Vista mes. Clic en un dia para ver y marcar sus tareas. Marcar ahi actualiza la tarea y las metricas. |
| Memoria | Historial de completadas, pendientes y bitacora de bloques de foco. |
| Seguimiento | Semanal y mensual: horas de foco, bloques, cumplimiento, racha, foco por dia, por area y donde invertiste el tiempo. |
| Notas | Captura rapida de apuntes, con buscador, edicion y opcion de ligarlos a una tarea. Tambien por Telegram con `/nota`. |
| Racha | Panel arriba en Hoy: dias seguidos activos, ultimos 7 dias, mejor racha, insignia y meta semanal. |

La vista Tareas separa **Por hacer** (pendiente y sin vencer, o sin fecha) de
**Atrasadas** (vencidas y sin hacer). Las vencidas siguen con estado pendiente,
solo no se mezclan con lo que te toca ahora.

Un dia cuenta para la racha si registras al menos un bloque de foco **o**
marcas una tarea como hecha. Insignias: 3 dias Arrancando, 7 Semana completa,
14 Constante, 30 Imparable.

Todo apunta a la misma base: marcar una tarea en cualquier modulo se refleja en
los demas y en las metricas.

## Nube de la universidad (UTSA / Moodle)

El modulo `moodle.py` entra a `nube.utesa.edu` con tu matricula y cruza CUATRO
fuentes por cada uno de tus cursos, para no dejar nada fuera:

| Fuente | Que aporta |
|---|---|
| `/course/view.php?id=CURSO` | lista completa de actividades del curso y su estado de finalizacion (Hecho / Pendiente) |
| `/mod/assign/index.php?id=CURSO` | tareas con fecha de entrega exacta y **estado de la entrega** (Enviado para calificar / No entregado) |
| `/mod/quiz/index.php?id=CURSO` | cuestionarios con fecha y hora de cierre y nota (**nota vacia = sin intento**) |
| `/calendar/view.php?view=month` | fechas de cierre de HVP, SCORM y foros |

Regla: entra como pendiente todo lo que **no** este entregado ni completado,
sin importar si la fecha ya paso (las atrasadas tambien entran). Lo que aparece
entregado se descarta; si ya estaba en tu lista, se marca como hecho solo
(contador `cerradas`). Cada una entra con:

- titulo limpio (sin el "Vencimiento de" ni el "deberia ser completado")
- fecha de vencimiento
- area = nombre del curso
- estimacion base segun el tipo de actividad
- enlace directo a la actividad (icono "abrir")
- etiqueta **Nube** y `externa_id` unico, asi no se duplica nunca

Corre sola 12 segundos despues de arrancar el servidor y luego cada 6 horas.
Tambien hay boton **Sincronizar** en la vista Tareas.

Entran tambien las **atrasadas**: una tarea no entregada de septiembre sigue
siendo deuda. Una sincronizacion completa tarda ~20 segundos (recorre 7 cursos
y 118 actividades) y corre cada 6 horas.

Si una actividad que ya marcaste hecha aparece entregada en la nube, no se
toca: se respeta tu marca.
Si la universidad cambia la fecha, se actualiza la tarea pendiente.

**Credenciales**: se guardan en `datos/moodle.json` en texto plano, solo en tu
computadora, y el servidor escucha unicamente en 127.0.0.1. No se envian a
ningun otro sitio. Si mas adelante expones la app a internet, hay que cifrarlas
(tarea pendiente de la etapa final).

### Tareas perdidas

Cuando una tarea de la nube ya **no acepta entrega** (Moodle cerro el envio, no
hay boton "Agregar entrega" ni formulario de subida), se marca con
`perdida = 1`. Deja de contar como pendiente y sale en su propio filtro
**Perdidas** en la vista Tareas. Se detecta abriendo la actividad y buscando el
formulario de entrega; si no aparece, esta perdida.

### Tareas parecidas (no duplicar)

Se comparan los titulos con `moodle.similitud` (texto + palabras en comun, los
numeros cuentan). Si escribes a mano una tarea que ya existe en la nube:

- al crearla desde la app o Telegram, te avisa "ya existe #N ..." y no duplica;
- si la creaste antes de la sincronizacion, al sincronizar se **enlaza** a la
  actividad de la nube en vez de crear otra.

## Google Calendar y Google Tasks

Sincronizacion en una sola via: **Habitos -> Google**. Cada tarea con fecha se
crea como evento en tu calendario principal y como tarea en Google Tasks. Si la
editas, completas o borras aqui, alla se refleja. Cada tarea guarda su
`gcal_id` y `gtask_id`, asi nunca se duplica.

### Puesta en marcha (una sola vez)

1. Entra a https://console.cloud.google.com con tu cuenta.
2. Crea un proyecto (o usa uno existente).
3. En **APIs y servicios -> Biblioteca** activa:
   - Google Calendar API
   - Google Tasks API
4. En **APIs y servicios -> Credenciales** -> Crear credenciales ->
   **ID de cliente de OAuth** -> tipo **Aplicacion de escritorio**.
5. Descarga el JSON.
6. En la app: menu lateral -> **Google** -> pega la ruta del JSON -> Cargar.
7. Boton **Autorizar con Google**: se abre Google, apruebas, y vuelve sola.
8. Boton **Sincronizar ahora**.

Si la app esta en modo "Prueba", agrega tu correo en
**Audiencia -> Usuarios de prueba**, si no Google te dara error 403.

### Detalles tecnicos

- OAuth2 con PKCE (S256), cliente de escritorio, redirect
  `http://127.0.0.1:8630/oauth2callback` servido por la misma app.
- Scopes: `calendar.events`, `tasks`, `userinfo.email`.
- El refresh_token se guarda en `datos/google_token.json` (texto plano, solo
  local) y se renueva solo.
- Las tareas sin fecha van solo a Google Tasks (no tienen dia para el evento).
- El evento se marca con prefijo "Hecho: " cuando la tarea se completa.

## Bot de Telegram

1. En Telegram busca **@BotFather** y manda `/newbot`. Copia el token.
2. En la app: menu lateral -> **Telegram** -> pega el token -> Guardar.
3. Abre tu bot y mandale `/start` una sola vez. Queda vinculado a tu chat (solo
   ese chat puede usarlo).

Comandos:

| Comando | Para |
|---|---|
| `/add texto \| manana 15:00` | crear tarea con fecha |
| texto suelto | se guarda como tarea (rapido) |
| `/hoy` | lo de hoy + atrasadas |
| `/pendientes` | todo lo pendiente |
| `/perdidas` | las que ya no aceptan entrega |
| `/hecho 12` | marcar hecha |
| `/agendar 12 2026-11-05 18:00` | cambiar fecha |
| `/pomo 12 25` | registrar bloque de foco |
| `/sync` | sincronizar con la nube |
| `/nota texto` | guardar apunte |
| `/notas` | ultimos apuntes |
| `/buscar texto` | buscar tareas |

El bot corre dentro del mismo proceso (long polling, sin librerias). Tambien
avisa solo cuando la sincronizacion encuentra tareas nuevas.

### Recordatorios automaticos

El bot te escribe **cada 90 minutos** (configurable) con lo que te falta, hasta
que no quede nada pendiente. Reglas:

- Solo dentro de una ventana horaria (por defecto **07:00 a 23:00**), para no
  despertarte.
- Ordena primero las **atrasadas**, despues lo que falta por hacer.
- Trae **botones**: "Listo #48 ..." cierra la tarea de un toque y te dice
  cuantas quedan.
- Se detiene solo cuando no hay pendientes: no molesta por gusto.
- El ultimo envio se guarda en la base, asi reiniciar la app no dispara un
  aviso repetido de golpe.

Se cambia desde la app (menu lateral -> Telegram -> Recordatorios automaticos)
o por chat: `/recordatorio on`, `/recordatorio off`, `/intervalo 45`.

**Importante**: los recordatorios viven dentro del proceso de la app. Si cierras
la app, no hay avisos. Por eso el siguiente paso natural es dejarla corriendo en
el VPS o en el telefono como servidor.

## Estructura

```
servidor.py        backend (http.server + sqlite3), API y estaticos
moodle.py          sincronizacion con la nube de UTSA (4 fuentes)
telegram.py        cliente minimo de Telegram (long polling)
web/index.html     interfaz
web/app.js         logica del cliente
web/app.css        estilos
assets/            Bootstrap 5 + Bootstrap Icons locales (funciona sin internet)
datos/habitos.db   base de datos (se crea sola)
datos/moodle.json  credenciales de la nube (texto plano, solo local)
datos/telegram.json token del bot y chat vinculado
```

## API

| Metodo | Ruta | Para |
|---|---|---|
| GET | /api/resumen | numeros del panel lateral y tarjetas de hoy |
| GET | /api/tareas?filtro=&q=&desde=&hasta= | listar con filtros |
| POST | /api/tareas | crear |
| PUT | /api/tareas/{id} | editar |
| POST | /api/tareas/{id}/estado | marcar hecha / devolver a pendiente |
| DELETE | /api/tareas/{id} | borrar |
| POST | /api/sesiones | registrar bloque de pomodoro |
| GET | /api/sesiones?desde=&hasta= | bitacora |
| GET | /api/metricas?periodo=semana\|mes | seguimiento |
| POST | /api/estimar | estimacion de duracion |

## Respaldo

Copiar `datos/habitos.db`. Eso es todo el estado.

## Estado del proyecto

Funcional completo en local: tareas, pomodoro, calendario, memoria, seguimiento,
notas, nube de UTSA con deteccion de perdidas y enlaces por similitud, y bot de
Telegram.

Pendiente: IA real (DeepSeek) para estimar y para la lectura del periodo,
clave de acceso para usarlo desde fuera, PWA instalable y despliegue en VPS o
Termux con systemd.
