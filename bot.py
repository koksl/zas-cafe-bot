"""
Демо-бот для кафе/ресторана — показывает клиентам Kwork/Авито
что такое "бот с ИИ под ключ".

Функции:
- Меню с категориями и ценами
- Бронирование столика (имя, телефон, дата, кол-во гостей)
- Акция дня
- ИИ-ответы на свободные вопросы (Claude API)
- Уведомление владельца о каждой брони
"""

import asyncio
import logging
import os
from dotenv import load_dotenv

load_dotenv()

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)
import anthropic

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_TELEGRAM_ID", "0"))
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CAFE_NAME = os.getenv("CAFE_NAME", "Кафе «Уют»")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

claude = anthropic.Anthropic(api_key=ANTHROPIC_KEY) if ANTHROPIC_KEY else None

# ─── МЕНЮ ────────────────────────────────────────────────────────────────────

MENU = {
    "hot": {
        "name": "🍲 Горячие блюда",
        "items": [
            ("Борщ домашний", "290 ₽"),
            ("Куриный суп с лапшой", "250 ₽"),
            ("Жаркое по-домашнему", "420 ₽"),
            ("Котлета по-киевски с гарниром", "380 ₽"),
            ("Паста карбонара", "350 ₽"),
            ("Стейк из лосося", "590 ₽"),
        ],
    },
    "salads": {
        "name": "🥗 Салаты и закуски",
        "items": [
            ("Цезарь с курицей", "320 ₽"),
            ("Греческий салат", "280 ₽"),
            ("Оливье", "220 ₽"),
            ("Брускетта с томатами", "180 ₽"),
            ("Сырная тарелка", "450 ₽"),
        ],
    },
    "drinks": {
        "name": "☕ Напитки",
        "items": [
            ("Американо", "120 ₽"),
            ("Капучино", "160 ₽"),
            ("Латте", "180 ₽"),
            ("Свежевыжатый сок", "220 ₽"),
            ("Чай (ассорти)", "100 ₽"),
            ("Лимонад домашний", "190 ₽"),
        ],
    },
    "desserts": {
        "name": "🍰 Десерты",
        "items": [
            ("Тирамису", "280 ₽"),
            ("Чизкейк Нью-Йорк", "260 ₽"),
            ("Блинчики со сгущёнкой", "200 ₽"),
            ("Мороженое (3 шарика)", "180 ₽"),
        ],
    },
}

DAILY_SPECIAL = "🌟 *Акция дня:* Бизнес-ланч — суп + горячее + напиток всего за *390 ₽* (с 12:00 до 16:00)"

SYSTEM_PROMPT = f"""Ты — приветливый администратор кафе «{CAFE_NAME}».
Помогаешь гостям с вопросами о меню, бронировании столиков, акциях и режиме работы.

ИНФОРМАЦИЯ О КАФЕ:
Режим работы: Пн–Пт 8:00–22:00, Сб–Вс 10:00–23:00
Адрес: уточняйте у администратора (это демо-бот)
Вместимость: 40 мест, есть зал для мероприятий на 20 человек
Wi-Fi: есть, бесплатный
Парковка: есть рядом

ПРАВИЛА:
- Отвечай тепло, коротко и по делу
- Если гость хочет забронировать — предложи кнопку "Забронировать столик"
- Не придумывай блюда и цены вне меню
- Бизнес-ланч: суп + горячее + напиток = 390 ₽ (12:00–16:00, пн–пт)

МЕНЮ (кратко):
Горячее от 250 ₽, салаты от 180 ₽, напитки от 100 ₽, десерты от 180 ₽.
"""


# ─── FSM: БРОНИРОВАНИЕ ───────────────────────────────────────────────────────

class BookingState(StatesGroup):
    entering_name = State()
    entering_phone = State()
    entering_date = State()
    entering_guests = State()
    confirming = State()

class LeadState(StatesGroup):
    waiting_description = State()


