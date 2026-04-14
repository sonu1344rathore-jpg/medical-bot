import os
import json
import logging
import gspread
from google.oauth2.service_account import Credentials
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ─── CONFIG ───────────────────────────────────────────────────────────────────

BOT_TOKEN  = os.environ["BOT_TOKEN"]
OWNER_ID   = int(os.environ["OWNER_ID"])
SHEET_ID   = os.environ["SHEET_ID"]
CREDS_INFO = json.loads(os.environ["GOOGLE_CREDS"])

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
WAITING_FILE = 1
WAITING_NAME = 2

# ─── GOOGLE SHEETS ────────────────────────────────────────────────────────────

def get_workbook():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds  = Credentials.from_service_account_info(CREDS_INFO, scopes=scopes)
    gc     = gspread.authorize(creds)
    return gc.open_by_key(SHEET_ID)

def get_materials_sheet():
    wb = get_workbook()
    try:
        return wb.worksheet("Materials")
    except:
        ws = wb.add_worksheet("Materials", 1000, 3)
        ws.append_row(["name", "file_id", "file_type"])
        return ws

def get_admins_sheet():
    wb = get_workbook()
    try:
        return wb.worksheet("Admins")
    except:
        ws = wb.add_worksheet("Admins", 100, 2)
        ws.append_row(["user_id", "username"])
        return ws

# ─── ADMIN HELPERS ────────────────────────────────────────────────────────────

def get_all_admins() -> list:
    try:
        sheet = get_admins_sheet()
        rows  = sheet.get_all_records()
        return [int(r["user_id"]) for r in rows if r.get("user_id")]
    except:
        return []

def is_admin(user_id: int) -> bool:
    if user_id == OWNER_ID:
        return True
    return user_id in get_all_admins()

def add_admin(user_id: int, username: str) -> bool:
    try:
        admins = get_all_admins()
        if user_id in admins:
            return False
        sheet = get_admins_sheet()
        sheet.append_row([user_id, username])
        return True
    except Exception as e:
        logger.error(f"Add admin error: {e}")
        return False

def remove_admin(user_id: int) -> bool:
    try:
        sheet = get_admins_sheet()
        cell  = sheet.find(str(user_id))
        if cell:
            sheet.delete_rows(cell.row)
            return True
        return False
    except Exception as e:
        logger.error(f"Remove admin error: {e}")
        return False

# ─── MATERIAL HELPERS ─────────────────────────────────────────────────────────

def load_materials() -> dict:
    try:
        sheet = get_materials_sheet()
        rows  = sheet.get_all_records()
        db = {}
        for row in rows:
            if row.get("name"):
                db[row["name"]] = {
                    "file_id":   row["file_id"],
                    "file_type": row["file_type"]
                }
        return db
    except Exception as e:
        logger.error(f"Load materials error: {e}")
        return {}

def save_material(name: str, file_id: str, file_type: str) -> bool:
    try:
        sheet = get_materials_sheet()
        sheet.append_row([name, file_id, file_type])
        return True
    except Exception as e:
        logger.error(f"Save material error: {e}")
        return False

def delete_material_db(name: str) -> bool:
    try:
        sheet = get_materials_sheet()
        cell  = sheet.find(name)
        if cell:
            sheet.delete_rows(cell.row)
            return True
        return False
    except Exception as e:
        logger.error(f"Delete material error: {e}")
        return False

def search_materials(query: str) -> list:
    """Smart search — returns list of (key, material) tuples that match."""
    db = load_materials()
    query_lower = query.lower().strip()
    results = []

    for key, val in db.items():
        key_lower = key.lower()
        if (query_lower in key_lower or
            key_lower in query_lower or
            any(word in key_lower for word in query_lower.split() if len(word) > 2)):
            results.append((key, val))

    return results

# ─── PREMIUM MESSAGES ─────────────────────────────────────────────────────────

WELCOME = (
    "🏥 *Obsessed With Medical*\n"
    "━━━━━━━━━━━━━━━━━━━━━\n\n"
    "Namaste! Main hoon aapka personal study assistant. 🎯\n\n"
    "📚 *Kaise use karein?*\n"
    "Bas koi bhi topic ya teacher ka naam likhein —\n"
    "jaise `MR Sir`, `Biology Notes`, `Chemistry PYQ`\n\n"
    "Main turant best match dhundh ke deta hoon! ⚡\n\n"
    "📋 Saara available material dekhne ke liye:\n"
    "👉 /list\n\n"
    "━━━━━━━━━━━━━━━━━━━━━\n"
    "_Study hard, dream big! 🚀_"
)

SORRY = (
    "😔 *Abhi Available Nahi Hai*\n"
    "━━━━━━━━━━━━━━━━━━━━━\n\n"
    "Aapne jo maanga — *{}* — abhi hamare collection mein nahi hai.\n\n"
    "🔜 *Jald hi upload hoga!*\n"
    "Hamari team constantly naya material add karti rehti hai.\n\n"
    "📋 Jo abhi available hai dekhne ke liye:\n"
    "👉 /list\n\n"
    "━━━━━━━━━━━━━━━━━━━━━\n"
    "_— Obsessed With Medical Team_ 🏥"
)

