import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "COLOQUE_SEU_TOKEN_AQUI")

PAYMENT_LINKS = {
    "pt": {
        "24h": "https://www.asaas.com/000/c/iz0rt71qqtlsa4mx",
        "7d": "https://www.asaas.com/000/c/d3sf864jwyku14f2",
        "30d": "https://www.asaas.com/000/c/yc49j7qgy9308lp9",
    },
    "en": {
        # Stripe links will be added later.
        "24h": None,
        "7d": None,
        "30d": None,
    },
}

PLANS = {
    "pt": {
        "24h": ("🔥 24 HORAS — R$ 11,90", "🔥 ACESSO POR 24 HORAS", "R$ 11,90"),
        "7d": ("📅 7 DIAS — R$ 47,00", "📅 ACESSO POR 7 DIAS", "R$ 47,00"),
        "30d": ("👑 30 DIAS — R$ 97,00", "👑 ACESSO POR 30 DIAS", "R$ 97,00"),
    },
    "en": {
        "24h": ("🔥 24 HOURS — $4.99", "🔥 24-HOUR ACCESS", "$4.99"),
        "7d": ("📅 7 DAYS — $19.99", "📅 7-DAY ACCESS", "$19.99"),
        "30d": ("👑 30 DAYS — $49.99", "👑 30-DAY ACCESS", "$49.99"),
    },
}

user_languages = {}


def language_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇧🇷 Português", callback_data="lang:pt"),
            InlineKeyboardButton("🇺🇸 English", callback_data="lang:en"),
        ]
    ])


def plans_keyboard(lang: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(PLANS[lang]["24h"][0], callback_data="plan:24h")],
        [InlineKeyboardButton(PLANS[lang]["7d"][0], callback_data="plan:7d")],
        [InlineKeyboardButton(PLANS[lang]["30d"][0], callback_data="plan:30d")],
        [
            InlineKeyboardButton("👤 Minha conta" if lang == "pt" else "👤 My account",
                                 callback_data="account"),
            InlineKeyboardButton("🌎 Idioma" if lang == "pt" else "🌎 Language",
                                 callback_data="language"),
        ],
        [InlineKeyboardButton("❓ Ajuda" if lang == "pt" else "❓ Help",
                              callback_data="help")],
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_languages.pop(update.effective_user.id, None)
    text = (
        "👋 Bem-vindo!\n\n"
        "Antes de continuar, escolha seu idioma:"
    )
    await update.message.reply_text(text, reply_markup=language_keyboard())


async def show_plans(update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str):
    text = (
        "🇧🇷 Escolha seu plano de acesso:"
        if lang == "pt"
        else "🇺🇸 Choose your access plan:"
    )
    await update.effective_message.edit_text(text, reply_markup=plans_keyboard(lang))


async def plans_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = user_languages.get(update.effective_user.id, "pt")
    await update.message.reply_text(
        "🇧🇷 Escolha seu plano de acesso:" if lang == "pt" else "🇺🇸 Choose your access plan:",
        reply_markup=plans_keyboard(lang),
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    data = query.data

    if data == "language":
        await query.edit_message_text(
            "🌎 Escolha seu idioma:" if user_languages.get(user_id, "pt") == "pt"
            else "🌎 Choose your language:",
            reply_markup=language_keyboard(),
        )
        return

    if data.startswith("lang:"):
        lang = data.split(":")[1]
        user_languages[user_id] = lang
        await show_plans(update, context, lang)
        return

    lang = user_languages.get(user_id, "pt")

    if data.startswith("plan:"):
        plan = data.split(":")[1]
        title, _, price = PLANS[lang][plan]
        link = PAYMENT_LINKS[lang][plan]

        if link:
            pay_text = "💳 PAGAR AGORA" if lang == "pt" else "💳 PAY NOW"
            back_text = "⬅️ Voltar" if lang == "pt" else "⬅️ Back"

            text = (
                f"{title}\n\n"
                f"💰 Valor: {price}\n\n"
                + (
                    "Acesso ao canal privado pelo período escolhido.\n\n"
                    "⚡ Após a confirmação do pagamento, seu acesso será liberado."
                    if lang == "pt"
                    else
                    "Access to the private channel for the selected period.\n\n"
                    "⚡ After payment is confirmed, your access will be released."
                )
            )

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(pay_text, url=link)],
                [InlineKeyboardButton(back_text, callback_data="back:plans")],
            ])
            await query.edit_message_text(text, reply_markup=keyboard)
        else:
            await query.edit_message_text(
                "💳 Payment for this plan is not configured yet."
                if lang == "en"
                else "💳 O pagamento deste plano ainda não foi configurado.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(
                        "⬅️ Voltar" if lang == "pt" else "⬅️ Back",
                        callback_data="back:plans"
                    )]
                ])
            )
        return

    if data == "back:plans":
        await show_plans(update, context, lang)
        return

    if data == "account":
        text = (
            "👤 Minha conta\n\n"
            "Status: Em configuração\n\n"
            "O controle de pagamento e acesso será conectado na próxima etapa."
            if lang == "pt"
            else
            "👤 My account\n\n"
            "Status: Setup in progress\n\n"
            "Payment and access control will be connected in the next step."
        )
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "⬅️ Voltar" if lang == "pt" else "⬅️ Back",
                    callback_data="back:plans"
                )]
            ])
        )
        return

    if data == "help":
        text = (
            "❓ Ajuda\n\n"
            "Escolha um plano, realize o pagamento e aguarde a confirmação."
            if lang == "pt"
            else
            "❓ Help\n\n"
            "Choose a plan, complete the payment and wait for confirmation."
        )
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "⬅️ Voltar" if lang == "pt" else "⬅️ Back",
                    callback_data="back:plans"
                )]
            ])
        )


async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌎 Escolha seu idioma:", reply_markup=language_keyboard()
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = user_languages.get(update.effective_user.id, "pt")
    text = (
        "❓ Ajuda\n\nEscolha um plano e siga as instruções de pagamento."
        if lang == "pt"
        else
        "❓ Help\n\nChoose a plan and follow the payment instructions."
    )
    await update.message.reply_text(text)


def main():
    if BOT_TOKEN == "COLOQUE_SEU_TOKEN_AQUI":
        raise RuntimeError("Defina a variável de ambiente BOT_TOKEN com o token do BotFather.")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("planos", plans_command))
    app.add_handler(CommandHandler("idioma", language_command))
    app.add_handler(CommandHandler("ajuda", help_command))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("Bot iniciado.")
    app.run_polling()


if __name__ == "__main__":
    main()
