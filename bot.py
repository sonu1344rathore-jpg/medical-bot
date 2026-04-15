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

BOT_TOKEN  = os.environ["BOT_TOKEN"]
OWNER_ID   = int(os.environ["OWNER_ID"])
SHEET_ID   = os.environ["SHEET_ID"]
CREDS_INFO = json.loads(os.environ["GOOGLE_CREDS"])

logging.basicConfig(
    format="%(asctime)s — %(levelname)s — %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

WAITING_FILE = 1
WAITING_NAME = 2

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  GOOGLE SHEETS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_workbook():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds  = Credentials.from_service_account_info(CREDS_INFO, scopes=scopes)
    gc     = gspread.authorize(creds)
    return gc.open_by_key(SHEET_ID)

def get_materials_sheet():
    wb = get_workbook()
    try:
        return wb.worksheet("Materials")
    except Exception:
        ws = wb.add_worksheet("Materials", 1000, 3)
        ws.append_row(["name", "file_id", "file_type"])
        return ws

def get_admins_sheet():
    wb = get_workbook()
    try:
        return wb.worksheet("Admins")
    except Exception:
        ws = wb.add_worksheet("Admins", 100, 2)
        ws.append_row(["user_id", "username"])
        return ws

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ADMIN HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_all_admin_ids() -> list:
    try:
        rows = get_admins_sheet().get_all_records()
        return [int(r["user_id"]) for r in rows if r.get("user_id")]
    except Exception:
        return []

def is_admin(user_id: int) -> bool:
    return user_id == OWNER_ID or user_id in get_all_admin_ids()

def add_admin_db(user_id: int, username: str) -> bool:
    try:
        if user_id in get_all_admin_ids():
            return False
        get_admins_sheet().append_row([user_id, username])
        return True
    except Exception as e:
        logger.error(f"add_admin error: {e}")
        return False

def remove_admin_db(user_id: int) -> bool:
    try:
        sheet = get_admins_sheet()
        cell  = sheet.find(str(user_id))
        if cell:
            sheet.delete_rows(cell.row)
            return True
        return False
    except Exception as e:
        logger.error(f"remove_admin error: {e}")
        return False

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  MATERIAL HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def load_all_materials() -> dict:
    try:
        rows = get_materials_sheet().get_all_records()
        return {
            r["name"]: {"file_id": r["file_id"], "file_type": r["file_type"]}
            for r in rows if r.get("name")
        }
    except Exception as e:
        logger.error(f"load_materials error: {e}")
        return {}

def save_material_db(name: str, file_id: str, file_type: str) -> bool:
    try:
        get_materials_sheet().append_row([name, file_id, file_type])
        return True
    except Exception as e:
        logger.error(f"save_material error: {e}")
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
        logger.error(f"delete_material error: {e}")
        return False

def smart_search(query: str) -> list:
    db          = load_all_materials()
    q           = query.lower().strip()
    words       = [w for w in q.split() if len(w) > 1]
    exact       = []
    partial     = []
    word_match  = []

    for key, val in db.items():
        k = key.lower()
        if k == q:
            exact.append((key, val))
        elif q in k or k in q:
            partial.append((key, val))
        elif any(w in k for w in words):
            word_match.append((key, val))

    seen    = set()
    results = []
    for item in exact + partial + word_match:
        if item[0] not in seen:
            seen.add(item[0])
            results.append(item)

    return results[:10]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SEND FILE HELPER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def send_material(msg, name: str, material: dict):
    file_id   = material["file_id"]
    file_type = material["file_type"]
    caption   = (
        f"📚 *{name}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"_Obsessed With Medical_ 🏥\n"
        f"_Study smart. Dream big. Crack NEET!_ 🎯"
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
        else:
            await msg.reply_text(f"❌ Unknown file type: {file_type}")
    except Exception as e:
        logger.error(f"send_material error: {e}")
        await msg.reply_text("❌ File send nahi ho payi. Admin se sampark karein.")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  COMMANDS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = (
        f"🏥 *Obsessed With Medical*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Namaste *{user.first_name}*! 👋\n\n"
        f"Main hoon aapka personal *NEET Study Assistant* ⚡\n\n"
        f"📌 *Kaise use karein?*\n"
        f"Koi bhi topic ya teacher ka naam likhein:\n"
        f"`MR Sir` • `Biology Notes` • `Chemistry PYQ`\n\n"
        f"Main best match dhundh ke turant de dunga! 🚀\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"_Study hard. Dream big. Crack NEET!_ 🎯"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id  = update.effective_user.id
    is_owner = user_id == OWNER_ID
    is_adm   = is_admin(user_id)

    member_cmds = (
        "👤 *Member Commands*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "/start — Bot start karein\n"
        "/list — Saara available material dekhein\n"
        "/help — Yeh help message\n"
    )

    admin_cmds = (
        "\n🛡️ *Admin Commands*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "/upload — Naya material upload karein\n"
        "/delete `naam` — Material delete karein\n"
        "/admins — Admin list dekhein\n"
    )

    owner_cmds = (
        "\n👑 *Owner Commands*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "/addadmin — Reply karke admin banayein\n"
        "/removeadmin — Reply karke admin hatayein\n"
    )

    search_info = (
        "\n🔍 *Material Search*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Group mein koi bhi naam likhein ya\n"
        "@BotUsername ke saath search karein\n\n"
        "_Example:_ `MR Sir Physics` ya\n"
        "`@ObsessedMedicalBot Chemistry Notes`"
    )

    text = member_cmds + search_info
    if is_adm:
        text += admin_cmds
    if is_owner:
        text += owner_cmds

    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = load_all_materials()
    if not db:
        await update.message.reply_text(
            "📭 *Abhi koi material available nahi hai.*\n\n"
            "Jald hi add hoga! Hamari team kaam kar rahi hai. 🔜",
            parse_mode="Markdown"
        )
        return

    lines = [
        "📚 *Available Study Material*",
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    ]
    for i, key in enumerate(sorted(db.keys()), 1):
        lines.append(f"  `{i}.` {key}")

    lines.append(f"\n━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"_Total: {len(db)} materials available_ ✅")
    lines.append(f"_Koi bhi naam likhein, file turant milegi!_ ⚡")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  UPLOAD FLOW
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def cmd_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(
            "⛔ *Access Denied*\n\nSirf authorized admins hi material upload kar sakte hain.",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "📤 *Upload Mode — Activated*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "✅ Ab file bhejein:\n"
        "PDF • Image • Video • Audio — kuch bhi!\n\n"
        "_Cancel karne ke liye_ /cancel",
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
        await msg.reply_text(
            "❌ *File nahi mili.*\n\nDobara try karein ya /cancel likhein.",
            parse_mode="Markdown"
        )
        return WAITING_FILE

    context.user_data["pending_file_id"]   = file_id
    context.user_data["pending_file_type"] = file_type

    await msg.reply_text(
        "✅ *File Received!*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📝 Ab is file ka *naam* likhein:\n"
        "_Jis naam se members search karenge_\n\n"
        "*Example:*\n"
        "`MR Sir — Thermodynamics Notes`\n"
        "`Biology NCERT Chapter 5`\n"
        "`Chemistry PYQ 2023`",
        parse_mode="Markdown"
    )
    return WAITING_NAME

async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    name      = update.message.text.strip()
    file_id   = context.user_data.get("pending_file_id")
    file_type = context.user_data.get("pending_file_type")

    if not name or not file_id:
        await update.message.reply_text(
            "❌ Kuch gadbad ho gayi. /upload se dobara shuru karein.",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    # Confirm karo pehle
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Confirm", callback_data=f"confirm_upload:{name}"),
            InlineKeyboardButton("❌ Cancel",  callback_data="cancel_upload")
        ]
    ])

    context.user_data["pending_name"] = name

    await update.message.reply_text(
        f"📋 *Confirm Upload?*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📁 *Naam:* `{name}`\n"
        f"📂 *Type:* `{file_type}`\n\n"
        f"Sahi hai?",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    return WAITING_NAME

async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "❌ *Operation cancelled.*\n\nKab bhi dobara /upload kar sakte hain.",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  DELETE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def cmd_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ *Access Denied*", parse_mode="Markdown")
        return

    if not context.args:
        await update.message.reply_text(
            "📝 *Usage:*\n`/delete Material Ka Naam`\n\n"
            "*Example:*\n`/delete MR Sir Notes`",
            parse_mode="Markdown"
        )
        return

    name = " ".join(context.args)

    # Confirm karo
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🗑️ Haan, Delete Karo", callback_data=f"confirm_delete:{name}"),
            InlineKeyboardButton("❌ Cancel",            callback_data="cancel_delete")
        ]
    ])

    await update.message.reply_text(
        f"⚠️ *Delete Confirmation*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Aap `{name}` ko *permanently delete* karna chahte hain?\n\n"
        f"Yeh action undo nahi ho sakta!",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ADMIN MANAGEMENT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def cmd_addadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ *Sirf Owner hi admin add kar sakta hai.*", parse_mode="Markdown")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "📝 *Kaise use karein?*\n\n"
            "Jise admin banana ho uske *kisi bhi message pe reply* karke\n"
            "`/addadmin` likhein.\n\n"
            "_Reply karna zaroori hai!_",
            parse_mode="Markdown"
        )
        return

    target    = update.message.reply_to_message.from_user
    tid       = target.id
    tname     = f"@{target.username}" if target.username else target.first_name

    if tid == OWNER_ID:
        await update.message.reply_text("👑 *Yeh pehle se hi Owner hain!*", parse_mode="Markdown")
        return

    if tid in get_all_admin_ids():
        await update.message.reply_text(
            f"⚠️ *{tname}* pehle se admin hain!",
            parse_mode="Markdown"
        )
        return

    # Confirm
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Admin Banao", callback_data=f"confirm_addadmin:{tid}:{tname}"),
            InlineKeyboardButton("❌ Cancel",      callback_data="cancel_admin")
        ]
    ])

    await update.message.reply_text(
        f"👤 *Admin Add Confirmation*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"*{tname}* ko admin banana chahte hain?\n\n"
        f"Woh upload/delete kar sakenge.",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

async def cmd_removeadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ *Sirf Owner hi admin remove kar sakta hai.*", parse_mode="Markdown")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "📝 *Kaise use karein?*\n\n"
            "Jise admin se hatana ho uske *message pe reply* karke\n"
            "`/removeadmin` likhein.",
            parse_mode="Markdown"
        )
        return

    target = update.message.reply_to_message.from_user
    tid    = target.id
    tname  = f"@{target.username}" if target.username else target.first_name

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🗑️ Haan, Hatao", callback_data=f"confirm_removeadmin:{tid}:{tname}"),
            InlineKeyboardButton("❌ Cancel",       callback_data="cancel_admin")
        ]
    ])

    await update.message.reply_text(
        f"⚠️ *Admin Remove Confirmation*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"*{tname}* ki admin access remove karni hai?",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

async def cmd_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    admin_ids = get_all_admin_ids()
    lines = [
        "👥 *Bot Admin List*",
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n",
        f"👑 *Owner:* `{OWNER_ID}`\n"
    ]

    if admin_ids:
        lines.append(f"🛡️ *Admins ({len(admin_ids)}):*")
        for uid in admin_ids:
            lines.append(f"  • `{uid}`")
    else:
        lines.append("_Koi extra admin nahi hai abhi._")

    lines.append("\n━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"_Total admins: {len(admin_ids) + 1}_")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CALLBACK HANDLER (Buttons)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    data = q.data
    await q.answer()

    # ── Material select (search results)
    if data.startswith("get:"):
        name = data[4:]
        db   = load_all_materials()
        if name in db:
            await q.edit_message_text(f"⚡ *Sending:* `{name}`...", parse_mode="Markdown")
            await send_material(q.message, name, db[name])
        else:
            await q.edit_message_text("❌ *File nahi mili.* Dobara search karein.", parse_mode="Markdown")

    # ── Search cancel
    elif data == "cancel":
        await q.edit_message_text("❌ *Cancelled.*", parse_mode="Markdown")

    # ── Upload confirm
    elif data.startswith("confirm_upload:"):
        name      = data[15:]
        file_id   = context.user_data.get("pending_file_id")
        file_type = context.user_data.get("pending_file_type")

        if not file_id:
            await q.edit_message_text("❌ Session expire ho gayi. /upload se dobara karein.", parse_mode="Markdown")
            return

        success = save_material_db(name, file_id, file_type)
        context.user_data.clear()

        if success:
            await q.edit_message_text(
                f"🎉 *Successfully Uploaded!*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📁 *Naam:* `{name}`\n"
                f"📂 *Type:* `{file_type}`\n\n"
                f"✅ Ab koi bhi `{name}` search karega to yeh file milegi! ⚡",
                parse_mode="Markdown"
            )
        else:
            await q.edit_message_text("❌ *Save nahi hua.* Dobara try karein.", parse_mode="Markdown")

    elif data == "cancel_upload":
        context.user_data.clear()
        await q.edit_message_text("❌ *Upload cancelled.*", parse_mode="Markdown")

    # ── Delete confirm
    elif data.startswith("confirm_delete:"):
        name    = data[15:]
        deleted = delete_material_db(name)
        if deleted:
            await q.edit_message_text(
                f"🗑️ *Deleted Successfully!*\n\n`{name}` remove kar diya gaya.",
                parse_mode="Markdown"
            )
        else:
            await q.edit_message_text(f"❌ `{name}` nahi mila.", parse_mode="Markdown")

    elif data == "cancel_delete":
        await q.edit_message_text("❌ *Delete cancelled.*", parse_mode="Markdown")

    # ── Add admin confirm
    elif data.startswith("confirm_addadmin:"):
        parts = data.split(":")
        tid   = int(parts[1])
        tname = parts[2]
        ok    = add_admin_db(tid, tname)
        if ok:
            await q.edit_message_text(
                f"✅ *Admin Added!*\n\n"
                f"*{tname}* ab bot admin hain.\n"
                f"Woh material upload/delete kar sakte hain! 🛡️",
                parse_mode="Markdown"
            )
        else:
            await q.edit_message_text(f"⚠️ *{tname}* pehle se admin hain!", parse_mode="Markdown")

    # ── Remove admin confirm
    elif data.startswith("confirm_removeadmin:"):
        parts = data.split(":")
        tid   = int(parts[1])
        tname = parts[2]
        ok    = remove_admin_db(tid)
        if ok:
            await q.edit_message_text(
                f"🗑️ *Admin Removed!*\n\n*{tname}* ki admin access remove kar di gayi.",
                parse_mode="Markdown"
            )
        else:
            await q.edit_message_text(f"❌ *{tname}* admin list mein nahi hain.", parse_mode="Markdown")

    elif data == "cancel_admin":
        await q.edit_message_text("❌ *Cancelled.*", parse_mode="Markdown")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SMART SEARCH HANDLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg          = update.message
    if not msg:
        return
    text         = msg.text or ""
    chat_type    = update.effective_chat.type
    bot_username = context.bot.username
    bot_tagged   = f"@{bot_username}" in text
    query        = text.replace(f"@{bot_username}", "").strip()

    if not query or query.startswith("/"):
        return

    # Group mein sirf 3+ chars ya tagged
    if chat_type != "private" and not bot_tagged and len(query) < 3:
        return

    results = smart_search(query)

    if not results:
        if bot_tagged or chat_type == "private":
            await msg.reply_text(
                f"😔 *Result Nahi Mila*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"*'{query}'* abhi hamare collection mein nahi hai.\n\n"
                f"🔜 Jald hi add hoga! Hamari team kaam kar rahi hai.\n\n"
                f"📋 Jo available hai: /list\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"_— Obsessed With Medical Team_ 🏥",
                parse_mode="Markdown"
            )
        return

    # Single result — seedha bhejo
    if len(results) == 1:
        key, material = results[0]
        await send_material(msg, key, material)
        return

    # Multiple results — buttons
    keyboard = [
        [InlineKeyboardButton(f"📄 {key}", callback_data=f"get:{key}")]
        for key, _ in results
    ]
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])

    await msg.reply_text(
        f"🔍 *{len(results)} Results Mile — '{query}'*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Niche se apna material select karein: 👇",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  BOT COMMANDS MENU
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def set_commands(app: Application):
    await app.bot.set_my_commands([
        BotCommand("start",       "Bot start karein"),
        BotCommand("list",        "Saara material dekhein"),
        BotCommand("help",        "Commands aur help"),
        BotCommand("upload",      "Naya material upload karein"),
        BotCommand("delete",      "Material delete karein"),
        BotCommand("addadmin",    "Admin add karein (Owner only)"),
        BotCommand("removeadmin", "Admin hatayein (Owner only)"),
        BotCommand("admins",      "Admin list dekhein"),
        BotCommand("cancel",      "Current operation cancel karein"),
    ])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  MAIN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main():
    app = Application.builder().token(BOT_TOKEN).post_init(set_commands).build()

    upload_conv = ConversationHandler(
        entry_points=[CommandHandler("upload", cmd_upload)],
        states={
            WAITING_FILE: [
                MessageHandler(
                    filters.Document.ALL | filters.PHOTO | filters.VIDEO |
                    filters.AUDIO | filters.VOICE,
                    receive_file
                ),
            ],
            WAITING_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name),
            ],
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
