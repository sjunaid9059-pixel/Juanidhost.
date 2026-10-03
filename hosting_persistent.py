# ====================================================
#               MADE BY XPILIOT
#     PRIME HOSTING SERVER v4.5 (RAILWAY READY)
# ====================================================

import os
import sys
import sqlite3
import subprocess
import time
import random
import string
import threading
from datetime import datetime, timedelta
from telebot import TeleBot, types

# ==================== RAILWAY CONFIGURATION ====================
# Railway Variables se Token aur IDs uthayega, agar nahi mile toh default use karega (Local ke liye)
# ==================== RAILWAY CONFIGURATION ====================
# Railway Variables se Token aur IDs uthayega, agar nahi mile toh default use karega (Local ke liye)
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

# Render Persistent Disk location. Keep this configurable for local testing.
STORAGE_DIR = os.environ.get("STORAGE_DIR", "/var/data")
HOST_DIR = os.path.join(STORAGE_DIR, "hosted_files")
MAX_LOG_SIZE_MB = 5

# Default Values
config = {"max_bots": 10}

os.makedirs(STORAGE_DIR, exist_ok=True)
os.makedirs(HOST_DIR, exist_ok=True)

# ⚡ Multi-Threaded Bot Instance
bot = TeleBot(BOT_TOKEN, threaded=True, num_threads=20) if BOT_TOKEN else None
if bot is None:
    raise RuntimeError("BOT_TOKEN environment variable is required.")

# ==================== DATABASE SETUP ====================
def get_db():
    conn = sqlite3.connect(os.path.join(STORAGE_DIR, "hosting_data.db"), check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS hosted_bots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            filepath TEXT NOT NULL,
            logpath TEXT NOT NULL,
            pid INTEGER DEFAULT NULL,
            status TEXT DEFAULT 'stopped',
            auto_guard INTEGER DEFAULT 1,
            UNIQUE(user_id, filename)
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ==================== HELPER FUNCTIONS ====================
def register_user(user_id, ref_by=None):
    conn = get_db()
    conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def is_process_alive(pid):
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError, TypeError):
        return False

def safe_bot_username():
    try:
        me = bot.get_me()
        return f"@{me.username}" if me.username else "Unknown"
    except Exception:
        return "Unknown"

def send_or_edit(chat_id, text, reply_markup=None, message_id=None, parse_mode="Markdown"):
    try:
        if message_id:
            bot.edit_message_text(
                text, chat_id, message_id,
                parse_mode=parse_mode, reply_markup=reply_markup
            )
            return
    except Exception:
        pass
    bot.send_message(chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup)

# ==================== CRASH GUARD WORKER ====================
def crash_guard_worker():
    while True:
        try:
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT * FROM hosted_bots WHERE status='running'")
            rows = cur.fetchall()

            for b in rows:
                if b["pid"] and is_process_alive(b["pid"]):
                    continue
                try:
                    log_file = open(b["logpath"], "a", encoding="utf-8")
                    log_file.write(f"\n--- [AUTO RESTART {datetime.now()}] ---\n")
                    log_file.flush()
                    proc = subprocess.Popen(
                        [sys.executable, "-u", b["filepath"]],
                        stdout=log_file,
                        stderr=log_file,
                        cwd=os.path.dirname(b["filepath"])
                    )
                    log_file.close()
                    cur.execute(
                        "UPDATE hosted_bots SET pid=?, status='running' WHERE id=?",
                        (proc.pid, b["id"])
                    )
                    conn.commit()
                except Exception as exc:
                    try:
                        with open(b["logpath"], "a", encoding="utf-8") as f:
                            f.write(f"\n[AUTO RESTART ERROR] {exc}\n")
                    except Exception:
                        pass
                    cur.execute(
                        "UPDATE hosted_bots SET pid=NULL, status='stopped' WHERE id=?",
                        (b["id"],)
                    )
                    conn.commit()
            conn.close()
        except Exception:
            pass
        time.sleep(5)

threading.Thread(target=crash_guard_worker, daemon=True).start()

