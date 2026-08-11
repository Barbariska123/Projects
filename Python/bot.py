import os
import threading
import time
import json
import sqlite3
import requests
import telebot
from telebot import types

# Класс-ограничитель скорости (Rate Limiter)
class RateLimiter:
    def __init__(self, calls, period):
        """
        :param calls: Максимальное число вызовов за период.
        :param period: Период в секундах.
        """
        self.calls = calls
        self.period = period
        self.lock = threading.Lock()
        self.call_times = []

    def wait(self):
        """
        Если число вызовов за последний период превышено, ждем нужное время.
        """
        with self.lock:
            now = time.time()
            # Удаляем старые вызовы, вышедшие за пределы периода
            while self.call_times and now - self.call_times[0] > self.period:
                self.call_times.pop(0)
            if len(self.call_times) >= self.calls:
                sleep_time = self.period - (now - self.call_times[0])
                time.sleep(sleep_time)
            self.call_times.append(time.time())

# Создаем глобальный ограничитель скорости:
# Например: 1 вызов в секунду (настройте по необходимости)
rate_limiter = RateLimiter(calls=1, period=1)

def limited_post(url, data, files=None, timeout=36000):
    """
    Обёртка для requests.post, которая сначала вызывает ограничитель скорости.
    """
    rate_limiter.wait()
    return requests.post(url, data=data, files=files, timeout=timeout)

# --- Настройки бота и базы данных ---
TOKEN = ""
bot = telebot.TeleBot(TOKEN)
DB_FILE = "lists.db"
WHATSAPP_SERVER_URL = "http://localhost:5000/api/whatsapp"
# Укажите здесь chat_id администратора (замените на реальный ID)
ADMIN_ID = ''  

