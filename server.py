from flask import Flask, request, jsonify, send_from_directory
import threading
import sqlite3
import os
import sys
from rapidfuzz import fuzz
import unicodedata
import re

def get_base_path():
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(__file__)

BASE_PATH = get_base_path()
DB_PATH = os.path.join(BASE_PATH, "bhajans.db")
STATIC_PATH = os.path.join(BASE_PATH, 'assets')

# Flask app should use the absolute static folder so bundled apps find assets
app = Flask(__name__, static_folder=STATIC_PATH)

# In-memory index objects
_vectorizer = None
_matrix = None
_ids = []
# title map for fuzzy matching: id -> original title
_titles = {}
_index_lock = threading.Lock()


def normalize_text(s: str) -> str:
    if not s:
        return ''
    s = str(s)
    # Unicode normalize and remove diacritics
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower()
    # remove punctuation except spaces
    s = re.sub(r"[^0-9a-z\s]", " ", s)
    # collapse spaces
    s = re.sub(r"\s+", " ", s).strip()
    return s

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def build_index():
    global _vectorizer, _matrix, _ids
    with _index_lock:
        from sklearn.feature_extraction.text import TfidfVectorizer

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, title, deity, tags, lyrics FROM songs")
        rows = cur.fetchall()
        conn.close()
        docs = []
        ids = []
        titles = {}
        for r in rows:
            text = " ".join([r['title'] or '', r['deity'] or '', r['tags'] or '', r['lyrics'] or ''])
            docs.append(text)
            ids.append(r['id'])
            titles[r['id']] = r['title'] or ''
        if docs:
            _vectorizer = TfidfVectorizer(stop_words='english')
            _matrix = _vectorizer.fit_transform(docs)
            _ids = ids
            _titles.clear()
            _titles.update(titles)
        else:
            _vectorizer = None
            _matrix = None
            _ids = []
            _titles.clear()

@app.route('/')
def index():
    return send_from_directory(BASE_PATH, 'sai-bhajans.html')

@app.route('/search')
def search():
    q = request.args.get('q', '').strip()
    limit = int(request.args.get('limit', '10'))
    mode = request.args.get('mode', 'combined').lower()  # tfidf | fuzzy | combined
    if not q:
        return jsonify({'error': 'query param `q` required'}), 400
    # ensure index/titles are available for requested mode
    if mode in ('tfidf', 'combined'):
        if _vectorizer is None or _matrix is None:
            build_index()
        if _vectorizer is None or _matrix is None:
            return jsonify({'results': []})
        from sklearn.metrics.pairwise import cosine_similarity
        import numpy as np

        qv = _vectorizer.transform([q])
        sims = cosine_similarity(qv, _matrix)[0]
        idx_order = np.argsort(-sims)[:limit]
    else:
        # fuzzy-only: ensure titles present
        if not _titles:
            build_index()
        # compute fuzzy score across all titles and deities
        scores = []
        for i, sid in enumerate(_ids):
            title = _titles.get(sid, '')
            # fetch deity quickly by querying DB (cached for top-N later)
            score = max(fuzz.token_sort_ratio(normalize_text(q), normalize_text(title)), 0)
            scores.append((i, score))
        # sort by fuzzy score desc
        scores.sort(key=lambda x: -x[1])
        idx_order = [s[0] for s in scores[:limit]]
    results = []
    conn = get_db_connection()
    cur = conn.cursor()
    # process selected indexes depending on mode
    for idx in idx_order:
        sid = _ids[idx]
        if mode == 'tfidf':
            score = float(sims[idx])
        elif mode == 'combined':
            tfidf_score = float(sims[idx])
            title = _titles.get(sid, '')
            fuzzy_title = fuzz.token_sort_ratio(normalize_text(q), normalize_text(title)) / 100.0
            cur.execute("SELECT deity, tags FROM songs WHERE id=?", (sid,))
            _row = cur.fetchone()
            deity = _row['deity'] if _row else ''
            fuzzy_deity = fuzz.token_sort_ratio(normalize_text(q), normalize_text(deity)) / 100.0
            qlen = len(q)
            fuzzy_weight = 0.35 if qlen <= 30 else 0.15
            score = (0.85 * tfidf_score) + (fuzzy_weight * max(fuzzy_title, fuzzy_deity))
        else:  # fuzzy-only
            # score was computed earlier as integer 0-100 in scores list; convert to 0-1
            # to fetch that, compute again for this sid
            title = _titles.get(sid, '')
            fuzzy_score = max(fuzz.token_sort_ratio(normalize_text(q), normalize_text(title)), 0) / 100.0
            cur.execute("SELECT deity, tags FROM songs WHERE id=?", (sid,))
            _row = cur.fetchone()
            deity = _row['deity'] if _row else ''
            fuzzy_deity = max(fuzz.token_sort_ratio(normalize_text(q), normalize_text(deity)), 0) / 100.0
            score = max(fuzzy_score, fuzzy_deity)
        cur.execute("SELECT id, title, deity, tags FROM songs WHERE id=?", (sid,))
        r = cur.fetchone()
        if r:
            results.append({'id': r['id'], 'title': r['title'], 'deity': r['deity'], 'tags': r['tags'], 'score': score})
    conn.close()
    return jsonify({'results': results})

