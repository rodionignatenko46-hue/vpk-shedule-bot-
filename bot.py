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
TOKEN = '8980864965:AAErIbgjJ6P_qN_HS-C_KpFy5Vjeupg88pA'
# ==========================================

bot = telebot.TeleBot(TOKEN)
API_BASE = "http://109.233.236.101:5000"

# --- БАЗА ДАННЫХ ---
conn = sqlite3.connect('schedule_bot.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                  (user_id INTEGER PRIMARY KEY, name TEXT, role TEXT)''')
conn.commit()

def get_user_data(user_id):
    cursor.execute("SELECT name, role FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    return result if result else (None, None)

def set_user_data(user_id, name, role):
    cursor.execute("INSERT OR REPLACE INTO users (user_id, name, role) VALUES (?, ?, ?)", (user_id, name, role))
    conn.commit()

# --- РАБОТА С API КОЛЛЕДЖА ---
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
        
        if r.status_code != 200: return "⚠️ Ошибка сервера. Возможно, неверно введено имя."
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

                result += (f"🔹 Пара {lesson.get('NumberLesson', '?')}: {lesson.get('Discipline', '')}\n"
                           f"{info_line}"
                           f"   🚪 Ауд. {lesson.get('LectureHall', '')}\n\n")
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
    
    # Кнопка Мафии (ссылка ведет на твой Render)
    web_app_info = telebot.types.WebAppInfo(url="https://college-botpython-bot-py.onrender.com/game")
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
# --- FLASK СЕРВЕР И ВЕБ-ПРИЛОЖЕНИЕ МАФИИ ---
# ==========================================
app = Flask(__name__)

@app.route('/')
def home(): 
    return "Bot is running!"

# Страница для игры Мафия (открывается в окошке Telegram)
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
        </style>
    </head>
    <body>
        <h1>🕵️‍♂️ Мафия</h1>
        <p>Онлайн-игра для компании</p>
        
        <button class="btn" onclick="alert('Тут будет создание лобби!')">➕ Создать лобби</button>
        <button class="btn btn-join" onclick="alert('Тут будет поиск лобби!')">🔍 Найти игру</button>
        
        <script>
            let tg = window.Telegram.WebApp;
            tg.expand();
            tg.setHeaderColor('#0a0a14');
        </script>
    </body>
    </html>
    """
    return html_content

# --- ЗАПУСК БОТА И СЕРВЕРА ---
def run_bot():
    print("Бот запущен...")
    bot.infinity_polling()

if __name__ == '__main__':
    t = threading.Thread(target=run_bot)
    t.start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
