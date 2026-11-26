import os
import secrets
import sqlite3
from datetime import datetime, timezone
from urllib.parse import urlencode

from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

BOT_TOKEN = os.environ["BOT_TOKEN"]
PUBLIC_URL = os.environ["PUBLIC_URL"].rstrip("/")
PORT = int(os.getenv("PORT", "8080"))
DB_PATH = os.getenv("DB_PATH", "/data/bot.db")

# Configure these in Railway after creating the new Kiwify checkout and the group invite link.
KIWIFY_CHECKOUT_URL = os.getenv("KIWIFY_CHECKOUT_URL", "").strip()
GROUP_INVITE_URL = os.getenv("GROUP_INVITE_URL", "").strip()

PLAN_ID = "weekly"
PLAN_PRICE_CENTS = 990
PLAN_DAYS = 7
PLAN_LABEL = "📅 PLANO SEMANAL — R$ 9,90"
PLAN_TITLE = "📅 ACESSO POR 1 SEMANA"

WELCOME_MESSAGE = """Olá amigo, seja bem vindo ao PORNOBÃO.
O acesso ao grupo tem duração de 1 semana, o plano custa apenas R$9,90.

ℹ️ Ao entrar no grupo você terá acesso a +500 mídias após o período, você pode renovar seu acesso quando quiser enviando "/start" aqui mesmo.

🔎 Na bio do grupo você pode conferir termos de pesquisa para facilitar sua navegação por algo específico.

— CONTEUDOS ATUALIZADOS SEMANALMENTE.

Seja bem vindo e divirta-se 💦"""

app = FastAPI()
tg_app = Application.builder().token(BOT_TOKEN).build()


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pending_checkouts (
            token TEXT PRIMARY KEY,
            telegram_id INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            telegram_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            delivered INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def plans_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔐 ACESSAR O GRUPO", callback_data="show:plan")]
    ])


def payment_keyboard(payment_url):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 EFETUAR PAGAMENTO — R$ 9,90", url=payment_url)],
        [InlineKeyboardButton("⬅️ Voltar", callback_data="back:start")]
    ])


def build_checkout_url(telegram_id):
    token = secrets.token_urlsafe(18)
    conn = db()
    conn.execute(
        "INSERT INTO pending_checkouts(token, telegram_id, created_at) VALUES (?, ?, ?)",
        (token, telegram_id, now_iso()),
    )
    conn.commit()
    conn.close()

    separator = "&" if "?" in KIWIFY_CHECKOUT_URL else "?"
    return KIWIFY_CHECKOUT_URL + separator + urlencode({"s1": token})


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        WELCOME_MESSAGE,
        reply_markup=plans_keyboard(),
    )


async def show_plan(query):
    if not KIWIFY_CHECKOUT_URL:
        await query.edit_message_text(
            "⚠️ O pagamento ainda está sendo configurado. Tente novamente em instantes."
        )
        return

    payment_url = build_checkout_url(query.from_user.id)
    await query.edit_message_text(
        f"{PLAN_TITLE}\n\n"
        "💰 Valor: R$ 9,90\n"
        "⏳ Duração: 1 semana\n\n"
        "Clique abaixo para efetuar o pagamento pela Kiwify.",
        reply_markup=payment_keyboard(payment_url),
    )


async def plans_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 PLANO DISPONÍVEL\n\n"
        f"{PLAN_LABEL}\n"
        "⏳ Duração: 1 semana.",
        reply_markup=plans_keyboard(),
    )


async def renew_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔄 Para renovar seu acesso, envie /start e escolha novamente o plano semanal.",
        reply_markup=plans_keyboard(),
    )


async def payment_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💳 Para pagar, envie /start, toque em "ACESSAR O GRUPO" e depois em "
        ""EFETUAR PAGAMENTO — R$ 9,90"."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❓ AJUDA\n\n"
        "O acesso é feito após a confirmação do pagamento pela Kiwify.\n\n"
        "Para começar ou renovar, envie /start."
    )


async def account_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👤 MINHA CONTA\n\n"
        "Neste momento, o sistema está configurado para acesso semanal.\n\n"
        "Para adquirir ou renovar o acesso, envie /start."
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "show:plan":
        await show_plan(query)
        return

    if query.data == "back:start":
        await query.edit_message_text(
            WELCOME_MESSAGE,
            reply_markup=plans_keyboard(),
        )
        return


