# HomeBot

Chatbot de Telegram con interfaz web para mensajería individual, gestión de contactos, persistencia y notificaciones en tiempo real.

## Stack

- **Python 3.13+**
- **Flask** — API REST + SSE
- **python-telegram-bot v21** — polling + envío de mensajes
- **SQLite3** — persistencia (WAL mode)

## Estado actual

Se descartó el modo grupal. El bot ahora funciona exclusivamente en **chat individual (privado)**. Cada persona que le escribe al bot se auto-registra como contacto. La web permite gestionar contactos, chatear con ellos en tiempo real, y ver el historial.

## Arquitectura

```
app.py (entry point)
├── Hilo principal: bot.run()
│   └── Telegram polling (solo mensajes privados)
├── Hilo daemon: start_flask()
│   └── Flask: API REST + SSE
│
├── db.py → SQLite (homebot.db)
│   ├── contacts      — telegram_id, name, username, alias, blocked
│   ├── messages      — id, contact_id, text, sender (me/them/bot), from_user
│   └── chat_state    — contact_id, last_read_msg_id
│
├── templates/index.html  — SPA vanilla JS (3 paneles)
└── static/style.css       — Tema Lux + editor de tema, iconos SVG
```

### Flujo de datos

**Telegram → Web (alguien escribe al bot):**
1. Bot recibe mensaje privado → `_handle_message()`
2. Auto-registra al remitente como contacto (upsert)
3. Guarda mensaje en DB (`sender='them'`)
4. Broadcast SSE → frontend actualiza la lista de contactos y el chat activo

**Web → Telegram (respondes desde la web):**
1. `POST /api/send/<contact_id>` con el texto
2. `bot.send_message()` envía a Telegram (usa `run_coroutine_threadsafe` sobre el event loop del bot)
3. Guarda en DB (`sender='me'`)
4. Broadcast SSE

## API REST

| Método | Ruta | Descripción | Body |
|--------|------|-------------|------|
| GET | `/` | Interfaz web | — |
| GET | `/api/contacts` | Lista contactos (incluye campo `avatar: bool`) | — |
| POST | `/api/contacts` | Añadir contacto | `{telegram_id, name?, username?, alias?}` |
| PUT | `/api/contacts/:id` | Editar contacto | `{name?, alias?, blocked?}` |
| DELETE | `/api/contacts/:id` | Eliminar contacto y sus mensajes | — |
| GET | `/api/messages/:contact_id` | Historial de mensajes (incluye `reply_to_msg_id` y datos del mensaje referenciado) | — |
| POST | `/api/send/:contact_id` | Enviar mensaje | `{text, reply_to_msg_id?}` |
| POST | `/api/read/:contact_id` | Marcar como leído | `{msg_id}` |
| GET | `/api/events` | SSE — notificaciones en tiempo real | — |
| GET | `/data/<path>` | Sirve archivos (audio, video, imagen, avatar, etc.) | — |

## Estructura

```
telebot/
├── app.py              # Flask: endpoints REST + SSE
├── bot.py              # Bot Telegram: polling privado + send_message()
├── db.py               # SQLite: contacts, messages, chat_state
├── data/
│   ├── audio/          # Archivos de audio
│   ├── video/          # Archivos de video
│   ├── image/          # Imágenes
│   ├── document/       # Documentos
│   └── avatars/        # Fotos de perfil de contactos
├── templates/
│   └── index.html      # SPA: chat (75%) + contactos (25%) + modal
├── static/
│   └── style.css       # Tema Lux + editor de tema, iconos SVG
├── .env                # TOKEN, HOST, PORT
├── requirements.txt    # Dependencias
└── PROJECT.md          # Documentación
```

## Instalación y uso

```bash
pip install -r requirements.txt
# Configurar TOKEN en .env
python3 app.py
# Abrir http://localhost:8080
```

## Notas técnicas

- **Event loop compartido**: `bot.py` mantiene un event loop único. `send_message()` programa los envíos sobre ese loop via `run_coroutine_threadsafe()`.
- **Auto-registro**: Cuando alguien escribe al bot en privado, se registra automáticamente como contacto con su `full_name` y `username`.
- **No-leídos**: Cada contacto tiene un `last_read_msg_id` en `chat_state`. La query de contactos cuenta los mensajes con `sender='them'` mayores a ese id.
- **Bloqueo**: Contactos bloqueados (`blocked=1`) se muestran atenuados. El bot igual recibe sus mensajes (para no perder datos), pero la UI los marca.
- **SSE**: El endpoint de eventos emite un comentario vacío (`:\n\n`) al abrir la conexión para que el navegador dispare `onopen` de inmediato.
- **Alias**: Cada contacto puede tener un alias personalizado que se muestra en la lista en lugar del nombre real.
- **Iconos profesionales**: Todos los botones de la interfaz (tema, personalizar, datos, emojis, adjuntar) usan iconos SVG inline con estilo Lux, reemplazando los emojis anteriores. Solo los placeholders de "no disponible" en archivos eliminados conservan emojis como indicadores visuales.
- **Bloqueo visual**: Contactos bloqueados muestran un ícono SVG de círculo tachado (color danger) en lugar del emoji 🚫.
- **Fotos de perfil**: Cuando un contacto envía un mensaje, el bot descarga su foto de perfil de Telegram y la guarda en `data/avatars/{id}.jpg`. La UI la muestra en la lista de contactos y el header del chat. Si no tiene foto, se muestra la inicial del nombre.
- **Auto-scroll**: Al abrir un chat, la vista se posiciona en el último mensaje. Si hay imágenes cargando, se re-posiciona automáticamente al terminar.
- **Reply a mensajes**: Cada mensaje tiene un botón de responder (SVG de flecha) que aparece al hover. Al hacer clic, se muestra una barra "Respondiendo" sobre el input. El mensaje enviado incluye `reply_to_msg_id`. Los mensajes que son respuestas muestran el mensaje original referenciado con un borde izquierdo rojo. Al hacer clic en la referencia, la vista se desplaza al mensaje original.

## Base de datos

### contacts

| Columna | Tipo | Descripción |
|---------|------|-------------|
| telegram_id | INTEGER PK | ID de Telegram del usuario |
| name | TEXT | Nombre real (full_name) |
| username | TEXT | @username (nullable) |
| alias | TEXT | Apodo personalizado (nullable) |
| blocked | INTEGER | 0=activo, 1=bloqueado |
| created_at | TEXT | Fecha de registro |

### messages

| Columna | Tipo | Descripción |
|---------|------|-------------|
| id | INTEGER PK | Autoincrement |
| contact_id | INTEGER FK | Referencia a contacts |
| text | TEXT | Contenido |
| sender | TEXT | `me`, `them` o `bot` |
| from_user | TEXT | Nombre visible del remitente |
| created_at | TEXT | Timestamp |

### chat_state

| Columna | Tipo | Descripción |
|---------|------|-------------|
| contact_id | INTEGER PK FK | Referencia a contacts |
| last_read_msg_id | INTEGER | ID del último mensaje leído |
