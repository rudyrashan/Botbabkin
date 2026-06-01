import os
import csv
import random
import sqlite3
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    LabeledPrice,
    InputFile
)
from aiogram.utils.exceptions import ChatNotFound


# =========================
# НАСТРОЙКИ
# =========================

BOT_TOKEN = "8362290757:AAGWF9ftw3-2KwZuwnt8i0P5TxfJ7bmTITM"

ADMIN_IDS = [
    7763554656
]

CHANNEL_BABKIN = "@vse7budet"
CHANNEL_PLATINUM = "@platinum_motors"

BABKIN_URL = "https://t.me/vse7budet"
PLATINUM_URL = "https://t.me/platinum_motors"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.sqlite3")
IMAGE_PATH = os.path.join(BASE_DIR, "image.jpg")

STARS_PRICE = 77
PAYLOAD_EXTRA_TICKET = "extra_ticket_77_stars"

BOT_USERNAME = None

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)


# =========================
# БАЗА ДАННЫХ
# =========================

def db_connect():
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = db_connect()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            referrer_id INTEGER,
            is_registered INTEGER DEFAULT 0,
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            ticket_number INTEGER UNIQUE,
            reason TEXT,
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER,
            referred_id INTEGER UNIQUE,
            ticket_given INTEGER DEFAULT 0,
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount INTEGER,
            payload TEXT,
            telegram_payment_charge_id TEXT,
            created_at TEXT
        )
    """)

    conn.commit()
    conn.close()


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def add_or_update_user(user: types.User, referrer_id=None):
    conn = db_connect()
    cur = conn.cursor()

    cur.execute("SELECT user_id FROM users WHERE user_id = ?", (user.id,))
    existing = cur.fetchone()

    if existing:
        cur.execute("""
            UPDATE users
            SET username = ?, first_name = ?
            WHERE user_id = ?
        """, (user.username, user.first_name, user.id))
    else:
        if referrer_id == user.id:
            referrer_id = None

        cur.execute("""
            INSERT INTO users (user_id, username, first_name, referrer_id, is_registered, created_at)
            VALUES (?, ?, ?, ?, 0, ?)
        """, (user.id, user.username, user.first_name, referrer_id, now()))

        if referrer_id:
            cur.execute("""
                INSERT OR IGNORE INTO referrals (referrer_id, referred_id, ticket_given, created_at)
                VALUES (?, ?, 0, ?)
            """, (referrer_id, user.id, now()))

    conn.commit()
    conn.close()


def is_user_registered(user_id):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT is_registered FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return bool(row and row[0] == 1)


def set_registered(user_id):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("UPDATE users SET is_registered = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def generate_ticket_number():
    conn = db_connect()
    cur = conn.cursor()

    while True:
        ticket = random.randint(100000, 999999)
        cur.execute("SELECT id FROM tickets WHERE ticket_number = ?", (ticket,))
        if not cur.fetchone():
            conn.close()
            return ticket


def add_ticket(user_id, reason):
    ticket_number = generate_ticket_number()

    conn = db_connect()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO tickets (user_id, ticket_number, reason, created_at)
        VALUES (?, ?, ?, ?)
    """, (user_id, ticket_number, reason, now()))
    conn.commit()
    conn.close()

    return ticket_number


