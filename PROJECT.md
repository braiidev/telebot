# HomeBot

Chatbot de Telegram con interfaz web para mensajería individual, gestión de contactos, multimedia, notificaciones en tiempo real y popups de escritorio.

## Stack

- **Python 3.13+**
- **Flask** — API REST + SSE (Server-Sent Events)
- **python-telegram-bot v21** — polling + envío de mensajes
- **SQLite3** — persistencia (WAL mode)
- **tkinter** — popups de escritorio nativos

## Arquitectura

```
app.py (entry point)
├── Hilo principal: bot.run()
│   └── Telegram polling (solo mensajes privados)
├── Hilo daemon: start_flask()
│   └── Flask: API REST + SSE (2 endpoints separados)
│
├── db.py → SQLite (homebot.db)
│   ├── contacts      — telegram_id, name, username, alias, blocked
│   ├── messages      — id, contact_id, text, sender, file_*, reply_to_msg_id, telegram_msg_id
│   ├── chat_state    — contact_id, last_read_msg_id
│   └── prefs         — key/value (notif_mode, etc.)
│
├── notifier.py       — Popups de escritorio via tkinter (SSE listener)
├── templates/
│   └── index.html    — SPA vanilla JS (chat + contactos + modal + notificaciones)
├── static/
│   └── style.css     — Tema Lux + editor de tema, iconos SVG
├── data/
│   ├── audio/        — Archivos de audio (.mp3, .ogg, .wav, etc.)
│   ├── video/        — Archivos de video (.mp4, .webm, .mov, etc.)
│   ├── image/        — Imágenes (.jpg, .png, .gif, etc.)
│   ├── document/     — Documentos (.pdf, .doc, .zip, .txt, etc.)
│   └── avatars/      — Fotos de perfil de contactos ({id}.jpg)
├── .env              — TOKEN, HOST, PORT, DEBUG
├── requirements.txt  — python-telegram-bot, Flask, python-dotenv
└── PROJECT.md        — Esta documentación
```

### Flujo de datos

**Telegram → Web (alguien escribe al bot):**
1. Bot recibe mensaje privado → `_handle_message()`
2. Auto-registra al remitente como contacto (upsert en `contacts`)
3. Descarga avatar si no existe
4. Convierte OGG→MP3 si es audio
5. Guarda mensaje en DB (`sender='them'`)
6. Broadcast SSE (`_broadcast(msg)`) → frontend actualiza

**Web → Telegram (respondes desde la web):**
1. `POST /api/send/<contact_id>` con texto
2. `bot.send_message()` programa el envío via `run_coroutine_threadsafe()`
3. Captura `message_id` de la respuesta de Telegram → `telegram_msg_id`
4. Guarda en DB (`sender='me'`)
5. Broadcast SSE

## API REST

| Método | Ruta | Descripción | Body |
|--------|------|-------------|------|
| GET | `/` | Interfaz web | — |
| GET | `/api/contacts` | Lista contactos (incluye `avatar: bool`, `unread_count`) | — |
| POST | `/api/contacts` | Añadir contacto | `{telegram_id, name?, username?, alias?}` |
| PUT | `/api/contacts/:id` | Editar contacto | `{name?, alias?, blocked?}` |
| DELETE | `/api/contacts/:id` | Eliminar contacto + mensajes | — |
| GET | `/api/messages/:contact_id` | Historial (incluye datos del mensaje reply) | — |
| DELETE | `/api/messages/:contact_id` | Borrar solo mensajes (no el contacto) | — |
| POST | `/api/send/:contact_id` | Enviar mensaje | `{text, reply_to_msg_id?}` |
| POST | `/api/upload/:contact_id` | Subir archivo | `multipart: file + caption? + reply_to_msg_id?` |
| POST | `/api/read/:contact_id` | Marcar como leído | `{msg_id}` |
| GET | `/api/events` | SSE para el browser (cuenta conexiones) | — |
| GET | `/api/notifier/events` | SSE para el notifier (no cuenta) | — |
| POST | `/api/notifier/mode` | Cambiar modo de notificación | `{mode}` |
| GET | `/api/notifier/status` | Estado + modo actual | — |
| GET | `/data/<path>` | Servir archivos (audio, video, imagen, etc.) | — |
| POST | `/api/data/clean` | Limpiar archivos | `{type: "all"|"audio"|"video"|"image"|"document"}` |
| GET | `/api/data/info` | Estadísticas de archivos por carpeta | — |

