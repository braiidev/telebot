import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "homebot.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS contacts (
            telegram_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            username TEXT,
            alias TEXT,
            blocked INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id INTEGER NOT NULL REFERENCES contacts(telegram_id),
            text TEXT NOT NULL DEFAULT '',
            sender TEXT NOT NULL CHECK(sender IN ('me', 'them', 'bot')),
            from_user TEXT,
            file_type TEXT,
            file_path TEXT,
            file_name TEXT,
            file_size INTEGER,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS chat_state (
            contact_id INTEGER PRIMARY KEY REFERENCES contacts(telegram_id),
            last_read_msg_id INTEGER NOT NULL DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_messages_contact ON messages(contact_id, id);
    """)
    conn.commit()
    conn.close()


def upsert_contact(telegram_id, name, username=None, alias=None):
    conn = get_conn()
    conn.execute("""
        INSERT INTO contacts (telegram_id, name, username, alias)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(telegram_id) DO UPDATE SET
            name=COALESCE(NULLIF(excluded.name, ''), contacts.name),
            username=COALESCE(NULLIF(excluded.username, ''), contacts.username)
    """, (telegram_id, name, username, alias))
    conn.commit()
    row = conn.execute("SELECT * FROM contacts WHERE telegram_id = ?", (telegram_id,)).fetchone()
    conn.close()
    return dict(row)


def update_contact(telegram_id, name=None, alias=None, blocked=None):
    sets = []
    params = []
    if name is not None:
        sets.append("name = ?")
        params.append(name)
    if alias is not None:
        sets.append("alias = ?")
        params.append(alias)
    if blocked is not None:
        sets.append("blocked = ?")
        params.append(1 if blocked else 0)
    if not sets:
        return None
    params.append(telegram_id)
    conn = get_conn()
    conn.execute(f"UPDATE contacts SET {', '.join(sets)} WHERE telegram_id = ?", params)
    conn.commit()
    row = conn.execute("SELECT * FROM contacts WHERE telegram_id = ?", (telegram_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_contact(telegram_id):
    conn = get_conn()
    conn.execute("DELETE FROM chat_state WHERE contact_id = ?", (telegram_id,))
    conn.execute("DELETE FROM messages WHERE contact_id = ?", (telegram_id,))
    conn.execute("DELETE FROM contacts WHERE telegram_id = ?", (telegram_id,))
    conn.commit()
    conn.close()


def delete_messages(contact_id):
    conn = get_conn()
    conn.execute("DELETE FROM chat_state WHERE contact_id = ?", (contact_id,))
    conn.execute("DELETE FROM messages WHERE contact_id = ?", (contact_id,))
    conn.commit()
    conn.close()


def get_contacts():
    conn = get_conn()
    rows = conn.execute("""
        SELECT
            c.*,
            m.text AS last_message,
            m.created_at AS last_message_at,
            COALESCE(cs.last_read_msg_id, 0) AS last_read_msg_id,
            (SELECT COUNT(*) FROM messages
             WHERE contact_id = c.telegram_id AND id > COALESCE(cs.last_read_msg_id, 0) AND sender = 'them'
            ) AS unread_count
        FROM contacts c
        LEFT JOIN messages m ON m.id = (
            SELECT MAX(id) FROM messages WHERE contact_id = c.telegram_id
        )
        LEFT JOIN chat_state cs ON cs.contact_id = c.telegram_id
        ORDER BY m.created_at DESC, c.name ASC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_message(contact_id, text, sender, from_user=None, file_type=None, file_path=None, file_name=None, file_size=None):
    conn = get_conn()
    conn.execute(
        "INSERT INTO messages (contact_id, text, sender, from_user, file_type, file_path, file_name, file_size) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (contact_id, text, sender, from_user, file_type, file_path, file_name, file_size),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id, contact_id, text, sender, from_user, file_type, file_path, file_name, file_size, created_at FROM messages WHERE id = last_insert_rowid()"
    ).fetchone()
    conn.close()
    return dict(row)


def get_messages(contact_id, limit=100):
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, contact_id, text, sender, from_user, file_type, file_path, file_name, file_size, created_at FROM messages WHERE contact_id = ? ORDER BY created_at ASC, id ASC LIMIT ?",
        (contact_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_read(contact_id, msg_id):
    conn = get_conn()
    conn.execute("""
        INSERT INTO chat_state (contact_id, last_read_msg_id) VALUES (?, ?)
        ON CONFLICT(contact_id) DO UPDATE SET last_read_msg_id = excluded.last_read_msg_id
    """, (contact_id, msg_id))
    conn.commit()
    conn.close()


def get_messages_by_file(file_type, file_name):
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, contact_id, text, file_type, file_path, file_name FROM messages WHERE file_type = ? AND file_name = ?",
        (file_type, file_name),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_message_text(msg_id, text):
    conn = get_conn()
    conn.execute("UPDATE messages SET text = ? WHERE id = ?", (text, msg_id))
    conn.commit()
    conn.close()


def clear_message_file(msg_id):
    conn = get_conn()
    conn.execute("UPDATE messages SET file_path = NULL, file_name = NULL, file_size = NULL WHERE id = ?", (msg_id,))
    conn.commit()
    conn.close()
