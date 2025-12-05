import asyncio
import os
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import CommandStart
from openai import OpenAI

BOT_TOKEN = os.environ.get("BOT_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

if not BOT_TOKEN:
    raise ValueError("Токен бота не найден! Добавь BOT_TOKEN в секреты.")

if not OPENAI_API_KEY:
    raise ValueError("OpenAI API ключ не найден! Добавь OPENAI_API_KEY в секреты.")

client = OpenAI(api_key=OPENAI_API_KEY)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


@dp.message(CommandStart())
async def start(message: Message) -> None:
    await message.answer(
        "👋 Привет! Я AI-бот DataHub.\n"
        "Задай мне любой вопрос о ВУЗах Казахстана.\n\n"
        "Например:\n"
        "• Лучшие IT вузы в Астане?\n"
        "• Сравни КБТУ и AITU.\n"
        "• Где самый низкий проходной балл на экономику?"
    )


async def ask_gpt(prompt: str) -> str:
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content":
                "Ты — эксперт по университетам Казахстана. "
                "Отвечай структурировано, коротко, точными фактами. "
                "Если информации нет — дай разумную оценку."
            },
            {"role": "user", "content": prompt}
        ],
        max_tokens=500
    )
    return response.choices[0].message.content or ""


@dp.message()
async def ai_answer(message: Message) -> None:
    user_text = message.text
    if not user_text:
        return

    await message.answer("⏳ Думаю...")

    try:
        reply = await ask_gpt(user_text)
        await message.answer(reply)
    except Exception as e:
        await message.answer("⚠️ Ошибка при обращении к ИИ.")
        print(e)


async def main() -> None:
    print("🚀 AI DataHub бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