def restore_hosted_bots():
    """After a Render worker restart, relaunch all previously running hosted scripts."""
    try:
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM hosted_bots WHERE status='running'"
        ).fetchall()

        for b in rows:
            try:
                if b["pid"] and is_process_alive(b["pid"]):
                    continue
                if not os.path.isfile(b["filepath"]):
                    conn.execute(
                        "UPDATE hosted_bots SET pid=NULL, status='stopped' WHERE id=?",
                        (b["id"],)
                    )
                    conn.commit()
                    continue

                os.makedirs(os.path.dirname(b["filepath"]), exist_ok=True)
                log_file = open(b["logpath"], "a", encoding="utf-8")
                log_file.write(f"\n--- [RESTORE AFTER SERVER RESTART {datetime.now()}] ---\n")
                log_file.flush()

                proc = subprocess.Popen(
                    [sys.executable, "-u", b["filepath"]],
                    stdout=log_file,
                    stderr=log_file,
                    cwd=os.path.dirname(b["filepath"])
                )
                log_file.close()

                conn.execute(
                    "UPDATE hosted_bots SET pid=?, status='running' WHERE id=?",
                    (proc.pid, b["id"])
                )
                conn.commit()
            except Exception as exc:
                try:
                    with open(b["logpath"], "a", encoding="utf-8") as f:
                        f.write(f"\n[RESTORE ERROR] {exc}\n")
                except Exception:
                    pass
                conn.execute(
                    "UPDATE hosted_bots SET pid=NULL, status='stopped' WHERE id=?",
                    (b["id"],)
                )
                conn.commit()

        conn.close()
    except Exception as exc:
        print(f"Restore error: {exc}")

restore_hosted_bots()

# ==================== KEYBOARDS ====================
def main_menu_keyboard(user_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📤 Upload Bot (.py)", callback_data="upload_info"),
        types.InlineKeyboardButton("📱 My Hosted Bots", callback_data="my_bots")
    )
    markup.add(
        types.InlineKeyboardButton("📊 Server Status", callback_data="server_stats"),
        types.InlineKeyboardButton("❓ Help & Guide", callback_data="help_guide")
    )
    if user_id == ADMIN_ID:
        markup.add(types.InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_panel"))
    return markup

def admin_panel_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📋 Hosted Bots", callback_data="my_bots"),
        types.InlineKeyboardButton("📊 Server Status", callback_data="server_stats")
    )
    markup.add(types.InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu"))
    return markup

# ==================== COMMAND HANDLERS ====================
@bot.message_handler(commands=["start"])
def start_cmd(message):
    user_id = message.from_user.id
    register_user(user_id)
    name = message.from_user.first_name or "User"
    role = "👑 ADMIN" if user_id == ADMIN_ID else "👤 USER"
    note = (
        "You can upload `.py` files and host them automatically."
        if user_id == ADMIN_ID else
        "Hosting uploads are restricted to the configured admin."
    )
    bot.send_message(
        message.chat.id,
        f"🤖 **Python Hosting Server**\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"👋 Welcome, **{name}**!\n"
        f"🆔 ID: `{user_id}`\n"
        f"🎖️ Role: **{role}**\n"
        f"🤖 Bot: **{safe_bot_username()}**\n\n{note}",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(user_id)
    )


# ==================== AUTO DEPENDENCY INSTALL ====================
os.environ.setdefault("PIP_CACHE_DIR", os.path.join(STORAGE_DIR, "pip-cache"))
# Standard-library modules that must never be sent to pip.
STDLIB_MODULES = {
    "os", "sys", "sqlite3", "subprocess", "time", "random", "string",
    "threading", "datetime", "pathlib", "json", "re", "math", "asyncio",
    "logging", "typing", "collections", "itertools", "functools", "io",
    "traceback", "socket", "ssl", "http", "urllib", "email", "hashlib",
    "hmac", "base64", "csv", "statistics", "shutil", "tempfile", "uuid",
    "platform", "signal", "queue", "dataclasses", "enum", "contextlib",
    "inspect", "warnings", "abc", "copy", "timeit", "pprint", "textwrap",
    "argparse", "configparser", "secrets", "decimal", "fractions",
    "xml", "html", "calendar", "gzip", "bz2", "lzma", "tarfile", "zipfile"
}

# Common import-name -> PyPI-name differences.
PACKAGE_ALIASES = {
    "cv2": "opencv-python",
    "PIL": "Pillow",
    "bs4": "beautifulsoup4",
    "dotenv": "python-dotenv",
    "yaml": "PyYAML",
    "Crypto": "pycryptodome",
    "telegram": "pyTelegramBotAPI",
    "telebot": "pyTelegramBotAPI",
    "sklearn": "scikit-learn",
    "dateutil": "python-dateutil",
    "jwt": "PyJWT",
    "multipart": "python-multipart",
    "fitz": "PyMuPDF",
    "discord": "discord.py",
    "flask": "Flask",
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "requests": "requests",
    "aiohttp": "aiohttp",
    "httpx": "httpx",
    "pandas": "pandas",
    "numpy": "numpy",
}

def detect_imports(filepath):
    """Return top-level import names found in a Python file."""
    try:
        source = Path(filepath).read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source, filename=str(filepath))
    except Exception:
        return set()

    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names