@app.route('/reindex', methods=['POST'])
def reindex():
    # rebuild index in background thread
    thread = threading.Thread(target=build_index, daemon=True)
    thread.start()
    return jsonify({'status': 'reindex started'})


@app.route('/song/<int:song_id>')
def get_song(song_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT id, title, deity, tags, lyrics FROM songs WHERE id=?', (song_id,))
    r = cur.fetchone()
    conn.close()
    if not r:
        return jsonify({'error': 'not found'}), 404
    return jsonify({'id': r['id'], 'title': r['title'], 'deity': r['deity'], 'tags': r['tags'], 'lyrics': r['lyrics']})


@app.route('/song', methods=['POST'])
def create_song():
    body = request.get_json() or {}
    title = body.get('title', '').strip()
    deity = body.get('deity', '').strip()
    tags = body.get('tags', '').strip()
    lyrics = body.get('lyrics', '').strip()
    if not title or not lyrics:
        return jsonify({'error': 'title and lyrics required'}), 400
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('INSERT INTO songs (title, deity, tags, lyrics) VALUES (?, ?, ?, ?)', (title, deity, tags, lyrics))
    conn.commit()
    song_id = cur.lastrowid
    conn.close()
    # rebuild index in background
    threading.Thread(target=build_index, daemon=True).start()
    return jsonify({'id': song_id, 'status': 'created'})


@app.route('/autocomplete')
def autocomplete():
    q = request.args.get('q', '').strip()
    limit = int(request.args.get('limit', '10'))
    if not q:
        return jsonify({'suggestions': []})
    # ensure titles available
    if not _titles:
        build_index()
    # compute fuzzy score against titles and deity
    qn = normalize_text(q)
    scores = []
    conn = get_db_connection()
    cur = conn.cursor()
    for sid in _ids:
        title = _titles.get(sid, '')
        tnorm = normalize_text(title)
        score_title = fuzz.token_sort_ratio(qn, tnorm)
        # get deity for small boost
        cur.execute('SELECT deity FROM songs WHERE id=?', (sid,))
        row = cur.fetchone()
        deity = row['deity'] if row else ''
        dnorm = normalize_text(deity)
        score_deity = fuzz.token_sort_ratio(qn, dnorm) if deity else 0
        score = max(score_title, score_deity)
        if score > 20:
            scores.append((sid, score, title, deity))
    conn.close()
    scores.sort(key=lambda x: -x[1])
    seen = set()
    suggestions = []
    for sid, score, title, deity in scores:
        key = (title.lower(), deity.lower() if deity else '')
        if key in seen:
            continue
        seen.add(key)
        suggestions.append({'id': sid, 'title': title, 'deity': deity, 'score': score/100.0})
        if len(suggestions) >= limit:
            break
    return jsonify({'suggestions': suggestions})


@app.route('/images_manifest')
def images_manifest():
    # Walk the assets/images directory on the server and return per-deity image URLs
    images_root = os.path.join(os.path.dirname(__file__), 'assets', 'images')
    result = {}
    if not os.path.isdir(images_root):
        return jsonify(result)
    for entry in sorted(os.listdir(images_root)):
        p = os.path.join(images_root, entry)
        if os.path.isdir(p):
            files = []
            for fname in sorted(os.listdir(p)):
                ext = fname.split('.')[-1].lower()
                if ext in ('jpg','jpeg','png','gif','webp','bmp','svg'):
                    # construct URL relative to server root
                    files.append(f"/assets/images/{entry}/{fname}")
            if files:
                result[entry] = files
    return jsonify(result)

if __name__ == '__main__':
    print("Starting Sri Sathya Sai Bhajans server on http://127.0.0.1:8000", flush=True)
    # Build the search index in the background so packaged macOS builds start listening promptly.
    if os.path.exists(DB_PATH):
        threading.Thread(target=build_index, daemon=True).start()
    app.run(host='0.0.0.0', port=8000)
