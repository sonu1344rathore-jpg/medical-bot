import os
import json
import logging
import gspread
from google.oauth2.service_account import Credentials
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CONFIG
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BOT_TOKEN   = os.environ["BOT_TOKEN"]
OWNER_ID    = int(os.environ["OWNER_ID"])
SHEET_ID    = os.environ["SHEET_ID"]
CREDS_INFO  = json.loads(os.environ["GOOGLE_CREDS"])

# Your group's "Study Material" topic/section thread ID
# Set this after checking (instructions below)
STUDY_THREAD_ID = int(os.environ.get("STUDY_THREAD_ID", "0"))

logging.basicConfig(format="%(asctime)s — %(levelname)s — %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

WAITING_FILE = 1
WAITING_NAME = 2

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  GOOGLE SHEETS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_workbook():
    creds = Credentials.from_service_account_info(
        CREDS_INFO, scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    return gspread.authorize(creds).open_by_key(SHEET_ID)

def get_sheet(name, headers):
    wb = get_workbook()
    try:
        return wb.worksheet(name)
    except Exception:
        ws = wb.add_worksheet(name, 1000, len(headers))
        ws.append_row(headers)
        return ws

def materials_sheet():
    return get_sheet("Materials", ["name", "file_id", "file_type"])

def admins_sheet():
    return get_sheet("Admins", ["user_id", "username"])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ADMIN HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_admin_ids():
    try:
        return [int(r["user_id"]) for r in admins_sheet().get_all_records() if r.get("user_id")]
    except Exception:
        return []

def is_admin(uid): return uid == OWNER_ID or uid in get_admin_ids()

def add_admin(uid, uname):
    if uid in get_admin_ids(): return False
    admins_sheet().append_row([uid, uname])
    return True

def remove_admin(uid):
    sh = admins_sheet()
    cell = sh.find(str(uid))
    if cell:
        sh.delete_rows(cell.row)
        return True
    return False

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  MATERIAL HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def load_materials():
    try:
        return {
            r["name"]: {"file_id": r["file_id"], "file_type": r["file_type"]}
            for r in materials_sheet().get_all_records() if r.get("name")
        }
    except Exception:
        return {}

def save_material(name, file_id, file_type):
    try:
        materials_sheet().append_row([name, file_id, file_type])
        return True
    except Exception:
        return False

def delete_material(name):
    try:
        sh = materials_sheet()
        cell = sh.find(name)
        if cell:
            sh.delete_rows(cell.row)
            return True
        return False
    except Exception:
        return False

def smart_search(query):
    db = load_materials()
    q  = query.lower().strip()
    words = [w for w in q.split() if len(w) > 1]
    seen, results = set(), []
    for key, val in db.items():
        k = key.lower()
        score = 0
        if k == q: score = 3
        elif q in k or k in q: score = 2
        elif any(w in k for w in words): score = 1
        if score:
            results.append((score, key, val))
    results.sort(reverse=True)
    out = []
    for _, key, val in results:
        if key not in seen:
            seen.add(key)
            out.append((key, val))
    return out[:10]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SEND FILE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def send_file(msg, name, material):
    fid  = material["file_id"]
    ft   = material["file_type"]
    cap  = f"📚 *{name}*\n_Obsessed With Medical_ 🏥"
    try:
        if ft == "document": await msg.reply_document(fid, caption=cap, parse_mode="Markdown")
        elif ft == "photo":  await msg.reply_photo(fid, caption=cap, parse_mode="Markdown")
        elif ft == "video":  await msg.reply_video(fid, caption=cap, parse_mode="Markdown")
        elif ft == "audio":  await msg.reply_audio(fid, caption=cap, parse_mode="Markdown")
        elif ft == "voice":  await msg.reply_voice(fid, caption=cap, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"send_file: {e}")
        await msg.reply_text("❌ Could not send file. Please contact admin.")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  COMMANDS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏥 *Obsessed With Medical*\n\n"
        "Your personal NEET study assistant.\n"
        "Search any topic or teacher name and get the material instantly!\n\n"
        "📋 /list — See all available material\n"
        "❓ /help — All commands",
        parse_mode="Markdown"
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = (
        "📋 *Commands*\n\n"
        "/start — Start the bot\n"
        "/list — All available material\n"
        "/help — This message\n"
    )
    if is_admin(uid):
        text += (
            "\n🛡️ *Admin*\n"
            "/upload — Upload new material\n"
            "/delete `name` — Delete material\n"
            "/admins — View admin list\n"
        )
    if uid == OWNER_ID:
        text += (
            "\n👑 *Owner*\n"
            "Reply to a message + /addadmin — Make admin\n"
            "Reply to a message + /removeadmin — Remove admin\n"
        )
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = load_materials()
    if not db:
        await update.message.reply_text("📭 No material available yet.")
        return
    lines = ["📚 *Available Material*\n"]
    for i, key in enumerate(sorted(db.keys()), 1):
        lines.append(f"{i}. {key}")
    lines.append(f"\n_Total: {len(db)} files_")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  UPLOAD FLOW (no confirmation)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def cmd_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Admins only.")
        return ConversationHandler.END
    await update.message.reply_text("📤 Send the file now.\n_/cancel to stop_", parse_mode="Markdown")
    return WAITING_FILE

async def receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    msg = update.message
    file_id = file_type = None
    if msg.document: file_id, file_type = msg.document.file_id, "document"
    elif msg.photo:  file_id, file_type = msg.photo[-1].file_id, "photo"
    elif msg.video:  file_id, file_type = msg.video.file_id, "video"
    elif msg.audio:  file_id, file_type = msg.audio.file_id, "audio"
    elif msg.voice:  file_id, file_type = msg.voice.file_id, "voice"
    if not file_id:
        await msg.reply_text("❌ No file found. Try again.")
        return WAITING_FILE
    context.user_data["fid"]  = file_id
    context.user_data["ftype"] = file_type
    await msg.reply_text("✅ File received! Now send the *name* for this material.", parse_mode="Markdown")
    return WAITING_NAME

async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    name  = update.message.text.strip()
    fid   = context.user_data.get("fid")
    ftype = context.user_data.get("ftype")
    if not name or not fid:
        await update.message.reply_text("❌ Something went wrong. Use /upload again.")
        return ConversationHandler.END
    ok = save_material(name, fid, ftype)
    context.user_data.clear()
    if ok:
        await update.message.reply_text(f"✅ *{name}* uploaded successfully!", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Failed to save. Try again.")
    return ConversationHandler.END

async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  DELETE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def cmd_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Admins only.")
        return
    if not context.args:
        await update.message.reply_text("Usage: `/delete Material Name`", parse_mode="Markdown")
        return
    name = " ".join(context.args)
    if delete_material(name):
        await update.message.reply_text(f"🗑️ *{name}* deleted.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ `{name}` not found.", parse_mode="Markdown")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ADMIN MANAGEMENT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def cmd_addadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ Owner only.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to someone's message and use /addadmin.")
        return
    t     = update.message.reply_to_message.from_user
    tname = f"@{t.username}" if t.username else t.first_name
    if add_admin(t.id, tname):
        await update.message.reply_text(f"✅ *{tname}* is now an admin.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"⚠️ *{tname}* is already an admin.", parse_mode="Markdown")

async def cmd_removeadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ Owner only.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to someone's message and use /removeadmin.")
        return
    t     = update.message.reply_to_message.from_user
    tname = f"@{t.username}" if t.username else t.first_name
    if remove_admin(t.id):
        await update.message.reply_text(f"🗑️ *{tname}* removed from admins.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ *{tname}* is not an admin.", parse_mode="Markdown")

async def cmd_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    ids = get_admin_ids()
    lines = [f"👑 Owner: `{OWNER_ID}`"]
    if ids:
        lines += [f"🛡️ Admin: `{i}`" for i in ids]
    else:
        lines.append("No extra admins yet.")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SMART SEARCH — GROUP FILTER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg       = update.message
    if not msg: return
    text      = msg.text or ""
    chat_type = update.effective_chat.type
    bot_user  = context.bot.username
    tagged    = f"@{bot_user}" in text
    query     = text.replace(f"@{bot_user}", "").strip()

    if not query or query.startswith("/"): return

    is_private = chat_type == "private"
    is_group   = chat_type in ("group", "supergroup")

    # Group mein sirf 3 cases mein respond:
    # 1. Bot tagged ho
    # 2. Study Material thread/section ho (STUDY_THREAD_ID)
    # 3. DM (private)
    if is_group and not tagged:
        thread_id = getattr(msg, "message_thread_id", None)
        if STUDY_THREAD_ID == 0 or thread_id != STUDY_THREAD_ID:
            return

    results = smart_search(query)

    if not results:
        if tagged or is_private:
            await msg.reply_text(
                f"❌ *'{query}'* not found in our collection.\n\n"
                f"📋 See what's available: /list\n"
                f"_— Obsessed With Medical_ 🏥",
                parse_mode="Markdown"
            )
        return

    # Single result
    if len(results) == 1:
        await send_file(msg, results[0][0], results[0][1])
        return

    # Multiple results — buttons
    keyboard = [[InlineKeyboardButton(f"📄 {k}", callback_data=f"get:{k}")] for k, _ in results]
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
    await msg.reply_text(
        f"🔍 *{len(results)} results for '{query}'*\nSelect one:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  BUTTON HANDLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    data = q.data
    await q.answer()

    if data == "cancel":
        await q.edit_message_text("❌ Cancelled.")
        return

    if data.startswith("get:"):
        name = data[4:]
        db   = load_materials()
        if name in db:
            await q.edit_message_text(f"⚡ Sending *{name}*...", parse_mode="Markdown")
            await send_file(q.message, name, db[name])
        else:
            await q.edit_message_text("❌ File not found. Try searching again.")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  BOT COMMANDS MENU
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def set_commands(app: Application):
    await app.bot.set_my_commands([
        BotCommand("start",       "Start the bot"),
        BotCommand("list",        "All available material"),
        BotCommand("help",        "Commands & help"),
        BotCommand("upload",      "Upload new material"),
        BotCommand("delete",      "Delete material"),
        BotCommand("addadmin",    "Add admin (Owner only)"),
        BotCommand("removeadmin", "Remove admin (Owner only)"),
        BotCommand("admins",      "View admin list"),
        BotCommand("cancel",      "Cancel current operation"),
    ])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  MAIN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main():
    app = Application.builder().token(BOT_TOKEN).post_init(set_commands).build()

    upload_conv = ConversationHandler(
        entry_points=[CommandHandler("upload", cmd_upload)],
        states={
            WAITING_FILE: [MessageHandler(
                filters.Document.ALL | filters.PHOTO | filters.VIDEO | filters.AUDIO | filters.VOICE,
                receive_file
            )],
            WAITING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
    )

    app.add_handler(CommandHandler("start",       cmd_start))
    app.add_handler(CommandHandler("help",        cmd_help))
    app.add_handler(CommandHandler("list",        cmd_list))
    app.add_handler(CommandHandler("delete",      cmd_delete))
    app.add_handler(CommandHandler("addadmin",    cmd_addadmin))
    app.add_handler(CommandHandler("removeadmin", cmd_removeadmin))
    app.add_handler(CommandHandler("admins",      cmd_admins))
    app.add_handler(upload_conv)
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("🏥 Obsessed With Medical Bot — Online!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
