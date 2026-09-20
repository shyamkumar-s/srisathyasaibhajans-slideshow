from flask import Flask, request, jsonify, send_file, send_from_directory
import threading
import sqlite3
import os
import sys
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile
import xml.etree.ElementTree as ET
from rapidfuzz import fuzz
import unicodedata
import re
from xml.sax.saxutils import escape as xml_escape

def get_base_path():
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(__file__)


def get_db_path():
    configured_db_path = os.environ.get('BHAJANS_DB_PATH')
    if configured_db_path and configured_db_path.strip():
        return os.path.abspath(os.path.expanduser(configured_db_path.strip()))
    return os.path.join(get_base_path(), "bhajans.db")


BASE_PATH = get_base_path()
DB_PATH = get_db_path()
STATIC_PATH = os.path.join(BASE_PATH, 'assets')

# Flask app should use the absolute static folder so bundled apps find assets
app = Flask(__name__, static_folder=STATIC_PATH)

# In-memory index objects
_vectorizer = None
_matrix = None
_ids = []
# title map for fuzzy matching: id -> original title
_titles = {}
_deities = {}
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

def clean_xml_text(value):
    text = str(value or '')
    return re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F]', '', text)

def xlsx_cell(value, is_number=False):
    if is_number:
        return f'<c><v>{int(value)}</v></c>'
    text = xml_escape(clean_xml_text(value), {'"': '&quot;', "'": '&apos;'})
    return f'<c t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'

def create_songs_xlsx(rows):
    headers = ('ID', 'Title', 'Deity', 'Tags', 'Lyrics')
    row_xml = ['<row r="1">' + ''.join(xlsx_cell(value) for value in headers) + '</row>']
    for row_number, row in enumerate(rows, start=2):
        values = (
            xlsx_cell(row['id'], is_number=True),
            xlsx_cell(row['title']),
            xlsx_cell(row['deity']),
            xlsx_cell(row['tags']),
            xlsx_cell(row['lyrics']),
        )
        row_xml.append(f'<row r="{row_number}">' + ''.join(values) + '</row>')

    worksheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheetData>' + ''.join(row_xml) + '</sheetData></worksheet>'
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Bhajans" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '</Types>'
    )
    package_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>'
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '</Relationships>'
    )
    output = BytesIO()
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', content_types)
        archive.writestr('_rels/.rels', package_rels)
        archive.writestr('xl/workbook.xml', workbook)
        archive.writestr('xl/_rels/workbook.xml.rels', workbook_rels)
        archive.writestr('xl/worksheets/sheet1.xml', worksheet)
    output.seek(0)
    return output