# ─── COMMANDS ────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(WELCOME, parse_mode="Markdown")

async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = load_materials()
    if not db:
        await update.message.reply_text(
            "📭 *Abhi koi material available nahi hai.*\n\nJald hi add hoga! 🔜",
            parse_mode="Markdown"
        )
        return

    lines = [
        "📚 *Available Study Material*",
        "━━━━━━━━━━━━━━━━━━━━━\n"
    ]
    for i, key in enumerate(sorted(db.keys()), 1):
        lines.append(f"  {i}. {key}")

    lines.append("\n━━━━━━━━━━━━━━━━━━━━━")
    lines.append("_Koi bhi naam likhein, file turant milegi! ⚡_")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ─── UPLOAD FLOW ─────────────────────────────────────────────────────────────

async def upload_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(
            "⛔ *Access Denied*\n\nSirf authorized admins hi material upload kar sakte hain.",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "📤 *Upload Mode — Activated*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Ab file bhejein — PDF, Image, Video, Audio, kuch bhi!\n\n"
        "_Cancel karne ke liye /cancel likhein_",
        parse_mode="Markdown"
    )
    return WAITING_FILE

async def receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    msg     = update.message
    file_id = file_type = None

    if msg.document:
        file_id, file_type = msg.document.file_id, "document"
    elif msg.photo:
        file_id, file_type = msg.photo[-1].file_id, "photo"
    elif msg.video:
        file_id, file_type = msg.video.file_id, "video"
    elif msg.audio:
        file_id, file_type = msg.audio.file_id, "audio"
    elif msg.voice:
        file_id, file_type = msg.voice.file_id, "voice"

    if not file_id:
        await msg.reply_text("❌ Koi file nahi mili. Dobara try karein.")
        return WAITING_FILE

    context.user_data["pending_file_id"]   = file_id
    context.user_data["pending_file_type"] = file_type

    await msg.reply_text(
        "✅ *File Received!*\n\n"
        "📝 Ab is file ka naam likhein:\n"
        "_Jis naam se students search karenge_\n\n"
        "Example: `MR Sir — Thermodynamics Notes`",
        parse_mode="Markdown"
    )
    return WAITING_NAME

async def save_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    name      = update.message.text.strip()
    file_id   = context.user_data.get("pending_file_id")
    file_type = context.user_data.get("pending_file_type")

    if not name or not file_id:
        await update.message.reply_text("❌ Kuch gadbad ho gayi. /upload se dobara shuru karein.")
        return ConversationHandler.END

    success = save_material(name, file_id, file_type)
    context.user_data.clear()

    if success:
        await update.message.reply_text(
            f"🎉 *Successfully Saved!*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📁 *Naam:* {name}\n"
            f"📂 *Type:* {file_type}\n\n"
            f"Ab koi bhi `{name}` search karega to yeh file turant milegi! ⚡",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ Save nahi hua. Dobara try karein.")
    return ConversationHandler.END

async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ *Operation cancelled.*", parse_mode="Markdown")
    return ConversationHandler.END

# ─── DELETE ──────────────────────────────────────────────────────────────────

async def delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ *Access Denied*", parse_mode="Markdown")
        return

    if not context.args:
        await update.message.reply_text(
            "📝 *Usage:* `/delete Material Ka Naam`\n\nExample: `/delete MR Sir Notes`",
            parse_mode="Markdown"
        )
        return

    name    = " ".join(context.args)
    deleted = delete_material_db(name)

    if deleted:
        await update.message.reply_text(
            f"🗑️ *Deleted Successfully!*\n\n`{name}` remove kar diya gaya.",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            f"❌ `{name}` naam ka koi material nahi mila.",
            parse_mode="Markdown"
        )

# ─── ADMIN MANAGEMENT ────────────────────────────────────────────────────────

async def addadmin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ *Sirf Owner hi admin add kar sakta hai.*", parse_mode="Markdown")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "📝 *Kisi ke message pe reply karke /addadmin likhein.*\n\n"
            "_Jise admin banana ho uske kisi bhi message pe reply karein._",
            parse_mode="Markdown"
        )
        return

    target      = update.message.reply_to_message.from_user
    target_id   = target.id
    target_name = target.username or target.first_name

    if target_id == OWNER_ID:
        await update.message.reply_text("👑 *Yeh pehle se hi Owner hain!*", parse_mode="Markdown")
        return

    success = add_admin(target_id, target_name)

    if success:
        await update.message.reply_text(
            f"✅ *Admin Added!*\n\n"
            f"👤 *{target_name}* ko ab bot admin bana diya gaya hai.\n"
            f"Ab woh material upload/delete kar sakte hain! 🎯",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            f"⚠️ *{target_name}* pehle se admin hain!",
            parse_mode="Markdown"
        )

