import telebot
from telebot import types
import threading
import time
import datetime as dt

BOT_TOKEN = '8076421586:AAHOfzXV87qtFoyMn_jLQaw4Nhf7DPDc4Ec'
DEFAULT_CHANNEL_ID = '@ponosfm103'
ADMIN_ID =  # замените на ваш Telegram ID

bot = telebot.TeleBot(BOT_TOKEN)
channel_id = DEFAULT_CHANNEL_ID
last_messages = []
user_drafts = {}  # временное хранилище для черновиков (по chat_id)
scheduled_posts = []  # список: {'chat_id', 'text', 'media', 'time'}

def main_menu():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📝 Новый пост", callback_data="new_post"))
    kb.add(types.InlineKeyboardButton("📋 Последние", callback_data="show_recent"))
    kb.add(types.InlineKeyboardButton("🗑 Удалить последнее", callback_data="delete_last"))
    kb.add(types.InlineKeyboardButton("⚙️ Настройки", callback_data="settings"))
    kb.add(types.InlineKeyboardButton("ℹ️ О боте", callback_data="about"))
    return kb

def post_menu():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("➕ Текст", callback_data="add_text"))
    kb.add(types.InlineKeyboardButton("🖼 Фото", callback_data="add_photo"))
    kb.add(types.InlineKeyboardButton("🎞 Видео", callback_data="add_video"))
    kb.add(types.InlineKeyboardButton("📎 Файл", callback_data="add_file"))
    kb.add(types.InlineKeyboardButton("✅ Опубликовать", callback_data="publish"))
    kb.add(types.InlineKeyboardButton("🕒 Запланировать", callback_data="schedule"))
    kb.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu"))
    return kb


def settings_menu():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📥 Показать канал", callback_data="show_channel"))
    kb.add(types.InlineKeyboardButton("✏️ Изменить канал", callback_data="change_channel"))
    kb.add(types.InlineKeyboardButton("⬅ Назад", callback_data="back_to_menu"))
    return kb

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "Добро пожаловать! Выберите действие:", reply_markup=main_menu())

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    global channel_id
    chat_id = call.message.chat.id
    user_id = call.from_user.id

    if call.data == "new_post":
        user_drafts[chat_id] = {"text": "", "media": []}
        bot.send_message(chat_id, "Создание нового поста:", reply_markup=post_menu())

    elif call.data == "add_text":
        msg = bot.send_message(chat_id, "Введите текст:")
        bot.register_next_step_handler(msg, lambda m: add_text_to_draft(chat_id, m))

    elif call.data == "add_photo":
        msg = bot.send_message(chat_id, "Отправьте фото:")
        bot.register_next_step_handler(msg, lambda m: add_media_to_draft(chat_id, m, "photo"))

    elif call.data == "add_video":
        msg = bot.send_message(chat_id, "Отправьте видео:")
        bot.register_next_step_handler(msg, lambda m: add_media_to_draft(chat_id, m, "video"))

    elif call.data == "add_file":
        msg = bot.send_message(chat_id, "Отправьте файл:")
        bot.register_next_step_handler(msg, lambda m: add_media_to_draft(chat_id, m, "document"))

    elif call.data == "publish":
        publish_draft(chat_id)

    elif call.data == "show_recent":
        if last_messages:
            for i, msg in enumerate(last_messages[-5:][::-1]):
                bot.send_message(chat_id, f"{i+1}) {msg['text']}")
        else:
            bot.send_message(chat_id, "Нет сообщений.")
        bot.send_message(chat_id, "↩ Главное меню", reply_markup=main_menu())

    elif call.data == "delete_last":
        if last_messages:
            msg_id = last_messages.pop()['msg_id']
            try:
                bot.delete_message(channel_id, msg_id)
                bot.send_message(chat_id, "🗑 Сообщение удалено.")
            except:
                bot.send_message(chat_id, "❌ Не удалось удалить.")
        else:
            bot.send_message(chat_id, "Нет сообщений.")
        bot.send_message(chat_id, "↩ Главное меню", reply_markup=main_menu())

    elif call.data == "settings":
        if user_id == ADMIN_ID:
            bot.send_message(chat_id, "⚙️ Настройки:", reply_markup=settings_menu())
        else:
            bot.send_message(chat_id, "⛔ Только админ может открыть настройки.")

    elif call.data == "show_channel":
        bot.send_message(chat_id, f"📢 Канал: <code>{channel_id}</code>", parse_mode="HTML")

    elif call.data == "change_channel":
        if user_id == ADMIN_ID:
            msg = bot.send_message(chat_id, "Введите новый ID канала (@username или -100...):")
            bot.register_next_step_handler(msg, lambda m: update_channel_id(m, chat_id))
        else:
            bot.send_message(chat_id, "⛔ Только админ может менять канал.")

    elif call.data == "about":
        bot.send_message(chat_id, "🤖 Бот для комбинированной публикации в канал.")
        bot.send_message(chat_id, "↩ Главное меню", reply_markup=main_menu())

    elif call.data == "back_to_menu":
        bot.send_message(chat_id, "↩ Главное меню:", reply_markup=main_menu())

