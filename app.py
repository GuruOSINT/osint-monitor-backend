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

# Configure CORS to allow requests from any origin
CORS(app, resources={
    r"/api/*": {
        "origins": "*",
        "methods": ["GET", "POST", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type"]
    }
})

# Storage for feeds and their data
feeds_storage = {}
categorized_data = {
    'middle_east': [],
    'europe': [],
    'asia': [],
    'americas': [],
    'africa': [],
    'uncategorized': [],
    'us_politics': []
}

# City-level tracking
city_data = {}

# Major world cities with coordinates
WORLD_CITIES = {
    # Americas
    'washington_dc': {'name': 'Washington D.C.', 'lat': 38.9072, 'lon': -77.0369, 'region': 'americas'},
    'new_york': {'name': 'New York', 'lat': 40.7128, 'lon': -74.0060, 'region': 'americas'},
    'mexico_city': {'name': 'Mexico City', 'lat': 19.4326, 'lon': -99.1332, 'region': 'americas'},
    'caracas': {'name': 'Caracas', 'lat': 10.4806, 'lon': -66.9036, 'region': 'americas'},
    'brasilia': {'name': 'Brasília', 'lat': -15.8267, 'lon': -47.9218, 'region': 'americas'},
    
    # Europe
    'london': {'name': 'London', 'lat': 51.5074, 'lon': -0.1278, 'region': 'europe'},
    'paris': {'name': 'Paris', 'lat': 48.8566, 'lon': 2.3522, 'region': 'europe'},
    'berlin': {'name': 'Berlin', 'lat': 52.5200, 'lon': 13.4050, 'region': 'europe'},
    'moscow': {'name': 'Moscow', 'lat': 55.7558, 'lon': 37.6173, 'region': 'europe'},
    'kyiv': {'name': 'Kyiv', 'lat': 50.4501, 'lon': 30.5234, 'region': 'europe'},
    'warsaw': {'name': 'Warsaw', 'lat': 52.2297, 'lon': 21.0122, 'region': 'europe'},
    
    # Middle East
    'tehran': {'name': 'Tehran', 'lat': 35.6892, 'lon': 51.3890, 'region': 'middle_east'},
    'tel_aviv': {'name': 'Tel Aviv', 'lat': 32.0853, 'lon': 34.7818, 'region': 'middle_east'},
    'jerusalem': {'name': 'Jerusalem', 'lat': 31.7683, 'lon': 35.2137, 'region': 'middle_east'},
    'baghdad': {'name': 'Baghdad', 'lat': 33.3152, 'lon': 44.3661, 'region': 'middle_east'},
    'damascus': {'name': 'Damascus', 'lat': 33.5138, 'lon': 36.2765, 'region': 'middle_east'},
    'beirut': {'name': 'Beirut', 'lat': 33.8886, 'lon': 35.4955, 'region': 'middle_east'},
    'riyadh': {'name': 'Riyadh', 'lat': 24.7136, 'lon': 46.6753, 'region': 'middle_east'},
    'cairo': {'name': 'Cairo', 'lat': 30.0444, 'lon': 31.2357, 'region': 'middle_east'},
    'dubai': {'name': 'Dubai', 'lat': 25.2048, 'lon': 55.2708, 'region': 'middle_east'},
    
    # Asia
    'beijing': {'name': 'Beijing', 'lat': 39.9042, 'lon': 116.4074, 'region': 'asia'},
    'tokyo': {'name': 'Tokyo', 'lat': 35.6762, 'lon': 139.6503, 'region': 'asia'},
    'seoul': {'name': 'Seoul', 'lat': 37.5665, 'lon': 126.9780, 'region': 'asia'},
    'new_delhi': {'name': 'New Delhi', 'lat': 28.6139, 'lon': 77.2090, 'region': 'asia'},
    'islamabad': {'name': 'Islamabad', 'lat': 33.6844, 'lon': 73.0479, 'region': 'asia'},
    'bangkok': {'name': 'Bangkok', 'lat': 13.7563, 'lon': 100.5018, 'region': 'asia'},
    'manila': {'name': 'Manila', 'lat': 14.5995, 'lon': 120.9842, 'region': 'asia'},
    
    # Africa
    'nairobi': {'name': 'Nairobi', 'lat': -1.2864, 'lon': 36.8172, 'region': 'africa'},
    'lagos': {'name': 'Lagos', 'lat': 6.5244, 'lon': 3.3792, 'region': 'africa'},
    'addis_ababa': {'name': 'Addis Ababa', 'lat': 9.0320, 'lon': 38.7469, 'region': 'africa'},
    'khartoum': {'name': 'Khartoum', 'lat': 15.5007, 'lon': 32.5599, 'region': 'africa'},
}

# Keywords for auto-categorization
REGION_KEYWORDS = {
    'middle_east': ['israel', 'gaza', 'palestine', 'iran', 'iraq', 'syria', 'lebanon', 'yemen', 'saudi', 'uae', 'turkey', 'egypt'],
    'europe': ['ukraine', 'russia', 'nato', 'eu', 'moscow', 'kyiv', 'kiev', 'poland', 'germany', 'france', 'uk', 'britain'],
    'asia': ['china', 'taiwan', 'japan', 'korea', 'india', 'pakistan', 'philippines', 'vietnam', 'beijing'],
    'americas': ['mexico', 'canada', 'brazil', 'venezuela', 'colombia', 'argentina'],
    'africa': ['sudan', 'ethiopia', 'somalia', 'nigeria', 'libya', 'congo', 'sahel'],
    'us_politics': ['trump', 'biden', 'congress', 'senate', 'white house', 'supreme court', 'election', 'republican', 'democrat', 'washington', 'capitol']
}

CITY_KEYWORDS = {
    'washington_dc': ['washington', 'dc', 'white house', 'capitol', 'pentagon'],
    'new_york': ['new york', 'nyc', 'manhattan'],
    'moscow': ['moscow', 'kremlin'],
    'kyiv': ['kyiv', 'kiev'],
    'london': ['london', 'uk'],
    'paris': ['paris', 'france'],
    'berlin': ['berlin', 'germany'],
    'tehran': ['tehran', 'iran'],
    'tel_aviv': ['tel aviv', 'israel'],
    'jerusalem': ['jerusalem'],
    'baghdad': ['baghdad'],
    'damascus': ['damascus', 'syria'],
    'beirut': ['beirut', 'lebanon'],
    'beijing': ['beijing', 'china'],
    'tokyo': ['tokyo', 'japan'],
    'seoul': ['seoul', 'korea'],
    'cairo': ['cairo', 'egypt'],
    'riyadh': ['riyadh', 'saudi'],
    'mexico_city': ['mexico city'],
    'caracas': ['caracas', 'venezuela'],
}

CONFLICT_KEYWORDS = ['war', 'conflict', 'strike', 'attack', 'military', 'troops', 'casualties', 'combat', 'offensive', 'defense', 'bombing', 'explosion']

def categorize_item(title, description):
    """Categorize item by region based on keywords"""
    text = (title + ' ' + description).lower()
    
    # Check for US politics first
    us_keywords = REGION_KEYWORDS.get('us_politics', [])
    if any(keyword in text for keyword in us_keywords):
        return 'us_politics'
    
    for region, keywords in REGION_KEYWORDS.items():
        if region == 'us_politics':
            continue
        if any(keyword in text for keyword in keywords):
            return region
    
    return 'uncategorized'

def categorize_by_city(title, description):
    """Categorize item by city"""
    text = (title + ' ' + description).lower()
    cities_found = []
    
    for city_key, keywords in CITY_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            cities_found.append(city_key)
    
    return cities_found

def calculate_priority(title, description):
    """Calculate priority based on conflict keywords"""
    text = (title + ' ' + description).lower()
    
    conflict_count = sum(1 for keyword in CONFLICT_KEYWORDS if keyword in text)
    
    if conflict_count >= 3:
        return 'high'
    elif conflict_count >= 1:
        return 'medium'
    else:
        return 'low'

def fetch_feed(feed_id, feed_url):
    """Fetch and parse RSS feed"""
    try:
        print(f"[DEBUG] Fetching feed {feed_id} from {feed_url}")
        
        # Add user agent and headers to avoid being blocked
        feed = feedparser.parse(feed_url, agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        print(f"[DEBUG] Feed status: {feed.get('status', 'unknown')}")
        print(f"[DEBUG] Feed entries count: {len(feed.entries)}")
        
        # Check for HTTP errors
        if hasattr(feed, 'status') and feed.status == 403:
            print(f"[ERROR] 403 Forbidden - RSSHub is blocking this request")
            print(f"[INFO] Trying alternative method...")
            # Try with requests library as fallback
            import requests
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'application/rss+xml, application/xml, text/xml, */*'
                }
                response = requests.get(feed_url, headers=headers, timeout=30)
                print(f"[DEBUG] Requests library status: {response.status_code}")
                if response.status_code == 200:
                    feed = feedparser.parse(response.content)
                    print(f"[DEBUG] Retry successful! Entries: {len(feed.entries)}")
            except Exception as req_error:
                print(f"[ERROR] Requests fallback failed: {req_error}")
        
        if hasattr(feed, 'bozo') and feed.bozo:
            print(f"[DEBUG] Feed parsing warning: {feed.bozo_exception}")
        
        items = []
        for entry in feed.entries[:15]:
            title = entry.get('title', 'No title')
            description = entry.get('description', entry.get('summary', ''))
            link = entry.get('link', '')
            pub_date = entry.get('published', entry.get('updated', ''))
            
            # Remove HTML tags from description
            clean_desc = re.sub('<[^<]+?>', '', description)
            
            region = categorize_item(title, clean_desc)
            priority = calculate_priority(title, clean_desc)
            cities = categorize_by_city(title, clean_desc)
            
            item = {
                'title': title,
                'description': clean_desc[:300],
                'link': link,
                'timestamp': pub_date,
                'region': region,
                'priority': priority,
                'cities': cities,
                'feed_id': feed_id
            }
            
            items.append(item)
            print(f"[DEBUG] Added item: {title[:50]}")
        
        print(f"[DEBUG] Successfully parsed {len(items)} items from feed {feed_id}")
        return items
    except Exception as e:
        print(f"[ERROR] Error fetching feed {feed_id}: {str(e)}")
        import traceback
        traceback.print_exc()
        return []

def update_all_feeds():
    """Update all registered feeds"""
    global categorized_data, city_data
    
    # Reset categorized data
    for region in categorized_data:
        categorized_data[region] = []
    
    # Reset city data
    city_data = {city: [] for city in WORLD_CITIES.keys()}
    
    for feed_id, feed_info in feeds_storage.items():
        items = fetch_feed(feed_id, feed_info['url'])
        
        # Store in feed's own storage
        feeds_storage[feed_id]['items'] = items
        feeds_storage[feed_id]['last_update'] = datetime.now().isoformat()
        
        # Categorize items by region and city
        for item in items:
            region = item['region']
            categorized_data[region].append(item)
            
            # Add to city data
            for city in item.get('cities', []):
                if city in city_data:
                    city_data[city].append(item)
    
    print(f"Updated {len(feeds_storage)} feeds at {datetime.now()}")

def background_updater():
    """Run scheduled updates in background"""
    schedule.every(2).minutes.do(update_all_feeds)
    
    while True:
        schedule.run_pending()
        time.sleep(30)

# API Endpoints
@app.route('/api/feeds', methods=['GET'])
def get_feeds():
    """Get all registered feeds"""
    return jsonify(list(feeds_storage.values()))

@app.route('/api/feeds', methods=['POST'])
def add_feed():
    """Add a new feed"""
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
    
    # Immediately fetch the new feed
    items = fetch_feed(feed_id, data['url'])
    feeds_storage[feed_id]['items'] = items
    feeds_storage[feed_id]['last_update'] = datetime.now().isoformat()
    
    # Update categorized data with new items
    for item in items:
        region = item['region']
        if region in categorized_data:
            categorized_data[region].append(item)
        
        # Update city data
        for city in item.get('cities', []):
            if city not in city_data:
                city_data[city] = []
            city_data[city].append(item)
    
    return jsonify({'success': True, 'feed': feeds_storage[feed_id]})

@app.route('/api/feeds/<feed_id>', methods=['DELETE'])
def delete_feed(feed_id):
    """Delete a feed"""
    if feed_id in feeds_storage:
        del feeds_storage[feed_id]
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Feed not found'}), 404

@app.route('/api/categorized', methods=['GET'])
def get_categorized():
    """Get all items categorized by region"""
    return jsonify(categorized_data)

@app.route('/api/cities', methods=['GET'])
def get_cities():
    """Get city data with activity levels"""
    city_activity = {}
    for city_key, city_info in WORLD_CITIES.items():
        item_count = len(city_data.get(city_key, []))
        
        # Determine activity level
        if item_count >= 5:
            activity = 'red'
        elif item_count >= 2:
            activity = 'yellow'
        else:
            activity = 'green'
        
        city_activity[city_key] = {
            'name': city_info['name'],
            'lat': city_info['lat'],
            'lon': city_info['lon'],
            'region': city_info['region'],
            'count': item_count,
            'activity': activity,
            'items': city_data.get(city_key, [])
        }
    
    return jsonify(city_activity)

@app.route('/api/city/<city_key>', methods=['GET'])
def get_city_items(city_key):
    """Get items for a specific city"""
    if city_key in city_data:
        return jsonify({
            'city': WORLD_CITIES.get(city_key, {}).get('name', city_key),
            'items': city_data[city_key]
        })
    return jsonify({'city': city_key, 'items': []})

@app.route('/api/refresh', methods=['POST'])
def refresh_feeds():
    """Manually trigger feed refresh"""
    update_all_feeds()
    return jsonify({'success': True, 'timestamp': datetime.now().isoformat()})

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'feeds_count': len(feeds_storage),
        'timestamp': datetime.now().isoformat()
    })

@app.route('/', methods=['GET'])
def home():
    """Root endpoint"""
    return jsonify({
        'service': 'OSINT Monitor Backend',
        'status': 'running',
        'endpoints': {
            'GET /api/health': 'Health check',
            'GET /api/feeds': 'Get all feeds',
            'POST /api/feeds': 'Add new feed',
            'DELETE /api/feeds/<id>': 'Delete feed',
            'GET /api/categorized': 'Get categorized items',
            'GET /api/cities': 'Get city activity map',
            'GET /api/city/<key>': 'Get items for specific city',
            'POST /api/refresh': 'Refresh all feeds'
        }
    })

if __name__ == '__main__':
    # Start background updater thread
    updater_thread = Thread(target=background_updater, daemon=True)
    updater_thread.start()
    
    # Run Flask app
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
