import telebot
import requests
from datetime import datetime, timedelta
import sqlite3
from flask import Flask, request, jsonify
import threading
import os
import uuid
import random
import time

# ==========================================
# ВСТАВЬ СЮДА СВОЙ НОВЫЙ ТОКЕН ОТ @BotFather
TOKEN = '8980864965:AAGCxoMfoUI0Ro6YgXCi1vzWX2mCq5vWtyw'

# ВСТАВЬ СЮДА СВОЙ ID (цифры от @userinfobot)
ADMIN_ID = 8651366498 
# ==========================================

BOT_ACTIVE = True
bot = telebot.TeleBot(TOKEN, threaded=False)
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
    
    # НОВАЯ КНОПКА НАЗАД
    markup.add(telebot.types.KeyboardButton('⬅️ Назад в выбор роли'))
    
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

# ОБРАБОТЧИК КНОПКИ "НАЗАД"
@bot.message_handler(func=lambda message: message.text == '⬅️ Назад в выбор роли')
def back_to_role_menu(message):
    user_id = message.chat.id
    tg_user = message.from_user.username
    # Сбрасываем группу/фамилию и ставим роль "none"
    set_user_data(user_id, "Новый", "none", tg_user)
    bot.send_message(user_id, "Выбери, кто ты:", reply_markup=get_role_menu())

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
# --- ВЕБ-СЕРВЕР (FLASK) И ИГРЫ ---
# ==========================================
app = Flask(__name__)

mafia_lobbies = {}
ttt_games = {}
rps_games = {}

@app.route('/')
def home(): return "Bot is running!"

@app.route('/' + TOKEN, methods=['POST'])
def getMessage():
    try:
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        if update: bot.process_new_updates([update])
    except Exception as e: print("Ошибка вебхука:", e)
    return "!", 200

@app.route('/set_webhook')
def set_webhook():
    url = "https://vpk-shedule-bot.onrender.com/" + TOKEN
    s = bot.set_webhook(url)
    return "Webhook setup ok" if s else "Webhook setup failed"

@app.route('/games')
def games_hub():
    html = """
    <!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>body { background-color: #0a0a14; color: #fff; font-family: 'Segoe UI', sans-serif; padding: 20px; margin: 0; min-height: 100vh; }
    h1 { text-align: center; background: linear-gradient(90deg, #6e44ff, #ff44cc); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 30px; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }
    .game-card { background: #14142b; border: 1px solid #2a2a4a; border-radius: 20px; padding: 20px; text-align: center; text-decoration: none; color: white; display: flex; flex-direction: column; align-items: center; justify-content: center; transition: 0.2s; }
    .game-card:active { transform: scale(0.95); background: #1a1a35; }
    .game-icon { font-size: 40px; margin-bottom: 10px; } .game-title { font-weight: bold; font-size: 16px; }</style></head>
    <body><h1>🎮 Игровой Хаб</h1><div class="grid">
    <a href="/mafia" class="game-card"><div class="game-icon">🕵️‍♂️</div><div class="game-title">Мафия (Лобби)</div></a>
    <a href="/ttt" class="game-card"><div class="game-icon">❌⭕</div><div class="game-title">Крестики-Нолики</div></a>
    <a href="/rps" class="game-card"><div class="game-icon">✊✌️✋</div><div class="game-title">КНБ (Дуэль)</div></a>
    </div><script> let tg = window.Telegram.WebApp; tg.expand(); tg.setHeaderColor('#0a0a14'); </script></body></html>
    """
    return html

@app.route('/ttt')
def ttt_page():
    # ... (код крестиков-ноликов оставляем как был) ...
    return "Крестики нолики (вставь HTML сюда)" # Заглушка, в реальном коде тут полный HTML из прошлого сообщения

@app.route('/rps')
def rps_page():
    # ... (код КНБ оставляем как был) ...
    return "КНБ (вставь HTML сюда)" # Заглушка

@app.route('/mafia')
def mafia_page(): return "<h1>Мафия в разработке</h1><a href='/games'>Назад</a>"