### SSE — Server-Sent Events

- `/api/events`: El navegador se conecta aquí. Cada conexión incrementa `_sse_count`. El servidor usa esto para saber si hay al menos un browser abierto.
- `/api/notifier/events`: El notifier de escritorio se conecta aquí. NO afecta `_sse_count`, evitando loops infinitos.
- Ambos emiten un comentario vacío (`:\n\n`) al abrir la conexión para forzar `onopen` en el navegador.

### 404

- Rutas que empiezan con `/api/` → responden con `{"error": "..."}` JSON.
- Otras rutas → redirigen a `/?error=Ruta+inexistente` y muestran un `alert()`.

### DEBUG mode

Si `DEBUG=true` en `.env`, Flask se inicia en modo debug (NO usar en producción).

## Base de datos

### contacts

| Columna | Tipo | Descripción |
|---------|------|-------------|
| telegram_id | INTEGER PK | ID de Telegram |
| name | TEXT | Nombre real (full_name) |
| username | TEXT | @username (nullable) |
| alias | TEXT | Apodo personalizado (nullable) |
| blocked | INTEGER | 0=activo, 1=bloqueado |
| created_at | TEXT | Fecha de registro |

### messages

| Columna | Tipo | Descripción |
|---------|------|-------------|
| id | INTEGER PK | Autoincrement |
| contact_id | INTEGER FK | → contacts(telegram_id) |
| text | TEXT | Contenido del mensaje |
| sender | TEXT | `me`, `them` o `bot` |
| from_user | TEXT | Nombre visible del remitente |
| file_type | TEXT | `audio`, `video`, `image`, `document` (nullable) |
| file_path | TEXT | Ruta relativa al archivo en `data/` (nullable) |
| file_name | TEXT | Nombre original del archivo (nullable) |
| file_size | INTEGER | Tamaño en bytes (nullable) |
| reply_to_msg_id | INTEGER | → messages(id) del mensaje al que responde (nullable) |
| telegram_msg_id | INTEGER | `message_id` de Telegram (para lookup de replies) |
| created_at | TEXT | Timestamp |

### chat_state

| Columna | Tipo | Descripción |
|---------|------|-------------|
| contact_id | INTEGER PK FK | → contacts(telegram_id) |
| last_read_msg_id | INTEGER | ID del último mensaje leído |

### prefs

| Columna | Tipo | Descripción |
|---------|------|-------------|
| key | TEXT PK | Clave de preferencia |
| value | TEXT | Valor |

## Sistema de notificaciones

### 4 modos (campana en el header del navegador)

| Modo | Label | Sonido (Web Audio API) | Push (Notification API) | Notifier escritorio |
|------|-------|:----------------------:|:-----------------------:|:-------------------:|
| `all` | Sonido + Push | ✅ | ✅ | — |
| `push` | Solo Push | — | ✅ | — |
| `sound` | Solo Sonido | ✅ | — | — |
| `none` | Desactivado | — | — | — |

### Auto-start/stop del notifier de escritorio

El servidor decide cuándo iniciar/detener `telebot-notifier.service` usando **heartbeats** en lugar de conexiones SSE:

| Visibilidad del browser | Último heartbeat | Modo | Notifier |
|------------------------|-----------------|------|----------|
| Visible | < 30s | cualquiera ≠ none | **STOP** |
| Oculta o sin heartbeat | > 30s | cualquiera ≠ none | **START** |
| Cualquiera | cualquiera | `none` | **STOP** |

