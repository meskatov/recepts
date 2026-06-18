# bot.py
import sqlite3
import os
from datetime import datetime
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from config import *

# ==================== БАЗА ДАННЫХ ====================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        last_name TEXT,
        registered_at TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        query TEXT,
        response TEXT,
        image_url TEXT,
        timestamp TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS admin_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        action TEXT,
        timestamp TEXT
    )''')
    conn.commit()
    conn.close()

init_db()

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
def log_action(user_id, action):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO admin_logs (user_id, action, timestamp) VALUES (?, ?, ?)",
              (user_id, action, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat()} | USER {user_id} | {action}\n")

def is_admin(user_id):
    return user_id == ADMIN_USER_ID

def save_user_history(user_id, query, response, image_url):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO requests (user_id, query, response, image_url, timestamp) VALUES (?, ?, ?, ?, ?)",
              (user_id, query, response, image_url, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    filename = os.path.join(HISTORY_DIR, f"user_{user_id}.txt")
    with open(filename, "a", encoding="utf-8") as f:
        f.write(f"--- {datetime.now().isoformat()} ---\n")
        f.write(f"Запрос: {query}\n")
        f.write(f"Ответ: {response[:300]}...\n")
        if image_url:
            f.write(f"Картинка: {image_url}\n")
        f.write("\n")

def get_user_history(user_id):
    filename = os.path.join(HISTORY_DIR, f"user_{user_id}.txt")
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            return f.read()
    return "История пуста."

def get_stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM requests")
    total_requests = c.fetchone()[0]
    conn.close()
    return total_users, total_requests

def get_last_requests(limit=10):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, user_id, query, timestamp FROM requests ORDER BY id DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_top_users(limit=5):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT users.user_id, users.username, COUNT(requests.id) as cnt 
        FROM users 
        LEFT JOIN requests ON users.user_id = requests.user_id 
        GROUP BY users.user_id 
        ORDER BY cnt DESC 
        LIMIT ?
    """, (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def delete_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE user_id=?", (user_id,))
    c.execute("DELETE FROM requests WHERE user_id=?", (user_id,))
    # Удаляем файл истории
    filename = os.path.join(HISTORY_DIR, f"user_{user_id}.txt")
    if os.path.exists(filename):
        os.remove(filename)
    conn.commit()
    conn.close()
    log_action(ADMIN_USER_ID, f"Удалён пользователь {user_id}")

# ==================== ПОИСК РЕЦЕПТА ====================
def get_recipe_from_ai(query):
    headers = {
        "Authorization": f"Bearer {AI_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": AI_MODEL,
        "messages": [
            {"role": "system", "content": "Ты — шеф-повар. Давай рецепт в формате:\n\n◈ ИНГРЕДИЕНТЫ:\n• ...\n• ...\n\n◈ ПРИГОТОВЛЕНИЕ:\n1. ...\n2. ...\n\n◈ СОВЕТ: ..."},
            {"role": "user", "content": f"Дай подробный рецепт блюда: {query}"}
        ],
        "max_tokens": 1500,
        "temperature": 0.7
    }
    try:
        resp = requests.post(AI_API_URL, headers=headers, json=data, timeout=20)
        resp.raise_for_status()
        result = resp.json()
        return result['choices'][0]['message']['content']
    except Exception as e:
        print(f"AI error: {e}")
        return None

def get_recipe_image(query):
    url = f"https://api.unsplash.com/photos/random?query={query}&orientation=landscape&w=800"
    headers = {"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data['urls']['regular']
    except:
        return None

# ==================== КЛАВИАТУРЫ ====================
def main_menu():
    keyboard = [
        [InlineKeyboardButton("▸ Найти рецепт", callback_data="search")],
        [InlineKeyboardButton("▪ Мой профиль", callback_data="profile")],
        [InlineKeyboardButton("◈ Статистика", callback_data="stats")],
        [InlineKeyboardButton("▣ Админ-панель", callback_data="admin")],
    ]
    return InlineKeyboardMarkup(keyboard)

def back_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton("◄ Назад", callback_data="back_to_main")]])

def admin_menu():
    keyboard = [
        [InlineKeyboardButton("◈ Расширенная статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("♢ Последние запросы", callback_data="admin_requests")],
        [InlineKeyboardButton("◙ История пользователя", callback_data="admin_history")],
        [InlineKeyboardButton("◘ Логи", callback_data="admin_logs")],
        [InlineKeyboardButton("◉ Все пользователи", callback_data="admin_users")],
        [InlineKeyboardButton("⊞ Добавить админа", callback_data="admin_add")],
        [InlineKeyboardButton("✖ Удалить пользователя", callback_data="admin_delete")],
        [InlineKeyboardButton("◄ Назад", callback_data="back_to_main")],
    ]
    return InlineKeyboardMarkup(keyboard)

# ==================== ОБРАБОТЧИКИ ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, registered_at) VALUES (?, ?, ?, ?, ?)",
              (user.id, user.username, user.first_name, user.last_name, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(
        "◆ *Добро пожаловать в Рецепт-Бот*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "▸ Найду любой рецепт с картинкой\n"
        "▸ Сохраню историю запросов\n"
        "▸ Полное управление для админа\n\n"
        "Выбери действие:",
        reply_markup=main_menu(),
        parse_mode="Markdown"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if data == "back_to_main":
        await query.edit_message_text(
            "◆ *Главное меню*\n━━━━━━━━━━━━━━━━━━━━━",
            reply_markup=main_menu(),
            parse_mode="Markdown"
        )
    
    elif data == "search":
        context.user_data['awaiting_recipe'] = True
        await query.edit_message_text(
            "▸ *Введи название блюда*\n━━━━━━━━━━━━━━━━━━━━━\n"
            "Например: блины, пицца, борщ",
            reply_markup=back_button(),
            parse_mode="Markdown"
        )
    
    elif data == "profile":
        history = get_user_history(user_id)
        total_requests = len(history.split("---")) - 1 if history != "История пуста." else 0
        
        text = f"▪ *Мой профиль*\n━━━━━━━━━━━━━━━━━━━━━\n"
        text += f"◉ ID: `{user_id}`\n"
        text += f"◈ Всего запросов: {total_requests}\n\n"
        text += f"◙ *Последние запросы:*\n```\n{history[:400]}\n```"
        
        await query.edit_message_text(
            text,
            reply_markup=back_button(),
            parse_mode="Markdown"
        )
    
    elif data == "stats":
        total_users, total_requests = get_stats()
        await query.edit_message_text(
            f"◈ *Статистика бота*\n━━━━━━━━━━━━━━━━━━━━━\n"
            f"◉ Всего пользователей: {total_users}\n"
            f"◙ Всего запросов: {total_requests}\n\n"
            f"◘ Логи: `logs.txt`",
            reply_markup=back_button(),
            parse_mode="Markdown"
        )
    
    elif data == "admin":
        if not is_admin(user_id):
            await query.edit_message_text(
                "✖ *Доступ запрещён!*\n━━━━━━━━━━━━━━━━━━━━━\n"
                "Эта панель только для администратора.",
                reply_markup=back_button(),
                parse_mode="Markdown"
            )
            return
        
        await query.edit_message_text(
            "▣ *Админ-панель*\n━━━━━━━━━━━━━━━━━━━━━\n"
            "Выбери действие:",
            reply_markup=admin_menu(),
            parse_mode="Markdown"
        )
    
    elif data == "admin_stats":
        if not is_admin(user_id):
            return
        
        total_users, total_requests = get_stats()
        top_users = get_top_users(5)
        
        text = f"◈ *Расширенная статистика*\n━━━━━━━━━━━━━━━━━━━━━\n"
        text += f"◉ Всего пользователей: {total_users}\n"
        text += f"◙ Всего запросов: {total_requests}\n\n"
        text += "◈ *Топ-5 активных:*\n"
        
        for uid, username, count in top_users:
            name = f"@{username}" if username else f"ID {uid}"
            text += f"  ▸ {name}: {count}\n"
        
        await query.edit_message_text(
            text,
            reply_markup=back_button(),
            parse_mode="Markdown"
        )
        log_action(user_id, "Просмотр статистики")
    
    elif data == "admin_requests":
        if not is_admin(user_id):
            return
        
        requests_list = get_last_requests(10)
        
        if not requests_list:
            text = "♢ *Последние запросы*\n━━━━━━━━━━━━━━━━━━━━━\nЗапросов пока нет."
        else:
            text = "♢ *Последние 10 запросов*\n━━━━━━━━━━━━━━━━━━━━━\n"
            for req_id, uid, query_text, timestamp in requests_list:
                text += f"  ▸ #{req_id} | `{uid}` | {query_text[:25]}...\n"
        
        await query.edit_message_text(
            text,
            reply_markup=back_button(),
            parse_mode="Markdown"
        )
        log_action(user_id, "Просмотр запросов")
    
    elif data == "admin_history":
        if not is_admin(user_id):
            return
        
        context.user_data['awaiting_check'] = True
        await query.edit_message_text(
            "◙ *Введи ID пользователя*\n━━━━━━━━━━━━━━━━━━━━━\n"
            "Пример: `123456789`\n"
            "Или используй команду: `/check 123`",
            reply_markup=back_button(),
            parse_mode="Markdown"
        )
    
    elif data == "admin_logs":
        if not is_admin(user_id):
            return
        
        if os.path.exists(LOG_PATH):
            with open(LOG_PATH, "r", encoding="utf-8") as f:
                logs = f.read()
                if len(logs) > 3000:
                    logs = "...\n" + logs[-3000:]
            
            if len(logs) > 4000:
                await query.edit_message_text(
                    "◘ *Логи отправлены файлом*",
                    reply_markup=back_button(),
                    parse_mode="Markdown"
                )
                with open(LOG_PATH, "rb") as f:
                    await query.message.reply_document(
                        document=f,
                        filename="logs.txt",
                        caption="◘ Логи бота"
                    )
            else:
                await query.edit_message_text(
                    f"◘ *Логи*\n━━━━━━━━━━━━━━━━━━━━━\n```\n{logs}\n```",
                    reply_markup=back_button(),
                    parse_mode="Markdown"
                )
        else:
            await query.edit_message_text(
                "◘ Логов пока нет.",
                reply_markup=back_button(),
                parse_mode="Markdown"
            )
        log_action(user_id, "Просмотр логов")
    
    elif data == "admin_users":
        if not is_admin(user_id):
            return
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT user_id, username, first_name, registered_at FROM users ORDER BY registered_at DESC LIMIT 20")
        users = c.fetchall()
        conn.close()
        
        if not users:
            text = "◉ *Пользователи*\n━━━━━━━━━━━━━━━━━━━━━\nПока нет пользователей."
        else:
            text = "◉ *Последние 20 пользователей*\n━━━━━━━━━━━━━━━━━━━━━\n"
            for uid, username, first_name, registered in users:
                name = f"@{username}" if username else first_name or f"ID {uid}"
                text += f"  ▸ {name} | `{uid}`\n"
        
        await query.edit_message_text(
            text,
            reply_markup=back_button(),
            parse_mode="Markdown"
        )
        log_action(user_id, "Просмотр пользователей")
    
    elif data == "admin_add":
        if not is_admin(user_id):
            return
        
        context.user_data['awaiting_add_admin'] = True
        await query.edit_message_text(
            "⊞ *Введи ID пользователя*\n━━━━━━━━━━━━━━━━━━━━━\n"
            "Которому нужно дать права админа.\n\n"
            "Пример: `123456789`",
            reply_markup=back_button(),
            parse_mode="Markdown"
        )
        log_action(user_id, "Запрос добавления админа")
    
    elif data == "admin_delete":
        if not is_admin(user_id):
            return
        
        context.user_data['awaiting_delete_user'] = True
        await query.edit_message_text(
            "✖ *Введи ID пользователя*\n━━━━━━━━━━━━━━━━━━━━━\n"
            "Для удаления всех данных:",
            reply_markup=back_button(),
            parse_mode="Markdown"
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    # Поиск рецепта
    if context.user_data.get('awaiting_recipe', False):
        context.user_data['awaiting_recipe'] = False
        
        await update.message.reply_text(
            "⏳ *Ищу рецепт...*\n━━━━━━━━━━━━━━━━━━━━━",
            parse_mode="Markdown"
        )
        
        recipe = get_recipe_from_ai(text)
        if not recipe:
            await update.message.reply_text(
                "✖ *Не удалось найти рецепт*\n━━━━━━━━━━━━━━━━━━━━━\n"
                "Попробуй переформулировать запрос.",
                reply_markup=back_button(),
                parse_mode="Markdown"
            )
            return
        
        image_url = get_recipe_image(text)
        save_user_history(user_id, text, recipe, image_url)
        log_action(user_id, f"Поиск: {text}")
        
        if image_url:
            await update.message.reply_photo(
                photo=image_url,
                caption=f"▸ *{text.capitalize()}*\n━━━━━━━━━━━━━━━━━━━━━\n\n{recipe}",
                reply_markup=main_menu(),
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                f"▸ *{text.capitalize()}*\n━━━━━━━━━━━━━━━━━━━━━\n\n{recipe}",
                reply_markup=main_menu(),
                parse_mode="Markdown"
            )
    
    # Проверка истории
    elif context.user_data.get('awaiting_check', False):
        context.user_data['awaiting_check'] = False
        
        try:
            target_id = int(text.strip())
            filename = os.path.join(HISTORY_DIR, f"user_{target_id}.txt")
            if os.path.exists(filename):
                with open(filename, "rb") as f:
                    await update.message.reply_document(
                        document=f,
                        filename=f"history_{target_id}.txt",
                        caption=f"◙ *История пользователя* `{target_id}`",
                        parse_mode="Markdown"
                    )
            else:
                await update.message.reply_text(
                    f"✖ *Нет истории* для `{target_id}`",
                    parse_mode="Markdown"
                )
        except ValueError:
            await update.message.reply_text(
                "✖ *Некорректный ID*",
                parse_mode="Markdown"
            )
        
        await update.message.reply_text(
            "◄ Возврат в админку",
            reply_markup=admin_menu(),
            parse_mode="Markdown"
        )
    
    # Добавление админа (сохраняем в отдельный файл)
    elif context.user_data.get('awaiting_add_admin', False):
        context.user_data['awaiting_add_admin'] = False
        
        try:
            new_admin_id = int(text.strip())
            # Сохраняем в файл админов
            with open("admins.txt", "a", encoding="utf-8") as f:
                f.write(f"{new_admin_id}\n")
            
            await update.message.reply_text(
                f"⊞ *Админ добавлен*\n━━━━━━━━━━━━━━━━━━━━━\n"
                f"Пользователь `{new_admin_id}` получил права админа.\n"
                f"Перезапусти бота для применения.",
                reply_markup=admin_menu(),
                parse_mode="Markdown"
            )
            log_action(user_id, f"Добавлен админ: {new_admin_id}")
        except ValueError:
            await update.message.reply_text(
                "✖ *Некорректный ID*",
                reply_markup=back_button(),
                parse_mode="Markdown"
            )
    
    # Удаление пользователя
    elif context.user_data.get('awaiting_delete_user', False):
        context.user_data['awaiting_delete_user'] = False
        
        try:
            delete_id = int(text.strip())
            delete_user(delete_id)
            
            await update.message.reply_text(
                f"✖ *Пользователь удалён*\n━━━━━━━━━━━━━━━━━━━━━\n"
                f"ID `{delete_id}` полностью удалён.",
                reply_markup=admin_menu(),
                parse_mode="Markdown"
            )
        except ValueError:
            await update.message.reply_text(
                "✖ *Некорректный ID*",
                reply_markup=back_button(),
                parse_mode="Markdown"
            )
    
    else:
        await update.message.reply_text(
            "◆ *Используй кнопки*\n━━━━━━━━━━━━━━━━━━━━━\n"
            "Или просто напиши название блюда.",
            reply_markup=main_menu(),
            parse_mode="Markdown"
        )

async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("✖ *Доступ запрещён*", parse_mode="Markdown")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text(
            "◙ *Использование:* `/check <ID>`\n"
            "Пример: `/check 123456789`",
            parse_mode="Markdown"
        )
        return
    
    try:
        target_id = int(args[0])
        filename = os.path.join(HISTORY_DIR, f"user_{target_id}.txt")
        if os.path.exists(filename):
            with open(filename, "rb") as f:
                await update.message.reply_document(
                    document=f,
                    filename=f"history_{target_id}.txt",
                    caption=f"◙ *История* `{target_id}`",
                    parse_mode="Markdown"
                )
        else:
            await update.message.reply_text(
                f"✖ *Нет истории* для `{target_id}`",
                parse_mode="Markdown"
            )
    except ValueError:
        await update.message.reply_text("✖ *Некорректный ID*", parse_mode="Markdown")

async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(
        f"◉ *Твой ID:* `{user_id}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"Отправь админу для проверки истории.",
        parse_mode="Markdown"
    )

# ==================== ЗАПУСК ====================
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("check", check_command))
    app.add_handler(CommandHandler("id", id_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🤖 Бот запущен!")
    print(f"👑 Админ ID: {ADMIN_USER_ID}")
    print("Нажми Ctrl+C для остановки\n")
    
    app.run_polling(allowed_updates=["message", "callback_query"])

if __name__ == "__main__":
    main()
