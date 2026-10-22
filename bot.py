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

@bot.message_handler(func=lambda message: message.text == '⬅️ Назад в выбор роли')
def back_to_role_menu(message):
    set_user_data(message.chat.id, "Новый", "none", message.from_user.username)
    bot.send_message(message.chat.id, "Выбери, кто ты:", reply_markup=get_role_menu())

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

# Хранилища для игр
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

# --- 1. ГЛАВНЫЙ ХАБ ИГР ---
@app.route('/games')
def games_hub():
    html = """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>
            body { background-color: #0a0a14; color: #fff; font-family: 'Segoe UI', sans-serif; padding: 20px; margin: 0; min-height: 100vh; }
            h1 { text-align: center; background: linear-gradient(90deg, #6e44ff, #ff44cc); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 30px; }
            .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }
            .game-card { background: #14142b; border: 1px solid #2a2a4a; border-radius: 20px; padding: 20px; text-align: center; text-decoration: none; color: white; display: flex; flex-direction: column; align-items: center; justify-content: center; transition: 0.2s; }
            .game-card:active { transform: scale(0.95); background: #1a1a35; }
            .game-icon { font-size: 40px; margin-bottom: 10px; } .game-title { font-weight: bold; font-size: 16px; }
        </style>
    </head>
    <body>
        <h1>🎮 Игровой Хаб</h1>
        <div class="grid">
            <a href="/mafia" class="game-card"><div class="game-icon">🕵️‍♂️</div><div class="game-title">Мафия (Лобби)</div></a>
            <a href="/ttt" class="game-card"><div class="game-icon">❌⭕</div><div class="game-title">Крестики-Нолики</div></a>
            <a href="/rps" class="game-card"><div class="game-icon">✊✌️✋</div><div class="game-title">КНБ (Дуэль)</div></a>
        </div>
        <script> let tg = window.Telegram.WebApp; tg.expand(); tg.setHeaderColor('#0a0a14'); </script>
    </body>
    </html>
    """
    return html