### Cómo funciona
1. El navegador envía un heartbeat (`POST /api/heartbeat`) cada 10 segundos con `{visible: true/false}`.
2. Al cambiar de pestaña o minimizar (`visibilitychange`), envía un heartbeat inmediato.
3. Al abrir la página, envía un heartbeat inicial con la visibilidad actual.
4. El servidor compara la última marca de tiempo: si pasaron más de 30s sin heartbeat, asume que no hay browser.
5. Un hilo de barrido ejecuta `_sync_notifier()` cada 15s para mantener el estado correcto.
6. Cada vez que llega un mensaje (`_broadcast`), también se verifica el estado del notifier.

### Notifier de escritorio (notifier.py)

- Servicio systemd que se conecta a `/api/notifier/events`
- Cuando llega un mensaje de `them` o `bot`, muestra un popup **tkinter**:
  - Sin barra de título (overrideredirect)
  - Posición: abajo a la derecha
  - Muestra: remitente + texto (truncado a 80 chars)
  - Botón **"Abrir"**: abre `http://localhost:8080/?contact=TELEGRAM_ID` en el browser
  - Botón **"Cerrar"**: descarta el popup
  - Auto-cierre: 8 segundos
  - Debounce: 3 segundos entre popups

### Parámetro `?contact=X` en la URL

Al abrir la página, si la URL contiene `?contact=TELEGRAM_ID`, el frontend selecciona automáticamente ese contacto y abre su chat. Esto es usado por el notifier para que al hacer clic en "Abrir" se abra directamente el chat del mensaje.

### ¿Por qué el notifier no arranca al cerrar las pestañas?

ChromeOS mantiene las pestañas en segundo plano (sesión restaurada) incluso sin ventanas visibles. Antes esto impedía que el notifier arrancara porque usábamos conexiones SSE. **Ahora está resuelto**: el servidor usa heartbeats + Page Visibility API. Al cambiar de pestaña o minimizar la ventana, el navegador envía un heartbeat con `visible=false` y el notifier arranca al instante — incluso con pestañas abiertas en segundo plano.

## Interfaz web (SPA)

### Layout

- **Chat** (75% izquierda): mensajes con avatar, reply, archivos multimedia, placeholder cuando no hay chat activo
- **Contactos** (25% derecha): lista con avatar, nombre, último mensaje, badge de no-leídos, filtro de búsqueda
- **Header**: título + botones (tema, personalizar, datos, notificaciones)

### Funcionalidades

- **Tema dark/light**: Toggle con colores Lux (Nunito Sans)
- **Editor de tema personalizado**: Color pickers + slider de tamaño de fuente, persistido en localStorage (`hb-custom-theme`)
- **Emoji picker**: Panel que se togglea con botón 😊
- **Reply a mensajes**: Hover → botón de reply → barra "Respondiendo" sobre el input → mensaje enviado incluye `reply_to_msg_id` → el mensaje se muestra con borde izquierdo rojo y referencia clickeable
- **Dropdown ...** en chat activo: Editar contacto, Archivar, Eliminar chat (borra solo mensajes), Borrar contacto (borra todo)
- **Modal de contacto**: Editar nombre, alias, bloquear/desbloquear, borrar contacto
- **Data manager** (icono DB en header): Estadísticas por carpeta, checkboxes, limpieza selectiva
- **Spinner de carga**: Animación en botón de enviar mientras se sube archivo
- **Notificaciones**: Sonido (Web Audio API, 880 Hz beep 0.2s), Push (Notification API con nombre del contacto)
- **Error**: `?error=` en URL se muestra via `alert()` al cargar la página

### Multimedia

- **Audio**: Reproductor HTML5 (`<audio>`) con controles
- **Video**: Reproductor HTML5 (`<video>`) con controles
- **Imagen**: Vista previa inline, click para abrir en nueva pestaña
- **Documento**: Link de descarga con nombre e ícono por tipo
- **OGG→MP3**: El bot convierte OGG Opus a MP3 via ffmpeg al recibir audio
- **Archivos eliminados**: Muestran "[Archivo eliminado: nombre]" con emoji según tipo (🎵🎬📷📄)

### Gestión de contactos

