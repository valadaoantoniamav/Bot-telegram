import asyncio
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from fastapi import FastAPI, Request, HTTPException
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

BOT_TOKEN = os.environ["BOT_TOKEN"]
PUBLIC_URL = os.environ["PUBLIC_URL"].rstrip("/")
PORT = int(os.getenv("PORT", "8080"))
DB_PATH = os.getenv("DB_PATH", "/data/bot.db")
KIWIFY_WEBHOOK_TOKEN = os.environ["KIWIFY_WEBHOOK_TOKEN"]
ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))
CHANNEL_ID_RAW = os.getenv("CHANNEL_ID", "").strip()
CHANNEL_ID = int(CHANNEL_ID_RAW) if CHANNEL_ID_RAW else None

PAYMENT_LINKS = {
    "7d": "https://pay.kiwify.com.br/nNtYoc4",
    "30d": "https://pay.kiwify.com.br/VTI5T6a",
    "lifetime": "https://pay.kiwify.com.br/cIuDDKM",
}
PLANS = {
    "7d": {"button": "📅 7 DIAS — R$ 29,90", "title": "📅 ACESSO POR 7 DIAS", "price": "R$ 29,90", "days": 7},
    "30d": {"button": "👑 MENSAL — R$ 49,90", "title": "👑 ACESSO MENSAL", "price": "R$ 49,90", "days": 30},
    "lifetime": {"button": "♾️ VITALÍCIO — R$ 79,90", "title": "♾️ ACESSO VITALÍCIO", "price": "R$ 79,90", "days": None},
}

app = FastAPI()
tg_app = Application.builder().token(BOT_TOKEN).build()


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            access_until TEXT,
            plan TEXT,
            status TEXT DEFAULT 'pending',
            invite_link TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pending_checkouts (
            token TEXT PRIMARY KEY,
            telegram_id INTEGER NOT NULL,
            plan TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            telegram_id INTEGER,
            plan TEXT,
            status TEXT,
            payload TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def now():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.isoformat()


def parse_iso(value):
    return datetime.fromisoformat(value) if value else None


def plans_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(PLANS["7d"]["button"], callback_data="plan:7d")],
        [InlineKeyboardButton(PLANS["30d"]["button"], callback_data="plan:30d")],
        [InlineKeyboardButton(PLANS["lifetime"]["button"], callback_data="plan:lifetime")],
        [
            InlineKeyboardButton("👤 Minha conta", callback_data="account"),
            InlineKeyboardButton("❓ Ajuda", callback_data="help"),
        ],
    ])


def back_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Voltar aos planos", callback_data="back:plans")]
    ])


def checkout_url(telegram_id, plan_id):
    token = secrets.token_urlsafe(16)
    conn = db()
    conn.execute(
        "INSERT INTO pending_checkouts(token, telegram_id, plan, created_at) VALUES (?, ?, ?, ?)",
        (token, telegram_id, plan_id, iso(now())),
    )
    conn.commit()
    conn.close()
    return PAYMENT_LINKS[plan_id] + "?" + urlencode({"s1": token})


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Bem-vindo!\n\n🔐 Acesso ao canal privado.\n\nEscolha abaixo o plano que deseja:",
        reply_markup=plans_keyboard(),
    )


async def plans_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📋 Escolha seu plano de acesso:", reply_markup=plans_keyboard())


async def renew_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Escolha o plano que deseja renovar:", reply_markup=plans_keyboard())


async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🇧🇷 Atualmente os pagamentos estão disponíveis somente em reais (R$).")


async def payment_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💳 Para realizar o pagamento:\n\n"
        "1️⃣ Use /planos\n2️⃣ Escolha seu plano\n3️⃣ Clique em PAGAR AGORA\n"
        "4️⃣ Finalize o pagamento pela Kiwify.\n\n"
        "Após a confirmação, seu acesso será processado automaticamente."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❓ AJUDA\n\n"
        "Escolha um plano, realize o pagamento pela Kiwify e aguarde a confirmação.\n\n"
        "Após a confirmação, o acesso ao canal privado será liberado automaticamente.\n\n"
        "🔄 Para renovar, use /renovar."
    )


async def account_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = db()
    row = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (user.id,)).fetchone()
    conn.close()
    if not row or row["status"] != "active":
        await update.message.reply_text(
            "👤 MINHA CONTA\n\n"
            "Você não possui um acesso ativo no momento.\n\n"
            "Use /planos para escolher um plano."
        )
        return
    until = row["access_until"]
    if row["plan"] == "lifetime":
        validity = "♾️ Vitalício"
    else:
        validity = f"📅 Válido até: {until[:19].replace('T', ' ')} UTC"
    await update.message.reply_text(
        f"👤 MINHA CONTA\n\n"
        f"📦 Plano: {row['plan']}\n"
        f"{validity}\n\n"
        f"🔐 Status: Ativo"
    )


