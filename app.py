from flask import Flask, jsonify, request
from flask_cors import CORS
import feedparser
import schedule
import time
import os
from datetime import datetime
from threading import Thread
import re
import requests

app = Flask(__name__)

CORS(app, resources={
    r"/api/*": {
        "origins": "*",
        "methods": ["GET", "POST", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type"]
    }
})

# Storage
feeds_storage = {}
conflict_data = {}

# Conflict definitions
CONFLICTS = {
    'us_iran': {
        'name': 'US-Iran Tensions',
        'keywords': ['iran', 'tehran', 'centcom', 'irgc', 'strait of hormuz', 'persian gulf', 'nuclear deal', 'sanctions iran'],
        'escalation_keywords': ['strike iran', 'bombing iran', 'military action iran', 'war with iran', 'attack iran', 'iranian retaliation']
    },
    'israel_gaza': {
        'name': 'Israel-Gaza War',
        'keywords': ['gaza', 'israel', 'hamas', 'idf', 'tel aviv', 'netanyahu', 'west bank', 'hezbollah lebanon'],
        'escalation_keywords': ['ground invasion', 'mass casualties gaza', 'escalation lebanon', 'wider war', 'regional conflict']
    },
    'russia_ukraine': {
        'name': 'Russia-Ukraine War',
        'keywords': ['ukraine', 'russia', 'kyiv', 'moscow', 'putin', 'zelensky', 'donbas', 'crimea', 'nato ukraine'],
        'escalation_keywords': ['nuclear threat', 'nato troops', 'offensive kyiv', 'tactical nuclear', 'article 5']
    },
    'us_china': {
        'name': 'US-China Relations',
        'keywords': ['china', 'beijing', 'xi jinping', 'south china sea', 'trade war china', 'chips act'],
        'escalation_keywords': ['military confrontation', 'blockade taiwan', 'invasion taiwan', 'us carrier strike']
    },
    'korean_peninsula': {
        'name': 'Korean Peninsula',
        'keywords': ['north korea', 'south korea', 'kim jong', 'pyongyang', 'seoul', 'nuclear test north korea'],
        'escalation_keywords': ['missile launch korea', 'nuclear test', 'war footing', 'dmz incident']
    },
    'arctic_greenland': {
        'name': 'Arctic & Greenland',
        'keywords': ['greenland', 'arctic', 'denmark', 'trump greenland', 'northwest passage', 'arctic sovereignty'],
        'escalation_keywords': ['military deployment greenland', 'annexation', 'arctic conflict']
    },
    'syria': {
        'name': 'Syria Situation',
        'keywords': ['syria', 'damascus', 'assad', 'rebels syria', 'kurdish syria'],
        'escalation_keywords': ['chemical weapons', 'turkish invasion', 'isis resurgence']
    },
    'taiwan_strait': {
        'name': 'Taiwan Strait',
        'keywords': ['taiwan', 'taipei', 'strait crossing', 'china taiwan'],
        'escalation_keywords': ['chinese naval', 'invasion preparation', 'taiwanese mobilization']
    },
    'us_domestic': {
        'name': 'US Domestic Politics',
        'keywords': ['trump', 'biden', 'congress', 'senate', 'white house', 'supreme court', 'election', 'capitol'],
        'escalation_keywords': ['impeachment', 'constitutional crisis', 'political violence', 'insurrection']
    }
}

WORLD_CITIES = {
    'washington_dc': {'name': 'Washington D.C.', 'lat': 38.9072, 'lon': -77.0369, 'country': 'USA'},
    'tehran': {'name': 'Tehran', 'lat': 35.6892, 'lon': 51.3890, 'country': 'Iran'},
    'tel_aviv': {'name': 'Tel Aviv', 'lat': 32.0853, 'lon': 34.7818, 'country': 'Israel'},
    'moscow': {'name': 'Moscow', 'lat': 55.7558, 'lon': 37.6173, 'country': 'Russia'},
    'kyiv': {'name': 'Kyiv', 'lat': 50.4501, 'lon': 30.5234, 'country': 'Ukraine'},
    'beijing': {'name': 'Beijing', 'lat': 39.9042, 'lon': 116.4074, 'country': 'China'},
    'seoul': {'name': 'Seoul', 'lat': 37.5665, 'lon': 126.9780, 'country': 'South Korea'},
    'damascus': {'name': 'Damascus', 'lat': 33.5138, 'lon': 36.2765, 'country': 'Syria'},
    'taipei': {'name': 'Taipei', 'lat': 25.0330, 'lon': 121.5654, 'country': 'Taiwan'},
}

def assess_threat_level(items):
    if not items:
        return 'green'
    
    total_text = ' '.join([item.get('title', '') + ' ' + item.get('description', '') for item in items]).lower()
    
    critical_keywords = ['imminent', 'hours away', 'preparing to strike', 'red alert', 'mobilization complete', 'war declared']
    elevated_keywords = ['tensions rising', 'troops deployed', 'military buildup', 'threatening', 'brink of war']
    
    if any(kw in total_text for kw in critical_keywords):
        return 'red'
    elif sum(1 for kw in elevated_keywords if kw in total_text) >= 2:
        return 'yellow'
    elif any(kw in total_text for kw in elevated_keywords):
        return 'yellow'
    return 'green'

def categorize_by_conflict(title, description):
    text = (title + ' ' + description).lower()
    conflicts_found = []
    
    for conflict_key, conflict_info in CONFLICTS.items():
        if any(keyword in text for keyword in conflict_info['keywords']):
            conflicts_found.append(conflict_key)
    
    return conflicts_found if conflicts_found else ['uncategorized']

def fetch_feed(feed_id, feed_url):
    try:
        print(f"[FETCH] {feed_url}")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/rss+xml, application/xml, text/xml, */*'
        }
        
        response = requests.get(feed_url, headers=headers, timeout=30)
        
        if response.status_code != 200:
            print(f"[ERROR] HTTP {response.status_code}")
            return []
        
        feed = feedparser.parse(response.content)
        
        if not feed.entries:
            print(f"[WARNING] No entries in feed")
            return []
        
        items = []
        for entry in feed.entries[:15]:
            title = entry.get('title', 'No title')
            description = entry.get('description', entry.get('summary', ''))
            link = entry.get('link', '')
            pub_date = entry.get('published', entry.get('updated', ''))
            
            clean_desc = re.sub('<[^<]+?>', '', description)
            conflicts = categorize_by_conflict(title, clean_desc)
            
            items.append({
                'title': title,
                'description': clean_desc[:300],
                'link': link,
                'timestamp': pub_date,
                'conflicts': conflicts,
                'feed_id': feed_id
            })
        
        print(f"[SUCCESS] {len(items)} items")
        return items
        
    except Exception as e:
        print(f"[ERROR] {e}")
        return []

def update_all_feeds():
    global conflict_data
    
    print(f"[UPDATE] Starting at {datetime.now()}")
    
    conflict_data = {k: [] for k in CONFLICTS.keys()}
    conflict_data['uncategorized'] = []
    
    total_items = 0
    for feed_id, feed_info in feeds_storage.items():
        items = fetch_feed(feed_id, feed_info['url'])
        total_items += len(items)
        
        feeds_storage[feed_id]['items'] = items
        feeds_storage[feed_id]['last_update'] = datetime.now().isoformat()
        
        for item in items:
            for conflict in item['conflicts']:
                if conflict in conflict_data:
                    conflict_data[conflict].append(item)
    
    print(f"[UPDATE] Complete: {len(feeds_storage)} feeds, {total_items} items")

def background_updater():
    print("[BACKGROUND] Starting updater")
    time.sleep(3)
    update_all_feeds()
    
    schedule.every(2).minutes.do(update_all_feeds)
    
    while True:
        schedule.run_pending()
        time.sleep(30)

@app.route('/api/feeds', methods=['GET'])
def get_feeds():
    return jsonify(list(feeds_storage.values()))

@app.route('/api/feeds', methods=['POST'])
def add_feed():
    data = request.json
    feed_id = str(int(time.time() * 1000))
    
    feeds_storage[feed_id] = {
        'id': feed_id,
        'name': data['name'],
        'url': data['url'],
        'source': data.get('source', 'telegram'),
        'items': [],
        'last_update': None
    }
    
    items = fetch_feed(feed_id, data['url'])
    feeds_storage[feed_id]['items'] = items
    feeds_storage[feed_id]['last_update'] = datetime.now().isoformat()
    
    for item in items:
        for conflict in item['conflicts']:
            if conflict not in conflict_data:
                conflict_data[conflict] = []
            conflict_data[conflict].append(item)
    
    return jsonify({'success': True, 'feed': feeds_storage[feed_id]})

@app.route('/api/feeds/<feed_id>', methods=['DELETE'])
def delete_feed(feed_id):
    if feed_id in feeds_storage:
        del feeds_storage[feed_id]
        return jsonify({'success': True})
    return jsonify({'success': False}), 404

@app.route('/api/conflicts', methods=['GET'])
def get_conflicts():
    result = {}
    for conflict_key, conflict_info in CONFLICTS.items():
        items = conflict_data.get(conflict_key, [])
        result[conflict_key] = {
            'name': conflict_info['name'],
            'threat_level': assess_threat_level(items),
            'count': len(items),
            'items': items
        }
    
    result['uncategorized'] = {
        'name': 'Other News',
        'threat_level': 'green',
        'count': len(conflict_data.get('uncategorized', [])),
        'items': conflict_data.get('uncategorized', [])
    }
    
    return jsonify(result)

@app.route('/api/cities', methods=['GET'])
def get_cities():
    city_threats = {}
    
    for city_key, city_info in WORLD_CITIES.items():
        city_threats[city_key] = {
            'name': city_info['name'],
            'lat': city_info['lat'],
            'lon': city_info['lon'],
            'country': city_info['country'],
            'threat': 'green',
            'count': 0
        }
    
    return jsonify(city_threats)

@app.route('/api/refresh', methods=['POST'])
def manual_refresh():
    try:
        update_all_feeds()
        return jsonify({'success': True, 'timestamp': datetime.now().isoformat()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'feeds_count': len(feeds_storage),
        'timestamp': datetime.now().isoformat()
    })

@app.route('/', methods=['GET'])
def home():
    return jsonify({'service': 'OSINT Monitor v2', 'status': 'running'})

if __name__ == '__main__':
    updater_thread = Thread(target=background_updater, daemon=True)
    updater_thread.start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
