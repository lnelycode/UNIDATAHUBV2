import asyncio
import os
import logging
import csv
from math import ceil
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

# ===== НАСТРОЙКИ =====

BOT_TOKEN = os.getenv("BOT_TOKEN")
CSV_PATH = "universities_kz_filled.csv"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ===== ГЛОБАЛЬНЫЕ ДАННЫЕ =====

universities = []      # список словарей с вузами
UNIS_BY_ID = {}        # ID -> вуз
cities = []            # список городов
specialties = []       # список специальностей
user_state = {}        # user_id -> {mode, value, page}

CITIES_PER_PAGE = 8
SPECS_PER_PAGE = 8
UNIS_PER_PAGE = 10


# ===== ЗАГРУЗКА CSV =====

def load_csv():
    global universities, UNIS_BY_ID, cities, specialties

    with open(CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        universities = list(reader)

    UNIS_BY_ID = {}
    for u in universities:
        uid = (u.get("ID") or "").strip()
        if uid:
            UNIS_BY_ID[uid] = u

    city_set = set()
    spec_set = set()

    for u in universities:
        c = (u.get("City") or "").strip()
        if c:
            city_set.add(c)

        specs_raw = u.get("Specialties") or ""
        for part in specs_raw.split(","):
            part = part.strip()
            if part:
                spec_set.add(part)

    cities[:] = sorted(city_set)
    specialties[:] = sorted(spec_set)

    logging.info(f"Загружено вузов: {len(universities)}")
    logging.info(f"Городов: {len(cities)}, специальностей: {len(specialties)}")


load_csv()


# ===== КЛАВИАТУРЫ =====

def main_reply_keyboard():
    return ReplyKeyboardMarkup(
        resize_keyboard=True,
        keyboard=[
            [KeyboardButton(text="Фильтры")],
            [KeyboardButton(text="Помощь")],
        ],
    )


def main_inline_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📍 Города", callback_data="filter_cities")],
            [InlineKeyboardButton(text="📚 Специальности", callback_data="filter_specs")],
            [InlineKeyboardButton(text="🔎 Все ВУЗы", callback_data="show_all:0")],
        ]
    )


# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====

def format_uni_card(uni):
    name = uni.get("Name", "Без названия")
    city = uni.get("City", "Не указан")
    specs = uni.get("Specialties", "")
    min_score = uni.get("MinScore", "")
    about = uni.get("About", "")
    programs = uni.get("Programs", "")
    admission = uni.get("Admission", "")
    international = uni.get("International", "")
    website = uni.get("Website", "")

    lines = [
        f"🎓 <b>{name}</b>",
        "",
        f"🏙 Город: <b>{city}</b>",
        f"📚 Направления: {specs}" if specs else "",
        f"📊 Минимальный балл: {min_score}" if str(min_score) != "" else "",
        "━━━━━━━━━━━━━━━━━━",
        "ℹ️ <b>Описание:</b>",
        about or "Нет данных.",
        "━━━━━━━━━━━━━━━━━━",
        "🎓 <b>Программы:</b>",
        programs or "Нет данных.",
        "━━━━━━━━━━━━━━━━━━",
        "🎖 <b>Поступление и стипендии:</b>",
        admission or "Нет данных.",
        "━━━━━━━━━━━━━━━━━━",
        "🌍 <b>Международное сотрудничество:</b>",
        international or "Нет данных.",
        "━━━━━━━━━━━━━━━━━━",
        f"🔗 <b>Сайт:</b>\n{website}" if website else "🔗 Сайт не указан",
    ]

    result_lines = [line for line in lines if line is not None and line != ""]
    return "\n".join(result_lines)


def filter_unis(mode, value):
    if mode == "all":
        return list(universities)

    if mode == "city" and value:
        return [
            u for u in universities
            if (u.get("City") or "").strip().lower() == value.lower()
        ]

    if mode == "spec" and value:
        value_low = value.lower()
        result = []
        for u in universities:
            specs_raw = (u.get("Specialties") or "").lower()
            if value_low in specs_raw:
                result.append(u)
        return result

    return []


def make_unis_list_text(unis_page, header, page, total_pages):
    lines = [
        header,
        f"Страница {page + 1}/{total_pages}",
        "",
    ]
    for u in unis_page:
        name = u.get("Name", "Без названия")
        city = u.get("City", "Не указан")
        specs = u.get("Specialties", "")
        min_score = u.get("MinScore", "")
        part = (
            f"🎓 <b>{name}</b>\n"
            f"🏙 {city} • 📊 {min_score} • {specs}"
        )
        lines.append(part)
        lines.append("")
    return "\n".join(lines)


