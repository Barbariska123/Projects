import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import pyautogui
import io
from PIL import Image
import psutil
import platform
import os
import threading
import time
import uuid
import sys
import tkinter as tk

BOT_TOKEN = ''
ADMIN_ID = ''
ALLOWED_MAC = ''
monitoring = {}
screensaver_active = False
screensaver_window = None

# --- MAC Check ---
def get_mac_address(target_name="Беспроводная сеть 2"):
    for iface_name, iface_addrs in psutil.net_if_addrs().items():
        if target_name.lower() in iface_name.lower():
            for addr in iface_addrs:
                if hasattr(psutil, 'AF_LINK') and addr.family == psutil.AF_LINK:
                    mac = addr.address
                    if mac and mac != '00:00:00:00:00:00':
                        print(f"✅ Выбран адаптер: {iface_name} → {mac}")
                        return mac.lower().replace('-', ':')
    print("❌ Подходящий интерфейс не найден")
    return None

if get_mac_address() != ALLOWED_MAC:
    print("🚫 Запуск запрещён: неверный ПК.")
    sys.exit()

bot = telebot.TeleBot(BOT_TOKEN)

# --- КАТЕГОРИАЛЬНОЕ МЕНЮ ---
def main_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📺 Экран", callback_data="cat_screen"),
        InlineKeyboardButton("🖱️ Мышь/Клава", callback_data="cat_input"),
        InlineKeyboardButton("🖥 Система", callback_data="cat_sys"),
        InlineKeyboardButton("⚡ Питание", callback_data="cat_power"),
    )
    return markup

def menu_screen():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📷 Скриншот", callback_data="screen"),
        InlineKeyboardButton("👁 Серия скринов", callback_data="screenloop"),
        InlineKeyboardButton("⬛ Заставка", callback_data="screensaver"),
        InlineKeyboardButton("◀️ Назад", callback_data="back_main"),
    )
    return markup

def menu_input():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🖱 Клик мыши", callback_data="click"),
        InlineKeyboardButton("🚀 Переместить мышь", callback_data="move"),
        InlineKeyboardButton("⌨️ Ввести текст", callback_data="write"),
        InlineKeyboardButton("◀️ Назад", callback_data="back_main"),
    )
    return markup

def menu_sys():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📊 Статус ПК", callback_data="status"),
        InlineKeyboardButton("📡 Мониторинг", callback_data="monitor"),
        InlineKeyboardButton("🗂 Процессы", callback_data="processes"),  # ← новая кнопка
        InlineKeyboardButton("◀️ Назад", callback_data="back_main"),
    )
    return markup

def menu_power():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🔄 Перезагрузка", callback_data="reboot"),
        InlineKeyboardButton("⛔ Выключение", callback_data="shutdown"),
        InlineKeyboardButton("🌙 Спящий режим", callback_data="sleep"),
        InlineKeyboardButton("◀️ Назад", callback_data="back_main"),
    )
    return markup

# --- /start ---
@bot.message_handler(commands=['start'])
def start_message(message):
    if message.from_user.id == ADMIN_ID:
        bot.send_message(message.chat.id, "🔧 <b>Управление ПК:</b>", reply_markup=main_menu(), parse_mode="HTML")
    else:
        bot.send_message(message.chat.id, "❌ Доступ запрещён")

# --- Скриншот ---
def send_screen(chat_id):
    try:
        screenshot = pyautogui.screenshot()
        bio = io.BytesIO()
        screenshot.save(bio, format='PNG')
        bio.seek(0)
        bot.send_photo(chat_id, bio, caption="📷 Скриншот сделан")
    except Exception as e:
        bot.send_message(chat_id, f"⚠️ Ошибка скриншота: {e}")

# --- Статус ПК ---
def get_system_status():
    cpu = psutil.cpu_percent(interval=1)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    return (
        f"📊 <b>Статус ПК</b>\n"
        f"🖥 ОС: {platform.system()} {platform.release()}\n"
        f"🔋 CPU: {cpu}%\n"
        f"🧠 RAM: {ram.percent}% ({round(ram.used / 1e+9, 2)} из {round(ram.total / 1e+9, 2)} ГБ)\n"
        f"💾 Диск: {disk.percent}% ({round(disk.used / 1e+9, 2)} из {round(disk.total / 1e+9, 2)} ГБ)"
    )

