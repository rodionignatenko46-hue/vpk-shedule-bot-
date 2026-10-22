import telebot
import requests
from datetime import datetime, timedelta
import sqlite3
from flask import Flask, request, jsonify
import threading
import os
import uuid
import random

# ==========================================
# ВСТАВЬ СЮДА СВОЙ НОВЫЙ ТОКЕН ОТ @BotFather
TOKEN = '8980864965:AAGCxoMfoUI0Ro6YgXCi1vzWX2mCq5vWtyw'

# ВСТАВЬ СЮДА СВОЙ ID (цифры от @userinfobot)
ADMIN_ID = 8651366498
# ==========================================

BOT_ACTIVE = True
bot = telebot.TeleBot(TOKEN)
API_BASE = "http://109.233.236.101:5000"

# --- БАЗА ДАННЫХ ---
conn = sqlite3.connect('schedule_bot.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, name TEXT, role TEXT)''')
cursor.execute("PRAGMA table_info(users)")
columns = [col[1] for col in cursor.fetchall()]
if 'balance' not in columns: cursor.execute("ALTER TABLE users ADD COLUMN balance INTEGER DEFAULT 100")
if 'tg_username' not in columns: cursor.execute("ALTER TABLE users ADD COLUMN tg_username TEXT")
conn.commit()