def make_unis_keyboard(unis_page, mode, value, page, total_pages):
    rows = []

    # кнопки вузов
    for u in unis_page:
        uid = (u.get("ID") or "").strip()
        if not uid:
            continue
        text = u.get("Name", "Без названия")
        rows.append([InlineKeyboardButton(text=text, callback_data=f"uni:{uid}")])

    # пагинация
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data="unis_prev"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="➡️ Далее", callback_data="unis_next"))
    if nav_row:
        rows.append(nav_row)

    # внизу — кнопка меню
    rows.append([InlineKeyboardButton(text="🏠 Меню", callback_data="menu")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_cities_keyboard(page):
    total_pages = max(1, ceil(len(cities) / CITIES_PER_PAGE))
    page = max(0, min(page, total_pages - 1))
    start = page * CITIES_PER_PAGE
    end = start + CITIES_PER_PAGE
    items = cities[start:end]

    rows = [
        [InlineKeyboardButton(text=c, callback_data=f"citysel:{cities.index(c)}")]
        for c in items
    ]

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"cities:{page - 1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="➡️ Далее", callback_data=f"cities:{page + 1}"))
    if nav_row:
        rows.append(nav_row)

    rows.append([InlineKeyboardButton(text="🏠 Меню", callback_data="menu")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_specs_keyboard(page):
    total_pages = max(1, ceil(len(specialties) / SPECS_PER_PAGE))
    page = max(0, min(page, total_pages - 1))
    start = page * SPECS_PER_PAGE
    end = start + SPECS_PER_PAGE
    items = specialties[start:end]

    rows = [
        [InlineKeyboardButton(text=s, callback_data=f"specsel:{specialties.index(s)}")]
        for s in items
    ]

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"specs:{page - 1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="➡️ Далее", callback_data=f"specs:{page + 1}"))
    if nav_row:
        rows.append(nav_row)

    rows.append([InlineKeyboardButton(text="🏠 Меню", callback_data="menu")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


async def show_unis_list(callback, mode, value, page):
    user_id = callback.from_user.id
    all_unis = filter_unis(mode, value)
    if not all_unis:
        if callback.message:
            await callback.message.edit_text(
                "Ничего не найдено по выбранному фильтру.",
                reply_markup=main_inline_menu(),
            )
        await callback.answer()
        return

    total_pages = max(1, ceil(len(all_unis) / UNIS_PER_PAGE))
    page = max(0, min(page, total_pages - 1))

    start = page * UNIS_PER_PAGE
    end = start + UNIS_PER_PAGE
    unis_page = all_unis[start:end]

    user_state[user_id] = {
        "mode": mode,
        "value": value,
        "page": page,
    }

    if mode == "all":
        header = "🔎 <b>Все ВУЗы Казахстана</b>"
    elif mode == "city":
        header = f"🏙 <b>ВУЗы в городе: {value}</b>"
    elif mode == "spec":
        header = f"📚 <b>ВУЗы по направлению: {value}</b>"
    else:
        header = "<b>ВУЗы</b>"

    text = make_unis_list_text(unis_page, header, page, total_pages)
    kb = make_unis_keyboard(unis_page, mode, value, page, total_pages)

    if callback.message:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()


# ===== ХЕНДЛЕРЫ СООБЩЕНИЙ =====

@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "👋 Привет! Это DataHub ВУЗов Казахстана.\n\n"
        "Используй кнопки ниже или выбери фильтр.",
        reply_markup=main_reply_keyboard(),
        parse_mode="HTML",
    )
    await message.answer(
        "Выберите фильтр:",
        reply_markup=main_inline_menu(),
    )


@dp.message(F.text == "Фильтры")
async def show_filters(message: Message):
    await message.answer(
        "Выберите фильтр:",
        reply_markup=main_inline_menu(),
    )


@dp.message(F.text == "Помощь")
async def help_message(message: Message):
    await message.answer(
        "ℹ <b>Как пользоваться ботом:</b>\n\n"
        "1. Нажмите «Фильтры».\n"
        "2. Выберите:\n"
        "   • 📍 Города — список городов\n"
        "   • 📚 Специальности — поиск по направлению\n"
        "   • 🔎 Все ВУЗы — полный список\n\n"
        "Также можно просто ввести текст (например «Алматы» или «IT»), и я попробую найти вузы.",
        parse_mode="HTML",
    )


# ===== CALLBACK'И МЕНЮ =====

@dp.callback_query(F.data == "menu")
async def cb_menu(callback: CallbackQuery):
    if callback.message:
        await callback.message.edit_text(
            "Выберите фильтр:",
            reply_markup=main_inline_menu(),
        )
    await callback.answer()


# --- Города ---

@dp.callback_query(F.data == "filter_cities")
async def cb_filter_cities(callback: CallbackQuery):
    if callback.message:
        kb = make_cities_keyboard(page=0)
        await callback.message.edit_text(
            "📍 Выберите город:",
            reply_markup=kb,
        )
    await callback.answer()


@dp.callback_query(F.data.startswith("cities:"))
async def cb_cities_page(callback: CallbackQuery):
    data = callback.data or ""
    try:
        page = int(data.split(":")[1])
    except (IndexError, ValueError):
        page = 0
    if callback.message:
        kb = make_cities_keyboard(page)
        await callback.message.edit_text(
            "📍 Выберите город:",
            reply_markup=kb,
        )
    await callback.answer()


@dp.callback_query(F.data.startswith("citysel:"))
async def cb_city_select(callback: CallbackQuery):
    data = callback.data or ""
    try:
        idx = int(data.split(":")[1])
        city = cities[idx]
    except Exception:
        await callback.answer("Ошибка выбора города", show_alert=True)
        return

    await show_unis_list(callback, mode="city", value=city, page=0)


# --- Специальности ---

@dp.callback_query(F.data == "filter_specs")
async def cb_filter_specs(callback: CallbackQuery):
    if callback.message:
        kb = make_specs_keyboard(page=0)
        await callback.message.edit_text(
            "📚 Выберите специальность:",
            reply_markup=kb,
        )
    await callback.answer()


@dp.callback_query(F.data.startswith("specs:"))
async def cb_specs_page(callback: CallbackQuery):
    data = callback.data or ""
    try:
        page = int(data.split(":")[1])
    except (IndexError, ValueError):
        page = 0
    if callback.message:
        kb = make_specs_keyboard(page)
        await callback.message.edit_text(
            "📚 Выберите специальность:",
            reply_markup=kb,
        )
    await callback.answer()


@dp.callback_query(F.data.startswith("specsel:"))
async def cb_spec_select(callback: CallbackQuery):
    data = callback.data or ""
    try:
        idx = int(data.split(":")[1])
        spec = specialties[idx]
    except Exception:
        await callback.answer("Ошибка выбора специальности", show_alert=True)
        return

    await show_unis_list(callback, mode="spec", value=spec, page=0)


# --- Все ВУЗы ---

@dp.callback_query(F.data.startswith("show_all:"))
async def cb_show_all(callback: CallbackQuery):
    data = callback.data or ""
    try:
        page = int(data.split(":")[1])
    except (IndexError, ValueError):
        page = 0
    await show_unis_list(callback, mode="all", value=None, page=page)


@dp.callback_query(F.data == "unis_prev")
async def cb_unis_prev(callback: CallbackQuery):
    user_id = callback.from_user.id
    st = user_state.get(user_id)
    if not st:
        await callback.answer()
        return
    new_page = max(0, st["page"] - 1)
    await show_unis_list(callback, st["mode"], st["value"], new_page)


@dp.callback_query(F.data == "unis_next")
async def cb_unis_next(callback: CallbackQuery):
    user_id = callback.from_user.id
    st = user_state.get(user_id)
    if not st:
        await callback.answer()
        return
    new_page = st["page"] + 1
    await show_unis_list(callback, st["mode"], st["value"], new_page)


# --- Карточка ВУЗа ---

@dp.callback_query(F.data.startswith("uni:"))
async def cb_uni_card(callback: CallbackQuery):
    data = callback.data or ""
    uid = data.split(":", 1)[1] if ":" in data else ""
    uni = UNIS_BY_ID.get(uid)
    if not uni:
        await callback.answer("Университет не найден", show_alert=True)
        return

    text = format_uni_card(uni)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="backtolist")],
            [InlineKeyboardButton(text="🏠 Меню", callback_data="menu")],
        ]
    )
    if callback.message:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data == "backtolist")
