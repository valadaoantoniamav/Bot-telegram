import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "COLOQUE_SEU_TOKEN_AQUI")
PUBLIC_URL = os.getenv("PUBLIC_URL", "").rstrip("/")
PORT = int(os.getenv("PORT", "8080"))

PAYMENT_LINKS = {
    "7d": "https://pay.kiwify.com.br/nNtYoc4",
    "30d": "https://pay.kiwify.com.br/VTI5T6a",
    "lifetime": "https://pay.kiwify.com.br/cIuDDKM",
}

PLANS = {
    "7d": {"button": "📅 7 DIAS — R$ 29,90", "title": "📅 ACESSO POR 7 DIAS", "price": "R$ 29,90"},
    "30d": {"button": "👑 MENSAL — R$ 49,90", "title": "👑 ACESSO MENSAL", "price": "R$ 49,90"},
    "lifetime": {"button": "♾️ VITALÍCIO — R$ 79,90", "title": "♾️ ACESSO VITALÍCIO", "price": "R$ 79,90"},
}


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
        "4️⃣ Finalize o pagamento pela Kiwify.\n\nApós a confirmação, seu acesso será processado."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❓ AJUDA\n\n"
        "Escolha um dos planos disponíveis e realize o pagamento pela Kiwify.\n\n"
        "Após a confirmação do pagamento, o acesso ao canal privado será liberado "
        "de acordo com o plano adquirido.\n\n🔄 Para renovar, use /renovar."
    )


async def account_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👤 MINHA CONTA\n\n"
        "O sistema de consulta de pagamento, validade e acesso será conectado na próxima etapa."
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "back:plans":
        await query.edit_message_text("📋 Escolha seu plano de acesso:", reply_markup=plans_keyboard())
        return

    if data == "account":
        await query.edit_message_text(
            "👤 MINHA CONTA\n\n"
            "O controle de pagamento, validade e acesso será conectado na próxima etapa.",
            reply_markup=back_keyboard(),
        )
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
        link = PAYMENT_LINKS[plan_id]
        text = (
            f"{plan['title']}\n\n💰 Valor: {plan['price']}\n\n"
            "🔐 Acesso ao canal privado pelo período correspondente ao plano.\n\n"
            "⚡ Clique abaixo para realizar o pagamento."
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 PAGAR AGORA", url=link)],
            [InlineKeyboardButton("⬅️ Voltar aos planos", callback_data="back:plans")],
        ])
        await query.edit_message_text(text, reply_markup=keyboard)


def main():
    if BOT_TOKEN == "COLOQUE_SEU_TOKEN_AQUI":
        raise RuntimeError("Defina a variável de ambiente BOT_TOKEN com o token do BotFather.")

    if not PUBLIC_URL:
        raise RuntimeError("Defina a variável PUBLIC_URL com a URL pública do serviço Railway.")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("planos", plans_command))
    app.add_handler(CommandHandler("minhaconta", account_command))
    app.add_handler(CommandHandler("renovar", renew_command))
    app.add_handler(CommandHandler("pagamento", payment_command))
    app.add_handler(CommandHandler("idioma", language_command))
    app.add_handler(CommandHandler("ajuda", help_command))
    app.add_handler(CallbackQueryHandler(button_handler))

    webhook_path = f"telegram/{BOT_TOKEN}"
    print("Bot iniciado em modo webhook.")
    print(f"Webhook público: {PUBLIC_URL}/{webhook_path}")

    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=webhook_path,
        webhook_url=f"{PUBLIC_URL}/{webhook_path}",
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
