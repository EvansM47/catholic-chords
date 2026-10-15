#!/usr/bin/env node
/**
 * Formatted importer: preserves BOLD / ITALIC and line spacing from the PDF.
 * Uses `pdftohtml -xml` (poppler) which emits <b> and <i> tags per line.
 * Output: assets/hymns/hymns.json + assets/hymns/text/*.txt with markdown markers:
 *   **bold**, *italic*, ***bold+italic***
 */
const fs = require('fs');
const path = require('path');
const cp = require('child_process');

const pdfPath = process.argv[2] || '/home/evans/Downloads/All_glory_Book.pdf';
const outRoot = path.join(__dirname, '..', 'assets', 'hymns');
const textDir = path.join(outRoot, 'text');
const xmlBase = '/tmp/choir-hymns-formatted';
const xmlFile = xmlBase + '.xml';

console.log('Converting PDF to XML (preserves bold/italic)...');
cp.execFileSync('pdftohtml', ['-xml', '-i', pdfPath, xmlBase]);
let xml = fs.readFileSync(xmlFile, 'utf8');

// Each <text ...>...</text> is one visual line. Extract with formatting.
const textRe = /<text([^>]*)>([\s\S]*?)<\/text>/g;
const pages = [];
// Split by page to keep reading order per page
const pageRe = /<page[^>]*number="(\d+)"[^>]*>([\s\S]*?)<\/page>/g;
let pm;
while ((pm = pageRe.exec(xml)) !== null) {
  const pageNum = Number(pm[1]);
  const body = pm[2];
  const items = [];
  let tm;
  const inner = new RegExp(textRe.source, 'g');
  while ((tm = inner.exec(body)) !== null) {
    const attrs = tm[1];
    const html = tm[2];
    const top = Number(/top="(\d+)"/.exec(attrs)?.[1] ?? 0);
    const left = Number(/left="(\d+)"/.exec(attrs)?.[1] ?? 0);
    const hasB = /<b[\s>]/.test(html);
    const hasI = /<i[\s>]/.test(html);
    // strip all tags to get plain text, decode basic entities
    let plain = html.replace(/<[^>]+>/g, '').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&#160;|&nbsp;/g, ' ').trim();
    // skip page footer numbers handled later; keep empties as breaks
    items.push({ top, left, hasB, hasI, plain, html });
  }
  pages.push({ pageNum, items });
}

// Reconstruct ordered lines with markdown
function mdLine(it) {
  if (!it.plain) return ''; // blank = stanza break
  let t = it.plain.replace(/[ \t]+/g, ' ');
  if (it.hasB && it.hasI) return `***${t}***`;
  if (it.hasB) return `**${t}**`;
  if (it.hasI) return `*${t}*`;
  return t;
}

const ignored = /^(ALL GLORY TO JESUS|HYMNAL BOOK|Y AL OO|PRAISE SONGS|WORSHP SONGS|WORSHIP SONGS|ENTRANCE HYMNS|RESPONSORIAL PSALM|GOSPEL ACCLAMATIONS?|OFFERTORY|OFFERTORY SONGS|COMMUNION SONGS|THANKSGIVING|MOTHER MARY|CHRISTMAS|EASTER|LENT|HOLY WEEK|GENERAL|BIOGRAPHICALNOTE)$/i;
const pageOnly = /^\s*\d{1,3}\s*$/;

function stripMd(s) { return s.replace(/\*\*\*(.+?)\*\*\*/g, '$1').replace(/\*\*(.+?)\*\*/g, '$1').replace(/\*(.+?)\*/g, '$1').trim(); }