# --- Инициализация базы данных ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Таблица для сохранённых списков групп
    c.execute('''CREATE TABLE IF NOT EXISTS group_lists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL,
                    list_name TEXT NOT NULL,
                    groups TEXT NOT NULL
                 )''')
    # Таблица для пользователей с ролями (admin или user)
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    chat_id TEXT PRIMARY KEY,
                    role TEXT NOT NULL
                 )''')
    # Таблица для заявок от пользователей со статусом "pending" по умолчанию
    c.execute('''CREATE TABLE IF NOT EXISTS applications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL,
                    application_text TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                 )''')
    conn.commit()
    # Если администратора ещё нет, добавляем его
    c.execute("SELECT 1 FROM users WHERE chat_id = ?", (str(ADMIN_ID),))
    if not c.fetchone():
        c.execute("INSERT INTO users (chat_id, role) VALUES (?, ?)", (str(ADMIN_ID), "admin"))
        conn.commit()
    conn.close()

init_db()

# --- Функции работы с БД ---
def add_list(chat_id, list_name, groups):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO group_lists (chat_id, list_name, groups) VALUES (?, ?, ?)",
              (str(chat_id), list_name, json.dumps(groups)))
    conn.commit()
    conn.close()

def get_lists(chat_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, list_name, groups FROM group_lists WHERE chat_id = ?", (str(chat_id),))
    rows = c.fetchall()
    conn.close()
    lists_out = []
    for row in rows:
        lists_out.append({
            "id": row[0],
            "list_name": row[1],
            "groups": json.loads(row[2])
        })
    return lists_out

def delete_list(chat_id, list_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM group_lists WHERE id = ? AND chat_id = ?", (list_id, str(chat_id)))
    conn.commit()
    conn.close()

def add_user(chat_id, role="user"):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (chat_id, role) VALUES (?, ?)", (str(chat_id), role))
    except sqlite3.IntegrityError:
        pass  # Пользователь уже зарегистрирован
    conn.commit()
    conn.close()

def is_registered(chat_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT role FROM users WHERE chat_id = ?", (str(chat_id),))
    result = c.fetchone()
    conn.close()
    return bool(result)

def add_application(chat_id, application_text):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Status установится автоматически в "pending"
    c.execute("INSERT INTO applications (chat_id, application_text) VALUES (?, ?)",
              (str(chat_id), application_text))
    conn.commit()
    conn.close()

def get_applications():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Возвращаем только заявки со статусом "pending"
    c.execute("SELECT id, chat_id, application_text, submitted_at FROM applications WHERE status='pending'")
    rows = c.fetchall()
    conn.close()
    apps = []
    for row in rows:
        apps.append({
            "id": row[0],
            "chat_id": row[1],
            "application_text": row[2],
            "submitted_at": row[3]
        })
    return apps

def update_application_status(app_id, status):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE applications SET status = ? WHERE id = ?", (status, app_id))
    conn.commit()
    conn.close()

# --- Вспомогательные функции для пагинации ---
def paginate_items(items, page, per_page=10):
    total_pages = (len(items) - 1) // per_page + 1 if items else 1
    start = (page - 1) * per_page
    end = start + per_page
    return items[start:end], total_pages

def build_saved_lists_markup(lists, page=1, per_page=10, mode="select"):
    markup = types.InlineKeyboardMarkup(row_width=1)
    paginated, total_pages = paginate_items(lists, page, per_page)
    for lst in paginated:
        if mode == "select":
            btn = types.InlineKeyboardButton(text=lst["list_name"], callback_data=f"normal_list_{lst['id']}")
        else:
            btn = types.InlineKeyboardButton(text=lst["list_name"], callback_data=f"edit_list_{lst['id']}")
        markup.add(btn)
    nav_buttons = []
    if page > 1:
        nav_buttons.append(types.InlineKeyboardButton("◀️", callback_data=f"saved_lists_page_{page-1}_{mode}"))
    nav_buttons.append(types.InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_buttons.append(types.InlineKeyboardButton("▶️", callback_data=f"saved_lists_page_{page+1}_{mode}"))
    if nav_buttons:
        markup.add(*nav_buttons)
    markup.add(types.InlineKeyboardButton("Главное меню", callback_data="back_main"))
    return markup

def build_paginated_groups_markup(groups, selected, page=1, per_page=10, prefix="list_group_", add_done_button=False):
    markup = types.InlineKeyboardMarkup(row_width=1)
    paginated, total_pages = paginate_items(groups, page, per_page)
    for g in paginated:
        text = g.get("name", "Группа")
        group_id = g.get("id", "")
        if group_id in selected:
            text = "✅ " + text
        btn = types.InlineKeyboardButton(text=text, callback_data=f"{prefix}{group_id}")
        markup.add(btn)
    nav_buttons = []
    if page > 1:
        nav_buttons.append(types.InlineKeyboardButton("◀️", callback_data=f"{prefix}page_{page-1}"))
    nav_buttons.append(types.InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_buttons.append(types.InlineKeyboardButton("▶️", callback_data=f"{prefix}page_{page+1}"))
    if nav_buttons:
        markup.add(*nav_buttons)
    if add_done_button:
        if prefix.startswith("list_group_"):
            done_callback = "list_done"
        elif prefix.startswith("timed_group_"):
            done_callback = "timed_done"
        else:
            done_callback = "done"
        markup.add(types.InlineKeyboardButton("Готово", callback_data=done_callback))
    markup.add(types.InlineKeyboardButton("Главное меню", callback_data="back_main"))
    return markup

def build_applications_markup(apps, page=1, per_page=10):
    markup = types.InlineKeyboardMarkup(row_width=1)
    paginated, total_pages = paginate_items(apps, page, per_page)
    for app in paginated:
        text = f"{app['chat_id']}: {app['application_text'][:20]}..."
        btn_accept = types.InlineKeyboardButton("Принять", callback_data=f"accept_{app['id']}")
        btn_decline = types.InlineKeyboardButton("Отклонить", callback_data=f"decline_{app['id']}")
        markup.add(types.InlineKeyboardButton(text=text, callback_data="noop"))
        markup.add(btn_accept, btn_decline)
    nav_buttons = []
    if page > 1:
        nav_buttons.append(types.InlineKeyboardButton("◀️", callback_data=f"applications_page_{page-1}"))
    nav_buttons.append(types.InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_buttons.append(types.InlineKeyboardButton("▶️", callback_data=f"applications_page_{page+1}"))
    if nav_buttons:
        markup.add(*nav_buttons)
    markup.add(types.InlineKeyboardButton("Главное меню", callback_data="back_main"))
    return markup

# --- Главное меню ---
def build_main_menu(chat_id=None):
    markup = types.InlineKeyboardMarkup(row_width=3)
    # Если пользователь не зарегистрирован (заявка не принята) – только кнопка "Заявка"
    if chat_id and not is_registered(chat_id):
        btn_app = types.InlineKeyboardButton("Заявка", callback_data="apply_request")
        markup.add(btn_app)
        return markup
    # Для зарегистрированных пользователей
    btn_normal = types.InlineKeyboardButton("Рассылка", callback_data="normal_choose_list")
    btn_timed = types.InlineKeyboardButton("Таймер", callback_data="toggle_timed")
    btn_lists = types.InlineKeyboardButton("Списки", callback_data="manage_lists")
    if chat_id is not None and str(chat_id) == ADMIN_ID:
        btn_app = types.InlineKeyboardButton("Заявки", callback_data="view_applications")
    else:
        btn_app = types.InlineKeyboardButton("Заявка", callback_data="apply_request")
    markup.add(btn_normal, btn_timed, btn_lists, btn_app)
    return markup

# --- Пользовательское состояние ---
user_state = {}

# --- Хендлер команды /start ---
@bot.message_handler(commands=['start'])
def handle_start(message):
    chat_id = message.chat.id
    user_state.pop(chat_id, None)  # Сброс состояния
    if not is_registered(chat_id):
        bot.send_message(chat_id, "Привет!\nДля использования бота необходимо подать заявку.\nНажмите кнопку «Заявка» и отправьте её текст.",
                         reply_markup=build_main_menu(chat_id))
    else:
        bot.send_message(chat_id, "Привет! Выберите режим работы:", reply_markup=build_main_menu(chat_id))

@bot.message_handler(commands=['help'])
def handle_help(message):
    bot.send_message(message.chat.id, "Доступные команды:\n/start – главное меню\n/help – помощь")

@bot.callback_query_handler(func=lambda call: call.data == "back_main")
def handle_back_main(call):
    chat_id = call.message.chat.id
    bot.edit_message_text(chat_id=chat_id,
                          message_id=call.message.message_id,
                          text="Главное меню:",
                          reply_markup=build_main_menu(chat_id))
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "noop")
def handle_noop(call):
    bot.answer_callback_query(call.id)

def require_registration(chat_id, call_id=None):
    if not is_registered(chat_id):
        if call_id:
            bot.answer_callback_query(call_id, "Сначала подайте заявку.")
        else:
            bot.send_message(chat_id, "Сначала подайте заявку.")
        return False
    return True

# --- Функция последовательной отправки сообщений с задержкой 5 секунд ---
def send_messages_sequentially(chat_id, groups, message_text, photo_path=None, delay=5):
    successes = []
    errors = []
    for group_id in groups:
        payload = {"chat_id": group_id, "message": message_text}
        files = {}
        if photo_path and os.path.exists(photo_path):
            try:
                files["photo"] = open(photo_path, "rb")
            except Exception as e:
                errors.append(f"Ошибка открытия файла для группы {group_id}: {e}")
                continue
        try:
            resp = limited_post(f"{WHATSAPP_SERVER_URL}/send", data=payload, files=files)
            if resp.status_code == 200:
                successes.append(group_id)
            else:
                errors.append(f"Ошибка в группе {group_id}. Код: {resp.status_code}")
        except Exception as e:
            errors.append(f"Ошибка для группы {group_id}: {e}")
        finally:
            if "photo" in files:
                files["photo"].close()
        # Дополнительная задержка между группами (если нужно)
        time.sleep(delay)
    return successes, errors


# =============================================================================
# Режим "Обычная рассылка" через сохранённые списки
# =============================================================================
@bot.callback_query_handler(func=lambda call: call.data == "normal_choose_list")
def handle_normal_choose_list(call):
    chat_id = call.message.chat.id
    if not require_registration(chat_id, call.id):
        return
    lists_db = get_lists(chat_id)
    if lists_db:
        markup = build_saved_lists_markup(lists_db, page=1, per_page=10, mode="select")
    else:
        bot.send_message(chat_id, "Нет сохранённых списков. Нажмите 'Добавить новый список' для создания.",
                         reply_markup=build_main_menu(chat_id))
        return
    btn_new = types.InlineKeyboardButton("Добавить новый список", callback_data="list_create")
    markup.add(btn_new)
    bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id,
                          text="Выберите список для рассылки:", reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("normal_list_"))
def handle_normal_list_select(call):
    chat_id = call.message.chat.id
    if not require_registration(chat_id, call.id):
        return
    list_id = call.data.split("normal_list_")[1]
    chosen = None
    for lst in get_lists(chat_id):
        if str(lst["id"]) == list_id:
            chosen = lst
            break
    if not chosen:
        bot.answer_callback_query(call.id, "Список не найден.")
        return
    user_state.setdefault(chat_id, {})["normal"] = {"list": chosen, "awaiting_text": True, "message": "", "photo_path": None}
    bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id,
                          text=f"Выбран список: {chosen['list_name']}\nПришлите фото (опционально) и введите текст для рассылки.",
                          reply_markup=build_main_menu(chat_id))
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda msg: (msg.chat.id in user_state and "normal" in user_state[msg.chat.id]
                                         and user_state[msg.chat.id]["normal"].get("awaiting_text", False)
                                         and not msg.text.startswith('/')), content_types=['text'])
def handle_normal_text(msg):
    chat_id = msg.chat.id
    if not require_registration(chat_id):
        return
    user_state[chat_id]["normal"]["message"] = msg.text
    user_state[chat_id]["normal"]["awaiting_text"] = False
    lst = user_state[chat_id]["normal"]["list"]
    groups = lst.get("groups", [])
    if not groups:
        bot.send_message(chat_id, "В выбранном списке нет групп. Возвращаем главное меню.", reply_markup=build_main_menu(chat_id))
        user_state.pop(chat_id, None)
        return
    photo_path = user_state[chat_id]["normal"].get("photo_path")
    
    def send_and_report():
        successes, errors = send_messages_sequentially(chat_id, groups, msg.text, photo_path, delay=5)
        reply = ""
        if successes:
            reply += "Сообщение успешно отправлено в группы: " + ", ".join(successes) + "\n"
        if errors:
            reply += "Ошибки:\n" + "\n".join(errors)
        bot.send_message(chat_id, reply, reply_markup=build_main_menu(chat_id))
        user_state.pop(chat_id, None)
    
    threading.Thread(target=send_and_report, daemon=True).start()

@bot.message_handler(func=lambda msg: (msg.chat.id in user_state and "normal" in user_state[msg.chat.id]
                                         and user_state[msg.chat.id]["normal"].get("awaiting_text", False)
                                         and not msg.text.startswith('/')), content_types=['photo'])
def handle_normal_photo(msg):
    chat_id = msg.chat.id
    if not require_registration(chat_id):
        return
    file_info = bot.get_file(msg.photo[-1].file_id)
    dldir = "downloads"
    os.makedirs(dldir, exist_ok=True)
    path = os.path.join(dldir, f"{msg.photo[-1].file_id}.jpg")
    downloaded_file = bot.download_file(file_info.file_path)
    with open(path, "wb") as f:
        f.write(downloaded_file)
    user_state[chat_id]["normal"]["photo_path"] = path
    bot.send_message(chat_id, "Фото получено для обычной рассылки. Теперь введите текст сообщения.")

# =============================================================================
# Управление списками групп
# =============================================================================
@bot.callback_query_handler(func=lambda call: call.data == "manage_lists")
def handle_manage_lists(call):
    chat_id = call.message.chat.id
    if not require_registration(chat_id, call.id):
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_select = types.InlineKeyboardButton("Выбрать существующий список", callback_data="list_select")
    btn_create = types.InlineKeyboardButton("Добавить новый список", callback_data="list_create")
    btn_edit = types.InlineKeyboardButton("Редактировать", callback_data="list_edit")
    markup.add(btn_select, btn_create, btn_edit)
    bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id,
                          text="Управление списками групп:", reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("saved_lists_page_"))
def handle_saved_lists_page(call):
    chat_id = call.message.chat.id
    if not require_registration(chat_id, call.id):
        return
    parts = call.data.split("_")
    try:
        page = int(parts[2])
        mode = parts[3]
    except Exception as e:
        bot.answer_callback_query(call.id, "Неверные данные пагинации.")
        return
    lists_db = get_lists(chat_id)
    markup = build_saved_lists_markup(lists_db, page=page, per_page=10, mode=mode)
    bot.edit_message_reply_markup(chat_id=chat_id, message_id=call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "list_select")
def handle_list_select(call):
    chat_id = call.message.chat.id
    if not require_registration(chat_id, call.id):
        return
    lists_db = get_lists(chat_id)
    if not lists_db:
        bot.send_message(chat_id, "Нет сохранённых списков. Нажмите 'Добавить новый список' для создания.",
                         reply_markup=build_main_menu(chat_id))
        return
    markup = build_saved_lists_markup(lists_db, page=1, per_page=10, mode="select")
    bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id,
                          text="Выберите список для рассылки:", reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "list_create")
def handle_list_create(call):
    chat_id = call.message.chat.id
    if not require_registration(chat_id, call.id):
        return
    user_state.setdefault(chat_id, {})["list_creation"] = {"awaiting_name": True}
    bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id,
                          text="Введите название нового списка групп:",
                          reply_markup=types.InlineKeyboardMarkup().add(
                              types.InlineKeyboardButton("Главное меню", callback_data="back_main")
                          ))
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda msg: (msg.chat.id in user_state and "list_creation" in user_state[msg.chat.id] 
                                        and user_state[msg.chat.id]["list_creation"].get("awaiting_name", False)
                                        and not msg.text.startswith('/')), content_types=['text'])
def handle_list_name(msg):
    chat_id = msg.chat.id
    if not require_registration(chat_id):
        return
    list_name = msg.text.strip()
    if not list_name:
        bot.send_message(chat_id, "Название не может быть пустым. Введите корректное название:")
        return
    user_state[chat_id]["list_creation"]["list_name"] = list_name
    user_state[chat_id]["list_creation"]["awaiting_name"] = False
    try:
        response = requests.get(f"{WHATSAPP_SERVER_URL}/groups", timeout=36000)
        if response.status_code == 200:
            data = response.json()
            groups = data.get("groups", [])
        else:
            groups = []
    except Exception as e:
        bot.send_message(chat_id, f"Ошибка получения групп: {e}")
        return
    if not groups:
        bot.send_message(chat_id, "Не удалось получить список групп с WhatsApp.")
        return
    user_state[chat_id]["list_creation"]["groups"] = groups
    user_state[chat_id]["list_creation"]["selected"] = []
    markup = build_paginated_groups_markup(groups, [], page=1, per_page=10, prefix="list_group_", add_done_button=True)
    bot.send_message(chat_id, "Выберите группы для нового списка (выбирайте, затем нажмите 'Готово')", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("list_group_") or call.data == "list_done")
def handle_list_group_selection(call):
    chat_id = call.message.chat.id
    if "list_creation" not in user_state.get(chat_id, {}):
        bot.answer_callback_query(call.id, "Сначала создайте новый список.")
        return

    # Если нажата кнопка пагинации, обновляем текущую страницу в состоянии
    if call.data.startswith("list_group_page_"):
        try:
            page = int(call.data.split("list_group_page_")[1])
        except Exception:
            page = 1
        user_state[chat_id]["list_creation"]["current_page"] = page
        groups = user_state[chat_id]["list_creation"]["groups"]
        selected = user_state[chat_id]["list_creation"].get("selected", [])
        markup = build_paginated_groups_markup(groups, selected, page=page, per_page=10, prefix="list_group_", add_done_button=True)
        bot.edit_message_reply_markup(chat_id=chat_id, message_id=call.message.message_id, reply_markup=markup)
        bot.answer_callback_query(call.id)
        return

    # Если нажата кнопка "Готово"
    if call.data == "list_done":
        selected = user_state[chat_id]["list_creation"].get("selected", [])
        if not selected:
            bot.answer_callback_query(call.id, "Ни одна группа не выбрана.")
            return
        list_name = user_state[chat_id]["list_creation"].get("list_name")
        try:
            add_list(chat_id, list_name, selected)
            bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id,
                                  text=f"Список '{list_name}' сохранён.", reply_markup=build_main_menu(chat_id))
        except Exception as e:
            bot.send_message(chat_id, f"Ошибка сохранения списка: {e}")
        user_state.pop(chat_id, None)
        bot.answer_callback_query(call.id)
        return

    # Обработка выбора/отмены выбора конкретной группы
    group_id = call.data.split("list_group_")[1]
    selected = user_state[chat_id]["list_creation"].get("selected", [])
    if group_id in selected:
        selected.remove(group_id)
    else:
        selected.append(group_id)
    user_state[chat_id]["list_creation"]["selected"] = selected
    current_page = user_state[chat_id]["list_creation"].get("current_page", 1)
    groups = user_state[chat_id]["list_creation"]["groups"]
    markup = build_paginated_groups_markup(groups, selected, page=current_page, per_page=10, prefix="list_group_", add_done_button=True)
    bot.edit_message_reply_markup(chat_id=chat_id, message_id=call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

# =============================================================================
# Режим редактирования списков (удаление)
# =============================================================================
@bot.callback_query_handler(func=lambda call: call.data == "list_edit")
def handle_list_edit(call):
    chat_id = call.message.chat.id
    if not require_registration(chat_id, call.id):
        return
    lists_db = get_lists(chat_id)
    if not lists_db:
        bot.send_message(chat_id, "Нет сохранённых списков для редактирования.", reply_markup=build_main_menu(chat_id))
        return
    markup = build_saved_lists_markup(lists_db, page=1, per_page=10, mode="edit")
    bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id,
                          text="Выберите список для удаления:", reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("edit_list_"))
def handle_edit_list(call):
    chat_id = call.message.chat.id
    if not require_registration(chat_id, call.id):
        return
    list_id = call.data.split("edit_list_")[1]
    lists_db = get_lists(chat_id)
    selected_list = next((lst for lst in lists_db if str(lst["id"]) == list_id), None)
    if not selected_list:
        bot.answer_callback_query(call.id, "Список не найден.")
        return
    text = f"Вы уверены, что хотите удалить список '{selected_list['list_name']}'?"
    markup = types.InlineKeyboardMarkup()
    btn_confirm = types.InlineKeyboardButton("Удалить", callback_data=f"confirm_delete_{list_id}")
    btn_cancel = types.InlineKeyboardButton("Главное меню", callback_data="back_main")
    markup.add(btn_confirm, btn_cancel)
    bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id,
                          text=text, reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_delete_"))
def handle_confirm_delete(call):
    chat_id = call.message.chat.id
    if not require_registration(chat_id, call.id):
        return
    list_id = call.data.split("confirm_delete_")[1]
    try:
        delete_list(chat_id, list_id)
        bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id,
                           text="Список удалён.", reply_markup=build_main_menu(chat_id))
    except Exception as e:
        bot.send_message(chat_id, f"Ошибка удаления списка: {e}")
    bot.answer_callback_query(call.id)

# =============================================================================
# Режим "Timed рассылка" (с использованием списка или прямой загрузкой)
# =============================================================================
def build_time_unit_markup():
    markup = types.InlineKeyboardMarkup(row_width=3)
    markup.add(
        types.InlineKeyboardButton("Секунды", callback_data="time_unit_seconds"),
        types.InlineKeyboardButton("Минуты", callback_data="time_unit_minutes"),
        types.InlineKeyboardButton("Часы", callback_data="time_unit_hours")
    )
    markup.add(types.InlineKeyboardButton("Главное меню", callback_data="back_main"))
    return markup

@bot.callback_query_handler(func=lambda call: call.data == "toggle_timed")
def handle_toggle_timed(call):
    chat_id = call.message.chat.id
    if not require_registration(chat_id, call.id):
        return
    if chat_id not in user_state:
        user_state[chat_id] = {}
    if "timed" not in user_state[chat_id]:
        user_state[chat_id]["timed"] = {
            "enabled": False,
            "mode": None,
            "selected": [],
            "photo_path": None
        }
    if user_state[chat_id]["timed"].get("enabled", False):
        user_state[chat_id]["timed"]["enabled"] = False
        bot.edit_message_text(chat_id=chat_id,
                              message_id=call.message.message_id,
                              text="Timed рассылка отключена.",
                              reply_markup=build_main_menu(chat_id))
        bot.answer_callback_query(call.id, "Timed рассылка отключена.")
    else:
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn_list = types.InlineKeyboardButton("Использовать список", callback_data="timed_list_select")
        btn_load = types.InlineKeyboardButton("Загрузить группы", callback_data="timed_load")
        markup.add(btn_list, btn_load)
        markup.add(types.InlineKeyboardButton("Главное меню", callback_data="back_main"))
        bot.edit_message_text(chat_id=chat_id,
                              message_id=call.message.message_id,
                              text="Выберите способ настройки timed рассылки:",
                              reply_markup=markup)
        bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "timed_list_select")
def handle_timed_setup_mode_list(call):
    chat_id = call.message.chat.id
    if not require_registration(chat_id, call.id):
        return
    lists_db = get_lists(chat_id)
    if not lists_db:
        bot.send_message(chat_id, "Нет сохранённых списков. Используйте 'Загрузить группы'.", reply_markup=build_main_menu(chat_id))
        return
    markup = build_saved_lists_markup(lists_db, page=1, per_page=10, mode="select")
    bot.edit_message_text(chat_id=chat_id,
                          message_id=call.message.message_id,
                          text="Выберите список для timed рассылки:",
                          reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "timed_load")
def handle_timed_setup_mode_load(call):
    chat_id = call.message.chat.id
    if not require_registration(chat_id, call.id):
        return
    try:
        response = requests.get(f"{WHATSAPP_SERVER_URL}/groups", timeout=36000)
        if response.status_code == 200:
            data = response.json()
            groups = data.get("groups", [])
        else:
            groups = []
    except Exception as e:
        bot.send_message(chat_id, f"Ошибка получения групп: {e}")
        return
    if not groups:
        bot.send_message(chat_id, "Не удалось получить список групп с WhatsApp.")
        return
    user_state[chat_id]["timed"] = {
        "enabled": False,
        "mode": "direct",
        "groups": groups,
        "selected": [],
        "photo_path": None,
        "unit": None,
        "interval": None,
        "message": "",
        "awaiting_interval": False,
        "awaiting_timed_message": False,
        "job": None
    }
    markup = build_paginated_groups_markup(groups, [], page=1, per_page=10, prefix="timed_group_", add_done_button=True)
    bot.edit_message_text(chat_id=chat_id,
                          message_id=call.message.message_id,
                          text="Выберите группы для timed рассылки:",
                          reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("timed_list_"))
def handle_timed_list_select(call):
    chat_id = call.message.chat.id
    if not require_registration(chat_id, call.id):
        return
    list_id = call.data.split("timed_list_")[1]
    chosen = None
    for lst in get_lists(chat_id):
        if str(lst["id"]) == list_id:
            chosen = lst
            break
    if not chosen:
        bot.answer_callback_query(call.id, "Список не найден.")
        return
    user_state[chat_id]["timed"] = {
        "enabled": False,
        "mode": "list",
        "list": chosen,
        "selected": chosen.get("groups", []),
        "photo_path": None,
        "unit": None,
        "interval": None,
        "message": "",
        "awaiting_interval": False,
        "awaiting_timed_message": True,
        "job": None
    }
    bot.edit_message_text(chat_id=chat_id,
                          message_id=call.message.message_id,
                          text=f"Выбран список: {chosen['list_name']}\nВыберите единицу времени:",
                          reply_markup=build_time_unit_markup())
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("timed_group_") or call.data == "timed_done")
def handle_timed_group_selection(call):
    chat_id = call.message.chat.id
    if not require_registration(chat_id, call.id):
        return
    if call.data.startswith("timed_group_page_"):
        try:
            page = int(call.data.split("timed_group_page_")[1])
        except Exception:
            page = 1
        user_state[chat_id]["timed"]["current_page"] = page
        groups = user_state[chat_id]["timed"].get("groups", [])
        selected = user_state[chat_id]["timed"].get("selected", [])
        markup = build_paginated_groups_markup(groups, selected, page=page, per_page=10, prefix="timed_group_", add_done_button=True)
        bot.edit_message_reply_markup(chat_id=chat_id, message_id=call.message.message_id, reply_markup=markup)
        bot.answer_callback_query(call.id)
        return
    if call.data == "timed_done":
        selected = user_state[chat_id]["timed"].get("selected", [])
        if not selected:
            bot.answer_callback_query(call.id, "Ни одна группа не выбрана.")
            return
        if not user_state[chat_id]["timed"].get("unit"):
            bot.edit_message_text(chat_id=chat_id,
                                  message_id=call.message.message_id,
                                  text="Выберите единицу времени:",
                                  reply_markup=build_time_unit_markup())
        else:
            bot.send_message(chat_id, f"Введите числовое значение интервала в {user_state[chat_id]['timed']['unit']} (например, 2):",
                             reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("Главное меню", callback_data="back_main")))
            user_state[chat_id]["timed"]["awaiting_interval"] = True
        bot.answer_callback_query(call.id)
        return
    # Обработка выбора/отмены выбора конкретной группы
    group_id = call.data.split("timed_group_")[1]
    selected = user_state[chat_id]["timed"].get("selected", [])
    if group_id in selected:
        selected.remove(group_id)
    else:
        selected.append(group_id)
    user_state[chat_id]["timed"]["selected"] = selected
    current_page = user_state[chat_id]["timed"].get("current_page", 1)
    groups = user_state[chat_id]["timed"].get("groups", [])
    markup = build_paginated_groups_markup(groups, selected, page=current_page, per_page=10, prefix="timed_group_", add_done_button=True)
    bot.edit_message_reply_markup(chat_id=chat_id, message_id=call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("time_unit_"))
def handle_time_unit(call):
    chat_id = call.message.chat.id
    if not require_registration(chat_id, call.id):
        return
    if "timed" not in user_state.get(chat_id, {}):
        bot.answer_callback_query(call.id, "Нажмите 'Таймер' сначала.")
        return
    unit = call.data.split("time_unit_")[1]
    user_state[chat_id]["timed"]["unit"] = unit
    bot.answer_callback_query(call.id, f"Выбрана единица: {unit}")
    bot.send_message(chat_id, f"Введите числовое значение интервала в {unit} (например, 2):",
                     reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("Главное меню", callback_data="back_main")))
    user_state[chat_id]["timed"]["awaiting_interval"] = True

@bot.message_handler(
    func=lambda msg: (
        msg.chat.id in user_state and 
        "timed" in user_state[msg.chat.id] and 
        not msg.text.startswith('/') and 
        (user_state[msg.chat.id]["timed"].get("awaiting_interval", False) or 
         user_state[msg.chat.id]["timed"].get("awaiting_timed_message", False))
    ),
    content_types=['text']
)
def handle_timed_text(msg):
    chat_id = msg.chat.id
    if not require_registration(chat_id):
        return
    timed = user_state[chat_id]["timed"]
    if timed.get("awaiting_interval", False):
        try:
            value = float(msg.text)
            unit = timed.get("unit", "seconds")
            if unit == "seconds":
                interval = value
            elif unit == "minutes":
                interval = value * 60
            elif unit == "hours":
                interval = value * 3600
            else:
                interval = value
            timed["interval"] = interval
            timed["awaiting_interval"] = False
            bot.send_message(
                chat_id, 
                "Введите текст сообщения для timed рассылки:",
                reply_markup=types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton("Главное меню", callback_data="back_main")
                )
            )
            timed["awaiting_timed_message"] = True
        except ValueError:
            bot.send_message(chat_id, "Введите корректное числовое значение.")
        return
    if timed.get("awaiting_timed_message", False):
        timed["message"] = msg.text
        timed["awaiting_timed_message"] = False
        timed["enabled"] = True
        bot.send_message(
            chat_id,
            f"Timed рассылка включена. Сообщение будет отправляться каждые {timed['interval']} секунд.\n"
            "Чтобы остановить, нажмите кнопку ниже.",
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("Остановить timed рассылку", callback_data="toggle_timed_off"),
                types.InlineKeyboardButton("Главное меню", callback_data="back_main")
            )
        )
        if "job" not in timed or timed["job"] is None:
            t = threading.Thread(target=timed_broadcast_job, args=(chat_id,))
            t.daemon = True
            timed["job"] = t
            t.start()
        return
    bot.send_message(chat_id, "Введите /start для возврата в главное меню.")


@bot.message_handler(content_types=['photo'])
def handle_photo(msg):
    chat_id = msg.chat.id
    if not require_registration(chat_id):
        return
    if chat_id in user_state:
        if "timed" in user_state[chat_id]:
            file_info = bot.get_file(msg.photo[-1].file_id)
            dldir = "downloads"
            os.makedirs(dldir, exist_ok=True)
            path = os.path.join(dldir, f"{msg.photo[-1].file_id}.jpg")
            with open(path, "wb") as f:
                f.write(bot.download_file(file_info.file_path))
            user_state[chat_id]["timed"]["photo_path"] = path
            bot.send_message(chat_id, "Фото получено для timed рассылки. Теперь введите текст или интервал.")
            return
        if "normal" in user_state[chat_id]:
            file_info = bot.get_file(msg.photo[-1].file_id)
            dldir = "downloads"
            os.makedirs(dldir, exist_ok=True)
            path = os.path.join(dldir, f"{msg.photo[-1].file_id}.jpg")
            with open(path, "wb") as f:
                f.write(bot.download_file(file_info.file_path))
            user_state[chat_id]["normal"]["photo_path"] = path
            bot.send_message(chat_id, "Фото получено для обычной рассылки. Теперь введите текст сообщения.")
            return
    bot.send_message(chat_id, "Сначала выберите режим рассылки, затем отправьте фото.", reply_markup=build_main_menu(chat_id))

# Функция отправки сообщений по группам с задержкой 5 секунд между отправками
def send_messages_sequentially(chat_id, groups, message_text, photo_path=None, delay=5):
    successes = []
    errors = []
    for group_id in groups:
        payload = {"chat_id": group_id, "message": message_text}
        files = {}
        if photo_path and os.path.exists(photo_path):
            try:
                files["photo"] = open(photo_path, "rb")
            except Exception as e:
                errors.append(f"Ошибка открытия файла для группы {group_id}: {e}")
                continue
        try:
            resp = requests.post(f"{WHATSAPP_SERVER_URL}/send", data=payload, files=files, timeout=36000)
            if resp.status_code == 200:
                successes.append(group_id)
            else:
                errors.append(f"Ошибка в группе {group_id}. Код: {resp.status_code}")
        except Exception as e:
            errors.append(f"Ошибка для группы {group_id}: {e}")
        finally:
            if "photo" in files:
                files["photo"].close()
        time.sleep(delay)
    return successes, errors

# =============================================================================
# Изменения для обычной рассылки: последовательная отправка с задержкой
# =============================================================================
@bot.message_handler(func=lambda msg: (
    msg.chat.id in user_state and "normal" in user_state[msg.chat.id] and 
    user_state[msg.chat.id]["normal"].get("awaiting_text", False) and 
    not msg.text.startswith('/')
), content_types=['text'])
def handle_normal_text(msg):
    chat_id = msg.chat.id
    if not require_registration(chat_id):
        return
    user_state[chat_id]["normal"]["message"] = msg.text
    user_state[chat_id]["normal"]["awaiting_text"] = False
    lst = user_state[chat_id]["normal"]["list"]
    groups = lst.get("groups", [])
    if not groups:
        bot.send_message(chat_id, "В выбранном списке нет групп. Возвращаем главное меню.",
                         reply_markup=build_main_menu(chat_id))
        user_state.pop(chat_id, None)
        return
    photo_path = user_state[chat_id]["normal"].get("photo_path")
    
    def send_and_report():
        successes, errors = send_messages_sequentially(chat_id, groups, msg.text, photo_path, delay=5)
        reply = ""
        if successes:
            reply += "Сообщение успешно отправлено в группы: " + ", ".join(successes) + "\n"
        if errors:
            reply += "Ошибки:\n" + "\n".join(errors)
        bot.send_message(chat_id, reply, reply_markup=build_main_menu(chat_id))
        user_state.pop(chat_id, None)
    
    threading.Thread(target=send_and_report, daemon=True).start()

# =============================================================================
# Режим "Timed рассылка" с задержкой 5 секунд между отправками в группы
# =============================================================================
def timed_broadcast_job(chat_id):
    while True:
        if (chat_id not in user_state or 
            "timed" not in user_state[chat_id] or 
            not user_state[chat_id]["timed"].get("enabled", False)):
            break
        timed = user_state[chat_id]["timed"]
        interval = timed.get("interval")
        msg_text = timed.get("message")
        selected = timed.get("selected", [])
        if not interval or not msg_text or not selected:
            break
        for group_id in selected:
            payload = {"chat_id": group_id, "message": msg_text}
            files = {}
            if "photo_path" in timed and timed["photo_path"] and os.path.exists(timed["photo_path"]):
                try:
                    files["photo"] = open(timed["photo_path"], "rb")
                except Exception as e:
                    print(f"Ошибка открытия фото для группы {group_id}: {e}")
                    continue
            try:
                resp = limited_post(f"{WHATSAPP_SERVER_URL}/send", data=payload, files=files)
                if resp.status_code != 200:
                    print(f"Ошибка при отправке в {group_id}. Код: {resp.status_code}")
            except Exception as e:
                print(f"Ошибка отправки в {group_id}: {e}")
            finally:
                if "photo" in files:
                    files["photo"].close()
            time.sleep(5)
        time.sleep(interval)
    print(f"Таймер завершён для {chat_id}")
    bot.send_message(chat_id, "Таймер остановлен.", reply_markup=build_main_menu(chat_id))
    user_state.pop(chat_id, None)




@bot.callback_query_handler(func=lambda call: call.data == "toggle_timed_off")
def handle_toggle_timed_off(call):
    chat_id = call.message.chat.id
    if not require_registration(chat_id, call.id):
        return
    if chat_id in user_state and "timed" in user_state[chat_id]:
        user_state[chat_id]["timed"]["enabled"] = False
        bot.edit_message_text(chat_id=chat_id,
                              message_id=call.message.message_id,
                              text="Timed рассылка остановлена.",
                              reply_markup=build_main_menu(chat_id))
        bot.answer_callback_query(call.id, "Timed рассылка остановлена.")
    else:
        bot.answer_callback_query(call.id, "Timed рассылка ещё не настроена.")

# =============================================================================
# Логика подачи заявки / регистрация пользователей
# =============================================================================
@bot.callback_query_handler(func=lambda call: call.data == "apply_request")
def handle_apply_request(call):
    chat_id = call.message.chat.id
    if is_registered(chat_id):
        bot.answer_callback_query(call.id, "Вы уже зарегистрированы!")
        return
    user_state.setdefault(chat_id, {})["application"] = {"awaiting_text": True}
    bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id,
                          text="Введите текст заявки:",
                          reply_markup=types.InlineKeyboardMarkup().add(
                              types.InlineKeyboardButton("Главное меню", callback_data="back_main")
                          ))
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda msg: (msg.chat.id in user_state and "application" in user_state[msg.chat.id]
                                        and user_state[msg.chat.id]["application"].get("awaiting_text", False)
                                        and not msg.text.startswith('/')), content_types=['text'])
def handle_application_text(msg):
    chat_id = msg.chat.id
    app_text = msg.text.strip()
    if not app_text:
        bot.send_message(chat_id, "Текст заявки не может быть пустым. Введите корректный текст:")
        return
    add_application(chat_id, app_text)  # status по умолчанию "pending"
    user_state.pop(chat_id, None)
    bot.send_message(chat_id, "Ваша заявка отправлена. Ожидайте одобрения. Пока ваша заявка не принята, вы не можете пользоваться ботом.",
                     reply_markup=build_main_menu(chat_id))
    try:
        bot.send_message(ADMIN_ID, f"Новая заявка от {chat_id}:\n{app_text}")
    except Exception as e:
        print("Ошибка уведомления администратора:", e)

# Для администратора – просмотр заявок с возможностью принятия/отклонения
@bot.callback_query_handler(func=lambda call: call.data == "view_applications")
def handle_view_applications(call):
    chat_id = call.message.chat.id
    if str(chat_id) != ADMIN_ID:
        bot.answer_callback_query(call.id, "Доступ запрещён.")
        return
    apps = get_applications()  # только pending заявки
    if not apps:
        bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id,
                              text="Нет заявок.", reply_markup=build_main_menu(chat_id))
        bot.answer_callback_query(call.id)
        return
    markup = build_applications_markup(apps, page=1, per_page=10)
    bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id,
                          text="Список заявок:", reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("applications_page_"))
def handle_applications_page(call):
    chat_id = call.message.chat.id
    if str(chat_id) != ADMIN_ID:
        bot.answer_callback_query(call.id, "Доступ запрещён.")
        return
    try:
        page = int(call.data.split("applications_page_")[1])
    except:
        page = 1
    apps = get_applications()
    markup = build_applications_markup(apps, page=page, per_page=10)
    bot.edit_message_reply_markup(chat_id=chat_id, message_id=call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

# Хендлер для принятия заявки
@bot.callback_query_handler(func=lambda call: call.data.startswith("accept_"))
def handle_accept(call):
    app_id = call.data.split("accept_")[1]
    update_application_status(app_id, "accepted")
    # Извлекаем chat_id заявителя
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT chat_id FROM applications WHERE id = ?", (app_id,))
    row = c.fetchone()
    conn.close()
    if row:
        applicant = row[0]
        add_user(applicant, role="user")
        bot.send_message(applicant, "Ваша заявка принята. Теперь вы можете пользоваться ботом!")
    bot.answer_callback_query(call.id, "Заявка принята.")

# Хендлер для отклонения заявки
@bot.callback_query_handler(func=lambda call: call.data.startswith("decline_"))
def handle_decline(call):
    app_id = call.data.split("decline_")[1]
    update_application_status(app_id, "declined")
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT chat_id FROM applications WHERE id = ?", (app_id,))
    row = c.fetchone()
    conn.close()
    if row:
        applicant = row[0]
        bot.send_message(applicant, "Ваша заявка отклонена. Вы не можете пользоваться ботом.")
    bot.answer_callback_query(call.id, "Заявка отклонена.")

if __name__ == '__main__':
    bot.polling(none_stop=True)
