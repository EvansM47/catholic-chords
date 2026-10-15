#!/usr/bin/env python3
"""
Sauti za Kuimba (https://sauti.gafkosoft.com/) Catholic Hymn Scraper
Extracts all song lyrics, musical structure (Kiitikio/Chorus vs Mashairi/Verses),
composers, choirs, liturgical categories, YouTube links, and metadata.
"""

import os
import sys
import re
import json
import time
import html
import sqlite3
import argparse
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_URL = "https://sauti.gafkosoft.com"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def get_request(url):
    return urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5,sw;q=0.3",
        }
    )

def fetch_url(url, retries=3, backoff=1.5):
    for attempt in range(retries):
        try:
            req = get_request(url)
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            if attempt == retries - 1:
                print(f"[ERROR] Failed fetching {url} after {retries} attempts: {e}")
                return None
            time.sleep(backoff * (attempt + 1))
    return None

def discover_all_songs(max_pages=18):
    print(f"[*] Discovering songs across up to {max_pages} catalog pages...")
    discovered = []
    seen_ids = set()

    for page in range(1, max_pages + 1):
        url = f"{BASE_URL}/songs/?pg={page}"
        page_html = fetch_url(url)
        if not page_html:
            print(f"[!] Warning: Page {page} could not be retrieved.")
            continue

        matches = re.findall(
            r'<li><a href=[\'"](/songs/(\d+)/([^\'"]+))[\'"]>([^<]+)</a>',
            page_html
        )

        new_on_page = 0
        for path, song_id, slug, title in matches:
            if song_id not in seen_ids:
                seen_ids.add(song_id)
                discovered.append({
                    "id": song_id,
                    "slug": slug,
                    "title": html.unescape(title).strip(),
                    "path": path,
                    "url": f"{BASE_URL}{path}",
                })
                new_on_page += 1

        print(f"  -> Page {page:2d}: Found {len(matches)} links ({new_on_page} new). Cumulative: {len(discovered)}")
        if new_on_page == 0 and page > 1:
            print(f"[*] Reached end of catalog at page {page}.")
            break

        time.sleep(0.2)

    print(f"[+] Total unique songs discovered: {len(discovered)}")
    return discovered

def parse_lyrics_structure(lyrics_block_html):
    """
    Parses lyrics HTML with musical structure detection:
    - Identifies start='0' (Song opens with Kiitikio/Chorus)
    - Distinguishes Kiitikio (Chorus) from Mashairi (Numbered Verses)
    - Handles embedded <h4> chorus blocks inside verse 1
    - Preserves repeat annotations { ... } *2
    """
    if not lyrics_block_html:
        return [], "", ""

    start_match = re.search(r'<ol[^>]*\bstart=[\'"](\d+)[\'"]', lyrics_block_html, re.I)
    start_index = int(start_match.group(1)) if start_match else 1

    lis = re.findall(r'<li[^>]*>(.*?)</li>', lyrics_block_html, re.DOTALL | re.I)
    sections = []
    chorus_text = None
    verse_counter = 1

    if lis:
        for i, li in enumerate(lis):
            idx = start_index + i
            # If start='0' and this is index 0, or the entire li is enclosed in <h4>
            is_pure_chorus = (idx == 0) or bool(re.match(r'^\s*<h4>.*?</h4>\s*$', li, re.DOTALL | re.I))

            if is_pure_chorus:
                clean = html.unescape(re.sub(r'<[^>]+>', '\n', li))
                lines = [l.strip() for l in clean.split('\n') if l.strip()]
                sec_text = '\n'.join(lines)
                if sec_text:
                    sections.append({
                        "type": "chorus",
                        "label": "Kiitikio (Chorus)",
                        "text": sec_text
                    })
                    if not chorus_text:
                        chorus_text = sec_text
            else:
                # Check for <h4> embedded inside verse (typically after Shairi 1)
                embedded_h4 = re.findall(r'<h4>(.*?)</h4>', li, re.DOTALL | re.I)
                if embedded_h4:
                    verse_part = re.sub(r'<h4>.*?</h4>', '', li, flags=re.DOTALL | re.I)
                    clean_v = html.unescape(re.sub(r'<[^>]+>', '\n', verse_part))
                    v_lines = [l.strip() for l in clean_v.split('\n') if l.strip()]
                    if v_lines:
                        sections.append({
                            "type": "verse",
                            "number": verse_counter,
                            "label": f"Shairi {verse_counter}",
                            "text": '\n'.join(v_lines)
                        })
                        verse_counter += 1

                    for ch in embedded_h4:
                        clean_c = html.unescape(re.sub(r'<[^>]+>', '\n', ch))
                        c_lines = [l.strip() for l in clean_c.split('\n') if l.strip()]
                        sec_c_text = '\n'.join(c_lines)
                        if sec_c_text:
                            sections.append({
                                "type": "chorus",
                                "label": "Kiitikio (Chorus)",
                                "text": sec_c_text
                            })
                            if not chorus_text:
                                chorus_text = sec_c_text
                else:
                    clean_v = html.unescape(re.sub(r'<[^>]+>', '\n', li))
                    v_lines = [l.strip() for l in clean_v.split('\n') if l.strip()]
                    if v_lines:
                        sections.append({
                            "type": "verse",
                            "number": verse_counter,
                            "label": f"Shairi {verse_counter}",
                            "text": '\n'.join(v_lines)
                        })
                        verse_counter += 1
    else:
        # Fallback for unlisted lyrics
        clean = html.unescape(re.sub(r'<br\s*/?>', '\n', lyrics_block_html))
        clean = html.unescape(re.sub(r'<[^>]+>', '', clean)).strip()
        if clean:
            sections.append({
                "type": "verse",
                "number": 1,
                "label": "Shairi 1",
                "text": clean
            })

    # Build clean formatted text representation
    formatted_parts = []
    for sec in sections:
        formatted_parts.append(f"[{sec['label'].upper()}]\n{sec['text']}")
    full_text = "\n\n".join(formatted_parts)

    return sections, chorus_text or "", full_text

