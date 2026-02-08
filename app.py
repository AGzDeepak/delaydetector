from flask import Flask, render_template, request, redirect, url_for, g, session, flash, abort
import sqlite3
from datetime import datetime, timedelta
from urllib.request import Request, urlopen
from urllib.error import URLError
import xml.etree.ElementTree as ET
from pathlib import Path
import json
import os
import threading
import time
import smtplib
from email.message import EmailMessage
import logging
import secrets
import shutil
import re
from werkzeug.exceptions import HTTPException

APP_DIR = Path(__file__).parent

def load_env_file(path):
    if not path.exists():
        return
    try:
        for raw in path.read_text(encoding='utf-8').splitlines():
            line = raw.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except Exception:
        pass

load_env_file(APP_DIR / '.env')
DB_PATH = Path(os.environ.get('DB_PATH', str(APP_DIR / 'data.db')))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
EXTERNAL_REFRESH_MINUTES = int(os.environ.get('EXTERNAL_REFRESH_MINUTES', '720'))
EXTERNAL_MAX_PER_SOURCE = int(os.environ.get('EXTERNAL_MAX_PER_SOURCE', '200'))
OPPS_PAGE_SIZE = int(os.environ.get('OPPS_PAGE_SIZE', '24'))
AUTO_REFRESH_EXTERNAL = os.environ.get('AUTO_REFRESH_EXTERNAL', '0') == '1'
EXTERNAL_AUTO_APPROVE = os.environ.get('EXTERNAL_AUTO_APPROVE', '1') == '1'
EXTERNAL_REQUEST_TIMEOUT = int(os.environ.get('EXTERNAL_REQUEST_TIMEOUT', '15'))
STATIC_CACHE_DEFAULT = int(os.environ.get('STATIC_CACHE_DEFAULT', '86400'))
STATIC_CACHE_SHORT = int(os.environ.get('STATIC_CACHE_SHORT', '604800'))
STATIC_CACHE_LONG = int(os.environ.get('STATIC_CACHE_LONG', '2592000'))
SITE_BASE_URL = os.environ.get('SITE_BASE_URL', 'https://awareness-delay.onrender.com').strip().rstrip('/')
GOOGLE_SITE_VERIFICATION = os.environ.get(
    'GOOGLE_SITE_VERIFICATION',
    'zn6e5WtR3PhASeTbbM7yGIZ4G6cdLD77TXPSQEBqaZ0'
).strip()

