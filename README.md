# TodoUtesa

Gestor de tareas personales con **Pomodoro**, **calendario**, **racha**,
**notas**, sincronizacion con la **nube de UTESA (Moodle)**, **bot de Telegram**
y **Google Calendar / Google Tasks**.

Hecho para el dia a dia de un estudiante que trabaja: las tareas se traen solas
de la plataforma, se avisan por Telegram cada 90 minutos y todo corre en Python
sin instalar ni una libreria.

**Instalacion paso a paso (Windows, Android/Termux, Linux, macOS, VPS) ->
[INSTALACION.md](INSTALACION.md)**

## Lo que hace

| Modulo | Que resuelve |
|---|---|
| **Hoy** | Plan del dia, atrasadas y bandeja de tareas sin fecha. Boton "Armar plan" que reparte pendientes segun el tiempo que tengas |
| **Tareas** | Filtros (por hacer, hoy, semana, atrasadas, perdidas, hechas), buscador, prioridad, area, fecha, hora, estimado |
| **Pomodoro** | Bloques de 25/50/15/5 ligados a una tarea, con minutos reales guardados |
| **Calendario** | Vista mes; marcar una tarea ahi actualiza todo lo demas |
| **Memoria** | Historial de lo hecho, lo pendiente y la bitacora de foco |
| **Seguimiento** | Semana y mes: horas de foco, cumplimiento, racha, por area |
| **Notas** | Captura rapida con buscador y opcion de ligarlas a una tarea |
| **Racha** | Dias seguidos activos, ultimos 7 dias, record e insignias |
| **Nube UTESA** | Entra a Moodle y trae tareas, cuestionarios, foros y recursos pendientes, cruzando 4 fuentes |
| **Telegram** | Comandos para agendar, cerrar y consultar; avisos automaticos con botones |
| **Google** | Cada tarea con fecha se vuelve evento en Calendar y tarea en Tasks |

## Por que no necesita dependencias

Backend en **Python 3 estandar** (`http.server` + `sqlite3` + `urllib`), sin
Flask, sin requests, sin ORM. El frontend es HTML + Bootstrap servido desde
`assets/` (sin CDN, funciona sin internet). Eso lo hace portable a Windows,
Linux, macOS, VPS y Termux sin `pip install`.

## Arrancar

### Windows
Doble clic en `Iniciar.bat`.

### Linux / macOS / VPS
```bash
sh arrancar.sh
```

### Termux (Android)
```bash
pkg update && pkg install -y python
cd TodoUtesa
sh arrancar.sh
```
Para que no se detenga al bloquear el telefono:
```bash
termux-wake-lock
```
Y si quieres que arranque solo al encender, copia
`deploy/termux-inicio.sh` a `~/.termux/boot/`.

### VPS con systemd
```bash
sudo cp deploy/todoutesa.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now todoutesa
```

Se abre en `http://127.0.0.1:8630` (si el puerto esta ocupado prueba 8631, 8632...).

## Acceso desde el telefono o desde fuera

1. Menu lateral -> **Servidor**.
2. Pon una **clave de acceso** (obligatoria para abrir a la red).
3. Activa **"Permitir acceso desde otros equipos"**.
4. Reinicia la app y abre desde el telefono la direccion que te muestra
   (algo como `http://192.168.1.50:8630`).

Sin clave no deja abrirlo a la red, a proposito. Para internet abierto hace
falta ademas un tunel o un proxy con HTTPS (Tailscale, Cloudflare Tunnel,
Nginx + Let's Encrypt).

## Conectar la nube de UTESA

Menu lateral -> **Tareas** -> **Credenciales** de la barra de la nube. Pide
recinto, matricula y contrasena. El modulo cruza:

| Fuente | Que aporta |
|---|---|
| `/course/view.php?id=CURSO` | todas las actividades y su estado de finalizacion |
| `/mod/assign/index.php?id=CURSO` | fecha de entrega y estado de la entrega |
| `/mod/quiz/index.php?id=CURSO` | cierre y nota (nota vacia = sin intento) |
| `/calendar/view.php` | fechas de cierre de HVP, SCORM y foros |

Entra todo lo que **no** este entregado, incluidas las **atrasadas**. Lo que ya
entregaste se cierra solo en la app. Las actividades que Moodle ya no deja
entregar van a **Perdidas**. Si escribes una tarea que ya existe en la nube, la
enlaza en vez de duplicarla (comparacion de titulos con `moodle.similitud`).

## Bot de Telegram

1. `@BotFather` -> `/newbot` -> copia el token.
2. App -> **Telegram** -> pega el token.
3. Abre tu bot y manda `/start` una vez.

| Comando | Para |
|---|---|
| texto suelto | se guarda como tarea |
| `/add texto \| manana 15:00` | tarea con fecha |
| `/hoy`, `/pendientes`, `/atrasadas`, `/perdidas` | listas con `#id` |
| `/hecho 12` | cerrar tarea |
| `/agendar 12 2026-11-05 18:00` | cambiar fecha |
| `/pomo 12 25` | registrar bloque de foco |
| `/sync` | sincronizar la nube |
| `/nota texto`, `/notas` | apuntes |
| `/racha` | como va la racha |
| `/recordatorio on\|off` | avisos automaticos |
| `/intervalo 90` | cada cuanto avisa |

Los recordatorios salen cada 90 minutos (configurable), de 7:00 a 23:00, con
botones para cerrar la tarea de un toque. Se apagan solos cuando no queda nada
pendiente.

## Google Calendar y Google Tasks

Una sola via: TodoUtesa -> Google. Requiere un OAuth client de tipo
**Desktop app** creado en Google Cloud (instrucciones dentro de la app, boton
**Google**). El token se renueva solo.

## Datos y respaldo

Todo el estado es un archivo: `datos/todoutesa.db` (SQLite). Copiarlo es todo el
respaldo. En `datos/` tambien viven las credenciales locales
(`moodle.json`, `telegram.json`, `google_token.json`), que **no se suben al
repositorio** (ver `.gitignore`).

## API

| Metodo | Ruta |
|---|---|
| GET | `/api/resumen`, `/api/racha`, `/api/apuntes`, `/api/moodle`, `/api/telegram`, `/api/recordatorios`, `/api/google` |
| GET | `/api/tareas?filtro=por_hacer\|hoy\|semana\|atrasadas\|perdidas\|hechas\|todas&q=` |
| POST | `/api/tareas`, `/api/tareas/{id}/estado`, `/api/sesiones`, `/api/estimar`, `/api/apuntes` |
| PUT / DELETE | `/api/tareas/{id}`, `/api/apuntes/{id}` |
| POST | `/api/moodle/config`, `/api/moodle/sync`, `/api/telegram/config`, `/api/google/sync` |

## Estructura

```
servidor.py    backend, API, autenticacion y estaticos
moodle.py      sincronizacion con Moodle (4 fuentes + similitud)
telegram.py    cliente minimo de Telegram (long polling)
google_sync.py OAuth2 PKCE + Calendar + Tasks
web/           index.html, app.js, app.css
assets/        Bootstrap 5 e iconos, locales
datos/         base de datos y credenciales (ignorado por git)
deploy/        unidad systemd y arranque en Termux
```

## Licencia

MIT.
