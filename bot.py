import asyncio
import logging
import os
import subprocess

from dotenv import load_dotenv

load_dotenv()

from telegram import Bot
from telegram.ext import Application, MessageHandler, filters

import db

logger = logging.getLogger(__name__)

TOKEN = os.getenv("TOKEN")
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

_bot_loop = None
_sse_callback = None

AVATAR_DIR = os.path.join(DATA_DIR, "avatars")

FILE_TYPE_MAP = {
    "audio": "audio",
    "video": "video",
    "voice": "audio",
    "photo": "image",
    "document": "document",
    "animation": "video",
}


def set_sse_callback(cb):
    global _sse_callback
    _sse_callback = cb


def _convert_to_mp3(local_path):
    if not local_path.lower().endswith(".ogg"):
        return local_path
    mp3_path = local_path.rsplit(".", 1)[0] + ".mp3"
    try:
        subprocess.run(
            ["ffmpeg", "-i", local_path, "-y", "-acodec", "libmp3lame", "-q:a", "2", mp3_path],
            capture_output=True, timeout=30,
        )
        if os.path.exists(mp3_path):
            os.remove(local_path)
            return mp3_path
    except Exception as e:
        logger.warning(f"OGG conversion failed: {e}")
    return local_path


async def _download_and_save(file_obj, contact_id, file_unique_id, ext, file_type):
    filename = f"{contact_id}_{file_unique_id}{ext}"
    rel_path = os.path.join(file_type, filename)
    local_path = os.path.join(DATA_DIR, rel_path)
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    await file_obj.download_to_drive(custom_path=local_path)

    if ext == ".ogg":
        new_local = _convert_to_mp3(local_path)
        if new_local != local_path:
            new_ext = ".mp3"
            new_filename = filename.rsplit(".", 1)[0] + new_ext
            new_rel_path = os.path.join(file_type, new_filename)
            return new_rel_path, new_filename

    return rel_path, filename


async def _save_avatar(bot, contact_id):
    try:
        photos = await bot.get_user_profile_photos(contact_id, limit=1)
        if not photos or not photos.photos:
            return
        # smallest photo is last in the array
        sizes = photos.photos[0]
        smallest = sizes[-1]
        file = await smallest.get_file()
        os.makedirs(AVATAR_DIR, exist_ok=True)
        local_path = os.path.join(AVATAR_DIR, f"{contact_id}.jpg")
        await file.download_to_drive(custom_path=local_path)
        logger.info(f"Avatar saved for contact {contact_id}")
    except Exception as e:
        logger.debug(f"Avatar fetch failed for {contact_id}: {e}")