async def cb_backtolist(callback: CallbackQuery):
    user_id = callback.from_user.id
    st = user_state.get(user_id)
    if not st:
        if callback.message:
            await callback.message.edit_text(
                "Выберите фильтр:",
                reply_markup=main_inline_menu(),
            )
        await callback.answer()
        return

    await show_unis_list(callback, st["mode"], st["value"], st["page"])


# ===== ТЕКСТОВЫЙ ПОИСК =====

@dp.message()
async def text_search(message: Message):
    query = (message.text or "").strip()
    if not query:
        return

    q = query.lower()
    results = []
    for u in universities:
        name = (u.get("Name") or "").lower()
        city = (u.get("City") or "").lower()
        specs = (u.get("Specialties") or "").lower()
        if q in name or q == city or q in specs:
            results.append(u)

    if not results:
        await message.answer(
            f"Ничего не найдено по запросу: <b>{query}</b>",
            parse_mode="HTML",
        )
        return

    results = results[:5]
    lines = [f"🔎 Результаты по запросу: <b>{query}</b>", ""]
    for u in results:
        name = u.get("Name", "Без названия")
        city = u.get("City", "Не указан")
        specs = u.get("Specialties", "")
        min_score = u.get("MinScore", "")
        lines.append(
            f"🎓 <b>{name}</b>\n"
            f"🏙 {city} • 📊 {min_score} • {specs}\n"
        )

    await message.answer("\n".join(lines), parse_mode="HTML")


# ===== ЗАПУСК БОТА =====

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    print(f"Бот запущен. Вузов в базе: {len(universities)}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())