async def setchannel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if ADMIN_TELEGRAM_ID and update.effective_user.id != ADMIN_TELEGRAM_ID:
        return
    await update.message.reply_text(
        "📢 Para configurar o canal, encaminhe para mim uma mensagem publicada dentro do canal privado. "
        "Eu identificarei o ID do canal e farei a configuração."
    )


async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 Seu Telegram ID: {update.effective_user.id}")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "back:plans":
        await query.edit_message_text("📋 Escolha seu plano de acesso:", reply_markup=plans_keyboard())
        return

    if data == "account":
        await account_from_callback(query)
        return

    if data == "help":
        await query.edit_message_text(
            "❓ AJUDA\n\n"
            "Escolha um plano, realize o pagamento pela Kiwify e aguarde a confirmação.\n\n"
            "🔄 Para renovar, use /renovar.",
            reply_markup=back_keyboard(),
        )
        return

    if data.startswith("plan:"):
        plan_id = data.split(":", 1)[1]
        plan = PLANS[plan_id]
        link = checkout_url(query.from_user.id, plan_id)
        await query.edit_message_text(
            f"{plan['title']}\n\n"
            f"💰 Valor: {plan['price']}\n\n"
            "🔐 Acesso ao canal privado pelo período correspondente ao plano.\n\n"
            "⚡ Clique abaixo para realizar o pagamento.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💳 PAGAR AGORA", url=link)],
                [InlineKeyboardButton("⬅️ Voltar aos planos", callback_data="back:plans")],
            ]),
        )


async def account_from_callback(query):
    conn = db()
    row = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (query.from_user.id,)).fetchone()
    conn.close()
    if not row or row["status"] != "active":
        await query.edit_message_text(
            "👤 MINHA CONTA\n\nVocê não possui um acesso ativo no momento.",
            reply_markup=back_keyboard(),
        )
        return
    validity = "♾️ Vitalício" if row["plan"] == "lifetime" else f"📅 Válido até: {row['access_until'][:19].replace('T', ' ')} UTC"
    await query.edit_message_text(
        f"👤 MINHA CONTA\n\n📦 Plano: {row['plan']}\n{validity}\n🔐 Status: Ativo",
        reply_markup=back_keyboard(),
    )


def extract_tracking_token(payload):
    tracking = payload.get("TrackingParameters") or {}
    return tracking.get("s1") or tracking.get("s2") or tracking.get("s3")


def plan_from_payload(payload, telegram_id):
    token = extract_tracking_token(payload)
    if token:
        conn = db()
        row = conn.execute("SELECT plan FROM pending_checkouts WHERE token = ?", (token,)).fetchone()
        conn.close()
        if row:
            return row["plan"]
    amount = (payload.get("Commissions") or {}).get("charge_amount")
    if str(amount) == "2990":
        return "7d"
    if str(amount) == "4990":
        return "30d"
    if str(amount) == "7990":
        return "lifetime"
    return None


async def grant_access(telegram_id, plan_id):
    if not CHANNEL_ID:
        return None, "CHANNEL_ID não configurado"

    plan = PLANS[plan_id]
    expire = None if plan["days"] is None else now() + timedelta(days=plan["days"])
    expire_ts = int(expire.timestamp()) if expire else None

    kwargs = {"chat_id": CHANNEL_ID, "member_limit": 1, "creates_join_request": False}
    if expire_ts:
        kwargs["expire_date"] = expire_ts

    invite = await tg_app.bot.create_chat_invite_link(**kwargs)

    conn = db()
    old = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
    conn.execute(
        """INSERT INTO users(telegram_id, username, first_name, access_until, plan, status, invite_link, created_at, updated_at)
        VALUES(?, ?, ?, ?, ?, 'active', ?, ?, ?)
        ON CONFLICT(telegram_id) DO UPDATE SET
        access_until=excluded.access_until, plan=excluded.plan, status='active',
        invite_link=excluded.invite_link, updated_at=excluded.updated_at,
        username=excluded.username, first_name=excluded.first_name""",
        (
            telegram_id,
            old["username"] if old else None,
            old["first_name"] if old else None,
            iso(expire) if expire else None,
            plan_id,
            invite.invite_link,
            iso(now()),
            iso(now()),
        ),
    )
    conn.commit()
    conn.close()
    return invite.invite_link, None


