from flask import Flask, jsonify, request
from flask_cors import CORS
import feedparser
import schedule
import time
import os
from datetime import datetime
from threading import Thread
import re

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
city_data = {}

# Conflict definitions with keywords
CONFLICTS = {
    'us_iran': {
        'name': 'US-Iran Tensions',
        'keywords': ['iran', 'tehran', 'centcom', 'irgc', 'strait of hormuz', 'persian gulf', 'nuclear deal', 'sanctions iran'],
        'escalation_keywords': ['strike iran', 'bombing iran', 'military action iran', 'war with iran', 'attack iran', 'iranian retaliation'],
        'cities': ['tehran', 'washington_dc']
    },
    'israel_gaza': {
        'name': 'Israel-Gaza War',
        'keywords': ['gaza', 'israel', 'hamas', 'idf', 'tel aviv', 'netanyahu', 'west bank', 'hezbollah lebanon'],
        'escalation_keywords': ['ground invasion', 'mass casualties gaza', 'escalation lebanon', 'wider war', 'regional conflict'],
        'cities': ['tel_aviv', 'jerusalem', 'beirut']
    },
    'russia_ukraine': {
        'name': 'Russia-Ukraine War',
        'keywords': ['ukraine', 'russia', 'kyiv', 'moscow', 'putin', 'zelensky', 'donbas', 'crimea', 'nato ukraine'],
        'escalation_keywords': ['nuclear threat', 'nato troops', 'offensive kyiv', 'tactical nuclear', 'article 5'],
        'cities': ['kyiv', 'moscow', 'warsaw']
    },
    'us_china': {
        'name': 'US-China Relations',
        'keywords': ['china', 'beijing', 'xi jinping', 'south china sea', 'trade war china', 'chips act'],
        'escalation_keywords': ['military confrontation', 'blockade taiwan', 'invasion taiwan', 'us carrier strike'],
        'cities': ['beijing', 'washington_dc', 'taipei']
    },
    'korean_peninsula': {
        'name': 'Korean Peninsula',
        'keywords': ['north korea', 'south korea', 'kim jong', 'pyongyang', 'seoul', 'nuclear test north korea'],
        'escalation_keywords': ['missile launch korea', 'nuclear test', 'war footing', 'dmz incident'],
        'cities': ['seoul', 'pyongyang']
    },
    'arctic_greenland': {
        'name': 'Arctic & Greenland',
        'keywords': ['greenland', 'arctic', 'denmark', 'trump greenland', 'northwest passage', 'arctic sovereignty'],
        'escalation_keywords': ['military deployment greenland', 'annexation', 'arctic conflict'],
        'cities': ['washington_dc', 'copenhagen']
    },
    'syria': {
        'name': 'Syria Situation',
        'keywords': ['syria', 'damascus', 'assad', 'rebels syria', 'kurdish syria'],
        'escalation_keywords': ['chemical weapons', 'turkish invasion', 'isis resurgence'],
        'cities': ['damascus', 'beirut', 'ankara']
    },
    'taiwan_strait': {
        'name': 'Taiwan Strait',
        'keywords': ['taiwan', 'taipei', 'strait crossing', 'china taiwan'],
        'escalation_keywords': ['chinese naval', 'invasion preparation', 'taiwanese mobilization'],
        'cities': ['taipei', 'beijing']
    },
    'us_domestic': {
        'name': 'US Domestic Politics',
        'keywords': ['trump', 'biden', 'congress', 'senate', 'white house', 'supreme court', 'election', 'capitol'],
        'escalation_keywords': ['impeachment', 'constitutional crisis', 'political violence', 'insurrection'],
        'cities': ['washington_dc', 'new_york']
    }
}