def get_user_tickets(user_id):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT ticket_number, reason, created_at
        FROM tickets
        WHERE user_id = ?
        ORDER BY id ASC
    """, (user_id,))
    rows = cur.fetchall()
    conn.close()
    return rows


def give_referrer_ticket_if_needed(referred_id):
    conn = db_connect()
    cur = conn.cursor()

    cur.execute("""
        SELECT referrer_id, ticket_given
        FROM referrals
        WHERE referred_id = ?
    """, (referred_id,))
    row = cur.fetchone()

    if not row:
        conn.close()
        return None

    referrer_id, ticket_given = row

    if ticket_given == 1:
        conn.close()
        return None

    cur.execute("""
        UPDATE referrals
        SET ticket_given = 1
        WHERE referred_id = ?
    """, (referred_id,))
    conn.commit()
    conn.close()

    ticket = add_ticket(referrer_id, "referral")
    return referrer_id, ticket


def save_payment(user_id, amount, payload, telegram_payment_charge_id):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO payments (user_id, amount, payload, telegram_payment_charge_id, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, amount, payload, telegram_payment_charge_id, now()))
    conn.commit()
    conn.close()


def get_stats():
    conn = db_connect()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM users")
    users_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM users WHERE is_registered = 1")
    registered_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM tickets")
    tickets_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM referrals WHERE ticket_given = 1")
    referrals_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM payments")
    payments_count = cur.fetchone()[0]

    conn.close()

    return users_count, registered_count, tickets_count, referrals_count, payments_count


# =========================
# КЛАВИАТУРЫ
# =========================

def main_menu_keyboard():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("Бабкин", url=BABKIN_URL),
        InlineKeyboardButton("Платинум Моторс", url=PLATINUM_URL),
        InlineKeyboardButton("Повысить шансы в конкурсе", callback_data="increase_chances")
    )
    return kb


def subscribe_keyboard():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("Подписаться на Бабкина", url=BABKIN_URL),
        InlineKeyboardButton("Подписаться на Платинум Моторс", url=PLATINUM_URL),
        InlineKeyboardButton("Я подписался, проверить", callback_data="check_subscribe")
    )
    return kb


def admin_keyboard():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("Статистика", callback_data="admin_stats"),
        InlineKeyboardButton("Выгрузить участников CSV", callback_data="admin_export"),
        InlineKeyboardButton("Выбрать победителя", callback_data="admin_winner")
    )
    return kb


# =========================
# ПРОВЕРКИ
# =========================

async def is_subscribed(user_id):
    channels = [CHANNEL_BABKIN, CHANNEL_PLATINUM]

    for channel in channels:
        try:
            member = await bot.get_chat_member(channel, user_id)

            if member.status in ["left", "kicked"]:
                return False

        except ChatNotFound:
            logging.error(f"Канал не найден: {channel}")
            return False

        except Exception as e:
            logging.error(f"Ошибка проверки подписки {channel}: {e}")
            return False

    return True


def is_admin(user_id):
    return user_id in ADMIN_IDS


async def send_main_menu(chat_id, user_id):
    tickets = get_user_tickets(user_id)

    if tickets:
        tickets_text = "\n".join([f"🎟 <b>{ticket[0]}</b> — {ticket[1]}" for ticket in tickets])
    else:
        tickets_text = "Пока билетов нет"

    text = (
        "🚘 <b>Добро пожаловать в совместный конкурс Платинум Моторс и Бабкина!</b>\n\n"
        "Мы запускаем большой розыгрыш, где у каждого участника есть шанс забрать "
        "<b>бесплатный Ford Focus</b>.\n\n"
        "Чтобы участвовать, оставайтесь подписанными на оба канала до конца конкурса. "
        "Чем больше билетов — тем выше шанс на победу.\n\n"
        f"<b>Ваши билеты:</b>\n{tickets_text}"
    )

    if os.path.exists(IMAGE_PATH):
        await bot.send_photo(
            chat_id=chat_id,
            photo=InputFile(IMAGE_PATH),
            caption=text,
            reply_markup=main_menu_keyboard()
        )
    else:
        await bot.send_message(
            chat_id=chat_id,
            text=text + "\n\n⚠️ Фото не найдено. Положи файл image.jpg рядом с bot.py.",
            reply_markup=main_menu_keyboard()
        )


async def complete_registration(user: types.User, chat_id):
    if not is_user_registered(user.id):
        set_registered(user.id)
        ticket = add_ticket(user.id, "start")

        await bot.send_message(
            chat_id,
            f"✅ Вы зарегистрированы в конкурсе!\n\n"
            f"Ваш билет: 🎟 <b>{ticket}</b>"
        )

        ref_result = give_referrer_ticket_if_needed(user.id)

        if ref_result:
            referrer_id, ref_ticket = ref_result
            try:
                await bot.send_message(
                    referrer_id,
                    "🎉 По вашей реферальной ссылке зарегистрировался новый участник!\n\n"
                    f"Вы получили дополнительный билет: 🎟 <b>{ref_ticket}</b>"
                )
            except Exception:
                pass

    await send_main_menu(chat_id, user.id)


# =========================
# ПОЛЬЗОВАТЕЛЬ
# =========================

@dp.message_handler(commands=["start"])
async def start_handler(message: types.Message):
    args = message.get_args()
    referrer_id = None

    if args.startswith("ref_"):
        try:
            referrer_id = int(args.replace("ref_", ""))
        except ValueError:
            referrer_id = None

    add_or_update_user(message.from_user, referrer_id)

    if await is_subscribed(message.from_user.id):
        await complete_registration(message.from_user, message.chat.id)
    else:
        text = (
            "🚘 <b>Добро пожаловать в конкурс на Ford Focus!</b>\n\n"
            "Чтобы получить билет участника, нужно подписаться на оба канала:\n\n"
            "1️⃣ Бабкин\n"
            "2️⃣ Платинум Моторс\n\n"
            "После подписки нажмите кнопку проверки ниже."
        )

        if os.path.exists(IMAGE_PATH):
            await bot.send_photo(
                chat_id=message.chat.id,
                photo=InputFile(IMAGE_PATH),
                caption=text,
                reply_markup=subscribe_keyboard()
            )
        else:
            await message.answer(text, reply_markup=subscribe_keyboard())


@dp.callback_query_handler(lambda c: c.data == "check_subscribe")
async def check_subscribe_handler(callback: types.CallbackQuery):
    add_or_update_user(callback.from_user)

    if await is_subscribed(callback.from_user.id):
        await callback.answer("Подписка подтверждена!", show_alert=True)
        await complete_registration(callback.from_user, callback.message.chat.id)
    else:
        await callback.answer("Вы ещё не подписались на оба канала.", show_alert=True)


@dp.callback_query_handler(lambda c: c.data == "increase_chances")
async def increase_chances_handler(callback: types.CallbackQuery):
    if not await is_subscribed(callback.from_user.id):
        await callback.answer("Сначала подпишитесь на оба канала.", show_alert=True)
        return

    text = (
        "🔥 <b>Как повысить шансы в конкурсе?</b>\n\n"
        f"⭐ <b>1 способ:</b> купить дополнительный билет за {STARS_PRICE} Telegram Stars.\n\n"
        "👥 <b>2 способ:</b> пригласить друга по своей реферальной ссылке. "
        "Когда друг подпишется на оба канала и зарегистрируется, вы получите ещё один билет.\n\n"
        "Количество дополнительных билетов не ограничено."
    )

    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton(f"Купить билет за {STARS_PRICE} ⭐", callback_data="buy_stars_ticket"),
        InlineKeyboardButton("Получить реферальную ссылку", callback_data="my_ref_link")
    )

    await callback.message.answer(text, reply_markup=kb)
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data == "my_ref_link")
async def my_ref_link_handler(callback: types.CallbackQuery):
    if not await is_subscribed(callback.from_user.id):
        await callback.answer("Сначала подпишитесь на оба канала.", show_alert=True)
        return

    ref_link = f"https://t.me/{BOT_USERNAME}?start=ref_{callback.from_user.id}"

    text = (
        "👥 <b>Ваша реферальная ссылка:</b>\n\n"
        f"{ref_link}\n\n"
        "Отправьте её друзьям. Когда человек перейдёт по ссылке, подпишется на оба канала "
        "и зарегистрируется в конкурсе — вы получите дополнительный билет."
    )

    await callback.message.answer(text)
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data == "buy_stars_ticket")
async def buy_stars_ticket_handler(callback: types.CallbackQuery):
    if not await is_subscribed(callback.from_user.id):
        await callback.answer("Сначала подпишитесь на оба канала.", show_alert=True)
        return

    prices = [
        LabeledPrice(
            label="Дополнительный билет в конкурс",
            amount=STARS_PRICE
        )
    ]

    await bot.send_invoice(
        chat_id=callback.message.chat.id,
        title="Дополнительный билет",
        description="Дополнительный билет для участия в розыгрыше Ford Focus.",
        payload=PAYLOAD_EXTRA_TICKET,
        provider_token="",
        currency="XTR",
        prices=prices,
        start_parameter="extra-ticket"
    )

    await callback.answer()


@dp.pre_checkout_query_handler(lambda query: True)
async def pre_checkout_handler(pre_checkout_query: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


@dp.message_handler(content_types=types.ContentType.SUCCESSFUL_PAYMENT)
async def successful_payment_handler(message: types.Message):
    payment = message.successful_payment

    if payment.invoice_payload != PAYLOAD_EXTRA_TICKET:
        await message.answer("Платёж получен, но payload неизвестен. Напишите администратору.")
        return

    save_payment(
        user_id=message.from_user.id,
        amount=payment.total_amount,
        payload=payment.invoice_payload,
        telegram_payment_charge_id=payment.telegram_payment_charge_id
    )

    ticket = add_ticket(message.from_user.id, "77_stars")

    await message.answer(
        "✅ Оплата прошла успешно!\n\n"
        f"Вы получили дополнительный билет: 🎟 <b>{ticket}</b>"
    )


@dp.message_handler(commands=["tickets"])
async def tickets_handler(message: types.Message):
    tickets = get_user_tickets(message.from_user.id)

    if not tickets:
        await message.answer("У вас пока нет билетов.")
        return

    text = "🎟 <b>Ваши билеты:</b>\n\n"

    for ticket_number, reason, created_at in tickets:
        text += f"• <b>{ticket_number}</b> — {reason} — {created_at}\n"

    await message.answer(text)


# =========================
# АДМИНКА
# =========================

@dp.message_handler(commands=["admin"])
async def admin_handler(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return

    await message.answer("Админ-панель:", reply_markup=admin_keyboard())


@dp.message_handler(commands=["stats"])
async def stats_command(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return

    users_count, registered_count, tickets_count, referrals_count, payments_count = get_stats()

    await message.answer(
        "📊 <b>Статистика конкурса</b>\n\n"
        f"Всего пользователей: <b>{users_count}</b>\n"
        f"Зарегистрировано: <b>{registered_count}</b>\n"
        f"Всего билетов: <b>{tickets_count}</b>\n"
        f"Реферальных билетов: <b>{referrals_count}</b>\n"
        f"Платежей Stars: <b>{payments_count}</b>"
    )


@dp.callback_query_handler(lambda c: c.data == "admin_stats")
async def admin_stats_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    users_count, registered_count, tickets_count, referrals_count, payments_count = get_stats()

    await callback.message.answer(
        "📊 <b>Статистика конкурса</b>\n\n"
        f"Всего пользователей: <b>{users_count}</b>\n"
        f"Зарегистрировано: <b>{registered_count}</b>\n"
        f"Всего билетов: <b>{tickets_count}</b>\n"
        f"Реферальных билетов: <b>{referrals_count}</b>\n"
        f"Платежей Stars: <b>{payments_count}</b>"
    )

    await callback.answer()


@dp.message_handler(commands=["users"])
async def users_command(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return

    await export_users(message.chat.id)


@dp.callback_query_handler(lambda c: c.data == "admin_export")
async def admin_export_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    await export_users(callback.message.chat.id)
    await callback.answer()


async def export_users(chat_id):
    conn = db_connect()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            users.user_id,
            users.username,
            users.first_name,
            users.referrer_id,
            users.is_registered,
            COUNT(tickets.id) as tickets_count
        FROM users
        LEFT JOIN tickets ON users.user_id = tickets.user_id
        GROUP BY users.user_id
        ORDER BY users.created_at ASC
    """)

    rows = cur.fetchall()
    conn.close()

    file_path = os.path.join(BASE_DIR, "users_export.csv")

    with open(file_path, "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow([
            "user_id",
            "username",
            "first_name",
            "referrer_id",
            "is_registered",
            "tickets_count"
        ])
        writer.writerows(rows)

    await bot.send_document(chat_id, InputFile(file_path))