def parse_song_page(song_info, raw_html):
    if not raw_html:
        return None

    m_title = re.search(r'<h1>(.*?)</h1>', raw_html, re.I)
    title = html.unescape(m_title.group(1).strip()) if m_title else song_info.get("title", "")

    metadata = {
        "performed_by": "",
        "choir_slug": "",
        "choir_url": "",
        "composer": "",
        "album": "",
        "category": "",
        "category_slug": "",
        "category_url": "",
        "views": "",
        "skiza_id": "",
    }

    infobox = re.search(r'<table class=[\'"]infobox[\'"]>(.*?)</table>', raw_html, re.DOTALL | re.I)
    if infobox:
        rows = re.findall(r'<tr>(.*?)</tr>', infobox.group(1), re.DOTALL | re.I)
        for r in rows:
            tds = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', r, re.DOTALL | re.I)
            if len(tds) == 2:
                key = re.sub(r'<[^>]+>', '', tds[0]).strip().lower()
                val_raw = tds[1].strip()
                val_text = html.unescape(re.sub(r'<[^>]+>', '', val_raw)).strip()
                if val_text == "-":
                    val_text = ""

                # Extract link if present
                link_m = re.search(r'href=[\'"]([^\'"]+)[\'"]', val_raw)
                link_val = link_m.group(1) if link_m else ""

                if "performed" in key or "choir" in key:
                    metadata["performed_by"] = val_text
                    if link_val:
                        metadata["choir_url"] = f"{BASE_URL}{link_val}" if link_val.startswith("/") else link_val
                        slug_m = re.search(r'/choirs/([^/?#]+)', link_val)
                        if slug_m:
                            metadata["choir_slug"] = slug_m.group(1)
                elif "composer" in key:
                    metadata["composer"] = val_text
                elif "album" in key:
                    metadata["album"] = val_text
                elif "category" in key:
                    metadata["category"] = val_text
                    if link_val:
                        metadata["category_url"] = f"{BASE_URL}{link_val}" if link_val.startswith("/") else link_val
                        slug_m = re.search(r'/categories/([^/?#]+)', link_val)
                        if slug_m:
                            metadata["category_slug"] = slug_m.group(1)
                elif "view" in key:
                    metadata["views"] = val_text
                elif "skiza" in key:
                    metadata["skiza_id"] = val_text

    # YouTube details
    yt_m = re.search(r'href=[\'"](https?://(?:www\.)?youtube\.com/watch\?v=([^\'"\s&]+)[^\'"]*)[\'"]', raw_html)
    video_url = yt_m.group(1) if yt_m else None
    youtube_id = yt_m.group(2) if yt_m else None
    youtube_thumbnail = f"https://img.youtube.com/vi/{youtube_id}/hqdefault.jpg" if youtube_id else None

    # Lyrics & musical structure
    lyrics_block = re.search(r'<div id=[\'"]lyrics[\'"][^>]*>(.*?)</div>', raw_html, re.DOTALL | re.I)
    lyrics_html = lyrics_block.group(1) if lyrics_block else ""
    sections, chorus_text, full_lyrics = parse_lyrics_structure(lyrics_html)

    # Views count
    view_count = None
    if metadata["views"]:
        num = re.sub(r'[^\d]', '', metadata["views"])
        if num:
            view_count = int(num)

    return {
        "id": song_info["id"],
        "title": title,
        "slug": song_info["slug"],
        "composer": metadata["composer"],
        "choir": metadata["performed_by"],
        "choir_slug": metadata["choir_slug"],
        "choir_url": metadata["choir_url"],
        "album": metadata["album"],
        "category": metadata["category"] or "General",
        "category_slug": metadata["category_slug"],
        "category_url": metadata["category_url"],
        "skiza_id": metadata["skiza_id"],
        "views": view_count,
        "video_url": video_url,
        "youtube_id": youtube_id,
        "youtube_thumbnail": youtube_thumbnail,
        "chorus": chorus_text,
        "sections": sections,
        "verse_count": sum(1 for s in sections if s["type"] == "verse"),
        "lyrics": full_lyrics,
        "source_url": song_info["url"],
        "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

def scrape_songs(songs_to_scrape, out_dir, max_workers=8):
    html_dir = os.path.join(out_dir, "raw_html")
    text_dir = os.path.join(out_dir, "text")
    os.makedirs(html_dir, exist_ok=True)
    os.makedirs(text_dir, exist_ok=True)

    results = []
    total = len(songs_to_scrape)
    completed = 0

    print(f"[*] Downloading and structuring {total} songs using {max_workers} threads...")

    def worker(song):
        html_file = os.path.join(html_dir, f"{song['id']}.html")
        raw_html = None

        if os.path.exists(html_file):
            try:
                with open(html_file, "r", encoding="utf-8") as f:
                    raw_html = f.read()
            except Exception:
                pass

        if not raw_html:
            raw_html = fetch_url(song["url"])
            if raw_html:
                with open(html_file, "w", encoding="utf-8") as f:
                    f.write(raw_html)

        if not raw_html:
            return None

        parsed = parse_song_page(song, raw_html)
        if parsed:
            # Write individual formatted text file
            txt_filename = f"{parsed['id']}_{parsed['slug']}.txt"
            txt_path = os.path.join(text_dir, txt_filename)
            with open(txt_path, "w", encoding="utf-8") as f:
                header = [
                    f"WIMBO: {parsed['title'].upper()}",
                    f"Mtunzi (Composer): {parsed['composer'] or 'Hajatajwa'}",
                    f"Kwaya (Choir): {parsed['choir'] or 'Haijatajwa'}",
                    f"Sehemu ya Misa/Kipindi: {parsed['category']}",
                ]
                if parsed['album']:
                    header.append(f"Albamu: {parsed['album']}")
                if parsed['video_url']:
                    header.append(f"YouTube: {parsed['video_url']}")
                header.append("=" * 40)
                header.append("")
                header.append(parsed['lyrics'])
                f.write("\n".join(header) + "\n")

        return parsed

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(worker, s): s for s in songs_to_scrape}
        for future in as_completed(future_map):
            completed += 1
            song = future_map[future]
            try:
                data = future.result()
                if data:
                    results.append(data)
                if completed % 100 == 0 or completed == total:
                    print(f"  [{completed:4d}/{total:4d}] ({completed/total*100:5.1f}%) Processed: {song['title'][:32]}")
            except Exception as e:
                print(f"[!] Error on {song['url']}: {e}")

    results.sort(key=lambda s: s["title"].lower())
    return results

