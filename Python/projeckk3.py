import sqlite3
from datetime import datetime
import hashlib
import telebot
import random
import string
import re
import os
import threading

# Инициализация бота
bot = telebot.TeleBot("7941964715:AAFGR8V0W9qF0o8LF576iEyJSVdwazDs13M")

# Параметры для главного и младшего администратора
MAIN_ADMIN_TELEGRAM_ID = '6664891663'
MAIN_ADMIN_PASSWORD = 'rЮ!a9*к№уD:b'

JUNIOR_ADMIN_TELEGRAM_ID = '8068244167'
JUNIOR_ADMIN_PASSWORD = '!pW&ix^;1^|Q'

def get_db_connection():
    try:
        # Укажите абсолютный путь к базе данных
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'MegaBASE.db')
        print(f"Путь к базе данных: {db_path}")
        conn = sqlite3.connect(db_path, check_same_thread=False)
        print("Подключение к базе данных успешно.")
        return conn
    except sqlite3.Error as e:
        print(f"Ошибка подключения к БД: {e}")
        return None
# Глобальная структура для временного хранения данных
session_data = {}

def initialize_session(chat_id):
    """
    Полная инициализация данных сессии для указанного chat_id.
    Если сессия уже существует, данные обновляются/дополняются.
    """
    global session_data

    # Структура для сессии
    default_session = {
        "characteristics": set(),  # Характеристики анкеты
        "profile_type": None,      # Тип анкеты
        "user_info": {             # Информация о пользователе
            "phone": None,         # Номер телефона
            "telegram_id": None    # Telegram ID
        },
        "comment": None            # Комментарий к анкете
    }

    # Инициализация или дополнение текущей сессии
    if chat_id not in session_data or not isinstance(session_data.get(chat_id), dict):
        session_data[chat_id] = default_session
    else:
        # Обновляем ключи, которые могли отсутствовать
        for key, value in default_session.items():
            if key not in session_data[chat_id]:
                session_data[chat_id][key] = value
            elif isinstance(value, dict):  # Обновляем вложенные словари
                for sub_key, sub_value in value.items():
                    if sub_key not in session_data[chat_id][key]:
                        session_data[chat_id][key][sub_key] = sub_value

    print(f"Сессия инициализирована или обновлена для chat_id {chat_id}: {session_data[chat_id]}")


