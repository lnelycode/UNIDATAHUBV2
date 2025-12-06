import os
import asyncio
import logging
import sqlite3
from math import ceil
from random import choice

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardRemove,
)

# ================== НАСТРОЙКИ ==================

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN:
    raise RuntimeError("Переменная окружения BOT_TOKEN не установлена!")

DB_PATH = os.getenv("DB_PATH", "universities.db")

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ================== ГЛОБАЛЬНЫЕ ДАННЫЕ ==================

universities = []
UNIS_BY_ID = {}
cities = []
specialties = []

user_state = {}      # user_id -> {"filters": {...}, "page": int, "await_score": bool}
compare_list = {}    # user_id -> [ID, ID, ID]

CITIES_PER_PAGE = 8
SPECS_PER_PAGE = 8
UNIS_PER_PAGE = 4   # сколько вузов на странице списка


# ================== РАБОТА С БАЗОЙ ==================

def load_from_sqlite():
    """Загружаем все вузы из SQLite в память."""
    global universities, UNIS_BY_ID, cities, specialties

    if not os.path.exists(DB_PATH):
        raise RuntimeError(f"Файл базы данных {DB_PATH} не найден.")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM universities")
    rows = cur.fetchall()
    conn.close()

    universities.clear()
    UNIS_BY_ID.clear()
    city_set = set()
    spec_set = set()

    for row in rows:
        uni = {
            "ID": row["id"],
            "Name": row["name"],
            "City": row["city"],
            "Specialties": row["specialties"] or "",
            "MinScore": row["min_score"],
            "About": row["about"] or "",
            "Programs": row["programs"] or "",
            "Admission": row["admission"] or "",
            "Tour_3d": row["tour_3d"] or "",
            "International": row["international"] or "",
            "Website": row["website"] or "",
        }
        universities.append(uni)

        uid = (uni["ID"] or "").strip()
        if uid:
            UNIS_BY_ID[uid] = uni

        c = (uni["City"] or "").strip()
        if c:
            city_set.add(c)

        specs_raw = uni["Specialties"] or ""
        for part in specs_raw.split(","):
            part = part.strip()
            if part:
                spec_set.add(part)

    cities[:] = sorted(city_set)
    specialties[:] = sorted(spec_set)

    logging.info(f"Загружено вузов из БД: {len(universities)}")
    logging.info(f"Городов: {len(cities)}, специальностей: {len(specialties)}")


load_from_sqlite()


# ================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==================

def get_state(user_id: int):
    st = user_state.get(user_id)
    if not st:
        st = {
            "filters": {
                "city": None,
                "spec": None,
                "score": None,
            },
            "page": 0,
            "await_score": False,
        }
        user_state[user_id] = st
    return st


def main_reply_keyboard() -> ReplyKeyboardMarkup:
    # Если вы хотите полностью убрать reply-клавиатуру — просто не используйте эту функцию.
    return ReplyKeyboardMarkup(
        resize_keyboard=True,
        keyboard=[
            [KeyboardButton(text="Фильтры")],
            [KeyboardButton(text="⚖ Сравнение"), KeyboardButton(text="🎲 Случайный ВУЗ")],
            [KeyboardButton(text="🔢 Поиск по баллу"), KeyboardButton(text="Помощь")],
            [KeyboardButton(text="Таблица ВУЗов Excel")],
        ],
    )


def main_inline_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📍 Города", callback_data="filter_cities")],
            [InlineKeyboardButton(text="📚 Специальности", callback_data="filter_specs")],
            [InlineKeyboardButton(text="🔎 Показать ВУЗы", callback_data="show_all")],
            [InlineKeyboardButton(text="🧹 Сбросить фильтры", callback_data="reset_filters")],
        ]
    )


def apply_filters(filters: dict):
    """Применяем фильтры к списку университетов."""
    res = universities

    city = filters.get("city")
    if city:
        city_l = city.strip().lower()
        res = [
            u for u in res
            if (u.get("City") or "").strip().lower() == city_l
        ]

    spec = filters.get("spec")
    if spec:
        spec_l = spec.lower()
        res = [
            u for u in res
            if spec_l in (u.get("Specialties") or "").lower()
        ]

    score = filters.get("score")
    if score is not None:
        filtered = []
        for u in res:
            ms_val = u.get("MinScore")
            try:
                ms = int(ms_val) if ms_val is not None else 0
            except ValueError:
                continue
            if ms >= score:
                filtered.append(u)
        filtered.sort(key=lambda x: int(x.get("MinScore") or 0), reverse=True)
        res = filtered

    return res