# --- ЗАСТАВКА ---
def show_screensaver():
    global screensaver_active, screensaver_window
    if screensaver_active:
        return
    screensaver_active = True

    def run():
        global screensaver_window
        root = tk.Tk()
        screensaver_window = root
        root.attributes("-fullscreen", True)
        root.attributes("-topmost", True)
        root.configure(bg="black")  # ← ЧЁРНЫЙ фон!
        root.overrideredirect(True)

        w = root.winfo_screenwidth()
        h = root.winfo_screenheight()
        frame = tk.Frame(root, bg="black")  # ← ЧЁРНЫЙ фон!
        frame.pack(expand=True, fill="both")

        label = tk.Label(
            frame,
            text="🔒 Экран заблокирован\n\nНажмите кнопку 'Разблокировать' в Telegram",
            font=("Arial", 32, "bold"),
            fg="white",     # ← БЕЛЫЙ текст
            bg="black",     # ← ЧЁРНЫЙ фон!
            justify="center"
        )
        label.pack(expand=True)

        root.mainloop()

    threading.Thread(target=run, daemon=True).start()


def close_screensaver():
    global screensaver_active, screensaver_window
    if screensaver_window is not None:
        try:
            screensaver_window.destroy()
        except:
            pass
    screensaver_window = None
    screensaver_active = False

# --- CALLBACKS ---
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ Нет доступа", show_alert=True)
        return

    try:
        # --- КАТЕГОРИИ ---
        if call.data == "cat_screen":
            bot.edit_message_text("📺 <b>Экран</b>", call.message.chat.id, call.message.message_id, 
                                  reply_markup=menu_screen(), parse_mode="HTML")
        elif call.data == "cat_input":
            bot.edit_message_text("🖱 <b>Мышь и клавиатура</b>", call.message.chat.id, call.message.message_id, 
                                  reply_markup=menu_input(), parse_mode="HTML")
        elif call.data == "cat_sys":
            bot.edit_message_text("🖥 <b>Система</b>", call.message.chat.id, call.message.message_id, 
                                  reply_markup=menu_sys(), parse_mode="HTML")
        elif call.data == "cat_power":
            bot.edit_message_text("⚡ <b>Питание</b>", call.message.chat.id, call.message.message_id, 
                                  reply_markup=menu_power(), parse_mode="HTML")
        elif call.data == "back_main":
            bot.edit_message_text("🔧 <b>Управление ПК:</b>", call.message.chat.id, call.message.message_id, 
                                  reply_markup=main_menu(), parse_mode="HTML")

        # --- Экран ---
        elif call.data == "screen":
            send_screen(call.message.chat.id)
        elif call.data == "screenloop":
            bot.send_message(call.message.chat.id, "📸 Отправка 5 скринов...")
            threading.Thread(target=loop_screenshots, args=(call.message.chat.id,)).start()
        elif call.data == "screensaver":
            bot.send_message(call.message.chat.id, "🟪 Заставка включена", reply_markup=unlock_menu())
            show_screensaver()

        # --- Мышь и клавиатура ---
        elif call.data == "click":
            msg = bot.send_message(call.message.chat.id, "Введите координаты (x y) или оставьте пустым для текущей позиции:")
            bot.register_next_step_handler(msg, mouse_click_coords)
        elif call.data == "move":
            pyautogui.moveTo(300, 300)
            bot.send_message(call.message.chat.id, "🖱 Мышь перемещена в (300, 300)")
        elif call.data == "write":
            msg = bot.send_message(call.message.chat.id, "⌨️ Введите текст для ввода:")
            bot.register_next_step_handler(msg, write_text)

        # --- Система ---
        elif call.data == "status":
            status = get_system_status()
            bot.send_message(call.message.chat.id, status, parse_mode='HTML')
        elif call.data == "monitor":
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🛑 Остановить", callback_data="stop_monitor"))
            msg = bot.send_message(call.message.chat.id, "🔄 Мониторинг запущен...", reply_markup=markup)
            monitoring[call.message.chat.id] = True
            threading.Thread(target=monitor_loop, args=(call.message.chat.id, msg.message_id), daemon=True).start()

        # --- Питание ---
        elif call.data == "reboot":
            bot.send_message(call.message.chat.id, "🔄 Перезагрузка через 3 секунды...")
            threading.Thread(target=delayed_command, args=("reboot",)).start()
        elif call.data == "shutdown":
            bot.send_message(call.message.chat.id, "⛔ Выключение через 3 секунды...")
            threading.Thread(target=delayed_command, args=("shutdown",)).start()
        elif call.data == "sleep":
            bot.send_message(call.message.chat.id, "🌙 Переход в спящий режим...")
            threading.Thread(target=sleep_command).start()

        # --- Разблокировка заставки ---
        elif call.data == "unlock":
            close_screensaver()
            bot.send_message(call.message.chat.id, "✅ Заставка отключена")
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        
        elif call.data == "processes":
            procs = []
            for p in psutil.process_iter(['pid', 'name', 'memory_info', 'cpu_percent']):
                try:
                    mem = p.info['memory_info'].rss / (1024 * 1024)
                    cpu = p.info['cpu_percent']
                    procs.append((p.info['pid'], p.info['name'], mem, cpu))
                except:
                    continue
            procs = sorted(procs, key=lambda x: x[2], reverse=True)[:10]  # топ-10 по памяти
            proc_text = "🗂 <b>Выберите процесс для завершения:</b>\n<b>PID</b> — <b>Имя</b> — <b>RAM</b> МБ — <b>CPU%</b>\n\n"
            markup = InlineKeyboardMarkup(row_width=1)
            for pid, name, mem, cpu in procs:
                btn_text = f"{pid} | {name[:20]} | {mem:.1f}MB | {cpu}%"
                markup.add(InlineKeyboardButton(btn_text, callback_data=f"killpid_{pid}"))
            markup.add(InlineKeyboardButton("◀️ Назад", callback_data="cat_sys"))
            bot.edit_message_text(proc_text, call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=markup)


        elif call.data.startswith("killpid_"):
            pid = int(call.data.split("_")[1])
            try:
                p = psutil.Process(pid)
                name = p.name()
                # Кнопки подтверждения
                markup = InlineKeyboardMarkup()
                markup.add(
                    InlineKeyboardButton("✅ Завершить", callback_data=f"confirmpid_{pid}"),
                    InlineKeyboardButton("◀️ Отмена", callback_data="processes")
                )
                bot.edit_message_text(
                    f"❗️ Завершить процесс <b>{name}</b> (PID <code>{pid}</code>)?",
                    call.message.chat.id, call.message.message_id,
                    parse_mode="HTML", reply_markup=markup)
            except Exception as e:
                bot.send_message(call.message.chat.id, f"❌ Ошибка: {e}")
        elif call.data.startswith("confirmpid_"):
            pid = int(call.data.split("_")[1])
            try:
                p = psutil.Process(pid)
                name = p.name()
                p.terminate()
                p.wait(timeout=3)
                bot.edit_message_text(
                    f"✅ Процесс <b>{name}</b> (PID <code>{pid}</code>) завершён.",
                    call.message.chat.id, call.message.message_id,
                    parse_mode="HTML", reply_markup=None)
            except Exception as e:
                bot.send_message(call.message.chat.id, f"❌ Ошибка завершения процесса: {e}")



    except Exception as e:
        bot.send_message(call.message.chat.id, f"⚠️ Ошибка: {e}")

