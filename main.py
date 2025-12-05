import asyncio
import os
from aiogram import Bot, Dispatcher
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Токен бота не найден! Добавь BOT_TOKEN в секреты.")

UNIVERSITIES = [
    {
        "id": "kbtu",
        "name": "КБТУ",
        "city": "Алматы",
        "specialties": ["IT", "Нефтегаз"],
        "min_score": 100,
        "about": "Казахстанско-Британский технический университет — ведущий тех. вуз.",
        "programs": "IT, Нефтегаз, Физика, Экономика, Менеджмент.",
        "admission": "Мин. проходной балл: 100\nЕсть гранты, скидки, конкурсы.",
        "international": "Партнёры: Великобритания, Турция, ЕС. Программы обмена.",
        "tour": "https://example.com/kbtu-tour"
    },
    {
        "id": "kaznu",
        "name": "КазНУ аль-Фараби",
        "city": "Алматы",
        "specialties": ["IT", "Физика", "Биология"],
        "min_score": 95,
        "about": "Национальный университет №1 в Казахстане.",
        "programs": "80+ образовательных направлений.",
        "admission": "Мин. проходной балл: 95\nГосударственные гранты.",
        "international": "Партнёрства с Германией, Кореей, США.",
        "tour": "https://example.com/kaznu-tour"
    },
    {
        "id": "sdu",
        "name": "СДУ",
        "city": "Алматы",
        "specialties": ["IT", "Педагогика"],
        "min_score": 90,
        "about": "Современный частный университет.",
        "programs": "IT, Педагогика, Гуманитарные направления.",
        "admission": "Мин. проходной балл: 90\nСкидки до 50%.",
        "international": "Партнёры: Турция и ЕС.",
        "tour": "https://example.com/sdu-tour"
    }
]

user_compare: dict[int, set[str]] = {}

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔎 Найти ВУЗ", callback_data="find")],
        [InlineKeyboardButton(text="⚖️ Сравнить ВУЗы", callback_data="compare")],
        [InlineKeyboardButton(text="❓ О проекте", callback_data="about_project")]
    ])


def detail_kb(uid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"uni:{uid}")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])


def get_uni(uid: str) -> dict | None:
    return next((u for u in UNIVERSITIES if u["id"] == uid), None)


def search_universities(city: str | None = None, spec: str | None = None, score: int | None = None) -> list[dict]:
    results = UNIVERSITIES
    if city:
        results = [u for u in results if u["city"] == city]
    if spec:
        results = [u for u in results if spec in u["specialties"]]
    if score:
        results = [u for u in results if u["min_score"] >= score]
    return results


@dp.message(CommandStart())
async def start(message: Message) -> None:
    await message.answer("Добро пожаловать в DataHub — каталог вузов Казахстана!", reply_markup=main_menu_kb())


@dp.callback_query(lambda c: c.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery) -> None:
    if callback.message:
        await callback.message.edit_text("Главное меню:", reply_markup=main_menu_kb())
    await callback.answer()


@dp.callback_query(lambda c: c.data == "about_project")
async def about_project(callback: CallbackQuery) -> None:
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])
    if callback.message:
        await callback.message.edit_text(
            "📘 *О DataHub*\n\n"
            "Это каталог вузов Казахстана с быстрым поиском, "
            "детальным меню университетов и функцией сравнения.",
            reply_markup=kb,
            parse_mode="Markdown"
        )
    await callback.answer()


@dp.callback_query(lambda c: c.data == "find")
async def find(callback: CallbackQuery) -> None:
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Город: Алматы", callback_data="find_city:Алматы")],
        [InlineKeyboardButton(text="Специальность: IT", callback_data="find_spec:IT")],
        [InlineKeyboardButton(text="Мин. балл: 100+", callback_data="find_score:100")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])
    if callback.message:
        await callback.message.edit_text("Выберите критерий поиска:", reply_markup=kb)
    await callback.answer()


async def show_university_list(callback: CallbackQuery, unis: list[dict], title: str) -> None:
    kb = []
    if unis:
        for u in unis:
            kb.append([InlineKeyboardButton(text=u["name"], callback_data=f"uni:{u['id']}")])
    else:
        if callback.message:
            await callback.message.edit_text(
                title + "\n\nНичего не найдено.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Назад", callback_data="find")],
                    [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
                ])
            )
        return

    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="find")])
    kb.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")])

    if callback.message:
        await callback.message.edit_text(title, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))


@dp.callback_query(lambda c: c.data and c.data.startswith("find_city:"))
async def find_city(callback: CallbackQuery) -> None:
    if callback.data:
        city = callback.data.split(":")[1]
        await show_university_list(callback, search_universities(city=city), f"Вузы в городе {city}:")
    await callback.answer()


@dp.callback_query(lambda c: c.data and c.data.startswith("find_spec:"))
async def find_spec(callback: CallbackQuery) -> None:
    if callback.data:
        spec = callback.data.split(":")[1]
        await show_university_list(callback, search_universities(spec=spec), f"Вузы со специальностью {spec}:")
    await callback.answer()