def describe_filters(filters: dict, total: int) -> str:
    parts = []

    city = filters.get("city")
    spec = filters.get("spec")
    score = filters.get("score")

    if city:
        parts.append(f"🏙 Город: <b>{city}</b>")
    if spec:
        parts.append(f"📚 Направление: <b>{spec}</b>")
    if score is not None:
        parts.append(f"📊 Балл ≥ <b>{score}</b>")

    if not parts:
        title = "🔎 <b>Все ВУЗы Казахстана</b>"
    else:
        title = "🔎 <b>ВУЗы по фильтрам</b>\n" + "\n".join(parts)

    title += f"\n\nНайдено: <b>{total}</b>"
    return title


def format_uni_card_full(uni: dict) -> str:
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
        f"📊 Минимальный балл: {min_score}" if str(min_score) != "" else "",
        f"📚 Направления: {specs}" if specs else "",
        "━━━━━━━━━━━━━━━━━━",
        "ℹ️ <b>Об университете</b>",
        about or "Нет данных.",
        "━━━━━━━━━━━━━━━━━━",
        "🎓 <b>Программы</b>",
        programs or "Нет данных.",
        "━━━━━━━━━━━━━━━━━━",
        "🎖 <b>Приём и стипендии</b>",
        admission or "Нет данных.",
        "━━━━━━━━━━━━━━━━━━",
        "🌍 <b>Международное сотрудничество</b>",
        international or "Нет данных.",
        "━━━━━━━━━━━━━━━━━━",
        f"🔗 <b>Сайт:</b>\n{website}" if website else "🔗 Сайт не указан",
    ]

    res = [l for l in lines if l]
    return "\n".join(res)


def format_uni_short_line(uni: dict) -> str:
    name = uni.get("Name", "Без названия")
    city = uni.get("City", "Не указан")
    specs = uni.get("Specialties", "")
    min_score = uni.get("MinScore", "")

    short_spec = specs.split(",")[0].strip() if specs else ""
    line = f"🎓 <b>{name}</b>\n🏙 {city}"
    if str(min_score) != "":
        line += f" • 📊 {min_score}"
    if short_spec:
        line += f"\n📚 {short_spec}"
    return line


def make_unis_list_text(unis_page, filters, page: int, total_pages: int, total_count: int) -> str:
    header = describe_filters(filters, total_count)
    lines = [
        header,
        "",
        f"Страница {page + 1}/{total_pages}",
        "",
    ]
    for u in unis_page:
        lines.append(format_uni_short_line(u))
        lines.append("")
    return "\n".join(lines)


def make_unis_keyboard(unis_page, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """Компактная клавиатура: одна кнопка = один вуз."""
    rows = []

    for u in unis_page:
        uid = (u.get("ID") or "").strip()
        if not uid:
            continue

        name = u.get("Name", "Без названия")
        if len(name) > 40:
            name = name[:37] + "..."

        btn = InlineKeyboardButton(
            text=f"🎓 {name}",
            callback_data=f"uni:{uid}",
        )
        rows.append([btn])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data="unis_prev"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="➡️ Далее", callback_data="unis_next"))
    if nav_row:
        rows.append(nav_row)

    rows.append(
        [
            InlineKeyboardButton(text="⚖ Сравнить выбранные", callback_data="cmp_show"),
            InlineKeyboardButton(text="🧹 Сбросить фильтры", callback_data="reset_filters"),
        ]
    )

    rows.append([InlineKeyboardButton(text="🏠 Меню", callback_data="menu")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_cities_keyboard(page: int) -> InlineKeyboardMarkup:
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


def make_specs_keyboard(page: int) -> InlineKeyboardMarkup:
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


async def send_unis_list(chat_id: int, user_id: int, page: int = None):
    """Отправить список вузов с учётом фильтров и пагинации."""
    st = get_state(user_id)
    filters = st["filters"]
    if page is None:
        page = st.get("page", 0)
    else:
        st["page"] = page

    all_unis = apply_filters(filters)
    if not all_unis:
        text = describe_filters(filters, 0) + "\n\nНичего не найдено по таким условиям."
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🧹 Сбросить фильтры", callback_data="reset_filters")],
                [InlineKeyboardButton(text="🏠 Меню", callback_data="menu")],
            ]
        )
        # Убираем reply-клавиатуру перед отправкой inline-меню
        await bot.send_message(chat_id, " ", reply_markup=ReplyKeyboardRemove())
        await bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=kb)
        return

    total_pages = max(1, ceil(len(all_unis) / UNIS_PER_PAGE))
    page = max(0, min(page, total_pages - 1))
    st["page"] = page

    start = page * UNIS_PER_PAGE
    end = start + UNIS_PER_PAGE
    unis_page = all_unis[start:end]

    text = make_unis_list_text(unis_page, filters, page, total_pages, len(all_unis))
    kb = make_unis_keyboard(unis_page, page, total_pages)

    # Убираем reply-клавиатуру перед отправкой inline-меню (иначе пользователь увидит обе клавиатуры)
    await bot.send_message(chat_id, " ", reply_markup=ReplyKeyboardRemove())
    await bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=kb)