def install_missing_packages(filepath, logpath):
    """Detect imports, test them, and install missing third-party packages."""
    imports = detect_imports(filepath)
    packages = []

    for module in sorted(imports):
        if module in STDLIB_MODULES:
            continue
        packages.append(PACKAGE_ALIASES.get(module, module))

    # Remove duplicates while preserving order.
    packages = list(dict.fromkeys(packages))
    if not packages:
        return [], True

    with open(logpath, "a", encoding="utf-8") as log:
        log.write(f"\n--- [DEPENDENCY CHECK {datetime.now()}] ---\n")
        log.write("Detected: " + ", ".join(packages) + "\n")

    # Install only packages that are actually missing.
    missing = []
    for module in sorted(imports):
        if module in STDLIB_MODULES:
            continue
        try:
            __import__(module)
        except Exception:
            missing.append(PACKAGE_ALIASES.get(module, module))

    missing = list(dict.fromkeys(missing))
    if not missing:
        return packages, True

    cmd = [
        sys.executable, "-m", "pip", "install",
        "--disable-pip-version-check", "--no-input"
    ] + missing

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=300
        )
        with open(logpath, "a", encoding="utf-8") as log:
            log.write(f"pip exit code: {result.returncode}\n")
            log.write(result.stdout[-12000:] + "\n")

        return packages, result.returncode == 0
    except Exception as exc:
        with open(logpath, "a", encoding="utf-8") as log:
            log.write(f"pip install exception: {exc}\n")
        return packages, False


