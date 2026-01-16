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
    'uncategorized': []
}

# Keywords for auto-categorization
REGION_KEYWORDS = {
    'middle_east': ['israel', 'gaza', 'palestine', 'iran', 'iraq', 'syria', 'lebanon', 'yemen', 'saudi', 'uae', 'turkey', 'egypt'],
    'europe': ['ukraine', 'russia', 'nato', 'eu', 'moscow', 'kyiv', 'kiev', 'poland', 'germany', 'france', 'uk', 'britain'],
    'asia': ['china', 'taiwan', 'japan', 'korea', 'india', 'pakistan', 'philippines', 'vietnam', 'beijing'],
    'americas': ['usa', 'us', 'america', 'mexico', 'canada', 'brazil', 'venezuela', 'colombia'],
    'africa': ['sudan', 'ethiopia', 'somalia', 'nigeria', 'libya', 'egypt', 'congo', 'sahel']
}

CONFLICT_KEYWORDS = ['war', 'conflict', 'strike', 'attack', 'military', 'troops', 'casualties', 'combat', 'offensive', 'defense']

def categorize_item(title, description):
    """Categorize item by region based on keywords"""
    text = (title + ' ' + description).lower()
    
    for region, keywords in REGION_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return region
    
    return 'uncategorized'

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
            
            item = {
                'title': title,
                'description': clean_desc[:300],
                'link': link,
                'timestamp': pub_date,
                'region': region,
                'priority': priority,
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
    global categorized_data
    
    # Reset categorized data
    for region in categorized_data:
        categorized_data[region] = []
    
    for feed_id, feed_info in feeds_storage.items():
        items = fetch_feed(feed_id, feed_info['url'])
        
        # Store in feed's own storage
        feeds_storage[feed_id]['items'] = items
        feeds_storage[feed_id]['last_update'] = datetime.now().isoformat()
        
        # Categorize items by region
        for item in items:
            region = item['region']
            categorized_data[region].append(item)
    
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
