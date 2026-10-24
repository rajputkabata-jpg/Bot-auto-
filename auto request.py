import asyncio
import json
import logging
import time
from copy import deepcopy
from functools import wraps
from html import escape as esc
from pathlib import Path

from telegram import (
    InlineKeyboardButton as Btn,
    InlineKeyboardMarkup as Markup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.error import RetryAfter, TelegramError
from telegram.ext import (
    ApplicationBuilder, CallbackQueryHandler, ChatJoinRequestHandler,
    CommandHandler, ContextTypes, MessageHandler, filters,
)

# ================= सेटिंग =================
BOT_TOKEN = "8827436789:AAEheqUcUl1KP-mXCOitLOwoMtgYZccQvuc"      # BotFather से नया token डालें
OWNER_ID = 8608761271
OWNER_USERNAME = "@ANSHxBHAI_666"
DEVELOPER_NAME = "समीर राजपूत"
TRIGGER = "/approve"
CONCURRENCY = 100
DATA_FILE = Path("data.json")

OWNER_TAG = esc(OWNER_USERNAME)
DEV_TAG = esc(DEVELOPER_NAME)
OWNER_LINK = OWNER_USERNAME.lstrip("@")
BLANK = "\u2800"

GREEN, BLUE, RED = "success", "primary", "danger"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("auto_approve")

DEFAULT_CAPTION = (
    "👋 <b>Hello {name}!</b>\n\n"
    "<blockquote>🎉 आपकी join request स्वीकार होने के लिए तैयार है।</blockquote>\n\n"
    "🔥 <b>PREMIUM ACCESS</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "🎮 <b>Game:</b> Free Fire • BGMI • Call Of Duty\n"
    "🛡️ <b>Benefits:</b> Safe &amp; Secure\n"
    "🎞️ <b>Quality:</b> 480p • 720p • 1080p • 4K\n"
    "⏰ <b>Active Time:</b> 1–12 Hours\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "👇 <b>नीचे दिए बटन से अभी जुड़ें</b> 👇"
)

DEFAULT_START_CAPTION = (
    "🚀 <b>High Speed Join Request Manager</b>\n\n"
    "👑 <b>Welcome To The Fastest Approval Engine On Telegram.</b>\n\n"
    "🧸 <b>Key Features</b>\n"
    "▶ Auto Log All Join Requests\n"
    "⚡ Ultra Fast Bulk Approval\n"
    "✅ Retry Logic For Failed Requests\n"
    "💯 Real Time Statistics\n"
    "🔮 Rate Limit Protection\n"
    "▶ Multi Channel Support\n\n"
    "▶ <b>Your Channels:</b> {channels}\n"
    "⚠️ <b>Pending:</b> {pending}"
)

DEFAULT_WELCOME = {
    "text": DEFAULT_CAPTION,
    "media": None,
    "buttons": [
        {"text": "🔑 Get Key & Injector (Main)", "url": "", "style": GREEN},
        {"text": "✅ Free Mod Menu", "url": "", "style": BLUE},
    ],
}

DEFAULT_START = {"text": DEFAULT_START_CAPTION, "media": None}

# ================= Button helpers =================
def ibtn(text, *, cb=None, url=None, style=BLUE):
    kw = {"api_kwargs": {"style": style}}
    if url:
        return Btn(text, url=url, **kw)
    return Btn(text, callback_data=cb, **kw)

def kbtn(text, style=BLUE):
    return KeyboardButton(text, api_kwargs={"style": style})

# ================= Storage =================
def load_data() -> dict:
    d = None
    if DATA_FILE.exists():
        try:
            d = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            d = None
    if d is None:
        d = {}
    d.setdefault("admins", [OWNER_ID])
    d.setdefault("stats", {})
    d.setdefault("users", [])
    d.setdefault("channels", {})

    wp = d.setdefault("welcome_post", deepcopy(DEFAULT_WELCOME))
    wp.setdefault("text", DEFAULT_CAPTION)
    wp.setdefault("buttons", deepcopy(DEFAULT_WELCOME["buttons"]))
    if "media" not in wp:
        old = wp.pop("photo", None)
        wp["media"] = {"type": "photo", "file_id": old} if old else None
    wp.pop("photo", None)

    sp = d.setdefault("start_post", deepcopy(DEFAULT_START))
    sp.setdefault("text", DEFAULT_START_CAPTION)
    sp.setdefault("media", None)
    return d

def save_data():
    DATA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

data = load_data()
pending: dict[int, dict[int, str]] = {}
user_states: dict[int, str] = {}

# ================= Helpers =================
def is_admin(uid: int) -> bool:
    return uid in data["admins"]

def admin_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not user or not is_admin(user.id):
            if update.effective_message:
                await update.effective_message.reply_text("❌ आप admin नहीं हैं।")
            return
        return await func(update, context)
    return wrapper

def add_stat(chat_id: int, approved: int):
    s = data["stats"].setdefault(str(chat_id), {"approved": 0, "runs": 0, "last": None})
    s["approved"] += approved
    s["runs"] += 1
    s["last"] = int(time.time())
    save_data()

def remember_channel(chat):
    if chat and chat.title and data["channels"].get(str(chat.id)) != chat.title:
        data["channels"][str(chat.id)] = chat.title
        save_data()

def spaced(text: str) -> str:
    text = text.strip().replace("\n\n", f"\n{BLANK}\n")
    return f"{BLANK}\n{text}\n{BLANK}"

def pending_total() -> int:
    return sum(len(p) for p in pending.values())

def links_overview():
    btns = data["welcome_post"].get("buttons", [])
    info_lines, inline_btns = [], []
    for i, b in enumerate(btns):
        info_lines.append(f"{i+1}. 🔑 {esc(b['text'])}\n🔗 {esc(b['url']) or 'सेट नहीं'}\n")
        inline_btns.append([ibtn(f"⚙️ Edit: {b['text'][:20]}...", cb=f"manage_btn_{i}", style=GREEN)])
    text = (
        "🔗 <b>MANAGE BUTTONS &amp; LINKS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "यहाँ से आप किसी भी बटन का नाम या लिंक बदल सकते हैं:\n\n"
        + "\n".join(info_lines) +
        "\nसम्पादित करने के लिए नीचे दिए गए बटन पर क्लिक करें 👇"
    )
    return text, Markup(inline_btns)

# ================= Start menu (फ़ोटो + कैप्शन + बटन) =================
def start_caption() -> str:
    text = data["start_post"].get("text", DEFAULT_START_CAPTION)
    return (text.replace("{channels}", str(len(data["channels"])))
                .replace("{pending}", str(pending_total())))

def start_markup(bot_username: str):
    return Markup([
        [
            ibtn("📂 My Channels", cb="my_channels", style=GREEN),
            ibtn("➕ Add To Channel",
                 url=f"https://t.me/{bot_username}?startchannel&admin=invite_users+post_messages",
                 style=BLUE),
        ],
        [
            ibtn("✅ Approve All", cb="approve_all", style=GREEN),
            ibtn("📊 Stats", cb="stats", style=BLUE),
        ],
        [
            ibtn("👤 Owner", url=f"https://t.me/{OWNER_LINK}", style=RED),
            ibtn("❓ Help", cb="help", style=BLUE),
        ],
    ])

async def send_start(bot, chat_id: int, bot_username: str):
    sp = data["start_post"]
    caption = spaced(start_caption())
    media = sp.get("media")
    markup = start_markup(bot_username)
    try:
        if media and media.get("file_id") and len(caption) <= 1024:
            if media["type"] == "video":
                await bot.send_video(chat_id=chat_id, video=media["file_id"], caption=caption,
                                     parse_mode="HTML", reply_markup=markup, supports_streaming=True)
            else:
                await bot.send_photo(chat_id=chat_id, photo=media["file_id"], caption=caption,
                                     parse_mode="HTML", reply_markup=markup)
            return
        if media and media.get("file_id"):
            if media["type"] == "video":
                await bot.send_video(chat_id=chat_id, video=media["file_id"], supports_streaming=True)
            else:
                await bot.send_photo(chat_id=chat_id, photo=media["file_id"])
        await bot.send_message(chat_id=chat_id, text=caption[:4096], parse_mode="HTML",
                               reply_markup=markup, disable_web_page_preview=True)
    except TelegramError as e:
        log.warning("Start menu failed for %s: %s", chat_id, e)

# ================= Welcome DM (join request पर) =================
def welcome_markup():
    rows = [
        [ibtn(b["text"], url=b["url"], style=b.get("style", BLUE))]
        for b in data["welcome_post"].get("buttons", []) if b.get("text") and b.get("url")
    ]
    return Markup(rows) if rows else None

async def send_welcome(bot, user_id: int, full_name: str):
    wp = data["welcome_post"]
    caption = spaced(wp.get("text", DEFAULT_CAPTION).replace("{name}", esc(full_name)))
    media = wp.get("media")
    markup = welcome_markup()
    try:
        if media and media.get("file_id") and len(caption) <= 1024:
            if media["type"] == "video":
                await bot.send_video(chat_id=user_id, video=media["file_id"], caption=caption,
                                     parse_mode="HTML", reply_markup=markup, supports_streaming=True)
            else:
                await bot.send_photo(chat_id=user_id, photo=media["file_id"], caption=caption,
                                     parse_mode="HTML", reply_markup=markup)
            return
        if media and media.get("file_id"):
            if media["type"] == "video":
                await bot.send_video(chat_id=user_id, video=media["file_id"], supports_streaming=True)
            else:
                await bot.send_photo(chat_id=user_id, photo=media["file_id"])
        await bot.send_message(chat_id=user_id, text=caption[:4096], parse_mode="HTML",
                               reply_markup=markup, disable_web_page_preview=True)
    except TelegramError as e:
        log.warning("DM Failed to %s: %s", user_id, e)

# ================= Approve Engine =================
async def approve_chat(bot, chat_id: int) -> tuple[int, int, int]:
    users = list(pending.get(chat_id, {}).keys())
    total_requested = len(users)
    if not users:
        return 0, 0, 0

    sem = asyncio.Semaphore(CONCURRENCY)
    ok = 0

    async def approve_one(uid: int):
        nonlocal ok
        async with sem:
            try:
                await bot.approve_chat_join_request(chat_id=chat_id, user_id=uid)
                ok += 1
                pending.get(chat_id, {}).pop(uid, None)
            except RetryAfter as e:
                await asyncio.sleep(e.retry_after)
                try:
                    await bot.approve_chat_join_request(chat_id=chat_id, user_id=uid)
                    ok += 1
                    pending.get(chat_id, {}).pop(uid, None)
                except Exception:
                    pass
            except TelegramError as e:
                log.warning("Approval error %s: %s", uid, e)

    await asyncio.gather(*(approve_one(uid) for uid in users))
    add_stat(chat_id, ok)
    return ok, len(pending.get(chat_id, {})), total_requested

async def run_approve(bot, chat_id: int, msg_id_to_delete: int | None = None, notify: int | None = None):
    if msg_id_to_delete:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=msg_id_to_delete)
        except Exception as e:
            log.warning("Could not delete trigger message: %s", e)

    t0 = time.time()
    ok, remaining, total = await approve_chat(bot, chat_id)
    taken = round(time.time() - t0, 2)

    if total > 0:
        text = (
            "⚡ <b>ULTRA-FAST JOIN APPROVAL COMPLETED</b> ⚡\n\n"
            f"✅ <b>Approved Members:</b> <code>{ok}</code>\n"
            f"⏳ <b>Remaining Pending:</b> <code>{remaining}</code>\n"
            f"🚀 <b>Speed:</b> <code>{total}</code> requests processed in just <code>{taken}s</code>!"
        )
    else:
        text = "ℹ️ <b>कोई pending request नहीं मिली!</b>"

    target = notify or chat_id
    if notify:
        text = f"<b>Chat:</b> <code>{chat_id}</code>\n" + text
    try:
        await bot.send_message(chat_id=target, text=text, parse_mode="HTML")
    except TelegramError as e:
        log.warning("Failed to send status: %s", e)