@dp.callback_query(lambda c: c.data and c.data.startswith("find_score:"))
async def find_score(callback: CallbackQuery) -> None:
    if callback.data:
        score = int(callback.data.split(":")[1])
        await show_university_list(callback, search_universities(score=score), f"Вузы с проходным баллом от {score}:")
    await callback.answer()


@dp.callback_query(lambda c: c.data and c.data.startswith("uni:"))
async def uni_menu(callback: CallbackQuery) -> None:
    if callback.data:
        uid = callback.data.split(":")[1]
        uni = get_uni(uid)
        if uni and callback.message:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="1️⃣ Об университете", callback_data=f"about:{uid}")],
                [InlineKeyboardButton(text="2️⃣ Программы", callback_data=f"programs:{uid}")],
                [InlineKeyboardButton(text="3️⃣ Приём и стипендии", callback_data=f"admission:{uid}")],
                [InlineKeyboardButton(text="4️⃣ 3D Тур", callback_data=f"tour:{uid}")],
                [InlineKeyboardButton(text="5️⃣ Междунар. сотрудничество", callback_data=f"intl:{uid}")],
                [InlineKeyboardButton(text="➕ Добавить в сравнение", callback_data=f"add_compare:{uid}")],
                [InlineKeyboardButton(text="🔙 Назад", callback_data="find")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
            ])
            await callback.message.edit_text(
                f"📘 *{uni['name']}*\nВыберите раздел:",
                reply_markup=kb, parse_mode="Markdown"
            )
    await callback.answer()


@dp.callback_query(lambda c: c.data and c.data.startswith("about:"))
async def about(callback: CallbackQuery) -> None:
    if callback.data:
        uid = callback.data.split(":")[1]
        uni = get_uni(uid)
        if uni and callback.message:
            await callback.message.edit_text(
                f"🏛 *О университете*\n\n{uni['about']}",
                parse_mode="Markdown",
                reply_markup=detail_kb(uid)
            )
    await callback.answer()


@dp.callback_query(lambda c: c.data and c.data.startswith("programs:"))
async def programs(callback: CallbackQuery) -> None:
    if callback.data:
        uid = callback.data.split(":")[1]
        uni = get_uni(uid)
        if uni and callback.message:
            await callback.message.edit_text(
                f"🎓 *Программы*\n\n{uni['programs']}",
                parse_mode="Markdown",
                reply_markup=detail_kb(uid)
            )
    await callback.answer()


@dp.callback_query(lambda c: c.data and c.data.startswith("admission:"))
async def admission(callback: CallbackQuery) -> None:
    if callback.data:
        uid = callback.data.split(":")[1]
        uni = get_uni(uid)
        if uni and callback.message:
            await callback.message.edit_text(
                f"📥 *Приём*\n\n{uni['admission']}",
                parse_mode="Markdown",
                reply_markup=detail_kb(uid)
            )
    await callback.answer()


@dp.callback_query(lambda c: c.data and c.data.startswith("tour:"))
async def tour(callback: CallbackQuery) -> None:
    if callback.data:
        uid = callback.data.split(":")[1]
        uni = get_uni(uid)
        if uni and callback.message:
            await callback.message.edit_text(
                f"🧭 3D тур:\n{uni['tour']}",
                reply_markup=detail_kb(uid)
            )
    await callback.answer()


@dp.callback_query(lambda c: c.data and c.data.startswith("intl:"))
async def intl(callback: CallbackQuery) -> None:
    if callback.data:
        uid = callback.data.split(":")[1]
        uni = get_uni(uid)
        if uni and callback.message:
            await callback.message.edit_text(
                f"🌍 *Международное сотрудничество*\n\n{uni['international']}",
                parse_mode="Markdown",
                reply_markup=detail_kb(uid)
            )
    await callback.answer()


@dp.callback_query(lambda c: c.data and c.data.startswith("add_compare:"))
async def add_compare(callback: CallbackQuery) -> None:
    if callback.data:
        uid = callback.data.split(":")[1]
        user_id = callback.from_user.id
        user_compare.setdefault(user_id, set()).add(uid)
    await callback.answer("Добавлено в сравнение!", show_alert=False)


@dp.callback_query(lambda c: c.data == "compare")
async def compare(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    selection = user_compare.get(user_id)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Очистить сравнение", callback_data="clear_compare")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])

    if not selection:
        if callback.message:
            await callback.message.edit_text("⚠️ Вы пока ничего не выбрали для сравнения.", reply_markup=kb)
        await callback.answer()
        return

    text = "⚖️ *Сравнение вузов*\n\n"
    for uid in selection:
        uni = get_uni(uid)
        if uni:
            text += (
                f"🔸 *{uni['name']}*\n"
                f"Город: {uni['city']}\n"
                f"Мин. балл: {uni['min_score']}\n"
                f"Направления: {', '.join(uni['specialties'])}\n\n"
            )

    if callback.message:
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    await callback.answer()


@dp.callback_query(lambda c: c.data == "clear_compare")
async def clear_compare(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    user_compare[user_id] = set()
    if callback.message:
        await callback.message.edit_text("🗑 Сравнение очищено!", reply_markup=main_menu_kb())
    await callback.answer()


async def main() -> None:
    print("🚀 DataHub бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
