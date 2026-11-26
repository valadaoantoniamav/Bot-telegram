import asyncio
import json
import os
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

BOT_TOKEN = os.environ["BOT_TOKEN"]
PUBLIC_URL = os.environ["PUBLIC_URL"].rstrip("/")
PORT = int(os.getenv("PORT", "8080"))
DB_PATH = os.getenv("DB_PATH", "/data/bot.db")

KIWIFY_CHECKOUT_URL = os.getenv("KIWIFY_CHECKOUT_URL", "").strip()
GROUP_INVITE_URL = os.getenv("GROUP_INVITE_URL", "").strip()
GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID", "").strip()

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
expiration_task = None


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
            created_at TEXT NOT NULL,
            paid_at TEXT,
            expires_at TEXT,
            subscription_id TEXT,
            event_type TEXT
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_orders_expires_at
        ON orders(expires_at)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_orders_telegram_id
        ON orders(telegram_id)
    """)
    conn.commit()
    conn.close()


def now_dt():
    return datetime.now(timezone.utc)


def now_iso():
    return now_dt().isoformat()


def iso_after_days(days):
    return (now_dt() + timedelta(days=days)).isoformat()


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
    await update.message.reply_text(WELCOME_MESSAGE, reply_markup=plans_keyboard())


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
        "🔄 Cobrança: semanal e recorrente\n\n"
        "Clique abaixo para assinar pela Kiwify.",
        reply_markup=payment_keyboard(payment_url),
    )


async def plans_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 PLANO DISPONÍVEL\n\n"
        f"{PLAN_LABEL}\n"
        "🔄 Cobrança recorrente semanal.",
        reply_markup=plans_keyboard(),
    )


async def renew_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔄 Para renovar ou reativar seu acesso, envie /start e escolha o plano semanal.",
        reply_markup=plans_keyboard(),
    )


async def payment_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        '💳 Para pagar, envie /start, toque em "ACESSAR O GRUPO" e depois em '
        '"EFETUAR PAGAMENTO — R$ 9,90".'
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❓ AJUDA\n\n"
        "O acesso é liberado após a confirmação do pagamento pela Kiwify.\n\n"
        "Para começar ou reativar, envie /start."
    )


async def account_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = db()
    row = conn.execute(
        "SELECT status, expires_at FROM orders "
        "WHERE telegram_id = ? ORDER BY created_at DESC LIMIT 1",
        (update.effective_user.id,),
    ).fetchone()
    conn.close()

    if not row:
        text = "👤 MINHA CONTA\n\nNenhuma assinatura encontrada.\n\nEnvie /start para começar."
    elif row["expires_at"]:
        text = (
            "👤 MINHA CONTA\n\n"
            f"Status: {row['status']}\n"
            f"Válido até: {row['expires_at']}\n\n"
            "Para renovar, envie /start."
        )
    else:
        text = "👤 MINHA CONTA\n\nAssinatura registrada.\n\nPara renovar, envie /start."

    await update.message.reply_text(text)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "show:plan":
        await show_plan(query)
        return

    if query.data == "back:start":
        await query.edit_message_text(WELCOME_MESSAGE, reply_markup=plans_keyboard())


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


def extract_subscription_id(payload):
    sub = payload.get("Subscription") or {}
    return (
        sub.get("id")
        or sub.get("subscription_id")
        or payload.get("subscription_id")
        or payload.get("subscriptionId")
    )


def extract_order_id(payload):
    return payload.get("order_id") or payload.get("orderId")


def extract_event_date(payload):
    for key in ("approved_date", "event_date", "created_at", "updated_at"):
        value = payload.get(key)
        if value:
            return value
    return now_iso()


async def create_access_link(expires_at):
    if not GROUP_CHAT_ID:
        return GROUP_INVITE_URL or None

    expire_ts = int(datetime.fromisoformat(expires_at).timestamp())
    link = await tg_app.bot.create_chat_invite_link(
        chat_id=GROUP_CHAT_ID,
        name="Acesso semanal",
        expire_date=expire_ts,
        member_limit=1,
        creates_join_request=False,
    )
    return link.invite_link


async def send_group_access(telegram_id, order_id, expires_at):
    conn = db()
    row = conn.execute(
        "SELECT delivered FROM orders WHERE order_id = ?",
        (order_id,),
    ).fetchone()
    conn.close()

    if row and row["delivered"]:
        return True

    try:
        invite_url = await create_access_link(expires_at)
        if not invite_url:
            print("GROUP_CHAT_ID/GROUP_INVITE_URL não configurado.")
            return False

        await tg_app.bot.send_message(
            chat_id=telegram_id,
            text=(
                "✅ PAGAMENTO CONFIRMADO!\n\n"
                "🔐 Seu acesso ao grupo está liberado.\n\n"
                "👇 Clique abaixo para entrar:"
            ),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔐 ACESSAR O GRUPO", url=invite_url)]
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


def upsert_paid_order(order_id, telegram_id, event_type, subscription_id=None):
    expires_at = iso_after_days(PLAN_DAYS)
    conn = db()
    existing = conn.execute(
        "SELECT * FROM orders WHERE order_id = ?",
        (order_id,),
    ).fetchone()

    if existing:
        current_expires = existing["expires_at"]
        try:
            current_dt = datetime.fromisoformat(current_expires) if current_expires else now_dt()
        except Exception:
            current_dt = now_dt()

        # A renewal starts a new paid 7-day period from the later of
        # the current expiry or the renewal time.
        base = max(current_dt, now_dt())
        expires_at = (base + timedelta(days=PLAN_DAYS)).isoformat()

        conn.execute(
            "UPDATE orders SET telegram_id=?, status='active', expires_at=?, "
            "subscription_id=COALESCE(?, subscription_id), event_type=? "
            "WHERE order_id=?",
            (telegram_id, expires_at, subscription_id, event_type, order_id),
        )
    else:
        conn.execute(
            "INSERT INTO orders(order_id, telegram_id, status, delivered, created_at, "
            "paid_at, expires_at, subscription_id, event_type) "
            "VALUES (?, ?, 'active', 0, ?, ?, ?, ?, ?)",
            (
                order_id,
                telegram_id,
                now_iso(),
                extract_event_date({"approved_date": now_iso()}),
                expires_at,
                subscription_id,
                event_type,
            ),
        )

    conn.commit()
    conn.close()
    return expires_at


async def remove_expired_member(telegram_id):
    if not GROUP_CHAT_ID:
        print("GROUP_CHAT_ID não configurado; não é possível remover membros automaticamente.")
        return False

    try:
        # Ban briefly, then unban: this removes the member while allowing
        # a future valid invite after a renewal.
        await tg_app.bot.ban_chat_member(
            chat_id=GROUP_CHAT_ID,
            user_id=telegram_id,
            until_date=int(time.time()) + 60,
            revoke_messages=False,
        )
        await tg_app.bot.unban_chat_member(
            chat_id=GROUP_CHAT_ID,
            user_id=telegram_id,
            only_if_banned=True,
        )
        return True
    except Exception as exc:
        print(f"Erro ao remover usuário {telegram_id}: {exc}")
        return False


async def expiration_loop():
    while True:
        try:
            conn = db()
            rows = conn.execute(
                "SELECT order_id, telegram_id FROM orders "
                "WHERE status='active' AND expires_at IS NOT NULL AND expires_at <= ?",
                (now_iso(),),
            ).fetchall()
            conn.close()

            for row in rows:
                removed = await remove_expired_member(int(row["telegram_id"]))
                if removed:
                    conn = db()
                    conn.execute(
                        "UPDATE orders SET status='expired' WHERE order_id=?",
                        (row["order_id"],),
                    )
                    conn.commit()
                    conn.close()

                    try:
                        await tg_app.bot.send_message(
                            chat_id=int(row["telegram_id"]),
                            text=(
                                "⏳ Seu acesso ao grupo expirou.\n\n"
                                "Para continuar, envie /start e faça uma nova assinatura."
                            ),
                        )
                    except Exception as exc:
                        print(f"Não foi possível avisar {row['telegram_id']}: {exc}")

        except Exception as exc:
            print(f"Erro na rotina de expiração: {exc}")

        await asyncio.sleep(300)


async def handle_approved_payment(payload):
    order_id = extract_order_id(payload)
    token = extract_tracking_token(payload)
    telegram_id = find_telegram_id_from_token(token)

    if not order_id or not telegram_id:
        print("Pagamento aprovado sem token Telegram correspondente.")
        return False

    subscription_id = extract_subscription_id(payload)
    expires_at = upsert_paid_order(
        order_id,
        telegram_id,
        "order_approved",
        subscription_id,
    )
    return await send_group_access(telegram_id, order_id, expires_at)


async def handle_renewal(payload):
    order_id = extract_order_id(payload)
    token = extract_tracking_token(payload)
    telegram_id = find_telegram_id_from_token(token)

    if not telegram_id:
        sub_id = extract_subscription_id(payload)
        conn = db()
        row = conn.execute(
            "SELECT telegram_id, order_id FROM orders WHERE subscription_id = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (sub_id,),
        ).fetchone() if sub_id else None
        conn.close()

        if row:
            telegram_id = int(row["telegram_id"])
            order_id = row["order_id"]

    if not telegram_id:
        print("Renovação recebida sem vínculo com Telegram.")
        return False

    if not order_id:
        order_id = f"renewal-{extract_subscription_id(payload) or secrets.token_hex(8)}"

    subscription_id = extract_subscription_id(payload)
    expires_at = upsert_paid_order(
        order_id,
        telegram_id,
        "subscription_renewed",
        subscription_id,
    )

    # Send a fresh one-use link when possible; the member may already be inside.
    try:
        invite_url = await create_access_link(expires_at)
        if invite_url:
            await tg_app.bot.send_message(
                chat_id=telegram_id,
                text=(
                    "🔄 ASSINATURA RENOVADA!\n\n"
                    "Seu acesso foi estendido por mais 1 semana."
                ),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔐 ACESSAR O GRUPO", url=invite_url)]
                ]),
            )
    except Exception as exc:
        print(f"Erro ao enviar renovação para {telegram_id}: {exc}")

    return True


async def handle_cancellation(payload):
    subscription_id = extract_subscription_id(payload)
    order_id = extract_order_id(payload)
    token = extract_tracking_token(payload)

    telegram_id = find_telegram_id_from_token(token)

    conn = db()
    row = None
    if subscription_id:
        row = conn.execute(
            "SELECT telegram_id, order_id FROM orders WHERE subscription_id = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (subscription_id,),
        ).fetchone()
    if not row and order_id:
        row = conn.execute(
            "SELECT telegram_id, order_id FROM orders WHERE order_id = ?",
            (order_id,),
        ).fetchone()
    conn.close()

    if not telegram_id and row:
        telegram_id = int(row["telegram_id"])

    if not telegram_id:
        print("Cancelamento recebido sem vínculo com Telegram.")
        return False

    # Cancellation prevents future charges; the current paid period remains valid.
    conn = db()
    if row:
        conn.execute(
            "UPDATE orders SET status='canceled', event_type='subscription_canceled' "
            "WHERE order_id=?",
            (row["order_id"],),
        )
    elif order_id:
        conn.execute(
            "UPDATE orders SET status='canceled', event_type='subscription_canceled' "
            "WHERE order_id=?",
            (order_id,),
        )
    conn.commit()
    conn.close()
    return True


async def handle_refund_or_chargeback(payload):
    order_id = extract_order_id(payload)
    token = extract_tracking_token(payload)
    telegram_id = find_telegram_id_from_token(token)

    conn = db()
    row = conn.execute(
        "SELECT telegram_id FROM orders WHERE order_id = ?",
        (order_id,),
    ).fetchone() if order_id else None
    conn.close()

    if not telegram_id and row:
        telegram_id = int(row["telegram_id"])

    if not telegram_id:
        return False

    removed = await remove_expired_member(telegram_id)
    if removed and order_id:
        conn = db()
        conn.execute(
            "UPDATE orders SET status='revoked' WHERE order_id=?",
            (order_id,),
        )
        conn.commit()
        conn.close()
    return removed


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "kiwify_checkout_configured": bool(KIWIFY_CHECKOUT_URL),
        "group_invite_configured": bool(GROUP_INVITE_URL or GROUP_CHAT_ID),
        "auto_expiration_configured": bool(GROUP_CHAT_ID),
        "recurring_subscription_supported": True,
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

    print("Kiwify webhook:", json.dumps({
        "event": event,
        "order_id": extract_order_id(payload),
        "subscription_id": extract_subscription_id(payload),
    }, ensure_ascii=False))

    if event == "order_approved" and order_status == "paid":
        commissions = payload.get("Commissions") or {}
        amount = int(commissions.get("charge_amount") or 0)
        currency = commissions.get("currency")

        if amount != PLAN_PRICE_CENTS or currency != "BRL":
            return {"ok": True, "ignored": True, "reason": "unexpected_amount_or_currency"}

        delivered = await handle_approved_payment(payload)
        return {"ok": True, "access_sent": delivered}

    if event == "subscription_renewed":
        renewed = await handle_renewal(payload)
        return {"ok": True, "renewed": renewed}

    if event == "subscription_canceled":
        canceled = await handle_cancellation(payload)
        return {"ok": True, "canceled": canceled}

    if event in {"order_refunded", "chargeback"}:
        revoked = await handle_refund_or_chargeback(payload)
        return {"ok": True, "revoked": revoked}

    # subscription_late is intentionally not an immediate removal:
    # Kiwify can retry the recurring charge. The member remains active
    # until the already-paid period expires.
    return {"ok": True, "ignored": True}


async def startup():
    global expiration_task
    init_db()
    await tg_app.initialize()
    await tg_app.start()

    await tg_app.bot.set_webhook(
        url=f"{PUBLIC_URL}/telegram",
        drop_pending_updates=True,
    )

    expiration_task = asyncio.create_task(expiration_loop())


async def shutdown():
    global expiration_task
    if expiration_task:
        expiration_task.cancel()
        try:
            await expiration_task
        except asyncio.CancelledError:
            pass

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
