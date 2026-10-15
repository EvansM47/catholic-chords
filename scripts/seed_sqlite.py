#!/usr/bin/env python3
"""Build the offline SQLite seed database and FTS5 index from hymns.json."""
import json, sqlite3, pathlib, datetime
ROOT = pathlib.Path(__file__).resolve().parents[1]
source = ROOT / 'assets/hymns/hymns.json'
out = ROOT / 'assets/hymns/hymns.db'
data = json.loads(source.read_text(encoding='utf8'))
if out.exists(): out.unlink()
con = sqlite3.connect(out)
con.executescript('''
PRAGMA foreign_keys = ON;
CREATE TABLE hymns (id TEXT PRIMARY KEY, hymn_number TEXT NOT NULL, title TEXT NOT NULL, lyrics TEXT NOT NULL, chorus TEXT, source_file TEXT NOT NULL, language TEXT, source_book TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE VIRTUAL TABLE hymn_search_fts USING fts5(hymn_id UNINDEXED, hymn_number, title, lyrics, content='hymns', content_rowid='rowid');
CREATE TABLE favorites (hymn_id TEXT PRIMARY KEY REFERENCES hymns(id), created_at TEXT NOT NULL);
CREATE TABLE recent_hymns (id INTEGER PRIMARY KEY AUTOINCREMENT, hymn_id TEXT NOT NULL REFERENCES hymns(id), opened_at TEXT NOT NULL);
CREATE TABLE mass_plans (id TEXT PRIMARY KEY, title TEXT NOT NULL, mass_date TEXT NOT NULL, mass_time TEXT, location TEXT, liturgical_season TEXT NOT NULL, notes TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE mass_parts (id TEXT PRIMARY KEY, mass_plan_id TEXT NOT NULL REFERENCES mass_plans(id), part_code TEXT NOT NULL, label TEXT NOT NULL, part_kind TEXT NOT NULL, position INTEGER NOT NULL, hymn_id TEXT, state TEXT NOT NULL, guidance TEXT, notes TEXT, is_override INTEGER NOT NULL DEFAULT 0);
CREATE TABLE season_templates (id TEXT PRIMARY KEY, name TEXT NOT NULL, source_name TEXT NOT NULL, is_verified INTEGER NOT NULL, notes TEXT);
CREATE TABLE season_template_parts (id TEXT PRIMARY KEY, template_id TEXT NOT NULL REFERENCES season_templates(id), part_code TEXT NOT NULL, label TEXT NOT NULL, part_kind TEXT NOT NULL, position INTEGER NOT NULL, default_state TEXT NOT NULL, guidance TEXT);
CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
''')
now = datetime.datetime.now(datetime.timezone.utc).isoformat()
for h in data:
    con.execute('INSERT INTO hymns VALUES (?,?,?,?,?,?,?,?,?,?)', (h['id'], h['hymnNumber'], h['title'], h.get('lyrics',''), h.get('chorus'), h['sourceFile'], h.get('language',''), h.get('sourceBook','All Glory to Jesus'), now, now))
con.execute("INSERT INTO hymn_search_fts(rowid,hymn_id,hymn_number,title,lyrics) SELECT rowid,id,hymn_number,title,lyrics FROM hymns")
con.commit(); con.close()
print(f'Created {out} with {len(data)} hymns and FTS5 search index')