DEFAULT_EXTERNAL_SOURCES = [
    {
        'name': 'RemoteOK Jobs',
        'url': 'https://remoteok.com/api',
        'kind': 'json'
    },
    {
        'name': 'We Work Remotely',
        'url': 'https://weworkremotely.com/categories/remote-programming-jobs.rss',
        'kind': 'rss'
    },
    {
        'name': 'Arbeitnow Job Board',
        'url': 'https://www.arbeitnow.com/api/job-board-api',
        'kind': 'json'
    }
]

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-change-me')
app.permanent_session_lifetime = timedelta(minutes=30)
logging.basicConfig(filename='app.log', level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

RATE_LIMIT = {}
EXTERNAL_REFRESH_LOCK = threading.Lock()
EXTERNAL_REFRESH_IN_PROGRESS = False

INDIA_STATES = [
    'Andhra Pradesh', 'Arunachal Pradesh', 'Assam', 'Bihar', 'Chhattisgarh', 'Goa',
    'Gujarat', 'Haryana', 'Himachal Pradesh', 'Jharkhand', 'Karnataka', 'Kerala',
    'Madhya Pradesh', 'Maharashtra', 'Manipur', 'Meghalaya', 'Mizoram', 'Nagaland',
    'Odisha', 'Punjab', 'Rajasthan', 'Sikkim', 'Tamil Nadu', 'Telangana', 'Tripura',
    'Uttarakhand', 'Uttar Pradesh', 'West Bengal'
]

INDIA_UNION_TERRITORIES = [
    'Andaman and Nicobar Islands', 'Chandigarh',
    'Dadra and Nagar Haveli and Daman and Diu', 'Delhi',
    'Jammu and Kashmir', 'Ladakh', 'Lakshadweep', 'Puducherry'
]

STATE_CAPITALS = {
    'Andhra Pradesh': 'Amaravati',
    'Arunachal Pradesh': 'Itanagar',
    'Assam': 'Dispur',
    'Bihar': 'Patna',
    'Chhattisgarh': 'Raipur',
    'Goa': 'Panaji',
    'Gujarat': 'Gandhinagar',
    'Haryana': 'Chandigarh',
    'Himachal Pradesh': 'Shimla',
    'Jharkhand': 'Ranchi',
    'Karnataka': 'Bangalore',
    'Kerala': 'Thiruvananthapuram',
    'Madhya Pradesh': 'Bhopal',
    'Maharashtra': 'Mumbai',
    'Manipur': 'Imphal',
    'Meghalaya': 'Shillong',
    'Mizoram': 'Aizawl',
    'Nagaland': 'Kohima',
    'Odisha': 'Bhubaneshwar',
    'Punjab': 'Chandigarh',
    'Rajasthan': 'Jaipur',
    'Sikkim': 'Gangtok',
    'Tamil Nadu': 'Chennai',
    'Telangana': 'Hyderabad',
    'Tripura': 'Agartala',
    'Uttarakhand': 'Dehradun',
    'Uttar Pradesh': 'Lucknow',
    'West Bengal': 'Kolkata'
}

UT_CAPITALS = {
    'Andaman and Nicobar Islands': 'Sri Vijaya Puram',
    'Chandigarh': 'Chandigarh',
    'Dadra and Nagar Haveli and Daman and Diu': 'Daman',
    'Delhi': 'Delhi',
    'Jammu and Kashmir': 'Srinagar (S), Jammu (W)',
    'Ladakh': 'Leh',
    'Lakshadweep': 'Kavaratti',
    'Puducherry': 'Puducherry'
}

INDIA_CAPITAL = 'Delhi'

REGION_SYNONYMS = {
    'nct of delhi': 'Delhi',
    'national capital territory of delhi': 'Delhi',
    'the government of nct of delhi': 'Delhi',
    'new delhi': 'Delhi',
    'orissa': 'Odisha',
    'pondicherry': 'Puducherry',
    'uttaranchal': 'Uttarakhand',
    'andaman nicobar islands': 'Andaman and Nicobar Islands',
    'andaman & nicobar islands': 'Andaman and Nicobar Islands',
    'daman & diu': 'Dadra and Nagar Haveli and Daman and Diu',
    'daman and diu': 'Dadra and Nagar Haveli and Daman and Diu',
    'dadra and nagar haveli and daman & diu': 'Dadra and Nagar Haveli and Daman and Diu',
    'dnhdd': 'Dadra and Nagar Haveli and Daman and Diu',
    'dadra and nagar haveli': 'Dadra and Nagar Haveli and Daman and Diu',
    'jammu & kashmir': 'Jammu and Kashmir',
    'jammu and kashmir': 'Jammu and Kashmir',
    'bangalore': 'Karnataka',
    'bengaluru': 'Karnataka',
    'mumbai': 'Maharashtra',
    'chennai': 'Tamil Nadu',
    'kolkata': 'West Bengal',
    'hyderabad': 'Telangana'
}

CENTRAL_TOKENS = {
    'all india', 'india', 'central', 'national', 'pan india', 'nationwide'
}

STATIC_CACHE_BY_EXT = {
    '.css': STATIC_CACHE_SHORT,
    '.js': STATIC_CACHE_SHORT,
    '.png': STATIC_CACHE_LONG,
    '.jpg': STATIC_CACHE_LONG,
    '.jpeg': STATIC_CACHE_LONG,
    '.gif': STATIC_CACHE_LONG,
    '.svg': STATIC_CACHE_LONG,
    '.webp': STATIC_CACHE_LONG,
    '.ico': STATIC_CACHE_LONG
}

def _normalize_region_key(text):
    if not text:
        return ''
    cleaned = re.sub(r'[^a-z0-9\s]', ' ', text.lower())
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned

REGION_LOOKUP = {}
for name in INDIA_STATES + INDIA_UNION_TERRITORIES:
    REGION_LOOKUP[_normalize_region_key(name)] = name
for key, value in REGION_SYNONYMS.items():
    REGION_LOOKUP[_normalize_region_key(key)] = value

def extract_regions(region_value):
    if not region_value:
        return ['Unknown']
    norm_full = _normalize_region_key(region_value)
    for token in CENTRAL_TOKENS:
        if token in norm_full:
            return ['Central / All India']
    parts = re.split(r'[,/;|]+', norm_full)
    regions = set()
    for part in parts:
        part = part.strip()
        if not part:
            continue
        subparts = [p.strip() for p in part.split(' and ') if p.strip()]
        for sub in subparts:
            key = _normalize_region_key(sub)
            if key in REGION_LOOKUP:
                regions.add(REGION_LOOKUP[key])
    return sorted(regions) if regions else ['Unknown']

def get_region_capital(region_name):
    if region_name in STATE_CAPITALS:
        return STATE_CAPITALS[region_name]
    if region_name in UT_CAPITALS:
        return UT_CAPITALS[region_name]
    if region_name == 'Central / All India':
        return INDIA_CAPITAL
    return '—'

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
    return db

def get_csrf_token():
    token = session.get('csrf_token')
    if not token:
        token = secrets.token_hex(16)
        session['csrf_token'] = token
    return token

@app.context_processor
def inject_csrf_token():
    return {'csrf_token': get_csrf_token()}

def _public_base_url():
    if SITE_BASE_URL:
        return SITE_BASE_URL
    return request.url_root.rstrip('/')

@app.context_processor
def inject_seo_defaults():
    return {
        'canonical_url': request.base_url,
        'site_base_url': _public_base_url(),
        'google_site_verification': GOOGLE_SITE_VERIFICATION
    }

def verify_csrf():
    token = session.get('csrf_token')
    form_token = request.form.get('csrf_token')
    return token and form_token and token == form_token

def ensure_session_user(db):
    user_id = session.get('user_id')
    if user_id:
        return user_id
    row = db.execute('SELECT id FROM users ORDER BY id ASC LIMIT 1').fetchone()
    if row:
        session['user_id'] = row['id']
        return row['id']
    username = f'guest_{int(time.time())}'
    cursor = db.execute(
        'INSERT OR IGNORE INTO users (username, password_hash, role) VALUES (?, ?, ?)',
        (username, generate_password_hash(secrets.token_urlsafe(12)), 'user')
    )
    db.commit()
    if cursor.lastrowid:
        session['user_id'] = cursor.lastrowid
        return cursor.lastrowid
    row = db.execute('SELECT id FROM users ORDER BY id ASC LIMIT 1').fetchone()
    if row:
        session['user_id'] = row['id']
        return row['id']
    return None

def is_rate_limited(key, limit=5, window_seconds=60):
    now = time.time()
    entries = RATE_LIMIT.get(key, [])
    entries = [t for t in entries if now - t < window_seconds]
    if len(entries) >= limit:
        RATE_LIMIT[key] = entries
        return True
    entries.append(now)
    RATE_LIMIT[key] = entries
    return False

from werkzeug.security import generate_password_hash

def ensure_default_external_sources(db):
    added = 0
    for src in DEFAULT_EXTERNAL_SOURCES:
        exists = db.execute(
            'SELECT 1 FROM external_sources WHERE url = ? LIMIT 1',
            (src['url'],)
        ).fetchone()
        if exists:
            continue
        db.execute(
            'INSERT INTO external_sources (name, url, kind, active) VALUES (?, ?, ?, 1)',
            (src['name'], src['url'], src['kind'])
        )
        added += 1
    return added


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        email TEXT UNIQUE,
        role TEXT DEFAULT 'user',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    db.execute('''
    CREATE TABLE IF NOT EXISTS admins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER UNIQUE NOT NULL,
        admin_since TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')
    db.execute('''
    CREATE TABLE IF NOT EXISTS awareness_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        opportunity_name TEXT NOT NULL,
        announcement_date TEXT NOT NULL,
        awareness_date TEXT NOT NULL,
        deadline TEXT NOT NULL,
        delay_days INTEGER,
        delay_category TEXT,
        delay_ratio REAL,
        college_type TEXT,
        region TEXT,
        description TEXT,
        status TEXT DEFAULT 'submitted',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')
    db.execute('''
    CREATE TABLE IF NOT EXISTS submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        opportunity_name TEXT NOT NULL,
        announcement_date TEXT NOT NULL,
        awareness_date TEXT NOT NULL,
        deadline TEXT NOT NULL,
        college_type TEXT,
        region TEXT,
        description TEXT,
        status TEXT DEFAULT 'submitted',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')
    db.execute('''
    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        action TEXT NOT NULL,
        table_name TEXT,
        record_id INTEGER,
        changes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')
    db.execute('''
    CREATE TABLE IF NOT EXISTS external_sources (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        url TEXT NOT NULL,
        kind TEXT NOT NULL,
        active INTEGER DEFAULT 1,
        last_fetched TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    db.execute('''
    CREATE TABLE IF NOT EXISTS external_opportunities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        company TEXT,
        type TEXT,
        region TEXT,
        deadline TEXT,
        url TEXT,
        description TEXT,
        salary TEXT,
        duration TEXT,
        online INTEGER DEFAULT 0,
        source TEXT,
        approved INTEGER DEFAULT 0,
        fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (source_id) REFERENCES external_sources (id)
    )
    ''')
    # Migrations for existing databases
    cols = [r['name'] for r in db.execute("PRAGMA table_info(external_opportunities)").fetchall()]
    if 'approved' not in cols:
        db.execute('ALTER TABLE external_opportunities ADD COLUMN approved INTEGER DEFAULT 0')
    db.execute('''
    CREATE TABLE IF NOT EXISTS user_profiles (
        user_id INTEGER PRIMARY KEY,
        full_name TEXT,
        college TEXT,
        degree TEXT,
        graduation_year TEXT,
        skills TEXT,
        preferred_regions TEXT,
        preferred_roles TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')
    db.execute('''
    CREATE TABLE IF NOT EXISTS user_preferences (
        user_id INTEGER PRIMARY KEY,
        regions TEXT,
        types TEXT,
        keywords TEXT,
        alert_channels TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')
    db.execute('''
    CREATE TABLE IF NOT EXISTS saved_opportunities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        source TEXT NOT NULL,
        source_id INTEGER,
        title TEXT NOT NULL,
        url TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')
    db.execute('''
    CREATE TABLE IF NOT EXISTS alert_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        channel TEXT NOT NULL,
        source TEXT NOT NULL,
        source_id INTEGER,
        title TEXT NOT NULL,
        url TEXT,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, channel, source, source_id)
    )
    ''')
    db.execute('CREATE INDEX IF NOT EXISTS idx_users_username ON users (username)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_users_email ON users (email)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_admins_user_id ON admins (user_id)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_awareness_user_id ON awareness_data (user_id)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_awareness_opportunity ON awareness_data (opportunity_name)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_awareness_category ON awareness_data (delay_category)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_awareness_region ON awareness_data (region)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_awareness_created ON awareness_data (created_at)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_submissions_user_id ON submissions (user_id)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_submissions_created ON submissions (created_at)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_sources_active ON external_sources (active)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_external_source_id ON external_opportunities (source_id)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_external_fetched ON external_opportunities (fetched_at)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_external_approved ON external_opportunities (approved)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_saved_user ON saved_opportunities (user_id)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_alert_user ON alert_queue (user_id)')
    ensure_default_external_sources(db)
    db.commit()
    # seed a default user for testing if none exist
    cur = db.execute('SELECT COUNT(*) as c FROM users')
    row = cur.fetchone()
    if row and row[0] == 0:
        db.execute('INSERT OR IGNORE INTO users (username, password_hash, role) VALUES (?, ?, ?)',
                   ('admin', generate_password_hash('password'), 'admin'))
        db.commit()
    # ensure admins table is synced for any existing admin users
    db.execute('''
        INSERT OR IGNORE INTO admins (user_id)
        SELECT id FROM users WHERE role = 'admin'
    ''')
    db.commit()
    db.close()

def is_admin_user(user_id, db):
    row = db.execute('SELECT 1 FROM admins WHERE user_id = ?', (user_id,)).fetchone()
    return row is not None

init_db()

def log_audit(db, user_id, action, table_name=None, record_id=None, changes=None):
    db.execute('''INSERT INTO audit_log (user_id, action, table_name, record_id, changes)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, action, table_name, record_id, changes))

def categorize_delay(days):
    if days is None:
        return 'Unknown'
    if days <= 2:
        return 'Early Access'
    if 3 <= days <= 7:
        return 'Medium Delay'
    return 'Late Access'

def parse_date(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None

def _static_cache_seconds(path):
    ext = Path(path or '').suffix.lower()
    return STATIC_CACHE_BY_EXT.get(ext, STATIC_CACHE_DEFAULT)

def validate_password(pw):
    if not pw or len(pw) < 8:
        return False
    has_letter = any(c.isalpha() for c in pw)
    has_digit = any(c.isdigit() for c in pw)
    return has_letter and has_digit

# AI-based opportunity recommendation system
def get_opportunity_keywords(opportunity_name):
    """Extract keywords from opportunity name for AI recommendation"""
    keywords = opportunity_name.lower().split()
    stop_words = {'the', 'a', 'an', 'and', 'or', 'for', 'is', 'at', 'to', 'from'}
    return [k for k in keywords if k not in stop_words and len(k) > 2]

def normalize_text(s):
    return ''.join(ch for ch in (s or '').lower() if ch.isalnum() or ch.isspace()).strip()

def categorize_opportunity(title, description=''):
    text = f"{title} {description}".lower()
    if any(k in text for k in ['intern', 'internship', 'summer intern']):
        return 'Internship'
    if any(k in text for k in ['scholarship', 'grant', 'fellowship']):
        return 'Scholarship/Fellowship'
    if any(k in text for k in ['hackathon', 'competition']):
        return 'Hackathon'
    if any(k in text for k in ['bootcamp', 'training', 'academy']):
        return 'Training'
    return 'Opportunity'

def summarize_opportunity(description):
    if not description:
        return ''
    clean = ' '.join(description.split())
    return clean[:160] + ('…' if len(clean) > 160 else '')

def compute_relevance(opp, prefs):
    if not prefs:
        return 0
    score = 0
    title = (opp.get('title') or '').lower()
    company = (opp.get('company') or '').lower()
    region = (opp.get('region') or '').lower()
    opp_type = (opp.get('type') or '').lower()
    keywords = [k.strip().lower() for k in (prefs.get('keywords') or '').split(',') if k.strip()]
    regions = [r.strip().lower() for r in (prefs.get('regions') or '').split(',') if r.strip()]
    types = [t.strip().lower() for t in (prefs.get('types') or '').split(',') if t.strip()]
    for k in keywords:
        if k in title or k in company:
            score += 2
    for r in regions:
        if r in region:
            score += 1
    for t in types:
        if t in opp_type:
            score += 1
    return score

def find_similar_opportunities(opportunity_name, db):
    """AI function: Find similar opportunities based on keyword matching"""
    keywords = get_opportunity_keywords(opportunity_name)
    if not keywords:
        return []
    
    similar = []
    all_opps = db.execute('SELECT DISTINCT opportunity_name FROM awareness_data').fetchall()
    
    for opp in all_opps:
        opp_name = opp['opportunity_name']
        if opp_name.lower() == opportunity_name.lower():
            continue
        
        opp_keywords = get_opportunity_keywords(opp_name)
        matches = len(set(keywords) & set(opp_keywords))
        if matches > 0:
            similar.append({
                'name': opp_name,
                'relevance': matches,
                'keywords': list(set(keywords) & set(opp_keywords))
            })
    
    similar.sort(key=lambda x: x['relevance'], reverse=True)
    return similar[:5]

def get_opp_recommendations_by_category(college_type, region, db):
    """AI function: Get opportunity recommendations by college type and region"""
    try:
        recommendations = db.execute('''
            SELECT opportunity_name, college_type, region, delay_category, COUNT(*) as count
            FROM awareness_data
            WHERE (college_type = ? OR region = ?)
            GROUP BY opportunity_name
            ORDER BY count DESC LIMIT 10
        ''', (college_type, region)).fetchall()
        return [dict(r) for r in recommendations]
    except:
        return []

def get_online_opportunities():
    """Fetch real opportunities from online sources for demo recommendations"""
    demo_opportunities = [
        {
            'title': 'Google Summer Internship 2026',
            'company': 'Google',
            'type': 'Internship',
            'region': 'Multiple (Global)',
            'deadline': '2026-03-15',
            'url': 'https://careers.google.com/internships/',
            'description': 'Paid internship at Google offices worldwide',
            'salary': '$25-35/hour',
            'duration': '12 weeks',
            'online': True,
            'source': 'Official'
        },
        {
            'title': 'Microsoft TEALS Fellowship',
            'company': 'Microsoft',
            'type': 'Fellowship',
            'region': 'USA + International',
            'deadline': '2026-04-01',
            'url': 'https://www.microsoft.com/en-us/teals',
            'description': 'Tech education and mentorship program',
            'salary': 'Scholarship',
            'duration': 'Full Year',
            'online': True,
            'source': 'Official'
        },
        {
            'title': 'Goldman Sachs Internship Program',
            'company': 'Goldman Sachs',
            'type': 'Internship',
            'region': 'USA, Europe, Asia',
            'deadline': '2026-02-28',
            'url': 'https://www.goldmansachs.com/careers/',
            'description': 'Summer analyst program with mentorship',
            'salary': '$30-40/hour',
            'duration': '10 weeks',
            'online': False,
            'source': 'Official'
        },
        {
            'title': 'Accenture Cloud Academy',
            'company': 'Accenture',
            'type': 'Training + Internship',
            'region': 'India, USA',
            'deadline': '2026-03-31',
            'url': 'https://www.accenture.com/careers/',
            'description': 'Cloud technology training and internship',
            'salary': 'Stipend + Offer',
            'duration': '3-6 months',
            'online': True,
            'source': 'Official'
        },
        {
            'title': 'McKinsey Forward Program',
            'company': 'McKinsey & Company',
            'type': 'Consulting Internship',
            'region': 'Global',
            'deadline': '2026-03-20',
            'url': 'https://www.mckinsey.com/careers/',
            'description': 'Leadership development and consulting experience',
            'salary': '$40-50/hour',
            'duration': '8-12 weeks',
            'online': False,
            'source': 'Official'
        },
        {
            'title': 'Amazon Leadership Development Internship',
            'company': 'Amazon',
            'type': 'Internship',
            'region': 'USA, Europe, India',
            'deadline': '2026-04-10',
            'url': 'https://www.amazon.jobs/internships',
            'description': 'Tech and business internship with leadership focus',
            'salary': '$28-38/hour',
            'duration': '12 weeks',
            'online': False,
            'source': 'Official'
        },
        {
            'title': 'JPMorgan Chase Code for Good',
            'company': 'JPMorgan Chase',
            'type': 'Hackathon + Internship',
            'region': 'USA, Europe, Asia',
            'deadline': '2026-03-15',
            'url': 'https://www.jpmorganchase.com/careers',
            'description': 'Tech hackathon for social impact + job opportunities',
            'salary': 'Award + Internship',
            'duration': 'Variable',
            'online': True,
            'source': 'Official'
        },
        {
            'title': 'Deloitte Discovery Internship',
            'company': 'Deloitte',
            'type': 'Internship',
            'region': 'USA, Asia, Europe',
            'deadline': '2026-04-05',
            'url': 'https://www2.deloitte.com/careers/',
            'description': 'Consulting and advisory internship program',
            'salary': '$26-36/hour',
            'duration': '10 weeks',
            'online': False,
            'source': 'Official'
        },
        {
            'title': 'Meta (Facebook) Internship',
            'company': 'Meta',
            'type': 'Internship',
            'region': 'USA, Europe, Asia',
            'deadline': '2026-03-30',
            'url': 'https://www.metacareers.com/internships',
            'description': 'Software engineering and business internship',
            'salary': '$30-40/hour',
            'duration': '12 weeks',
            'online': False,
            'source': 'Official'
        },
        {
            'title': 'Apple Internship Programs',
            'company': 'Apple',
            'type': 'Internship',
            'region': 'USA, Europe',
            'deadline': '2026-04-15',
            'url': 'https://www.apple.com/careers/',
            'description': 'Hardware and software engineering internships',
            'salary': '$32-42/hour',
            'duration': '12 weeks',
            'online': False,
            'source': 'Official'
        },
        {
            'title': 'Tesla Leadership Program',
            'company': 'Tesla',
            'type': 'Engineering Internship',
            'region': 'USA, China',
            'deadline': '2026-03-25',
            'url': 'https://www.tesla.com/careers/',
            'description': 'EV and renewable energy engineering internship',
            'salary': '$28-38/hour',
            'duration': '12 weeks',
            'online': False,
            'source': 'Official'
        },
        {
            'title': 'BCG Platinion Internship',
            'company': 'Boston Consulting Group',
            'type': 'Tech Consulting',
            'region': 'Global',
            'deadline': '2026-03-20',
            'url': 'https://www.bcg.com/careers/',
            'description': 'Technology and digital strategy consulting',
            'salary': '$35-45/hour',
            'duration': '12 weeks',
            'online': False,
            'source': 'Official'
        },
        {
            'title': 'IBM Accelerate Program',
            'company': 'IBM',
            'type': 'Early Talent',
            'region': 'USA, Europe',
            'deadline': '2026-03-10',
            'url': 'https://www.ibm.com/careers/',
            'description': 'Early talent program with mentorship and skills training',
            'salary': 'Stipend',
            'duration': '8 weeks',
            'online': True,
            'source': 'Official'
        },
        {
            'title': 'Salesforce Futureforce Internship',
            'company': 'Salesforce',
            'type': 'Internship',
            'region': 'USA, India, UK',
            'deadline': '2026-04-08',
            'url': 'https://www.salesforce.com/company/careers/',
            'description': 'Software and product internships for students',
            'salary': '$28-38/hour',
            'duration': '10-12 weeks',
            'online': False,
            'source': 'Official'
        },
        {
            'title': 'NVIDIA Deep Learning Institute Internship',
            'company': 'NVIDIA',
            'type': 'Research Internship',
            'region': 'USA, Taiwan',
            'deadline': '2026-03-28',
            'url': 'https://www.nvidia.com/en-us/about-nvidia/careers/',
            'description': 'AI research internship with GPU computing focus',
            'salary': '$32-45/hour',
            'duration': '12 weeks',
            'online': False,
            'source': 'Official'
        },
        {
            'title': 'Intel Software Engineering Internship',
            'company': 'Intel',
            'type': 'Internship',
            'region': 'USA, Israel, India',
            'deadline': '2026-04-02',
            'url': 'https://jobs.intel.com/',
            'description': 'Software engineering internships across business units',
            'salary': '$27-37/hour',
            'duration': '12 weeks',
            'online': False,
            'source': 'Official'
        },
        {
            'title': 'Adobe Digital Academy',
            'company': 'Adobe',
            'type': 'Training + Internship',
            'region': 'USA',
            'deadline': '2026-02-22',
            'url': 'https://www.adobe.com/careers.html',
            'description': 'Career training with pathway to internships',
            'salary': 'Stipend + Offer',
            'duration': '3-4 months',
            'online': True,
            'source': 'Official'
        },
        {
            'title': 'Stripe University Internship',
            'company': 'Stripe',
            'type': 'Internship',
            'region': 'USA, Ireland',
            'deadline': '2026-03-18',
            'url': 'https://stripe.com/jobs',
            'description': 'Engineering and product internships with impact projects',
            'salary': '$35-50/hour',
            'duration': '12 weeks',
            'online': False,
            'source': 'Official'
        },
        {
            'title': 'Uber University Program',
            'company': 'Uber',
            'type': 'Internship',
            'region': 'USA, Canada, India',
            'deadline': '2026-03-26',
            'url': 'https://www.uber.com/us/en/careers/',
            'description': 'Software engineering and data internships',
            'salary': '$30-42/hour',
            'duration': '12 weeks',
            'online': False,
            'source': 'Official'
        },
        {
            'title': 'Airbnb Internship Program',
            'company': 'Airbnb',
            'type': 'Internship',
            'region': 'USA',
            'deadline': '2026-03-22',
            'url': 'https://careers.airbnb.com/',
            'description': 'Product, design, and engineering internships',
            'salary': '$32-44/hour',
            'duration': '12 weeks',
            'online': False,
            'source': 'Official'
        },
        {
            'title': 'Zoom University Internship',
            'company': 'Zoom',
            'type': 'Internship',
            'region': 'USA',
            'deadline': '2026-03-12',
            'url': 'https://careers.zoom.us/',
            'description': 'Engineering internships focused on collaboration tools',
            'salary': '$28-38/hour',
            'duration': '10-12 weeks',
            'online': True,
            'source': 'Official'
        },
        {
            'title': 'Snap Research Internship',
            'company': 'Snap',
            'type': 'Research Internship',
            'region': 'USA, France',
            'deadline': '2026-04-12',
            'url': 'https://careers.snap.com/',
            'description': 'Computer vision and AR research internships',
            'salary': '$35-48/hour',
            'duration': '12 weeks',
            'online': False,
            'source': 'Official'
        },
        {
            'title': 'Palantir Path Internship',
            'company': 'Palantir',
            'type': 'Internship',
            'region': 'USA, UK',
            'deadline': '2026-03-05',
            'url': 'https://www.palantir.com/careers/',
            'description': 'Engineering internships with real-world data problems',
            'salary': '$38-55/hour',
            'duration': '10-12 weeks',
            'online': False,
            'source': 'Official'
        },
        {
            'title': 'ServiceNow Summer Internship',
            'company': 'ServiceNow',
            'type': 'Internship',
            'region': 'USA, India',
            'deadline': '2026-03-29',
            'url': 'https://careers.servicenow.com/',
            'description': 'Software engineering and platform internships',
            'salary': '$26-36/hour',
            'duration': '12 weeks',
            'online': False,
            'source': 'Official'
        },
        {
            'title': 'Databricks University Internship',
            'company': 'Databricks',
            'type': 'Internship',
            'region': 'USA, Netherlands',
            'deadline': '2026-04-06',
            'url': 'https://www.databricks.com/company/careers',
            'description': 'Data engineering and ML internships',
            'salary': '$38-52/hour',
            'duration': '12 weeks',
            'online': False,
            'source': 'Official'
        },
        {
            'title': 'EY Technology Consulting Internship',
            'company': 'EY',
            'type': 'Consulting Internship',
            'region': 'USA, Europe, India',
            'deadline': '2026-04-03',
            'url': 'https://www.ey.com/en_us/careers',
            'description': 'Technology consulting internships across industries',
            'salary': '$24-34/hour',
            'duration': '10 weeks',
            'online': False,
            'source': 'Official'
        },
        {
            'title': 'UNICEF Innovation Internship',
            'company': 'UNICEF',
            'type': 'Nonprofit Internship',
            'region': 'Global',
            'deadline': '2026-03-14',
            'url': 'https://www.unicef.org/careers',
            'description': 'Innovation and digital development internships',
            'salary': 'Stipend',
            'duration': '12 weeks',
            'online': True,
            'source': 'Official'
        },
        {
            'title': 'NASA Pathways Internship',
            'company': 'NASA',
            'type': 'Government Internship',
            'region': 'USA',
            'deadline': '2026-02-26',
            'url': 'https://www.nasa.gov/careers/',
            'description': 'STEM internships with NASA centers',
            'salary': '$22-30/hour',
            'duration': '10-16 weeks',
            'online': False,
            'source': 'Official'
        }
    ]
    
    return demo_opportunities

def filter_opportunities(opps, query=None, region=None, internship_type=None):
    """Filter opportunities from a given list"""
    
    if query:
        query = query.lower()
        opps = [o for o in opps if query in (o.get('title') or '').lower() or query in (o.get('company') or '').lower()]
    
    if region:
        opps = [o for o in opps if region.lower() in (o.get('region') or '').lower()]
    
    if internship_type:
        opps = [o for o in opps if internship_type.lower() in (o.get('type') or '').lower()]
    
    return opps

def filter_online_opportunities(query=None, region=None, internship_type=None):
    """Backward-compatible helper expected by older tests/scripts."""
    return filter_opportunities(
        get_online_opportunities(),
        query=query,
        region=region,
        internship_type=internship_type
    )

def _clean_text(value, limit=240):
    text = re.sub(r'<[^>]+>', ' ', value or '')
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:limit]

def _pick_first_value(record, keys):
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, (int, float)):
            return str(value)
    return ''

def _normalize_json_records(data):
    if isinstance(data, dict):
        for key in ('items', 'data', 'results', 'jobs', 'opportunities'):
            value = data.get(key)
            if isinstance(value, list):
                return value
    if isinstance(data, list):
        return data
    return []

def _fetch_url(url):
    req = Request(url, headers={'User-Agent': 'AwarenessDelayBot/1.0'})
    with urlopen(req, timeout=EXTERNAL_REQUEST_TIMEOUT) as resp:
        return resp.read()

def _parse_rss(content, source_name):
    items = []
    try:
        root = ET.fromstring(content)
        channel = root.find('channel')
        if channel is not None:
            for item in channel.findall('item'):
                title = (item.findtext('title') or '').strip()
                link = (item.findtext('link') or '').strip()
                desc = _clean_text(item.findtext('description') or '')
                if not title:
                    continue
                items.append({
                    'title': title,
                    'company': source_name,
                    'type': 'Opportunity',
                    'region': 'Unknown',
                    'deadline': '',
                    'url': link,
                    'description': desc,
                    'salary': '',
                    'duration': '',
                    'online': True,
                    'source': source_name
                })
            return items

        # Fallback for Atom feeds.
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        for entry in root.findall('.//atom:entry', ns):
            title = (entry.findtext('atom:title', default='', namespaces=ns) or '').strip()
            summary = _clean_text(entry.findtext('atom:summary', default='', namespaces=ns) or '')
            link = ''
            link_node = entry.find("atom:link[@rel='alternate']", ns) or entry.find('atom:link', ns)
            if link_node is not None:
                link = (link_node.get('href') or '').strip()
            if not title:
                continue
            items.append({
                'title': title,
                'company': source_name,
                'type': 'Opportunity',
                'region': 'Unknown',
                'deadline': '',
                'url': link,
                'description': summary,
                'salary': '',
                'duration': '',
                'online': True,
                'source': source_name
            })
    except Exception:
        return []
    return items

def _parse_json(content, source_name):
    items = []
    try:
        data = json.loads(content.decode('utf-8'))
    except Exception:
        return items
    data = _normalize_json_records(data)
    for it in data:
        if not isinstance(it, dict):
            continue
        title = _pick_first_value(it, ('title', 'name', 'position', 'role'))
        if not title:
            continue
        type_value = it.get('type') or it.get('category') or it.get('job_type') or it.get('job_types') or ''
        if isinstance(type_value, list):
            type_value = ', '.join(str(v) for v in type_value if v)
        type_value = (str(type_value).strip() if type_value else '') or 'Opportunity'
        description = _pick_first_value(it, ('description', 'summary', 'snippet', 'details'))
        items.append({
            'title': title,
            'company': _pick_first_value(it, ('company', 'company_name', 'organization', 'org')) or source_name,
            'type': type_value,
            'region': _pick_first_value(it, ('region', 'location', 'country')) or 'Unknown',
            'deadline': _pick_first_value(it, ('deadline', 'close_date', 'expires_at', 'expiry_date')),
            'url': _pick_first_value(it, ('url', 'link', 'redirect_url', 'apply_url')),
            'description': _clean_text(description),
            'salary': _pick_first_value(it, ('salary', 'compensation', 'salary_range')),
            'duration': _pick_first_value(it, ('duration', 'tenure', 'period')),
            'online': bool(it.get('online')) if 'online' in it else True,
            'source': source_name
        })
    return items

def _parse_html(content, source_name):
    items = []
    try:
        text = content.decode('utf-8', errors='ignore')
    except Exception:
        return items
    for line in text.splitlines():
        if '<a ' in line and 'href=' in line:
            start = line.find('href=')
            if start == -1:
                continue
            quote = line[start+5:start+6]
            if quote not in ['"', "'"]:
                continue
            end = line.find(quote, start+6)
            url = line[start+6:end] if end != -1 else ''
            title_start = line.find('>')
            title_end = line.find('</a>')
            title = ''
            if title_start != -1 and title_end != -1 and title_end > title_start:
                title = line[title_start+1:title_end].strip()
            if not title:
                continue
            items.append({
                'title': title,
                'company': source_name,
                'type': 'Opportunity',
                'region': 'Unknown',
                'deadline': '',
                'url': url,
                'description': '',
                'salary': '',
                'duration': '',
                'online': True,
                'source': source_name
            })
            if len(items) >= 50:
                break
    return items

def refresh_external_opportunities(db):
    sources = db.execute('SELECT * FROM external_sources WHERE active = 1').fetchall()
    total_added = 0
    for src in sources:
        try:
            content = _fetch_url(src['url'])
            if src['kind'] == 'rss':
                items = _parse_rss(content, src['name'])
            elif src['kind'] == 'json':
                items = _parse_json(content, src['name'])
            else:
                items = _parse_html(content, src['name'])
        except (URLError, TimeoutError):
            continue
        except Exception:
            continue
        for item in items:
            item_title = (item.get('title') or '').strip()
            item_url = (item.get('url') or '').strip()
            if not item_title:
                continue
            exists = db.execute('''
                SELECT 1 FROM external_opportunities
                WHERE source_id = ? AND title = ? AND IFNULL(url, '') = IFNULL(?, '')
                LIMIT 1
            ''', (src['id'], item_title, item_url)).fetchone()
            if exists:
                continue
            db.execute('''
                INSERT INTO external_opportunities
                (source_id, title, company, type, region, deadline, url, description, salary, duration, online, source, approved)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ''', (
                src['id'], item_title, item.get('company') or src['name'], item.get('type') or 'Opportunity',
                item.get('region') or 'Unknown', item.get('deadline') or '', item_url,
                item.get('description') or '', item.get('salary') or '',
                item.get('duration') or '', 1 if item.get('online', True) else 0,
                item.get('source') or src['name'], 1 if EXTERNAL_AUTO_APPROVE else 0
            ))
            total_added += 1
        db.execute('UPDATE external_sources SET last_fetched = CURRENT_TIMESTAMP WHERE id = ?', (src['id'],))
        db.execute('''
            DELETE FROM external_opportunities
            WHERE source_id = ?
              AND id NOT IN (
                SELECT id FROM external_opportunities
                WHERE source_id = ?
                ORDER BY fetched_at DESC, id DESC
                LIMIT ?
              )
        ''', (src['id'], src['id'], EXTERNAL_MAX_PER_SOURCE))
    db.commit()
    return total_added

def refresh_external_opportunities_async():
    global EXTERNAL_REFRESH_IN_PROGRESS
    with EXTERNAL_REFRESH_LOCK:
        if EXTERNAL_REFRESH_IN_PROGRESS:
            return False
        EXTERNAL_REFRESH_IN_PROGRESS = True

    def _worker():
        global EXTERNAL_REFRESH_IN_PROGRESS
        db = None
        try:
            db = sqlite3.connect(DB_PATH)
            db.row_factory = sqlite3.Row
            refresh_external_opportunities(db)
        except Exception:
            pass
        finally:
            try:
                if db is not None:
                    db.close()
            finally:
                with EXTERNAL_REFRESH_LOCK:
                    EXTERNAL_REFRESH_IN_PROGRESS = False

    threading.Thread(target=_worker, daemon=True, name='external-refresh-worker').start()
    return True

def get_external_opportunities(db, limit=None, include_unapproved=False):
    sql = 'SELECT * FROM external_opportunities'
    if not include_unapproved:
        sql += ' WHERE approved = 1'
    sql += ' ORDER BY fetched_at DESC'
    if limit:
        sql += f' LIMIT {int(limit)}'
    rows = db.execute(sql).fetchall()
    return [dict(r) for r in rows]

def enrich_opportunities(opps, prefs=None):
    seen = set()
    enriched = []
    for opp in opps:
        title = opp.get('title') or ''
        company = opp.get('company') or ''
        key = f"{normalize_text(title)}|{normalize_text(company)}"
        if key in seen:
            continue
        seen.add(key)
        opp['category'] = categorize_opportunity(title, opp.get('description') or '')
        opp['summary'] = summarize_opportunity(opp.get('description') or '')
        opp['relevance'] = compute_relevance(opp, prefs) if prefs else 0
        enriched.append(opp)
    return enriched

def get_live_opportunities(db, limit=None, user_id=None, include_unapproved=False):
    has_sources = db.execute('SELECT 1 FROM external_sources WHERE active = 1 LIMIT 1').fetchone() is not None
    if has_sources:
        cached_count = db.execute('SELECT COUNT(*) as c FROM external_opportunities').fetchone()['c']
        if cached_count == 0:
            refresh_external_opportunities_async()
        elif AUTO_REFRESH_EXTERNAL:
            last = db.execute('SELECT MAX(last_fetched) as lf FROM external_sources WHERE active = 1').fetchone()
            if last and last['lf']:
                try:
                    lf_dt = datetime.fromisoformat(last['lf'])
                    if datetime.utcnow() - lf_dt > timedelta(minutes=EXTERNAL_REFRESH_MINUTES):
                        refresh_external_opportunities_async()
                except Exception:
                    pass
    external = get_external_opportunities(db, limit=limit, include_unapproved=include_unapproved)
    if external:
        prefs = None
        if user_id:
            pref = db.execute('SELECT * FROM user_preferences WHERE user_id = ?', (user_id,)).fetchone()
            prefs = dict(pref) if pref else None
        return enrich_opportunities(external, prefs=prefs)
    demo = get_online_opportunities()
    prefs = None
    if user_id:
        pref = db.execute('SELECT * FROM user_preferences WHERE user_id = ?', (user_id,)).fetchone()
        prefs = dict(pref) if pref else None
    demo = demo[:limit] if limit else demo
    return enrich_opportunities(demo, prefs=prefs)

def send_pending_alerts(db):
    host = os.environ.get('SMTP_HOST')
    port = int(os.environ.get('SMTP_PORT', '587'))
    user = os.environ.get('SMTP_USER')
    password = os.environ.get('SMTP_PASS')
    sender = os.environ.get('SMTP_FROM') or user
    if not host or not user or not password:
        return 0
    rows = db.execute('''
        SELECT a.id, a.user_id, a.title, a.url, a.channel, u.email
        FROM alert_queue a
        JOIN users u ON u.id = a.user_id
        WHERE a.status = 'pending' AND a.channel = 'email' AND u.email IS NOT NULL
        ORDER BY a.created_at ASC
        LIMIT 50
    ''').fetchall()
    if not rows:
        return 0
    msg_server = smtplib.SMTP(host, port, timeout=10)
    msg_server.starttls()
    msg_server.login(user, password)
    sent = 0
    for r in rows:
        msg = EmailMessage()
        msg['Subject'] = f"New Opportunity: {r['title']}"
        msg['From'] = sender
        msg['To'] = r['email']
        body = f"{r['title']}\n{r['url'] or ''}\n\nThis matches your preferences."
        msg.set_content(body)
        try:
            msg_server.send_message(msg)
            db.execute('UPDATE alert_queue SET status = ? WHERE id = ?', ('sent', r['id']))
            sent += 1
        except Exception:
            db.execute('UPDATE alert_queue SET status = ? WHERE id = ?', ('failed', r['id']))
    db.commit()
    msg_server.quit()
    return sent

def backup_database():
    backup_dir = Path(__file__).parent / 'backups'
    backup_dir.mkdir(exist_ok=True)
    ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    dest = backup_dir / f"data_backup_{ts}.db"
    shutil.copy(DB_PATH, dest)
    return dest

def generate_alerts_for_user(db, user_id, limit=20):
    pref = db.execute('SELECT * FROM user_preferences WHERE user_id = ?', (user_id,)).fetchone()
    prefs = dict(pref) if pref else {}
    channels = (prefs.get('alert_channels') or 'email').split(',')
    channels = [c.strip() for c in channels if c.strip()]
    opps = get_live_opportunities(db, user_id=user_id)
    generated = 0
    for opp in opps:
        if generated >= limit:
            break
        score = compute_relevance(opp, prefs)
        if prefs and score < 2:
            continue
        for ch in channels:
            db.execute('''
                INSERT OR IGNORE INTO alert_queue
                (user_id, channel, source, source_id, title, url)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, ch, opp.get('source') or 'external', opp.get('id') or 0, opp.get('title'), opp.get('url')))
        generated += 1
    db.commit()
    return generated

def send_test_email(email):
    host = os.environ.get('SMTP_HOST')
    port = int(os.environ.get('SMTP_PORT', '587'))
    user = os.environ.get('SMTP_USER')
    password = os.environ.get('SMTP_PASS')
    sender = os.environ.get('SMTP_FROM') or user
    if not host or not user or not password:
        return False, 'SMTP not configured'
    msg_server = smtplib.SMTP(host, port, timeout=10)
    msg_server.starttls()
    msg_server.login(user, password)
    msg = EmailMessage()
    msg['Subject'] = 'SMTP Test: Awareness Delay'
    msg['From'] = sender
    msg['To'] = email
    msg.set_content('This is a test email from Awareness Delay.')
    msg_server.send_message(msg)
    msg_server.quit()
    return True, None

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

@app.errorhandler(Exception)
def handle_exception(e):
    if isinstance(e, HTTPException):
        return e
    logging.exception("Unhandled error")
    return "An internal error occurred. Please try again later.", 500

@app.before_request
def enforce_csrf_and_rate_limits():
    if request.method == 'POST':
        if not verify_csrf():
            abort(400)
    ensure_session_user(get_db())
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if request.path == '/submit' and request.method == 'POST':
        if is_rate_limited(f'submit:{ip}', limit=8, window_seconds=60):
            flash('Too many submissions. Please slow down.')
            return redirect(url_for('submit'))

@app.after_request
def add_static_cache_headers(response):
    if request.path.startswith('/static/'):
        max_age = _static_cache_seconds(request.path)
        response.headers['Cache-Control'] = f'public, max-age={max_age}'
        response.headers['Vary'] = 'Accept-Encoding'
    return response

@app.route('/')
def index():
    db = get_db()
    online_opps = get_live_opportunities(db, limit=8, user_id=session.get('user_id'))
    return render_template('index.html', online_opps=online_opps)

@app.route('/healthz')
def healthz():
    return {'status': 'ok'}, 200

@app.route('/robots.txt')
def robots_txt():
    site_base = _public_base_url()
    content = '\n'.join([
        'User-agent: *',
        'Allow: /',
        f'Sitemap: {site_base}/sitemap.xml'
    ]) + '\n'
    return app.response_class(content, mimetype='text/plain')

@app.route('/sitemap.xml')
def sitemap_xml():
    site_base = _public_base_url()
    pages = [
        ('/', '1.0', 'daily'),
        ('/opportunities', '0.9', 'daily'),
        ('/submit', '0.8', 'weekly'),
        ('/dashboard', '0.8', 'daily'),
        ('/insights', '0.8', 'weekly'),
        ('/saved', '0.7', 'weekly'),
        ('/alerts', '0.7', 'weekly'),
        ('/preferences', '0.6', 'weekly'),
        ('/profile', '0.6', 'weekly')
    ]
    today = datetime.utcnow().date().isoformat()
    entries = []
    for path, priority, changefreq in pages:
        entries.append(
            f'<url><loc>{site_base}{path}</loc><lastmod>{today}</lastmod>'
            f'<changefreq>{changefreq}</changefreq><priority>{priority}</priority></url>'
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + ''.join(entries) +
        '</urlset>'
    )
    return app.response_class(xml, mimetype='application/xml')


@app.route('/submit', methods=['GET', 'POST'])
def submit():
    if request.method == 'POST':
        name = request.form.get('opportunity_name')
        ann = request.form.get('announcement_date')
        aware = request.form.get('awareness_date')
        deadline = request.form.get('deadline')
        college = request.form.get('college_type')
        region = request.form.get('region')

        ann_d = parse_date(ann)
        aware_d = parse_date(aware)
        dead_d = parse_date(deadline)

        delay_days = None
        delay_ratio = None
        if ann_d and aware_d:
            delta = (aware_d - ann_d).days
            delay_days = max(0, delta)
        if ann_d and dead_d:
            total = (dead_d - ann_d).days
            if total > 0 and delay_days is not None:
                delay_ratio = round(delay_days / total, 4)

        delay_category = categorize_delay(delay_days)

        db = get_db()
        user_id = session.get('user_id')
        sub_cursor = db.execute('''INSERT INTO submissions
            (user_id, opportunity_name, announcement_date, awareness_date, deadline, college_type, region)
            VALUES (?,?,?,?,?,?,?)
        ''', (user_id, name, ann, aware, deadline, college, region))
        db.commit()
        submission_id = sub_cursor.lastrowid
        cursor = db.execute('''INSERT INTO awareness_data
            (user_id, opportunity_name, announcement_date, awareness_date, deadline, delay_days, delay_category, delay_ratio, college_type, region)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        ''', (user_id, name, ann, aware, deadline, delay_days, delay_category, delay_ratio, college, region))
        db.commit()
        last_id = cursor.lastrowid
        
        # Log the action
        log_audit(db, user_id, 'INSERT', 'submissions', submission_id, f'Submitted opportunity: {name}')
        log_audit(db, user_id, 'INSERT', 'awareness_data', last_id, f'Computed metrics for: {name}')
        db.commit()
        
        flash('Data submitted successfully!', 'success')
        return redirect(url_for('dashboard'))

    return render_template('submit.html')


@app.route('/preferences', methods=['GET', 'POST'])
def preferences():
    db = get_db()
    user_id = session.get('user_id')
    if request.method == 'POST':
        regions = request.form.get('regions', '').strip()
        types = request.form.get('types', '').strip()
        keywords = request.form.get('keywords', '').strip()
        channels = request.form.get('channels', '').strip()
        db.execute('''
            INSERT INTO user_preferences (user_id, regions, types, keywords, alert_channels, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                regions=excluded.regions,
                types=excluded.types,
                keywords=excluded.keywords,
                alert_channels=excluded.alert_channels,
                updated_at=CURRENT_TIMESTAMP
        ''', (user_id, regions, types, keywords, channels))
        db.commit()
        flash('Preferences saved', 'success')
        return redirect(url_for('preferences', cleared='1'))
    if request.args.get('cleared') == '1':
        return render_template('preferences.html', pref={})
    pref = db.execute('SELECT * FROM user_preferences WHERE user_id = ?', (user_id,)).fetchone()
    return render_template('preferences.html', pref=dict(pref) if pref else {})

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    db = get_db()
    user_id = session.get('user_id')
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        college = request.form.get('college', '').strip()
        degree = request.form.get('degree', '').strip()
        graduation_year = request.form.get('graduation_year', '').strip()
        skills = request.form.get('skills', '').strip()
        preferred_regions = request.form.get('preferred_regions', '').strip()
        preferred_roles = request.form.get('preferred_roles', '').strip()
        db.execute('''
            INSERT INTO user_profiles (user_id, full_name, college, degree, graduation_year, skills, preferred_regions, preferred_roles, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                full_name=excluded.full_name,
                college=excluded.college,
                degree=excluded.degree,
                graduation_year=excluded.graduation_year,
                skills=excluded.skills,
                preferred_regions=excluded.preferred_regions,
                preferred_roles=excluded.preferred_roles,
                updated_at=CURRENT_TIMESTAMP
        ''', (user_id, full_name, college, degree, graduation_year, skills, preferred_regions, preferred_roles))
        db.commit()
        flash('Profile saved', 'success')
        return redirect(url_for('profile', cleared='1'))
    if request.args.get('cleared') == '1':
        return render_template('profile.html', profile={})
    return render_template('profile.html', profile={})

@app.route('/saved')
def saved():
    db = get_db()
    user_id = session.get('user_id')
    rows = db.execute('''
        SELECT * FROM saved_opportunities WHERE user_id = ?
        ORDER BY created_at DESC
    ''', (user_id,)).fetchall()
    return render_template('saved.html', saved=[dict(r) for r in rows])

@app.route('/alerts')
def alerts():
    db = get_db()
    user_id = session.get('user_id')
    rows = db.execute('''
        SELECT * FROM alert_queue WHERE user_id = ?
        ORDER BY created_at DESC
    ''', (user_id,)).fetchall()
    if not rows:
        generate_alerts_for_user(db, user_id, limit=20)
        rows = db.execute('''
            SELECT * FROM alert_queue WHERE user_id = ?
            ORDER BY created_at DESC
        ''', (user_id,)).fetchall()
    return render_template('alerts.html', alerts=[dict(r) for r in rows])

@app.route('/save-opportunity', methods=['POST'])
def save_opportunity():
    db = get_db()
    user_id = session.get('user_id')
    source = request.form.get('source', 'demo')
    source_id_raw = request.form.get('source_id')
    title = request.form.get('title', '').strip()
    url = request.form.get('url', '').strip()
    source_id = (source_id_raw or '').strip() or None
    if not title:
        flash('Invalid opportunity', 'error')
        return redirect(request.referrer or url_for('opportunities'))
    if source_id:
        existing = db.execute('''
            SELECT 1 FROM saved_opportunities
            WHERE user_id = ? AND source = ? AND source_id = ?
        ''', (user_id, source, source_id)).fetchone()
    else:
        existing = db.execute('''
            SELECT 1 FROM saved_opportunities
            WHERE user_id = ? AND source = ? AND (source_id IS NULL OR source_id = '')
              AND url = ?
        ''', (user_id, source, url)).fetchone()
    if not existing:
        db.execute('''
            INSERT INTO saved_opportunities (user_id, source, source_id, title, url)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, source, source_id, title, url))
        db.commit()
        flash('Saved', 'success')
    else:
        flash('Already saved', 'info')
    return redirect(request.referrer or url_for('opportunities'))

@app.route('/dashboard')
def dashboard():
    db = get_db()
    user_id = session.get('user_id')
    is_admin = is_admin_user(user_id, db)
    
    # Get user-specific data
    rows = db.execute('SELECT * FROM awareness_data WHERE user_id = ? ORDER BY created_at DESC', (user_id,)).fetchall()
    total = len(rows)
    avg_delay = None
    late_count = 0
    avg_delay_ratio = None
    recommendations = []
    
    if total:
        delays = [r['delay_days'] for r in rows if r['delay_days'] is not None]
        if delays:
            avg_delay = round(sum(delays) / len(delays), 2)
        late_count = sum(1 for r in rows if r['delay_category'] == 'Late Access')
        ratios = [r['delay_ratio'] for r in rows if r['delay_ratio'] is not None]
        if ratios:
            avg_delay_ratio = round(sum(ratios) / len(ratios), 4)
        
        # AI: Get recommendations based on latest opportunity
        latest_opp = rows[0] if rows else None
        if latest_opp:
            recommendations = find_similar_opportunities(latest_opp['opportunity_name'], db)
            category_recs = get_opp_recommendations_by_category(
                latest_opp['college_type'], 
                latest_opp['region'], 
                db
            )
            for rec in category_recs[:3]:
                if rec['opportunity_name'].lower() != latest_opp['opportunity_name'].lower():
                    recommendations.append(rec)

    categories = {}
    for r in rows:
        cat = r['delay_category'] or 'Unknown'
        categories[cat] = categories.get(cat, 0) + 1

    data = {
        'total': total,
        'avg_delay': avg_delay,
        'late_percent': round((late_count / total) * 100, 2) if total else 0,
        'avg_delay_ratio': avg_delay_ratio,
        'categories': categories,
        'rows': [dict(r) for r in rows],
        'recommendations': recommendations[:5],
        'is_admin': is_admin
    }
    return render_template('dashboard.html', data=data)

@app.route('/insights')
def insights():
    """Generate and display AI insights about opportunity awareness patterns"""
    db = get_db()
    rows = db.execute('SELECT * FROM awareness_data').fetchall()
    total = len(rows)
    
    if not total:
        return render_template('insights.html', insights=[], insights_data={})

    # Calculate metrics
    late_count = sum(1 for r in rows if r['delay_category'] == 'Late Access')
    medium_count = sum(1 for r in rows if r['delay_category'] == 'Medium Delay')
    early_count = sum(1 for r in rows if r['delay_category'] == 'Early Access')
    
    ratios = [r['delay_ratio'] for r in rows if r['delay_ratio'] is not None]
    avg_ratio = sum(ratios) / len(ratios) if ratios else 0
    max_ratio = max(ratios) if ratios else 0
    
    delays = [r['delay_days'] for r in rows if r['delay_days'] is not None]
    avg_delay = sum(delays) / len(delays) if delays else 0
    
    # Regional analysis
    regions = {}
    for r in rows:
        mapped_regions = extract_regions(r['region'])
        for region in mapped_regions:
            if region not in regions:
                regions[region] = {'total': 0, 'late': 0, 'delay_sum': 0, 'delay_count': 0}
            regions[region]['total'] += 1
            if r['delay_category'] == 'Late Access':
                regions[region]['late'] += 1
            if r['delay_days'] is not None:
                regions[region]['delay_sum'] += r['delay_days']
                regions[region]['delay_count'] += 1

    # India-focused: state vs central aggregation
    def classify_scope(name):
        if name == 'Central / All India':
            return 'central'
        if name in INDIA_UNION_TERRITORIES:
            return 'central'
        if name in INDIA_STATES:
            return 'state'
        return 'state'

    state_stats = []
    central_stats = []
    unknown_total = regions.get('Unknown', {}).get('total', 0)
    for region_name, data in regions.items():
        avg_delay_region = (data['delay_sum'] / data['delay_count']) if data['delay_count'] else 0
        late_pct_region = (data['late'] / data['total']) * 100 if data['total'] else 0
        entry = {
            'region': region_name,
            'total': data['total'],
            'late_pct': round(late_pct_region, 1),
            'avg_delay': round(avg_delay_region, 1),
            'capital': get_region_capital(region_name)
        }
        if region_name == 'Unknown':
            continue
        if classify_scope(region_name) == 'central':
            central_stats.append(entry)
        else:
            state_stats.append(entry)

    state_stats = sorted(state_stats, key=lambda x: x['late_pct'], reverse=True)
    central_stats = sorted(central_stats, key=lambda x: x['late_pct'], reverse=True)
    
    high_risk_regions = []
    for region, data in regions.items():
        if data['total'] > 0:
            late_pct = (data['late'] / data['total']) * 100
            high_risk_regions.append({'region': region, 'late_pct': late_pct, 'count': data['total']})
    high_risk_regions = sorted(high_risk_regions, key=lambda x: x['late_pct'], reverse=True)[:3]

    # Generate insights
    insights_list = []
    
    if (late_count / total) > 0.6:
        insights_list.append(f'🚨 CRITICAL: {(late_count/total)*100:.1f}% of submissions show late awareness. This indicates a major systemic inequality in opportunity reach.')
    elif (late_count / total) > 0.4:
        insights_list.append(f'⚠️ WARNING: {(late_count/total)*100:.1f}% of submissions show late awareness. Significant portions of users receive information too late.')
    else:
        insights_list.append(f'✅ POSITIVE: Only {(late_count/total)*100:.1f}% of submissions show late awareness. Opportunities are reaching users relatively on time.')
    
    if avg_ratio > 0.7:
        insights_list.append(f'📉 SEVERE LOSS: On average, users lose {avg_ratio*100:.1f}% of the opportunity window before becoming aware. This is critical.')
    elif avg_ratio > 0.5:
        insights_list.append(f'📉 MAJOR LOSS: On average, users lose {avg_ratio*100:.1f}% of the opportunity window before becoming aware.')
    else:
        insights_list.append(f'📈 ACCEPTABLE: Users retain approximately {(1-avg_ratio)*100:.1f}% of the opportunity window on average.')
    
    if early_count > 0:
        insights_list.append(f'🌟 EXCELLENCE: {early_count} case(s) of early awareness detected - these are examples of optimal opportunity reach!')
    
    if high_risk_regions:
        top_risk = high_risk_regions[0]
        insights_list.append(f'🗺️ REGIONAL ALERT: {top_risk["region"]} shows {top_risk["late_pct"]:.1f}% late awareness rate ({top_risk["count"]} submissions). Needs targeted intervention.')
    
    insights_list.append(f'📊 DATA QUALITY: Analysis based on {total} submissions across {len(regions)} regions.')

    insights_data = {
        'total': total,
        'late': late_count,
        'medium': medium_count,
        'early': early_count,
        'avg_delay': f'{avg_delay:.1f}',
        'avg_ratio': f'{avg_ratio:.2f}',
        'max_ratio': f'{max_ratio:.2f}',
        'regions': len(regions),
        'high_risk_regions': high_risk_regions,
        'state_stats': state_stats,
        'central_stats': central_stats,
        'unknown_total': unknown_total
    }
    
    return render_template('insights.html', insights=insights_list, insights_data=insights_data)

@app.route('/opportunities')
def opportunities():
    """Show all online opportunities with filtering"""
    db = get_db()
    user_id = session.get('user_id')
    # Get filter parameters
    search_query = request.args.get('search', '')
    filter_region = request.args.get('region', '')
    filter_type = request.args.get('type', '')
    page = int(request.args.get('page', '1') or 1)
    if page < 1:
        page = 1
    
    # Fetch once and reuse for filters + dropdown values.
    all_opps = get_live_opportunities(db, user_id=user_id)
    if search_query or filter_region or filter_type:
        opps = filter_opportunities(
            all_opps,
            query=search_query if search_query else None,
            region=filter_region if filter_region else None,
            internship_type=filter_type if filter_type else None
        )
    else:
        opps = all_opps
    total_count = len(opps)
    start = (page - 1) * OPPS_PAGE_SIZE
    end = start + OPPS_PAGE_SIZE
    opps_page = opps[start:end]
    
    # Get unique values for filter dropdowns
    regions = sorted(set(
        region.strip()
        for opp in all_opps
        for region in (opp.get('region') or '').split(',')
        if region.strip()
    ))
    opportunity_types = sorted(set(opp.get('type') or '' for opp in all_opps if opp.get('type')))
    
    data = {
        'opportunities': opps_page,
        'search_query': search_query,
        'filter_region': filter_region,
        'filter_type': filter_type,
        'regions': regions,
        'opportunity_types': opportunity_types,
        'total_count': total_count,
        'total_available': len(all_opps)
        ,
        'page': page,
        'total_pages': (total_count + OPPS_PAGE_SIZE - 1) // OPPS_PAGE_SIZE
    }
    
    return render_template('opportunities.html', data=data)


if __name__ == '__main__':
    init_db()
    if os.environ.get('ENABLE_SCHEDULER', '0') == '1' and os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        def _scheduler_worker():
            while True:
                try:
                    db = sqlite3.connect(DB_PATH)
                    db.row_factory = sqlite3.Row
                    refresh_external_opportunities(db)
                    db.close()
                except Exception:
                    pass
                time.sleep(EXTERNAL_REFRESH_MINUTES * 60)
        t = threading.Thread(target=_scheduler_worker, daemon=True)
        t.start()
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', '5000'))
    debug = os.environ.get('FLASK_DEBUG', '1') == '1'
    app.run(host=host, port=port, debug=debug)