# Major cities
WORLD_CITIES = {
    'washington_dc': {'name': 'Washington D.C.', 'lat': 38.9072, 'lon': -77.0369, 'country': 'USA'},
    'new_york': {'name': 'New York', 'lat': 40.7128, 'lon': -74.0060, 'country': 'USA'},
    'london': {'name': 'London', 'lat': 51.5074, 'lon': -0.1278, 'country': 'UK'},
    'paris': {'name': 'Paris', 'lat': 48.8566, 'lon': 2.3522, 'country': 'France'},
    'berlin': {'name': 'Berlin', 'lat': 52.5200, 'lon': 13.4050, 'country': 'Germany'},
    'moscow': {'name': 'Moscow', 'lat': 55.7558, 'lon': 37.6173, 'country': 'Russia'},
    'kyiv': {'name': 'Kyiv', 'lat': 50.4501, 'lon': 30.5234, 'country': 'Ukraine'},
    'tehran': {'name': 'Tehran', 'lat': 35.6892, 'lon': 51.3890, 'country': 'Iran'},
    'tel_aviv': {'name': 'Tel Aviv', 'lat': 32.0853, 'lon': 34.7818, 'country': 'Israel'},
    'jerusalem': {'name': 'Jerusalem', 'lat': 31.7683, 'lon': 35.2137, 'country': 'Israel'},
    'baghdad': {'name': 'Baghdad', 'lat': 33.3152, 'lon': 44.3661, 'country': 'Iraq'},
    'damascus': {'name': 'Damascus', 'lat': 33.5138, 'lon': 36.2765, 'country': 'Syria'},
    'beirut': {'name': 'Beirut', 'lat': 33.8886, 'lon': 35.4955, 'country': 'Lebanon'},
    'beijing': {'name': 'Beijing', 'lat': 39.9042, 'lon': 116.4074, 'country': 'China'},
    'tokyo': {'name': 'Tokyo', 'lat': 35.6762, 'lon': 139.6503, 'country': 'Japan'},
    'seoul': {'name': 'Seoul', 'lat': 37.5665, 'lon': 126.9780, 'country': 'South Korea'},
    'taipei': {'name': 'Taipei', 'lat': 25.0330, 'lon': 121.5654, 'country': 'Taiwan'},
    'pyongyang': {'name': 'Pyongyang', 'lat': 39.0392, 'lon': 125.7625, 'country': 'North Korea'},
    'copenhagen': {'name': 'Copenhagen', 'lat': 55.6761, 'lon': 12.5683, 'country': 'Denmark'},
    'ankara': {'name': 'Ankara', 'lat': 39.9334, 'lon': 32.8597, 'country': 'Turkey'},
    'warsaw': {'name': 'Warsaw', 'lat': 52.2297, 'lon': 21.0122, 'country': 'Poland'},
}

def assess_threat_level(items):
    """Assess threat level based on escalation keywords"""
    if not items:
        return 'green'
    
    escalation_count = 0
    total_text = ''
    
    for item in items:
        total_text += (item.get('title', '') + ' ' + item.get('description', '')).lower()
    
    # Count escalation indicators
    critical_keywords = ['imminent', 'hours away', 'preparing to strike', 'red alert', 'mobilization complete', 'war declared']
    elevated_keywords = ['tensions rising', 'troops deployed', 'military buildup', 'threatening', 'brink of war', 'evacuation']
    
    critical_score = sum(1 for kw in critical_keywords if kw in total_text)
    elevated_score = sum(1 for kw in elevated_keywords if kw in total_text)
    
    if critical_score >= 2 or 'imminent' in total_text:
        return 'red'
    elif critical_score >= 1 or elevated_score >= 3:
        return 'yellow'
    elif elevated_score >= 1:
        return 'yellow'
    else:
        return 'green'

def categorize_by_conflict(title, description):
    """Categorize item by conflict"""
    text = (title + ' ' + description).lower()
    conflicts_found = []
    
    for conflict_key, conflict_info in CONFLICTS.items():
        keywords = conflict_info['keywords']
        if any(keyword in text for keyword in keywords):
            conflicts_found.append(conflict_key)
    
    return conflicts_found if conflicts_found else ['uncategorized']