# ================= Listeners =================
async def on_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    req = update.chat_join_request
    remember_channel(req.chat)
    pending.setdefault(req.chat.id, {})[req.from_user.id] = req.from_user.full_name
    if req.from_user.id not in data["users"]:
        data["users"].append(req.from_user.id)
        save_data()
    await send_welcome(context.bot, req.from_user.id, req.from_user.full_name)

async def on_channel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.channel_post or update.effective_message
    if not msg or not msg.text or not msg.text.startswith(TRIGGER):
        return
    remember_channel(msg.chat)
    asyncio.create_task(run_approve(context.bot, msg.chat.id, msg_id_to_delete=msg.message_id))

# ================= Admin keyboard =================
LBL_MEDIA = "🖼️ PHOTO / VIDEO"
LBL_CAPTION = "📝 CAPTION"
LBL_START_MEDIA = "🌟 START PHOTO"
LBL_START_CAPTION = "✍️ START CAPTION"
LBL_CHANNEL = "🔗 CHANNEL LINK"
LBL_LINKS = "🔗 LINKS & BUTTONS"
LBL_BROADCAST = "📢 BROADCAST"
LBL_REMOVE = "🗑️ REMOVE MEDIA"
LBL_STATS = "📊 STATS"
PANEL_LABELS = (LBL_MEDIA, LBL_CAPTION, LBL_START_MEDIA, LBL_START_CAPTION,
                LBL_CHANNEL, LBL_LINKS, LBL_BROADCAST, LBL_REMOVE, LBL_STATS)

