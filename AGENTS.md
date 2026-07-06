# AGENTS.md — telebot

## Entry point

`app.py` is the single entrypoint. It starts Flask in a daemon thread, then blocks on `bot.run()` (Telegram polling).

## Dependencies

- `python3 -m pip install -r requirements.txt` — `pip` as bare command does not exist on this system.
- On Debian/Ubuntu with PEP 668, `--break-system-packages` may be needed.
- Python 3.13+. FFmpeg required for OGG→MP3 conversion.

## Running

```bash
python3 app.py
```

Opens `http://localhost:8080`. Token must be set in `.env` as `TOKEN=<value>`.

## Known install.sh bugs (repo at github.com/braiidev/telebot)

- `set -euo pipefail` + `trap cleanup EXIT` references `$TMPDIR` before init → crashes when directory already exists. Fix: set `TMPDIR=""` before trap.
- Uses bare `pip` → `command not found`. Fix: replace with `python3 -m pip`.
- Does not handle `--break-system-packages`.
- `read` prompts read from stdin (the pipe) when using `curl ... | bash`, consuming script content and causing syntax errors. Fix: redirect each `read` with `< /dev/tty`.
- `.env` is overwritten cleanly but script crashes before creating services or CLI commands.

## Architecture

- `app.py` → Flask thread (SSE, REST API) + main thread blocks on `bot.run()`.
- `bot.py` → async handlers, sync bridge via `asyncio.run_coroutine_threadsafe()`.
- `db.py` → SQLite (WAL mode), opens/closes connection per call. `homebot.db` in repo root.
- `notifier.py` → standalone tkinter popup, runs as systemd user service, reads SSE byte-by-byte (CPython chunked encoding workaround).
- Frontend: vanilla JS SPA in `templates/index.html`, no framework.

## SSE & notifier

- `/api/events` for browser, `/api/notifier/events` for desktop notifier (separate queue, excluded from browser connection count).
- Browser sends heartbeat (`POST /api/heartbeat {visible}`) every 10s. Server uses it to auto-start/stop `telebot-notifier.service` via systemctl.
- Notifier SSE reads byte-by-byte (`response.read(1)`) — required because CPython's `read(4096)` blocks on small chunks.

## No test / lint / build infra

Zero test files, no CI, no formatter/linter config, no Makefile, no pyproject.toml.

## `.env` format

```
TOKEN=<telegram_bot_token>
HOST=127.0.0.1
PORT=8080
```

`DEBUG=true` enables Flask debug mode (optional).

## No authentication

Web UI is open. Default `HOST=127.0.0.1` restricts to localhost.

## Notable quirks

- `.env` and `homebot.db` are in `.gitignore` — but verify before committing.
- `drop_pending_updates=True` in `bot.run()` — pending messages during downtime are lost.
- `hb-custom-theme` in localStorage (private-browsing safe, wrapped in try-catch).
- `allowed_extensions` dict only applies to web uploads, not Telegram file downloads.
- FFmpeg conversion is in a try/except — failure is silently logged, original file kept.