# ================== ХЕНДЛЕРЫ ==================

@dp.message(CommandStart())
async def cmd_start(message: Message):
    get_state(message.from_user.id)
    # Убираем reply-клавиатуру, чтобы клиент перешёл на inline-интерфейс
    await message.answer("👋 Привет! Это DataHub ВУЗов Казахстана.", reply_markup=ReplyKeyboardRemove())
    await message.answer(
        "Найди ВУЗ по городу, направлению, баллу или сравни несколько между собой.\n\nВыберите фильтр:",
        reply_markup=main_inline_menu(),
        parse_mode="HTML",
    )


@dp.message(F.text == "Фильтры")
async def show_filters(message: Message):
    # Перед показом inline-меню — удаляем reply-клавиатуру на всякий случай
    await message.answer(" ", reply_markup=ReplyKeyboardRemove())
    await message.answer(
        "Выберите фильтр:",
        reply_markup=main_inline_menu(),
    )


@dp.message(F.text == "Помощь")
async def help_message(message: Message):
    await message.answer(
        "ℹ <b>Как пользоваться ботом:</b>\n\n"
        "• «Фильтры» — выбираешь город, специальность, можешь сбросить фильтры.\n"
        "• Фильтры комбинируются: город + направление + минимальный балл.\n"
        "• «⚖ Сравнение» — показывает ВУЗы, добавленные через «➕ В сравнение».\n"
        "• «🎲 Случайный ВУЗ» — случайная рекомендация.\n"
        "• «🔢 Поиск по баллу» — фильтр по минимальному баллу ЕНТ.\n"
        "• «Таблица ВУЗов Excel» — ссылка на полную таблицу ВУЗов в Google Drive.\n\n"
        "Можно также писать название города, ВУЗа или направления (например, «Алматы», «НУ», «IT").",
        parse_mode="HTML",
    )


@dp.message(F.text == "Таблица ВУЗов Excel")
async def excel_link(message: Message):
    await message.answer(
        "📊 Полная таблица ВУЗов Казахстана в формате Excel находится здесь:\n"
        "https://drive.google.com/drive/folders/1fjZvILeJXRLSkiL2zhaz_fcngD7nKkoU",
        parse_mode="HTML",
    )


@dp.message(F.text == "🎲 Случайный ВУЗ")
async def random_uni(message: Message):
    if not universities:
        await message.answer("База ВУЗов пустая.")
        return
    uni = choice(universities)
    text = "🎲 Случайный ВУЗ:\n\n" + format_uni_card_full(uni)
    await message.answer(text, parse_mode="HTML")


@dp.message(F.text == "⚖ Сравнение")
async def compare_button(message: Message):
    user_id = message.from_user.id
    ids = compare_list.get(user_id, [])
    if not ids:
        await message.answer(
            "Список сравнения пуст.\n\n"
            "В списке ВУЗов нажимай «➕ В сравнение» в карточке ВУЗа, чтобы добавить.",
            parse_mode="HTML",
        )
        return
    await send_compare_view(message.chat.id, user_id)


@dp.message(F.text == "🔢 Поиск по баллу")
async def ask_score(message: Message):
    st = get_state(message.from_user.id)
    st["await_score"] = True
    await message.answer(
        "Введи минимальный балл ЕНТ (например, <code>90</code>):",
        parse_mode="HTML",
    )


@dp.callback_query(F.data == "menu")
async def cb_menu(callback: CallbackQuery):
    await callback.answer()
    # удаляем reply-клавиатуру на всякий случай
    await callback.message.answer(" ", reply_markup=ReplyKeyboardRemove())
    await callback.message.answer(
        "Выберите фильтр:",
        reply_markup=main_inline_menu(),
    )


