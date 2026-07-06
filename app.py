import json
import logging
import os
import queue
import subprocess
import threading
import uuid

from dotenv import load_dotenv

load_dotenv()

from flask import Flask, Response, jsonify, redirect, render_template, request, send_from_directory

import bot
import db

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


@app.errorhandler(404)
def not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Ruta de API inexistente"}), 404
    return redirect("/?error=Ruta+inexistente")

_sse_queues = []
_sse_lock = threading.Lock()
_sse_count = 0
_notifier_queues = []


def _systemd_notifier(action):
    r = subprocess.run(
        ["systemctl", "--user", action, "telebot-notifier"],
        capture_output=True, text=True, timeout=10,
    )
    if r.returncode != 0:
        logger.warning(f"systemctl --user {action} notifier failed: {r.stderr.strip()}")


def _sync_notifier():
    mode = db.get_pref("notif_mode", "all")
    sse_count = _sse_count
    logger.info(f"_sync_notifier: mode={mode} sse_count={sse_count}")
    if mode == "none":
        _systemd_notifier("stop")
    elif sse_count > 0:
        _systemd_notifier("stop")
    else:
        _systemd_notifier("start")


ALLOWED_EXTENSIONS = {
    "image": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"},
    "audio": {".mp3", ".ogg", ".wav", ".m4a", ".flac", ".aac"},
    "video": {".mp4", ".webm", ".mov", ".avi", ".mkv"},
    "document": {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar", ".txt", ".csv", ".json", ".py", ".js", ".html", ".css"},
}


def _broadcast(msg):
    with _sse_lock:
        dead = []
        for q in _sse_queues + _notifier_queues:
            try:
                q.put_nowait(msg)
            except queue.Full:
                dead.append(q)
        for q in dead:
            if q in _sse_queues:
                _sse_queues.remove(q)
            if q in _notifier_queues:
                _notifier_queues.remove(q)


bot.set_sse_callback(_broadcast)


@app.route("/")
def index():
    resp = render_template("index.html")
    return Response(resp, headers={
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    })


@app.route("/api/contacts")
def list_contacts():
    contacts = db.get_contacts()
    for c in contacts:
        avatar_path = os.path.join(DATA_DIR, "avatars", f"{c['telegram_id']}.jpg")
        c["avatar"] = os.path.exists(avatar_path)
    return jsonify(contacts)


@app.route("/api/contacts", methods=["POST"])
def add_contact():
    data = request.get_json(force=True)
    telegram_id = data.get("telegram_id")
    if not telegram_id:
        return jsonify({"error": "telegram_id is required"}), 400
    try:
        telegram_id = int(telegram_id)
    except (ValueError, TypeError):
        return jsonify({"error": "telegram_id must be an integer"}), 400
    contact = db.upsert_contact(
        telegram_id,
        data.get("name", str(telegram_id)),
        username=data.get("username"),
        alias=data.get("alias"),
    )
    return jsonify(contact), 201


@app.route("/api/contacts/<int:telegram_id>", methods=["PUT"])
def edit_contact(telegram_id):
    data = request.get_json(force=True)
    contact = db.update_contact(
        telegram_id,
        name=data.get("name"),
        alias=data.get("alias"),
        blocked=data.get("blocked"),
    )
    if not contact:
        return jsonify({"error": "contact not found"}), 404
    return jsonify(contact)


@app.route("/api/contacts/<int:telegram_id>", methods=["DELETE"])
def remove_contact(telegram_id):
    db.delete_contact(telegram_id)
    return "", 204


@app.route("/api/messages/<int:contact_id>")
def get_messages(contact_id):
    return jsonify(db.get_messages(contact_id))


@app.route("/api/messages/<int:contact_id>", methods=["DELETE"])
def delete_messages(contact_id):
    db.delete_messages(contact_id)
    return "", 204


@app.route("/api/send/<int:contact_id>", methods=["POST"])
def send(contact_id):
    data = request.get_json(force=True)
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "El mensaje no puede estar vacío"}), 400
    try:
        msg = bot.send_message(contact_id, text, reply_to_msg_id=data.get("reply_to_msg_id"))
        _broadcast(msg)
        return jsonify(msg), 201
    except Exception as e:
        logger.error(f"Error sending to {contact_id}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/upload/<int:contact_id>", methods=["POST"])
def upload_file(contact_id):
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    f = request.files["file"]
    if f.filename == "":
        return jsonify({"error": "Empty filename"}), 400

    caption = request.form.get("caption", "").strip()
    reply_to_msg_id = request.form.get("reply_to_msg_id")
    if reply_to_msg_id is not None:
        reply_to_msg_id = int(reply_to_msg_id)
    ext = os.path.splitext(f.filename)[1].lower()

    file_type = None
    for ft, exts in ALLOWED_EXTENSIONS.items():
        if ext in exts:
            file_type = ft
            break
    if not file_type:
        file_type = "document"

    filename = f"{contact_id}_{uuid.uuid4().hex}{ext}"
    rel_dir = os.path.join(file_type, filename)
    abs_path = os.path.join(DATA_DIR, rel_dir)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    f.save(abs_path)

    try:
        msg = bot.send_message(contact_id, caption, file_path=rel_dir, file_type=file_type, file_name=f.filename, reply_to_msg_id=reply_to_msg_id)
        _broadcast(msg)
        return jsonify(msg), 201
    except Exception as e:
        logger.error(f"Error sending file to {contact_id}: {e}")
        os.remove(abs_path)
        return jsonify({"error": str(e)}), 500


