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
telebot status      # Estado del bot
telebot logs        # Logs en vivo
telebot start|stop
telebot notifier status   # Estado del notificador de escritorio
telebot help              # Todos los comandos
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
