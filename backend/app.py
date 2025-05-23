from flask import Flask, request, jsonify
from flask_cors import CORS
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes
import os
import requests
import json
import time
import asyncio
import logging
import base64
from dotenv import load_dotenv
import telegram

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "https://jump-cyborg.vercel.app"}})

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Проверка версии python-telegram-bot
if telegram.__version__.split('.')[0] < '20':
    logger.error(f"Требуется python-telegram-bot >= 20.0, установлена версия {telegram.__version__}")
    raise ImportError("Обновите python-telegram-bot до версии >= 20.0")

# Загрузка переменных окружения
load_dotenv()

# Токен бота и URL
BOT_TOKEN = os.getenv('BOT_TOKEN')
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
WEBAPP_URL = 'https://jump-cyborg.vercel.app/'

# Проверка, что токены загружены
if not BOT_TOKEN:
    logger.error("BOT_TOKEN не указан в переменных окружения")
    raise ValueError("BOT_TOKEN не указан")
if not GITHUB_TOKEN:
    logger.error("GITHUB_TOKEN не указан в переменных окружения")
    raise ValueError("GITHUB_TOKEN не указан")

# Конфигурация GitHub
GITHUB_REPO = 'usedfrom/Jump_cyborg'  # Указан ваш реальный репозиторий
GITHUB_FILE_PATH = 'data/scores.json'
GITHUB_API_URL = f'https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}'
GITHUB_HEADERS = {
    'Authorization': f'token {GITHUB_TOKEN}',
    'Accept': 'application/vnd.github.v3+json',
    'User-Agent': 'JumpCyborgBot'
}

# Проверка GITHUB_TOKEN
def validate_github_token():
    try:
        response = requests.get('https://api.github.com/user', headers=GITHUB_HEADERS)
        if response.status_code == 200:
            logger.info(f"GitHub токен валиден, пользователь: {response.json()['login']}")
            return True
        else:
            logger.error(f"Недействительный GITHUB_TOKEN: {response.status_code} {response.text}")
            return False
    except Exception as e:
        logger.error(f"Ошибка проверки GITHUB_TOKEN: {e}")
        return False

if not validate_github_token():
    raise ValueError("Недействительный GITHUB_TOKEN, проверьте переменную окружения")

# Инициализация бота
try:
    bot = Bot(token=BOT_TOKEN)
    application = Application.builder().token(BOT_TOKEN).build()
    logger.info("Telegram Bot успешно инициализирован")
except Exception as e:
    logger.error(f"Ошибка инициализации Telegram Bot: {e}")
    raise

# Функция для создания папки data (пустой файл .gitkeep)
def create_data_folder():
    try:
        logger.info("Попытка создания папки data через .gitkeep")
        content = base64.b64encode(b'').decode('utf-8')
        payload = {
            'message': 'Create data folder with .gitkeep',
            'content': content,
            'branch': 'main'
        }
        response = requests.put(
            f'https://api.github.com/repos/{GITHUB_REPO}/contents/data/.gitkeep',
            headers=GITHUB_HEADERS,
            json=payload
        )
        if response.status_code in [200, 201]:
            logger.info("Папка data успешно создана")
            return True
        else:
            logger.error(f"Ошибка при создании папки data: {response.status_code} {response.text}")
            return False
    except Exception as e:
        logger.error(f"Ошибка при создании папки data: {e}")
        return False

# Функция для создания scores.json
def create_scores_file():
    try:
        logger.info("Попытка создания scores.json")
        content = json.dumps([], indent=2)
        encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
        payload = {
            'message': 'Create scores.json',
            'content': encoded_content,
            'branch': 'main'
        }
        response = requests.put(GITHUB_API_URL, headers=GITHUB_HEADERS, json=payload)
        if response.status_code in [200, 201]:
            logger.info("Файл scores.json успешно создан")
            return response.json()['content']['sha']
        else:
            logger.error(f"Ошибка при создании scores.json: {response.status_code} {response.text}")
            return None
    except Exception as e:
        logger.error(f"Ошибка при создании scores.json: {e}")
        return None