def parse_xlsx_rows(file_bytes):
    with ZipFile(BytesIO(file_bytes)) as archive:
        shared_strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            root = ET.fromstring(archive.read('xl/sharedStrings.xml'))
            namespace = {'x': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            for item in root.findall('x:si', namespace):
                shared_strings.append(''.join(item.itertext()))
        sheet_name = 'xl/worksheets/sheet1.xml'
        if sheet_name not in archive.namelist():
            raise ValueError('The workbook does not contain a first worksheet')
        root = ET.fromstring(archive.read(sheet_name))
        namespace = {'x': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        rows = []
        for row in root.findall('.//x:sheetData/x:row', namespace):
            values = []
            for cell in row.findall('x:c', namespace):
                reference = cell.get('r', '')
                column = re.match(r'([A-Z]+)', reference)
                if column:
                    column_index = 0
                    for letter in column.group(1):
                        column_index = column_index * 26 + ord(letter) - ord('A') + 1
                    while len(values) < column_index - 1:
                        values.append('')
                value = cell.find('x:v', namespace)
                inline = cell.find('x:is', namespace)
                if inline is not None:
                    text = ''.join(inline.itertext())
                elif value is not None:
                    text = value.text or ''
                    if cell.get('t') == 's' and text.isdigit():
                        text = shared_strings[int(text)]
                else:
                    text = ''
                if column:
                    while len(values) < column_index:
                        values.append('')
                    values[column_index - 1] = text
                else:
                    values.append(text)
            rows.append(values)
        return rows

def normalize_header(value):
    return re.sub(r'[^a-z0-9]', '', str(value or '').lower())

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
        deities = {}
        for r in rows:
            text = " ".join([r['title'] or '', r['deity'] or '', r['tags'] or '', r['lyrics'] or ''])
            docs.append(text)
            ids.append(r['id'])
            titles[r['id']] = r['title'] or ''
            deities[r['id']] = r['deity'] or ''
        if docs:
            _vectorizer = TfidfVectorizer(stop_words='english')
            _matrix = _vectorizer.fit_transform(docs)
            _ids = ids
            _titles.clear()
            _titles.update(titles)
            _deities.clear()
            _deities.update(deities)
        else:
            _vectorizer = None
            _matrix = None
            _ids = []
            _titles.clear()
            _deities.clear()

@app.route('/')
def index():
    return send_from_directory(BASE_PATH, 'sai-bhajans.html')

@app.route('/songs')
def songs():
    query = request.args.get('q', '').strip()
    conn = get_db_connection()
    cur = conn.cursor()
    if query:
        pattern = f'%{query}%'
        cur.execute(
            'SELECT id, title, deity, tags FROM songs '
            'WHERE title LIKE ? OR deity LIKE ? OR tags LIKE ? ORDER BY id',
            (pattern, pattern, pattern)
        )
    else:
        cur.execute('SELECT id, title, deity, tags FROM songs ORDER BY id')
    result = [dict(row) for row in cur.fetchall()]
    conn.close()
    return jsonify({'songs': result})

@app.route('/samithi-map', methods=['POST'])
def upload_samithi_map():
    uploaded = request.files.get('file')
    if not uploaded:
        return jsonify({'error': 'Excel file is required'}), 400
    try:
        rows = parse_xlsx_rows(uploaded.read())
    except Exception as error:
        return jsonify({'error': f'Unable to read Excel file: {error}'}), 400
    if not rows:
        return jsonify({'error': 'The Excel file is empty'}), 400
    headers = [normalize_header(value) for value in rows[0]]
    first_line_index = next((i for i, value in enumerate(headers) if value in ('firstline', 'songfirstline', 'lyricsfirstline')), None)
    samithi_index = next((i for i, value in enumerate(headers) if value in ('samithi', 'samithiname', 'center', 'centre')), None)
    id_index = next((i for i, value in enumerate(headers) if value in ('id', 'songid', 'bhajanid')), None)
    if first_line_index is None or samithi_index is None:
        return jsonify({'error': 'Excel must contain First Line and Samithi Name columns'}), 400
    mappings = []
    for row in rows[1:]:
        get_value = lambda index: str(row[index]).strip() if index is not None and index < len(row) else ''
        first_line = get_value(first_line_index)
        samithi = get_value(samithi_index)
        song_id = get_value(id_index)
        if first_line and samithi:
            mappings.append({'id': song_id, 'firstLine': first_line, 'samithi': samithi})
    return jsonify({'mappings': mappings, 'count': len(mappings)})

@app.route('/songs.xlsx')
def export_songs_xlsx():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT id, title, deity, tags, lyrics FROM songs ORDER BY id')
    rows = cur.fetchall()
    conn.close()
    workbook = create_songs_xlsx(rows)
    return send_file(
        workbook,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='bhajans.xlsx'
    )

@app.route('/search')
def search():
    q = request.args.get('q', '').strip()
    qn = normalize_text(q)
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
        # initial ordering by TF-IDF similarity
        idx_order = np.argsort(-sims)
        # ensure any exact normalized-title matches appear first
        # consider normalized equality or prefix/containment as an exact-like match
        exact_idxs = [i for i, sid in enumerate(_ids) if (lambda t: t == qn or qn.startswith(t) or t.startswith(qn))(normalize_text(_titles.get(sid, '')))]
        # move exact indices to front preserving their order
        idx_list = [int(i) for i in idx_order]
        for ei in reversed(exact_idxs):
            if ei in idx_list:
                idx_list.remove(ei)
            idx_list.insert(0, ei)
        idx_order = idx_list[:limit]
    else:
        # fuzzy-only: ensure titles present
        if not _titles:
            build_index()
        # compute fuzzy score across all titles and deities (use cached deities)
        scores = []
        qn = normalize_text(q)
        for i, sid in enumerate(_ids):
            title = _titles.get(sid, '')
            deity = _deities.get(sid, '')
            tnorm = normalize_text(title)
            score_title = fuzz.token_sort_ratio(qn, tnorm) if title else 0
            score_deity = fuzz.token_sort_ratio(qn, normalize_text(deity)) if deity else 0
            score = max(score_title, score_deity, 0)
            # explicit exact-match boost (highest possible fuzzy score)
            if tnorm == qn or qn.startswith(tnorm) or tnorm.startswith(qn):
                score = 100
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
            fuzzy_title = fuzz.token_sort_ratio(qn, normalize_text(title)) / 100.0
            cur.execute("SELECT deity, tags FROM songs WHERE id=?", (sid,))
            _row = cur.fetchone()
            deity = _row['deity'] if _row else ''
            fuzzy_deity = fuzz.token_sort_ratio(qn, normalize_text(deity)) / 100.0
            qlen = len(q)
            fuzzy_weight = 0.35 if qlen <= 30 else 0.15
            score = (0.85 * tfidf_score) + (fuzzy_weight * max(fuzzy_title, fuzzy_deity))
            # boost exact normalized title matches to ensure top placement
            if normalize_text(title) == qn or qn.startswith(normalize_text(title)) or normalize_text(title).startswith(qn):
                score = max(score, 0.99)
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


@app.route('/song/<int:song_id>', methods=['DELETE'])
def delete_song(song_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT id FROM songs WHERE id=?', (song_id,))
    r = cur.fetchone()
    if not r:
        conn.close()
        return jsonify({'error': 'not found'}), 404
    cur.execute('DELETE FROM songs WHERE id=?', (song_id,))
    conn.commit()
    conn.close()
    # rebuild index in background
    threading.Thread(target=build_index, daemon=True).start()
    return jsonify({'status': 'deleted', 'id': song_id})


@app.route('/autocomplete')
def autocomplete():
    q = request.args.get('q', '').strip()
    limit = int(request.args.get('limit', '10'))
    if not q:
        return jsonify({'suggestions': []})
    # ensure titles available
    if not _titles:
        build_index()
    # compute fuzzy score against titles and deity, but prioritize exact normalized matches
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
        if tnorm == qn:
            score = 100
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
    print(f"Using database: {DB_PATH}", flush=True)
    print("Starting Sri Sathya Sai Bhajans server on http://127.0.0.1:8000", flush=True)
    # Build the search index in the background so packaged macOS builds start listening promptly.
    if os.path.exists(DB_PATH):
        threading.Thread(target=build_index, daemon=True).start()
    app.run(host='0.0.0.0', port=8000)