# ─── КЛАВИАТУРЫ ──────────────────────────────────────────────────────────────

def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍲 Горячие блюда", callback_data="cat:hot"),
         InlineKeyboardButton(text="🥗 Салаты", callback_data="cat:salads")],
        [InlineKeyboardButton(text="☕ Напитки", callback_data="cat:drinks"),
         InlineKeyboardButton(text="🍰 Десерты", callback_data="cat:desserts")],
        [InlineKeyboardButton(text="🌟 Акция дня", callback_data="special")],
        [InlineKeyboardButton(text="📅 Забронировать столик", callback_data="book:start")],
        [InlineKeyboardButton(text="❓ Задать вопрос", callback_data="ask")],
        [InlineKeyboardButton(text="💼 Хочу такой бот для своего бизнеса", callback_data="lead")],
    ])


def back_to_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Главное меню", callback_data="menu")],
        [InlineKeyboardButton(text="📅 Забронировать столик", callback_data="book:start")],
    ])


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить бронь", callback_data="book:confirm"),
         InlineKeyboardButton(text="✏️ Изменить", callback_data="book:start")],
    ])


def phone_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Отправить номер", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def guests_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for i in range(1, 9):
        row.append(InlineKeyboardButton(text=str(i), callback_data=f"guests:{i}"))
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="Больше 8 — уточнить", callback_data="guests:8+")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ─── ХЭНДЛЕРЫ ────────────────────────────────────────────────────────────────

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        f"Добро пожаловать в *{CAFE_NAME}*! ☕\n\n"
        "Я помогу вам:\n"
        "• Посмотреть меню и цены\n"
        "• Забронировать столик\n"
        "• Узнать об акциях\n"
        "• Ответить на любые вопросы\n\n"
        f"{DAILY_SPECIAL}\n\n"
        "Выберите, что вас интересует:\n\n"
        "_Хотите такого бота для своего бизнеса? → «💼 Хочу такой бот»_",
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )


@dp.callback_query(F.data == "menu")
async def cb_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        f"*{CAFE_NAME}* — чем могу помочь? ☕\n\n{DAILY_SPECIAL}",
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )
    await callback.answer()


# ── Каталог меню ──────────────────────────────────────────────────────────────

@dp.callback_query(F.data.startswith("cat:"))
async def cb_category(callback: CallbackQuery):
    key = callback.data.split(":")[1]
    cat = MENU.get(key)
    if not cat:
        await callback.answer("Раздел не найден")
        return

    lines = [f"*{cat['name']}*\n"]
    for name, price in cat["items"]:
        lines.append(f"• {name} — *{price}*")

    await callback.message.edit_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=back_to_menu(),
    )
    await callback.answer()


@dp.callback_query(F.data == "special")
async def cb_special(callback: CallbackQuery):
    await callback.message.edit_text(
        f"{DAILY_SPECIAL}\n\n"
        "Бизнес-ланч включает:\n"
        "• Любой суп из меню\n"
        "• Горячее блюдо (котлета / паста / рыба)\n"
        "• Чай или кофе\n\n"
        "Предложение действует с 12:00 до 16:00, пн–пт.\n"
        "Столик лучше забронировать заранее — бывает очередь! 😊",
        parse_mode="Markdown",
        reply_markup=back_to_menu(),
    )
    await callback.answer()


# ── Бронирование ──────────────────────────────────────────────────────────────

@dp.callback_query(F.data == "book:start")
async def cb_book_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BookingState.entering_name)
    await callback.message.edit_text(
        "📅 *Бронирование столика*\n\n"
        "Шаг 1/4 — Как вас зовут?\n"
        "(Введите имя и фамилию)",
        parse_mode="Markdown",
    )
    await callback.answer()