# Функция для получения содержимого JSON-файла из GitHub
def get_scores_from_github():
    try:
        logger.info(f"Получение scores.json из {GITHUB_API_URL}")
        response = requests.get(GITHUB_API_URL, headers=GITHUB_HEADERS)
        logger.info(f"Ответ GitHub: {response.status_code}")
        if response.status_code == 200:
            file_data = response.json()
            content = base64.b64decode(file_data['content']).decode('utf-8')
            scores = json.loads(content)
            logger.info(f"Получено записей: {len(scores)}")
            return scores, file_data['sha']
        elif response.status_code == 404:
            logger.warning("scores.json не найден, создаём новый")
            # Проверяем существование папки data
            folder_check = requests.get(
                f'https://api.github.com/repos/{GITHUB_REPO}/contents/data',
                headers=GITHUB_HEADERS
            )
            if folder_check.status_code == 404:
                logger.info("Папка data не существует, создаём")
                if not create_data_folder():
                    logger.error("Не удалось создать папку data")
                    return [], None
            sha = create_scores_file()
            return [], sha
        else:
            logger.error(f"Ошибка при получении файла: {response.status_code} {response.text}")
            return [], None
    except Exception as e:
        logger.error(f"Ошибка при получении файла: {e}")
        return [], None

# Функция для сохранения JSON-файла в GitHub
def save_scores_to_github(scores, sha):
    try:
        logger.info(f"Сохранение {len(scores)} записей в scores.json")
        content = json.dumps(scores, indent=2)
        encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
        payload = {
            'message': 'Update scores.json',
            'content': encoded_content,
            'sha': sha if sha else None,
            'branch': 'main'
        }
        response = requests.put(GITHUB_API_URL, headers=GITHUB_HEADERS, json=payload)
        if response.status_code in [200, 201]:
            logger.info("Файл scores.json успешно обновлён")
            return response.json()['content']['sha']
        else:
            logger.error(f"Ошибка при сохранении файла: {response.status_code} {response.text}")
            return None
    except Exception as e:
        logger.error(f"Ошибка при сохранении файла: {e}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Команда /start от пользователя {update.effective_user.id}")
    keyboard = [[InlineKeyboardButton("Играть", web_app={'url': WEBAPP_URL})]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Нажми "Играть", чтобы начать!', reply_markup=reply_markup)
    logger.info("Кнопка 'Играть' отправлена")

async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Команда /top от пользователя {update.effective_user.id}")
    try:
        scores, _ = get_scores_from_github()
        logger.info(f"Получено {len(scores)} записей для /top")
        
        top_scores = sorted(scores, key=lambda x: x['score'], reverse=True)[:10]
        
        user_id = update.effective_user.id
        user_score = next((entry['score'] for entry in scores if entry['user_id'] == user_id), None)
        
        user_rank = None
        if user_score is not None:
            user_rank = sum(1 for entry in scores if entry['score'] > user_score) + 1
        
        message = '🏆 Таблица лидеров:\n'
        if top_scores:
            for i, entry in enumerate(top_scores, 1):
                username = entry['username'].replace('_', '\\_').replace('*', '\\*').replace('`', '\\`').replace('[', '\\[')
                message += f"{i}. {username}: {entry['score']}\n"
        else:
            message += 'Таблица лидеров пуста.\n'
        
        if user_score is not None:
            message += f'\nВы на {user_rank} месте с {user_score} очками'
        else:
            message += '\nУ вас пока нет результатов.'
        
        await update.message.reply_text(message, parse_mode='MarkdownV2')
        logger.info("Таблица лидеров отправлена")
    except Exception as e:
        logger.error(f"Ошибка при /top: {e}")
        await update.message.reply_text('Ошибка загрузки лидерборда. Попробуйте позже.')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Команда /help от пользователя {update.effective_user.id}")
    message = (
        "🎮 *JumpBot* — бот для игры Jump Cyborg!\n\n"
        "Доступные команды:\n"
        "/start — Начать игру, открывает ссылку на игру.\n"
        "/top — Показать таблицу лидеров (топ-10 игроков).\n"
        "/help — Показать это сообщение.\n\n"
        f"Играйте на: {WEBAPP_URL}"
    )
    await update.message.reply_text(message, parse_mode='MarkdownV2')
    logger.info("Сообщение /help отправлено")

@app.route('/webhook', methods=['POST'])
async def webhook():
    try:
        update = Update.de_json(request.get_json(), bot)
        await application.process_update(update)
        return jsonify({'status': 'OK'})
    except Exception as e:
        logger.error(f"Ошибка webhook: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/save_score', methods=['POST'])
def save_score():
    data = request.get_json()
    logger.info(f"Запрос /save_score: {json.dumps(data, indent=2)}")
    if not data or 'user_id' not in data or 'username' not in data or 'score' not in data:
        logger.error("Неверный формат данных")
        return jsonify({'status': 'error', 'message': 'Invalid data'}), 400
    
    user_id = data['user_id']
    username = data['username']
    score = data['score']
    
    try:
        scores, sha = get_scores_from_github()
        
        # Проверяем, существует ли пользователь
        existing_entry = next((entry for entry in scores if entry['user_id'] == user_id), None)
        
        if existing_entry:
            existing_entry['username'] = username
            existing_entry['score'] = score
            logger.info(f"Обновлён счёт: user_id={user_id}, username={username}, score={score}")
        else:
            scores.append({'user_id': user_id, 'username': username, 'score': score})
            logger.info(f"Новый счёт: user_id={user_id}, username={username}, score={score}")
        
        new_sha = save_scores_to_github(scores, sha)
        if new_sha:
            logger.info("Счёт успешно сохранён")
            return jsonify({'status': 'OK'})
        else:
            logger.error("Не удалось сохранить счёт в GitHub")
            return jsonify({'status': 'error', 'message': 'Failed to save score to GitHub'}), 500
    except Exception as e:
        logger.error(f"Ошибка при /save_score: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/get_leaderboard_with_rank', methods=['GET'])
def get_leaderboard_with_rank():
    logger.info("Запрос /get_leaderboard_with_rank")
    user_id = request.args.get('user_id', type=int)
    current_score = request.args.get('score', type=int, default=0)
    logger.info(f"Параметры: user_id={user_id}, score={current_score}")
    
    try:
        scores, _ = get_scores_from_github()
        logger.info(f"Получено {len(scores)} записей")
        
        top_scores = sorted(scores, key=lambda x: x['score'], reverse=True)[:10]
        logger.info(f"Возвращено топ-10: {json.dumps(top_scores, indent=2)}")
        
        user_rank = None
        if user_id:
            user_score = next((entry['score'] for entry in scores if entry['user_id'] == user_id), None)
            effective_score = max(user_score, current_score) if user_score is not None else current_score
            user_rank = sum(1 for entry in scores if entry['score'] > effective_score) + 1
            logger.info(f"Ранг пользователя: {user_rank}, эффективный счёт: {effective_score}")
        
        response = {'status': 'OK', 'leaderboard': top_scores, 'user_rank': user_rank}
        logger.info(f"Ответ лидерборда: {json.dumps(response, indent=2)}")
        return jsonify(response)
    except Exception as e:
        logger.error(f"Ошибка при /get_leaderboard_with_rank: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

async def run_polling_with_retry():
    max_retries = 5
    retry_delay = 10  # секунд
    attempt = 0
    
    while attempt < max_retries:
        try:
            logger.info(f"Запуск polling, попытка {attempt + 1}")
            await application.run_polling()
            logger.info("Polling Telegram Bot успешно запущен")
            break
        except Exception as e:
            attempt += 1
            logger.error(f"Ошибка при запуске polling (попытка {attempt}): {e}")
            if attempt < max_retries:
                logger.info(f"Повторная попытка через {retry_delay} секунд")
                await asyncio.sleep(retry_delay)
            else:
                logger.error("Достигнуто максимальное количество попыток, polling не запущен")
                raise

def main():
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('top', top))
    application.add_handler(CommandHandler('help', help_command))
    
    # Запускаем polling в асинхронной задаче
    loop = asyncio.get_event_loop()
    loop.create_task(run_polling_with_retry())

if __name__ == '__main__':
    port = int(os.getenv('PORT', 10000))
    logger.info(f"Запуск Flask сервера на порту {port}")
    app.run(host='0.0.0.0', port=port)
