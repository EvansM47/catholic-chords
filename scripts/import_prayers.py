#!/usr/bin/env python3
"""Import prayer sections from the supplied Christ Is All PDF using Poppler."""
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PDF = Path.home() / 'Downloads' / 'CHRIST_IS_ALL_BOOK.pdf'
OUT = ROOT / 'assets' / 'prayers' / 'prayers.json'

SECTION_HEADINGS = {
    'BIBLE TEACHINGS ON PRAYER', 'COMMON PRAYERS', 'PERSONAL PRAYERS',
    'PRAYERS FOR PROTECTION', 'DEVOTION TO THE BLESSED TRINITY',
    'DEOTION TO THE BLESSED TRINITY', 'DEVOTION TO ABBA FATHER',
    'PRAYERS TO THE HOLY SPIRIT', 'PRAYERS TO HOLY SPIRIT',
    'DEVOTION TO THE SACRED HEART OF JESUS', 'AT THE FEET OF JESUS IN THE EUCHARIST',
    'DEVOTION TO BLESSED VIRGIN MARY', 'CHAPLETS TO MOTHER MARY',
    'ROSARIES', 'CHAPLETS', 'DEVOTION TO ANGELS', 'PRAYERS TO HOLY ANGELS',
    'DEVOTION TO SAINTS', 'NOVENAS', 'THE HOLY MASS', 'THE LITANIES',
    'SPECIAL PRAYERS', 'THE SACRAMENT OF PENANCE', 'READ, REPEAT AND MEDITATE',
    'APPENDIX', 'SAINTS AND THEIR PATRONAGE', 'THE VINCENTIAN CONGREGATION IN INDIA',
    'A SHORT HISTORY', 'EAST-AFRICAN MISSION', 'VINCENTIAN PRAYER HOUSE',
    'POPULAR MISSIONS', 'HOW OFTEN SHOULD WE PRAY', 'HOW SHOULD WE PRAY',
    'THE FOUR PARTS OF PRAYER', 'THE LORD’S PRAYER',
}
SUBHEADINGS = {
    'INTENTIONS', 'REFLECTION', 'REFLECTION:', 'SCRIPTURE REFLECTION',
    'METHOD OF MAKING THE NOVENA', 'HOW TO PRAY THE ROSARY',
    'HOW TO PRAY THE NOVENA', 'INTRODUCTION PRAYER', 'CLOSING PRAYER',
    'LET US PRAY', 'LET US PRAY:', 'PRAYER', 'PRAYER:', 'CHRIST SPEAKS:',
    'JESUS SPEAKS', 'JESUS SPEAKS:', 'CHRIST SPEAKS', 'THE CONCLUDING PRAYER',
    'THE CONCLUDING PRAYER:', 'CONCLUDING PRAYER',
    'SIMON THE CYRENEAN HELPS JESUS CARRY HIS CROSS',
    'JESUS IS NAILED TO THE CROSS', 'JESUS IS TAKEN DOWN FROM THE CROSS',
}
TITLE_CASE_HEADINGS = {
    'The Creed Praises', 'The Forgiveness Prayer',
}
MYSTERY_RE = re.compile(r'^(?:THE\s+)?(?:(?:JOYFUL|LUMINOUS|SORROWFUL|GLORIOUS) MYSTERIES|(?:FIRST|SECOND|THIRD|FOURTH|FIFTH|SIXTH|SEVENTH|EIGHTH|NINTH|TENTH|ELEVENTH|TWELFTH) MYSTERY)$', re.I)
STATION_RE = re.compile(r'^(?:THE\s+)?[A-Z]+\s+ST[A-Z]+|^THE EMPTY TOMB', re.I)
DAY_RE = re.compile(r'^(?:DAY|FIRST DAY|SECOND DAY|THIRD DAY|FOURTH DAY|FIFTH DAY|SIXTH DAY|SEVENTH DAY|EIGHTH DAY|NINTH DAY)\s*\d*\b', re.I)


def is_section(line):
    key = ' '.join(line.upper().split())
    return key in SECTION_HEADINGS


def is_heading(line):
    s = ' '.join(line.split()).strip()
    if not s:
        return False
    if s in TITLE_CASE_HEADINGS:
        return True
    if s in SUBHEADINGS:
        return False
    if MYSTERY_RE.match(s) or STATION_RE.match(s) or DAY_RE.match(s):
        return False
    if is_section(s):
        return False
    letters = [c for c in s if c.isalpha()]
    if len(s) < 5 or len(s) > 92 or not letters:
        return False
    # Prayer headings in this book are set in capitals; ignore occasional uppercase labels.
    return sum(c.isupper() for c in letters) / len(letters) >= .78


def slug(value):
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '-', value).strip('-') or 'prayer'


def display_title(value):
    if not value.isupper():
        return value
    title = value.title()
    title = re.sub(r"([’'])S\b", lambda m: m.group(1) + 's', title)
    return title


def category_for(title, pdf_page):
    u = title.upper()
    if 'LITANY' in u or 'LITANIES' in u:
        return 'litanies'
    if 'WAY OF THE CROSS' in u or 151 <= pdf_page <= 157:
        return 'way-of-the-cross'
    if any(w in u for w in ('ROSARY', 'CHAPLET')) or 54 <= pdf_page <= 75:
        return 'rosary'
    if (30 <= pdf_page <= 53 or 111 <= pdf_page <= 112 or
            any(w in u for w in ('EUCHARIST', 'EUCHARISTIC', 'BLESSED SACRAMENT', 'SACRED HOST', 'COMMUNION'))):
        return 'eucharist'
    if pdf_page <= 14 or u in {"OUR FATHER", "HAIL MARY", "GLORY BE", "THE APOSTLE’S CREED", "THE APOSTLE'S CREED"}:
        return 'common'
    return 'other'