function heading(lineMd) {
  const s = stripMd(lineMd).replace(/\s+/g, ' ').trim();
  let m = s.match(/^(?:l\s*)?(\d{1,3})\s*\.\s*(?:([A-D])\s+)?(.+?)\s*$/i);
  if (!m) m = s.match(/^(?:l\s*)?(\d{1,3})\s+([A-D])\s*\.\s*(.+?)\s*$/i);
  if (!m) return null;
  const number = m[1];
  let title = (m[3] || '').trim();
  let variant = m[2] ? m[2].toUpperCase() : '';
  const pv = title.match(/^\(([A-D])\)\s*/i);
  if (pv) { variant = pv[1].toUpperCase(); title = title.replace(/^\([A-D]\)\s*/i, '').trim(); }
  if (!title) return null;
  const letters = title.replace(/[^A-Za-zÀ-ÖØ-öø-ÿ]/g, '');
  const upper = (title.match(/[A-ZÀ-Ý]/g) || []).length;
  const lower = (title.match(/[a-zà-ÿ]/g) || []).length;
  const looksHeading = Number(number) >= 100 || upper >= Math.max(2, lower * 1.6) || (number === '3' && /^EE TATA/i.test(title));
  if (!looksHeading) return null;
  return { number, variant, title };
}

// Build global ordered line stream: for each page, left-col then right-col
const stream = []; // {page, md, plain}
for (const { pageNum, items } of pages) {
  // drop footer (top > 820) and top running header (top < 50 and all-caps short)
  const filtered = items.filter(it => {
    if (it.top > 820) return false; // footer page number
    if (!it.plain) return true; // keep breaks
    if (pageOnly.test(it.plain)) return false;
    if (ignored.test(it.plain)) return false;
    if (/^\$OO|^VINCENTIAN MINISTRIES$/i.test(it.plain)) return false;
    return true;
  });
  const leftCol = filtered.filter(t => t.left < 200).sort((a, b) => a.top - b.top || a.left - b.left);
  const rightCol = filtered.filter(t => t.left >= 200).sort((a, b) => a.top - b.top || a.left - b.left);
  // merge bullet "•" with following text on same row (top within 4px)
  function mergeBullets(col) {
    const out = [];
    for (let i = 0; i < col.length; i++) {
      const cur = col[i];
      if (cur.plain === '•' || cur.plain === '·') {
        const nxt = col[i + 1];
        if (nxt && Math.abs(nxt.top - cur.top) < 6) {
          out.push({ ...nxt, plain: '• ' + nxt.plain, html: nxt.html });
          i++;
          continue;
        }
      }
      out.push(cur);
    }
    return out;
  }
  // merge fragments on the same visual row (same top) within a column
  function mergeRows(col) {
    const rows = [];
    for (const it of col) {
      if (!it.plain) { rows.push({ page: pageNum, md: '', plain: '' }); continue; }
      const last = rows[rows.length - 1];
      if (last && last.top !== undefined && Math.abs(last.top - it.top) < 5 && last.page === pageNum) {
        last.plain += ' ' + it.plain;
        // if either fragment bold, keep bold
        last.hasB = last.hasB || it.hasB;
        last.hasI = last.hasI || it.hasI;
        last.md = mdLine({ plain: last.plain, hasB: last.hasB, hasI: last.hasI });
      } else {
        rows.push({ page: pageNum, top: it.top, left: it.left, hasB: it.hasB, hasI: it.hasI, plain: it.plain, md: mdLine(it) });
      }
    }
    return rows;
  }
  for (const row of mergeRows(mergeBullets(leftCol))) stream.push(row);
  for (const row of mergeRows(mergeBullets(rightCol))) stream.push(row);
}

// Find hymn headings in stream
const candidates = [];
stream.forEach((row, i) => {
  if (!row.md) return;
  const h = heading(row.md);
  if (h) candidates.push({ ...h, idx: i, page: row.page, md: row.md });
});

const start = candidates.findIndex(c => c.number === '1');
let selected = candidates.slice(start >= 0 ? start : 0);
// stop after hymn 532
const lastIdx = selected.findIndex((h, i) => i > 0 && h.number === '532');
if (lastIdx >= 0) selected = selected.slice(0, lastIdx + 1);

console.log(`Found ${selected.length} hymn headings (stream lines: ${stream.length})`);

fs.rmSync(textDir, { recursive: true, force: true });
fs.mkdirSync(textDir, { recursive: true });