# --- 2. КРЕСТИКИ-НОЛИКИ (ПОЛНЫЙ КОД) ---
@app.route('/ttt')
def ttt_page():
    html = """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>
            body { background-color: #0a0a14; color: #fff; font-family: 'Segoe UI', sans-serif; text-align: center; padding: 20px; margin: 0; display: flex; flex-direction: column; align-items: center; }
            h1 { background: linear-gradient(90deg, #6e44ff, #ff44cc); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
            .btn { background: linear-gradient(90deg, #6e44ff, #ff44cc); border: none; color: white; padding: 15px 30px; border-radius: 15px; font-size: 18px; font-weight: bold; cursor: pointer; margin-bottom: 10px; width: 200px; }
            .btn-join { background: #1a1a35; border: 1px solid #2a2a4a; }
            #game-area { display: none; flex-direction: column; align-items: center; }
            .board { display: grid; grid-template-columns: repeat(3, 90px); grid-template-rows: repeat(3, 90px); gap: 5px; margin: 20px auto; }
            .cell { background: #14142b; border: 1px solid #2a2a4a; display: flex; align-items: center; justify-content: center; font-size: 40px; cursor: pointer; border-radius: 10px; }
            .cell:active { background: #1a1a35; }
            .code { font-size: 30px; color: #00ff88; font-weight: bold; letter-spacing: 5px; }
            .back-btn { position: absolute; top: 20px; left: 20px; color: #6e44ff; text-decoration: none; font-size: 24px; }
        </style>
    </head>
    <body>
        <a href="/games" class="back-btn">←</a>
        <div id="lobby-screen">
            <h1>Крестики-Нолики</h1>
            <button class="btn" onclick="createGame()">➕ Создать игру</button>
            <button class="btn btn-join" onclick="joinGame()">🔍 Присоединиться</button>
        </div>
        <div id="game-area">
            <h2 id="status">Ожидание...</h2>
            <div class="code" id="room-code">----</div>
            <div class="board" id="board"></div>
        </div>
        <script>
            let tg = window.Telegram.WebApp; tg.expand(); tg.setHeaderColor('#0a0a14');
            let userId = tg.initDataUnsafe?.user?.id || Math.floor(Math.random() * 1000000);
            let roomId = null; let mySymbol = null;
            
            function renderBoard(board) {
                const b = document.getElementById('board'); b.innerHTML = '';
                board.forEach((cell, i) => {
                    const d = document.createElement('div'); d.className = 'cell';
                    d.innerText = cell || '';
                    d.onclick = () => makeMove(i);
                    b.appendChild(d);
                });
            }

            async function createGame() {
                const res = await fetch('/api/ttt/create', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ user_id: userId }) });
                const data = await res.json();
                if (data.success) {
                    roomId = data.room_id; mySymbol = 'X';
                    document.getElementById('lobby-screen').style.display = 'none';
                    document.getElementById('game-area').style.display = 'flex';
                    document.getElementById('room-code').innerText = roomId;
                    document.getElementById('status').innerText = "Ждем второго игрока...";
                    pollState();
                }
            }

            async function joinGame() {
                const code = prompt("Введите код комнаты:");
                if (!code) return;
                const res = await fetch('/api/ttt/join', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ user_id: userId, room_id: code.toUpperCase() }) });
                const data = await res.json();
                if (data.success) {
                    roomId = code.toUpperCase(); mySymbol = 'O';
                    document.getElementById('lobby-screen').style.display = 'none';
                    document.getElementById('game-area').style.display = 'flex';
                    document.getElementById('room-code').innerText = roomId;
                    pollState();
                } else alert(data.error);
            }

            async function makeMove(index) {
                if (!roomId) return;
                await fetch('/api/ttt/move', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ room_id: roomId, user_id: userId, index: index }) });
            }

            async function pollState() {
                if (!roomId) return;
                const res = await fetch('/api/ttt/state/' + roomId);
                const data = await res.json();
                if (data.success) {
                    renderBoard(data.board);
                    if (data.status === 'waiting') document.getElementById('status').innerText = "Ждем игрока...";
                    else if (data.status === 'playing') {
                        document.getElementById('status').innerText = data.turn === userId ? "Твой ход!" : "Ход соперника...";
                    } else if (data.status === 'finished') {
                        if (data.winner === 'draw') document.getElementById('status').innerText = "Ничья! 🤝";
                        else document.getElementById('status').innerText = data.winner === userId ? "Ты победил! 🎉" : "Ты проиграл 😢";
                        return; // Останавливаем обновление
                    }
                }
                setTimeout(pollState, 1500);
            }
        </script>
    </body>
    </html>
    """
    return html

