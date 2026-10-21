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
# ВСТАВЬ СЮДА СВОЙ ТОКЕН ОТ @BotFather
TOKEN = '8980864965:AAErIbgjJ6P_qN_HS-C_KpFy5Vjeupg88pA'
# ==========================================

bot = telebot.TeleBot(TOKEN)
API_BASE = "http://109.233.236.101:5000"

# --- БАЗА ДАННЫХ ---
conn = sqlite3.connect('schedule_bot.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, name TEXT, role TEXT)''')
conn.commit()

def get_user_data(user_id):
    cursor.execute("SELECT name, role FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    return result if result else (None, None)

def set_user_data(user_id, name, role):
    cursor.execute("INSERT OR REPLACE INTO users (user_id, name, role) VALUES (?, ?, ?)", (user_id, name, role))
    conn.commit()

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
    
    web_app_info = telebot.types.WebAppInfo(url="https://vpk-shedule-bot.onrender.com/game")
    markup.add(telebot.types.KeyboardButton('🎮 Мафия (Бета)', web_app=web_app_info))
    
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

# --- ОБРАБОТЧИКИ БОТА ---
@bot.message_handler(commands=['start'])
def start_message(message):
    name, role = get_user_data(message.chat.id)
    author_info = "🤖 **Создатель:** Игнатенко Р.В. (гр. 36тп)\n"
    if name and role:
        title = "преподаватель" if role == "teacher" else "группа"
        bot.send_message(message.chat.id, f"👋 С возвращением!\nТвой выбор: {title} **{name}**.\n\n{author_info}", parse_mode='Markdown', reply_markup=get_main_menu(role == "teacher"))
    else:
        bot.send_message(message.chat.id, f"👋 Привет! Я бот для просмотра расписания.\n\n{author_info}\nКто ты?", reply_markup=get_role_menu())

@bot.message_handler(func=lambda message: message.text == '🎓 Я студент')
def choose_student(message):
    bot.send_message(message.chat.id, "Выбери свою группу из списка:", reply_markup=get_groups_menu())

@bot.message_handler(func=lambda message: message.text == '👨‍🏫 Я преподаватель')
def choose_teacher(message):
    bot.send_message(message.chat.id, "Напиши свою фамилию (например: Шалыгина):", reply_markup=telebot.types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda message: message.text in ['🔄 Сменить группу', '🔄 Сменить преподавателя'])
def change_target(message):
    name, role = get_user_data(message.chat.id)
    if role == "teacher":
        bot.send_message(message.chat.id, "Напиши фамилию другого преподавателя:")
    else:
        bot.send_message(message.chat.id, "Выбери новую группу:", reply_markup=get_groups_menu())

@bot.message_handler(func=lambda message: message.text in ['📅 Расписание на сегодня', '📅 На неделю', '🗓 На месяц'])
def show_schedule(message):
    name, role = get_user_data(message.chat.id)
    if not name or not role:
        bot.send_message(message.chat.id, "Нажми /start, чтобы выбрать роль.")
        return
    is_teacher = (role == "teacher")
    today = datetime.now()
    
    if message.text == '📅 Расписание на сегодня':
        date_from = date_to = today.strftime('%Y-%m-%d')
        title = "на сегодня"
    elif message.text == '📅 На неделю':
        date_from = today.strftime('%Y-%m-%d')
        date_to = (today + timedelta(days=6)).strftime('%Y-%m-%d')
        title = "на неделю"
    else:
        date_from = today.strftime('%Y-%m-%d')
        date_to = (today + timedelta(days=29)).strftime('%Y-%m-%d')
        title = "на месяц"

    bot.send_message(message.chat.id, f"⏳ Загружаю расписание {title}...")
    schedule = get_schedule(name, date_from, date_to, is_teacher)
    send_long_message(message.chat.id, f"📚 Расписание {title} ({name}):\n{schedule}", reply_markup=get_main_menu(is_teacher))

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    text = message.text
    groups = get_groups()
    if text in groups:
        set_user_data(message.chat.id, text, "student")
        bot.send_message(message.chat.id, f"✅ Отлично! Группа **{text}** сохранена.", parse_mode='Markdown', reply_markup=get_main_menu(False))
    elif len(text) > 2 and text not in ['📅 Расписание на сегодня', '📅 На неделю', '🗓 На месяц']:
        set_user_data(message.chat.id, text, "teacher")
        bot.send_message(message.chat.id, f"✅ Принято! Ищу расписание для преподавателя **{text}**.", parse_mode='Markdown', reply_markup=get_main_menu(True))
    else:
        bot.send_message(message.chat.id, "Я не знаю такой команды. Нажми /start.")


# ==========================================
# --- СЕРВЕР И ЛОГИКА МАФИИ ---
# ==========================================
app = Flask(__name__)

# Хранилище для лобби (в памяти)
lobbies = {}

@app.route('/')
def home(): 
    return "Bot is running!"

@app.route('/game')
def game_page():
    html_content = """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>
            body { background-color: #0a0a14; color: #fff; font-family: 'Segoe UI', sans-serif; text-align: center; padding: 20px; margin: 0; height: 100vh; display: flex; flex-direction: column; justify-content: center; }
            h1 { background: linear-gradient(90deg, #6e44ff, #ff44cc); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-size: 32px; margin-bottom: 10px; }
            p { color: #888; margin-bottom: 40px; }
            .btn { background: linear-gradient(90deg, #6e44ff, #ff44cc); border: none; color: white; padding: 15px 30px; border-radius: 15px; font-size: 18px; font-weight: bold; cursor: pointer; box-shadow: 0 5px 20px rgba(110, 68, 255, 0.5); width: 80%; max-width: 300px; margin: 0 auto 15px auto; display: block;}
            .btn:active { transform: scale(0.95); }
            .btn-join { background: #1a1a35; border: 1px solid #2a2a4a; box-shadow: none; }
            
            /* Экран лобби */
            #lobby-screen { display: none; flex-direction: column; align-items: center; }
            .lobby-code { font-size: 36px; font-weight: bold; color: #00ff88; letter-spacing: 5px; margin: 20px 0; text-shadow: 0 0 10px rgba(0,255,136,0.5); }
            .player-list { background: #1a1a35; padding: 20px; border-radius: 15px; width: 80%; max-width: 300px; margin-bottom: 20px; text-align: left;}
            .player-item { padding: 10px; border-bottom: 1px solid #2a2a4a; }
            .player-item:last-child { border-bottom: none; }
        </style>
    </head>
    <body>
        <!-- Главный экран -->
        <div id="main-screen">
            <h1>🕵️‍♂️ Мафия</h1>
            <p>Онлайн-игра для компании</p>
            <button class="btn" onclick="createLobby()">➕ Создать лобби</button>
            <button class="btn btn-join" onclick="joinLobby()">🔍 Найти игру</button>
        </div>

        <!-- Экран лобби -->
        <div id="lobby-screen">
            <h1 style="font-size: 24px;">Ожидание игроков</h1>
            <p style="margin-bottom: 5px;">Код комнаты:</p>
            <div class="lobby-code" id="lobby-code">----</div>
            
            <div class="player-list" id="player-list">
                <div class="player-item">Загрузка...</div>
            </div>
            
            <p style="font-size: 12px; color: #888;">Скинь этот код друзьям, чтобы они зашли в игру.</p>
            <button class="btn btn-join" onclick="location.reload()" style="margin-top: 20px;">Выйти</button>
        </div>

        <script>
            let tg = window.Telegram.WebApp;
            tg.expand();
            tg.setHeaderColor('#0a0a14');
            
            // ЗАЩИТА: Если Telegram не дал ID, генерируем случайный
            let userId = tg.initDataUnsafe?.user?.id || Math.floor(Math.random() * 1000000);
            
            let currentLobbyId = null;
            let pollInterval = null;

            async function createLobby() {
                const res = await fetch('/api/create_lobby', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ user_id: userId })
                });
                const data = await res.json();
                
                if (data.success) {
                    currentLobbyId = data.lobby_id;
                    showLobby(data.lobby_id);
                }
            }

            async function joinLobby() {
                const code = prompt("Введите код комнаты:");
                if (!code) return;

                const res = await fetch('/api/join_lobby', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ user_id: userId, lobby_id: code.toUpperCase() })
                });
                const data = await res.json();
                
                if (data.success) {
                    currentLobbyId = code.toUpperCase();
                    showLobby(currentLobbyId);
                } else {
                    alert(data.error);
                }
            }

            function showLobby(code) {
                document.getElementById('main-screen').style.display = 'none';
                document.getElementById('lobby-screen').style.display = 'flex';
                document.getElementById('lobby-code').innerText = code;
                
                // Начинаем проверять, кто зашел
                pollInterval = setInterval(() => checkPlayers(code), 2000);
                checkPlayers(code);
            }

            async function checkPlayers(code) {
                const res = await fetch('/api/lobby_status/' + code);
                const data = await res.json();
                
                if (data.success) {
                    const list = document.getElementById('player-list');
                    list.innerHTML = '';
                    data.players.forEach((p, index) => {
                        list.innerHTML += `<div class="player-item">👤 Игрок ${index + 1}</div>`;
                    });
                }
            }
        </script>
    </body>
    </html>
    """
    return html_content

# --- API ДЛЯ ЛОББИ ---
@app.route('/api/create_lobby', methods=['POST'])
def create_lobby():
    data = request.json
    user_id = data.get('user_id')
    lobby_id = str(uuid.uuid4())[:4].upper() # Короткий код из 4 букв/цифр
    
    lobbies[lobby_id] = {
        'host': user_id,
        'players': [user_id],
        'status': 'waiting'
    }
    return jsonify({"success": True, "lobby_id": lobby_id})

@app.route('/api/join_lobby', methods=['POST'])
def join_lobby():
    data = request.json
    user_id = data.get('user_id')
    lobby_id = data.get('lobby_id')
    
    if lobby_id in lobbies:
        if user_id not in lobbies[lobby_id]['players']:
            lobbies[lobby_id]['players'].append(user_id)
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Комната не найдена"})

@app.route('/api/lobby_status/<lobby_id>')
def lobby_status(lobby_id):
    if lobby_id in lobbies:
        return jsonify({"success": True, "players": lobbies[lobby_id]['players']})
    return jsonify({"success": False})


# --- ЗАПУСК ---
def run_bot():
    print("Бот запущен...")
    bot.infinity_polling()

if __name__ == '__main__':
    t = threading.Thread(target=run_bot)
    t.start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
