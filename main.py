import asyncio
import os
from aiogram import Bot, Dispatcher
from aiogram.types import Message, CallbackQuery
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Токен бота не найден! Добавь BOT_TOKEN в секреты.")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


def reply_main_menu() -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton(text="🔎 Найти ВУЗ")],
        [KeyboardButton(text="⚖️ Сравнить ВУЗы")],
        [KeyboardButton(text="❓ О проекте")],
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


UNIVERSITIES = [
    {
        "id": "kbtu",
        "name": "КБТУ",
        "city": "Алматы",
        "specialties": ["IT", "Нефтегаз"],
        "min_score": 100,
        "about": "КБТУ — ведущий технический вуз Казахстана.",
        "programs": "IT, Нефтегаз, Физика, Экономика, Менеджмент.",
        "admission": "Мин. балл: 100. Есть гранты.",
        "international": "Обмен с Великобританией, Турцией и ЕС.",
        "tour": "https://example.com/kbtu-tour"
    },
    {
        "id": "kaznu",
        "name": "КазНУ аль-Фараби",
        "city": "Алматы",
        "specialties": ["IT", "Физика", "Биология"],
        "min_score": 95,
        "about": "КазНУ — топовый государственный университет.",
        "programs": "80+ образовательных направлений.",
        "admission": "Мин. балл: 95. Много госгрантов.",
        "international": "Партнёры: Германия, США, Корея.",
        "tour": "https://example.com/kaznu-tour"
    },
    {
        "id": "sdu",
        "name": "СДУ",
        "city": "Алматы",
        "specialties": ["IT", "Педагогика"],
        "min_score": 90,
        "about": "СДУ — современный частный университет.",
        "programs": "IT, Педагогика, Гуманитарные направления.",
        "admission": "Мин. балл: 90. Есть скидки до 50%.",
        "international": "Партнёрства с Турцией и странами ЕС.",
        "tour": "https://example.com/sdu-tour"
    }
]

user_compare: dict[int, set[str]] = {}


@dp.message(CommandStart())
async def start(message: Message) -> None:
    await message.answer(
        "Добро пожаловать в DataHub!\n\nВыберите действие:",
        reply_markup=reply_main_menu()
    )


@dp.message(lambda m: m.text == "🔎 Найти ВУЗ")
async def reply_find(message: Message) -> None:
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Город: Алматы", callback_data="find_city:Алматы")],
        [InlineKeyboardButton(text="Специальность: IT", callback_data="find_spec:IT")],
        [InlineKeyboardButton(text="Мин. балл: 100+", callback_data="find_score:100")],
    ])
    await message.answer("Выберите критерий поиска:", reply_markup=kb)


@dp.message(lambda m: m.text == "⚖️ Сравнить ВУЗы")
async def reply_compare(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else 0
    selected = user_compare.get(user_id)

    if not selected:
        await message.answer("⚠️ Пока ничего не выбрано.", reply_markup=reply_main_menu())
        return

    text = "⚖️ *Сравнение ВУЗов*\n\n"
    for uid in selected:
        uni = get_uni(uid)
        if uni:
            text += (
                f"🔸 *{uni['name']}*\n"
                f"Город: {uni['city']}\n"
                f"Мин. балл: {uni['min_score']}\n"
                f"Специальности: {', '.join(uni['specialties'])}\n\n"
            )

    await message.answer(text, parse_mode="Markdown", reply_markup=reply_main_menu())


@dp.message(lambda m: m.text == "❓ О проекте")
async def reply_about(message: Message) -> None:
    await message.answer(
        "📘 *О проекте DataHub*\n\n"
        "Каталог вузов Казахстана с поиском и сравнением.",
        parse_mode="Markdown"
    )


def search(city: str | None = None, spec: str | None = None, score: int | None = None) -> list[dict]:
    results = UNIVERSITIES
    if city:
        results = [u for u in results if u["city"] == city]
    if spec:
        results = [u for u in results if spec in u["specialties"]]
    if score:
        results = [u for u in results if u["min_score"] >= score]
    return results


def get_uni(uid: str) -> dict | None:
    return next((u for u in UNIVERSITIES if u["id"] == uid), None)


def uni_back(uid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"uni:{uid}")]
    ])


@dp.callback_query(lambda c: c.data and c.data.startswith("find_city:"))
async def find_city(callback: CallbackQuery) -> None:
    if callback.data and callback.message:
        city = callback.data.split(":")[1]
        unis = search(city=city)
        if not unis:
            await callback.message.edit_text(f"Вузы в городе {city}\n\n❗ Ничего не найдено.")
        else:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=u["name"], callback_data=f"uni:{u['id']}")]
                for u in unis
            ])
            await callback.message.edit_text(f"Вузы в городе {city}\n\nВыберите университет:", reply_markup=kb)
    await callback.answer()


