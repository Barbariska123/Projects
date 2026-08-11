import telebot
import sqlite3
from datetime import datetime
from telebot import types

# Токен
TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

# Подключение к базе данных
conn = sqlite3.connect('base.db', check_same_thread=False)
cursor = conn.cursor()

ADMIN_ID = os.getenv("ADMIN_ID")

# Создание таблицы, если её нет
def create_table():
    conn, cursor = connect_db()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT NOT NULL,
            file_type TEXT NOT NULL,
            caption TEXT,
            date TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

# Подключение к базе данных
def connect_db():
    conn = sqlite3.connect('bot_files.db')
    return conn, conn.cursor()

# Сохранение файла в базе данных с обработкой ошибок
def save_file(file_id, file_type, caption=None):
    try:
        conn, cursor = connect_db()
        cursor.execute('''
            INSERT INTO files (file_id, file_type, caption, date) 
            VALUES (?, ?, ?, ?)
        ''', (file_id, file_type, caption if caption else '', datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()
        print(f"Файл с ID {file_id} успешно сохранён в базе данных.")
    except sqlite3.Error as e:
        print(f"Ошибка при сохранении файла: {e}")

# Сохранение файла в базе данных с обработкой ошибок
def save_file(file_id, file_type, caption=None):
    try:
        conn, cursor = connect_db()
        cursor.execute('''
            INSERT INTO files (file_id, file_type, caption, date) 
            VALUES (?, ?, ?, ?)
        ''', (file_id, file_type, caption if caption else '', datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()
        print(f"Файл с ID {file_id} успешно сохранён в базе данных.")
    except sqlite3.Error as e:
        print(f"Ошибка при сохранении файла: {e}")

# Поиск файлов по подписи
def search_files_by_caption(caption):
    conn, cursor = connect_db()
    cursor.execute('''
        SELECT file_id, file_type, date FROM files WHERE caption LIKE ?
    ''', (f"%{caption}%",))
    results = cursor.fetchall()
    conn.close()
    return results

# Поиск файлов по типу
def search_files_by_type(file_type):
    conn, cursor = connect_db()
    cursor.execute('''
        SELECT file_id, caption, date FROM files WHERE file_type=?
    ''', (file_type,))
    results = cursor.fetchall()
    conn.close()
    return results

# Поиск файлов по дате
def search_files_by_date(date):
    conn, cursor = connect_db()
    cursor.execute('''
        SELECT file_id, caption, file_type FROM files WHERE date LIKE ?
    ''', (f"{date}%",))
    results = cursor.fetchall()
    conn.close()
    return results

# Создание кнопок главного меню
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton('Загрузить файл')
    btn2 = types.KeyboardButton('Поиск файла')
    markup.add(btn1, btn2)
    return markup

# Кнопки для поиска файла
def search_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton('Поиск по типу файла')
    btn2 = types.KeyboardButton('Поиск по дате')
    btn3 = types.KeyboardButton('Поиск по подписи')
    btn4 = types.KeyboardButton('Назад в главное меню')
    markup.add(btn1, btn2, btn3, btn4)
    return markup

# Кнопки для выбора типа файла
def file_type_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton('Фото')
    btn2 = types.KeyboardButton('Документ')
    btn3 = types.KeyboardButton('Видео')
    btn4 = types.KeyboardButton('Аудио')
    btn5 = types.KeyboardButton('Назад')
    markup.add(btn1, btn2, btn3, btn4, btn5)
    return markup

# Стартовое сообщение с кнопками
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.send_message(message.chat.id, "Добро пожаловать! Выберите действие:", reply_markup=main_menu())

# Обработка сообщений от пользователя
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.from_user.id
    
    if message.text == 'Загрузить файл':
        if str(user_id) == ADMIN_ID:
            bot.send_message(message.chat.id, "Пожалуйста, отправьте файл для загрузки.")
        else:
            bot.send_message(message.chat.id, "У вас нет прав на добавление файлов.")
    elif message.text == 'Поиск файла':
        bot.send_message(message.chat.id, "Выберите метод поиска:", reply_markup=search_menu())
    elif message.text == 'Поиск по типу файла':
        bot.send_message(message.chat.id, "Выберите тип файла для поиска:", reply_markup=file_type_menu())
    elif message.text == 'Поиск по дате':
        bot.send_message(message.chat.id, "Введите дату в формате YYYY-MM-DD для поиска.")
        bot.register_next_step_handler(message, process_search_by_date)
    elif message.text == 'Поиск по подписи':
        bot.send_message(message.chat.id, "Введите подпись для поиска.")
        bot.register_next_step_handler(message, process_search_by_caption)
    elif message.text == 'Назад в главное меню':
        bot.send_message(message.chat.id, "Вы вернулись в главное меню.", reply_markup=main_menu())
    else:
        bot.send_message(message.chat.id, "Неизвестная команда. Выберите действие из меню.", reply_markup=main_menu())

# Обработка поиска по дате
def process_search_by_date(message):
    search_date = message.text
    results = search_files_by_date(search_date)
    
    if results:
        for file in results:
            file_id, caption, file_type = file
            bot.send_message(message.chat.id, f"Найден файл: {file_type}\nОписание: {caption}\nДата: {search_date}")
            if file_type == 'photo':
                bot.send_photo(message.chat.id, file_id)
            elif file_type == 'document':
                bot.send_document(message.chat.id, file_id)
            elif file_type == 'video':
                bot.send_video(message.chat.id, file_id)
            elif file_type == 'audio':
                bot.send_audio(message.chat.id, file_id)
    else:
        bot.send_message(message.chat.id, "Файлы не найдены по указанной дате.")
    
    bot.send_message(message.chat.id, "Выберите дальнейшее действие:", reply_markup=search_menu())

# Обработка поиска по подписи
def process_search_by_caption(message):
    search_caption = message.text
    results = search_files_by_caption(search_caption)
    
    if results:
        for file in results:
            file_id, file_type, date = file
            bot.send_message(message.chat.id, f"Найден файл:\nТип: {file_type}\nДата: {date}")
            if file_type == 'photo':
                bot.send_photo(message.chat.id, file_id)
            elif file_type == 'document':
                bot.send_document(message.chat.id, file_id)
            elif file_type == 'video':
                bot.send_video(message.chat.id, file_id)
            elif file_type == 'audio':
                bot.send_audio(message.chat.id, file_id)
    else:
        bot.send_message(message.chat.id, "Файлы не найдены по указанной подписи.")
    
    bot.send_message(message.chat.id, "Выберите дальнейшее действие:", reply_markup=search_menu())

# Обработка отправки любого файла
@bot.message_handler(content_types=['photo', 'document', 'video', 'audio'])
def handle_files(message):
    user_id = message.from_user.id
    
    if str(user_id) == ADMIN_ID:  # Только администратор может отправлять файлы
        try:
            if message.content_type == 'photo':
                file_id = message.photo[-1].file_id  # Выбираем последнее фото (наибольшего разрешения)
                bot.send_message(message.chat.id, "Как вы хотите подписать это фото?")
                bot.register_next_step_handler(message, save_caption, file_id, 'photo')
            elif message.content_type == 'document':
                file_id = message.document.file_id
                bot.send_message(message.chat.id, "Как вы хотите подписать этот документ?")
                bot.register_next_step_handler(message, save_caption, file_id, 'document')
            elif message.content_type == 'video':
                file_id = message.video.file_id
                bot.send_message(message.chat.id, "Как вы хотите подписать это видео?")
                bot.register_next_step_handler(message, save_caption, file_id, 'video')
            elif message.content_type == 'audio':
                file_id = message.audio.file_id
                bot.send_message(message.chat.id, "Как вы хотите подписать это аудио?")
                bot.register_next_step_handler(message, save_caption, file_id, 'audio')
        except Exception as e:
            bot.reply_to(message, f"Произошла ошибка при сохранении файла: {e}")
    else:
        bot.reply_to(message, "У вас нет прав на добавление файлов.")

# Обработка подписи файла
def save_caption(message, file_id, file_type):
    caption = message.text
    save_file(file_id, file_type, caption)
    bot.send_message(message.chat.id, "Файл успешно сохранён с подписью.")
# Запуск бота
bot.polling(none_stop=True)
