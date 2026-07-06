# telebot 🤖

Chatbot de Telegram con interfaz web, mensajería en tiempo real, multimedia y notificaciones de escritorio.

## Stack

Python 3.13+ · Flask · SSE · python-telegram-bot v21 · SQLite3 · tkinter

## Instalación rápida

```bash
curl -fsSL https://raw.githubusercontent.com/braiidev/telebot/main/install.sh | bash
```

Te va a pedir el **token de Telegram** (creá un bot en [@BotFather](https://t.me/botfather)) y después arranca solo.

Abrí `http://localhost:8080` y listo.

## Uso

```bash
telebot start          # Inicia el bot
telebot stop           # Detiene bot + notificador
telebot restart        # Reinicia el bot
telebot status         # Estado del bot
telebot enable         # Auto-inicio al boot
telebot disable        # Quita auto-inicio
telebot logs           # Logs en vivo
telebot notifier       # Gestiona notificador (start|stop|restart|status|enable|disable)
telebot set token TKN  # Cambia token de Telegram
telebot set host HOST  # Cambia host (defecto: 127.0.0.1)
telebot set port NUM   # Cambia puerto (defecto: 8080)
telebot set debug on|off  # Modo debug
telebot set show       # Muestra configuración
telebot uninstall      # Elimina telebot por completo
telebot help           # Todos los comandos
```

## Funcionalidades

- Mensajería individual con contactos de Telegram
- Archivos multimedia (audio, video, imagen, documento)
- Notificaciones push, sonido y popups de escritorio (tkinter)
- Auto-inicio al encender el PC (systemd user services)
- Tema dark/light con editor de colores

## Requisitos

- Python 3.13+
- ffmpeg (para audio OGG→MP3)
- tkinter (para popups de escritorio)
- systemd
