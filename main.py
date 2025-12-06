
# Исправлённый main.py с добавленной кнопкой "📄 Полный список ВУЗов"
# - Кнопка добавлена в главное меню, в карточку университета и в просмотр сравнения.
# - Кнопка открывает ссылку на Google Drive с полной таблицей (url).
#
# Запустите: python main.py

import os
import asyncio
import logging
import sqlite3
from math import ceil
from random import choice
import html

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.exceptions import TelegramBadRequest

# ================== НАСТРОЙКИ ==================
BOT_TOKEN = os.getenv("BOT_TOKEN", "ВАШ_ТОКЕН_ЗДЕСЬ")
DB_PATH = os.getenv("DB_PATH", "universities.db")

# Ссылка на полный список ВУЗов (Google Drive)
FULL_UNIS_URL = "https://drive.google.com/drive/folders/1fjZvILeJXRLSkiL2zhaz_fcngD7nKkoU"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if not BOT_TOKEN or BOT_TOKEN == "ВАШ_ТОКЕН_ЗДЕСЬ":
    logger.warning("⚠️ ПРЕДУПРЕЖДЕНИЕ: Введите реальный токен бота в переменную BOT_TOKEN!")

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
UNIS_PER_PAGE = 5   # Количество ВУЗов на странице (кнопок)

# ================== РАБОТА С БАЗОЙ ==================