def normalize_phone(phone):
    """
    Приводит номер телефона к стандартному формату +7XXXXXXXXXX.
    Удаляет пробелы, скобки, тире и другие лишние символы.
    """
    try:
        # Удаляем все символы, кроме цифр
        phone = re.sub(r"[^\d]", "", phone)

        # Проверяем длину номера
        if len(phone) == 11 and phone.startswith("8"):
            phone = "+7" + phone[1:]  # Заменяем 8 на +7
        elif len(phone) == 11 and phone.startswith("7"):
            phone = "+7" + phone[1:]  # Добавляем +7, если номер начинается с 7
        elif len(phone) == 10:  # Если только 10 цифр
            phone = "+7" + phone
        elif len(phone) == 12 and phone.startswith("7"):  # Если 12 цифр и начинается с 7
            phone = "+" + phone
        elif len(phone) == 12 and phone.startswith("+7"):  # Если уже в формате +7
            return phone
        else:
            # Если номер не соответствует стандартным форматам
            raise ValueError("Некорректный формат номера телефона.")

        return phone
    except Exception as e:
        print(f"Ошибка нормализации номера телефона: {e}")
        raise ValueError("Некорректный формат номера телефона.")


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def init_db():
    """
    Инициализация базы данных: создание таблиц и добавление администраторов.
    """
    try:
        conn = get_db_connection()
        if not conn:
            raise ConnectionError("Не удалось подключиться к базе данных.")

        with conn:
            cursor = conn.cursor()

            # Создание таблицы пользователей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id TEXT UNIQUE,
                    phone TEXT,
                    role TEXT,
                    status TEXT,
                    password TEXT,
                    search_count INTEGER DEFAULT 0,
                    date_added TEXT
                )
            ''')

            # Создание таблицы анкет
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    user_info TEXT,
                    type TEXT,
                    characteristic TEXT,
                    comment TEXT,
                    date_added TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')

            # Создание таблицы истории поиска
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS search_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    search_text TEXT,
                    date_searched TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS requests (
                    request_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER UNIQUE,
                    username TEXT,
                    is_approved INTEGER DEFAULT 0,  -- 0 = не одобрено, 1 = одобрено
                    role TEXT DEFAULT 'user',       -- 'user' или 'младший админ'
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            print("Таблицы успешно созданы или уже существуют.")

            # Добавление администраторов
            add_admin(cursor, MAIN_ADMIN_TELEGRAM_ID, "794991817", "главный админ", MAIN_ADMIN_PASSWORD)
            add_admin(cursor, JUNIOR_ADMIN_TELEGRAM_ID, "8068244167", "младший админ", JUNIOR_ADMIN_PASSWORD)

            # Проверка таблицы users
            cursor.execute("SELECT * FROM users")
            all_users = cursor.fetchall()
            print("Список всех пользователей в таблице users:", all_users)

    except sqlite3.Error as e:
        print(f"Ошибка при инициализации базы данных: {e}")
    finally:
        if conn:
            conn.close()
            print("Соединение с базой данных закрыто.")


def add_admin(cursor, telegram_id, phone, role, password):
    """
    Добавляет администратора в таблицу пользователей, если он ещё не существует.
    """
    try:
        cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        admin = cursor.fetchone()
        if not admin:
            cursor.execute('''
                INSERT INTO users (telegram_id, phone, role, status, password, date_added)
                VALUES (?, ?, ?, 'одобрено', ?, ?)
            ''', (telegram_id, phone, role, hash_password(password), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            print(f"{role.capitalize()} {telegram_id} добавлен.")
        else:
            print(f"{role.capitalize()} с Telegram ID {telegram_id} уже существует.")
    except sqlite3.Error as e:
        print(f"Ошибка при добавлении {role}: {e}")

# Запуск инициализации базы данных
init_db()
def update_db_schema():
    """
    Обновление структуры базы данных: добавление поля search_count, если его нет.
    """
    try:
        conn = get_db_connection()
        if not conn:
            raise ConnectionError("Не удалось подключиться к базе данных.")

        with conn:
            cursor = conn.cursor()

            # Проверяем, существует ли поле search_count в таблице profiles
            cursor.execute("PRAGMA table_info(profiles)")
            columns = [col[1] for col in cursor.fetchall()]
            if "search_count" not in columns:
                cursor.execute("""
                    ALTER TABLE profiles ADD COLUMN search_count INTEGER DEFAULT 0
                """)
                print("Поле search_count добавлено в таблицу profiles.")
            else:
                print("Поле search_count уже существует.")
    except sqlite3.Error as e:
        print(f"Ошибка обновления структуры базы данных: {e}")
    finally:
        if conn:
            conn.close()


# Вызов функции обновления базы данных
update_db_schema()

# Вызываем обновление схемы
update_db_schema()

# Временное хранение данных сессии
# Обработчик выбора роли из кнопок
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    username = message.from_user.username or f"User_{user_id}"

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Проверяем, есть ли пользователь в таблице users
        cursor.execute("SELECT role FROM users WHERE telegram_id = ?", (str(user_id),))
        row = cursor.fetchone()

        if row:
            role = row[0]
            if role in ["главный админ", "младший админ"]:
                bot.send_message(message.chat.id, f"Добро пожаловать, {role}!")
                main_menu(message)  # Если админ, сразу в главное меню
                return

        # Если не админ, проверяем заявку в requests
        cursor.execute("SELECT is_approved FROM requests WHERE user_id=?", (user_id,))
        row = cursor.fetchone()

        if row:
            is_approved = row[0]
            if is_approved == 1:
                bot.send_message(message.chat.id, "Вы уже авторизованы!")
                return
            else:
                bot.send_message(message.chat.id, "Ваша заявка на рассмотрении.")
                return

        # Если заявки нет, создаём новую
        cursor.execute("INSERT INTO requests (user_id, username) VALUES (?, ?)", (user_id, username))
        conn.commit()
        bot.send_message(message.chat.id, "Ваша заявка подана! Ожидайте решения администратора.")




def verify_password(message):
    """
    Проверяет пароль пользователя.
    """
    entered_password = message.text.strip()
    telegram_id = str(message.from_user.id)

    if telegram_id == MAIN_ADMIN_TELEGRAM_ID and entered_password == MAIN_ADMIN_PASSWORD:
        bot.send_message(message.chat.id, "Добро пожаловать, главный администратор!")
        main_menu(message)
    elif telegram_id == JUNIOR_ADMIN_TELEGRAM_ID and entered_password == JUNIOR_ADMIN_PASSWORD:
        bot.send_message(message.chat.id, "Добро пожаловать, младший администратор!")
        main_menu(message)
    else:
        bot.send_message(message.chat.id, "Неверный пароль. Попробуйте снова:")
        bot.register_next_step_handler(message, verify_password)


def verify_junior_admin_password(message):
    """Проверка пароля младшего администратора."""
    if hash_password(message.text.strip()) == hash_password(JUNIOR_ADMIN_PASSWORD):
        bot.send_message(message.chat.id, "Пароль верный. Добро пожаловать, младший администратор!")
        main_menu(message)
    else:
        bot.send_message(message.chat.id, "Неверный пароль. Попробуйте снова.")
        bot.register_next_step_handler(message, verify_junior_admin_password)

def verify_user_password(message):
    telegram_id = str(message.from_user.id)
    input_password = message.text.strip()
    hashed_input_password = hash_password(input_password)

    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT password FROM users WHERE telegram_id = ?", (telegram_id,))
            user = cursor.fetchone()
            if user and user[0] == hashed_input_password:
                bot.send_message(message.chat.id, "Пароль верный. Добро пожаловать!")
                main_menu(message)
            else:
                bot.send_message(message.chat.id, "Неверный пароль. Попробуйте снова.")
                bot.register_next_step_handler(message, verify_user_password)
        except Exception as e:
            print(f"Ошибка при проверке пароля пользователя: {e}")
            bot.send_message(message.chat.id, "Произошла ошибка при проверке пароля. Попробуйте позже.")
        finally:
            conn.close()

# Основное меню
def main_menu(message):
    """
    Главное меню с учетом уникальных пользователей,
    где Telegram ID и номер телефона считаются как одно.
    """
    conn = get_db_connection()
    empty_profiles_count = 0
    unique_users_count = 0

    if conn:
        try:
            cursor = conn.cursor()
            
            # Получаем роль пользователя
            cursor.execute("SELECT role FROM users WHERE telegram_id = ?", (str(message.from_user.id),))
            row = cursor.fetchone()
            role = row[0] if row else "user"  # Если нет роли, считаем обычным пользователем

            # Подсчет числа пустых анкет
            cursor.execute("""
                SELECT COUNT(*)
                FROM profiles
                WHERE (characteristic IS NULL OR characteristic = '')
                  AND (comment IS NULL OR comment = '')
            """)
            empty_profiles_count = cursor.fetchone()[0] or 0

            # Подсчет уникальных пользователей
            cursor.execute("""
                SELECT COUNT(DISTINCT COALESCE(NULLIF(telegram_id, ''), NULLIF(phone, '')))
                FROM users
                WHERE (telegram_id IS NOT NULL AND telegram_id != '')
                   OR (phone IS NOT NULL AND phone != '')
            """)
            unique_users_count = cursor.fetchone()[0] or 0

        except Exception as e:
            print(f"Ошибка подсчета данных: {e}")
        finally:
            conn.close()

    message_text = (
        f"Главное меню:\n"
        f"Общее число анкет: {unique_users_count}\n"
        f"Число пустых анкет: {empty_profiles_count}\n"
        "Выберите действие:"
    )

    # Создаем Inline-кнопки
    inline_markup = telebot.types.InlineKeyboardMarkup()
    inline_markup.add(
        telebot.types.InlineKeyboardButton("Поиск", callback_data="поиск"),
        telebot.types.InlineKeyboardButton("Добавить", callback_data="Добавить"),
    )
    inline_markup.add(
        telebot.types.InlineKeyboardButton("Главное меню", callback_data="Главное меню"),
        telebot.types.InlineKeyboardButton("Выход", callback_data="exit")
    )

    # Показываем кнопку "Просмотр заявок" только если пользователь админ
    if role in ["главный админ", "мл. админ"]:  # Проверь, как точно записана роль в БД!
        inline_markup.add(
            telebot.types.InlineKeyboardButton("Просмотр заявок", callback_data="просмотр_заявок")
        )

    bot.send_message(message.chat.id, message_text, reply_markup=inline_markup)

    if empty_profiles_count > 0:
        # Inline-кнопка для показа незаполненных анкет
        unfilled_markup = telebot.types.InlineKeyboardMarkup()
        unfilled_markup.add(
            telebot.types.InlineKeyboardButton(
                f"Показать незаполненные ({empty_profiles_count})",
                callback_data="show_unfilled_profiles"
            )
        )
        bot.send_message(
            message.chat.id,
            "Вы также можете показать незаполненные анкеты:",
            reply_markup=unfilled_markup
        )

@bot.callback_query_handler(func=lambda call: call.data == "просмотр_заявок")
def show_requests_callback(call):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT request_id, user_id, username FROM requests WHERE is_approved = 0")
        requests = cursor.fetchall()

        if not requests:
            bot.send_message(call.message.chat.id, "Нет заявок в ожидании.")
            return

        for req_id, user_id, username in requests:
            markup = telebot.types.InlineKeyboardMarkup()
            markup.add(
                telebot.types.InlineKeyboardButton("✅ Одобрить (пользователь)", callback_data=f"approve_user_{req_id}_{user_id}"),
                telebot.types.InlineKeyboardButton("🛠 Одобрить (мл. админ)", callback_data=f"approve_admin_{req_id}_{user_id}"),
                telebot.types.InlineKeyboardButton("❌ Отклонить", callback_data=f"deny_{req_id}_{user_id}")
            )
            bot.send_message(call.message.chat.id, f"🔹 Заявка #{req_id} от @{username} (ID: {user_id})", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("approve_user_") or call.data.startswith("approve_admin_") or call.data.startswith("deny_"))
def process_request(call):
    try:
        print(f"Получен callback_data: {call.data}")  # Лог для отладки

        parts = call.data.split("_")
        if len(parts) < 4:
            bot.send_message(call.message.chat.id, "⚠ Ошибка: некорректный формат данных. Попробуйте снова.")
            return

        action = f"{parts[0]}_{parts[1]}"  # approve_user / approve_admin / deny
        req_id = int(parts[2])  # ID заявки
        user_id = int(parts[3])  # ID пользователя

        new_status = 1 if "approve" in action else 0
        new_role = "user" if action == "approve_user" else "младший администратор"

        with get_db_connection() as conn:
            cursor = conn.cursor()

            if "deny" in action:
                cursor.execute("DELETE FROM requests WHERE request_id=?", (req_id,))
                bot.send_message(call.message.chat.id, f"❌ Заявка #{req_id} отклонена.")
            else:
                cursor.execute("UPDATE requests SET is_approved=?, role=? WHERE request_id=?", (new_status, new_role, req_id))
                cursor.execute("INSERT OR REPLACE INTO users (telegram_id, role, status) VALUES (?, ?, 'одобрено')",
                               (str(user_id), new_role))  
                bot.send_message(call.message.chat.id, f"✅ Заявка #{req_id} одобрена! Назначена роль: {new_role}")

                try:
                    bot.send_message(user_id, f"🎉 Ваша заявка одобрена! Ваша роль: {new_role}.")
                    main_menu(user_id)  # Вызываем правильную функцию
                except:
                    print(f"⚠ Не удалось отправить сообщение пользователю {user_id}")

            conn.commit()
    except Exception as e:
        print(f"Ошибка в process_request: {e}")
        bot.send_message(call.message.chat.id, "⚠ Ошибка обработки заявки. Попробуйте снова.")





@bot.callback_query_handler(func=lambda call: call.data in ["поиск", "Добавить", "Главное меню", "Выход"])
def handle_main_menu_buttons(call):
    """
    Обрабатывает нажатия кнопок в главном меню.
    """
    if call.data == "поиск":
        # Переход к поиску
        bot.send_message(call.message.chat.id, "Вы выбрали поиск.")
        search_request(call.message)

    elif call.data == "Добавить":
        # Переход к добавлению данных
        bot.send_message(call.message.chat.id, "Вы выбрали добавление данных.")
        add_information(call.message)

    elif call.data == "Главное меню":
        # Перезапуск главного меню
        bot.send_message(call.message.chat.id, "Возвращаемся в главное меню.")
        main_menu(call.message)

    elif call.data == "Выход":
        # Выход из бота
        bot.send_message(call.message.chat.id, "Вы вышли из бота. До свидания!")
        clear_session(call.message.chat.id)

@bot.message_handler(func=lambda message: message.text == "Главное меню")
def return_to_main_menu(message):
    """
    Обработчик кнопки "Главное меню".
    Возвращает пользователя в главное меню.
    """
    bot.send_message(message.chat.id, "Вы возвращены в главное меню.")
    main_menu(message)



@bot.callback_query_handler(func=lambda call: call.data == "show_unfilled_profiles")
def show_unfilled_profiles(call):
    """
    Показывает следующую незаполненную анкету.
    """
    try:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT p.id, u.telegram_id, u.phone
                FROM profiles p
                LEFT JOIN users u ON p.user_id = u.id
                WHERE (p.characteristic IS NULL OR p.characteristic = '')
                  AND (p.comment IS NULL OR p.comment = '')
                LIMIT 1
            """)
            profile = cursor.fetchone()

            conn.close()

            if profile:
                profile_id, telegram_id, phone = profile
                profile_text = (
                    f"Незаполненная анкета:\n"
                    f"Telegram ID: {telegram_id or 'Не указан'}\n"
                    f"Телефон: {phone or 'Не указан'}\n\n"
                    "Выберите действие:"
                )
                markup = telebot.types.InlineKeyboardMarkup()
                markup.add(
                    telebot.types.InlineKeyboardButton("Пропустить", callback_data=f"skip_profile_{profile_id}"),
                    telebot.types.InlineKeyboardButton("Редактировать", callback_data=f"edit_profile_{profile_id}")
                )
                # Обновляем сообщение
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=profile_text,
                    reply_markup=markup
                )
            else:
                # Если анкеты закончились, обновляем сообщение и возвращаем в главное меню
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="Все анкеты обработаны. Возвращаемся в главное меню."
                )
                main_menu(call.message)
    except Exception as e:
        print(f"Ошибка отображения незаполненных анкет: {e}")
        bot.send_message(call.message.chat.id, "Произошла ошибка при обработке анкеты.")



@bot.callback_query_handler(func=lambda call: call.data.startswith("edit_profile_"))
def edit_profile(call):
    """
    Редактирование пустой анкеты.
    """
    profile_id = int(call.data.split("_")[2])
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT u.telegram_id, u.phone
                FROM profiles p
                LEFT JOIN users u ON p.user_id = u.id
                WHERE p.id = ?
            """, (profile_id,))
            profile = cursor.fetchone()

            if profile:
                telegram_id, phone = profile
                session_data[call.message.chat.id] = {
                    "profile_id": profile_id,
                    "user_info": {"telegram_id": telegram_id, "phone": phone},
                    "profile_type": None,
                    "characteristics": set(),
                    "comment": None
                }
                bot.send_message(
                    call.message.chat.id,
                    f"Редактирование анкеты:\nTelegram ID: {telegram_id or 'Не указан'}\n"
                    f"Телефон: {phone or 'Не указан'}\n\nВведите новые данные:"
                )
                add_information(call.message)
            else:
                bot.send_message(call.message.chat.id, "Анкета не найдена.")
                show_unfilled_profiles(call.message)
        except Exception as e:
            print(f"Ошибка редактирования анкеты: {e}")
            bot.send_message(call.message.chat.id, "Произошла ошибка при редактировании анкеты.")
        finally:
            conn.close()


@bot.callback_query_handler(func=lambda call: call.data.startswith("skip_profile_"))
def skip_profile(call):
    """
    Обновляет отображение незаполненных анкет, пропуская текущую анкету.
    """
    try:
        profile_id = int(call.data.split("_")[2])

        # Удаляем сообщение текущей анкеты
        bot.delete_message(call.message.chat.id, call.message.message_id)

        # Проверяем, есть ли ещё незаполненные анкеты
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()

            # Получаем следующую незаполненную анкету
            cursor.execute("""
                SELECT p.id, u.telegram_id, u.phone
                FROM profiles p
                LEFT JOIN users u ON p.user_id = u.id
                WHERE (p.characteristic IS NULL OR p.characteristic = '')
                  AND (p.comment IS NULL OR p.comment = '')
                  AND p.id != ?
                LIMIT 1
            """, (profile_id,))
            next_profile = cursor.fetchone()

            conn.close()

            if next_profile:
                # Если есть следующая анкета, обновляем сообщение
                next_profile_id, telegram_id, phone = next_profile
                profile_text = (
                    f"Незаполненная анкета:\n"
                    f"Telegram ID: {telegram_id or 'Не указан'}\n"
                    f"Телефон: {phone or 'Не указан'}\n\n"
                    "Выберите действие:"
                )
                markup = telebot.types.InlineKeyboardMarkup()
                markup.add(
                    telebot.types.InlineKeyboardButton("Пропустить", callback_data=f"skip_profile_{next_profile_id}"),
                    telebot.types.InlineKeyboardButton("Редактировать", callback_data=f"edit_profile_{next_profile_id}")
                )
                bot.send_message(call.message.chat.id, profile_text, reply_markup=markup)
            else:
                # Если анкеты закончились, обновляем текущее сообщение
                bot.send_message(call.message.chat.id, "Все анкеты обработаны.")
                main_menu(call.message)
    except Exception as e:
        print(f"Ошибка в обработке пропуска анкеты: {e}")
        bot.send_message(call.message.chat.id, "Произошла ошибка при обработке анкеты.")






@bot.message_handler(func=lambda message: message.text == "Пропустить")
def skip_unfilled_profiles(message):
    """
    Пропускает этап с незаполненными анкетами и возвращает в главное меню.
    """
    bot.send_message(message.chat.id, "Вы пропустили этап с незаполненными анкетами.")
    main_menu(message)
def check_unfilled_profiles():
    """
    Проверяет количество незаполненных анкет и возвращает их список.
    """
    conn = get_db_connection()
    unfilled_profiles = []
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT u.telegram_id, u.phone
                FROM users u
                LEFT JOIN profiles p ON u.id = p.user_id
                WHERE (p.characteristic IS NULL OR p.characteristic = '') OR (p.comment IS NULL OR p.comment = '')
            """)
            unfilled_profiles = cursor.fetchall()
        except Exception as e:
            print(f"Ошибка при проверке незаполненных анкет: {e}")
        finally:
            conn.close()
    return unfilled_profiles

# Обработчик кнопки "Добавить"
@bot.message_handler(func=lambda message: message.text == "Добавить")
def add_information(message):
    """
    Начало процесса добавления анкеты.
    """
    initialize_session(message.chat.id)
    bot.send_message(
        message.chat.id,
        "Введите Telegram ID и/или номер телефона для добавления информации.\n"
        "Пример ввода:\n"
        "- Telegram ID: 123456789\n"
        "- Номер телефона: +79998887766\n"
        "Или оба через пробел: 123456789 +79998887766"
    )
    bot.register_next_step_handler(message, process_user_info)


def validate_input(input_text):
    """
    Валидирует и нормализует ввод Telegram ID и номера телефона.
    """
    try:
        inputs = input_text.split()
        telegram_id, phone = None, None

        for value in inputs:
            # Проверяем Telegram ID (9-12 цифр)
            if value.isdigit() and 9 <= len(value) <= 12:
                telegram_id = value
            # Проверяем номер телефона (+7XXXXXXXXXX)
            elif re.match(r"^\+7\d{10}$", value):
                phone = value
            # Приводим номер телефона в формате "8XXXXXXXXXX" к "+7XXXXXXXXXX"
            elif re.match(r"^8\d{10}$", value):
                phone = "+7" + value[1:]

        return telegram_id, phone
    except Exception as e:
        print(f"Ошибка валидации входных данных: {e}")
        raise ValueError("Ошибка: введены некорректные данные. Укажите Telegram ID и/или номер телефона.")


def process_user_info(message):
    """
    Обрабатывает ввод Telegram ID и/или номера телефона при добавлении анкеты.
    """
    try:
        user_info = message.text.strip()
        if not user_info:
            raise ValueError("Ошибка: данные пользователя не указаны.")

        # Валидируем и нормализуем ввод
        telegram_id, phone = validate_input(user_info)

        if not telegram_id and not phone:
            raise ValueError("Ошибка: введите корректный Telegram ID и/или номер телефона.")

        # Подключение к базе данных
        conn = get_db_connection()
        if not conn:
            raise ConnectionError("Не удалось подключиться к базе данных.")

        cursor = conn.cursor()

        # Проверяем существование пользователя
        cursor.execute("""
            SELECT id, telegram_id, phone FROM users
            WHERE telegram_id = ? OR phone = ?
        """, (telegram_id, phone))
        user = cursor.fetchone()

        if user:
            # Пользователь найден
            user_id, existing_telegram_id, existing_phone = user

            # Обновляем Telegram ID, если он отсутствует или отличается
            if telegram_id and existing_telegram_id != telegram_id:
                cursor.execute("""
                    UPDATE users
                    SET telegram_id = ?
                    WHERE id = ?
                """, (telegram_id, user_id))
                conn.commit()

            # Обновляем номер телефона, если он отсутствует или отличается
            if phone and existing_phone != phone:
                cursor.execute("""
                    UPDATE users
                    SET phone = ?
                    WHERE id = ?
                """, (phone, user_id))
                conn.commit()

            bot.send_message(
                message.chat.id,
                f"Данные пользователя обновлены:\n"
                f"Telegram ID: {telegram_id or existing_telegram_id}\n"
                f"Телефон: {phone or existing_phone}"
            )
        else:
            # Если пользователь не найден, добавляем нового
            cursor.execute("""
                INSERT INTO users (telegram_id, phone, role, status, date_added)
                VALUES (?, ?, 'пользователь', 'активен', ?)
            """, (telegram_id, phone, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()

            bot.send_message(
                message.chat.id,
                "Новый пользователь успешно добавлен:\n"
                f"Telegram ID: {telegram_id or 'Не указан'}\n"
                f"Телефон: {phone or 'Не указан'}"
            )

        # Сохраняем данные для последующего добавления анкеты
        session_data[message.chat.id] = {
            "user_info": {"telegram_id": telegram_id, "phone": phone}
        }
        bot.send_message(
            message.chat.id,
            "Теперь выберите тип анкеты:",
            reply_markup=get_type_markup(message.chat.id),
        )
    except sqlite3.IntegrityError as ie:
        print(f"Ошибка уникальности данных: {ie}")
        bot.send_message(
            message.chat.id,
            "Произошла ошибка: этот Telegram ID или номер телефона уже существует в базе данных."
        )
    except ValueError as ve:
        bot.send_message(
            message.chat.id,
            f"{ve}\nПример ввода:\n- Telegram ID: 123456789\n- Номер телефона: +79998887766\nИли оба через пробел:\n123456789 +79998887766"
        )
        bot.register_next_step_handler(message, process_user_info)
    except Exception as e:
        print(f"Ошибка обработки данных пользователя: {e}")
        bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте снова.")
        bot.register_next_step_handler(message, process_user_info)
    finally:
        if conn:
            conn.close()

    




def get_type_markup(chat_id):
    """
    Генерация кнопок для выбора типа анкеты.
    """
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(
        telebot.types.InlineKeyboardButton("🟩", callback_data=f"type_Подходящий🟩_{chat_id}"),
        telebot.types.InlineKeyboardButton("🟥", callback_data=f"type_Проблемный🟥_{chat_id}"),
        telebot.types.InlineKeyboardButton("Не был ⬛️", callback_data=f"type_Не был⬛️_{chat_id}"),
        telebot.types.InlineKeyboardButton("Вирт 🟦", callback_data=f"type_Вирт🟦_{chat_id}")
    )
    return markup


@bot.callback_query_handler(func=lambda call: call.data.startswith("type_"))
def process_profile_type_selection(call):
    """
    Обработка выбора типа анкеты.
    """
    try:
        chat_id = call.message.chat.id
        profile_type = call.data.split("_")[1]

        # Инициализируем сессию, если не существует
        initialize_session(chat_id)

        # Сохраняем выбранный тип анкеты в сессии
        session_data[chat_id]["profile_type"] = profile_type

        # Если тип анкеты "Вирт" или "Не был", пропускаем выбор характеристик
        if profile_type in ["Вирт🟦", "Не был⬛️"]:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=call.message.message_id,
                text=f"Вы выбрали тип анкеты: {profile_type}. Теперь введите комментарий:"
            )
            bot.register_next_step_handler(call.message, process_comment, session_data[chat_id]["user_info"], profile_type, None)
        else:
            # Если выбран другой тип, переходим к выбору характеристик
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=call.message.message_id,
                text=f"Вы выбрали тип анкеты: {profile_type}. Теперь выберите характеристики:",
                reply_markup=get_characteristic_markup(chat_id, profile_type)
            )
    except Exception as e:
        print(f"Ошибка обработки выбора типа анкеты: {e}")
        bot.send_message(call.message.chat.id, "Произошла ошибка при обработке выбора типа анкеты. Попробуйте снова.")


def get_characteristic_markup(chat_id, profile_type):
    """
    Генерация кнопок для выбора характеристик.
    """
    initialize_session(chat_id)

    # Если тип анкеты "Вирт" или "Не был", не показываем характеристики
    if profile_type in ["Вирт🟦", "Не был⬛️"]:
        markup = telebot.types.InlineKeyboardMarkup()
        markup.add(telebot.types.InlineKeyboardButton("Подтвердить", callback_data=f"confirm_{chat_id}"))
        return markup

    selected_characteristics = session_data[chat_id]["characteristics"]

    characteristics = {
        "Подходящий🟩": [("Вежливый 😊", "Вежливый😊"), ("Чистоплотный 💧", "Чистоплотный💧"),
                         ("Красивый ✨", "Красивый✨"), ("Большой >15", "Большой>15"),
                         ("Маленький <15", "Маленький<15"), ("Толстый 🍔", "Толстый🍔"),
                         ("Худой 🧍‍♂️", "Худой🧍‍♂️"), ("Известный 🔥", "Известный🔥")],
        "Проблемный🟥": [("Хам 😠", "Хам😠"), ("Нищий 💰", "Нищий💰"),
                         ("Дроч 🤦", "Дроч🤦"), ("Наркоман 💉", "Наркоман💉"),
                         ("Вымогатель 💀", "Вымогатель💀"), ("Мент 👮", "Мент👮")]
    }

    markup = telebot.types.InlineKeyboardMarkup(row_width=2)
    for name, callback_data in characteristics.get(profile_type, []):
        # Если характеристика выбрана, добавляем галочку перед её названием
        display_name = f"✅ {name}" if callback_data in selected_characteristics else name
        markup.add(telebot.types.InlineKeyboardButton(display_name, callback_data=f"character_{callback_data}_{chat_id}"))

    # Кнопка подтверждения выбора
    markup.add(telebot.types.InlineKeyboardButton("Подтвердить", callback_data=f"confirm_{chat_id}"))
    return markup

@bot.callback_query_handler(func=lambda call: call.data.startswith("character_"))
def process_characteristic_selection(call):
    """
    Обработка выбора характеристик с возможностью добавления и отмены.
    """
    try:
        chat_id = call.message.chat.id
        characteristic = call.data.split("_")[1]  # Извлекаем характеристику

        # Инициализируем сессию, если не существует
        initialize_session(chat_id)

        # Если характеристика выбрана, убираем её, иначе добавляем
        if characteristic in session_data[chat_id]["characteristics"]:
            session_data[chat_id]["characteristics"].remove(characteristic)  # Убираем характеристику
        else:
            session_data[chat_id]["characteristics"].add(characteristic)  # Добавляем характеристику

        # Получаем текущий тип анкеты из сессии
        profile_type = session_data[chat_id]["profile_type"]

        # Обновляем кнопки с учетом изменений
        bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=get_characteristic_markup(chat_id, profile_type)
        )
    except Exception as e:
        print(f"Ошибка обработки выбора характеристики: {e}")
        bot.send_message(call.message.chat.id, "Произошла ошибка при обработке выбора. Попробуйте снова.")




@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_"))
def confirm_characteristics(call):
    """
    Подтверждение анкеты и переход к добавлению комментария.
    """
    try:
        chat_id = int(call.data.split("_")[1])
        user_info = session_data.get(chat_id, {}).get("user_info", {})
        profile_type = session_data.get(chat_id, {}).get("profile_type")
        characteristics = session_data.get(chat_id, {}).get("characteristics", set())

        # Если тип анкеты "Вирт" или "Не был", пропускаем проверку характеристик
        if profile_type in ["Вирт🟦", "Не был⬛️"]:
            bot.send_message(chat_id, "Введите ваш комментарий:")
            bot.register_next_step_handler(call.message, process_comment, user_info, profile_type, None)
        elif characteristics:
            bot.send_message(chat_id, "Введите ваш комментарий:")
            bot.register_next_step_handler(call.message, process_comment, user_info, profile_type, characteristics)
        else:
            bot.send_message(chat_id, "Ошибка: Вы не выбрали ни одной характеристики. Попробуйте снова.")
    except Exception as e:
        print(f"Ошибка подтверждения анкеты: {e}")
        bot.send_message(call.message.chat.id, "Произошла ошибка при подтверждении анкеты. Попробуйте снова.")







def process_comment(message, user_info, profile_type, characteristics):
    """
    Сохранение анкеты с комментарием.
    """
    try:
        comment = message.text.strip()
        if not comment:
            bot.send_message(message.chat.id, "Вы не ввели комментарий. Пожалуйста, попробуйте снова.")
            bot.register_next_step_handler(message, process_comment, user_info, profile_type, characteristics)
            return

        save_profile(message.chat.id, user_info, profile_type, characteristics, comment)
        bot.send_message(message.chat.id, "Анкета успешно добавлена.")
        clear_session(message.chat.id)
    except Exception as e:
        print(f"Ошибка сохранения комментария: {e}")
        bot.send_message(message.chat.id, "Произошла ошибка при сохранении комментария. Попробуйте снова.")





# Сохранение анкеты в базу данных
def save_profile(chat_id, user_info, profile_type, characteristics, comment):
    """
    Сохраняет анкету в базу данных и возвращает в главное меню.
    """
    try:
        conn = get_db_connection()
        if not conn:
            raise ConnectionError("Не удалось подключиться к базе данных.")

        cursor = conn.cursor()
        conn.execute("BEGIN")  # Начало транзакции

        telegram_id = user_info.get("telegram_id")
        phone = user_info.get("phone")
        characteristics_str = ", ".join(characteristics) if characteristics else None

        # Определяем роль: по умолчанию "Пользователь"
        role = "Пользователь"
        if str(chat_id) == MAIN_ADMIN_TELEGRAM_ID:
            role = "Главный администратор"
        elif str(chat_id) == JUNIOR_ADMIN_TELEGRAM_ID:
            role = "Младший администратор"

        cursor.execute("""
            SELECT id FROM users WHERE telegram_id = ? OR phone = ?
        """, (telegram_id, phone))
        user = cursor.fetchone()

        if not user:
            cursor.execute("""
                INSERT INTO users (telegram_id, phone, role, status, date_added)
                VALUES (?, ?, ?, 'активен', ?)
            """, (telegram_id, phone, role, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            user_id = cursor.lastrowid
        else:
            user_id = user[0]

        cursor.execute("""
            INSERT INTO profiles (user_id, user_info, type, characteristic, comment, date_added)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            f"{telegram_id or ''}/{phone or ''}",
            profile_type,
            characteristics_str,
            comment,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        conn.commit()

        bot.send_message(chat_id, "Анкета успешно сохранена!")
        clear_session(chat_id)

        # Создаем корректный fake_message с обязательными атрибутами: chat и from_user
        fake_message = type("FakeMessage", (object,), {
            "chat": type("Chat", (object,), {"id": chat_id})(),
            "from_user": type("User", (object,), {"id": chat_id})()
        })()
        main_menu(fake_message)

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"Ошибка сохранения анкеты: {e}")
        bot.send_message(chat_id, "Произошла ошибка при сохранении анкеты.")
    finally:
        if conn:
            conn.close()


    









# Очистка данных сессии
def clear_session(chat_id):
    if chat_id in session_data:
        del session_data[chat_id]
# Временное хранение данных сессии
session_data = {}

def store_user_profile_type_in_session(chat_id, profile_type):
    if chat_id not in session_data:
        session_data[chat_id] = {"characteristics": set()}
    session_data[chat_id]['profile_type'] = profile_type

def store_user_characteristics_in_session(chat_id, characteristic):
    if chat_id not in session_data:
        session_data[chat_id] = {"characteristics": set()}
    if 'characteristics' not in session_data[chat_id]:
        session_data[chat_id]['characteristics'] = set()
    
    # Переключение: добавление или удаление характеристики
    if characteristic in session_data[chat_id]['characteristics']:
        session_data[chat_id]['characteristics'].remove(characteristic)
    else:
        session_data[chat_id]['characteristics'].add(characteristic)

def retrieve_user_characteristics_from_session(chat_id):
    return session_data.get(chat_id, {}).get('characteristics', set())

def clear_session(chat_id):
    if chat_id in session_data:
        del session_data[chat_id]
# Функция для получения Telegram ID по user_id
def retrieve_telegram_id_for_user_id(user_id):
    conn = get_db_connection()
    telegram_id = None
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT telegram_id FROM users WHERE id = ?", (user_id,))
            result = cursor.fetchone()
            if result:
                telegram_id = result[0]
        except Exception as e:
            print(f"Ошибка при получении Telegram ID: {e}")
        finally:
            conn.close()
    return telegram_id
PAGE_SIZE = 3  # Количество анкет на одной странице

@bot.message_handler(func=lambda message: message.text.lower() == "поиск")
def search_request(message):
    """
    Запрос для поиска. Ожидает ввода Telegram ID или номера телефона.
    """
    bot.send_message(
        message.chat.id,
        "Введите Telegram ID или номер телефона для поиска.\nПример:\n"
        "- Telegram ID: 123456789\n"
        "- Номер телефона: +79998887766\n"
        "- Оба: 123456789 +79998887766"
    )
    bot.register_next_step_handler(message, perform_search)

def perform_search(message):
    """
    Выполняет поиск пользователя в базе данных.
    Если пользователь найден, отображает данные. Если не найден — создает пустую анкету.
    """
    query = message.text.strip()
    if not query:
        bot.send_message(message.chat.id, "Ошибка: введите Telegram ID или номер телефона.")
        return

    conn = None
    try:
        telegram_id, phone = None, None
        inputs = query.split()

        for value in inputs:
            if value.isdigit() and 9 <= len(value) <= 12:  # Telegram ID
                telegram_id = value
            elif re.match(r"^\+7\d{10}$", value):  # Номер телефона в формате +7XXXXXXXXXX
                phone = value

        if not telegram_id and not phone:
            raise ValueError("Ошибка: введите корректный Telegram ID или номер телефона.")

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT u.id, u.telegram_id, u.phone, u.search_count
            FROM users u
            WHERE u.telegram_id = ? OR u.phone = ?
        """, (telegram_id, phone))
        user = cursor.fetchone()

        if user:
            user_id, found_telegram_id, found_phone, search_count = user

            cursor.execute("""
                UPDATE users
                SET search_count = COALESCE(search_count, 0) + 1
                WHERE id = ?
            """, (user_id,))
            conn.commit()

            cursor.execute("""
                SELECT p.type, p.characteristic, p.comment, p.date_added
                FROM profiles p
                WHERE p.user_id = ?
                ORDER BY p.date_added DESC
            """, (user_id,))
            profiles = cursor.fetchall()

            session_data[message.chat.id] = {
                "search_results": profiles,
                "user_info": {
                    "telegram_id": found_telegram_id,
                    "phone": found_phone,
                    "search_count": search_count
                },
                "current_page": 0,
                "search_shown": False  # Добавляем флаг, чтобы не показывать меню при перелистывании
            }

            display_search_results(message, 0)
        else:
            bot.send_message(message.chat.id, "Пользователь не найден. Создаем пустую анкету...")
            main_menu(message)  # Если пользователя нет, сразу переходим в меню

    except ValueError as ve:
        bot.send_message(message.chat.id, str(ve))
    except Exception as e:
        print(f"Ошибка выполнения поиска: {e}")
        bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте снова.")
    finally:
        if conn:
            conn.close()






def display_search_results(message, page, edit_message=True):
    """
    Отображает результаты поиска на указанной странице.
    """
    chat_id = message.chat.id  # Получаем chat_id из message

    if chat_id not in session_data or "search_results" not in session_data[chat_id]:
        bot.send_message(chat_id, "Ошибка: данные для отображения отсутствуют.")
        main_menu(message)  # Возвращаем в меню
        return

    results = session_data[chat_id]["search_results"]
    user_info = session_data[chat_id].get("user_info", {})
    total_pages = (len(results) + PAGE_SIZE - 1) // PAGE_SIZE

    if not results:
        bot.send_message(chat_id, "Результаты поиска отсутствуют.")
        main_menu(message)  # Если результатов нет, сразу в меню
        return

    results = sorted(results, key=lambda x: x[3], reverse=True)  # Сортировка по дате

    type_statistics = {}
    for record in results:
        profile_type = record[0]
        if profile_type:
            type_statistics[profile_type] = type_statistics.get(profile_type, 0) + 1

    most_common_type = max(type_statistics, key=type_statistics.get) if type_statistics else "Не определено"
    telegram_id = user_info.get("telegram_id", "Не указан")
    phone = user_info.get("phone", "Не указан")
    search_count = user_info.get("search_count", 0)

    response_message = (
        f"🔍 Общее количество поисков: {search_count}\n"
        f"Анкета:\n"
        f"Telegram ID: {telegram_id}\n"
        f"Телефон: {phone}\n"
        f"Тип анкеты: {most_common_type}\n"
        "——————————————\n"
    )

    start_index = page * PAGE_SIZE
    end_index = start_index + PAGE_SIZE
    page_results = results[start_index:end_index]

    conn = get_db_connection()
    role_mapping = {}
    if conn:
        try:
            cursor = conn.cursor()
            date_added_list = [result[3] for result in page_results]
            cursor.execute(f"""
                SELECT p.date_added, u.telegram_id, u.role
                FROM profiles p
                JOIN users u ON u.id = p.user_id
                WHERE p.date_added IN ({','.join(['?'] * len(date_added_list))})
            """, date_added_list)
            role_results = cursor.fetchall()

            for date_added, telegram_id, role in role_results:
                if telegram_id == MAIN_ADMIN_TELEGRAM_ID:
                    role_mapping[date_added] = "Главный администратор"
                elif telegram_id == JUNIOR_ADMIN_TELEGRAM_ID:
                    role_mapping[date_added] = "Младший администратор"
                else:
                    role_mapping[date_added] = role or "Пользователь"
        except Exception as e:
            print(f"Ошибка при получении ролей: {e}")
        finally:
            conn.close()

    for i, data in enumerate(page_results, start=start_index + 1):
        profile_type, characteristic, comment, date_added = data
        role = role_mapping.get(date_added, "Не определено")

        response_message += (
            f"Тип анкеты: {profile_type or 'Не указано'}\n"
            f"Дата добавления: {date_added or 'Не указана'}\n"
            f"Характеристика: {characteristic or 'Не указано'}\n"
            f"Комментарий: {comment or 'Нет комментария'}\n"
            f"Добавлено: {role}\n"
            "——————————————\n"
        )

    markup = telebot.types.InlineKeyboardMarkup(row_width=2)
    if page > 0:
        markup.add(telebot.types.InlineKeyboardButton("⬅ Назад", callback_data=f"page_{page - 1}"))
    if page < total_pages - 1:
        markup.add(telebot.types.InlineKeyboardButton("➡ Вперед", callback_data=f"page_{page + 1}"))

    try:
        if edit_message and "last_message_id" in session_data[chat_id]:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=session_data[chat_id]["last_message_id"],
                text=response_message,
                reply_markup=markup
            )
        else:
            msg = bot.send_message(chat_id, response_message, reply_markup=markup)
            session_data[chat_id]["last_message_id"] = msg.message_id

            # Переход в главное меню только после первого показа
            if not session_data[chat_id].get("search_shown", False):
                session_data[chat_id]["search_shown"] = True
                main_menu(message)  # После поиска отправляем в главное меню
    except telebot.apihelper.ApiException as e:
        print(f"Ошибка редактирования сообщения: {e}")
        msg = bot.send_message(chat_id, response_message, reply_markup=markup)
        session_data[chat_id]["last_message_id"] = msg.message_id

    












@bot.callback_query_handler(func=lambda call: call.data.startswith("page_"))
def handle_page_navigation(call):
    """
    Обработка нажатий на кнопки навигации по страницам.
    """
    new_page = int(call.data.split("_")[1])

    # Обновляем текущую страницу в сессии и отображаем её
    session_data[call.message.chat.id]["current_page"] = new_page

    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="Обновляем результаты...",
        reply_markup=None
    )

    # Передаём call.message вместо chat_id
    display_search_results(call.message, new_page)





@bot.callback_query_handler(func=lambda call: call.data in ["return_main_menu", "stay"])
def handle_return_choice(call):
    if call.data == "return_main_menu":
        main_menu(call.message)
    else:
        bot.send_message(call.message.chat.id, "Вы остались на текущем экране.")
# Завершение работы пользователя с ботом
@bot.message_handler(func=lambda message: message.text == "Выход")
def exit_bot(message):
    bot.send_message(message.chat.id, "Вы успешно вышли из бота.")
    clear_session(message.chat.id)
    bot.clear_step_handler_by_chat_id(message.chat.id)


def clear_session(chat_id):
    if chat_id in session_data:
        del session_data[chat_id]

# Запуск бота
try:
    bot.polling(none_stop=True)
except Exception as e:
    print(f"Ошибка при запуске бота: {e}")