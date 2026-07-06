#!/usr/bin/env python3
"""Background SSE listener — desktop popup via tkinter for new messages.
Click "Abrir" to open the web app in the corresponding chat.
"""

import json
import logging
import os
import queue
import threading
import time
import tkinter as tk
import urllib.request
import webbrowser

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("notifier")

HOST = os.getenv("HOST", "127.0.0.1")
PORT = os.getenv("PORT", "8080")
WEB_TOKEN = os.getenv("WEB_TOKEN", "")
BASE_URL = f"http://{HOST}:{PORT}"
TOKEN_QS = f"?token={WEB_TOKEN}" if WEB_TOKEN else ""
SSE_URL = f"{BASE_URL}/api/notifier/events{TOKEN_QS}"
WEB_URL = BASE_URL
DEBOUNCE_SEC = 3
AUTOCLOSE_SEC = 8


class DesktopNotifier:
    def __init__(self):
        self._msg_queue: "queue.Queue[dict]" = queue.Queue()
        self._last_notif = 0.0
        self._running = True

    def _debounce(self) -> bool:
        now = time.time()
        if now - self._last_notif < DEBOUNCE_SEC:
            return False
        self._last_notif = now
        return True

    def _open_chat(self, contact_id):
        url = f"{WEB_URL}/?contact={contact_id}"
        webbrowser.open(url)

    def _show_popup(self, msg):
        if not self._debounce():
            return
        contact_id = msg.get("contact_id", "")
        sender = msg.get("from_user") or str(contact_id)
        body = msg.get("text") or msg.get("file_name") or "Nuevo mensaje"
        body_short = body if len(body) <= 80 else body[:77] + "..."

        root = tk.Tk()
        root.title("")
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.configure(bg="#222")
        root.resizable(False, False)

        inner = tk.Frame(root, bg="#333", padx=14, pady=10)
        inner.pack(fill="both", expand=True)

        tk.Label(
            inner, text=f"Mensaje de {sender}", font=("Segoe UI", 10, "bold"),
            fg="#fff", bg="#333", anchor="w",
        ).pack(fill="x")

        tk.Label(
            inner, text=body_short, font=("Segoe UI", 9),
            fg="#ccc", bg="#333", anchor="w", wraplength=280, justify="left",
        ).pack(fill="x", pady=(4, 10))

        btn_frame = tk.Frame(inner, bg="#333")
        btn_frame.pack(fill="x")

        def _open():
            root.destroy()
            self._open_chat(contact_id)

        def _close():
            root.destroy()

        tk.Button(
            btn_frame, text="Abrir", command=_open,
            font=("Segoe UI", 9), bg="#4a4", fg="#fff", bd=0, padx=16, pady=4,
            cursor="hand2",
        ).pack(side="right", padx=(4, 0))

        tk.Button(
            btn_frame, text="Cerrar", command=_close,
            font=("Segoe UI", 9), bg="#555", fg="#fff", bd=0, padx=12, pady=4,
            cursor="hand2",
        ).pack(side="right")

        # Position bottom-right
        root.update_idletasks()
        w = root.winfo_width()
        h = root.winfo_height()
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        x = sw - w - 20
        y = sh - h - 60
        root.geometry(f"+{x}+{y}")

        # Auto-close timer
        root.after(AUTOCLOSE_SEC * 1000, _close)

        root.mainloop()

    def _popup_worker(self):
        while self._running:
            try:
                msg = self._msg_queue.get(timeout=1)
                logger.info(f"Showing popup for contact {msg.get('contact_id')}")
                self._show_popup(msg)
                logger.info("Popup closed")
            except queue.Empty:
                continue

    def _sse_reader(self):
        retry_delay = 2
        while self._running:
            try:
                req = urllib.request.Request(SSE_URL)
                req.add_header("Cache-Control", "no-cache")
                response = urllib.request.urlopen(req, timeout=None)
                retry_delay = 2
                buf = ""
                while self._running:
                    try:
                        byte = response.read(1)
                    except Exception:
                        break
                    if not byte:
                        break
                    buf += byte.decode("utf-8", errors="replace")
                    if buf.endswith("\n\n"):
                        event = buf[:-2]
                        buf = ""
                        for line in event.split("\n"):
                            if line.startswith("data: "):
                                data = line[6:]
                                try:
                                    msg = json.loads(data)
                                    if msg.get("sender") in ("them", "bot"):
                                        self._msg_queue.put(msg)
                                except json.JSONDecodeError:
                                    pass
            except Exception as e:
                if self._running:
                    logger.warning(f"SSE connection error: {e}, retry in {retry_delay}s")
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 1.5, 30)

    def run(self):
        t = threading.Thread(target=self._sse_reader, daemon=True)
        t.start()
        self._popup_worker()


def main():
    logger.info("Notifier started")
    notifier = DesktopNotifier()
    notifier.run()


if __name__ == "__main__":
    main()