def load_from_sqlite():
    """Загружаем все вузы из SQLite в память."""
    global universities, UNIS_BY_ID, cities, specialties

    if not os.path.exists(DB_PATH):
        logging.error(f"Файл базы данных {DB_PATH} не найден. Проверьте путь.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM universities")
        rows = cur.fetchall()
    except sqlite3.OperationalError:
        logging.error("Таблица universities не найдена в БД. Убедитесь, что таблица существует.")
        rows = []
    finally:
        conn.close()

    universities.clear()
    UNIS_BY_ID.clear()
    city_set = set()
    spec_set = set()

    for row in rows:
        uni = {
            "ID": str(row["id"]),
            "Name": row["name"] or "",
            "City": row["city"] or "",
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

        uid = uni["ID"].strip()
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

    cities[:] = sorted(list(city_set))
    specialties[:] = sorted(list(spec_set))

    logging.info(f"Загружено вузов из БД: {len(universities)}")


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


def main_inline_menu() -> InlineKeyboardMarkup:
    """Генерирует главное инлайн-меню с добавленной кнопкой полного списка."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📍 Города", callback_data="filter_cities")],
            [InlineKeyboardButton(text="📚 Специальности", callback_data="filter_specs")],
            [InlineKeyboardButton(text="🔎 Показать ВУЗы", callback_data="show_all")],
            [InlineKeyboardButton(text="🧹 Сбросить фильтры", callback_data="reset_filters")],
            # Кнопка внешней ссылки на полный список
            [InlineKeyboardButton(text="📄 Полный список ВУЗов", url=FULL_UNIS_URL)],
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
            except (ValueError, TypeError):
                continue
            if ms >= score:
                filtered.append(u)
        filtered.sort(key=lambda x: int(x.get("MinScore") or 0), reverse=True)
        res = filtered

    return res


def describe_filters(filters: dict, total: int) -> str:
    """Форматирует описание текущих фильтров."""
    parts = []

    city = filters.get("city")
    spec = filters.get("spec")
    score = filters.get("score")

    if city:
        parts.append(f"🏙 Город: <b>{html.escape(city)}</b>")
    if spec:
        parts.append(f"📚 Направление: <b>{html.escape(spec)}</b>")
    if score is not None:
        parts.append(f"📊 Балл ≥ <b>{int(score)}</b>")

    if not parts:
        title = "🔎 <b>Все ВУЗы Казахстана</b>"
    else:
        title = "🔎 <b>Результаты поиска</b>\n" + "\n".join(parts)

    title += f"\n\nНайдено ВУЗов: <b>{total}</b>"
    return title


def format_uni_card_full(uni: dict) -> str:
    """Полное форматирование карточки ВУЗа (HTML-экранирование содержимого)."""
    name = html.escape(uni.get("Name", "Без названия"))
    city = html.escape(uni.get("City", "Не указан"))
    specs = html.escape(uni.get("Specialties", ""))
    min_score = uni.get("MinScore", "")
    about = html.escape(uni.get("About", ""))
    programs = html.escape(uni.get("Programs", ""))
    admission = html.escape(uni.get("Admission", ""))
    international = html.escape(uni.get("International", ""))
    website = html.escape(uni.get("Website", ""))

    lines = [
        f"🎓 <b>{name}</b>",
        "",
        f"🏙 Город: <b>{city}</b>",
        f"📊 Минимальный балл: {html.escape(str(min_score))}" if str(min_score) != "" else "",
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


# --- ФУНКЦИИ ОТОБРАЖЕНИЯ СПИСКА ---

def make_unis_list_text(filters: dict, page: int, total_pages: int, total_count: int) -> str:
    """Текст сообщения над списком кнопок (ТОЛЬКО ЗАГОЛОВОК)."""
    header = describe_filters(filters, total_count)
    text = (
        f"{header}\n\n"
        f"📄 Страница {page + 1} из {total_pages}\n"
        f"👇 <b>Выберите университет:</b>"
    )
    return text


def make_unis_keyboard(unis_page, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """Генерация клавиатуры со списком ВУЗов в формате: каждая строка — 2 кнопки (Открыть / В сравнение).
       Навигация и сервисные кнопки — отдельные широкие строки (как на скриншоте)."""
    rows = []

    # 1. Для каждого ВУЗа: две кнопки в одной строке
    for u in unis_page:
        uid = (u.get("ID") or "").strip()
        if not uid:
            continue

        # Кнопка открыть (отправляет uni_open:<uid>:<page>)
        btn_open = InlineKeyboardButton(
            text="🔍 Открыть",
            callback_data=f"uni_open:{uid}:{page}"
        )
        # Кнопка добавить в сравнение
        btn_cmp = InlineKeyboardButton(
            text="➕ В сравнение",
            callback_data=f"cmp_add:{uid}"
        )
        rows.append([btn_open, btn_cmp])

    # 2. Навигация: назад / далее по одной строке (широкие)
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data="unis_prev"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="➡️ Далее", callback_data="unis_next"))
    if nav_row:
        rows.append(nav_row)

    # 3. Действия (широкие кнопки на отдельных строках)
    rows.append([InlineKeyboardButton(text="⚖ Сравнить выбр", callback_data="cmp_show")])
    rows.append([InlineKeyboardButton(text="🧹 Сбросить фильт", callback_data="reset_filters")])

    # 4. Ссылка на полный список ВУЗов (широкая кнопка)
    rows.append([InlineKeyboardButton(text="📄 Полный список ВУЗов", url=FULL_UNIS_URL)])

    # 5. Главное меню
    rows.append([InlineKeyboardButton(text="🏠 Меню", callback_data="menu")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


# ================== ОТПРАВКА СПИСКА (УНИВЕРСАЛЬНАЯ ФУНКЦИЯ) ==================

async def send_unis_list(message_or_call, user_id: int, page: int = None):
    """Отправляет/обновляет список вузов."""
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
                [InlineKeyboardButton(text="📄 Полный список ВУЗов", url=FULL_UNIS_URL)],
                [InlineKeyboardButton(text="🏠 Меню", callback_data="menu")],
            ]
        )
        
        if isinstance(message_or_call, CallbackQuery):
            try:
                await message_or_call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
            except TelegramBadRequest as e:
                logger.exception("Не удалось edit_text (empty results). Отправляю новое сообщение.")
                await bot.send_message(message_or_call.message.chat.id, text, parse_mode="HTML", reply_markup=kb)
        else:
            await message_or_call.answer(text, parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
        return

    total_pages = max(1, ceil(len(all_unis) / UNIS_PER_PAGE))
    page = max(0, min(page, total_pages - 1))
    st["page"] = page

    start = page * UNIS_PER_PAGE
    end = start + UNIS_PER_PAGE
    unis_page = all_unis[start:end]

    text = make_unis_list_text(filters, page, total_pages, len(all_unis))
    kb = make_unis_keyboard(unis_page, page, total_pages)

    if isinstance(message_or_call, CallbackQuery):
        # При листании/возврате назад редактируем сообщение
        try:
            await message_or_call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except TelegramBadRequest:
            # fallback: отправить новое сообщение
            logger.exception("edit_text failed in send_unis_list; sending new message.")
            await bot.send_message(message_or_call.message.chat.id, text, parse_mode="HTML", reply_markup=kb)
    else:
        # При поиске отправляем новое сообщение и удаляем Reply-клавиатуру в одном сообщении
        await message_or_call.answer(text, parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
        await message_or_call.answer(text, parse_mode="HTML", reply_markup=kb)


# ================== ХЕНДЛЕРЫ ==================

@dp.message(CommandStart())
async def cmd_start(message: Message):
    get_state(message.from_user.id)
    # Удаляем Reply-клавиатуру и показываем инлайн-меню
    await message.answer("👋 Привет! Это DataHub ВУЗов Казахстана.", reply_markup=ReplyKeyboardRemove())
    await message.answer(
        "Найди ВУЗ по городу, направлению, баллу или сравни несколько между собой.\n\nВыберите фильтр:",
        reply_markup=main_inline_menu(),
        parse_mode="HTML",
    )


@dp.message(F.text == "Фильтры")
async def show_filters(message: Message):
    await message.answer("Выберите фильтр:", reply_markup=main_inline_menu())


@dp.message(F.text == "Помощь")
async def help_message(message: Message):
    await message.answer(
        "ℹ <b>Как пользоваться ботом:</b>\n\n"
        "• Фильтры — выбираешь город, специальность.\n"
        "• Сравнение — сравни до 3-х ВУЗов.\n"
        "• Случайный ВУЗ — рекомендация наугад.\n"
        "• Поиск по баллу — фильтр по ЕНТ.\n\n"
        "Можно также писать название города или ВУЗа в чат. Для навигации используйте 🏠 Меню.",
        parse_mode="HTML",
    )


@dp.message(F.text == "Таблица ВУЗов Excel")
async def excel_link(message: Message):
    await message.answer(
        "📊 Полная таблица ВУЗов Казахстана в Excel:\n" + FULL_UNIS_URL,
        parse_mode="HTML",
    )


@dp.message(F.text == "🎲 Случайный ВУЗ")
async def random_uni(message: Message):
    if not universities:
        await message.answer("База ВУЗов пустая.")
        return
    uni = choice(universities)
    text = "🎲 <b>Случайный ВУЗ:</b>\n\n" + format_uni_card_full(uni)
    
    uid = uni["ID"]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ В сравнение", callback_data=f"cmp_add:{uid}")],
        [InlineKeyboardButton(text="📄 Полный список ВУЗов", url=FULL_UNIS_URL)],
        [InlineKeyboardButton(text="🏠 Меню", callback_data="menu")]
    ])
    
    await message.answer(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)


@dp.message(F.text == "⚖ Сравнение")
async def compare_button(message: Message):
    await send_compare_view(message.chat.id, message.from_user.id)


@dp.message(F.text == "🔢 Поиск по баллу")
async def ask_score(message: Message):
    st = get_state(message.from_user.id)
    st["await_score"] = True
    await message.answer(
        "Введи минимальный балл ЕНТ (например, <code>90</code>):",
        parse_mode="HTML",
    )


# --- CALLBACKS ГЛАВНОГО МЕНЮ ---

@dp.callback_query(F.data == "menu")
async def cb_menu(callback: CallbackQuery):
    await callback.answer()
    try:
        await callback.message.edit_text(
            "🏠 <b>Главное меню</b>\nВыберите действие:",
            reply_markup=main_inline_menu(),
            parse_mode="HTML"
        )
    except TelegramBadRequest:
        await callback.message.reply("🏠 <b>Главное меню</b>\nВыберите действие:", reply_markup=main_inline_menu(), parse_mode="HTML")


@dp.callback_query(F.data == "reset_filters")
async def cb_reset_filters(callback: CallbackQuery):
    st = get_state(callback.from_user.id)
    st["filters"] = {"city": None, "spec": None, "score": None}
    st["page"] = 0
    await callback.answer("Фильтры сброшены")
    try:
        await callback.message.edit_text(
            "✅ Фильтры сброшены. Выберите действие:",
            reply_markup=main_inline_menu(),
        )
    except TelegramBadRequest:
        await callback.message.reply("✅ Фильтры сброшены. Выберите действие:", reply_markup=main_inline_menu())


@dp.callback_query(F.data == "show_all")
async def cb_show_all(callback: CallbackQuery):
    await callback.answer()
    st = get_state(callback.from_user.id)
    st["page"] = 0
    await send_unis_list(callback, callback.from_user.id, page=0)


# --- CALLBACKS ГОРОДОВ ---

def make_cities_keyboard(page: int) -> InlineKeyboardMarkup:
    total_pages = max(1, ceil(len(cities) / CITIES_PER_PAGE))
    page = max(0, min(page, total_pages - 1))
    start = page * CITIES_PER_PAGE
    end = start + CITIES_PER_PAGE
    items = cities[start:end]

    rows = [
        [InlineKeyboardButton(text=c, callback_data=f"citysel:{c}")]
        for c in items
    ]

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"cities:{page - 1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"cities:{page + 1}"))
    if nav_row:
        rows.append(nav_row)

    rows.append([InlineKeyboardButton(text="🏠 Назад в меню", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@dp.callback_query(F.data == "filter_cities")
async def cb_filter_cities(callback: CallbackQuery):
    await callback.answer()
    kb = make_cities_keyboard(page=0)
    try:
        await callback.message.edit_text("📍 Выберите город:", reply_markup=kb)
    except TelegramBadRequest:
        await callback.message.reply("📍 Выберите город:", reply_markup=kb)


@dp.callback_query(F.data.startswith("cities:"))
async def cb_cities_page(callback: CallbackQuery):
    data = callback.data or ""
    try:
        page = int(data.split(":")[1])
    except (IndexError, ValueError):
        page = 0
    await callback.answer()
    kb = make_cities_keyboard(page)
    try:
        await callback.message.edit_text("📍 Выберите город:", reply_markup=kb)
    except TelegramBadRequest:
        await callback.message.reply("📍 Выберите город:", reply_markup=kb)


@dp.callback_query(F.data.startswith("citysel:"))
async def cb_city_select(callback: CallbackQuery):
    data = callback.data or ""
    try:
        city = data.split(":", 1)[1]
        if not city:
            raise ValueError("Empty city")
    except Exception:
        await callback.answer("Ошибка выбора", show_alert=True)
        return

    st = get_state(callback.from_user.id)
    st["filters"]["city"] = city
    st["page"] = 0

    await callback.answer(f"Выбран город: {city}")
    await send_unis_list(callback, callback.from_user.id, page=0)


# --- CALLBACKS СПЕЦИАЛЬНОСТЕЙ ---

def make_specs_keyboard(page: int) -> InlineKeyboardMarkup:
    total_pages = max(1, ceil(len(specialties) / SPECS_PER_PAGE))
    page = max(0, min(page, total_pages - 1))
    start = page * SPECS_PER_PAGE
    end = start + SPECS_PER_PAGE
    items = specialties[start:end]

    rows = [
        [InlineKeyboardButton(text=s, callback_data=f"specsel:{s}")]
        for s in items
    ]

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"specs:{page - 1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"specs:{page + 1}"))
    if nav_row:
        rows.append(nav_row)

    rows.append([InlineKeyboardButton(text="🏠 Назад в меню", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@dp.callback_query(F.data == "filter_specs")
async def cb_filter_specs(callback: CallbackQuery):
    await callback.answer()
    kb = make_specs_keyboard(page=0)
    try:
        await callback.message.edit_text("📚 Выберите специальность:", reply_markup=kb)
    except TelegramBadRequest:
        await callback.message.reply("📚 Выберите специальность:", reply_markup=kb)


@dp.callback_query(F.data.startswith("specs:"))
async def cb_specs_page(callback: CallbackQuery):
    data = callback.data or ""
    try:
        page = int(data.split(":")[1])
    except (IndexError, ValueError):
        page = 0
    await callback.answer()
    kb = make_specs_keyboard(page)
    try:
        await callback.message.edit_text("📚 Выберите специальность:", reply_markup=kb)
    except TelegramBadRequest:
        await callback.message.reply("📚 Выберите специальность:", reply_markup=kb)


@dp.callback_query(F.data.startswith("specsel:"))
async def cb_spec_select(callback: CallbackQuery):
    data = callback.data or ""
    try:
        spec = data.split(":", 1)[1]
        if not spec:
            raise ValueError("Empty spec")
    except Exception:
        await callback.answer("Ошибка выбора", show_alert=True)
        return

    st = get_state(callback.from_user.id)
    st["filters"]["spec"] = spec
    st["page"] = 0

    await callback.answer(f"Выбрана специальность: {spec}")
    await send_unis_list(callback, callback.from_user.id, page=0)


# --- НАВИГАЦИЯ ПО СПИСКУ ВУЗОВ ---

@dp.callback_query(F.data == "unis_prev")
async def cb_unis_prev(callback: CallbackQuery):
    st = get_state(callback.from_user.id)
    new_page = max(0, st.get("page", 0) - 1)
    await callback.answer()
    await send_unis_list(callback, callback.from_user.id, page=new_page)


@dp.callback_query(F.data == "unis_next")
async def cb_unis_next(callback: CallbackQuery):
    st = get_state(callback.from_user.id)
    new_page = st.get("page", 0) + 1
    await callback.answer()
    await send_unis_list(callback, callback.from_user.id, page=new_page)


# --- ОТКРЫТИЕ КАРТОЧКИ ВУЗА ---

@dp.callback_query(F.data.startswith("uni_open:"))
async def cb_uni_open(callback: CallbackQuery):
    # Формат: uni_open:<uid>:<page>
    data = callback.data or ""
    parts = data.split(":")
    if len(parts) < 3:
        await callback.answer("Ошибка данных", show_alert=True)
        return
    uid = parts[1]
    try:
        page = int(parts[2])
    except ValueError:
        page = 0

    uni = UNIS_BY_ID.get(uid)
    if not uni:
        await callback.answer("Университет не найден", show_alert=True)
        return

    text = format_uni_card_full(uni)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➕ В сравнение", callback_data=f"cmp_add:{uid}"),
                InlineKeyboardButton(text="⬅️ Назад к списку", callback_data=f"unis_goto:{page}"),
            ],
            [InlineKeyboardButton(text="📄 Полный список ВУЗов", url=FULL_UNIS_URL)],
            [InlineKeyboardButton(text="🏠 Меню", callback_data="menu")],
        ]
    )
    
    await callback.answer()
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
    except TelegramBadRequest:
        logger.exception("edit_text failed for uni card; sending message")
        await bot.send_message(callback.message.chat.id, text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)


@dp.callback_query(F.data.startswith("unis_goto:"))
async def cb_unis_goto(callback: CallbackQuery):
    """Обработчик кнопки 'Назад к списку' из карточки."""
    data = callback.data or ""
    try:
        page = int(data.split(":")[1])
    except Exception:
        page = 0
    st = get_state(callback.from_user.id)
    st["page"] = page
    
    await callback.answer()
    await send_unis_list(callback, callback.from_user.id, page=page)


# --- СРАВНЕНИЕ ---

def add_to_compare(user_id: int, uni_id: str):
    ids = compare_list.get(user_id, [])
    if uni_id in ids:
        return ids, False
    if len(ids) >= 3:
        return ids, False
    new_ids = ids + [uni_id]
    compare_list[user_id] = new_ids
    return new_ids, True


async def send_compare_view(chat_id: int, user_id: int):
    ids = compare_list.get(user_id, [])
    
    await bot.send_message(chat_id, " ", reply_markup=ReplyKeyboardRemove())

    if not ids:
        text = "Список сравнения пуст.\nДобавь ВУЗы через кнопку «➕ В сравнение»."
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 Меню", callback_data="menu"),
                                                    InlineKeyboardButton(text="📄 Полный список ВУЗов", url=FULL_UNIS_URL)]])
        await bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=kb)
        return

    items = []
    for uid in ids[:3]:
        u = UNIS_BY_ID.get(uid)
        if not u:
            continue
        name = html.escape(u.get("Name", "Без названия"))
        city = html.escape(u.get("City", "Не указан"))
        min_score = u.get("MinScore", "")
        specs = html.escape(u.get("Specialties", ""))
        website = html.escape(u.get("Website", ""))
        short_spec = specs.split(",")[0].strip() if specs else ""

        block_lines = [
            f"🎓 <b>{name}</b>",
            f"🏙 {city}",
        ]
        if str(min_score) != "":
            block_lines.append(f"📊 Мин. балл: {html.escape(str(min_score))}")
        if short_spec:
            block_lines.append(f"📚 Направление: {short_spec}")
        if website:
            block_lines.append(f"🔗 {website}")
        items.append("\n".join(block_lines))

    text = "⚖ <b>Сравнение ВУЗов</b>\n\n" + "\n\n━━━━━━━━━━━━\n\n".join(items)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧹 Очистить сравнение", callback_data="cmp_clear")],
            [InlineKeyboardButton(text="📄 Полный список ВУЗов", url=FULL_UNIS_URL)],
            [InlineKeyboardButton(text="🏠 Меню", callback_data="menu")],
        ]
    )
    
    await bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)


@dp.callback_query(F.data.startswith("cmp_add:"))
async def cb_cmp_add(callback: CallbackQuery):
    user_id = callback.from_user.id
    data = callback.data or ""
    uid = data.split(":", 1)[1] if ":" in data else ""
    
    if uid not in UNIS_BY_ID:
        await callback.answer("Ошибка добавления", show_alert=True)
        return

    ids_now, added = add_to_compare(user_id, uid)

    if added:
        await callback.answer(f"Добавлено! (Всего: {len(ids_now)}/3)")
    else:
        if len(ids_now) >= 3:
            await callback.answer("Максимум 3 ВУЗа в сравнении!", show_alert=True)
        else:
            await callback.answer("Уже в списке!")


@dp.callback_query(F.data == "cmp_show")
async def cb_cmp_show(callback: CallbackQuery):
    await callback.answer()
    await send_compare_view(callback.message.chat.id, callback.from_user.id)


@dp.callback_query(F.data == "cmp_clear")
async def cb_cmp_clear(callback: CallbackQuery):
    user_id = callback.from_user.id
    compare_list[user_id] = []
    await callback.answer("Список сравнения очищен")
    try:
        await callback.message.edit_text("⚖ Список сравнения пуст.", reply_markup=main_inline_menu())
    except TelegramBadRequest:
        await callback.message.reply("⚖ Список сравнения пуст.", reply_markup=main_inline_menu())


# --- ОБРАБОТКА ТЕКСТА (ПОИСК) ---

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

        # После ввода балла показываем список с фильтром
        await send_unis_list(message, user_id, page=0)
        return

    # Поиск по тексту (название/город)
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
            f"Ничего не найдено по запросу: <b>{html.escape(txt)}</b>",
            parse_mode="HTML",
            reply_markup=main_inline_menu() # Предлагаем вернуться в меню
        )
        return

    limit_res = results[:5]
    text_msg = f"🔎 Результаты по запросу: <b>{html.escape(txt)}</b>"
    
    rows = []
    # Отображаем найденные ВУЗы кнопками (каждая кнопка — отдельная строка)
    for u in limit_res:
        uid = u["ID"]
        name = html.escape(u["Name"] or "Без названия")
        btn = InlineKeyboardButton(text=f"🎓 {name}", callback_data=f"uni_open:{uid}:0")
        rows.append([btn])
    
    rows.append([InlineKeyboardButton(text="🏠 Меню", callback_data="menu")])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    
    await message.answer(text_msg, parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
    await message.answer(text_msg, parse_mode="HTML", reply_markup=kb)


async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info(f"Бот запущен. Вузов в базе: {len(universities)}")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())