def save_sqlite(songs, db_path):
    print(f"[*] Rebuilding SQLite database at {db_path}...")
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE songs (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            slug TEXT,
            composer TEXT,
            choir TEXT,
            choir_slug TEXT,
            choir_url TEXT,
            album TEXT,
            category TEXT,
            category_slug TEXT,
            category_url TEXT,
            views INTEGER,
            video_url TEXT,
            youtube_id TEXT,
            youtube_thumbnail TEXT,
            skiza_id TEXT,
            chorus TEXT,
            sections_json TEXT,
            verse_count INTEGER,
            lyrics TEXT,
            source_url TEXT
        )
    """)

    cur.execute("""
        CREATE VIRTUAL TABLE songs_fts USING fts5(
            id UNINDEXED,
            title,
            lyrics,
            chorus,
            composer,
            choir,
            category
        )
    """)

    for s in songs:
        cur.execute("""
            INSERT INTO songs (
                id, title, slug, composer, choir, choir_slug, choir_url,
                album, category, category_slug, category_url, views,
                video_url, youtube_id, youtube_thumbnail, skiza_id,
                chorus, sections_json, verse_count, lyrics, source_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            s["id"], s["title"], s["slug"], s["composer"], s["choir"], s["choir_slug"], s["choir_url"],
            s["album"], s["category"], s["category_slug"], s["category_url"], s["views"],
            s["video_url"], s["youtube_id"], s["youtube_thumbnail"], s["skiza_id"],
            s["chorus"], json.dumps(s.get("sections", []), ensure_ascii=False),
            s["verse_count"], s["lyrics"], s["source_url"]
        ))

        cur.execute("""
            INSERT INTO songs_fts (id, title, lyrics, chorus, composer, choir, category)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            s["id"], s["title"], s["lyrics"], s["chorus"], s["composer"], s["choir"], s["category"]
        ))

    conn.commit()
    conn.close()
    print(f"[+] SQLite database created successfully with {len(songs)} songs and FTS5 search index.")

def generate_summary(songs, out_path):
    from collections import Counter
    categories = Counter(s.get("category") or "Unknown" for s in songs)
    choirs = Counter(s.get("choir") or "Not Specified" for s in songs)
    composers = Counter(s.get("composer") or "Not Specified" for s in songs)
    with_lyrics = sum(1 for s in songs if len(s.get("lyrics", "").strip()) > 0)
    with_chorus = sum(1 for s in songs if len(s.get("chorus", "").strip()) > 0)
    with_video = sum(1 for s in songs if s.get("video_url"))

    lines = [
        "# Sauti za Kuimba — Complete Musical Catalog Summary",
        f"**Generated:** {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}",
        "",
        "## Overall Metrics",
        f"- **Total Songs Scraped:** {len(songs)}",
        f"- **Songs with Complete Lyrics:** {with_lyrics} ({with_lyrics/len(songs)*100:.1f}%)",
        f"- **Songs with Explicit Kiitikio / Chorus Identified:** {with_chorus} ({with_chorus/len(songs)*100:.1f}%)",
        f"- **Songs with YouTube Links & Thumbnails:** {with_video}",
        f"- **Unique Liturgical Categories:** {len(categories)}",
        f"- **Unique Choirs:** {len(choirs)}",
        f"- **Unique Composers:** {len(composers)}",
        "",
        "## Songs by Liturgical Category",
        "| Category | Song Count |",
        "|---|---|",
    ]
    for cat, count in categories.most_common():
        lines.append(f"| {cat} | {count} |")

    lines.extend([
        "",
        "## Top Choirs",
        "| Choir | Song Count |",
        "|---|---|",
    ])
    for ch, count in choirs.most_common(20):
        if ch != "Not Specified":
            lines.append(f"| {ch} | {count} |")

    lines.extend([
        "",
        "## Top Composers",
        "| Composer | Song Count |",
        "|---|---|",
    ])
    for cp, count in composers.most_common(20):
        if cp != "Not Specified":
            lines.append(f"| {cp} | {count} |")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[+] Summary written to {out_path}")

def main():
    parser = argparse.ArgumentParser(description="Scrape and structure songs from sauti.gafkosoft.com")
    parser.add_argument("--test", action="store_true", help="Run test on first 10 songs only")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of songs to scrape")
    parser.add_argument("--workers", type=int, default=10, help="Number of concurrent worker threads")
    parser.add_argument("--out-dir", default="assets/sauti", help="Output directory for assets")
    args = parser.parse_args()

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    out_dir = os.path.join(project_root, args.out_dir)
    catalog_cache_file = os.path.join(out_dir, "discovered_catalog.json")
    os.makedirs(out_dir, exist_ok=True)

    if os.path.exists(catalog_cache_file):
        print(f"[*] Loading discovered catalog from {catalog_cache_file}...")
        with open(catalog_cache_file, "r", encoding="utf-8") as f:
            all_songs = json.load(f)
    else:
        all_songs = discover_all_songs(max_pages=18)
        with open(catalog_cache_file, "w", encoding="utf-8") as f:
            json.dump(all_songs, f, ensure_ascii=False, indent=2)

    if args.test:
        songs_to_scrape = all_songs[:10]
    elif args.limit:
        songs_to_scrape = all_songs[:args.limit]
    else:
        songs_to_scrape = all_songs

    scraped_songs = scrape_songs(songs_to_scrape, out_dir, max_workers=args.workers)

    json_path = os.path.join(out_dir, "sauti_songs.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(scraped_songs, f, ensure_ascii=False, indent=2)
    print(f"[+] Saved {len(scraped_songs)} structured songs to {json_path}")

    db_path = os.path.join(out_dir, "sauti_songs.db")
    save_sqlite(scraped_songs, db_path)

    summary_path = os.path.join(project_root, "docs", "SAUTI_CATALOG_SUMMARY.md")
    os.makedirs(os.path.dirname(summary_path), exist_ok=True)
    generate_summary(scraped_songs, summary_path)

    print("\n[SUCCESS] Sauti za Kuimba musical structure scrape complete!")

if __name__ == "__main__":
    main()
