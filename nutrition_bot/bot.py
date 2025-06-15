import logging
import os
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from .giga_api import GigaChatClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

(
    AGE,
    GENDER,
    WEIGHT,
    HEIGHT,
    ACTIVITY,
    WORKOUTS,
    PREFERENCES,
    ALLERGIES,
    FASTING,
    SUMMARY,
) = range(10)

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GIGACHAT_CLIENT_ID = os.getenv("GIGACHAT_CLIENT_ID")
GIGACHAT_CLIENT_SECRET = os.getenv("GIGACHAT_CLIENT_SECRET")

giga_client = GigaChatClient(GIGACHAT_CLIENT_ID, GIGACHAT_CLIENT_SECRET)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Здравствуйте! Давайте подберем ваш рацион. Сколько вам лет?"
    )
    return AGE

async def age(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["age"] = update.message.text
    reply_keyboard = [["Мужской", "Женский"]]
    await update.message.reply_text(
        "Ваш пол?",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True),
    )
    return GENDER

async def gender(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["gender"] = update.message.text
    await update.message.reply_text("Ваш вес (кг)?", reply_markup=ReplyKeyboardRemove())
    return WEIGHT

async def weight(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["weight"] = update.message.text
    await update.message.reply_text("Ваш рост (см)?")
    return HEIGHT

async def height(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["height"] = update.message.text
    reply_keyboard = [["Сидячая", "Стоячая"]]
    await update.message.reply_text(
        "Характер работы?",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True),
    )
    return ACTIVITY

async def activity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["activity"] = update.message.text
    await update.message.reply_text("Сколько тренировок в неделю?")
    return WORKOUTS

async def workouts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["workouts"] = update.message.text
    await update.message.reply_text("Пищевые предпочтения?")
    return PREFERENCES

async def preferences(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["preferences"] = update.message.text
    await update.message.reply_text("Есть ли аллергии?")
    return ALLERGIES

async def allergies(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["allergies"] = update.message.text
    reply_keyboard = [["Да", "Нет"]]
    await update.message.reply_text(
        "Интересует интервальное голодание?",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True),
    )
    return FASTING

async def fasting(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["fasting"] = update.message.text
    summary = "\n".join(f"{k}: {v}" for k, v in context.user_data.items())
    prompt = f"Составь рацион по данным:\n{summary}"
    plan = giga_client.generate(prompt)
    await update.message.reply_text(
        f"Ваш индивидуальный рацион:\n{plan}", reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Диалог прерван.", reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END


def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, age)],
            GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, gender)],
            WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, weight)],
            HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, height)],
            ACTIVITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, activity)],
            WORKOUTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, workouts)],
            PREFERENCES: [MessageHandler(filters.TEXT & ~filters.COMMAND, preferences)],
            ALLERGIES: [MessageHandler(filters.TEXT & ~filters.COMMAND, allergies)],
            FASTING: [MessageHandler(filters.TEXT & ~filters.COMMAND, fasting)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    logger.info("Bot started")
    app.run_polling()

if __name__ == "__main__":
    main()
