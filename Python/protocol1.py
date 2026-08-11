# bot.py

import telebot
from telebot import types
import sqlite3
import os
import uuid
import random
import string
import logging

logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------
#                      НАСТРОЙКИ
# ---------------------------------------------------------

TOKEN = "7671471089:AAEb1HopQCfMkIN6HKNaju4RvPtcwI2cIaU"  # <-- ваш токен
MASTER_ADMIN_ID = 6664891663                            # <-- ваш TG user_id
MASTER_ADMIN_PASS = "rЮ!a9*к№уD:b"                        # <-- пароль главного админа

PHOTOS_FOLDER = "photos"
os.makedirs(PHOTOS_FOLDER, exist_ok=True)

conn = sqlite3.connect("bot.db", check_same_thread=False)
bot = telebot.TeleBot(TOKEN, parse_mode='HTML')

# ---------------------------------------------------------
#                   СОЗДАЁМ ТАБЛИЦЫ
# ---------------------------------------------------------
with conn:
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        is_admin INTEGER DEFAULT 0,
        is_approved INTEGER DEFAULT 0,
        user_password TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS requests (
        request_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        status TEXT DEFAULT 'pending',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        age INTEGER,
        height INTEGER,
        weight INTEGER,
        breast_size INTEGER,
        hips INTEGER,
        waist INTEGER,
        services TEXT,
        photo_files TEXT,
        manager_contact TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS user_swipes (
        user_id INTEGER,
        profile_id INTEGER,
        like_value INTEGER,
        PRIMARY KEY(user_id, profile_id)
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS user_favorites (
        user_id INTEGER,
        profile_id INTEGER,
        PRIMARY KEY(user_id, profile_id)
    )
    """)

# ---------------------------------------------------------
#                     FSM-СТАТУСЫ
# ---------------------------------------------------------
user_states = {}

# ---------------------------------------------------------
#                   УТИЛИТЫ (SQL-функции)
# ---------------------------------------------------------

def register_user_if_not_exists(user_id: int):
    with conn:
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))

def user_is_approved(user_id: int) -> bool:
    with conn:
        c = conn.cursor()
        c.execute("SELECT is_approved FROM users WHERE user_id=?", (user_id,))
        row = c.fetchone()
    return bool(row and row[0] == 1)

def user_is_admin(user_id: int) -> bool:
    with conn:
        c = conn.cursor()
        c.execute("SELECT is_admin FROM users WHERE user_id=?", (user_id,))
        row = c.fetchone()
    return bool(row and row[0] == 1)

def set_user_admin(user_id: int, is_admin_flag: bool):
    val = 1 if is_admin_flag else 0
    with conn:
        c = conn.cursor()
        c.execute("UPDATE users SET is_admin=? WHERE user_id=?", (val, user_id))

def set_user_approved(user_id: int, pwd: str):
    with conn:
        c = conn.cursor()
        c.execute("""
        UPDATE users
        SET is_approved=1, user_password=?
        WHERE user_id=?
        """, (pwd, user_id))

def generate_random_pass(length=8):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

def reset_swipes_for_user(user_id: int):
    with conn:
        c = conn.cursor()
        c.execute("DELETE FROM user_swipes WHERE user_id=?", (user_id,))

# ---------- Заявки ----------
def create_request(user_id: int, username: str):
    with conn:
        c = conn.cursor()
        c.execute("SELECT request_id FROM requests WHERE user_id=? AND status='pending'", (user_id,))
        row = c.fetchone()
        if row:
            return False
        c.execute("""
        INSERT INTO requests (user_id, username, status)
        VALUES (?, ?, 'pending')
        """, (user_id, username))
    return True

def get_pending_requests():
    with conn:
        c = conn.cursor()
        c.execute("SELECT request_id, user_id, username, status, created_at FROM requests WHERE status='pending'")
        return c.fetchall()

def update_request_status(req_id: int, status: str):
    with conn:
        c = conn.cursor()
        c.execute("UPDATE requests SET status=? WHERE request_id=?", (status, req_id))

# ---------- Анкеты ----------
def get_profile_data(profile_id: int):
    with conn:
        c = conn.cursor()
        c.execute("SELECT * FROM profiles WHERE id=?", (profile_id,))
        row = c.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "name": row[1],
        "age": row[2],
        "height": row[3],
        "weight": row[4],
        "breast_size": row[5],
        "hips": row[6],
        "waist": row[7],
        "services": row[8],
        "photo_files": row[9].split(",") if row[9] else [],
        "manager_contact": row[10]
    }

def add_swipe(user_id: int, profile_id: int, val: int):
    with conn:
        c = conn.cursor()
        c.execute("""
        INSERT OR REPLACE INTO user_swipes (user_id, profile_id, like_value)
        VALUES (?, ?, ?)
        """, (user_id, profile_id, val))

def add_to_favorites(user_id: int, profile_id: int):
    with conn:
        c = conn.cursor()
        c.execute("""
        INSERT OR IGNORE INTO user_favorites (user_id, profile_id)
        VALUES (?, ?)
        """, (user_id, profile_id))

def get_user_favorites(user_id: int):
    with conn:
        c = conn.cursor()
        c.execute("SELECT profile_id FROM user_favorites WHERE user_id=?", (user_id,))
        rows = c.fetchall()
    return [r[0] for r in rows]

# ---------- Фильтры ----------
def build_sql_filter(fdict: dict):
    conds = []
    params = []

    if fdict.get("name"):
        conds.append("p.name LIKE ?")
        params.append(f"%{fdict['name']}%")
    if fdict.get("services"):
        conds.append("p.services LIKE ?")
        params.append(f"%{fdict['services']}%")

    if fdict.get("age_min"):
        conds.append("p.age >= ?")
        params.append(fdict["age_min"])
    if fdict.get("age_max"):
        conds.append("p.age <= ?")
        params.append(fdict["age_max"])

    if fdict.get("height_min"):
        conds.append("p.height >= ?")
        params.append(fdict["height_min"])
    if fdict.get("height_max"):
        conds.append("p.height <= ?")
        params.append(fdict["height_max"])

    if fdict.get("weight_min"):
        conds.append("p.weight >= ?")
        params.append(fdict["weight_min"])
    if fdict.get("weight_max"):
        conds.append("p.weight <= ?")
        params.append(fdict["weight_max"])

    if fdict.get("breast_min"):
        conds.append("p.breast_size >= ?")
        params.append(fdict["breast_min"])
    if fdict.get("breast_max"):
        conds.append("p.breast_size <= ?")
        params.append(fdict["breast_max"])

    if fdict.get("hips_min"):
        conds.append("p.hips >= ?")
        params.append(fdict["hips_min"])
    if fdict.get("hips_max"):
        conds.append("p.hips <= ?")
        params.append(fdict["hips_max"])

    if fdict.get("waist_min"):
        conds.append("p.waist >= ?")
        params.append(fdict["waist_min"])
    if fdict.get("waist_max"):
        conds.append("p.waist <= ?")
        params.append(fdict["waist_max"])

    if conds:
        return " AND " + " AND ".join(conds), params
    else:
        return "", []

def get_next_profile_id_for_user(user_id: int, fdict=None):
    sql = """
    SELECT p.id
    FROM profiles p
    LEFT JOIN user_swipes s ON (p.id = s.profile_id AND s.user_id=?)
    WHERE s.profile_id IS NULL
    """
    params = [user_id]
    if fdict:
        cs, pr = build_sql_filter(fdict)
        if cs:
            sql += cs
        params += pr
    sql += " ORDER BY p.id ASC LIMIT 1"
    with conn:
        c = conn.cursor()
        c.execute(sql, params)
        row = c.fetchone()
    return row[0] if row else None

# ---------- Показываем анкету ----------
def show_profile(chat_id, profile_id, user_id):
    data = get_profile_data(profile_id)
    if not data:
        bot.send_message(chat_id, "Анкета не найдена.")
        return

    text = (
        f"<b>Анкета #{data['id']}</b>\n"
        f"Имя: {data['name']}\n"
        f"Возраст: {data['age']}\n"
        f"Рост: {data['height']}\n"
        f"Вес: {data['weight']}\n"
        f"Размер груди: {data['breast_size']}\n"
        f"Бёдра: {data['hips']}\n"
        f"Талия: {data['waist']}\n"
        f"Услуги: {data['services']}\n"
    )

    media = []
    for i, fn in enumerate(data["photo_files"]):
        path = os.path.join(PHOTOS_FOLDER, fn)
        if os.path.isfile(path):
            with open(path, 'rb') as f:
                if i == 0:
                    media.append(types.InputMediaPhoto(f.read(), caption=text, parse_mode='HTML'))
                else:
                    media.append(types.InputMediaPhoto(f.read()))
    if media:
        bot.send_media_group(chat_id, media)
    else:
        bot.send_message(chat_id, text)

    kb = types.InlineKeyboardMarkup()
    b_yes = types.InlineKeyboardButton("✅", callback_data=f"like_{profile_id}")
    b_no  = types.InlineKeyboardButton("❌", callback_data=f"dislike_{profile_id}")
    kb.add(b_yes, b_no)
    b_fav = types.InlineKeyboardButton("⭐", callback_data=f"fav_{profile_id}")
    kb.add(b_fav)

    if user_is_admin(user_id):
        b1 = types.InlineKeyboardButton("Редактировать", callback_data=f"edit_{profile_id}")
        b2 = types.InlineKeyboardButton("Удалить", callback_data=f"delete_{profile_id}")
        kb.add(b1, b2)

    bot.send_message(chat_id, "Доступные действия:", reply_markup=kb)

# ---------- Главное меню ----------
def get_main_menu_kb(user_id: int):
    kb = types.InlineKeyboardMarkup()
    if user_is_admin(user_id):
        b_req = types.InlineKeyboardButton("Заявки", callback_data="show_requests")
        b_add = types.InlineKeyboardButton("Добавить анкету", callback_data="add_profile")
        b_src = types.InlineKeyboardButton("Поиск", callback_data="search_menu")
        b_fav = types.InlineKeyboardButton("Избранные", callback_data="show_favorites")
        b_rst = types.InlineKeyboardButton("Сброс выборов", callback_data="reset_swipes")
        b_ext = types.InlineKeyboardButton("Выход", callback_data="exit")
        kb.add(b_req, b_add, b_src, b_fav, b_rst, b_ext)
    else:
        b_src = types.InlineKeyboardButton("Поиск", callback_data="search_menu")
        b_fav = types.InlineKeyboardButton("Избранные", callback_data="show_favorites")
        b_rst = types.InlineKeyboardButton("Сброс выборов", callback_data="reset_swipes")
        b_ext = types.InlineKeyboardButton("Выход", callback_data="exit")
        kb.add(b_src, b_fav, b_rst, b_ext)
    return kb

# ---------- /start ----------
@bot.message_handler(commands=['start'])
def cmd_start(message: types.Message):
    user_id = message.from_user.id
    register_user_if_not_exists(user_id)

    if user_id == MASTER_ADMIN_ID:
        with conn:
            c = conn.cursor()
            c.execute("""
            UPDATE users SET is_admin=1, is_approved=1, user_password=?
            WHERE user_id=?
            """, (MASTER_ADMIN_PASS, user_id))

    with conn:
        c = conn.cursor()
        c.execute("SELECT is_approved, user_password FROM users WHERE user_id=?", (user_id,))
        row = c.fetchone()
    if row:
        approved, upass = row
    else:
        approved, upass = 0, ""

    if not approved:
        text = (
            "Добро пожаловать!\n"
            "Вы не авторизованы.\n"
            "Если у вас есть пароль, введите его сообщением.\n"
            "Если нет – нажмите «Подать заявку»."
        )
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("Подать заявку", callback_data="create_request"))
        bot.send_message(message.chat.id, text, reply_markup=kb)
    else:
        bot.send_message(message.chat.id, "С возвращением! Вы авторизованы.")
        mkb = get_main_menu_kb(user_id)
        bot.send_message(message.chat.id, "Главное меню:", reply_markup=mkb)

# ---------- Обработка текста (пароль / FSM) ----------
@bot.message_handler(func=lambda m: True)
def handle_text_all(message: types.Message):
    user_id = message.from_user.id
    with conn:
        c = conn.cursor()
        c.execute("SELECT is_approved, user_password FROM users WHERE user_id=?", (user_id,))
        row = c.fetchone()
    if not row:
        return
    approved, upass = row
    if approved == 1:
        # уже одобрен => FSM
        if user_id in user_states:
            handle_fsm_text(message)
        return
    else:
        # Пароль
        attempt = message.text.strip()
        if attempt == upass and upass != "":
            with conn:
                c = conn.cursor()
                c.execute("UPDATE users SET is_approved=1 WHERE user_id=?", (user_id,))
            bot.send_message(message.chat.id, "Пароль верный! Вы авторизованы.")
            mkb = get_main_menu_kb(user_id)
            bot.send_message(message.chat.id, "Главное меню:", reply_markup=mkb)
        else:
            bot.send_message(message.chat.id, "Неверный пароль. Или нажмите «Подать заявку».")

# ---------- FSM-текст (добавление анкеты и т.п.) ----------
def handle_fsm_text(message: types.Message):
    user_id = message.from_user.id
    st = user_states[user_id]
    action = st.get("action")

    if action == "add_profile_step":
        step = st.get("step", 0)
        data = st.setdefault("profile_data", {})
        if step == 0:
            data["name"] = message.text
            st["step"] = 1
            bot.send_message(message.chat.id, "Введите возраст (число):")
        elif step == 1:
            if not message.text.isdigit():
                bot.send_message(message.chat.id, "Возраст – число, повторите:")
                return
            data["age"] = int(message.text)
            st["step"] = 2
            bot.send_message(message.chat.id, "Введите рост (число):")
        elif step == 2:
            if not message.text.isdigit():
                bot.send_message(message.chat.id, "Рост – число, повторите:")
                return
            data["height"] = int(message.text)
            st["step"] = 3
            bot.send_message(message.chat.id, "Введите вес (число):")
        elif step == 3:
            if not message.text.isdigit():
                bot.send_message(message.chat.id, "Вес – число, повторите:")
                return
            data["weight"] = int(message.text)
            st["step"] = 4
            bot.send_message(message.chat.id, "Введите размер груди (число):")
        elif step == 4:
            if not message.text.isdigit():
                bot.send_message(message.chat.id, "Грудь – число, повторите:")
                return
            data["breast_size"] = int(message.text)
            st["step"] = 5
            bot.send_message(message.chat.id, "Введите обхват бёдер (число):")
        elif step == 5:
            if not message.text.isdigit():
                bot.send_message(message.chat.id, "Бёдра – число, повторите:")
                return
            data["hips"] = int(message.text)
            st["step"] = 6
            bot.send_message(message.chat.id, "Введите обхват талии (число):")
        elif step == 6:
            if not message.text.isdigit():
                bot.send_message(message.chat.id, "Талия – число, повторите:")
                return
            data["waist"] = int(message.text)
            st["step"] = 7
            bot.send_message(message.chat.id, "Опишите услуги:")
        elif step == 7:
            data["services"] = message.text
            st["step"] = 8
            bot.send_message(message.chat.id, "Введите контакт менеджера (текст):")
        elif step == 8:
            data["manager_contact"] = message.text
            st["step"] = 9
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("Загрузить фото", callback_data="add_photos_now"))
            kb.add(types.InlineKeyboardButton("Пропустить", callback_data="skip_photos_add"))
            bot.send_message(message.chat.id, "Добавить фото к анкете?", reply_markup=kb)

    elif action == "edit_field":
        p_id = st["profile_id"]
        field = st["field"]
        val = message.text.strip()
        numeric_fields = ["age","height","weight","breast_size","hips","waist"]
        if field in numeric_fields:
            if not val.isdigit():
                bot.send_message(message.chat.id, "Нужно число. Повторите:")
                return
            val = int(val)
        with conn:
            c = conn.cursor()
            c.execute(f"UPDATE profiles SET {field}=? WHERE id=?", (val, p_id))
        bot.send_message(message.chat.id, f"Поле {field} обновлено у анкеты #{p_id}!")
        user_states.pop(user_id, None)

    elif action == "filter_checklist":
        f_in_edit = st.get("field_in_edit")
        if not f_in_edit:
            return
        txt = message.text.strip()
        if txt == "":
            st["filters"][f_in_edit] = None
        else:
            if f_in_edit in ["name","services"]:
                st["filters"][f_in_edit] = txt
            else:
                if not txt.isdigit():
                    bot.send_message(message.chat.id, "Ошибка: нужно число или пустая строка.")
                    return
                st["filters"][f_in_edit] = int(txt)
        st["field_in_edit"] = None
        show_filter_checklist(message.chat.id, st["filters"], editing_done=True)

def show_filter_checklist(chat_id: int, fdict: dict, editing_done=False) -> None:
    def mark(v):
        return " (✓)" if v else ""

    txt = (
        "Текущие фильтры:\n"
        f"Имя{mark(fdict.get('name'))}: {fdict.get('name')}\n"
        f"Услуги{mark(fdict.get('services'))}: {fdict.get('services')}\n"
        f"Возраст: {fdict.get('age_min')}{mark(fdict.get('age_min'))} - {fdict.get('age_max')}{mark(fdict.get('age_max'))}\n"
        f"Рост: {fdict.get('height_min')}{mark(fdict.get('height_min'))} - {fdict.get('height_max')}{mark(fdict.get('height_max'))}\n"
        f"Вес: {fdict.get('weight_min')}{mark(fdict.get('weight_min'))} - {fdict.get('weight_max')}{mark(fdict.get('weight_max'))}\n"
        f"Грудь: {fdict.get('breast_min')}{mark(fdict.get('breast_min'))} - {fdict.get('breast_max')}{mark(fdict.get('breast_max'))}\n"
        f"Бёдра: {fdict.get('hips_min')}{mark(fdict.get('hips_min'))} - {fdict.get('hips_max')}{mark(fdict.get('hips_max'))}\n"
        f"Талия: {fdict.get('waist_min')}{mark(fdict.get('waist_min'))} - {fdict.get('waist_max')}{mark(fdict.get('waist_max'))}\n"
    )
    if editing_done:
        txt += "\nИзменения сохранены."

    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(f"Имя{mark(fdict.get('name'))}", callback_data="editfilter_name"),
        types.InlineKeyboardButton(f"Услуги{mark(fdict.get('services'))}", callback_data="editfilter_services")
    )
    kb.add(
        types.InlineKeyboardButton(f"Мин. возраст{mark(fdict.get('age_min'))}", callback_data="editfilter_age_min"),
        types.InlineKeyboardButton(f"Макс. возраст{mark(fdict.get('age_max'))}", callback_data="editfilter_age_max")
    )
    kb.add(
        types.InlineKeyboardButton(f"Мин. рост{mark(fdict.get('height_min'))}", callback_data="editfilter_height_min"),
        types.InlineKeyboardButton(f"Макс. рост{mark(fdict.get('height_max'))}", callback_data="editfilter_height_max")
    )
    kb.add(
        types.InlineKeyboardButton(f"Мин. вес{mark(fdict.get('weight_min'))}", callback_data="editfilter_weight_min"),
        types.InlineKeyboardButton(f"Макс. вес{mark(fdict.get('weight_max'))}", callback_data="editfilter_weight_max")
    )
    kb.add(
        types.InlineKeyboardButton(f"Мин. грудь{mark(fdict.get('breast_min'))}", callback_data="editfilter_breast_min"),
        types.InlineKeyboardButton(f"Макс. грудь{mark(fdict.get('breast_max'))}", callback_data="editfilter_breast_max")
    )
    kb.add(
        types.InlineKeyboardButton(f"Мин. бёдра{mark(fdict.get('hips_min'))}", callback_data="editfilter_hips_min"),
        types.InlineKeyboardButton(f"Макс. бёдра{mark(fdict.get('hips_max'))}", callback_data="editfilter_hips_max")
    )
    kb.add(
        types.InlineKeyboardButton(f"Мин. талия{mark(fdict.get('waist_min'))}", callback_data="editfilter_waist_min"),
        types.InlineKeyboardButton(f"Макс. талия{mark(fdict.get('waist_max'))}", callback_data="editfilter_waist_max")
    )
    kb.add(types.InlineKeyboardButton("Сбросить всё", callback_data="filter_reset"))
    kb.add(types.InlineKeyboardButton("Подтвердить", callback_data="filter_confirm"))
    kb.add(types.InlineKeyboardButton("Назад", callback_data="back_to_search_menu"))

    bot.send_message(chat_id, txt, reply_markup=kb)

# ------------------ Приём фото (медиагруппа) ------------------
@bot.message_handler(content_types=['photo'], func=lambda m: 'media_group_id' in m.json)
def handle_media_group(msg: types.Message):
    user_id = msg.from_user.id
    if user_id not in user_states:
        return
    st = user_states[user_id]
    if st.get("action") != "add_photos_now":
        return

    file_info = bot.get_file(msg.photo[-1].file_id)
    downloaded = bot.download_file(file_info.file_path)
    fn = f"{uuid.uuid4()}.jpg"
    with open(os.path.join(PHOTOS_FOLDER, fn), 'wb') as f:
        f.write(downloaded)
    ph_list = st.setdefault("photo_files", [])
    if len(ph_list) < 5:
        ph_list.append(fn)

# ------------------ Приём одиночного фото ------------------
@bot.message_handler(content_types=['photo'], func=lambda m: 'media_group_id' not in m.json)
def handle_single_photo(msg: types.Message):
    user_id = msg.from_user.id
    if user_id not in user_states:
        return
    st = user_states[user_id]
    if st.get("action") != "add_photos_now":
        return

    file_info = bot.get_file(msg.photo[-1].file_id)
    downloaded = bot.download_file(file_info.file_path)
    fn = f"{uuid.uuid4()}.jpg"
    with open(os.path.join(PHOTOS_FOLDER, fn), 'wb') as f:
        f.write(downloaded)
    ph_list = st.setdefault("photo_files", [])
    if len(ph_list) < 5:
        ph_list.append(fn)

# ------------------ CALLBACK ------------------
@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call: types.CallbackQuery):
    user_id = call.from_user.id

    # Если не одобрен и не главный админ, разрешаем только create_request
    if not user_is_approved(user_id) and user_id != MASTER_ADMIN_ID:
        if call.data != "create_request":
            bot.answer_callback_query(call.id, "Вы не авторизованы!", show_alert=True)
            return

    if call.data == "exit":
        if user_id in user_states:
            user_states.pop(user_id)
        bot.send_message(call.message.chat.id, "Вы вышли из меню. Наберите /start при необходимости.")
        bot.answer_callback_query(call.id)
        return

    if call.data == "create_request":
        uname = call.from_user.username or f"User_{user_id}"
        ok = create_request(user_id, uname)
        if not ok:
            bot.send_message(call.message.chat.id, "У вас уже есть заявка в ожидании.")
        else:
            bot.send_message(call.message.chat.id, "Заявка создана! Ждите решения админа.")
        bot.answer_callback_query(call.id)

    elif call.data == "show_requests":
        if not user_is_admin(user_id):
            bot.answer_callback_query(call.id, "Нет доступа!", show_alert=True)
            return
        reqs = get_pending_requests()
        if not reqs:
            bot.send_message(call.message.chat.id, "Нет заявок в ожидании.")
        else:
            for (req_id, uid, uname, status, ctime) in reqs:
                text = f"Заявка #{req_id} от {uname} (ID={uid})\nСтатус: {status}\nСоздана: {ctime}"
                kb = types.InlineKeyboardMarkup()
                b1 = types.InlineKeyboardButton("Принять", callback_data=f"req_approve_{req_id}_{uid}")
                b2 = types.InlineKeyboardButton("Отклонить", callback_data=f"req_deny_{req_id}_{uid}")
                kb.add(b1, b2)
                bot.send_message(call.message.chat.id, text, reply_markup=kb)
        bot.answer_callback_query(call.id)

    elif call.data.startswith("req_approve_") or call.data.startswith("req_deny_"):
        if not user_is_admin(user_id):
            bot.answer_callback_query(call.id, "Нет доступа!", show_alert=True)
            return
        parts = call.data.split("_")
        action = parts[1]
        req_id = int(parts[2])
        tgt_uid = int(parts[3])

        if action == "approve":
            update_request_status(req_id, "approved")
            new_pass = generate_random_pass()
            kb = types.InlineKeyboardMarkup()
            kb.add(
                types.InlineKeyboardButton("Сделать админом", callback_data=f"make_admin_{tgt_uid}_{new_pass}"),
                types.InlineKeyboardButton("Сделать пользователем", callback_data=f"make_user_{tgt_uid}_{new_pass}")
            )
            bot.send_message(call.message.chat.id, f"Заявка #{req_id} принята. Пароль: {new_pass}\nВыберите роль:", reply_markup=kb)
        else:
            update_request_status(req_id, "denied")
            with conn:
                c = conn.cursor()
                c.execute("UPDATE users SET is_approved=0, user_password='' WHERE user_id=?", (tgt_uid,))
            bot.send_message(call.message.chat.id, f"Заявка #{req_id} от {tgt_uid} отклонена.")
        bot.answer_callback_query(call.id)

    elif call.data.startswith("make_admin_") or call.data.startswith("make_user_"):
        parts = call.data.split("_")
        role_prefix = parts[0] + "_" + parts[1]  # "make_admin" / "make_user"
        tgt_uid = int(parts[2])
        assigned_pass = parts[3]

        if not user_is_admin(user_id):
            bot.answer_callback_query(call.id, "Нет доступа!", show_alert=True)
            return

        if role_prefix == "make_admin":
            set_user_admin(tgt_uid, True)
            roletxt = "админ"
        else:
            set_user_admin(tgt_uid, False)
            roletxt = "пользователь"

        set_user_approved(tgt_uid, assigned_pass)
        bot.send_message(call.message.chat.id,
                         f"Пользователь {tgt_uid} теперь {roletxt}, пароль={assigned_pass}")
        try:
            bot.send_message(tgt_uid,
                             f"Ваша заявка одобрена!\nПароль: {assigned_pass}\nВведите /start.")
        except:
            pass
        bot.answer_callback_query(call.id)

    elif call.data == "search_menu":
        kb = types.InlineKeyboardMarkup()
        b1 = types.InlineKeyboardButton("Общий поиск", callback_data="search_all")
        b2 = types.InlineKeyboardButton("Поиск по фильтрам", callback_data="search_filter")
        b3 = types.InlineKeyboardButton("Назад", callback_data="back_to_main_menu")
        kb.add(b1, b2, b3)
        bot.send_message(call.message.chat.id, "Выберите тип поиска:", reply_markup=kb)
        bot.answer_callback_query(call.id)

    elif call.data == "search_all":
        nxt = get_next_profile_id_for_user(user_id, None)
        if not nxt:
            bot.send_message(call.message.chat.id, "Анкет больше нет.")
            # [Изменено] Переход в главное меню
            mkb = get_main_menu_kb(user_id)
            bot.send_message(call.message.chat.id, "Главное меню:", reply_markup=mkb)
        else:
            show_profile(call.message.chat.id, nxt, user_id)
        bot.answer_callback_query(call.id)

    elif call.data == "search_filter":
        user_states[user_id] = {
            "action": "filter_checklist",
            "filters": {
                "name":None,"services":None,
                "age_min":None,"age_max":None,
                "height_min":None,"height_max":None,
                "weight_min":None,"weight_max":None,
                "breast_min":None,"breast_max":None,
                "hips_min":None,"hips_max":None,
                "waist_min":None,"waist_max":None
            }
        }
        show_filter_checklist(call.message.chat.id, user_states[user_id]["filters"])
        bot.answer_callback_query(call.id)

    elif call.data == "back_to_main_menu":
        mkb = get_main_menu_kb(user_id)
        bot.send_message(call.message.chat.id, "Главное меню:", reply_markup=mkb)
        bot.answer_callback_query(call.id)

    elif call.data == "reset_swipes":
        reset_swipes_for_user(user_id)
        bot.send_message(call.message.chat.id, "Ваши лайки/дизлайки сброшены.")
        bot.answer_callback_query(call.id)





    elif call.data.startswith("show_favorites") or call.data.startswith("fav_page_"):
        favs = get_user_favorites(user_id)
        if not favs:
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("Главное меню", callback_data="back_to_main_menu"))
            try:
                bot.edit_message_text(
                    "У вас нет избранных анкет.",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=kb
                )
            except Exception:
                bot.send_message(call.message.chat.id, "У вас нет избранных анкет.", reply_markup=kb)
        else:
            CONFIG_ITEMS_PER_PAGE = 1
            items_per_page = CONFIG_ITEMS_PER_PAGE
            total_pages = max(1, (len(favs) + items_per_page - 1) // items_per_page)

            # Определение текущей страницы
            try:
                if call.data.startswith("fav_page_"):
                    page = int(call.data.split("_")[2])
                else:
                    page = 1
            except (IndexError, ValueError):
                page = 1
                logging.warning(f"Некорректные данные в call.data: {call.data}")

            # Ограничиваем номер страницы
            page = max(1, min(page, total_pages))

            # Получаем профили для текущей страницы
            start_idx = (page - 1) * items_per_page
            end_idx = start_idx + items_per_page
            current_profiles = favs[start_idx:end_idx]

            for profile_id in current_profiles:
                data = get_profile_data(profile_id)
                if not data:
                    bot.send_message(call.message.chat.id, "Анкета не найдена. Это будет сообщено администратору.")
                    logging.warning(f"Profile ID {profile_id} not found for user {user_id}")
                    continue

                # Текст анкеты
                text = (
                    f"<b>Анкета #{data['id']}</b>\n"
                    f"Имя: {data['name']}\n"
                    f"Возраст: {data['age']}\n"
                    f"Рост: {data['height']}\n"
                    f"Вес: {data['weight']}\n"
                    f"Размер груди: {data['breast_size']}\n"
                    f"Бёдра: {data['hips']}\n"
                    f"Талия: {data['waist']}\n"
                    f"Услуги: {data['services']}\n"
                    f"Менеджер: {data['manager_contact']}\n"
                )

                # Клавиатура
                kb = types.InlineKeyboardMarkup()
                if page > 1:
                    kb.add(types.InlineKeyboardButton("⬅️ Назад", callback_data=f"fav_page_{page - 1}"))
                else:
                    kb.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="noop"))

                kb.add(types.InlineKeyboardButton(f"Страница {page}/{total_pages}", callback_data="noop"))

                if page < total_pages:
                    next_page = page + 1
                    kb.add(types.InlineKeyboardButton("Вперёд ➡️", callback_data=f"fav_page_{next_page}"))
                else:
                    kb.add(types.InlineKeyboardButton("Вперёд ➡️", callback_data="noop"))

                if len(data["photo_files"]) > 1:
                    kb.add(types.InlineKeyboardButton("Показать все фото", callback_data=f"show_all_photos_{profile_id}"))

                kb.add(types.InlineKeyboardButton("Главное меню", callback_data="back_to_main_menu"))

                # Отправляем обновленное сообщение с текстом и первой фотографией
                photo_file = data["photo_files"][0] if data["photo_files"] else None
                if photo_file:
                    photo_path = os.path.join(PHOTOS_FOLDER, photo_file)
                    if os.path.isfile(photo_path):
                        with open(photo_path, 'rb') as photo:
                            try:
                                bot.edit_message_media(
                                    media=types.InputMediaPhoto(photo.read(), caption=text, parse_mode='HTML'),
                                    chat_id=call.message.chat.id,
                                    message_id=call.message.message_id,
                                    reply_markup=kb
                                )
                            except Exception:
                                bot.send_photo(
                                    chat_id=call.message.chat.id,
                                    photo=photo.read(),
                                    caption=text,
                                    parse_mode='HTML',
                                    reply_markup=kb
                                )
                else:
                    try:
                        bot.edit_message_text(
                            text=text,
                            chat_id=call.message.chat.id,
                            message_id=call.message.message_id,
                            reply_markup=kb
                        )
                    except Exception:
                        bot.send_message(call.message.chat.id, text, parse_mode='HTML', reply_markup=kb)

            bot.answer_callback_query(call.id)

 
 
    elif call.data.startswith("show_all_photos_"):
        try:
            # Извлекаем последний элемент после разделения по '_'
            parts = call.data.split("_")
            profile_id_str = parts[-1]
            if not profile_id_str.isdigit():
                raise ValueError(f"Некорректный формат ID профиля: {profile_id_str}")
            profile_id = int(profile_id_str)
        except (IndexError, ValueError) as e:
            logging.error(f"Некорректный формат данных: {call.data}, ошибка: {e}")
            bot.answer_callback_query(call.id, "Ошибка: некорректный запрос.")
            return

        # Получаем данные профиля
        data = get_profile_data(profile_id)
        if not data:
            bot.send_message(call.message.chat.id, "Анкета не найдена.")
            return

        # Формируем медиагруппу
        media_group = []
        text = (
            f"<b>Анкета #{data['id']}</b>\n"
            f"Имя: {data['name']}\n"
            f"Возраст: {data['age']}\n"
            f"Рост: {data['height']}\n"
            f"Вес: {data['weight']}\n"
            f"Размер груди: {data['breast_size']}\n"
            f"Бёдра: {data['hips']}\n"
            f"Талия: {data['waist']}\n"
            f"Услуги: {data['services']}\n"
            f"Менеджер: {data['manager_contact']}\n"
        )
        for i, photo_file in enumerate(data["photo_files"]):
            photo_path = os.path.join(PHOTOS_FOLDER, photo_file)
            if os.path.isfile(photo_path):
                with open(photo_path, 'rb') as photo:
                    if i == 0:
                        media_group.append(types.InputMediaPhoto(photo.read(), caption=text, parse_mode='HTML'))
                    else:
                        media_group.append(types.InputMediaPhoto(photo.read()))

        # Отправляем медиагруппу или текст
        if media_group:
            bot.send_media_group(call.message.chat.id, media_group)
        else:
            bot.send_message(call.message.chat.id, text, parse_mode='HTML')

        bot.answer_callback_query(call.id)










    










    elif call.data.startswith("fav_page_"):
        try:
            # Разделяем call.data и пытаемся получить номер страницы
            page_str = call.data.split("_")[2]
            page = int(page_str)
        except (IndexError, ValueError):
            # В случае ошибки задаем номер страницы по умолчанию
            page = 1
            logging.warning(f"Некорректные данные в call.data: {call.data}")
    elif call.data == "noop":
        bot.answer_callback_query(call.id)  # Подтверждение без действия








    elif call.data.startswith("favopen_"):
        pid = int(call.data.split("_")[1])
        show_profile(call.message.chat.id, pid, user_id)
        bot.answer_callback_query(call.id)

    elif call.data == "exit":
        if user_id in user_states:
            user_states.pop(user_id)
        bot.send_message(call.message.chat.id, "Вы вышли. Для возвращения /start.")
        bot.answer_callback_query(call.id)

    # --- Фильтры: filter_reset / filter_confirm / editfilter_... ---
    elif call.data in ["filter_reset","filter_confirm"] or call.data.startswith("editfilter_"):
        st = user_states.get(user_id)
        if not st or st.get("action") != "filter_checklist":
            bot.answer_callback_query(call.id)
            return

        if call.data == "filter_reset":
            st["filters"] = {
                "name":None,"services":None,
                "age_min":None,"age_max":None,
                "height_min":None,"height_max":None,
                "weight_min":None,"weight_max":None,
                "breast_min":None,"breast_max":None,
                "hips_min":None,"hips_max":None,
                "waist_min":None,"waist_max":None
            }
            show_filter_checklist(call.message.chat.id, st["filters"])
            bot.answer_callback_query(call.id)

        elif call.data == "filter_confirm":
            fdict = st["filters"]
            nxt = get_next_profile_id_for_user(user_id, fdict)
            if not nxt:
                bot.send_message(call.message.chat.id, "Нет анкет под такие фильтры.")
                # [Изменено] Переход в главное меню
                mkb = get_main_menu_kb(user_id)
                bot.send_message(call.message.chat.id, "Главное меню:", reply_markup=mkb)
            else:
                show_profile(call.message.chat.id, nxt, user_id)
            user_states.pop(user_id, None)
            bot.answer_callback_query(call.id)

        elif call.data.startswith("editfilter_"):
            field = call.data.split("_",1)[1]
            st["field_in_edit"] = field
            if field in ["name","services"]:
                bot.send_message(call.message.chat.id, f"Введите текст (или пусто) для поля «{field}»:")
            else:
                bot.send_message(call.message.chat.id, f"Введите число (или пусто) для поля «{field}»:")
            bot.answer_callback_query(call.id)

    elif call.data == "add_profile":
        if not user_is_admin(user_id):
            bot.answer_callback_query(call.id, "Нет доступа!", show_alert=True)
            return
        user_states[user_id] = {
            "action": "add_profile_step",
            "step": 0
        }
        bot.send_message(call.message.chat.id, "Введите имя:")
        bot.answer_callback_query(call.id)

    elif call.data in ["add_photos_now","skip_photos_add","finish_photos_add"]:
        st = user_states.get(user_id)
        if not st:
            bot.answer_callback_query(call.id)
            return
        action = st.get("action")

        if call.data == "add_photos_now":
            if action != "add_profile_step":
                bot.answer_callback_query(call.id)
                return
            user_states[user_id] = {
                "action": "add_photos_now",
                "profile_data": st["profile_data"],
                "photo_files": []
            }
            bot.send_message(call.message.chat.id,
                             "Отправьте до 5 фото (медиагруппа или по одной). Затем нажмите «Завершить».")
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("Завершить", callback_data="finish_photos_add"))
            bot.send_message(call.message.chat.id, "Когда закончите, нажмите:", reply_markup=kb)
            bot.answer_callback_query(call.id)

        elif call.data == "skip_photos_add":
            if action != "add_profile_step":
                bot.answer_callback_query(call.id)
                return
            data = st["profile_data"]
            with conn:
                c = conn.cursor()
                c.execute("""
                INSERT INTO profiles (name, age, height, weight, breast_size, hips, waist, services, photo_files, manager_contact)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """, (
                    data["name"], data["age"], data["height"], data["weight"],
                    data["breast_size"], data["hips"], data["waist"],
                    data["services"], "", data["manager_contact"]
                ))
                new_id = c.lastrowid
            bot.send_message(call.message.chat.id, f"Анкета #{new_id} добавлена без фото!")
            user_states.pop(user_id, None)
            bot.answer_callback_query(call.id)

            # [Изменено] Сразу в главное меню
            mkb = get_main_menu_kb(user_id)
            bot.send_message(call.message.chat.id, "Главное меню:", reply_markup=mkb)

        elif call.data == "finish_photos_add":
            if action != "add_photos_now":
                bot.answer_callback_query(call.id)
                return
            data = st["profile_data"]
            photos = st["photo_files"][:5]
            files_str = ",".join(photos)
            with conn:
                c = conn.cursor()
                c.execute("""
                INSERT INTO profiles (name, age, height, weight, breast_size, hips, waist, services, photo_files, manager_contact)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """, (
                    data["name"], data["age"], data["height"], data["weight"],
                    data["breast_size"], data["hips"], data["waist"],
                    data["services"], files_str, data["manager_contact"]
                ))
                new_id = c.lastrowid
            bot.send_message(call.message.chat.id,
                             f"Фотографии добавлены. Анкета #{new_id} создана!")
            user_states.pop(user_id, None)
            bot.answer_callback_query(call.id)

            # [Изменено] Сразу в главное меню
            mkb = get_main_menu_kb(user_id)
            bot.send_message(call.message.chat.id, "Главное меню:", reply_markup=mkb)


    elif call.data.startswith("like_"):
        pid = int(call.data.split("_")[1])
        add_swipe(user_id, pid, 1)
        prof = get_profile_data(pid)
        contact = prof["manager_contact"] if prof and prof["manager_contact"] else "Контакт менеджера не указан."
        bot.send_message(call.message.chat.id, f"Спасибо за выбор! Контакт менеджера: {contact}")
        nxt = get_next_profile_id_for_user(user_id)
        if not nxt:
            bot.send_message(call.message.chat.id, "Больше нет анкет.")
            # [Изменено] Переход в главное меню
            mkb = get_main_menu_kb(user_id)
            bot.send_message(call.message.chat.id, "Главное меню:", reply_markup=mkb)
        else:
            show_profile(call.message.chat.id, nxt, user_id)
        bot.answer_callback_query(call.id)

    elif call.data.startswith("dislike_"):
        pid = int(call.data.split("_")[1])
        add_swipe(user_id, pid, 0)
        bot.send_message(call.message.chat.id, "Анкета пропущена.")
        nxt = get_next_profile_id_for_user(user_id)
        if not nxt:
            bot.send_message(call.message.chat.id, "Больше нет анкет.")
            # [Изменено] Переход в главное меню
            mkb = get_main_menu_kb(user_id)
            bot.send_message(call.message.chat.id, "Главное меню:", reply_markup=mkb)
        else:
            show_profile(call.message.chat.id, nxt, user_id)
        bot.answer_callback_query(call.id)

    elif call.data.startswith("fav_"):
        pid = int(call.data.split("_")[1])
        add_to_favorites(user_id, pid)
        add_swipe(user_id, pid, 0)
        bot.send_message(call.message.chat.id,
                         f"Анкета #{pid} добавлена в избранное и пропущена в общем поиске.")
        nxt = get_next_profile_id_for_user(user_id)
        if not nxt:
            bot.send_message(call.message.chat.id, "Больше нет анкет.")
            # [Изменено] Переход в главное меню
            mkb = get_main_menu_kb(user_id)
            bot.send_message(call.message.chat.id, "Главное меню:", reply_markup=mkb)
        else:
            show_profile(call.message.chat.id, nxt, user_id)
        bot.answer_callback_query(call.id)

    elif call.data.startswith("edit_"):
        if not user_is_admin(user_id):
            bot.answer_callback_query(call.id, "Нет доступа!", show_alert=True)
            return
        p_id = int(call.data.split("_")[1])
        kb = types.InlineKeyboardMarkup()
        fields = [
            ("Имя","name"), ("Возраст","age"), ("Рост","height"),
            ("Вес","weight"), ("Грудь","breast_size"), ("Бёдра","hips"),
            ("Талия","waist"), ("Услуги","services"), ("Контакт менеджера","manager_contact")
        ]
        for (title, fld) in fields:
            kb.add(types.InlineKeyboardButton(title, callback_data=f"editfield_{p_id}_{fld}"))
        bot.send_message(call.message.chat.id, f"Что редактируем в анкете #{p_id}?", reply_markup=kb)
        bot.answer_callback_query(call.id)

    elif call.data.startswith("delete_"):
        if not user_is_admin(user_id):
            bot.answer_callback_query(call.id, "Нет доступа!", show_alert=True)
            return
        p_id = int(call.data.split("_")[1])
        with conn:
            c = conn.cursor()
            c.execute("DELETE FROM profiles WHERE id=?", (p_id,))
        bot.send_message(call.message.chat.id, f"Анкета #{p_id} удалена.")
        bot.answer_callback_query(call.id)

    elif call.data.startswith("editfield_"):
        if not user_is_admin(user_id):
            bot.answer_callback_query(call.id, "Нет доступа!", show_alert=True)
            return
        _, p_id, fld = call.data.split("_")
        p_id = int(p_id)
        user_states[user_id] = {
            "action": "edit_field",
            "profile_id": p_id,
            "field": fld
        }
        bot.send_message(call.message.chat.id, f"Введите новое значение для поля «{fld}»:")
        bot.answer_callback_query(call.id)

    else:
        bot.answer_callback_query(call.id)

# ------------------ ЗАПУСК БОТА ------------------
if __name__ == '__main__':
    bot.infinity_polling()