@dp.message_handler(commands=["winner"])
async def winner_command(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return

    await choose_winner(message.chat.id)


@dp.callback_query_handler(lambda c: c.data == "admin_winner")
async def admin_winner_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    await choose_winner(callback.message.chat.id)
    await callback.answer()


async def choose_winner(chat_id):
    conn = db_connect()
    cur = conn.cursor()

    cur.execute("""
        SELECT tickets.ticket_number, users.user_id, users.username, users.first_name
        FROM tickets
        JOIN users ON users.user_id = tickets.user_id
        WHERE users.is_registered = 1
    """)

    tickets = cur.fetchall()
    conn.close()

    if not tickets:
        await bot.send_message(chat_id, "Пока нет билетов для выбора победителя.")
        return

    winner = random.choice(tickets)
    ticket_number, user_id, username, first_name = winner

    username_text = f"@{username}" if username else "username не указан"

    await bot.send_message(
        chat_id,
        "🏆 <b>Победитель выбран!</b>\n\n"
        f"🎟 Билет: <b>{ticket_number}</b>\n"
        f"👤 User ID: <code>{user_id}</code>\n"
        f"📛 Имя: <b>{first_name}</b>\n"
        f"🔗 Username: <b>{username_text}</b>"
    )


# =========================
# ЗАПУСК
# =========================

async def on_startup(_):
    global BOT_USERNAME

    init_db()

    me = await bot.get_me()
    BOT_USERNAME = me.username

    logging.info(f"Bot started: @{BOT_USERNAME}")


if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)