- Auto-registro al recibir mensaje privado
- Búsqueda/filtro en sidebar
- Badge de mensajes no leídos (oculto cuando el chat está activo)
- Alias personalizado (se muestra en lugar del nombre real)
- Bloqueo: contacto atenuado con ícono SVG de círculo tachado
- Orden: por fecha del último mensaje (más reciente arriba)

## CLI: comando `telebot`

Comando global instalado en `/usr/local/bin/telebot` para gestionar servicios systemd:

```bash
telebot status                  # Estado del bot + Flask
telebot start                   # Iniciar bot
telebot stop                    # Detener bot
telebot restart                 # Reiniciar bot
telebot enable                  # Habilitar autostart al iniciar sesión
telebot disable                 # Deshabilitar autostart
telebot logs                    # Ver logs en tiempo real (journalctl -f)

telebot notifier status         # Estado del notifier de escritorio
telebot notifier start          # Iniciar notifier manualmente
telebot notifier stop           # Detener notifier manualmente
telebot notifier restart        # Reiniciar notifier
telebot notifier enable         # Habilitar autostart
telebot notifier disable        # Deshabilitar autostart
```

### Auto-start al encender el PC

El servicio `telebot` arranca automáticamente al boot gracias a `loginctl enable-linger`. No necesitás abrir una terminal Penguin para que funcione.

Si por algún motivo no arranca, verificá:
```bash
loginctl show-user $USER | grep Linger    # Debería decir "yes"
systemctl --user is-enabled telebot        # Debería decir "enabled"
telebot status                             # Debería estar active (running)
```

### Systemd user services

| Servicio | Archivo | Descripción |
|----------|---------|-------------|
| `telebot.service` | `~/.config/systemd/user/telebot.service` | Bot + Flask, `Restart=always` |
| `telebot-notifier.service` | `~/.config/systemd/user/telebot-notifier.service` | Notifier, arranca/para automáticamente |

- Los servicios son **user services** (no requieren sudo).
- `telebot.service` tiene `Restart=always` para recuperarse del error `TimedOut` en el polling de Telegram.
- `telebot-notifier.service` se auto-gestiona: el servidor Flask lo inicia/detiene según conexiones SSE.

## Notas técnicas

- **Event loop compartido**: `bot.py` mantiene un event loop único. `send_message()` programa envíos via `run_coroutine_threadsafe()` para evitar corrupción de conexiones httpx.
- **Auto-registro**: Cuando alguien escribe al bot en privado, se registra automáticamente como contacto con su `full_name` y `username`.
- **No-leídos**: Cada contacto tiene `last_read_msg_id` en `chat_state`. La query de contactos cuenta mensajes con `sender='them'` mayores a ese id.
- **Reply lookup**: El bot resuelve `reply_to_message.message_id` buscando por `telegram_msg_id` en DB (no por texto). `save_message()` retorna datos del mensaje reply via JOIN para SSE inmediato.
- **OGG→MP3**: ffmpeg convierte OGG Opus a MP3 al recibir audio. El .ogg original se elimina.
- **Avatares**: Se descargan automáticamente de Telegram al recibir el primer mensaje de un contacto. Guardados en `data/avatars/{id}.jpg`.
- **SSE inicial** `:\n\n`: Comentario vacío al abrir conexión para que el navegador dispare `onopen` inmediatamente.
- **SSE chunked encoding bug**: `http.client.HTTPResponse.read(4096)` no retorna datos en respuestas chunked cuando el chunk es pequeño (e.g., 3 bytes del keepalive). `_safe_read()` en CPython lee `min(amt, 1MB)` bytes de una vez y se bloquea si la respuesta tiene menos datos. Solución: el `notifier.py` lee **byte a byte** (`response.read(1)`) en lugar de bloques de 4096.
- **Thread safety**: Todas las operaciones sobre `_sse_queues` usan `_sse_lock`.
- **404**: Las rutas `/api/*` devuelven JSON; las demás redirigen a `/?error=...` con `alert()`.
- **DB migrations**: `ALTER TABLE ... ADD COLUMN` con `except` pasivo para compatibilidad con DBs existentes.
- **localStorage seguro**: Todo acceso a localStorage está envuelto en try-catch para soportar navegación privada.