@bot.message_handler(content_types=["document"])
def handle_document(message):
    user_id = message.from_user.id
    if user_id != ADMIN_ID:
        bot.reply_to(message, "🔒 Only the configured admin can upload and host `.py` files.")
        return

    filename = os.path.basename(message.document.file_name or "")
    if not filename.lower().endswith(".py"):
        bot.reply_to(message, "❌ Please upload a `.py` Python file only.")
        return

    status_msg = bot.reply_to(message, "📥 Downloading…\n🔎 Checking Python libraries…")

    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)

        user_dir = os.path.join(HOST_DIR, str(user_id))
        os.makedirs(user_dir, exist_ok=True)
        filepath = os.path.join(user_dir, filename)
        logpath = filepath + ".log"

        with open(filepath, "wb") as f:
            f.write(downloaded)

        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, pid FROM hosted_bots WHERE user_id=? AND filename=?",
            (user_id, filename)
        )
        old = cur.fetchone()

        if old:
            if old["pid"] and is_process_alive(old["pid"]):
                try:
                    os.kill(int(old["pid"]), 9)
                except Exception:
                    pass
            cur.execute(
                "UPDATE hosted_bots SET filepath=?, logpath=?, pid=NULL, status='stopped' WHERE id=?",
                (filepath, logpath, old["id"])
            )
            bot_id = old["id"]
        else:
            cur.execute(
                "INSERT INTO hosted_bots (user_id, filename, filepath, logpath, status) "
                "VALUES (?, ?, ?, ?, 'stopped')",
                (user_id, filename, filepath, logpath)
            )
            bot_id = cur.lastrowid

        conn.commit()
        conn.close()

        # Detect and install missing third-party libraries BEFORE hosting.
        try:
            bot.edit_message_text(
                "🔎 **Libraries detected…**\n📦 Installing missing packages…",
                chat_id, status_msg.message_id, parse_mode="Markdown"
            )
        except Exception:
            pass

        detected, dependencies_ok = install_missing_packages(filepath, logpath)

        try:
            req_path = filepath + ".requirements.txt"
            with open(req_path, "w", encoding="utf-8") as rf:
                for package in detected:
                    rf.write(package + "\n")
        except Exception:
            pass


        if not dependencies_ok:
            bot.edit_message_text(
                "❌ **Dependency installation failed.**\n\n"
                f"📦 Detected: `{', '.join(detected) if detected else 'None'}`\n"
                "📜 Open **My Hosted Bots → Live Logs** for the pip error.",
                chat_id, status_msg.message_id, parse_mode="Markdown"
            )
            return

        # Start only after dependency setup succeeds.
        bot.edit_message_text(
            f"⚡ **Starting `{filename}`…**\n\n"
            f"🤖 Host Bot: **{safe_bot_username()}**",
            chat_id, status_msg.message_id, parse_mode="Markdown"
        )

        log_file = open(logpath, "a", encoding="utf-8")
        log_file.write(f"\n--- [STARTED {datetime.now()}] ---\n")
        log_file.flush()

        proc = subprocess.Popen(
            [sys.executable, "-u", filepath],
            stdout=log_file,
            stderr=log_file,
            cwd=user_dir
        )
        log_file.close()

        conn = get_db()
        conn.execute(
            "UPDATE hosted_bots SET status='running', pid=? WHERE id=?",
            (proc.pid, bot_id)
        )
        conn.commit()
        conn.close()

        bot.edit_message_text(
            f"✅ **Hosted Successfully!**\n\n"
            f"📄 File: `{filename}`\n"
            f"📦 Libraries: `{len(detected)}` detected\n"
            f"🤖 Host Bot: **{safe_bot_username()}**\n"
            f"🟢 Status: **Running**\n"
            f"🆔 PID: `{proc.pid}`",
            chat_id, status_msg.message_id, parse_mode="Markdown"
        )

    except Exception as exc:
        try:
            bot.edit_message_text(
                f"❌ **Hosting failed:** `{exc}`",
                chat_id, status_msg.message_id, parse_mode="Markdown"
            )
        except Exception:
            bot.reply_to(message, f"❌ Hosting failed: `{exc}`")

