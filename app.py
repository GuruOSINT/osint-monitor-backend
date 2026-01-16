from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import os
import time
from datetime import datetime
from threading import Thread
import re
from collections import deque
import asyncio
from telegram import Bot
from telegram.ext import Application, MessageHandler, filters
import tweepy

app = Flask(__name__)
app.config['SECRET_KEY'] = 'osint-monitor-secret'
CORS(app, resources={r"/*": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Real-time storage
intelligence_stream = deque(maxlen=1000)  # Keep last 1000 items
conflict_data = {}
active_sources = {}

CONFLICTS = {
    'us_iran': {
        'name': 'US-Iran Tensions',
        'keywords': ['iran', 'tehran', 'centcom', 'irgc', 'strait of hormuz', 'persian gulf'],
        'escalation_keywords': ['strike iran', 'bombing iran', 'war with iran']
    },
    'israel_gaza': {
        'name': 'Israel-Gaza War',
        'keywords': ['gaza', 'israel', 'hamas', 'idf', 'tel aviv', 'netanyahu', 'hezbollah'],
        'escalation_keywords': ['ground invasion', 'mass casualties', 'escalation']
    },
    'russia_ukraine': {
        'name': 'Russia-Ukraine War',
        'keywords': ['ukraine', 'russia', 'kyiv', 'moscow', 'putin', 'zelensky'],
        'escalation_keywords': ['nuclear threat', 'nato troops', 'offensive']
    },
    'us_china': {
        'name': 'US-China Relations',
        'keywords': ['china', 'beijing', 'taiwan', 'south china sea'],
        'escalation_keywords': ['military confrontation', 'invasion taiwan']
    },
    'korean_peninsula': {
        'name': 'Korean Peninsula',
        'keywords': ['north korea', 'south korea', 'kim jong', 'pyongyang'],
        'escalation_keywords': ['missile launch', 'nuclear test']
    },
    'arctic_greenland': {
        'name': 'Arctic & Greenland',
        'keywords': ['greenland', 'arctic', 'denmark'],
        'escalation_keywords': ['military deployment', 'annexation']
    },
    'syria': {
        'name': 'Syria Situation',
        'keywords': ['syria', 'damascus', 'assad'],
        'escalation_keywords': ['chemical weapons', 'isis']
    },
    'taiwan_strait': {
        'name': 'Taiwan Strait',
        'keywords': ['taiwan', 'taipei', 'strait'],
        'escalation_keywords': ['chinese naval', 'invasion']
    },
    'us_domestic': {
        'name': 'US Domestic Politics',
        'keywords': ['trump', 'biden', 'congress', 'white house'],
        'escalation_keywords': ['impeachment', 'crisis']
    }
}

WORLD_CITIES = {
    'washington_dc': {'name': 'Washington D.C.', 'lat': 38.9072, 'lon': -77.0369, 'country': 'USA'},
    'tehran': {'name': 'Tehran', 'lat': 35.6892, 'lon': 51.3890, 'country': 'Iran'},
    'tel_aviv': {'name': 'Tel Aviv', 'lat': 32.0853, 'lon': 34.7818, 'country': 'Israel'},
    'moscow': {'name': 'Moscow', 'lat': 55.7558, 'lon': 37.6173, 'country': 'Russia'},
    'kyiv': {'name': 'Kyiv', 'lat': 50.4501, 'lon': 30.5234, 'country': 'Ukraine'},
    'beijing': {'name': 'Beijing', 'lat': 39.9042, 'lon': 116.4074, 'country': 'China'},
}

def assess_threat_level(items):
    if not items:
        return 'green'
    
    total_text = ' '.join([item.get('title', '') + ' ' + item.get('description', '') for item in items]).lower()
    critical = ['imminent', 'hours away', 'preparing to strike', 'war declared']
    elevated = ['tensions rising', 'troops deployed', 'military buildup']
    
    if any(k in total_text for k in critical):
        return 'red'
    elif sum(1 for k in elevated if k in total_text) >= 2:
        return 'yellow'
    return 'green'

def categorize_by_conflict(text):
    text = text.lower()
    conflicts = []
    for conflict_key, conflict_info in CONFLICTS.items():
        if any(k in text for k in conflict_info['keywords']):
            conflicts.append(conflict_key)
    return conflicts if conflicts else ['uncategorized']

def process_intelligence(title, description, source, link=''):
    """Process and broadcast new intelligence"""
    timestamp = datetime.now().isoformat()
    text = title + ' ' + description
    conflicts = categorize_by_conflict(text)
    
    intel = {
        'title': title,
        'description': description[:300],
        'source': source,
        'link': link,
        'timestamp': timestamp,
        'conflicts': conflicts,
        'id': int(time.time() * 1000)
    }
    
    # Add to stream
    intelligence_stream.appendleft(intel)
    
    # Add to conflict categories
    for conflict in conflicts:
        if conflict not in conflict_data:
            conflict_data[conflict] = []
        conflict_data[conflict].insert(0, intel)
        # Keep only last 100 per conflict
        conflict_data[conflict] = conflict_data[conflict][:100]
    
    # Broadcast via WebSocket
    socketio.emit('new_intelligence', intel, broadcast=True)
    
    print(f"[INTEL] {source}: {title[:50]}")
    return intel

# Telegram Bot Handler
telegram_apps = {}

async def telegram_message_handler(update, context):
    """Handle incoming Telegram messages"""
    try:
        chat = update.effective_chat
        message = update.message
        
        if not message or not message.text:
            return
        
        source_name = chat.title or chat.username or 'Telegram'
        
        process_intelligence(
            title=f"[{source_name}] New Update",
            description=message.text,
            source='telegram',
            link=f"https://t.me/{chat.username}/{message.message_id}" if chat.username else ''
        )
    except Exception as e:
        print(f"[ERROR] Telegram handler: {e}")

def start_telegram_monitor(bot_token, channel_username):
    """Start monitoring a Telegram channel"""
    try:
        async def run_bot():
            application = Application.builder().token(bot_token).build()
            application.add_handler(MessageHandler(filters.ALL, telegram_message_handler))
            await application.initialize()
            await application.start()
            await application.updater.start_polling()
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_bot())
        
    except Exception as e:
        print(f"[ERROR] Telegram monitor: {e}")

# Twitter Stream Handler
class TwitterStreamListener(tweepy.StreamingClient):
    def on_tweet(self, tweet):
        try:
            process_intelligence(
                title=f"@{tweet.author.username}",
                description=tweet.text,
                source='twitter',
                link=f"https://twitter.com/i/web/status/{tweet.id}"
            )
        except Exception as e:
            print(f"[ERROR] Twitter handler: {e}")

twitter_stream = None

def start_twitter_monitor(bearer_token, keywords):
    """Start monitoring Twitter for keywords"""
    global twitter_stream
    try:
        twitter_stream = TwitterStreamListener(bearer_token)
        
        # Delete existing rules
        rules = twitter_stream.get_rules()
        if rules.data:
            twitter_stream.delete_rules([rule.id for rule in rules.data])
        
        # Add new rules
        for keyword in keywords:
            twitter_stream.add_rules(tweepy.StreamRule(keyword))
        
        # Start stream
        twitter_stream.filter(tweet_fields=['author_id', 'created_at'])
        
    except Exception as e:
        print(f"[ERROR] Twitter monitor: {e}")

# API Endpoints
@app.route('/api/sources', methods=['POST'])
def add_source():
    """Add a monitoring source"""
    data = request.json
    source_type = data.get('type')  # 'telegram' or 'twitter'
    
    if source_type == 'telegram':
        bot_token = data.get('bot_token')
        channel = data.get('channel')
        
        if not bot_token or not channel:
            return jsonify({'success': False, 'error': 'Missing bot_token or channel'}), 400
        
        # Start monitoring in background thread
        thread = Thread(target=start_telegram_monitor, args=(bot_token, channel), daemon=True)
        thread.start()
        
        source_id = f"tg_{channel}"
        active_sources[source_id] = {
            'type': 'telegram',
            'channel': channel,
            'started': datetime.now().isoformat()
        }
        
        return jsonify({'success': True, 'source_id': source_id})
    
    elif source_type == 'twitter':
        bearer_token = data.get('bearer_token')
        keywords = data.get('keywords', [])
        
        if not bearer_token or not keywords:
            return jsonify({'success': False, 'error': 'Missing bearer_token or keywords'}), 400
        
        # Start monitoring in background thread
        thread = Thread(target=start_twitter_monitor, args=(bearer_token, keywords), daemon=True)
        thread.start()
        
        source_id = f"tw_{int(time.time())}"
        active_sources[source_id] = {
            'type': 'twitter',
            'keywords': keywords,
            'started': datetime.now().isoformat()
        }
        
        return jsonify({'success': True, 'source_id': source_id})
    
    return jsonify({'success': False, 'error': 'Invalid source type'}), 400

@app.route('/api/sources', methods=['GET'])
def get_sources():
    """Get active monitoring sources"""
    return jsonify(active_sources)

@app.route('/api/stream', methods=['GET'])
def get_stream():
    """Get recent intelligence stream"""
    limit = int(request.args.get('limit', 100))
    return jsonify(list(intelligence_stream)[:limit])

@app.route('/api/conflicts', methods=['GET'])
def get_conflicts():
    """Get conflicts with threat levels"""
    result = {}
    for conflict_key, conflict_info in CONFLICTS.items():
        items = conflict_data.get(conflict_key, [])
        result[conflict_key] = {
            'name': conflict_info['name'],
            'threat_level': assess_threat_level(items),
            'count': len(items),
            'items': items[:50]  # Return last 50
        }
    
    result['uncategorized'] = {
        'name': 'Other News',
        'threat_level': 'green',
        'count': len(conflict_data.get('uncategorized', [])),
        'items': conflict_data.get('uncategorized', [])[:50]
    }
    
    return jsonify(result)

@app.route('/api/cities', methods=['GET'])
def get_cities():
    """Get city threat levels"""
    return jsonify({k: {**v, 'threat': 'green', 'count': 0} for k, v in WORLD_CITIES.items()})

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'healthy',
        'sources': len(active_sources),
        'intel_count': len(intelligence_stream),
        'timestamp': datetime.now().isoformat()
    })

@app.route('/', methods=['GET'])
def home():
    return jsonify({'service': 'OSINT Real-Time Monitor', 'status': 'running'})

# WebSocket event
@socketio.on('connect')
def handle_connect():
    print('[WEBSOCKET] Client connected')
    emit('connection_status', {'status': 'connected'})

@socketio.on('disconnect')
def handle_disconnect():
    print('[WEBSOCKET] Client disconnected')

if __name__ == '__main__':
    print("[STARTUP] OSINT Real-Time Monitor")
    print("[INFO] Waiting for source configuration...")
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
