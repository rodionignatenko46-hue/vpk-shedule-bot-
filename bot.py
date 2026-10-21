import telebot
import requests
from datetime import datetime, timedelta
import sqlite3
from flask import Flask
import threading
import os

# ВСТАВЬ СЮДА СВОЙ НОВЫЙ ТОКЕН ОТ @BotFather
TOKEN = '8980864965:AAErIbgjJ6P_qN_HS-C_KpFy5Vjeupg88pA'
bot = telebot.TeleBot(TOKEN)
API_BASE = "http://109.233.236.101:5000"

# --- БАЗА ДАННЫХ ---
conn = sqlite3.connect('schedule_bot.db', check_same_thread=False)
cursor = conn.cursor()
# Создаем таблицу (user_id, group_name/teacher_name, role)
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

# --- РАБОТА С API ---
def get_groups():
    try:
        r = requests.get(f"{API_BASE}/groups")
        return r.json() if r.status_code == 200 else []
    except:
        return []

def get_schedule(target, date_from, date_to, is_teacher=False):
    try:
        # Если препод - используем teacher, если студент - group
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
                
                # Для препода выводим группу, для студента - препода
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

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def send_long_message(chat_id, text, reply_markup=None):
    # Разбиваем длинные сообщения (лимит телеграма 4096 символов)
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

# --- ОБРАБОТЧИКИ ---
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

# --- РАСПИСАНИЕ ---
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

# --- ОБРАБОТКА ТЕКСТА (ГРУППЫ ИЛИ ФАМИЛИИ) ---
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

# --- ЗАПУСК ДЛЯ RENDER ---
app = Flask(__name__)
@app.route('/')
def home(): return "Bot is running!"

def run_bot():
    print("Бот запущен...")
    bot.infinity_polling()

if __name__ == '__main__':
    t = threading.Thread(target=run_bot)
    t.start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
