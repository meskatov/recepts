# config.py
import os

# ===== ТОКЕН TELEGRAM =====
# Получить у @BotFather
BOT_TOKEN = "123"

# ===== ТВОЙ ID (АДМИН) =====
# Узнай у бота @userinfobot
ADMIN_USER_ID = 5024855573 # ЗАМЕНИ НА СВОЙ ID

# ===== API ДЛЯ РЕЦЕПТОВ (OpenRouter) =====
# Получить ключ: https://openrouter.ai/keys
AI_API_KEY = "123"
AI_MODEL = "deepseek/deepseek-chat"  # или "openai/gpt-3.5-turbo"
AI_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# ===== ПУТИ =====
DB_PATH = "recipes.db"
LOG_PATH = "logs.txt"
HISTORY_DIR = "user_history"

# Создаём папки
os.makedirs(HISTORY_DIR, exist_ok=True)