async def kiwify_webhook(request: Request):
    body = await request.json()
    event = body.get("webhook_event_type")
    status = body.get("order_status")

    if event not in {"order_approved", "subscription_renewed"} and status != "paid":
        return {"ok": True, "ignored": True}

    order_id = body.get("order_id")
    token = extract_tracking_token(body)
    telegram_id = None

    if token:
        conn = db()
        row = conn.execute("SELECT telegram_id FROM pending_checkouts WHERE token = ?", (token,)).fetchone()
        conn.close()
        if row:
            telegram_id = int(row["telegram_id"])

    if not telegram_id:
        return {"ok": True, "waiting_for_link": True}

    plan_id = plan_from_payload(body, telegram_id)
    if not plan_id:
        return {"ok": True, "unknown_plan": True}

    conn = db()
    if order_id:
        exists = conn.execute("SELECT order_id FROM orders WHERE order_id = ?", (order_id,)).fetchone()
        if exists:
            conn.close()
            return {"ok": True, "duplicate": True}
        conn.execute(
            "INSERT INTO orders(order_id, telegram_id, plan, status, payload, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (order_id, telegram_id, plan_id, "paid", str(body), iso(now())),
        )
        conn.commit()
    conn.close()

    invite_link, error = await grant_access(telegram_id, plan_id)
    if error:
        return {"ok": True, "access_pending": error}

    try:
        await tg_app.bot.send_message(
            chat_id=telegram_id,
            text=(
                "✅ PAGAMENTO CONFIRMADO!\n\n"
                f"📦 Plano: {PLANS[plan_id]['title']}\n\n"
                "🔐 Seu acesso ao canal privado está liberado.\n\n"
                "👇 Clique no botão abaixo para entrar:"
            ),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔐 ENTRAR NO CANAL", url=invite_link)]
            ]),
        )
    except Exception:
        pass

    return {"ok": True}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/telegram")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, tg_app.bot)
    await tg_app.update_queue.put(update)
    return {"ok": True}


@app.post("/kiwify/webhook/" + KIWIFY_WEBHOOK_TOKEN)
async def kiwify_endpoint(request: Request):
    return await kiwify_webhook(request)


async def expiry_loop():
    while True:
        try:
            conn = db()
            rows = conn.execute(
                "SELECT telegram_id, access_until FROM users WHERE status='active' AND access_until IS NOT NULL"
            ).fetchall()
            conn.close()
            current = now()
            for row in rows:
                until = parse_iso(row["access_until"])
                if until and until <= current and CHANNEL_ID:
                    try:
                        await tg_app.bot.ban_chat_member(chat_id=CHANNEL_ID, user_id=row["telegram_id"])
                        await tg_app.bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=row["telegram_id"], only_if_banned=True)
                    except Exception:
                        pass
                    conn = db()
                    conn.execute(
                        "UPDATE users SET status='expired', updated_at=? WHERE telegram_id=?",
                        (iso(current), row["telegram_id"]),
                    )
                    conn.commit()
                    conn.close()
                    try:
                        await tg_app.bot.send_message(
                            chat_id=row["telegram_id"],
                            text="⏳ Seu acesso ao canal expirou. Use /renovar para adquirir um novo período.",
                        )
                    except Exception:
                        pass
        except Exception as exc:
            print(f"Erro no ciclo de expiração: {exc}")
        await asyncio.sleep(60)


async def startup():
    init_db()
    await tg_app.initialize()
    await tg_app.start()
    await tg_app.bot.set_webhook(
        url=f"{PUBLIC_URL}/telegram",
        drop_pending_updates=True,
    )
    asyncio.create_task(expiry_loop())


async def shutdown():
    await tg_app.stop()
    await tg_app.shutdown()


@app.on_event("startup")
async def on_startup():
    await startup()


@app.on_event("shutdown")
async def on_shutdown():
    await shutdown()


tg_app.add_handler(CommandHandler("start", start))
tg_app.add_handler(CommandHandler("planos", plans_command))
tg_app.add_handler(CommandHandler("minhaconta", account_command))
tg_app.add_handler(CommandHandler("renovar", renew_command))
tg_app.add_handler(CommandHandler("pagamento", payment_command))
tg_app.add_handler(CommandHandler("idioma", language_command))
tg_app.add_handler(CommandHandler("ajuda", help_command))
tg_app.add_handler(CommandHandler("id", id_command))
tg_app.add_handler(CommandHandler("setchannel", setchannel_command))
tg_app.add_handler(CallbackQueryHandler(button_handler))
