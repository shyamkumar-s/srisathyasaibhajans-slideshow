# Bhajans App — SQLite search

Quick setup (Windows):

1. Create a virtualenv and install dependencies

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

2. Load lyrics from `assets/bhajans` into `bhajans.db`:

```bash
python load_lyrics.py --rebuild
```

3. Run the server (starts on port 8000):

```bash
python server.py
```

4. Search endpoint:

- `GET /search?q=your+query&limit=10` — returns JSON results ordered by similarity.
- `POST /reindex` — rebuilds in-memory TF-IDF index.

Notes:
- Each song row now includes a `deity` column derived from the first-level folder under `assets/bhajans`.
- Keep images inside the deity folders and store lyrics in the DB; the loader will parse deity and remaining subfolders as `tags`.
# Data model
- Each song is stored in the SQLite table `songs` with columns: `id`, `title`, `deity`, `tags`, `lyrics`.
- The previous `path` column is removed; images may be kept in the deity folders but lyrics are stored in DB.

Search API response schema
- `GET /search?q=...&limit=...` returns JSON: `{ "results": [ { "id": int, "title": str, "deity": str, "tags": str, "score": float }, ... ] }` ordered by descending similarity score.

Search modes
- Use `mode` query param to choose search behavior:
	- `mode=tfidf` — TF-IDF + cosine similarity (default behavior before fuzzy boost).
	- `mode=fuzzy` — RapidFuzz fuzzy title/deity matching only.
	- `mode=combined` — TF-IDF ranking with a fuzzy title/deity boost (default).

Adding new lyrics via the UI or API
- The frontend provides an "Add new" flow when searches return no results. It submits to `POST /song` with JSON `{ "title": str, "deity": str, "tags": str, "lyrics": str }` and returns `{ "id": int, "status": "created" }`.
- The server triggers a background reindex after creating a song.

Autocomplete
- The search box supports autocomplete suggestions fetched from `GET /autocomplete?q=...&limit=...`. Suggestions are title + deity scored by RapidFuzz.

Cleaning up source files
- Since lyrics are now stored in the database, keeping the original `.txt` files under `assets/bhajans/` is optional. If you want to remove them to save space, ensure you have backups of any images you still need (images can remain under deity folders). If you prefer, I can add a script to export the DB back to `.txt` files before deletion.

Fuzzy/title boosting
- The search now applies normalization and a small fuzzy-title/deity boost (RapidFuzz) combined with TF-IDF scores to better handle transliteration variants and short queries. This improves matches for Sanskrit/transliterated titles without replacing the TF-IDF ranking.

# Sai Bhajans App

A simple static collection of bhajan (devotional song) text files with a lightweight HTML viewer.

## Overview
- This workspace contains `sai-bhajans.html`, which is the main viewer for the bhajans.
- Song files are stored under `assets/bhajans/` organized by category (e.g., `Krishna`, `Sai`, `Anjaneya`).

## Usage
- Open `sai-bhajans.html` in your web browser (double-click or use `File -> Open`).
- Browse categories and select a song to view its text.

## Adding Bhajans
- Add a `.txt` file under `assets/bhajans/<Category>/`.
- Use a clear filename (the app uses the filename as the song title).
- The file content should be plain text (UTF-8 recommended).

## Project structure
- `sai-bhajans.html` — main HTML viewer.
- `assets/bhajans/` — categorized bhajan `.txt` files.

## Notes & Next Steps
- This is a static project — no build steps required.
- If you want, I can add a small script to generate an index or enable search.

## License
- Add a license file if you plan to share this repository publicly.