# --- 3. КНБ (ПОЛНЫЙ КОД) ---
@app.route('/rps')
def rps_page():
    html = """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>
            body { background-color: #0a0a14; color: #fff; font-family: 'Segoe UI', sans-serif; text-align: center; padding: 20px; margin: 0; display: flex; flex-direction: column; align-items: center; }
            h1 { background: linear-gradient(90deg, #6e44ff, #ff44cc); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
            .btn { background: linear-gradient(90deg, #6e44ff, #ff44cc); border: none; color: white; padding: 15px 30px; border-radius: 15px; font-size: 18px; font-weight: bold; cursor: pointer; margin-bottom: 10px; width: 200px; }
            .btn-join { background: #1a1a35; border: 1px solid #2a2a4a; }
            #game-area { display: none; flex-direction: column; align-items: center; }
            .choices { display: flex; gap: 15px; margin: 30px 0; }
            .choice-btn { font-size: 50px; background: #14142b; border: 1px solid #2a2a4a; border-radius: 20px; padding: 15px; cursor: pointer; }
            .choice-btn:active { transform: scale(0.9); }
            .code { font-size: 30px; color: #00ff88; font-weight: bold; letter-spacing: 5px; }
            .back-btn { position: absolute; top: 20px; left: 20px; color: #6e44ff; text-decoration: none; font-size: 24px; }
        </style>
    </head>
    <body>
        <a href="/games" class="back-btn">←</a>
        <div id="lobby-screen">
            <h1>КНБ Дуэль</h1>
            <button class="btn" onclick="createGame()">➕ Создать игру</button>
            <button class="btn btn-join" onclick="joinGame()">🔍 Присоединиться</button>
        </div>
        <div id="game-area">
            <h2 id="status">Ожидание...</h2>
            <div class="code" id="room-code">----</div>
            <div class="choices">
                <div class="choice-btn" onclick="makeChoice('rock')">✊</div>
                <div class="choice-btn" onclick="makeChoice('scissors')">✌️</div>
                <div class="choice-btn" onclick="makeChoice('paper')">✋</div>
            </div>
        </div>
        <script>
            let tg = window.Telegram.WebApp; tg.expand(); tg.setHeaderColor('#0a0a14');
            let userId = tg.initDataUnsafe?.user?.id || Math.floor(Math.random() * 1000000);
            let roomId = null; let hasChosen = false;

            async function createGame() {
                const res = await fetch('/api/rps/create', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ user_id: userId }) });
                const data = await res.json();
                if (data.success) {
                    roomId = data.room_id;
                    document.getElementById('lobby-screen').style.display = 'none';
                    document.getElementById('game-area').style.display = 'flex';
                    document.getElementById('room-code').innerText = roomId;
                    document.getElementById('status').innerText = "Ждем второго игрока...";
                    pollState();
                }
            }

            async function joinGame() {
                const code = prompt("Введите код комнаты:");
                if (!code) return;
                const res = await fetch('/api/rps/join', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ user_id: userId, room_id: code.toUpperCase() }) });
                const data = await res.json();
                if (data.success) {
                    roomId = code.toUpperCase();
                    document.getElementById('lobby-screen').style.display = 'none';
                    document.getElementById('game-area').style.display = 'flex';
                    document.getElementById('room-code').innerText = roomId;
                    pollState();
                } else alert(data.error);
            }

            async function makeChoice(choice) {
                if (!roomId || hasChosen) return;
                hasChosen = true;
                document.getElementById('status').innerText = "Выбор сделан. Ждем соперника...";
                await fetch('/api/rps/choose', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ room_id: roomId, user_id: userId, choice: choice }) });
            }

            async function pollState() {
                if (!roomId) return;
                const res = await fetch('/api/rps/state/' + roomId + '?user_id=' + userId);
                const data = await res.json();
                if (data.success) {
                    if (data.status === 'waiting') document.getElementById('status').innerText = "Ждем игрока...";
                    else if (data.status === 'playing') {
                        if (!hasChosen) document.getElementById('status').innerText = "Сделай свой выбор!";
                    } else if (data.status === 'finished') {
                        const emojis = {'rock': '✊', 'scissors': '✌️', 'paper': '✋'};
                        let txt = `Ты: ${emojis[data.choices[userId]]} | Соперник: ${emojis[data.choices[data.opponent]]}\n`;
                        if (data.winner === userId) txt += "🎉 Ты победил!";
                        else if (data.winner === 'draw') txt += "🤝 Ничья!";
                        else txt += "😢 Ты проиграл";
                        document.getElementById('status').innerText = txt;
                        return; 
                    }
                }
                setTimeout(pollState, 1500);
            }
        </script>
    </body>
    </html>
    """
    return html

