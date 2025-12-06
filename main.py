"""
Улучшенный main.py — Telegram бот для поиска и сравнения ВУЗов Казахстана.
Основные цели:
 - Более понятная структура (функции/модули в одном файле для простоты)
 - Безопасный вывод HTML (html.escape уже использовался)
 - Чёткие клавиатуры: по 2 кнопки для каждого ВУЗа (Открыть / В сравнение), навигация и сервисные кнопки — широкие
 - Меньше дублирующих сообщений (нет пустых сообщений)
 - Больше валидации callback_data
 - Лёгкая опция переключиться на aiosqlite (закомментирована)
 - Комментарии и типы для лучшей понимаемости

Запуск: python main_improved.py

Перед запуском нужно указать BOT_TOKEN (переменная окружения) или заменить в файле.
"""

import os
import logging
import asyncio
import sqlite3
from math import ceil
from random import choice
import html
from typing import Dict, List, Optional, Any, Tuple

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

# ----------------- Настройки и логирование -----------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "ВАШ_ТОКЕН_ЗДЕСЬ")
DB_PATH = os.getenv("DB_PATH", "universities.db")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

if not BOT_TOKEN or BOT_TOKEN == "ВАШ_ТОКЕН_ЗДЕСЬ":
    logger.warning("⚠️ Внимание: не задан BOT_TOKEN. Замените на реальный токен перед запуском.")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ----------------- Конфигурация приложения -----------------
UNIS_PER_PAGE = 5
CITIES_PER_PAGE = 8
SPECS_PER_PAGE = 8

# ----------------- Данные в памяти -----------------
universities: List[Dict[str, Any]] = []  # список словарей с данными вузов
UNIS_BY_ID: Dict[str, Dict[str, Any]] = {}
cities: List[str] = []
specialties: List[str] = []

# состояние пользователей
user_state: Dict[int, Dict[str, Any]] = {}
# список сравнения: user_id -> list[uni_id]
compare_list: Dict[int, List[str]] = {}

# ----------------- Работа с БД -----------------

def load_from_sqlite(path: str = DB_PATH) -> None:
    """Загружает все записи в память.

    Для очень больших баз рекомендую переключиться на aiosqlite и ленивую пагинацию.
    """
    global universities, UNIS_BY_ID, cities, specialties

    if not os.path.exists(path):
        logger.error("Файл базы данных не найден: %s", path)
        universities = []
        UNIS_BY_ID = {}
        cities = []
        specialties = []
        return

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    try:
        cur.execute("SELECT * FROM universities")
        rows = cur.fetchall()
    except sqlite3.OperationalError as e:
        logger.exception("Ошибка чтения БД: %s", e)
        rows = []
    finally:
        conn.close()

    universities = []
    UNIS_BY_ID = {}
    city_set = set()
    spec_set = set()

    for row in rows:
        # безопасный набор полей — если что-то отсутствует, ставим пустую строку
        uid = str(row["id"]) if row.get("id") is not None else ""
        uni = {
            "ID": uid,
            "Name": row.get("name") or "",
            "City": row.get("city") or "",
            "Specialties": row.get("specialties") or "",
            "MinScore": row.get("min_score"),
            "About": row.get("about") or "",
            "Programs": row.get("programs") or "",
            "Admission": row.get("admission") or "",
            "Tour_3d": row.get("tour_3d") or "",
            "International": row.get("international") or "",
            "Website": row.get("website") or "",
        }
        universities.append(uni)
        if uid:
            UNIS_BY_ID[uid] = uni

        if uni["City"]:
            city_set.add(uni["City"].strip())

        # specialties могут быть в виде 'Спец1, Спец2'
        specs_raw = uni["Specialties"]
        for part in (specs_raw or "").split(","):
            p = part.strip()
            if p:
                spec_set.add(p)

    cities = sorted(city_set)
    specialties = sorted(spec_set)

    logger.info("Загружено %d вузов, %d городов, %d специальностей", len(universities), len(cities), len(specialties))


# первичная загрузка
load_from_sqlite()

# ----------------- Вспомогательные функции -----------------

