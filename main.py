import asyncio
import os
import google.generativeai as genai
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import CommandStart

BOT_TOKEN = os.environ.get("BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not BOT_TOKEN:
    raise ValueError("Токен бота не найден! Добавь BOT_TOKEN в секреты.")

if not GEMINI_API_KEY:
    raise ValueError("Gemini API ключ не найден! Добавь GEMINI_API_KEY в секреты.")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-pro")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


@dp.message(CommandStart())
async def start(message: Message) -> None:
    await message.answer(
        "👋 Привет! Я AI-бот DataHub (Gemini).\n"
        "Задавай любые вопросы о вузах Казахстана, ЕНТ, специальностях и т.д.\n\n"
        "Например:\n"
        "• Лучшие IT вузы в Казахстане?\n"
        "• Сравни КБТУ и AITU\n"
        "• Куда поступить с 75 баллами?\n"
        "• Какие специальности есть в NU?\n"
    )


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
        return response.text or ""
    except Exception as e:
        return f"⚠️ Ошибка Gemini: {e}"


@dp.message()
async def ai_answer(message: Message) -> None:
    user_text = message.text
    if not user_text:
        return

    await message.answer("⏳ Думаю...")

    reply = await ask_gemini(user_text)
    await message.answer(reply)


async def main() -> None:
    print("🚀 Gemini AI бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
