import os
import sqlite3
import argparse

DB_PATH = os.path.join(os.path.dirname(__file__), "bhajans.db")

def init_db(conn):
    cur = conn.cursor()
    cur.execute('''
    CREATE TABLE IF NOT EXISTS songs (
        id INTEGER PRIMARY KEY,
        title TEXT,
        deity TEXT,
        tags TEXT,
        lyrics TEXT
    )
    ''')
    # Ensure deity column exists (for older DBs)
    cur.execute("PRAGMA table_info(songs)")
    cols = [r[1] for r in cur.fetchall()]
    if 'deity' not in cols:
        cur.execute('ALTER TABLE songs ADD COLUMN deity TEXT')
    conn.commit()

def scan_and_load(root_folder, conn, clear=False):
    cur = conn.cursor()
    if clear:
        cur.execute('DELETE FROM songs')
    id_count = 0
    for dirpath, dirs, files in os.walk(root_folder):
        for f in files:
            if not f.lower().endswith('.txt'):
                continue
            full = os.path.join(dirpath, f)
            try:
                with open(full, 'r', encoding='utf-8') as fh:
                    lyrics = fh.read().strip()
            except Exception:
                continue
            title = os.path.splitext(f)[0]
            # derive deity as first level folder under assets/bhajans, tags are remaining folders
            rel_dir = os.path.relpath(dirpath, start=os.path.join(os.path.dirname(__file__), 'assets', 'bhajans'))
            parts = [p for p in os.path.normpath(rel_dir).split(os.sep) if p and p != os.curdir]
            deity = parts[0] if parts else ''
            tags = ','.join(parts[1:]) if len(parts) > 1 else ''
            cur.execute('INSERT INTO songs (title, deity, tags, lyrics) VALUES (?, ?, ?, ?)', (title, deity, tags, lyrics))
            id_count += 1

    # If an older DB still has a `path` column, migrate to a new table without it
    cur.execute("PRAGMA table_info(songs)")
    cols = [r[1] for r in cur.fetchall()]
    if 'path' in cols:
        # perform migration: copy data to new table without path
        cur.execute('''
            CREATE TABLE IF NOT EXISTS songs_new (
                id INTEGER PRIMARY KEY,
                title TEXT,
                deity TEXT,
                tags TEXT,
                lyrics TEXT
            )
        ''')
        cur.execute('INSERT OR IGNORE INTO songs_new (id, title, deity, tags, lyrics) SELECT id, title, deity, tags, lyrics FROM songs')
        cur.execute('DROP TABLE songs')
        cur.execute('ALTER TABLE songs_new RENAME TO songs')
        conn.commit()
    conn.commit()
    return id_count

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default=os.path.join(os.path.dirname(__file__), 'assets', 'bhajans'))
    parser.add_argument('--rebuild', action='store_true')
    args = parser.parse_args()
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    count = scan_and_load(args.root, conn, clear=args.rebuild)
    conn.close()
    print(f'Loaded {count} text files into {DB_PATH}')

if __name__ == '__main__':
    main()