# --- API ДЛЯ КРЕСТИКОВ-НОЛИКОВ ---
@app.route('/api/ttt/create', methods=['POST'])
def ttt_create():
    u_id = request.json['user_id']; room_id = str(uuid.uuid4())[:4].upper()
    ttt_games[room_id] = {'board': [None]*9, 'players': [u_id], 'turn': u_id, 'status': 'waiting', 'winner': None}
    return jsonify({"success": True, "room_id": room_id})
@app.route('/api/ttt/join', methods=['POST'])
def ttt_join():
    data = request.json; u_id = data['user_id']; room_id = data['room_id']
    if room_id in ttt_games and len(ttt_games[room_id]['players']) == 1:
        ttt_games[room_id]['players'].append(u_id); ttt_games[room_id]['status'] = 'playing'
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Комната занята"})
@app.route('/api/ttt/move', methods=['POST'])
def ttt_move():
    data = request.json; u_id = data['user_id']; room_id = data['room_id']; idx = data['index']
    g = ttt_games.get(room_id)
    if not g or g['status'] != 'playing' or g['turn'] != u_id or g['board'][idx]: return jsonify({"success": False})
    symbol = 'X' if g['players'][0] == u_id else 'O'; g['board'][idx] = symbol
    win_lines = [[0,1,2],[3,4,5],[6,7,8],[0,3,6],[1,4,7],[2,5,8],[0,4,8],[2,4,6]]
    for line in win_lines:
        if g['board'][line[0]] == g['board'][line[1]] == g['board'][line[2]] != None:
            g['status'] = 'finished'; g['winner'] = u_id; return jsonify({"success": True})
    if None not in g['board']: g['status'] = 'finished'; g['winner'] = 'draw'; return jsonify({"success": True})
    g['turn'] = g['players'][1] if g['turn'] == g['players'][0] else g['players'][0]
    return jsonify({"success": True})
@app.route('/api/ttt/state/<room_id>')
def ttt_state(room_id):
    g = ttt_games.get(room_id)
    if g: return jsonify({"success": True, "board": g['board'], "status": g['status'], "turn": g['turn'], "winner": g['winner']})
    return jsonify({"success": False})

# --- API ДЛЯ КНБ ---
@app.route('/api/rps/create', methods=['POST'])
def rps_create():
    u_id = request.json['user_id']; room_id = str(uuid.uuid4())[:4].upper()
    rps_games[room_id] = {'players': [u_id], 'choices': {}, 'status': 'waiting', 'winner': None}
    return jsonify({"success": True, "room_id": room_id})
@app.route('/api/rps/join', methods=['POST'])
def rps_join():
    data = request.json; u_id = data['user_id']; room_id = data['room_id']
    if room_id in rps_games and len(rps_games[room_id]['players']) == 1:
        rps_games[room_id]['players'].append(u_id); rps_games[room_id]['status'] = 'playing'
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Комната занята"})
@app.route('/api/rps/choose', methods=['POST'])
def rps_choose():
    data = request.json; u_id = data['user_id']; room_id = data['room_id']; choice = data['choice']
    g = rps_games.get(room_id)
    if not g or g['status'] != 'playing': return jsonify({"success": False})
    g['choices'][u_id] = choice
    if len(g['choices']) == 2:
        p1, p2 = g['players']; c1, c2 = g['choices'][p1], g['choices'][p2]
        if c1 == c2: g['winner'] = 'draw'
        elif (c1 == 'rock' and c2 == 'scissors') or (c1 == 'scissors' and c2 == 'paper') or (c1 == 'paper' and c2 == 'rock'): g['winner'] = p1
        else: g['winner'] = p2
        g['status'] = 'finished'
    return jsonify({"success": True})
@app.route('/api/rps/state/<room_id>')
def rps_state(room_id):
    g = rps_games.get(room_id)
    if g:
        u_id = request.args.get('user_id')
        opp = [p for p in g['players'] if str(p) != str(u_id)]
        return jsonify({"success": True, "status": g['status'], "choices": g['choices'], "winner": g['winner'], "opponent": opp[0] if opp else None})
    return jsonify({"success": False})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
