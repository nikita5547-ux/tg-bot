import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from groq import Groq

logging.basicConfig(level=logging.INFO)

groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])

SYSTEM_PROMPT = """Ты — персональный помощник сотрудника финансового отдела университета. 
Отвечай коротко и по делу, на русском языке. 
Помогай с финансовыми вопросами, анализом данных, составлением писем и документов.
Если вопрос не по теме — всё равно помогай, но держи фокус на рабочих задачах."""

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ]
    )
    reply = response.choices[0].message.content
    await update.message.reply_text(reply)

app = ApplicationBuilder().token(os.environ["TELEGRAM_TOKEN"]).build()
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.run_polling()
