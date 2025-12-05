import asyncio
import requests
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import CommandStart

BOT_TOKEN = "ВСТАВЬ_ТУТ_СВОЙ_ТОКЕН"

# Бесплатная модель HuggingFace без API ключей
HF_MODEL_URL = "https://api-inference.huggingface.co/models/HuggingFaceH4/zephyr-7b-beta"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "🤖 Привет! Я бесплатный ИИ-бот на HuggingFace.\n"
        "Задай любой вопрос!"
    )


def ask_hf(prompt: str) -> str:
    """Отправка запроса на бесплатную HF модель"""

    if prompt is None:
        return "Пожалуйста, отправь текстовое сообщение."

    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": 200,
            "temperature": 0.7
        }
    }

    try:
        response = requests.post(HF_MODEL_URL, json=payload)
        data = response.json()

        # Если модель "заснула" (HF подгружает её)
        if "error" in data:
            return "⚠️ Модель прогружается. Попробуй снова через 5 секунд."

        # HF возвращает список вариантов
        return data[0]["generated_text"]

    except Exception as e:
        return f"Ошибка HuggingFace: {e}"


@dp.message()
async def chat(message: Message):
    text = message.text

    await message.answer("⏳ Генерирую ответ...")

    reply = ask_hf(text)
    await message.answer(reply)


async def main():
    print("🚀 Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())