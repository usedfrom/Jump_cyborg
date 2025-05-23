from flask import Flask, request, jsonify
from flask_cors import CORS
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes
import os
import requests
import json
import hashlib
import hmac
import time
import asyncio
import logging
import base64
from dotenv import load_dotenv

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "https://jump-cyborg.vercel.app"}})

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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
GITHUB_REPO = 'your-username/your-repo'  # Замените на ваш репозиторий
GITHUB_FILE_PATH = 'data/scores.json'
GITHUB_API_URL = f'https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}'
GITHUB_HEADERS = {
    'Authorization': f'token {GITHUB_TOKEN}',
    'Accept': 'application/vnd.github.v3+json',
    'User-Agent': 'JumpCyborgBot'
}

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
application = Application.builder().token(BOT_TOKEN).build()

# Проверка Telegram Login
def check_telegram_auth(data):
    received_hash = data.get('hash')
    if not received_hash:
        logger.error("Отсутствует hash в данных Telegram Login")
        return False
    
    data_check = sorted([(k, v) for k, v in data.items() if k != 'hash' and v])
    data_check_string = '\n'.join(f'{k}={v}' for k, v in data_check)
    
    secret_key = hashlib.sha256(BOT_TOKEN.encode()).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    
    if computed_hash != received_hash:
        logger.error("Неверная подпись Telegram Login")
        return False
    
    auth_date = int(data.get('auth_date', 0))
    if time.time() - auth_date > 86400:
        logger.error("Устаревшая авторизация Telegram Login")
        return False
    
    return True

# Функция для создания scores.json, если он не существует
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
        if user_score:
            user_rank = sum(1 for entry in scores if entry['score'] > user_score) + 1
        
        message = '🏆 Таблица лидеров:\n'
        if top_scores:
            for i, entry in enumerate(top_scores, 1):
                username = entry['username'].replace('_', '\\_').replace('*', '\\*').replace('`', '\\`').replace('[', '\\[')
                message += f"{i}. {username}: {entry['score']}\n"
        else:
            message += 'Таблица лидеров пуста.\n'
        
        if user_score and user_rank:
            message += f'\nВы на {user_rank} месте с {user_score} очками'
        elif user_score:
            message += f'\nВаш счёт: {user_score} (вне топ-10)'
        else:
            message += '\nУ вас пока нет результатов.'
        
        await update.message.reply_text(message, parse_mode='MarkdownV2')
        logger.info("Таблица лидеров отправлена")
    except Exception as e:
        logger.error(f"Ошибка при /top: {e}")
        await update.message.reply_text('Ошибка загрузки лидерборда. Попробуйте позже.')

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
            if score > existing_entry['score']:
                existing_entry['username'] = username
                existing_entry['score'] = score
                logger.info(f"Обновлён счёт: user_id={user_id}, username={username}, score={score}")
            else:
                logger.info(f"Счёт не обновлён, текущий выше: {existing_entry['score']} >= {score}")
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
            effective_score = max(user_score, current_score) if user_score else current_score
            user_rank = sum(1 for entry in scores if entry['score'] > effective_score) + 1
            logger.info(f"Ранг пользователя: {user_rank}, эффективный счёт: {effective_score}")
        
        response = {'status': 'OK', 'leaderboard': top_scores, 'user_rank': user_rank}
        logger.info(f"Ответ лидерборда: {json.dumps(response, indent=2)}")
        return jsonify(response)
    except Exception as e:
        logger.error(f"Ошибка при /get_leaderboard_with_rank: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/telegram_login', methods=['POST'])
def telegram_login():
    data = request.get_json()
    logger.info(f"Запрос /telegram_login: {json.dumps(data, indent=2)}")
    
    if not check_telegram_auth(data):
        logger.error("Неверная авторизация Telegram")
        return jsonify({'status': 'error', 'message': 'Invalid Telegram auth'}), 400
    
    user = {
        'id': data['id'],
        'username': data.get('username', data.get('first_name', 'Unknown')),
        'first_name': data.get('first_name', ''),
        'last_name': data.get('last_name', '')
    }
    logger.info(f"Успешная авторизация: {json.dumps(user, indent=2)}")
    return jsonify({'status': 'OK', 'user': user})

def main():
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('top', top))
    application.run_polling()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 10000)))