@dp.callback_query(F.data == "reset_filters")
async def cb_reset_filters(callback: CallbackQuery):
    st = get_state(callback.from_user.id)
    st["filters"] = {"city": None, "spec": None, "score": None}
    st["page"] = 0
    await callback.answer("Фильтры сброшены")
    # удаляем reply-клавиатуру и показываем inline-меню
    await callback.message.answer(" ", reply_markup=ReplyKeyboardRemove())
    await callback.message.answer(
        "Фильтры сброшены. Показаны все ВУЗы.",
        reply_markup=main_inline_menu(),
    )


@dp.callback_query(F.data == "show_all")
async def cb_show_all(callback: CallbackQuery):
    await callback.answer()
    st = get_state(callback.from_user.id)
    st["page"] = 0
    await send_unis_list(callback.message.chat.id, callback.from_user.id, page=0)


@dp.callback_query(F.data == "filter_cities")
async def cb_filter_cities(callback: CallbackQuery):
    await callback.answer()
    kb = make_cities_keyboard(page=0)
    # удаляем reply-клавиатуру перед показом inline списка
    await callback.message.answer(" ", reply_markup=ReplyKeyboardRemove())
    await callback.message.answer("📍 Выберите город:", reply_markup=kb)


@dp.callback_query(F.data.startswith("cities:"))
async def cb_cities_page(callback: CallbackQuery):
    data = callback.data or ""
    try:
        page = int(data.split(":")[1])
    except (IndexError, ValueError):
        page = 0
    await callback.answer()
    kb = make_cities_keyboard(page)
    await callback.message.answer("📍 Выберите город:", reply_markup=kb)


@dp.callback_query(F.data.startswith("citysel:"))
async def cb_city_select(callback: CallbackQuery):
    data = callback.data or ""
    try:
        idx = int(data.split(":")[1])
        city = cities[idx]
    except Exception:
        await callback.answer("Ошибка выбора города", show_alert=True)
        return

    st = get_state(callback.from_user.id)
    st["filters"]["city"] = city
    st["page"] = 0

    await callback.answer(f"Фильтр по городу: {city}")
    await send_unis_list(callback.message.chat.id, callback.from_user.id, page=0)


@dp.callback_query(F.data == "filter_specs")
async def cb_filter_specs(callback: CallbackQuery):
    await callback.answer()
    kb = make_specs_keyboard(page=0)
    await callback.message.answer(" ", reply_markup=ReplyKeyboardRemove())
    await callback.message.answer("📚 Выберите специальность:", reply_markup=kb)


@dp.callback_query(F.data.startswith("specs:"))
async def cb_specs_page(callback: CallbackQuery):
    data = callback.data or ""
    try:
        page = int(data.split(":")[1])
    except (IndexError, ValueError):
        page = 0
    await callback.answer()
    kb = make_specs_keyboard(page)
    await callback.message.answer("📚 Выберите специальность:", reply_markup=kb)


@dp.callback_query(F.data.startswith("specsel:"))
async def cb_spec_select(callback: CallbackQuery):
    data = callback.data or ""
    try:
        idx = int(data.split(":")[1])
        spec = specialties[idx]
    except Exception:
        await callback.answer("Ошибка выбора специальности", show_alert=True)
        return

    st = get_state(callback.from_user.id)
    st["filters"]["spec"] = spec
    st["page"] = 0

    await callback.answer(f"Фильтр по специальности: {spec}")
    await send_unis_list(callback.message.chat.id, callback.from_user.id, page=0)


@dp.callback_query(F.data == "unis_prev")
async def cb_unis_prev(callback: CallbackQuery):
    st = get_state(callback.from_user.id)
    new_page = max(0, st.get("page", 0) - 1)
    st["page"] = new_page
    await callback.answer()
    await send_unis_list(callback.message.chat.id, callback.from_user.id, page=new_page)


@dp.callback_query(F.data == "unis_next")
async def cb_unis_next(callback: CallbackQuery):
    st = get_state(callback.from_user.id)
    new_page = st.get("page", 0) + 1
    st["page"] = new_page
    await callback.answer()
    await send_unis_list(callback.message.chat.id, callback.from_user.id, page=new_page)


@dp.callback_query(F.data.startswith("uni:"))
async def cb_uni_card(callback: CallbackQuery):
    data = callback.data or ""
    uid = data.split(":", 1)[1] if ":" in data else ""
    uni = UNIS_BY_ID.get(uid)
    if not uni:
        await callback.answer("Университет не найден", show_alert=True)
        return

    text = format_uni_card_full(uni)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ В сравнение", callback_data=f"cmp_add:{uid}"
                )
            ],
            [InlineKeyboardButton(text="🏠 Меню", callback_data="menu")],
        ]
    )
    await callback.answer()
    await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)