def get_state(user_id: int) -> Dict[str, Any]:
    st = user_state.get(user_id)
    if not st:
        st = {"filters": {"city": None, "spec": None, "score": None}, "page": 0, "await_score": False}
        user_state[user_id] = st
    return st


def apply_filters(filters: Dict[str, Any]) -> List[Dict[str, Any]]:
    res = universities

    city = filters.get("city")
    if city:
        city_l = city.strip().lower()
        res = [u for u in res if (u.get("City") or "").strip().lower() == city_l]

    spec = filters.get("spec")
    if spec:
        spec_l = spec.strip().lower()
        res = [u for u in res if spec_l in (u.get("Specialties") or "").lower()]

    score = filters.get("score")
    if score is not None:
        filtered: List[Dict[str, Any]] = []
        for u in res:
            ms_val = u.get("MinScore")
            try:
                ms = int(ms_val) if ms_val is not None else 0
            except (ValueError, TypeError):
                # Пропускаем некорректные записи
                continue
            # Сохранена прежняя логика: ms >= score
            if ms >= int(score):
                filtered.append(u)
        # сортируем по убыванию min_score
        filtered.sort(key=lambda x: int(x.get("MinScore") or 0), reverse=True)
        res = filtered

    return res


def describe_filters(filters: Dict[str, Any], total: int) -> str:
    parts: List[str] = []
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


def format_uni_card_full(uni: Dict[str, Any]) -> str:
    """Формирует карточку университета — безопасно экранируя HTML-данные."""
    name = html.escape(uni.get("Name", "Без названия"))
    city = html.escape(uni.get("City", "Не указан"))
    specs = html.escape(uni.get("Specialties", ""))
    min_score = uni.get("MinScore", "")
    about = html.escape(uni.get("About", ""))
    programs = html.escape(uni.get("Programs", ""))
    admission = html.escape(uni.get("Admission", ""))
    international = html.escape(uni.get("International", ""))
    website = html.escape(uni.get("Website", ""))

    lines: List[str] = [f"🎓 <b>{name}</b>", "", f"🏙 Город: <b>{city}</b>"]
    if str(min_score) != "":
        lines.append(f"📊 Минимальный балл: {html.escape(str(min_score))}")
    if specs:
        lines.append(f"📚 Направления: {specs}")

    # Разделы
    lines.extend(["━━━━━━━━━━━━━━━━━━", "ℹ️ <b>Об университете</b>", about or "Нет данных.", "━━━━━━━━━━━━━━━━━━", "🎓 <b>Программы</b>", programs or "Нет данных.", "━━━━━━━━━━━━━━━━━━", "🎖 <b>Приём и стипендии</b>", admission or "Нет данных.", "━━━━━━━━━━━━━━━━━━", "🌍 <b>Международное сотрудничество</b>", international or "Нет данных."])

    if website:
        lines.extend(["━━━━━━━━━━━━━━━━━━", f"🔗 <b>Сайт:</b>\n{website}"])

    return "\n".join([l for l in lines if l is not None and l != ""])


# ----------------- Клавиатуры -----------------

def main_inline_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📍 Города", callback_data="filter_cities")],
        [InlineKeyboardButton(text="📚 Специальности", callback_data="filter_specs")],
        [InlineKeyboardButton(text="🔎 Показать ВУЗы", callback_data="show_all")],
        [InlineKeyboardButton(text="🧹 Сбросить фильтры", callback_data="reset_filters")],
    ])