# ==================== CALLBACK HANDLER ====================
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass

    uid = call.from_user.id
    chat_id = call.message.chat.id
    msg_id = call.message.message_id

    if call.data == "main_menu":
        send_or_edit(
            chat_id,
            f"🏠 **Hosting Dashboard**\n\n🤖 Host Bot: **{safe_bot_username()}**",
            main_menu_keyboard(uid), msg_id
        )

    elif call.data == "upload_info":
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu"))
        send_or_edit(
            chat_id,
            "📥 **Send your `.py` file directly into this chat.**\n\n"
            "The configured admin upload starts it automatically.",
            markup, msg_id
        )

    elif call.data == "server_stats":
        conn = get_db()
        total = conn.execute("SELECT COUNT(*) FROM hosted_bots").fetchone()[0]
        running = conn.execute(
            "SELECT COUNT(*) FROM hosted_bots WHERE status='running'"
        ).fetchone()[0]
        conn.close()
        msg = (
            f"🖥️ **Server Status**\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🤖 Host Bot: `{safe_bot_username()}`\n"
            f"📦 Total Hosted: `{total}`\n"
            f"🟢 Running: `{running}`\n"
            f"🛡️ Auto-Restart: Enabled"
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔄 Refresh", callback_data="server_stats"))
        markup.add(types.InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu"))
        send_or_edit(chat_id, msg, markup, msg_id)

    elif call.data == "help_guide":
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu"))
        send_or_edit(
            chat_id,
            "❓ **How to Host**\n\n"
            "1️⃣ Send a `.py` file.\n"
            "2️⃣ Open **My Hosted Bots**.\n"
            "3️⃣ Press **Start Bot** if needed.\n"
            "4️⃣ Check **Live Logs** for errors.\n\n"
            "🛡️ Crashed hosted processes are automatically restarted.",
            markup, msg_id
        )

    elif call.data == "admin_panel":
        if uid != ADMIN_ID:
            return
        send_or_edit(
            chat_id,
            f"⚙️ **Admin Panel**\n\n🤖 Host Bot: `{safe_bot_username()}`\n"
            f"🆔 Admin ID: `{ADMIN_ID}`\n\n"
            "Send any `.py` file to host it automatically.",
            admin_panel_keyboard(), msg_id
        )

    elif call.data == "my_bots":
        conn = get_db()
        bots = conn.execute(
            "SELECT * FROM hosted_bots WHERE user_id=?", (uid,)
        ).fetchall()
        conn.close()
        if not bots:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu"))
            send_or_edit(chat_id, "❌ **No hosted bots found.**", markup, msg_id)
            return

        markup = types.InlineKeyboardMarkup(row_width=1)
        for b in bots:
            icon = "🟢" if is_process_alive(b["pid"]) else "🔴"
            markup.add(types.InlineKeyboardButton(
                f"{icon} {b['filename']}", callback_data=f"manage_{b['id']}"
            ))
        markup.add(types.InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu"))
        send_or_edit(chat_id, "⚙️ **Your Hosted Bots:**", markup, msg_id)

    elif call.data.startswith("manage_"):
        render_bot_control(chat_id, int(call.data.split("_")[1]), msg_id)
    elif call.data.startswith("startbot_"):
        start_bot_action(chat_id, int(call.data.split("_")[1]), msg_id)
    elif call.data.startswith("stopbot_"):
        stop_bot_action(chat_id, int(call.data.split("_")[1]), msg_id)
    elif call.data.startswith("logbot_"):
        show_logs_action(chat_id, int(call.data.split("_")[1]), msg_id)
    elif call.data.startswith("clearlog_"):
        clear_logs_action(chat_id, int(call.data.split("_")[1]), msg_id)
    elif call.data.startswith("piplist_"):
        show_pip_action(chat_id, int(call.data.split("_")[1]), msg_id)
    elif call.data.startswith("delbot_"):
        delete_bot_action(chat_id, int(call.data.split("_")[1]), msg_id)

# ==================== BOT CONTROL ACTIONS ====================
def render_bot_control(chat_id, bot_id, msg_id=None):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM hosted_bots WHERE id = ?", (bot_id,))
    b = cursor.fetchone()
    conn.close()

    if not b:
        bot.send_message(chat_id, "❌ Bot process not found.")
        return

    is_running = False
    if b['status'] == 'running' and b['pid'] and is_process_alive(b['pid']):
        is_running = True

    status_icon = "🟢 Running" if is_running else "🔴 Stopped"

    msg = (
        f"🤖 **Bot Control Panel**\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📄 **File:** `{b['filename']}`\n"
        f"📊 **Status:** {status_icon}\n"
        f"🆔 **PID:** `{b['pid'] if is_running else 'N/A'}`\n"
        f"━━━━━━━━━━━━━━━━━━━"
    )

    markup = types.InlineKeyboardMarkup(row_width=2)
    if is_running:
        markup.add(types.InlineKeyboardButton("🛑 Stop Bot", callback_data=f"stopbot_{b['id']}"))
    else:
        markup.add(types.InlineKeyboardButton("▶️ Start Bot", callback_data=f"startbot_{b['id']}"))

    markup.add(
        types.InlineKeyboardButton("📜 Live Logs", callback_data=f"logbot_{b['id']}"),
        types.InlineKeyboardButton("🧹 Clear Logs", callback_data=f"clearlog_{b['id']}")
    )
    markup.add(
        types.InlineKeyboardButton("📋 Pip Packages", callback_data=f"piplist_{b['id']}"),
        types.InlineKeyboardButton("🔄 Refresh Panel", callback_data=f"manage_{b['id']}")
    )
    markup.add(types.InlineKeyboardButton("🗑️ Delete Bot", callback_data=f"delbot_{b['id']}"))
    markup.add(types.InlineKeyboardButton("🔙 My Hosted Bots", callback_data="my_bots"))

    send_or_edit(chat_id, msg, markup, msg_id)

def start_bot_action(chat_id, bot_id, msg_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM hosted_bots WHERE id = ?", (bot_id,))
    b = cursor.fetchone()

    if b and (not b['pid'] or not is_process_alive(b['pid'])):
        try:
            log_file = open(b['logpath'], 'a', encoding='utf-8')
            process = subprocess.Popen(
                [sys.executable, "-u", b['filepath']],
                stdout=log_file,
                stderr=log_file,
                cwd=os.path.dirname(b['filepath'])
            )
            log_file.close()
            cursor.execute("UPDATE hosted_bots SET status = 'running', pid = ? WHERE id = ?", (process.pid, bot_id))
            conn.commit()
        except Exception:
            pass
    conn.close()
    render_bot_control(chat_id, bot_id, msg_id)

def stop_bot_action(chat_id, bot_id, msg_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM hosted_bots WHERE id = ?", (bot_id,))
    b = cursor.fetchone()

    if b and b['pid']:
        try:
            if is_process_alive(b['pid']):
                os.kill(b['pid'], 9)
        except Exception:
            pass

    cursor.execute("UPDATE hosted_bots SET status = 'stopped', pid = NULL WHERE id = ?", (bot_id,))
    conn.commit()
    conn.close()
    render_bot_control(chat_id, bot_id, msg_id)

def show_logs_action(chat_id, bot_id, msg_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM hosted_bots WHERE id = ?", (bot_id,))
    b = cursor.fetchone()
    conn.close()

    if not b or not os.path.exists(b['logpath']):
        bot.send_message(chat_id, "❌ Log file missing.")
        return

    try:
        with open(b['logpath'], 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            last_lines = "".join(lines[-35:])
            
        if not last_lines.strip():
            last_lines = "No logs recorded yet."

        msg = f"📜 **Live Logs for `{b['filename']}`:**\n```\n{last_lines[:3500]}\n```"
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("🔄 Refresh Logs", callback_data=f"logbot_{bot_id}"),
            types.InlineKeyboardButton("🧹 Clear Logs", callback_data=f"clearlog_{bot_id}")
        )
        markup.add(types.InlineKeyboardButton("🔙 Back to Management", callback_data=f"manage_{bot_id}"))
        send_or_edit(chat_id, msg, markup, msg_id)
    except Exception as e:
        bot.send_message(chat_id, f"❌ Error: `{str(e)}`")

def clear_logs_action(chat_id, bot_id, msg_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT logpath FROM hosted_bots WHERE id = ?", (bot_id,))
    b = cursor.fetchone()
    conn.close()

    if b and os.path.exists(b['logpath']):
        try:
            with open(b['logpath'], 'w', encoding='utf-8') as f:
                f.write("")
        except Exception:
            pass
    show_logs_action(chat_id, bot_id, msg_id)

def show_pip_action(chat_id, bot_id, msg_id):
    try:
        res = subprocess.run([sys.executable, "-m", "pip", "list"], capture_output=True, text=True)
        packages = res.stdout[:3000]
        msg = f"📋 **Installed Python Packages:**\n```\n{packages}\n```"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Back to Management", callback_data=f"manage_{bot_id}"))
        send_or_edit(chat_id, msg, markup, msg_id)
    except Exception as e:
        bot.send_message(chat_id, f"❌ Error: `{str(e)}`")

def delete_bot_action(chat_id, bot_id, msg_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT filepath, logpath, pid FROM hosted_bots WHERE id = ?", (bot_id,))
    b = cursor.fetchone()

    if b:
        if b['pid'] and is_process_alive(b['pid']):
            try:
                os.kill(b['pid'], 9)
            except Exception:
                pass
        if os.path.exists(b['filepath']): 
            try: os.remove(b['filepath'])
            except Exception: pass
        if os.path.exists(b['logpath']): 
            try: os.remove(b['logpath'])
            except Exception: pass

    cursor.execute("DELETE FROM hosted_bots WHERE id = ?", (bot_id,))
    conn.commit()
    conn.close()

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 My Hosted Bots", callback_data="my_bots"))
    send_or_edit(chat_id, "🗑️ **Bot script and logs deleted successfully.**", markup, msg_id)



# ==================== HIGH PERFORMANCE POLLING ====================
if __name__ == "__main__":
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is required.")
    if ADMIN_ID <= 0:
        raise RuntimeError("ADMIN_ID environment variable is required.")

    print("Python Hosting Server is running...")
    print(f"Host Bot: @{bot.get_me().username}")
    print(f"Admin ID: {ADMIN_ID}")

    bot.infinity_polling(
        skip_pending=True,
        timeout=20,
        long_polling_timeout=10
    )