def fetch_feed(feed_id, feed_url):
    """Fetch and parse RSS feed"""
    try:
        print(f"[DEBUG] Fetching feed {feed_id} from {feed_url}")
        
        feed = feedparser.parse(feed_url, agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        print(f"[DEBUG] Feed status: {feed.get('status', 'unknown')}")
        print(f"[DEBUG] Feed entries count: {len(feed.entries)}")
        
        if hasattr(feed, 'status') and feed.status == 403:
            print(f"[ERROR] 403 Forbidden")
            import requests
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept': 'application/rss+xml, application/xml, text/xml, */*'
                }
                response = requests.get(feed_url, headers=headers, timeout=30)
                if response.status_code == 200:
                    feed = feedparser.parse(response.content)
            except Exception as req_error:
                print(f"[ERROR] Fallback failed: {req_error}")
        
        items = []
        for entry in feed.entries[:15]:
            title = entry.get('title', 'No title')
            description = entry.get('description', entry.get('summary', ''))
            link = entry.get('link', '')
            pub_date = entry.get('published', entry.get('updated', ''))
            
            clean_desc = re.sub('<[^<]+?>', '', description)
            
            conflicts = categorize_by_conflict(title, clean_desc)
            
            item = {
                'title': title,
                'description': clean_desc[:300],
                'link': link,
                'timestamp': pub_date,
                'conflicts': conflicts,
                'feed_id': feed_id
            }
            
            items.append(item)
        
        print(f"[DEBUG] Successfully parsed {len(items)} items")
        return items
    except Exception as e:
        print(f"[ERROR] Error fetching feed {feed_id}: {str(e)}")
        import traceback
        traceback.print_exc()
        return []

def update_all_feeds():
    """Update all feeds"""
    global conflict_data, city_data
    
    update_start = datetime.now()
    print(f"[UPDATE] Starting feed update cycle at {update_start}")
    
    # Reset
    conflict_data = {k: [] for k in CONFLICTS.keys()}
    conflict_data['uncategorized'] = []
    city_data = {city: [] for city in WORLD_CITIES.keys()}
    
    total_items = 0
    for feed_id, feed_info in feeds_storage.items():
        print(f"[UPDATE] Fetching feed: {feed_info['name']}")
        items = fetch_feed(feed_id, feed_info['url'])
        total_items += len(items)
        
        feeds_storage[feed_id]['items'] = items
        feeds_storage[feed_id]['last_update'] = datetime.now().isoformat()
        
        for item in items:
            for conflict in item['conflicts']:
                if conflict in conflict_data:
                    conflict_data[conflict].append(item)
    
    update_duration = (datetime.now() - update_start).total_seconds()
    print(f"[UPDATE] Completed! Updated {len(feeds_storage)} feeds, {total_items} total items in {update_duration:.2f}s")

def background_updater():
    """Background updates"""
    print("[BACKGROUND] Starting background updater thread")
    
    # Initial update on startup
    time.sleep(5)  # Wait for app to fully start
    print("[BACKGROUND] Running initial feed update")
    update_all_feeds()
    
    schedule.every(2).minutes.do(update_all_feeds)
    
    while True:
        try:
            schedule.run_pending()
            time.sleep(30)
        except Exception as e:
            print(f"[ERROR] Background updater error: {e}")
            time.sleep(30)

# API Endpoints
@app.route('/api/feeds', methods=['GET'])
def get_feeds():
    return jsonify(list(feeds_storage.values()))

@app.route('/api/feeds', methods=['POST'])
def add_feed():
    data = request.json
    feed_id = data.get('id', str(int(time.time() * 1000)))
    
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
    """Get conflicts with threat levels"""
    result = {}
    for conflict_key, conflict_info in CONFLICTS.items():
        items = conflict_data.get(conflict_key, [])
        threat = assess_threat_level(items)
        result[conflict_key] = {
            'name': conflict_info['name'],
            'threat_level': threat,
            'count': len(items),
            'items': items
        }
    
    # Add uncategorized
    result['uncategorized'] = {
        'name': 'Other News',
        'threat_level': 'green',
        'count': len(conflict_data.get('uncategorized', [])),
        'items': conflict_data.get('uncategorized', [])
    }
    
    return jsonify(result)

@app.route('/api/cities', methods=['GET'])
def get_cities():
    """Get city threat levels"""
    city_threats = {}
    
    for city_key, city_info in WORLD_CITIES.items():
        # Find conflicts involving this city
        city_items = []
        for conflict_key, conflict_info in CONFLICTS.items():
            if city_key in conflict_info.get('cities', []):
                city_items.extend(conflict_data.get(conflict_key, []))
        
        threat = assess_threat_level(city_items)
        
        city_threats[city_key] = {
            'name': city_info['name'],
            'lat': city_info['lat'],
            'lon': city_info['lon'],
            'country': city_info['country'],
            'threat': threat,
            'count': len(city_items)
        }
    
    return jsonify(city_threats)

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'feeds_count': len(feeds_storage),
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/refresh', methods=['POST'])
def manual_refresh():
    """Manually trigger feed refresh"""
    try:
        update_all_feeds()
        return jsonify({
            'success': True,
            'timestamp': datetime.now().isoformat(),
            'feeds_updated': len(feeds_storage)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        'service': 'OSINT Monitor Backend v2',
        'status': 'running'
    })

if __name__ == '__main__':
    updater_thread = Thread(target=background_updater, daemon=True)
    updater_thread.start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
