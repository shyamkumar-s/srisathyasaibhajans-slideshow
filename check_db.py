import sqlite3
import pprint

DB = 'bhajans.db'

def main():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    try:
        cur.execute('SELECT count(*) FROM songs')
        cnt = cur.fetchone()[0]
        cur.execute('SELECT id, title, deity, tags FROM songs LIMIT 5')
        rows = cur.fetchall()
    except Exception as e:
        print('ERROR', e)
        return
    finally:
        conn.close()
    print('COUNT:', cnt)
    pprint.pprint(rows)

if __name__ == '__main__':
    main()
