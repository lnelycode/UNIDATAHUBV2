import asyncio
import google.generativeai as genai
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import CommandStart

# =============================
# 👉 ВСТАВЬ ТУТ СВОИ КЛЮЧИ
BOT_TOKEN = "8567318943:AAF44rNeeo5tdWY8ScdAnYrzfr5YAcFXMCs"
GEMINI_API_KEY = ""
# =============================

# Проверка
if BOT_TOKEN.startswith("ВСТАВЬ"):
    raise RuntimeError("❌ Ты не указал BOT_TOKEN от BotFather.")
if GEMINI_API_KEY.startswith("ВСТАВЬ"):
    raise RuntimeError("❌ Ты не указал Gemini API Key.")

# Настройка Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-pro")

# Настройка Telegram
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# ---------- Команда /start ----------
@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "👋 Привет! Я AI-бот DataHub (Gemini).\n"
        "Задавай любые вопросы о вузах Казахстана, ЕНТ, специальностях и т.д.\n\n"
        "Например:\n"
        "• Лучшие IT вузы в Казахстане?\n"
        "• Сравни КБТУ и AITU\n"
        "• Куда поступить с 75 баллами?\n"
        "• Какие специальности есть в NU?\n"
    )


# ---------- Функция общения с Gemini ----------
async def ask_gemini(prompt: str) -> str:
    try:
        response = model.generate_content(
            f"""
Ты — эксперт по образованию, вузам Казахстана, ЕНТ, специальностям и поступлению.
Отвечай структурировано, понятно, с фактами.
Никогда не выдумывай ложные данные — используй общую информацию.

Запрос пользователя:
{prompt}
"""
        )
        return response.text

    except Exception as e:
        # Любую ошибку возвращаем в чат
        return f"⚠️ Ошибка Gemini: {e}"


# ---------- Основной обработчик всех сообщений ----------
@dp.message()
async def ai_answer(message: Message):
    user_text = message.text
    await message.answer("⏳ Думаю...")

    reply = await ask_gemini(user_text)
    await message.answer(reply)


# ---------- Запуск бота ----------
async def main():
    print("🚀 Gemini AI бот запущен!")
    await dp.start_polling(bot)

asyncio.run(main())