const slug = s => s.toLowerCase().normalize('NFKD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 80);
const pad = s => String(s).padStart(4, '0');

const output = [];
const reviews = [];
const seen = new Map();
for (let i = 0; i < selected.length; i++) {
  const h = selected[i];
  const nextIdx = i + 1 < selected.length ? selected[i + 1].idx : stream.length;
  // collect body rows between headings
  const rows = stream.slice(h.idx + 1, nextIdx);
  // build body preserving stanza breaks: empty md => blank line, collapse 3+ blanks to 2
  const lines = [];
  for (const r of rows) {
    if (!r.md) { lines.push(''); continue; }
    const p = stripMd(r.md);
    if (!p || pageOnly.test(p) || ignored.test(p)) continue;
    if (/^\$OO|^VINCENTIAN MINISTRIES$/i.test(p)) continue;
    lines.push(r.md.trim());
  }
  let body = lines.join('\n').replace(/\n{3,}/g, '\n\n').trim();
  const id = h.variant ? `${h.number}${h.variant}` : h.number;
  const title = h.title;
  const sourceFile = `${pad(h.number)}${h.variant || ''}_${slug(title)}.txt`;
  const text = [`HYMN_NUMBER: ${id}`, `TITLE: ${title}`, '', 'VERSE 1:', body || '[No text extracted — human review required.]', ''].join('\n');
  fs.writeFileSync(path.join(textDir, sourceFile), text + '\n', 'utf8');
  const boldCount = (body.match(/\*\*/g) || []).length / 2;
  const item = {
    id, hymnNumber: id, title,
    verses: [{ number: 1, text: body }],
    chorus: null, lyrics: body,
    sourceFile: `assets/hymns/text/${sourceFile}`,
    sourcePage: h.page,
    language: /[à-ÿ]|\b(na|kwa|mungu|bwana|yesu|mama|roho)\b/i.test(body) ? 'Mixed / source language' : 'English',
    sourceBook: 'All Glory to Jesus (supplied PDF)',
    needsReview: !body,
    formatted: true, boldLines: Math.round(boldCount),
  };
  output.push(item);
  seen.set(id, (seen.get(id) || 0) + 1);
  if (!body) reviews.push(`${id} — page ${h.page}: no body text extracted.`);
  if (body.length < 20) reviews.push(`${id} — page ${h.page}: short extraction (${body.length} chars).`);
}

const duplicates = [...seen.entries()].filter(([, c]) => c > 1).map(([id, c]) => `${id} (${c}x)`);
const nums = [...new Set(output.map(h => Number(String(h.hymnNumber).replace(/[A-D]$/, ''))))].filter(Number.isFinite).sort((a, b) => a - b);
const missing = [];
for (let n = 1; n <= 532; n++) if (!nums.includes(n)) missing.push(String(n));
const withBold = output.filter(h => h.boldLines > 0).length;
const review = ['# Hymn import review (formatted)', '', `Source: '${path.basename(pdfPath)}' via pdftohtml -xml (preserves <b>/<i>).`, '', `- Total hymn entries: **${output.length}**`, `- Entries with bold lines: **${withBold}**`, `- Duplicates: ${duplicates.length ? duplicates.join(', ') : 'None'}`, `- Missing 1–532: ${missing.length ? missing.join(', ') : 'None'}`, '', '## Notes', '', reviews.length ? reviews.map(x => '- ' + x).join('\n') : '- No empty entries. Bold = **text**, bold+italic = ***text***, italic = *text*. Blank lines = stanza breaks.', ''].join('\n');
fs.writeFileSync(path.join(__dirname, '..', 'docs', 'HYMN_IMPORT_REVIEW.md'), review, 'utf8');
fs.writeFileSync(path.join(outRoot, 'hymns.json'), JSON.stringify(output, null, 2) + '\n', 'utf8');
console.log(`Wrote ${output.length} hymns, ${withBold} with bold. Missing: ${missing.length}. Reviews: ${reviews.length}`);