def extract_tracking_token(payload):
    tracking = payload.get("TrackingParameters") or {}
    return tracking.get("s1") or tracking.get("s2") or tracking.get("s3")


def find_telegram_id_from_token(token):
    if not token:
        return None

    conn = db()
    row = conn.execute(
        "SELECT telegram_id FROM pending_checkouts WHERE token = ?",
        (token,),
    ).fetchone()
    conn.close()

    return int(row["telegram_id"]) if row else None


async def send_group_access(telegram_id, order_id):
    if not GROUP_INVITE_URL:
        print("GROUP_INVITE_URL não configurado.")
        return False

    conn = db()
    row = conn.execute(
        "SELECT delivered FROM orders WHERE order_id = ?",
        (order_id,),
    ).fetchone()

    if row and row["delivered"]:
        conn.close()
        return True

    if not row:
        conn.execute(
            "INSERT INTO orders(order_id, telegram_id, status, delivered, created_at) "
            "VALUES (?, ?, 'paid', 0, ?)",
            (order_id, telegram_id, now_iso()),
        )
        conn.commit()
    conn.close()

    try:
        await tg_app.bot.send_message(
            chat_id=telegram_id,
            text=(
                "✅ PAGAMENTO CONFIRMADO!\n\n"
                "🔐 Seu acesso ao grupo está liberado.\n\n"
                "👇 Clique abaixo para entrar:"
            ),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔐 ACESSAR O GRUPO", url=GROUP_INVITE_URL)]
            ]),
        )
    except Exception as exc:
        print(f"Erro ao enviar acesso para {telegram_id}: {exc}")
        return False

    conn = db()
    conn.execute(
        "UPDATE orders SET delivered = 1 WHERE order_id = ?",
        (order_id,),
    )
    conn.commit()
    conn.close()
    return True


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "kiwify_checkout_configured": bool(KIWIFY_CHECKOUT_URL),
        "group_invite_configured": bool(GROUP_INVITE_URL),
    }


@app.post("/telegram")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, tg_app.bot)
    await tg_app.update_queue.put(update)
    return {"ok": True}


@app.post("/kiwify/webhook")
async def kiwify_endpoint(request: Request):
    payload = await request.json()

    event = payload.get("webhook_event_type")
    order_status = payload.get("order_status")

    # Only approved payments are relevant to access delivery.
    if event != "order_approved" or order_status != "paid":
        return {"ok": True, "ignored": True}

    commissions = payload.get("Commissions") or {}
    amount = commissions.get("charge_amount")
    currency = commissions.get("currency")

    # This bot sells only one product: R$ 9,90 in BRL.
    if int(amount or 0) != PLAN_PRICE_CENTS or currency != "BRL":
        return {"ok": True, "ignored": True, "reason": "unexpected_amount_or_currency"}

    order_id = payload.get("order_id")
    token = extract_tracking_token(payload)
    telegram_id = find_telegram_id_from_token(token)

    if not order_id or not telegram_id:
        # A 2xx response prevents unnecessary webhook retries.
        print("Pagamento aprovado sem token Telegram correspondente.")
        return {"ok": True, "waiting_for_telegram_link": True}

    conn = db()
    existing = conn.execute(
        "SELECT order_id, delivered FROM orders WHERE order_id = ?",
        (order_id,),
    ).fetchone()

    if existing and existing["delivered"]:
        conn.close()
        return {"ok": True, "duplicate": True}

    if not existing:
        conn.execute(
            "INSERT INTO orders(order_id, telegram_id, status, delivered, created_at) "
            "VALUES (?, ?, 'paid', 0, ?)",
            (order_id, telegram_id, now_iso()),
        )
        conn.commit()
    conn.close()

    delivered = await send_group_access(telegram_id, order_id)

    return {
        "ok": True,
        "access_sent": delivered,
    }


async def startup():
    init_db()
    await tg_app.initialize()
    await tg_app.start()

    await tg_app.bot.set_webhook(
        url=f"{PUBLIC_URL}/telegram",
        drop_pending_updates=True,
    )


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
tg_app.add_handler(CommandHandler("ajuda", help_command))
tg_app.add_handler(CallbackQueryHandler(button_handler))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("bot_telegram_v1:app", host="0.0.0.0", port=PORT)