def clean_line(raw):
    s = raw.rstrip().replace('\u00a0', ' ')
    compact = ' '.join(s.split())
    if not compact:
        return ''
    if compact in {'Christ is All', 'VPH Prayer Book'}:
        return ''
    if re.fullmatch(r'\d+\s+(?:Christ is All|VPH Prayer Book)(?:\s+\d+)?', compact, re.I):
        return ''
    if re.fullmatch(r'(?:Christ is All|VPH Prayer Book)\s+\d+', compact, re.I):
        return ''
    if re.fullmatch(r'\d+', compact):
        return ''
    return s.strip()


def main():
    pdf = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PDF
    result = subprocess.run(['pdftotext', '-layout', str(pdf), '-'], check=True, capture_output=True, text=True)
    pages = result.stdout.split('\f')
    prayers = []
    active = None

    def new_record(title, page_no):
        kind = 'litany' if 'LITANY' in title.upper() else ('stations' if 'WAY OF THE CROSS' in title.upper() else 'prayer')
        return {
            'id': f'{slug(title)}-p{page_no}',
            'title': display_title(title),
            'category': category_for(title, page_no + 6),
            'type': kind,
            'sourcePage': page_no,
            'source': 'Christ Is All Prayer Book · Vincentian Ministries',
            'text': '',
        }

    # The PDF has six cover/contents pages; the first numbered prayer page is PDF page 7.
    for pdf_page, page in enumerate(pages[6:172], start=7):
        printed_page = pdf_page - 6
        for raw in page.splitlines():
            line = clean_line(raw)
            if not line:
                if active and active['text'] and not active['text'].endswith('\n\n'):
                    active['text'] += '\n'
                continue
            normalized = ' '.join(line.split())
            upper = normalized.upper()
            if is_section(normalized):
                active = None
                continue
            if normalized in TITLE_CASE_HEADINGS or is_heading(normalized):
                title = display_title(normalized)
                active = new_record(title, printed_page)
                prayers.append(active)
                continue
            if active:
                active['text'] += line + '\n'

    for item in prayers:
        text = item['text'].strip()
        text = re.sub(r'(?<=\w)-\n(?=[a-z])', '', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        # Keep speaker turns explicit and easy to read on narrow screens.
        text = re.sub(r'(?m)^\s*L:\s*', 'Leader: ', text)
        text = re.sub(r'(?m)^\s*R:\s*', 'All: ', text)
        if item['category'] == 'way-of-the-cross':
            text = text.replace('STATTION', 'STATION').replace('STATIOON', 'STATION')
            text = text.replace('THE FIRTH STATION:', 'THE FIFTH STATION:')
            text = text.replace('THE ELVENTH STATION:', 'THE ELEVENTH STATION:')
        if item['type'] == 'litany':
            # Poppler keeps the two printed columns separated by a wide gap.
            # Store them as an invocation/response pair for narrow screens.
            text = re.sub(r'(?m)^(.+?)\s{3,}(.+)$', r'\1 — \2', text)
            text = text.replace('Blessed Trinity, hear us, Adorable Unity, graciously hear us.', 'Blessed Trinity — hear us; Adorable Unity — graciously hear us.')
            item['format'] = 'call-and-response'
        item['text'] = text

    prayers = [p for p in prayers if p['text'].strip()]
    seen_ids = {}
    for item in prayers:
        base = item['id']
        seen_ids[base] = seen_ids.get(base, 0) + 1
        if seen_ids[base] > 1:
            item['id'] = f"{base}-{seen_ids[base]}"
    bundle = {
        'title': 'Christ Is All Prayer Book',
        'publisher': 'Vincentian Ministries',
        'publisherSites': ['https://www.vphnairobi.org', 'https://www.vrcthika.org'],
        'categories': [
            {'id': 'rosary', 'title': 'Holy Rosary', 'subtitle': 'Meditate on the mysteries of Christ with Mary.', 'image': 'assets/images/prayer-rosary.jpg', 'icon': 'crown', 'theme': 'blue'},
            {'id': 'common', 'title': 'Common Prayers', 'subtitle': 'Essential Catholic prayers for everyday life.', 'image': 'assets/images/prayer-common.jpg', 'icon': 'session', 'theme': 'purple'},
            {'id': 'eucharist', 'title': 'Jesus in the Eucharist', 'subtitle': 'Prayers for adoration and Holy Communion.', 'image': 'assets/images/prayer-eucharist.jpg', 'icon': 'candle', 'theme': 'amber'},
            {'id': 'litanies', 'title': 'Litanies', 'subtitle': 'Pray each invocation and response in order.', 'image': 'assets/images/prayer-other.jpg', 'icon': 'dove', 'theme': 'purple'},
            {'id': 'way-of-the-cross', 'title': 'The Way of the Cross', 'subtitle': 'Pray and reflect on Christ’s Passion.', 'image': 'assets/images/prayer-cross.jpg', 'icon': 'cross', 'theme': 'maroon'},
            {'id': 'other', 'title': 'Other Prayers', 'subtitle': 'Explore more prayers, devotions, and novenas.', 'image': 'assets/images/prayer-other.jpg', 'icon': 'praying', 'theme': 'green'},
        ],
        'prayers': prayers,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Imported {len(prayers)} prayer sections from {pdf.name} to {OUT.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