@dp.message(BookingState.entering_name)
async def booking_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("Пожалуйста, введите корректное имя:")
        return
    await state.update_data(name=name)
    await state.set_state(BookingState.entering_phone)
    await message.answer(
        f"Отлично, *{name}*! 👋\n\n"
        "Шаг 2/4 — Укажите номер телефона\n"
        "(для подтверждения брони)",
        parse_mode="Markdown",
        reply_markup=phone_keyboard(),
    )


@dp.message(BookingState.entering_phone, F.contact)
async def booking_phone_contact(message: Message, state: FSMContext):
    await _proceed_to_date(message, state, message.contact.phone_number)


@dp.message(BookingState.entering_phone, F.text)
async def booking_phone_text(message: Message, state: FSMContext):
    phone = message.text.strip()
    digits = ''.join(c for c in phone if c.isdigit())
    if len(digits) < 10:
        await message.answer("Введите корректный номер телефона (например: +7 999 123-45-67):")
        return
    await _proceed_to_date(message, state, phone)


async def _proceed_to_date(message: Message, state: FSMContext, phone: str):
    await state.update_data(phone=phone)
    await state.set_state(BookingState.entering_date)
    await message.answer(
        "Шаг 3/4 — На какую дату и время?\n\n"
        "Например: *сегодня в 19:00* или *15 марта в 20:30*\n\n"
        "Работаем: Пн–Пт 8:00–22:00, Сб–Вс 10:00–23:00",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )


@dp.message(BookingState.entering_date)
async def booking_date(message: Message, state: FSMContext):
    date_str = message.text.strip()
    if len(date_str) < 3:
        await message.answer("Укажите дату и время:")
        return
    await state.update_data(date=date_str)
    await state.set_state(BookingState.entering_guests)
    await message.answer(
        "Шаг 4/4 — Сколько гостей?\n\nВыберите количество:",
        reply_markup=guests_keyboard(),
    )


@dp.callback_query(BookingState.entering_guests, F.data.startswith("guests:"))
async def booking_guests(callback: CallbackQuery, state: FSMContext):
    guests = callback.data.split(":")[1]
    await state.update_data(guests=guests)
    data = await state.get_data()
    await state.set_state(BookingState.confirming)

    guests_label = f"{guests} чел." if guests != "8+" else "более 8 (уточним)"

    await callback.message.edit_text(
        f"📋 *Проверьте данные брони:*\n\n"
        f"👤 Имя: {data['name']}\n"
        f"📱 Телефон: {data['phone']}\n"
        f"📅 Дата/время: {data['date']}\n"
        f"👥 Гостей: {guests_label}\n\n"
        "Всё верно?",
        parse_mode="Markdown",
        reply_markup=confirm_keyboard(),
    )
    await callback.answer()


@dp.callback_query(F.data == "book:confirm", BookingState.confirming)
async def booking_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    guests_label = f"{data['guests']} чел." if data['guests'] != "8+" else "более 8 (уточним)"

    # Уведомляем владельца — plain text
    owner_text = (
        f"🔔 Новая бронь!\n\n"
        f"👤 {data['name']}\n"
        f"📱 {data['phone']}\n"
        f"📅 {data['date']}\n"
        f"👥 Гостей: {guests_label}\n"
        f"TG: @{callback.from_user.username or '—'} (id: {callback.from_user.id})"
    )
    try:
        await bot.send_message(OWNER_ID, owner_text)
    except Exception as e:
        log.error(f"Owner notification failed: {e}")

    await callback.message.edit_text(
        f"✅ *Столик забронирован!*\n\n"
        f"📅 {data['date']}\n"
        f"👥 {guests_label}\n\n"
        "Мы позвоним для подтверждения в течение 30 минут.\n\n"
        f"Ждём вас в *{CAFE_NAME}*! ☕",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← Главное меню", callback_data="menu")]
        ]),
    )
    await callback.answer("Бронь оформлена!")


# ── ИИ-ответы ─────────────────────────────────────────────────────────────────