def unlock_menu():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔓 Разблокировать", callback_data="unlock"))
    return markup

# --- ОСТАЛЬНОЕ ---
def sleep_command():
    time.sleep(1)
    if os.name == 'nt':  # Windows
        os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")

def loop_screenshots(chat_id, count=5):
    for i in range(count):
        send_screen(chat_id)
        time.sleep(3)

def write_text(message):
    if message.from_user.id == ADMIN_ID:
        pyautogui.write(message.text, interval=0.05)
        bot.send_message(message.chat.id, "✅ Текст введён")

def delayed_command(cmd):
    time.sleep(3)
    if cmd == "shutdown":
        os.system("shutdown /s /t 1" if os.name == "nt" else "shutdown now")
    elif cmd == "reboot":
        os.system("shutdown /r /t 1" if os.name == "nt" else "reboot")

def monitor_loop(chat_id, msg_id):
    while monitoring.get(chat_id, False):
        try:
            status = get_system_status()
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🛑 Остановить", callback_data="stop_monitor"))
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=status,
                parse_mode='HTML',
                reply_markup=markup
            )
        except Exception as e:
            bot.send_message(chat_id, f"❌ Ошибка мониторинга: {e}")
            monitoring[chat_id] = False
            break
        time.sleep(3)

def mouse_click_coords(message):
    try:
        if message.text.strip():
            x, y = map(int, message.text.strip().split())
            pyautogui.click(x, y)
            bot.send_message(message.chat.id, f"🖱 Клик в точке ({x}, {y}) выполнен")
        else:
            pyautogui.click()
            bot.send_message(message.chat.id, "🖱 Клик в текущей позиции выполнен")
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка: {e}")
def kill_proc_handler(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "❌ Нет доступа")
        return
    pid_text = message.text.strip()
    if not pid_text.isdigit():
        bot.send_message(message.chat.id, "⚠️ Введите только число (PID)!")
        return
    pid = int(pid_text)
    try:
        p = psutil.Process(pid)
        name = p.name()
        p.terminate()
        p.wait(timeout=3)
        bot.send_message(message.chat.id, f"✅ Процесс <b>{name}</b> (PID {pid}) завершён", parse_mode="HTML")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка завершения процесса: {e}")

@bot.callback_query_handler(func=lambda call: call.data == "stop_monitor")
def stop_monitoring(call):
    monitoring[call.message.chat.id] = False
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.answer_callback_query(call.id, "✅ Мониторинг остановлен.")

# --- Запуск ---
bot.infinity_polling()