async def _handle_message(update, context):
    try:
        msg_obj = update.message
        if not msg_obj:
            return
        if msg_obj.chat.type != "private":
            return

        user = msg_obj.from_user
        contact_id = user.id
        caption = msg_obj.caption or ""

        db.upsert_contact(contact_id, user.full_name, user.username)
        await _save_avatar(context.bot, contact_id)

        # resolve reply_to reference from Telegram
        reply_to_id = None
        if msg_obj.reply_to_message:
            tg_msg_id = msg_obj.reply_to_message.message_id
            found = db.find_message_by_telegram_id(contact_id, tg_msg_id)
            if found:
                reply_to_id = found["id"]

        # Check for file attachments
        if msg_obj.audio:
            a = msg_obj.audio
            file = await a.get_file()
            ext = os.path.splitext(file.file_path or ".mp3")[1]
            rel_path, filename = await _download_and_save(file, contact_id, file.file_unique_id, ext, "audio")
            msg = db.save_message(contact_id, caption, "them", from_user=user.full_name,
                                  file_type="audio", file_path=rel_path, file_name=a.file_name or filename, file_size=a.file_size,
                                  reply_to_msg_id=reply_to_id, telegram_msg_id=msg_obj.message_id)
            logger.info(f"Audio from {user.full_name}: {filename}")
        elif msg_obj.voice:
            v = msg_obj.voice
            file = await v.get_file()
            rel_path, filename = await _download_and_save(file, contact_id, file.file_unique_id, ".ogg", "audio")
            msg = db.save_message(contact_id, caption, "them", from_user=user.full_name,
                                  file_type="audio", file_path=rel_path, file_name="voice.ogg", file_size=v.file_size,
                                  reply_to_msg_id=reply_to_id, telegram_msg_id=msg_obj.message_id)
            logger.info(f"Voice from {user.full_name}")
        elif msg_obj.video:
            v = msg_obj.video
            file = await v.get_file()
            ext = os.path.splitext(file.file_path or ".mp4")[1]
            rel_path, filename = await _download_and_save(file, contact_id, file.file_unique_id, ext, "video")
            msg = db.save_message(contact_id, caption, "them", from_user=user.full_name,
                                  file_type="video", file_path=rel_path, file_name=filename, file_size=v.file_size,
                                  reply_to_msg_id=reply_to_id, telegram_msg_id=msg_obj.message_id)
            logger.info(f"Video from {user.full_name}: {filename}")
        elif msg_obj.photo:
            photo = msg_obj.photo[-1]
            file = await photo.get_file()
            rel_path, filename = await _download_and_save(file, contact_id, file.file_unique_id, ".jpg", "image")
            msg = db.save_message(contact_id, caption, "them", from_user=user.full_name,
                                  file_type="image", file_path=rel_path, file_name=filename, file_size=photo.file_size,
                                  reply_to_msg_id=reply_to_id, telegram_msg_id=msg_obj.message_id)
            logger.info(f"Photo from {user.full_name}: {filename}")
        elif msg_obj.document:
            d = msg_obj.document
            file = await d.get_file()
            ext = os.path.splitext(d.file_name or file.file_path or ".dat")[1]
            rel_path, filename = await _download_and_save(file, contact_id, file.file_unique_id, ext, "document")
            msg = db.save_message(contact_id, caption, "them", from_user=user.full_name,
                                  file_type="document", file_path=rel_path, file_name=d.file_name or filename, file_size=d.file_size,
                                  reply_to_msg_id=reply_to_id, telegram_msg_id=msg_obj.message_id)
            logger.info(f"Document from {user.full_name}: {d.file_name}")
        elif msg_obj.text:
            text = msg_obj.text
            msg = db.save_message(contact_id, text, "them", from_user=user.full_name, reply_to_msg_id=reply_to_id, telegram_msg_id=msg_obj.message_id)
            logger.info(f"Text from {user.full_name}: {text[:60]}")
        else:
            logger.debug(f"Unhandled message type from {user.full_name}")
            return

        if _sse_callback:
            _sse_callback(msg)
    except Exception as e:
        logger.error(f"Handler error: {e}", exc_info=True)


async def _send_message(contact_id, text, file_path=None, file_type=None, file_name=None, reply_to_msg_id=None):
    b = Bot(TOKEN)
    tg_reply_id = db.get_telegram_msg_id(reply_to_msg_id) if reply_to_msg_id else None
    if file_path and file_type:
        abs_path = os.path.join(DATA_DIR, file_path)
        with open(abs_path, "rb") as f:
            if file_type == "image":
                sent = await b.send_photo(chat_id=contact_id, photo=f, caption=text, reply_to_message_id=tg_reply_id)
            elif file_type == "audio":
                sent = await b.send_audio(chat_id=contact_id, audio=f, caption=text, title=file_name, reply_to_message_id=tg_reply_id)
            elif file_type == "video":
                sent = await b.send_video(chat_id=contact_id, video=f, caption=text, reply_to_message_id=tg_reply_id)
            else:
                sent = await b.send_document(chat_id=contact_id, document=f, caption=text, filename=file_name, reply_to_message_id=tg_reply_id)
        return db.save_message(contact_id, text, "me", from_user="Tú",
                               file_type=file_type, file_path=file_path, file_name=file_name,
                               reply_to_msg_id=reply_to_msg_id, telegram_msg_id=sent.message_id)
    else:
        sent = await b.send_message(chat_id=contact_id, text=text, reply_to_message_id=tg_reply_id)
        return db.save_message(contact_id, text, "me", from_user="Tú",
                               reply_to_msg_id=reply_to_msg_id, telegram_msg_id=sent.message_id)


def send_message(contact_id, text, file_path=None, file_type=None, file_name=None, reply_to_msg_id=None):
    async def _run():
        return await _send_message(contact_id, text, file_path, file_type, file_name, reply_to_msg_id)
    future = asyncio.run_coroutine_threadsafe(_run(), _bot_loop)
    return future.result()


def run():
    global _bot_loop
    _bot_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_bot_loop)

    app = Application.builder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.ALL, _handle_message))
    logger.info("Bot started polling (individual chat mode)")
    app.run_polling(drop_pending_updates=True)