@dp.callback_query(F.data == "ask")
async def cb_ask(callback: CallbackQuery):
    await callback.message.edit_text(
        "❓ Задайте любой вопрос — о меню, бронировании, акциях или режиме работы:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← Меню", callback_data="menu")]
        ]),
    )
    await callback.answer()


@dp.message(F.text & ~F.text.startswith("/"))
async def handle_free_text(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state:
        return

    await bot.send_chat_action(message.chat.id, "typing")

    if claude:
        try:
            response = claude.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=300,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": message.text}],
            )
            answer = response.content[0].text
        except Exception as e:
            log.error(f"Claude error: {e}")
            answer = _fallback_answer(message.text)
    else:
        answer = _fallback_answer(message.text)

    await message.answer(
        answer,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📅 Забронировать", callback_data="book:start"),
             InlineKeyboardButton(text="📋 Меню", callback_data="menu")],
        ]),
    )


def _fallback_answer(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ["цен", "стоит", "сколько", "прайс"]):
        return (
            "Наши цены:\n\n"
            "🍲 Горячее — от 250 ₽\n"
            "🥗 Салаты — от 180 ₽\n"
            "☕ Напитки — от 100 ₽\n"
            "🍰 Десерты — от 180 ₽\n\n"
            "Бизнес-ланч: суп + горячее + напиток = 390 ₽ (12–16ч)"
        )
    if any(w in t for w in ["работает", "время", "часы", "режим", "открыт"]):
        return "Пн–Пт: 8:00–22:00\nСб–Вс: 10:00–23:00 ☕"
    if any(w in t for w in ["брон", "забронир", "столик", "место"]):
        return "Конечно! Нажмите кнопку «Забронировать столик» — займёт 1 минуту 😊"
    if any(w in t for w in ["акци", "скидк", "специальн", "ланч"]):
        return "Бизнес-ланч: суп + горячее + напиток = 390 ₽\nДействует пн–пт с 12:00 до 16:00 🌟"
    return (
        "Спасибо за вопрос! ☕ Для быстрого ответа нажмите «Забронировать столик» "
        "или выберите раздел в меню — я помогу с любым вопросом."
    )


# ─── ЗАХВАТ ЛИДОВ ────────────────────────────────────────────────────────────

@dp.callback_query(F.data == "lead")
async def cb_lead_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(LeadState.waiting_description)
    await callback.message.edit_text(
        "💼 *Хотите такого бота для своего бизнеса?*\n\n"
        "Этот бот сделан за 5 дней на Python + ИИ.\n\n"
        "Расскажите кратко:\n"
        "• Чем занимается ваш бизнес?\n"
        "• Что должен делать бот?\n\n"
        "Я передам запрос разработчику — он пришлёт расчёт:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← Отмена", callback_data="menu")]
        ]),
    )
    await callback.answer()


@dp.message(LeadState.waiting_description)
async def lead_description(message: Message, state: FSMContext):
    await state.clear()
    user = message.from_user
    username = f"@{user.username}" if user.username else f"id{user.id}"
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "Без имени"

    owner_text = (
        f"🔥 Новый лид — @ZasCafeBot (кафе)!\n\n"
        f"👤 {full_name} ({username})\n"
        f"🔗 Написать: tg://user?id={user.id}\n\n"
        f"📝 Задача:\n{message.text}"
    )
    try:
        await bot.send_message(OWNER_ID, owner_text)
    except Exception as e:
        log.error(f"Lead notification failed: {e}")

    await message.answer(
        "✅ *Отлично! Запрос передан разработчику.*\n\n"
        "Он свяжется с вами в ближайший час — обсудит детали и пришлёт точный расчёт стоимости.\n\n"
        "_Разработка ботов от 25 000 ₽, срок 5-7 дней._",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← Вернуться в меню", callback_data="menu")]
        ]),
    )


# ─── ЗАПУСК ───────────────────────────────────────────────────────────────────

async def main():
    log.info(f"Demo cafe bot '{CAFE_NAME}' starting...")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