async def removeadmin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ *Sirf Owner hi admin remove kar sakta hai.*", parse_mode="Markdown")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "📝 *Kisi ke message pe reply karke /removeadmin likhein.*",
            parse_mode="Markdown"
        )
        return

    target      = update.message.reply_to_message.from_user
    target_id   = target.id
    target_name = target.username or target.first_name

    success = remove_admin(target_id)

    if success:
        await update.message.reply_text(
            f"🗑️ *Admin Removed!*\n\n*{target_name}* ki admin access remove kar di gayi.",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            f"❌ *{target_name}* admin list mein nahi hain.",
            parse_mode="Markdown"
        )

async def admins_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    admin_ids = get_all_admins()
    lines = [
        "👥 *Bot Admins List*",
        "━━━━━━━━━━━━━━━━━━━━━\n",
        f"👑 Owner: `{OWNER_ID}`\n"
    ]

    if admin_ids:
        lines.append("🛡️ *Admins:*")
        for uid in admin_ids:
            lines.append(f"  • `{uid}`")
    else:
        lines.append("_Koi extra admin nahi hai abhi._")

    lines.append("\n━━━━━━━━━━━━━━━━━━━━━")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ─── SMART SEARCH WITH BUTTONS ────────────────────────────────────────────────

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg          = update.message
    text         = msg.text or ""
    chat_type    = update.effective_chat.type
    bot_username = context.bot.username
    bot_tagged   = f"@{bot_username}" in text
    query        = text.replace(f"@{bot_username}", "").strip()

    if not query or query.startswith("/"):
        return

    # Private chat mein hamesha respond, group mein sirf 3+ chars ya tag
    if chat_type != "private" and not bot_tagged and len(query) < 3:
        return

    results = search_materials(query)

    if not results:
        if bot_tagged or chat_type == "private":
            await msg.reply_text(SORRY.format(query), parse_mode="Markdown")
        return

    # Ek hi result mila — seedha file bhejo
    if len(results) == 1:
        key, material = results[0]
        await send_file(msg, key, material)
        return

    # Multiple results — buttons show karo
    keyboard = []
    for key, _ in results[:8]:  # max 8 buttons
        keyboard.append([InlineKeyboardButton(f"📄 {key}", callback_data=f"get:{key}")])

    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])

    await msg.reply_text(
        f"🔍 *'{query}' ke liye {len(results)} results mile!*\n\n"
        f"Niche se select karein jo chahiye:\n"
        f"━━━━━━━━━━━━━━━━━━━━━",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query    = update.callback_query
    await query.answer()
    data     = query.data

    if data == "cancel":
        await query.edit_message_text("❌ *Cancelled.*", parse_mode="Markdown")
        return

    if data.startswith("get:"):
        name = data[4:]
        db   = load_materials()

        if name in db:
            await query.edit_message_text(
                f"⚡ *Sending:* `{name}`...",
                parse_mode="Markdown"
            )
            await send_file(query.message, name, db[name])
        else:
            await query.edit_message_text(
                "❌ *File nahi mili.* Dobara try karein.",
                parse_mode="Markdown"
            )

async def send_file(msg, name: str, material: dict):
    file_id   = material["file_id"]
    file_type = material["file_type"]
    caption   = (
        f"📚 *{name}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"_Obsessed With Medical_ 🏥\n"
        f"_Study hard, crack NEET! 🎯_"
    )
    try:
        if file_type == "document":
            await msg.reply_document(file_id, caption=caption, parse_mode="Markdown")
        elif file_type == "photo":
            await msg.reply_photo(file_id, caption=caption, parse_mode="Markdown")
        elif file_type == "video":
            await msg.reply_video(file_id, caption=caption, parse_mode="Markdown")
        elif file_type == "audio":
            await msg.reply_audio(file_id, caption=caption, parse_mode="Markdown")
        elif file_type == "voice":
            await msg.reply_voice(file_id, caption=caption, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Send error: {e}")
        await msg.reply_text("❌ File send karne mein error aaya. Admin se contact karein.")

# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    upload_conv = ConversationHandler(
        entry_points=[CommandHandler("upload", upload_cmd)],
        states={
            WAITING_FILE: [
                MessageHandler(
                    filters.Document.ALL | filters.PHOTO | filters.VIDEO |
                    filters.AUDIO | filters.VOICE,
                    receive_file
                ),
            ],
            WAITING_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_name),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_cmd)],
    )

    app.add_handler(CommandHandler("start",       start))
    app.add_handler(CommandHandler("list",        list_cmd))
    app.add_handler(CommandHandler("delete",      delete_cmd))
    app.add_handler(CommandHandler("addadmin",    addadmin_cmd))
    app.add_handler(CommandHandler("removeadmin", removeadmin_cmd))
    app.add_handler(CommandHandler("admins",      admins_cmd))
    app.add_handler(upload_conv)
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("🏥 Obsessed With Medical Bot — Online!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