@app.route("/data/<path:filename>")
def serve_data(filename):
    return send_from_directory(DATA_DIR, filename)


@app.route("/api/data/info")
def data_info():
    folders = []
    total_files = 0
    total_size = 0
    for folder in ("audio", "video", "image", "document"):
        folder_path = os.path.join(DATA_DIR, folder)
        count = 0
        size = 0
        if os.path.exists(folder_path):
            for f in os.listdir(folder_path):
                fpath = os.path.join(folder_path, f)
                if os.path.isfile(fpath):
                    fs = os.path.getsize(fpath)
                    count += 1
                    size += fs
        total_files += count
        total_size += size
        folders.append({"type": folder, "count": count, "size": size})
    return jsonify({"folders": folders, "total_files": total_files, "total_size": total_size})


@app.route("/api/data/clean", methods=["POST"])
def clean_data():
    data = request.get_json(force=True)
    folder_type = data.get("type", "all")
    targets = ("audio", "video", "image", "document") if folder_type == "all" else (folder_type,)

    deleted = []
    not_found = []
    affected_msg_ids = []

    for folder in targets:
        folder_path = os.path.join(DATA_DIR, folder)
        if not os.path.exists(folder_path):
            continue
        for f in os.listdir(folder_path):
            fpath = os.path.join(folder_path, f)
            if os.path.isfile(fpath):
                try:
                    os.remove(fpath)
                    deleted.append({"type": folder, "name": f, "size": 0})
                except Exception as e:
                    not_found.append({"type": folder, "name": f, "error": str(e)})

    # Update DB: nullify file_path and append deletion notice to text
    for entry in deleted:
        msgs = db.get_messages_by_file(entry["type"], entry["name"])
        for m in msgs:
            db.update_message_text(m["id"], (m["text"] or "") + f"\n[Archivo eliminado: {entry['name']}]")
            db.clear_message_file(m["id"])
            affected_msg_ids.append(m["id"])

    _broadcast({"type": "data_cleaned", "deleted": len(deleted), "not_found": len(not_found), "affected": affected_msg_ids})
    return jsonify({"deleted": len(deleted), "not_found": len(not_found), "affected": affected_msg_ids})


@app.route("/api/read/<int:contact_id>", methods=["POST"])
def mark_read(contact_id):
    data = request.get_json(force=True) or {}
    msg_id = data.get("msg_id", 0)
    db.mark_read(contact_id, msg_id)
    return "", 204


@app.route("/api/events")
def events():
    q = queue.Queue(maxsize=100)
    with _sse_lock:
        _sse_queues.append(q)
        global _sse_count
        _sse_count += 1
    _sync_notifier()

    def generate():
        yield ":\n\n"
        try:
            while True:
                data = q.get()
                yield f"data: {json.dumps(data, default=str)}\n\n"
        except GeneratorExit:
            with _sse_lock:
                if q in _sse_queues:
                    _sse_queues.remove(q)
                    global _sse_count
                    _sse_count -= 1
            _sync_notifier()

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.route("/api/notifier/events")
def notifier_events():
    q = queue.Queue(maxsize=100)
    with _sse_lock:
        _notifier_queues.append(q)

    def generate():
        yield ":\n\n"
        try:
            while True:
                data = q.get()
                yield f"data: {json.dumps(data, default=str)}\n\n"
        except GeneratorExit:
            with _sse_lock:
                if q in _notifier_queues:
                    _notifier_queues.remove(q)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.route("/api/notifier/mode", methods=["POST"])
def set_notifier_mode():
    data = request.get_json(force=True)
    mode = data.get("mode", "all")
    if mode not in ("all", "push", "sound", "none"):
        return jsonify({"error": "Modo inválido"}), 400
    db.set_pref("notif_mode", mode)
    _sync_notifier()
    return jsonify({"status": "ok"})


@app.route("/api/notifier/status")
def notifier_status():
    r = subprocess.run(
        ["systemctl", "--user", "is-active", "telebot-notifier"],
        capture_output=True, text=True, timeout=10,
    )
    mode = db.get_pref("notif_mode", "all")
    return jsonify({"status": r.stdout.strip() or "inactive", "mode": mode})


def start_flask():
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", 8080))
    debug = os.getenv("DEBUG", "").lower() in ("true", "1", "yes")
    if debug:
        logger.warning("DEBUG mode enabled — do not use in production!")
    logger.info(f"Web server on http://{host}:{port}")
    app.run(host=host, port=port, debug=debug, use_reloader=False)


if __name__ == "__main__":
    db.init_db()
    t = threading.Thread(target=start_flask, daemon=True)
    t.start()
    bot.run()
