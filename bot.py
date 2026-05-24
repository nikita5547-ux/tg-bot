import os
import logging
import imaplib
import smtplib
import email
import feedparser
import requests
from datetime import time
import pytz
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
from groq import Groq

logging.basicConfig(level=logging.INFO)

groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])
YANDEX_EMAIL = os.environ["YANDEX_EMAIL"]
YANDEX_PASSWORD = os.environ["YANDEX_PASSWORD"]
OPENWEATHER_API_KEY = os.environ["OPENWEATHER_API_KEY"]
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
YOUR_CHAT_ID = os.environ["YOUR_CHAT_ID"]

SYSTEM_PROMPT = """Ты — персональный помощник Никиты, специалиста департамента финансового обеспечения и контроля РУДН.

О пользователе:
- Работает в РУДН, департамент финансового обеспечения и контроля
- Занимается закупками бытовой и компьютерной техники
- Ведёт дайджест — готовит материалы для публикации на сайте университета

Твои задачи:
1. Фиксировать задачи которые пишет пользователь
2. Раскладывать их по приоритетам (высокий / средний / низкий) и срокам
3. Помогать с текстами для дайджеста, письмами поставщикам, закупочными вопросами

Форматируй списки задач:
🔴 Высокий приоритет
🟡 Средний приоритет
🟢 Низкий приоритет

Отвечай коротко и по делу, на русском языке."""

chat_histories = {}

def decode_mime_str(value):
    if not value:
        return ""
    parts = decode_header(value)
    decoded = []
    for part, encoding in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(encoding or "utf-8", errors="ignore"))
        else:
            decoded.append(part)
    return "".join(decoded)

def get_last_emails(n=3):
    try:
        imap = imaplib.IMAP4_SSL("imap.yandex.ru")
        imap.login(YANDEX_EMAIL, YANDEX_PASSWORD)
        imap.select("INBOX")
        _, messages = imap.search(None, "ALL")
        mail_ids = messages[0].split()
        last_ids = mail_ids[-n:]
        result = []
        for mid in reversed(last_ids):
            _, msg_data = imap.fetch(mid, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])
            subject = decode_mime_str(msg["Subject"])
            sender = decode_mime_str(msg.get("From", ""))
            result.append(f"От: {sender}\nТема: {subject}")
        imap.logout()
        return "\n\n".join(result)
    except Exception as e:
        return f"Ошибка при получении писем: {e}"

def send_email(to, subject, body):
    try:
        msg = MIMEMultipart()
        msg["From"] = YANDEX_EMAIL
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))
        server = smtplib.SMTP_SSL("smtp.yandex.ru", 465)
        server.login(YANDEX_EMAIL, YANDEX_PASSWORD)
        server.sendmail(YANDEX_EMAIL, to, msg.as_string())
        server.quit()
        return "Письмо отправлено!"
    except Exception as e:
        return f"Ошибка отправки: {e}"

def get_weather():
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?q=Moscow&appid={OPENWEATHER_API_KEY}&units=metric&lang=ru"
        response = requests.get(url)
        data = response.json()
        temp = round(data["main"]["temp"])
        feels_like = round(data["main"]["feels_like"])
        description = data["weather"][0]["description"]
        humidity = data["main"]["humidity"]
        wind = round(data["wind"]["speed"])
        return (f"🌤 Погода в Москве:\n"
                f"{description.capitalize()}, {temp}°C (ощущается как {feels_like}°C)\n"
                f"Влажность: {humidity}%, Ветер: {wind} м/с")
    except Exception as e:
        return f"Ошибка получения погоды: {e}"

def get_news():
    feeds = [
        ("РБК", "https://rssexport.rbc.ru/rbcnews/news/30/full.rss"),
        ("Коммерсант", "https://www.kommersant.ru/RSS/news.xml"),
    ]
    result = []
    for source, url in feeds:
        try:
            feed = feedparser.parse(url)
            items = feed.entries[:3]
            news_lines = [f"• {item.title}" for item in items]
            result.append(f"📰 {source}:\n" + "\n".join(news_lines))
        except Exception as e:
            result.append(f"📰 {source}: ошибка загрузки")
    return "\n\n".join(result)

def build_morning_summary():
    weather = get_weather()
    emails = get_last_emails(3)
    news = get_news()
    summary = (
        f"☀️ Доброе утро, Никита!\n\n"
        f"{weather}\n\n"
        f"✉️ Последние письма:\n{emails}\n\n"
        f"{news}"
    )
    return summary

async def morning(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Собираю утреннюю сводку...")
    summary = build_morning_summary()
    await update.message.reply_text(summary)

async def send_morning_auto(context: ContextTypes.DEFAULT_TYPE):
    summary = build_morning_summary()
    await context.bot.send_message(chat_id=YOUR_CHAT_ID, text=summary)

async def show_emails(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Загружаю последние письма...")
    result = get_last_emails(5)
    await update.message.reply_text(result)

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

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

moscow_tz = pytz.timezone("Europe/Moscow")
app.job_queue.run_daily(
    send_morning_auto,
    time=time(8, 0, 0, tzinfo=moscow_tz)
)

app.add_handler(CommandHandler("tasks", show_tasks))
app.add_handler(CommandHandler("reset", reset))
app.add_handler(CommandHandler("mail", show_emails))
app.add_handler(CommandHandler("morning", morning))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.run_polling()
