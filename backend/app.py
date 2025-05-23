from flask import Flask, request, jsonify
from flask_cors import CORS
import aiofiles
import json
import os
from dotenv import load_dotenv
from telegram import Bot
import asyncio

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "https://jump-cyborg.vercel.app"}})

load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
WEBAPP_URL = 'https://jump-cyborg.vercel.app/'

bot = Bot(token=BOT_TOKEN)

@app.route('/')
async def index():
    return jsonify({'status': 'OK'})

@app.route('/save_score', methods=['POST'])
async def save_score():
    try:
        data = await request.get_json()
        user_id = data.get('user_id')
        username = data.get('username', 'Unknown')
        score = data.get('score', 0)
        
        if not user_id:
            return jsonify({'status': 'ERROR', 'message': 'user_id is required'}), 400
            
        async with aiofiles.open('scores.json', 'r+') as f:
            content = await f.read()
            scores = json.loads(content) if content else {}
            scores[str(user_id)] = {'username': username, 'score': score}
            await f.seek(0)
            await f.write(json.dumps(scores, indent=2))
            await f.truncate()
            
        return jsonify({'status': 'OK'})
    except Exception as e:
        return jsonify({'status': 'ERROR', 'message': str(e)}), 500

@app.route('/get_leaderboard_with_rank')
async def get_leaderboard_with_rank():
    try:
        user_id = request.args.get('user_id')
        current_score = int(request.args.get('score', 0))
        
        async with aiofiles.open('scores.json', 'r') as f:
            content = await f.read()
            scores = json.loads(content) if content else {}
            
        leaderboard = [
            {'user_id': k, 'username': v['username'], 'score': v['score']}
            for k, v in scores.items()
        ]
        leaderboard.sort(key=lambda x: x['score'], reverse=True)
        
        user_rank = None
        if user_id:
            for i, entry in enumerate(leaderboard, 1):
                if entry['user_id'] == user_id:
                    user_rank = i
                    break
                    
        return jsonify({
            'status': 'OK',
            'leaderboard': leaderboard[:10],
            'user_rank': user_rank
        })
    except Exception as e:
        return jsonify({'status': 'ERROR', 'message': str(e)}), 500

if __name__ == '__main__':
    app.run()