def add_to_compare(user_id: int, uni_id: str):
    ids = compare_list.get(user_id, [])
    if uni_id in ids:
        return ids
    if len(ids) >= 3:
        return ids
    new_ids = ids + [uni_id]
    compare_list[user_id] = new_ids
    return new_ids


async def send_compare_view(chat_id: int, user_id: int):
    ids = compare_list.get(user_id, [])
    if not ids:
        text = (
            "Список сравнения пуст.\n\n"
            "Добавь ВУЗы через кнопку «➕ В сравнение» в карточке ВУЗа."
        )
        await bot.send_message(chat_id, text, reply_markup=main_inline_menu())
        return

    items = []
    for uid in ids[:3]:
        u = UNIS_BY_ID.get(uid)
        if not u:
            continue
        name = u.get("Name", "Без названия")
        city = u.get("City", "Не указан")
        min_score = u.get("MinScore", "")
        specs = u.get("Specialties", "")
        website = u.get("Website", "")
        short_spec = specs.split(",")[0].strip() if specs else ""

        block_lines = [
            f"🎓 <b>{name}</b>",
            f"🏙 {city}",
        ]
        if str(min_score) != "":
            block_lines.append(f"📊 Мин. балл: {min_score}")
        if short_spec:
            block_lines.append(f"📚 Направление: {short_spec}")
        if website:
            block_lines.append(f"🔗 {website}")
        items.append("\n".join(block_lines))

    text = "⚖ <b>Сравнение ВУЗов</b>\n\n" + "\n\n━━━━━━━━━━━━\n\n".join(items)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🧹 Очистить сравнение", callback_data="cmp_clear"
                )
            ],
            [InlineKeyboardButton(text="🏠 Меню", callback_data="menu")],
        ]
    )

    # Убираем reply-клавиатуру перед отправкой inline-меню
    await bot.send_message(chat_id, " ", reply_markup=ReplyKeyboardRemove())
    await bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=kb)


@dp.callback_query(F.data.startswith("cmp_add:"))
async def cb_cmp_add(callback: CallbackQuery):
    user_id = callback.from_user.id
    data = callback.data or ""
    uid = data.split(":", 1)[1] if ":" in data else ""
    if uid not in UNIS_BY_ID:
        await callback.answer("Не удалось добавить в сравнение", show_alert=True)
        return

    ids_before = compare_list.get(user_id, [])
    ids_after = add_to_compare(user_id, uid)

    if len(ids_before) == len(ids_after):
        if len(ids_after) >= 3:
            await callback.answer("В сравнении уже максимум 3 ВУЗа.", show_alert=True)
        else:
            await callback.answer("Этот ВУЗ уже в сравнении.")
    else:
        await callback.answer("Добавлено в сравнение ✅")


@dp.callback_query(F.data == "cmp_show")
async def cb_cmp_show(callback: CallbackQuery):
    await callback.answer()
    await send_compare_view(callback.message.chat.id, callback.from_user.id)


@dp.callback_query(F.data == "cmp_clear")
async def cb_cmp_clear(callback: CallbackQuery):
    user_id = callback.from_user.id
    compare_list[user_id] = []
    await callback.answer("Список сравнения очищен")
    await callback.message.answer(
        "Список сравнения очищен.",
        reply_markup=main_inline_menu(),
    )


@dp.message()
async def text_handler(message: Message):
    user_id = message.from_user.id
    st = get_state(user_id)
    txt = (message.text or "").strip()

    # Ввод балла
    if st.get("await_score"):
        try:
            score = int(txt)
        except ValueError:
            await message.answer("Нужно ввести целое число, например: 95")
            return

        st["filters"]["score"] = score
        st["page"] = 0
        st["await_score"] = False

        await send_unis_list(message.chat.id, user_id, page=0)
        return

    # Поиск по тексту
    q = txt.lower()
    results = []
    for u in universities:
        name = (u.get("Name") or "").lower()
        city = (u.get("City") or "").lower()
        specs = (u.get("Specialties") or "").lower()
        if q in name or q == city or q in specs:
            results.append(u)

    if not results:
        await message.answer(
            f"Ничего не найдено по запросу: <b>{txt}</b>",
            parse_mode="HTML",
        )
        return

    results = results[:5]
    lines = [f"🔎 Результаты по запросу: <b>{txt}</b>", ""]
    for u in results:
        lines.append(format_uni_short_line(u))
        lines.append("")

    await message.answer("\n".join(lines), parse_mode="HTML")


async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    print(f"Бот запущен. Вузов в базе (SQLite): {len(universities)}")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
