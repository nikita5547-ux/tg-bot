import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
from groq import Groq

logging.basicConfig(level=logging.INFO)

groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])

SYSTEM_PROMPT = """Ты — персональный помощник Никиты, специалиста департамента финансового обеспечения и контроля РУДН.

О пользователе:
- Работает в РУДН, департамент финансового обеспечения и контроля
- Занимается закупками бытовой и компьютерной техники
- Ведёт дайджест — готовит материалы для публикации на сайте университета

Твои задачи:
1. Фиксировать задачи которые пишет пользователь
2. Раскладывать их по приоритетам (высокий / средний / низкий) и срокам
3. По команде /tasks — показывать все текущие задачи структурированно
4. Помогать с текстами для дайджеста, письмами поставщикам, закупочными вопросами

Формат списка задач:
🔴 Высокий приоритет
🟡 Средний приоритет
🟢 Низкий приоритет

Отвечай коротко и по делу, на русском языке."""

chat_histories = {}

async def show_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in chat_histories or not chat_histories[user_id]:
        await update.message.reply_text("Задач пока нет. Напиши что нужно сделать!")
        return

    chat_histories[user_id].append({"role": "user", "content": "Покажи все текущие задачи структурированно по приоритетам"})

    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "system", "content": SYSTEM_PROMPT}] + chat_histories[user_id]
    )

    reply = response.choices[0].message.content
    chat_histories[user_id].append({"role": "assistant", "content": reply})
    await update.message.reply_text(reply)

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    chat_histories[user_id] = []
    await update.message.reply_text("История очищена. Начинаем заново!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_message = update.message.text

    if user_id not in chat_histories:
        chat_histories[user_id] = []

    chat_histories[user_id].append({"role": "user", "content": user_message})

    if len(chat_histories[user_id]) > 30:
        chat_histories[user_id] = chat_histories[user_id][-30:]

    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "system", "content": SYSTEM_PROMPT}] + chat_histories[user_id]
    )

    reply = response.choices[0].message.content
    chat_histories[user_id].append({"role": "assistant", "content": reply})
    await update.message.reply_text(reply)

app = ApplicationBuilder().token(os.environ["TELEGRAM_TOKEN"]).build()
app.add_handler(CommandHandler("tasks", show_tasks))
app.add_handler(CommandHandler("reset", reset))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.run_polling()