def make_unis_keyboard(unis_page: List[Dict[str, Any]], page: int, total_pages: int) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []

    for u in unis_page:
        uid = (u.get("ID") or "").strip()
        if not uid:
            continue
        btn_open = InlineKeyboardButton(text="🔍 Открыть", callback_data=f"uni_open:{uid}:{page}")
        btn_cmp = InlineKeyboardButton(text="➕ В сравнение", callback_data=f"cmp_add:{uid}")
        rows.append([btn_open, btn_cmp])

    # Навигация: если обе кнопки — в одной строке, Telegram автоматически распределит ширину
    nav_buttons: List[InlineKeyboardButton] = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data="unis_prev"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="➡️ Далее", callback_data="unis_next"))
    if nav_buttons:
        rows.append(nav_buttons)

    # Сервисные кнопки — широкие строки
    rows.append([InlineKeyboardButton(text="⚖ Сравнить выбр", callback_data="cmp_show")])
    rows.append([InlineKeyboardButton(text="🧹 Сбросить фильт", callback_data="reset_filters")])
    rows.append([InlineKeyboardButton(text="🏠 Меню", callback_data="menu")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_cities_keyboard(page: int) -> InlineKeyboardMarkup:
    total_pages = max(1, ceil(len(cities) / CITIES_PER_PAGE))
    page = max(0, min(page, total_pages - 1))
    start = page * CITIES_PER_PAGE
    items = cities[start:start + CITIES_PER_PAGE]

    rows = [[InlineKeyboardButton(text=c, callback_data=f"citysel:{c}")] for c in items]

    nav_row: List[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"cities:{page - 1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"cities:{page + 1}"))
    if nav_row:
        rows.append(nav_row)

    rows.append([InlineKeyboardButton(text="🏠 Назад в меню", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_specs_keyboard(page: int) -> InlineKeyboardMarkup:
    total_pages = max(1, ceil(len(specialties) / SPECS_PER_PAGE))
    page = max(0, min(page, total_pages - 1))
    start = page * SPECS_PER_PAGE
    items = specialties[start:start + SPECS_PER_PAGE]

    rows = [[InlineKeyboardButton(text=s, callback_data=f"specsel:{s}")] for s in items]

    nav_row: List[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"specs:{page - 1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"specs:{page + 1}"))
    if nav_row:
        rows.append(nav_row)

    rows.append([InlineKeyboardButton(text="🏠 Назад в меню", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ----------------- Отправка списка ВУЗов -----------------

async def send_unis_list(message_or_call: Any, user_id: int, page: Optional[int] = None) -> None:
    st = get_state(user_id)
    filters = st["filters"]

    if page is None:
        page = st.get("page", 0)
    else:
        st["page"] = page

    all_unis = apply_filters(filters)

    # Если ничего не найдено — показываем информативное сообщение и клавиатуру
    if not all_unis:
        text = describe_filters(filters, 0) + "\n\nНичего не найдено по таким условиям."
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🧹 Сбросить фильтры", callback_data="reset_filters")],
            [InlineKeyboardButton(text="🏠 Меню", callback_data="menu")],
        ])

        if isinstance(message_or_call, CallbackQuery):
            try:
                await message_or_call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
            except TelegramBadRequest:
                logger.exception("edit_text failed while showing empty results; sending new message")
                await bot.send_message(message_or_call.message.chat.id, text, parse_mode="HTML", reply_markup=kb)
        else:
            # message_or_call — Message
            await message_or_call.answer(text, parse_mode="HTML", reply_markup=kb)
        return

    total_pages = max(1, ceil(len(all_unis) / UNIS_PER_PAGE))
    page = max(0, min(page, total_pages - 1))
    st["page"] = page

    start = page * UNIS_PER_PAGE
    unis_page = all_unis[start:start + UNIS_PER_PAGE]

    text = describe_filters(filters, len(all_unis)) + f"\n\n📄 Страница {page + 1} из {total_pages}\n👇 <b>Выберите университет:</b>"
    kb = make_unis_keyboard(unis_page, page, total_pages)

    if isinstance(message_or_call, CallbackQuery):
        try:
            await message_or_call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except TelegramBadRequest:
            logger.exception("edit_text failed while sending unis list; fallback to new message")
            await bot.send_message(message_or_call.message.chat.id, text, parse_mode="HTML", reply_markup=kb)
    else:
        # Убираем reply keyboard и отправляем список как одно сообщение с инлайн-кнопками
        await message_or_call.answer(text, parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
        await message_or_call.answer(text, parse_mode="HTML", reply_markup=kb)


# ----------------- Хендлеры -----------------
@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    get_state(message.from_user.id)
    await message.answer("👋 Привет! Это DataHub ВУЗов Казахстана.", reply_markup=ReplyKeyboardRemove())
    await message.answer(
        "Найди ВУЗ по городу, направлению, баллу или сравни несколько между собой.\n\nВыберите фильтр:",
        reply_markup=main_inline_menu(),
        parse_mode="HTML",
    )


@dp.message(F.text == "Фильтры")
async def show_filters(message: Message) -> None:
    await message.answer("Выберите фильтр:", reply_markup=main_inline_menu())


@dp.message(F.text == "Помощь")
async def help_message(message: Message) -> None:
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
async def excel_link(message: Message) -> None:
    await message.answer(
        "📊 Полная таблица ВУЗов Казахстана в Excel:\n"
        "https://drive.google.com/drive/folders/1fjZvILeJXRLSkiL2zhaz_fcngD7nKkoU",
        parse_mode="HTML",
    )


@dp.message(F.text == "🎲 Случайный ВУЗ")
async def random_uni(message: Message) -> None:
    if not universities:
        await message.answer("База ВУЗов пустая.")
        return
    uni = choice(universities)
    text = "🎲 <b>Случайный ВУЗ:</b>\n\n" + format_uni_card_full(uni)
    uid = uni["ID"]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ В сравнение", callback_data=f"cmp_add:{uid}")],
        [InlineKeyboardButton(text="🏠 Меню", callback_data="menu")],
    ])
    await message.answer(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)


@dp.message(F.text == "⚖ Сравнение")
async def compare_button(message: Message) -> None:
    await send_compare_view(message.chat.id, message.from_user.id)


@dp.message(F.text == "🔢 Поиск по баллу")
async def ask_score(message: Message) -> None:
    st = get_state(message.from_user.id)
    st["await_score"] = True
    await message.answer("Введи минимальный балл ЕНТ (например, <code>90</code>):", parse_mode="HTML")


# ----------------- CALLBACKS -----------------
@dp.callback_query(F.data == "menu")
async def cb_menu(callback: CallbackQuery) -> None:
    await callback.answer()
    try:
        await callback.message.edit_text("🏠 <b>Главное меню</b>\nВыберите действие:", reply_markup=main_inline_menu(), parse_mode="HTML")
    except TelegramBadRequest:
        await callback.message.reply("🏠 <b>Главное меню</b>\nВыберите действие:", reply_markup=main_inline_menu(), parse_mode="HTML")


@dp.callback_query(F.data == "reset_filters")
async def cb_reset_filters(callback: CallbackQuery) -> None:
    st = get_state(callback.from_user.id)
    st["filters"] = {"city": None, "spec": None, "score": None}
    st["page"] = 0
    await callback.answer("Фильтры сброшены")
    try:
        await callback.message.edit_text("✅ Фильтры сброшены. Выберите действие:", reply_markup=main_inline_menu())
    except TelegramBadRequest:
        await callback.message.reply("✅ Фильтры сброшены. Выберите действие:", reply_markup=main_inline_menu())


@dp.callback_query(F.data == "show_all")
async def cb_show_all(callback: CallbackQuery) -> None:
    await callback.answer()
    st = get_state(callback.from_user.id)
    st["page"] = 0
    await send_unis_list(callback, callback.from_user.id, page=0)


# --- Города ---
@dp.callback_query(F.data == "filter_cities")
async def cb_filter_cities(callback: CallbackQuery) -> None:
    await callback.answer()
    kb = make_cities_keyboard(page=0)
    try:
        await callback.message.edit_text("📍 Выберите город:", reply_markup=kb)
    except TelegramBadRequest:
        await callback.message.reply("📍 Выберите город:", reply_markup=kb)


@dp.callback_query(F.data.startswith("cities:"))
async def cb_cities_page(callback: CallbackQuery) -> None:
    data = callback.data or ""
    page = 0
    try:
        page = int(data.split(":", 1)[1])
    except Exception:
        page = 0
    await callback.answer()
    kb = make_cities_keyboard(page)
    try:
        await callback.message.edit_text("📍 Выберите город:", reply_markup=kb)
    except TelegramBadRequest:
        await callback.message.reply("📍 Выберите город:", reply_markup=kb)


@dp.callback_query(F.data.startswith("citysel:"))
async def cb_city_select(callback: CallbackQuery) -> None:
    data = callback.data or ""
    try:
        city = data.split(":", 1)[1]
        if not city:
            raise ValueError("empty")
    except Exception:
        await callback.answer("Ошибка выбора", show_alert=True)
        return
    st = get_state(callback.from_user.id)
    st["filters"]["city"] = city
    st["page"] = 0
    await callback.answer(f"Выбран город: {city}")
    await send_unis_list(callback, callback.from_user.id, page=0)


# --- Специальности ---
@dp.callback_query(F.data == "filter_specs")
async def cb_filter_specs(callback: CallbackQuery) -> None:
    await callback.answer()
    kb = make_specs_keyboard(page=0)
    try:
        await callback.message.edit_text("📚 Выберите специальность:", reply_markup=kb)
    except TelegramBadRequest:
        await callback.message.reply("📚 Выберите специальность:", reply_markup=kb)


@dp.callback_query(F.data.startswith("specs:"))
async def cb_specs_page(callback: CallbackQuery) -> None:
    data = callback.data or ""
    page = 0
    try:
        page = int(data.split(":", 1)[1])
    except Exception:
        page = 0
    await callback.answer()
    kb = make_specs_keyboard(page)
    try:
        await callback.message.edit_text("📚 Выберите специальность:", reply_markup=kb)
    except TelegramBadRequest:
        await callback.message.reply("📚 Выберите специальность:", reply_markup=kb)


@dp.callback_query(F.data.startswith("specsel:"))
async def cb_spec_select(callback: CallbackQuery) -> None:
    data = callback.data or ""
    try:
        spec = data.split(":", 1)[1]
        if not spec:
            raise ValueError("empty")
    except Exception:
        await callback.answer("Ошибка выбора", show_alert=True)
        return
    st = get_state(callback.from_user.id)
    st["filters"]["spec"] = spec
    st["page"] = 0
    await callback.answer(f"Выбрана специальность: {spec}")
    await send_unis_list(callback, callback.from_user.id, page=0)


# --- Навигация ---
@dp.callback_query(F.data == "unis_prev")
async def cb_unis_prev(callback: CallbackQuery) -> None:
    st = get_state(callback.from_user.id)
    new_page = max(0, st.get("page", 0) - 1)
    await callback.answer()
    await send_unis_list(callback, callback.from_user.id, page=new_page)


@dp.callback_query(F.data == "unis_next")
async def cb_unis_next(callback: CallbackQuery) -> None:
    st = get_state(callback.from_user.id)
    new_page = st.get("page", 0) + 1
    await callback.answer()
    await send_unis_list(callback, callback.from_user.id, page=new_page)


# --- Карточка ВУЗа ---
@dp.callback_query(F.data.startswith("uni_open:"))
async def cb_uni_open(callback: CallbackQuery) -> None:
    data = callback.data or ""
    parts = data.split(":")
    if len(parts) < 3:
        await callback.answer("Ошибка данных", show_alert=True)
        return
    uid = parts[1]
    try:
        page = int(parts[2])
    except Exception:
        page = 0

    uni = UNIS_BY_ID.get(uid)
    if not uni:
        await callback.answer("Университет не найден", show_alert=True)
        return

    text = format_uni_card_full(uni)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ В сравнение", callback_data=f"cmp_add:{uid}"), InlineKeyboardButton(text="⬅️ Назад к списку", callback_data=f"unis_goto:{page}")],
        [InlineKeyboardButton(text="🏠 Меню", callback_data="menu")],
    ])

    await callback.answer()
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
    except TelegramBadRequest:
        logger.exception("edit_text failed for uni card; sending new message")
        await bot.send_message(callback.message.chat.id, text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)


@dp.callback_query(F.data.startswith("unis_goto:"))
async def cb_unis_goto(callback: CallbackQuery) -> None:
    data = callback.data or ""
    try:
        page = int(data.split(":", 1)[1])
    except Exception:
        page = 0
    st = get_state(callback.from_user.id)
    st["page"] = page
    await callback.answer()
    await send_unis_list(callback, callback.from_user.id, page=page)


# --- Сравнение ---
def add_to_compare(user_id: int, uni_id: str) -> Tuple[List[str], bool]:
    ids = compare_list.get(user_id, [])
    if uni_id in ids:
        return ids, False
    if len(ids) >= 3:
        return ids, False
    new_ids = ids + [uni_id]
    compare_list[user_id] = new_ids
    return new_ids, True


async def send_compare_view(chat_id: int, user_id: int) -> None:
    ids = compare_list.get(user_id, [])

    if not ids:
        text = "⚖ <b>Сравнение ВУЗов</b>\n\nСписок сравнения пуст. Добавь ВУЗы через кнопку «➕ В сравнение»."
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 Меню", callback_data="menu")]])
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

        short_spec = (specs.split(",")[0].strip() if specs else "")
        lines = [f"🎓 <b>{name}</b>", f"🏙 {city}"]
        if str(min_score) != "":
            lines.append(f"📊 Мин. балл: {html.escape(str(min_score))}")
        if short_spec:
            lines.append(f"📚 Направление: {short_spec}")
        if website:
            lines.append(f"🔗 {website}")
        items.append("\n".join(lines))

    text = "⚖ <b>Сравнение ВУЗов</b>\n\n" + "\n\n━━━━━━━━━━━━\n\n".join(items)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧹 Очистить сравнение", callback_data="cmp_clear")],
        [InlineKeyboardButton(text="🏠 Меню", callback_data="menu")],
    ])

    await bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)


@dp.callback_query(F.data.startswith("cmp_add:"))
async def cb_cmp_add(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    data = callback.data or ""
    uid = ""
    try:
        uid = data.split(":", 1)[1]
    except Exception:
        uid = ""

    if not uid or uid not in UNIS_BY_ID:
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
async def cb_cmp_show(callback: CallbackQuery) -> None:
    await callback.answer()
    await send_compare_view(callback.message.chat.id, callback.from_user.id)


@dp.callback_query(F.data == "cmp_clear")
async def cb_cmp_clear(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    compare_list[user_id] = []
    await callback.answer("Список сравнения очищен")
    try:
        await callback.message.edit_text("⚖ Список сравнения пуст.", reply_markup=main_inline_menu())
    except TelegramBadRequest:
        await callback.message.reply("⚖ Список сравнения пуст.", reply_markup=main_inline_menu())


# --- Обработка текста (поиск) ---
@dp.message()
async def text_handler(message: Message) -> None:
    user_id = message.from_user.id
    st = get_state(user_id)
    txt = (message.text or "").strip()

    # Если ожидается ввод балла
    if st.get("await_score"):
        try:
            score = int(txt)
        except ValueError:
            await message.answer("Нужно ввести целое число, например: 95")
            return
        st["filters"]["score"] = score
        st["page"] = 0
        st["await_score"] = False
        await send_unis_list(message, user_id, page=0)
        return

    # Поиск по тексту: имя / город / специальность
    q = txt.lower()
    results: List[Dict[str, Any]] = []
    for u in universities:
        name = (u.get("Name") or "").lower()
        city = (u.get("City") or "").lower()
        specs = (u.get("Specialties") or "").lower()
        if q in name or q == city or q in specs:
            results.append(u)

    if not results:
        await message.answer(f"Ничего не найдено по запросу: <b>{html.escape(txt)}</b>", parse_mode="HTML", reply_markup=main_inline_menu())
        return

    limit_res = results[:5]
    text_msg = f"🔎 Результаты по запросу: <b>{html.escape(txt)}</b>"

    rows: List[List[InlineKeyboardButton]] = []
    for u in limit_res:
        uid = u["ID"]
        name = html.escape(u.get("Name") or "Без названия")
        rows.append([InlineKeyboardButton(text=f"🎓 {name}", callback_data=f"uni_open:{uid}:0")])

    rows.append([InlineKeyboardButton(text="🏠 Меню", callback_data="menu")])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)

    await message.answer(text_msg, parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
    await message.answer(text_msg, parse_mode="HTML", reply_markup=kb)


# ----------------- Утилиты админа (опционально) -----------------
@dp.message(F.text == "/reload_db")
async def cmd_reload_db(message: Message) -> None:
    # Команда для разработчика: перезагрузить базу в память
    load_from_sqlite()
    await message.answer(f"БД перезагружена. Вузов в памяти: {len(universities)}")


# ----------------- Запуск бота -----------------
async def main() -> None:
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Бот запущен. Вузов в базе: %d", len(universities))
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Завершение работы бота")
