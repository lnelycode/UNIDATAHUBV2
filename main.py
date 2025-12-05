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
        "about": "Казахстанско-Британский технический университет — один из лучших технических вузов.",
        "programs": "Сильные программы: IT, Нефтегаз, Экономика, Менеджмент.",
        "admission": "Проходной балл: от 100. Есть гранты и стипендии для лучших студентов.",
        "international": "Партнёры: Великобритания, Турция, ЕС. Программы обмена 1–2 семестра.",
        "tour": "https://example.com/kbtu-tour"
    },
    {
        "id": "kaznu",
        "name": "КазНУ",
        "city": "Алматы",
        "specialties": ["IT", "Физика", "Биология"],
        "min_score": 95,
        "about": "Казахский Национальный Университет имени Аль-Фараби.",
        "programs": "Бакалавриат, магистратура, PhD по 80+ направлениям.",
        "admission": "Проходной балл: от 95. Много грантов и государственных программ.",
        "international": "Обмен: Германия, Юж. Корея, Китай, США.",
        "tour": "https://example.com/kaznu-tour"
    },
    {
        "id": "sdu",
        "name": "СДУ",
        "city": "Алматы",
        "specialties": ["IT", "Педагогика"],
        "min_score": 90,
        "about": "Сулейман Демирель Университет — современный частный вуз.",
        "programs": "IT-программы, педагогика, гуманитарные науки.",
        "admission": "Проходной балл: от 90. Есть скидки и гранты.",
        "international": "Обмен с Турцией и рядом европейских стран.",
        "tour": "https://example.com/sdu-tour"
    }
]

user_compare = {}

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


@dp.message(CommandStart())
async def start(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔎 Найти ВУЗ", callback_data="find")],
        [InlineKeyboardButton(text="⚖️ Сравнить ВУЗы", callback_data="compare")],
        [InlineKeyboardButton(text="❓ О проекте", callback_data="about_project")]
    ])
    await message.answer("Добро пожаловать в DataHub — каталог вузов Казахстана!", reply_markup=kb)


@dp.callback_query(lambda c: c.data == "about_project")
async def about_project(callback: CallbackQuery):
    await callback.message.edit_text(
        "📘 *О проекте DataHub*\n\n"
        "Это интерактивный каталог вузов Казахстана.\n"
        "Здесь вы можете найти университет по критериям, "
        "изучить подробную информацию и сравнить разные вузы.",
        parse_mode="Markdown"
    )


@dp.callback_query(lambda c: c.data == "find")
async def find(callback: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Город: Алматы", callback_data="find_city:Алматы")],
        [InlineKeyboardButton(text="Специальность: IT", callback_data="find_spec:IT")],
        [InlineKeyboardButton(text="Мин. балл: 100+", callback_data="find_score:100")]
    ])
    await callback.message.edit_text("Выберите критерий поиска:", reply_markup=kb)


def search_universities(city=None, spec=None, score=None):
    results = UNIVERSITIES
    if city:
        results = [u for u in results if u["city"] == city]
    if spec:
        results = [u for u in results if spec in u["specialties"]]
    if score:
        results = [u for u in results if u["min_score"] >= score]
    return results


async def show_university_list(callback, unis, title):
    if not unis:
        await callback.message.edit_text(title + "\n\nНичего не найдено.")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=u["name"], callback_data=f"uni:{u['id']}")]
        for u in unis
    ])

    await callback.message.edit_text(title + "\n\nВыберите университет:", reply_markup=kb)


@dp.callback_query(lambda c: c.data.startswith("find_city:"))
async def find_city(callback: CallbackQuery):
    city = callback.data.split(":")[1]
    unis = search_universities(city=city)
    await show_university_list(callback, unis, f"Вузы в городе {city}")


@dp.callback_query(lambda c: c.data.startswith("find_spec:"))
async def find_spec(callback: CallbackQuery):
    spec = callback.data.split(":")[1]
    unis = search_universities(spec=spec)
    await show_university_list(callback, unis, f"Вузы со специальностью {spec}")


@dp.callback_query(lambda c: c.data.startswith("find_score:"))
async def find_score(callback: CallbackQuery):
    score = int(callback.data.split(":")[1])
    unis = search_universities(score=score)
    await show_university_list(callback, unis, f"Вузы с проходным баллом от {score}")


def get_uni(uid):
    for u in UNIVERSITIES:
        if u["id"] == uid:
            return u
    return None


@dp.callback_query(lambda c: c.data.startswith("uni:"))
async def uni_menu(callback: CallbackQuery):
    uid = callback.data.split(":")[1]
    uni = get_uni(uid)

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


@dp.callback_query(lambda c: c.data.startswith("about:"))
async def uni_about(callback: CallbackQuery):
    uid = callback.data.split(":")[1]
    uni = get_uni(uid)
    await callback.message.edit_text(f"🏛 *О университете*\n\n{uni['about']}", parse_mode="Markdown")


@dp.callback_query(lambda c: c.data.startswith("programs:"))
async def uni_programs(callback: CallbackQuery):
    uid = callback.data.split(":")[1]
    uni = get_uni(uid)
    await callback.message.edit_text(f"🎓 *Программы*\n\n{uni['programs']}", parse_mode="Markdown")


@dp.callback_query(lambda c: c.data.startswith("admission:"))
async def uni_admission(callback: CallbackQuery):
    uid = callback.data.split(":")[1]
    uni = get_uni(uid)
    await callback.message.edit_text(f"📥 *Приём*\n\n{uni['admission']}", parse_mode="Markdown")


@dp.callback_query(lambda c: c.data.startswith("tour:"))
async def uni_tour(callback: CallbackQuery):
    uid = callback.data.split(":")[1]
    uni = get_uni(uid)
    await callback.message.edit_text(f"🧭 3D Тур:\n{uni['tour']}")


@dp.callback_query(lambda c: c.data.startswith("intl:"))
async def uni_intl(callback: CallbackQuery):
    uid = callback.data.split(":")[1]
    uni = get_uni(uid)
    await callback.message.edit_text(f"🌍 *Международное сотрудничество*\n\n{uni['international']}", parse_mode="Markdown")


@dp.callback_query(lambda c: c.data.startswith("add_compare:"))
async def add_compare(callback: CallbackQuery):
    uid = callback.data.split(":")[1]
    user_id = callback.from_user.id

    user_compare.setdefault(user_id, set()).add(uid)

    await callback.answer("Добавлено в сравнение!", show_alert=True)


@dp.callback_query(lambda c: c.data == "compare")
async def compare(callback: CallbackQuery):
    user_id = callback.from_user.id
    unis = user_compare.get(user_id)

    if not unis:
        await callback.message.edit_text("❗ Вы ещё не выбрали ни одного университета для сравнения.")
        return

    text = "⚖️ *Сравнение университетов*\n\n"
    for uid in unis:
        uni = get_uni(uid)
        text += f"🔸 *{uni['name']}*\n"
        text += f"Город: {uni['city']}\n"
        text += f"Минимальный балл: {uni['min_score']}\n"
        text += f"Направления: {', '.join(uni['specialties'])}\n\n"

    await callback.message.edit_text(text, parse_mode="Markdown")


async def main():
    print("🚀 DataHub бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