@dp.callback_query(lambda c: c.data and c.data.startswith("find_spec:"))
async def find_spec(callback: CallbackQuery) -> None:
    if callback.data and callback.message:
        spec = callback.data.split(":")[1]
        unis = search(spec=spec)
        if not unis:
            await callback.message.edit_text(f"Вузы по специальности {spec}\n\n❗ Ничего не найдено.")
        else:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=u["name"], callback_data=f"uni:{u['id']}")]
                for u in unis
            ])
            await callback.message.edit_text(f"Вузы по специальности {spec}\n\nВыберите университет:", reply_markup=kb)
    await callback.answer()


@dp.callback_query(lambda c: c.data and c.data.startswith("find_score:"))
async def find_score(callback: CallbackQuery) -> None:
    if callback.data and callback.message:
        score = int(callback.data.split(":")[1])
        unis = search(score=score)
        if not unis:
            await callback.message.edit_text(f"Вузы с баллом от {score}\n\n❗ Ничего не найдено.")
        else:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=u["name"], callback_data=f"uni:{u['id']}")]
                for u in unis
            ])
            await callback.message.edit_text(f"Вузы с баллом от {score}\n\nВыберите университет:", reply_markup=kb)
    await callback.answer()


@dp.callback_query(lambda c: c.data and c.data.startswith("uni:"))
async def uni_menu(callback: CallbackQuery) -> None:
    if callback.data and callback.message:
        uid = callback.data.split(":")[1]
        uni = get_uni(uid)
        if uni:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="1️⃣ Об университете", callback_data=f"about:{uid}")],
                [InlineKeyboardButton(text="2️⃣ Программы", callback_data=f"programs:{uid}")],
                [InlineKeyboardButton(text="3️⃣ Приём и стипендии", callback_data=f"admission:{uid}")],
                [InlineKeyboardButton(text="4️⃣ 3D Тур", callback_data=f"tour:{uid}")],
                [InlineKeyboardButton(text="5️⃣ Международное сотрудничество", callback_data=f"intl:{uid}")],
                [InlineKeyboardButton(text="➕ Добавить в сравнение", callback_data=f"add_compare:{uid}")]
            ])
            await callback.message.edit_text(
                f"📘 *{uni['name']}*\nВыберите раздел:",
                reply_markup=kb,
                parse_mode="Markdown"
            )
    await callback.answer()


@dp.callback_query(lambda c: c.data and c.data.startswith("about:"))
async def about(callback: CallbackQuery) -> None:
    if callback.data and callback.message:
        uid = callback.data.split(":")[1]
        uni = get_uni(uid)
        if uni:
            await callback.message.edit_text(
                f"🏛 *О вузе*\n\n{uni['about']}",
                parse_mode="Markdown",
                reply_markup=uni_back(uid)
            )
    await callback.answer()


@dp.callback_query(lambda c: c.data and c.data.startswith("programs:"))
async def programs(callback: CallbackQuery) -> None:
    if callback.data and callback.message:
        uid = callback.data.split(":")[1]
        uni = get_uni(uid)
        if uni:
            await callback.message.edit_text(
                f"🎓 *Программы*\n\n{uni['programs']}",
                parse_mode="Markdown",
                reply_markup=uni_back(uid)
            )
    await callback.answer()


@dp.callback_query(lambda c: c.data and c.data.startswith("admission:"))
async def admission(callback: CallbackQuery) -> None:
    if callback.data and callback.message:
        uid = callback.data.split(":")[1]
        uni = get_uni(uid)
        if uni:
            await callback.message.edit_text(
                f"📥 *Приём*\n\n{uni['admission']}",
                parse_mode="Markdown",
                reply_markup=uni_back(uid)
            )
    await callback.answer()


@dp.callback_query(lambda c: c.data and c.data.startswith("tour:"))
async def tour(callback: CallbackQuery) -> None:
    if callback.data and callback.message:
        uid = callback.data.split(":")[1]
        uni = get_uni(uid)
        if uni:
            await callback.message.edit_text(
                f"🧭 3D тур:\n{uni['tour']}",
                reply_markup=uni_back(uid)
            )
    await callback.answer()


@dp.callback_query(lambda c: c.data and c.data.startswith("intl:"))
async def intl(callback: CallbackQuery) -> None:
    if callback.data and callback.message:
        uid = callback.data.split(":")[1]
        uni = get_uni(uid)
        if uni:
            await callback.message.edit_text(
                f"🌍 *Международное сотрудничество*\n\n{uni['international']}",
                parse_mode="Markdown",
                reply_markup=uni_back(uid)
            )
    await callback.answer()


@dp.callback_query(lambda c: c.data and c.data.startswith("add_compare:"))
async def add_compare(callback: CallbackQuery) -> None:
    if callback.data:
        user_id = callback.from_user.id
        uid = callback.data.split(":")[1]
        user_compare.setdefault(user_id, set()).add(uid)
    await callback.answer("Добавлено!")


async def main() -> None:
    print("🚀 Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