# --- 4. МАФИЯ (ЛОББИ) ---
@app.route('/mafia')
def mafia_page():
    html = """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>
            body { background-color: #0a0a14; color: #fff; font-family: 'Segoe UI', sans-serif; text-align: center; padding: 20px; margin: 0; height: 100vh; display: flex; flex-direction: column; justify-content: center; }
            h1 { background: linear-gradient(90deg, #6e44ff, #ff44cc); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-size: 32px; margin-bottom: 10px; }
            p { color: #888; margin-bottom: 40px; }
            .btn { background: linear-gradient(90deg, #6e44ff, #ff44cc); border: none; color: white; padding: 15px 30px; border-radius: 15px; font-size: 18px; font-weight: bold; cursor: pointer; box-shadow: 0 5px 20px rgba(110, 68, 255, 0.5); width: 80%; max-width: 300px; margin: 0 auto 15px auto; display: block;}
            .btn:active { transform: scale(0.95); }
            .btn-join { background: #1a1a35; border: 1px solid #2a2a4a; box-shadow: none; }
            #lobby-screen { display: none; flex-direction: column; align-items: center; }
            .lobby-code { font-size: 36px; font-weight: bold; color: #00ff88; letter-spacing: 5px; margin: 20px 0; text-shadow: 0 0 10px rgba(0,255,136,0.5); }
            .player-list { background: #1a1a35; padding: 20px; border-radius: 15px; width: 80%; max-width: 300px; margin-bottom: 20px; text-align: left;}
            .player-item { padding: 10px; border-bottom: 1px solid #2a2a4a; }
            .player-item:last-child { border-bottom: none; }
            .back-btn { position: absolute; top: 20px; left: 20px; color: #6e44ff; text-decoration: none; font-size: 24px; }
        </style>
    </head>
    <body>
        <a href="/games" class="back-btn">←</a>
        <div id="main-screen">
            <h1>🕵️‍♂️ Мафия</h1>
            <p>Онлайн-игра для компании</p>
            <button class="btn" onclick="createLobby()">➕ Создать лобби</button>
            <button class="btn btn-join" onclick="joinLobby()">🔍 Найти игру</button>
        </div>
        <div id="lobby-screen">
            <h1 style="font-size: 24px;">Ожидание игроков</h1>
            <p style="margin-bottom: 5px;">Код комнаты:</p>
            <div class="lobby-code" id="lobby-code">----</div>
            <div class="player-list" id="player-list"><div class="player-item">Загрузка...</div></div>
            <p style="font-size: 12px; color: #888;">Скинь этот код друзьям.</p>
            <button class="btn btn-join" onclick="location.reload()" style="margin-top: 20px;">Выйти</button>
        </div>
        <script>
            let tg = window.Telegram.WebApp;
            tg.expand();
            tg.setHeaderColor('#0a0a14');
            let userId = tg.initDataUnsafe?.user?.id || Math.floor(Math.random() * 1000000);
            async function createLobby() {
                const res = await fetch('/api/create_lobby', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ user_id: userId }) });
                const data = await res.json();
                if (data.success) showLobby(data.lobby_id);
            }
            async function joinLobby() {
                const code = prompt("Введите код комнаты:");
                if (!code) return;
                const res = await fetch('/api/join_lobby', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ user_id: userId, lobby_id: code.toUpperCase() }) });
                const data = await res.json();
                if (data.success) showLobby(code.toUpperCase()); else alert(data.error);
            }
            function showLobby(code) {
                document.getElementById('main-screen').style.display = 'none';
                document.getElementById('lobby-screen').style.display = 'flex';
                document.getElementById('lobby-code').innerText = code;
                setInterval(() => checkPlayers(code), 2000);
                checkPlayers(code);
            }
            async function checkPlayers(code) {
                const res = await fetch('/api/lobby_status/' + code);
                const data = await res.json();
                if (data.success) {
                    const list = document.getElementById('player-list');
                    list.innerHTML = '';
                    data.players.forEach((p, index) => { list.innerHTML += `<div class="player-item">👤 Игрок ${index + 1}</div>`; });
                }
            }
        </script>
    </body>
    </html>
    """
    return html

# --- API ДЛЯ МАФИИ ---
@app.route('/api/create_lobby', methods=['POST'])
def create_lobby():
    data = request.json
    user_id = data.get('user_id')
    lobby_id = str(uuid.uuid4())[:4].upper()
    mafia_lobbies[lobby_id] = {'host': user_id, 'players': [user_id], 'status': 'waiting'}
    return jsonify({"success": True, "lobby_id": lobby_id})

@app.route('/api/join_lobby', methods=['POST'])
def join_lobby():
    data = request.json
    user_id = data.get('user_id')
    lobby_id = data.get('lobby_id')
    if lobby_id in mafia_lobbies:
        if user_id not in mafia_lobbies[lobby_id]['players']: mafia_lobbies[lobby_id]['players'].append(user_id)
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Комната не найдена"})

@app.route('/api/lobby_status/<lobby_id>')
def lobby_status(lobby_id):
    if lobby_id in mafia_lobbies: return jsonify({"success": True, "players": mafia_lobbies[lobby_id]['players']})
    return jsonify({"success": False})

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