def get_user_data(user_id):
    cursor.execute("SELECT name, role, balance, tg_username FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    return result if result else (None, None, 0, None)

def set_user_data(user_id, name, role, tg_username=None):
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if cursor.fetchone():
        if tg_username:
            cursor.execute("UPDATE users SET name=?, role=?, tg_username=? WHERE user_id=?", (name, role, tg_username, user_id))
        else:
            cursor.execute("UPDATE users SET name=?, role=? WHERE user_id=?", (name, role, user_id))
    else:
        cursor.execute("INSERT INTO users (user_id, name, role, balance, tg_username) VALUES (?, ?, ?, 100, ?)", (user_id, name, role, tg_username))
    conn.commit()

def update_balance(user_id, amount):
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()

def get_balance(user_id):
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    res = cursor.fetchone()
    return res[0] if res else 0

# --- API КОЛЛЕДЖА ---
def get_groups():
    try:
        r = requests.get(f"{API_BASE}/groups")
        return r.json() if r.status_code == 200 else []
    except:
        return []

def get_schedule(target, date_from, date_to, is_teacher=False):
    try:
        param = "teacher" if is_teacher else "group"
        url = f"{API_BASE}/schedule_range?{param}={requests.utils.quote(target)}&from={date_from}&to={date_to}"
        r = requests.get(url)
        if r.status_code != 200: return "⚠️ Ошибка сервера."
        data = r.json()
        if not data: return "На выбранные даты занятий нет."
        
        result = ""
        for day in data:
            date_obj = datetime.strptime(day['date'], '%Y-%m-%d')
            result += f"\n📅 **{date_obj.strftime('%d.%m.%Y')}**\n"
            if not day.get('lessons'):
                result += "Занятий нет.\n"
                continue
            for lesson in day['lessons']:
                territory = lesson.get('Territory', '')
                territory_text = f" | 📍 {territory}" if territory else ""
                if is_teacher:
                    info_line = f"   👥 Группа: {lesson.get('Group', '')}{territory_text}\n"
                else:
                    info_line = f"   👨‍🏫 {lesson.get('Teacher', '')}{territory_text}\n"
                result += (f"🔹 Пара {lesson.get('NumberLesson', '?')}: {lesson.get('Discipline', '')}\n{info_line}   🚪 Ауд. {lesson.get('LectureHall', '')}\n\n")
        return result
    except Exception as e:
        return f"Ошибка: {e}"

def send_long_message(chat_id, text, reply_markup=None):
    if len(text) <= 4000:
        bot.send_message(chat_id, text, parse_mode='Markdown', reply_markup=reply_markup)
    else:
        chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for i, chunk in enumerate(chunks):
            markup = reply_markup if i == len(chunks) - 1 else None
            bot.send_message(chat_id, chunk, parse_mode='Markdown', reply_markup=markup)

# --- КЛАВИАТУРЫ ---
def get_role_menu():
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(telebot.types.KeyboardButton('🎓 Я студент'), telebot.types.KeyboardButton('👨‍🏫 Я преподаватель'))
    return markup

def get_main_menu(is_teacher=False):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(telebot.types.KeyboardButton('📅 Расписание на сегодня'))
    markup.add(telebot.types.KeyboardButton('📅 На неделю'), telebot.types.KeyboardButton('🗓 На месяц'))
    
    web_app_info = telebot.types.WebAppInfo(url="https://vpk-shedule-bot.onrender.com/games")
    markup.add(telebot.types.KeyboardButton('🎮 Игры', web_app=web_app_info))
    
    markup.add(telebot.types.KeyboardButton('💰 Баланс'), telebot.types.KeyboardButton('💸 Перевести'))
    
    if is_teacher:
        markup.add(telebot.types.KeyboardButton('🔄 Сменить преподавателя'))
    else:
        markup.add(telebot.types.KeyboardButton('🔄 Сменить группу'))
    return markup

def get_groups_menu():
    groups = get_groups()
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    buttons = [telebot.types.KeyboardButton(g) for g in groups[:50]]
    markup.add(*buttons)
    return markup

# --- АДМИН-ПАНЕЛЬ ---
@bot.message_handler(func=lambda message: not BOT_ACTIVE and message.from_user.id != ADMIN_ID, content_types=['text'])
def bot_offline(message):
    bot.send_message(message.chat.id, "🛠 Бот временно на техническом обслуживании.")

@bot.message_handler(commands=['off'])
def turn_off(message):
    global BOT_ACTIVE
    if message.from_user.id == ADMIN_ID:
        BOT_ACTIVE = False
        bot.send_message(message.chat.id, "🛑 Бот выключен.")

@bot.message_handler(commands=['on'])
def turn_on(message):
    global BOT_ACTIVE
    if message.from_user.id == ADMIN_ID:
        BOT_ACTIVE = True
        bot.send_message(message.chat.id, "✅ Бот включен.")

@bot.message_handler(commands=['stats'])
def show_stats(message):
    if message.from_user.id != ADMIN_ID: return
    cursor.execute("SELECT user_id, name, role, balance, tg_username FROM users")
    users = cursor.fetchall()
    text = f"📊 **Статистика бота**\nВсего пользователей: {len(users)}\n\n"
    for u_id, name, role, balance, tg_user in users:
        username_str = f"@{tg_user}" if tg_user else f"ID: {u_id}"
        role_str = "🎓" if role == "student" else ("👨‍🏫" if role == "teacher" else "🤷")
        text += f"{role_str} {username_str} ({name}) | {balance} 🪙\n"
    bot.send_message(message.chat.id, text, parse_mode='Markdown')

# --- ОБРАБОТЧИКИ БОТА ---
@bot.message_handler(commands=['start'])
def start_message(message):
    tg_user = message.from_user.username
    name, role, balance, _ = get_user_data(message.chat.id)
    if tg_user: set_user_data(message.chat.id, name if name else "Новый", role if role else "none", tg_user)

    author_info = "🤖 **Создатель:** Игнатенко Р.В. (гр. 36тп)\n"
    if name and role and role != "none":
        title = "преподаватель" if role == "teacher" else "группа"
        bot.send_message(message.chat.id, f"👋 С возвращением!\nТвой выбор: {title} **{name}**.\nБаланс: **{balance} 🪙**\n\n{author_info}", parse_mode='Markdown', reply_markup=get_main_menu(role == "teacher"))
    else:
        bot.send_message(message.chat.id, f"👋 Привет! Я бот для просмотра расписания.\n\n{author_info}\nКто ты?", reply_markup=get_role_menu())

@bot.message_handler(func=lambda message: message.text == '🎓 Я студент')
def choose_student(message): bot.send_message(message.chat.id, "Выбери свою группу:", reply_markup=get_groups_menu())

@bot.message_handler(func=lambda message: message.text == '👨‍🏫 Я преподаватель')
def choose_teacher(message): bot.send_message(message.chat.id, "Напиши фамилию:", reply_markup=telebot.types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda message: message.text in ['🔄 Сменить группу', '🔄 Сменить преподавателя'])
def change_target(message):
    name, role, balance, tg_user = get_user_data(message.chat.id)
    if role == "teacher": bot.send_message(message.chat.id, "Напиши фамилию другого преподавателя:")
    else: bot.send_message(message.chat.id, "Выбери новую группу:", reply_markup=get_groups_menu())

@bot.message_handler(func=lambda message: message.text in ['📅 Расписание на сегодня', '📅 На неделю', '🗓 На месяц'])
def show_schedule(message):
    name, role, balance, _ = get_user_data(message.chat.id)
    if not name or not role or role == "none": return bot.send_message(message.chat.id, "Нажми /start.")
    is_teacher = (role == "teacher")
    today = datetime.now()
    if message.text == '📅 Расписание на сегодня': date_from = date_to = today.strftime('%Y-%m-%d'); title = "на сегодня"
    elif message.text == '📅 На неделю': date_from = today.strftime('%Y-%m-%d'); date_to = (today + timedelta(days=6)).strftime('%Y-%m-%d'); title = "на неделю"
    else: date_from = today.strftime('%Y-%m-%d'); date_to = (today + timedelta(days=29)).strftime('%Y-%m-%d'); title = "на месяц"
    bot.send_message(message.chat.id, f"⏳ Загружаю...")
    schedule = get_schedule(name, date_from, date_to, is_teacher)
    send_long_message(message.chat.id, f"📚 Расписание {title} ({name}):\n{schedule}", reply_markup=get_main_menu(is_teacher))

@bot.message_handler(func=lambda message: message.text == '💰 Баланс')
def show_balance(message):
    balance = get_balance(message.chat.id)
    bot.send_message(message.chat.id, f"💰 Твой баланс: **{balance} 🪙**", parse_mode='Markdown')

@bot.message_handler(func=lambda message: message.text == '💸 Перевести')
def transfer_menu(message):
    bot.send_message(message.chat.id, "💸 Формат: `/pay @username сумма`", parse_mode='Markdown')

@bot.message_handler(commands=['pay'])
def transfer_coins(message):
    try:
        parts = message.text.split()
        if len(parts) != 3: return bot.send_message(message.chat.id, "❌ Формат: `/pay @username сумма`", parse_mode='Markdown')
        target_username = parts[1].replace('@', '')
        amount = int(parts[2])
        if amount <= 0: return bot.send_message(message.chat.id, "❌ Сумма > 0")
        if get_balance(message.chat.id) < amount: return bot.send_message(message.chat.id, "❌ Мало монет!")
        cursor.execute("SELECT user_id FROM users WHERE tg_username = ?", (target_username,))
        target = cursor.fetchone()
        if not target: return bot.send_message(message.chat.id, f"❌ @{target_username} не найден.")
        target_id = target[0]
        if target_id == message.chat.id: return bot.send_message(message.chat.id, "❌ Себе нельзя.")
        update_balance(message.chat.id, -amount); update_balance(target_id, amount)
        bot.send_message(message.chat.id, f"✅ Переведено {amount} 🪙 для @{target_username}!")
        try: bot.send_message(target_id, f"🎁 Тебе перевели {amount} 🪙 от @{message.from_user.username}!")
        except: pass
    except ValueError: bot.send_message(message.chat.id, "❌ Сумма должна быть числом.")

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    user_id = message.chat.id
    text = message.text
    tg_user = message.from_user.username
    groups = get_groups()
    if text in groups:
        set_user_data(user_id, text, "student", tg_user)
        bot.send_message(user_id, f"✅ Группа **{text}** сохранена.", parse_mode='Markdown', reply_markup=get_main_menu(False))
    elif len(text) > 2 and text not in ['📅 Расписание на сегодня', '📅 На неделю', '🗓 На месяц']:
        set_user_data(user_id, text, "teacher", tg_user)
        bot.send_message(user_id, f"✅ Преподаватель **{text}** сохранен.", parse_mode='Markdown', reply_markup=get_main_menu(True))
    else:
        bot.send_message(user_id, "Нажми /start.")

# ==========================================
# --- ВЕБ-СЕРВЕР (FLASK) ---
# ==========================================
app = Flask(__name__)

@app.route('/')
def home(): 
    return "Bot is running!"

# --- ВЕБХУК ДЛЯ TELEGRAM ---
@app.route('/' + TOKEN, methods=['POST'])
def getMessage():
    try:
        json_string = request.get_data().decode('utf-8')
        print("ПОЛУЧЕНО СООБЩЕНИЕ ОТ TELEGRAM:", json_string[:100], "...") # Выведет начало сообщения в логи
        update = telebot.types.Update.de_json(json_string)
        if update:
            print("РАСШИФРОВАНО УСПЕШНО")
            bot.process_new_updates([update])
            print("ПЕРЕДАНО В БОТА")
        else:
            print("ОШИБКА: update равен None")
    except Exception as e:
        print("КРИТИЧЕСКАЯ ОШИБКА ПРИ ОБРАБОТКЕ:", e)
    return "!", 200
@app.route('/set_webhook')
def set_webhook():
    # Эта функция нужна, чтобы сообщить Telegram, куда отправлять сообщения
    # Замени URL на свой адрес Render!
    url = "https://vpk-shedule-bot.onrender.com/" + TOKEN
    s = bot.set_webhook(url)
    if s:
        return "Webhook setup ok"
    else:
        return "Webhook setup failed"

# --- ИГРЫ (Web App) ---
@app.route('/games')
def games_hub():
    # ... (код хаба игр оставь как был, он не мешает) ...
    return "Игровой хаб"

@app.route('/game')
def game_page():
    # ... (код мафии оставь как был) ...
    return "Мафия"

# --- API ДЛЯ ЛОББИ ---
lobbies = {}
@app.route('/api/create_lobby', methods=['POST'])
def create_lobby():
    data = request.json
    user_id = data.get('user_id')
    lobby_id = str(uuid.uuid4())[:4].upper()
    lobbies[lobby_id] = {'host': user_id, 'players': [user_id], 'status': 'waiting'}
    return jsonify({"success": True, "lobby_id": lobby_id})

@app.route('/api/join_lobby', methods=['POST'])
def join_lobby():
    data = request.json
    user_id = data.get('user_id')
    lobby_id = data.get('lobby_id')
    if lobby_id in lobbies:
        if user_id not in lobbies[lobby_id]['players']: lobbies[lobby_id]['players'].append(user_id)
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Комната не найдена"})

@app.route('/api/lobby_status/<lobby_id>')
def lobby_status(lobby_id):
    if lobby_id in lobbies:
        return jsonify({"success": True, "players": lobbies[lobby_id]['players']})
    return jsonify({"success": False})

# --- ЗАПУСК ---
if __name__ == '__main__':
    # Удаляем вебхук, если он был, и запускаем сервер
    bot.remove_webhook()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
