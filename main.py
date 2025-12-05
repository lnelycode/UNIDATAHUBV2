import asyncio
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message

# =============================
# 👉 ВСТАВЬ СВОЙ ТОКЕН СЮДА 👇
BOT_TOKEN = "8567318943:AAF44rNeeo5tdWY8ScdAnYrzfr5YAcFXMCs"
# =============================

# Проверка токена
if BOT_TOKEN == "" or BOT_TOKEN == "8567318943:AAF44rNeeo5tdWY8ScdAnYrzfr5YAcFXMCs":
    raise ValueError("❌ Ты забыл вставить токен бота!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


@dp.message(CommandStart())
async def start(message: Message):
    await message.answer("🔥 Привет! Бот успешно работает на Replit!")


async def main():
    print("🚀 Бот запущен! Ожидаю сообщения...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())