import os
import json
import logging
import gspread
from google.oauth2.service_account import Credentials
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# ─── CONFIG FROM ENVIRONMENT VARIABLES ───────────────────────────────────────

BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_IDS = [int(x) for x in os.environ["ADMIN_IDS"].split(",")]
SHEET_ID  = os.environ["SHEET_ID"]
CREDS_INFO = json.loads(os.environ["GOOGLE_CREDS"])

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

WAITING_FOR_NAME = 1

# ─── GOOGLE SHEETS ────────────────────────────────────────────────────────────

def get_sheet():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds  = Credentials.from_service_account_info(CREDS_INFO, scopes=scopes)
    gc     = gspread.authorize(creds)
    sh     = gc.open_by_key(SHEET_ID)
    return sh.sheet1

def load_db() -> dict:
    try:
        sheet = get_sheet()
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
        logger.error(f"Sheet load error: {e}")
        return {}

def save_to_sheet(name, file_id, file_type):
    try:
        sheet = get_sheet()
        sheet.append_row([name, file_id, file_type])
        return True
    except Exception as e:
        logger.error(f"Sheet save error: {e}")
        return False

def delete_from_sheet(name):
    try:
        sheet = get_sheet()
        cell  = sheet.find(name)
        if cell:
            sheet.delete_rows(cell.row)
            return True
        return False
    except Exception as e:
        logger.error(f"Sheet delete error: {e}")
        return False

def find_material(query):
    db = load_db()
    query_lower = query.lower().strip()
    for key, val in db.items():
        if key.lower() == query_lower:
            return key, val
    for key, val in db.items():
        if query_lower in key.lower() or key.lower() in query_lower:
            return key, val
    return None, None

def is_admin(user_id):
    return user_id in ADMIN_IDS

# ─── COMMANDS ────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🏥 *Obsessed With Medical Bot*\n\n"
        "📚 Kisi bhi study material ke liye bas naam likho!\n\n"
        "*Example:*\n"
        "• `Physics Notes`\n"
        "• `Biology NCERT`\n"
        "• `Chemistry PYQ`\n\n"
        "📋 Saari files dekhne ke liye: /list\n\n"
        "🔴 *Admins ke liye:* /upload"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def list_materials(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    if not db:
        await update.message.reply_text("📭 Abhi koi material available nahi hai.\nJald hi add hoga! 🔜")
        return
    lines = ["📚 *Available Study Materials:*\n"]
    for i, key in enumerate(sorted(db.keys()), 1):
        lines.append(f"{i}. {key}")
    lines.append("\n✏️ Koi bhi naam likhoge to file mil jaayegi!")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ─── UPLOAD FLOW ─────────────────────────────────────────────────────────────

async def upload_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Sirf admins upload kar sakte hain.")
        return ConversationHandler.END
    await update.message.reply_text(
        "📤 *Upload Mode*\n\nAb file bhejo (PDF, image, video, kuch bhi).\nBhejne ke baad naam puchunga! 📝",
        parse_mode="Markdown"
    )
    return WAITING_FOR_NAME

async def receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    msg = update.message
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
        await msg.reply_text("❌ Koi file nahi mili. Dobara try karo.")
        return ConversationHandler.END

    context.user_data["pending_file_id"]   = file_id
    context.user_data["pending_file_type"] = file_type

    await msg.reply_text(
        "✅ File mil gayi!\n\n📝 *Ab is file ka naam batao:*\n_(Jis naam se students search karenge)_",
        parse_mode="Markdown"
    )
    return WAITING_FOR_NAME

async def save_file_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    name      = update.message.text.strip()
    file_id   = context.user_data.get("pending_file_id")
    file_type = context.user_data.get("pending_file_type")

    if not name or not file_id:
        await update.message.reply_text("❌ Kuch gadbad ho gayi. /upload se dobara shuru karo.")
        return ConversationHandler.END

    success = save_to_sheet(name, file_id, file_type)
    context.user_data.clear()

    if success:
        await update.message.reply_text(
            f"🎉 *File save ho gayi!*\n\n📁 Naam: *{name}*\n\nAb koi bhi `{name}` likhega to yeh file mil jaayegi! ✅",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ Save nahi hua. Dobara try karo.")
    return ConversationHandler.END

async def cancel_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Upload cancel ho gaya.")
    return ConversationHandler.END

# ─── DELETE ──────────────────────────────────────────────────────────────────

async def delete_material(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Sirf admins delete kar sakte hain.")
        return
    if not context.args:
        await update.message.reply_text("Usage: `/delete Material Ka Naam`", parse_mode="Markdown")
        return
    name    = " ".join(context.args)
    deleted = delete_from_sheet(name)
    if deleted:
        await update.message.reply_text(f"🗑️ *{name}* delete ho gaya!", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ `{name}` nahi mila.", parse_mode="Markdown")

# ─── MATERIAL REQUEST ─────────────────────────────────────────────────────────

async def handle_text_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg          = update.message
    text         = msg.text or ""
    chat_type    = update.effective_chat.type
    bot_username = context.bot.username
    bot_tagged   = f"@{bot_username}" in text
    query        = text.replace(f"@{bot_username}", "").strip()

    if not query or query.startswith("/"):
        return

    should_respond = (chat_type == "private") or bot_tagged or len(query) >= 3
    if not should_respond:
        return

    matched_key, material = find_material(query)

    if material:
        file_id   = material["file_id"]
        file_type = material["file_type"]
        caption   = f"📚 *{matched_key}*\n\n_Obsessed With Medical_ 🏥"
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
            await msg.reply_text("❌ File send karne me error aaya.")

    elif bot_tagged:
        await msg.reply_text(
            f"😔 *Sorry!*\n\n*{query}* abhi available nahi hai.\n\n"
            f"🔜 Jald hi upload hoga!\n\n📋 Available materials: /list\n\n"
            f"— *Obsessed With Medical Team* 🏥",
            parse_mode="Markdown"
        )

# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    upload_conv = ConversationHandler(
        entry_points=[CommandHandler("upload", upload_command)],
        states={
            WAITING_FOR_NAME: [
                MessageHandler(
                    filters.Document.ALL | filters.PHOTO | filters.VIDEO |
                    filters.AUDIO | filters.VOICE,
                    receive_file
                ),
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_file_name),
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel_upload)],
    )

    app.add_handler(CommandHandler("start",  start))
    app.add_handler(CommandHandler("list",   list_materials))
    app.add_handler(CommandHandler("delete", delete_material))
    app.add_handler(upload_conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_request))

    logger.info("Bot chal raha hai...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