def admin_floating_keyboard():
    keyboard = [
        [kbtn(LBL_MEDIA, GREEN), kbtn(LBL_CAPTION, GREEN)],
        [kbtn(LBL_START_MEDIA, GREEN), kbtn(LBL_START_CAPTION, GREEN)],
        [kbtn(LBL_CHANNEL, GREEN), kbtn(LBL_LINKS, GREEN)],
        [kbtn(LBL_BROADCAST, RED), kbtn(LBL_REMOVE, RED)],
        [kbtn(LBL_STATS, BLUE)],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def back_kb():
    return Markup([[ibtn("🔙 Back to Main Menu", cb="back_main", style=RED)]])

# ================= Text blocks =================
def stats_text() -> str:
    total_approved = sum(s.get("approved", 0) for s in data["stats"].values())
    return (
        "📊 <b>High-Speed Bot Statistics</b>\n\n"
        f"🏢 <b>Active Channels:</b> <code>{len(data['channels'])}</code>\n"
        f"👥 <b>Saved Users:</b> <code>{len(data['users'])}</code>\n"
        f"📡 <b>Total Approved Requests:</b> <code>{total_approved}</code>\n"
        f"⏳ <b>Total Pending Requests:</b> <code>{pending_total()}</code>\n"
        "🤖 <b>Status:</b> Online &amp; Running\n\n"
        f"<b>Owner:</b> {OWNER_TAG}"
    )

def help_text() -> str:
    return (
        "📚 <b>How to Use This High-Speed Bot</b>\n\n"
        "<b>For Channel / Group Admins:</b>\n"
        "1. Add me to your channel/group as admin\n"
        "2. Give me permission to manage join requests\n"
        "3. Users' join requests will be auto-logged\n"
        "4. Send <code>/approve</code> in your chat for fast approval\n\n"
        "<b>Commands:</b>\n"
        "• <code>/start</code> - Show main menu\n"
        "• <code>/admin</code> - Admin panel (admins only)\n"
        "• <code>/approve</code> - Approve all pending requests\n\n"
        f"<b>Owner:</b> {OWNER_TAG}\n"
        f"<b>Developer:</b> {DEV_TAG}"
    )

def my_channels_text() -> str:
    if not data["channels"]:
        return "📂 <b>My Channels</b>\n\nअभी कोई चैनल नहीं जुड़ा। <b>Add To Channel</b> से जोड़ें।"
    lines = []
    for cid, title in data["channels"].items():
        n = len(pending.get(int(cid), {}))
        lines.append(f"• {esc(title)} — pending <code>{n}</code>")
    return "📂 <b>My Channels</b>\n\n" + "\n".join(lines)

# ================= Commands =================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in data["users"]:
        data["users"].append(user_id)
        save_data()
    await send_start(context.bot, update.effective_chat.id, context.bot.username)
    if is_admin(user_id):
        await update.effective_message.reply_text(
            "👑 <b>ADMIN CONTROL PANEL</b>\n\nनीचे दिए गए कीबोर्ड से विकल्प चुनें 👇",
            reply_markup=admin_floating_keyboard(), parse_mode="HTML")

@admin_only
async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_states.pop(update.effective_user.id, None)
    await update.effective_message.reply_text(
        "👑 <b>ADMIN CONTROL PANEL</b>\n\nनीचे दिए गए कीबोर्ड से विकल्प चुनें 👇",
        reply_markup=admin_floating_keyboard(), parse_mode="HTML")

# ================= Admin: मीडिया सीधे भेजकर सेट =================
async def on_admin_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    uid = update.effective_user.id
    if not is_admin(uid):
        return

    if msg.video:
        media = {"type": "video", "file_id": msg.video.file_id}
    elif msg.photo:
        media = {"type": "photo", "file_id": msg.photo[-1].file_id}
    else:
        return

    state = user_states.get(uid)
    if state == "set_start_media":
        target, label = data["start_post"], "स्टार्ट मेनू"
    else:
        target, label = data["welcome_post"], "वेलकम पोस्ट (DM)"

    target["media"] = media
    if msg.caption:
        target["text"] = msg.caption_html
    save_data()
    user_states.pop(uid, None)

    kind = "वीडियो" if media["type"] == "video" else "फोटो"
    extra = " और कैप्शन भी" if msg.caption else ""
    await msg.reply_text(f"✅ {kind}{extra} {label} में सेट हो गया!",
                         reply_markup=admin_floating_keyboard())

# ================= Admin: बटन आधारित टेक्स्ट इनपुट =================
async def handle_admin_text_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    text = msg.text
    uid = update.effective_user.id
    if not is_admin(uid):
        return

    if text in PANEL_LABELS:
        user_states.pop(uid, None)
        await handle_panel_button(update, text)
        return

    state = user_states.get(uid)
    if not state:
        return

    if state == "set_caption":
        data["welcome_post"]["text"] = msg.text_html
        save_data()
        user_states.pop(uid, None)
        await msg.reply_text("✅ DM वाला कैप्शन अपडेट हो गया!", reply_markup=admin_floating_keyboard())

    elif state == "set_start_caption":
        data["start_post"]["text"] = msg.text_html
        save_data()
        user_states.pop(uid, None)
        await msg.reply_text("✅ Start मेनू का कैप्शन अपडेट हो गया!", reply_markup=admin_floating_keyboard())

    elif state == "set_channel":
        link = text.strip()
        if not link.startswith(("http://", "https://", "t.me/")):
            await msg.reply_text("❌ अमान्य लिंक! कृपया <code>https://t.me/...</code> भेजें।", parse_mode="HTML")
            return
        for b in data["welcome_post"]["buttons"]:
            b["url"] = link
        save_data()
        user_states.pop(uid, None)
        await msg.reply_text(f"✅ चैनल लिंक सेट हो गया: <code>{esc(link)}</code>",
                             reply_markup=admin_floating_keyboard(), parse_mode="HTML")

    elif state == "broadcast":
        user_states.pop(uid, None)
        users = list(data["users"])
        sent = 0
        await msg.reply_text(f"⏳ {len(users)} यूज़र्स को भेजा जा रहा है...")
        for u in users:
            try:
                await context.bot.send_message(chat_id=u, text=msg.text_html, parse_mode="HTML")
                sent += 1
                await asyncio.sleep(0.04)
            except Exception:
                pass
        await msg.reply_text(f"✅ Broadcast पूरा! Sent: {sent}/{len(users)}",
                             reply_markup=admin_floating_keyboard())

    elif state.startswith("edit_name_"):
        idx = int(state.split("_")[-1])
        data["welcome_post"]["buttons"][idx]["text"] = text
        save_data()
        user_states.pop(uid, None)
        await msg.reply_text(f"✅ Button {idx+1} का नाम बदल दिया गया: <code>{esc(text)}</code>",
                             reply_markup=admin_floating_keyboard(), parse_mode="HTML")

    elif state.startswith("edit_url_"):
        idx = int(state.split("_")[-1])
        if not text.startswith(("http://", "https://", "t.me/")):
            await msg.reply_text("❌ अमान्य लिंक! कृपया <code>https://t.me/link</code> भेजें।",
                                 parse_mode="HTML")
            return
        data["welcome_post"]["buttons"][idx]["url"] = text
        save_data()
        user_states.pop(uid, None)
        await msg.reply_text(f"✅ Button {idx+1} का लिंक बदल दिया गया: <code>{esc(text)}</code>",
                             reply_markup=admin_floating_keyboard(), parse_mode="HTML")

async def handle_panel_button(update: Update, text: str):
    msg = update.effective_message
    uid = update.effective_user.id

    if text == LBL_MEDIA:
        media = data["welcome_post"].get("media")
        status = f"✅ {media['type']} सेट है" if media else "❌ कोई मीडिया नहीं है"
        await msg.reply_text(
            f"🖼️ <b>DM मीडिया</b> ({status})\n\n"
            "सीधे फोटो या वीडियो भेजें। वह अपने आप DM पोस्ट में सेट हो जाएगा।",
            parse_mode="HTML")

    elif text == LBL_CAPTION:
        user_states[uid] = "set_caption"
        await msg.reply_text(
            f"📝 <b>DM कैप्शन (अभी का):</b>\n\n{data['welcome_post'].get('text', '')}\n\n"
            "अब नया कैप्शन लिखकर भेजें। नाम के लिए <code>{name}</code> लिखें।",
            parse_mode="HTML")

    elif text == LBL_START_MEDIA:
        user_states[uid] = "set_start_media"
        media = data["start_post"].get("media")
        status = f"✅ {media['type']} सेट है" if media else "❌ कोई मीडिया नहीं है"
        await msg.reply_text(
            f"🌟 <b>Start मेनू फ़ोटो</b> ({status})\n\n"
            "अब फोटो या वीडियो भेजें। वह /start पर दिखेगा।",
            parse_mode="HTML")

    elif text == LBL_START_CAPTION:
        user_states[uid] = "set_start_caption"
        await msg.reply_text(
            f"✍️ <b>Start कैप्शन (अभी का):</b>\n\n<code>{esc(data['start_post'].get('text', ''))}</code>\n\n"
            "नया कैप्शन लिखकर भेजें। लाइव आंकड़ों के लिए <code>{channels}</code> और "
            "<code>{pending}</code> लिखें।",
            parse_mode="HTML")

    elif text == LBL_CHANNEL:
        user_states[uid] = "set_channel"
        cur = data["welcome_post"]["buttons"][0].get("url") or "सेट नहीं है"
        await msg.reply_text(
            f"🔗 <b>Channel Link</b>\n\nअभी का लिंक: <code>{esc(cur)}</code>\n\n"
            "नया चैनल लिंक भेजें। यह दोनों DM बटनों पर लगेगा।",
            parse_mode="HTML")

    elif text == LBL_LINKS:
        info_text, kb = links_overview()
        await msg.reply_text(info_text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)

    elif text == LBL_BROADCAST:
        user_states[uid] = "broadcast"
        await msg.reply_text(
            f"📢 <b>Broadcast</b>\n\nकुल यूज़र्स: <code>{len(data['users'])}</code>\n\n"
            "अब जो मैसेज भेजना है वह लिखकर भेजें।",
            parse_mode="HTML")

    elif text == LBL_REMOVE:
        data["welcome_post"]["media"] = None
        save_data()
        await msg.reply_text("🗑️ DM मीडिया हटा दिया गया है।", reply_markup=admin_floating_keyboard())

    elif text == LBL_STATS:
        await msg.reply_text(stats_text(), parse_mode="HTML")

# ================= Inline callbacks =================
async def on_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    cb = query.data
    uid = query.from_user.id
    chat_id = query.message.chat_id

    admin_cb = cb == "approve_all" or cb.startswith(("manage_btn_", "change_", "back_to_links"))
    if admin_cb and not is_admin(uid):
        return await query.answer("❌ अनुमति नहीं है", show_alert=True)
    await query.answer()

    if cb == "stats":
        await context.bot.send_message(chat_id, stats_text(), parse_mode="HTML", reply_markup=back_kb())
    elif cb == "help":
        await context.bot.send_message(chat_id, help_text(), parse_mode="HTML", reply_markup=back_kb())
    elif cb == "my_channels":
        await context.bot.send_message(chat_id, my_channels_text(), parse_mode="HTML", reply_markup=back_kb())
    elif cb == "back_main":
        await send_start(context.bot, chat_id, context.bot.username)
    elif cb == "approve_all":
        if not pending:
            await context.bot.send_message(chat_id, "ℹ️ कोई pending request नहीं है।")
            return
        await context.bot.send_message(chat_id, "⏳ सभी चैनलों की requests approve हो रही हैं...")
        for cid in list(pending.keys()):
            asyncio.create_task(run_approve(context.bot, cid, notify=uid))

    elif cb.startswith("manage_btn_"):
        idx = int(cb.split("_")[-1])
        b = data["welcome_post"]["buttons"][idx]
        text = (
            f"⚙️ <b>Managing Button:</b> {esc(b['text'])}\n\n"
            f"<b>Current URL:</b> {esc(b['url']) or 'सेट नहीं'}\n\n"
            "आप क्या बदलना चाहते हैं?"
        )
        kb = Markup([
            [ibtn("✏️ Change Button Name", cb=f"change_name_{idx}", style=GREEN)],
            [ibtn("🔗 Change Button URL", cb=f"change_url_{idx}", style=BLUE)],
            [ibtn("🔙 Back to Menu", cb="back_to_links", style=RED)],
        ])
        await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)

    elif cb.startswith("change_name_"):
        idx = int(cb.split("_")[-1])
        user_states[uid] = f"edit_name_{idx}"
        await query.edit_message_text(f"📝 <b>Button {idx+1} का नया नाम चैट में लिखकर भेजें:</b>", parse_mode="HTML")

    elif cb.startswith("change_url_"):
        idx = int(cb.split("_")[-1])
        user_states[uid] = f"edit_url_{idx}"
        await query.edit_message_text(f"🔗 <b>Button {idx+1} का नया URL चैट में लिखकर भेजें:</b>", parse_mode="HTML")

    elif cb == "back_to_links":
        user_states.pop(uid, None)
        info_text, kb = links_overview()
        await query.edit_message_text(info_text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)

# ================= Main =================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(ChatJoinRequestHandler(on_join_request))
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL & filters.Regex(rf"^{TRIGGER}"), on_channel_command))
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.Regex(rf"^{TRIGGER}"), on_channel_command))

    app.add_handler(CommandHandler("start", cmd_start, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("admin", cmd_admin, filters=filters.ChatType.PRIVATE))

    app.add_handler(CallbackQueryHandler(on_callback_query))
    app.add_handler(MessageHandler((filters.PHOTO | filters.VIDEO) & filters.ChatType.PRIVATE, on_admin_media))
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, handle_admin_text_buttons))

    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()