def add_text_to_draft(chat_id, message):
    user_drafts[chat_id]['text'] = message.text
    bot.send_message(chat_id, "📝 Текст добавлен.", reply_markup=post_menu())

def add_media_to_draft(chat_id, message, media_type):
    if media_type == "photo" and message.photo:
        media_id = message.photo[-1].file_id
    elif media_type == "video" and message.video:
        media_id = message.video.file_id
    elif media_type == "document" and message.document:
        media_id = message.document.file_id
    else:
        bot.send_message(chat_id, "❗ Неверный тип файла.")
        return
    user_drafts[chat_id]['media'].append((media_type, media_id))
    bot.send_message(chat_id, f"📎 {media_type.capitalize()} добавлен.", reply_markup=post_menu())

def publish_draft(chat_id):
    draft = user_drafts.get(chat_id)
    if not draft:
        bot.send_message(chat_id, "❗ Нет черновика.")
        return

    text = draft['text']
    media = draft['media']

    if len(media) == 0:
        sent = bot.send_message(channel_id, text or "Без текста")
        last_messages.append({'msg_id': sent.message_id, 'text': text})
    elif len(media) == 1:
        m_type, m_id = media[0]
        if m_type == "photo":
            sent = bot.send_photo(channel_id, m_id, caption=text)
        elif m_type == "video":
            sent = bot.send_video(channel_id, m_id, caption=text)
        elif m_type == "document":
            sent = bot.send_document(channel_id, m_id, caption=text)
        last_messages.append({'msg_id': sent.message_id, 'text': f"{m_type}: {text}"})
    else:
        media_group = []
        for i, (m_type, m_id) in enumerate(media):
            caption = text if i == 0 else ""
            if m_type == "photo":
                media_group.append(types.InputMediaPhoto(m_id, caption=caption))
            elif m_type == "video":
                media_group.append(types.InputMediaVideo(m_id, caption=caption))
        sent_group = bot.send_media_group(channel_id, media_group)
        for s in sent_group:
            last_messages.append({'msg_id': s.message_id, 'text': "media group"})

    user_drafts.pop(chat_id, None)
    bot.send_message(chat_id, "✅ Опубликовано.", reply_markup=main_menu())

def update_channel_id(message, chat_id):
    global channel_id
    channel_id = message.text.strip()
    bot.send_message(chat_id, f"✅ Канал обновлён на {channel_id}", reply_markup=main_menu())
def ask_schedule_time(chat_id, message):
    try:
        send_time = dt.datetime.strptime(message.text.strip(), "%d.%m.%Y %H:%M")
        now = dt.datetime.now()
        if send_time <= now:
            bot.send_message(chat_id, "❗ Время должно быть в будущем.", reply_markup=post_menu())
            return
        draft = user_drafts.get(chat_id)
        if not draft:
            bot.send_message(chat_id, "❌ Нет черновика.", reply_markup=post_menu())
            return
        scheduled_posts.append({
            'chat_id': chat_id,
            'text': draft['text'],
            'media': draft['media'],
            'time': send_time
        })
        user_drafts.pop(chat_id, None)
        bot.send_message(chat_id, f"✅ Пост запланирован на {send_time.strftime('%d.%m.%Y %H:%M')}", reply_markup=main_menu())
    except Exception as e:
        bot.send_message(chat_id, "❗ Неверный формат. Попробуйте снова.", reply_markup=post_menu())
def scheduled_post_worker():
    while True:
        now = dt.datetime.now()
        for post in scheduled_posts[:]:
            if now >= post['time']:
                publish_scheduled_post(post)
                scheduled_posts.remove(post)
        time.sleep(30)  # проверка каждые 30 секунд

def publish_scheduled_post(post):
    chat_id = post['chat_id']
    text = post['text']
    media = post['media']

    if not media:
        sent = bot.send_message(channel_id, text or "Без текста")
        last_messages.append({'msg_id': sent.message_id, 'text': text})
    elif len(media) == 1:
        m_type, m_id = media[0]
        if m_type == "photo":
            sent = bot.send_photo(channel_id, m_id, caption=text)
        elif m_type == "video":
            sent = bot.send_video(channel_id, m_id, caption=text)
        elif m_type == "document":
            sent = bot.send_document(channel_id, m_id, caption=text)
        last_messages.append({'msg_id': sent.message_id, 'text': f"{m_type}: {text}"})
    else:
        media_group = []
        for i, (m_type, m_id) in enumerate(media):
            caption = text if i == 0 else ""
            if m_type == "photo":
                media_group.append(types.InputMediaPhoto(m_id, caption=caption))
            elif m_type == "video":
                media_group.append(types.InputMediaVideo(m_id, caption=caption))
        sent_group = bot.send_media_group(channel_id, media_group)
        for s in sent_group:
            last_messages.append({'msg_id': s.message_id, 'text': "media group"})
    bot.send_message(chat_id, "📢 Запланированный пост опубликован.")

# Запуск фонового потока
threading.Thread(target=scheduled_post_worker, daemon=True).start()

bot.infinity_polling()
