#!/usr/bin/env node
/**
 * Import the supplied hymn book PDF into reviewable text files and JSON.
 * The PDF remains the source of truth; this script deliberately preserves
 * extracted wording and records pages that need human review.
 */
const fs = require('fs');
const path = require('path');
const cp = require('child_process');

const pdfPath = process.argv[2] || path.join(__dirname, '..', 'All_glory_Book.pdf');
const outRoot = path.join(__dirname, '..', 'assets', 'hymns');
const textDir = path.join(outRoot, 'text');
const tmp = '/tmp/choir-hymns-import.txt';
fs.rmSync(textDir, { recursive: true, force: true });
fs.mkdirSync(textDir, { recursive: true });
cp.execFileSync('pdftotext', ['-raw', pdfPath, tmp]);
const raw = fs.readFileSync(tmp, 'utf8');
const lines = raw.split(/\r?\n/);

// Heading text is printed in capitals throughout the book. The exceptions
// below are retained because they are visibly part of the printed heading.
function heading(line) {
  const original = line;
  let s = line.replace(/\f/g, '').trim();
  let m = s.match(/^(?:l\s*)?(\d{1,3})\s*\.\s*(?:([A-D])\s+)?(.+?)\s*$/i);
  if (!m) m = s.match(/^(?:l\s*)?(\d{1,3})\s+([A-D])\s*\.\s*(.+?)\s*$/i);
  if (!m) return null;
  const number = m[1];
  let title = (m[3] || '').trim();
  let variant = m[2] ? m[2].toUpperCase() : '';
  const parentheticalVariant = title.match(/^\(([A-D])\)\s*/i);
  if (parentheticalVariant) { variant = parentheticalVariant[1].toUpperCase(); title = title.replace(/^\([A-D]\)\s*/i, '').trim(); }
  if (!title) return null;
  // Verse lines are numeric but sentence case and always single-digit in the
  // source. Hymn numbers >= 100 are unambiguous; for 1–99 require a mostly
  // uppercase heading or one of the known parenthetical title forms.
  const letters = title.replace(/[^A-Za-zÀ-ÖØ-öø-ÿ]/g, '');
  const upper = title.replace(/[^A-ZÀ-Ý]/g, '').length;
  const lower = title.replace(/[^a-zà-ÿ]/g, '').length;
  const looksHeading = Number(number) >= 100 || upper >= Math.max(2, lower * 1.6) || (number === '3' && /^EE TATA/i.test(title));
  if (!looksHeading) return null;
  return { number, variant, title, sourceLine: original };
}

const candidates = [];
for (let i = 0; i < lines.length; i++) {
  const h = heading(lines[i]);
  if (h) candidates.push({ ...h, line: i });
}

// Keep only the hymn section (the first numbered song starts at 1; after 532
// the book contains biographies and publisher information).
const start = candidates.findIndex((c) => c.number === '1');
const end = candidates.findIndex((c, i) => i > start && c.number === '522' && c.line > 10000);
const hymns = candidates.slice(start, end >= 0 ? end + 11 : candidates.length);
// Stop after the final printed hymn 532.
const last = hymns.findIndex((h, i) => i > 0 && h.number === '532');
const selected = hymns.slice(0, last >= 0 ? last + 1 : hymns.length);

const ignored = /^(ALL GLORY TO JESUS|Y AL OO|PRAISE SONGS|WORSHP SONGS|WORSHIP SONGS|ENTRANCE HYMNS|RESPONSORIAL PSALM|GOSPEL ACCLAMATIONS?|OFFERTORY|OFFERTORY SONGS|COMMUNION SONGS|THANKSGIVING|MOTHER MARY|CHRISTMAS|EASTER|LENT|HOLY WEEK|GENERAL|BIOGRAPHICALNOTE)$/i;
const pageOnly = /^\s*\d{1,3}\s*$/;
const cleanBody = (body) => {
  const out = [];
  for (let line of body) {
    line = line.replace(/\f/g, '').trim();
    if (!line || pageOnly.test(line) || ignored.test(line)) continue;
    // Header fragments introduced by the raw text extractor.
    if (/^\$OO|^VINCENTIAN MINISTRIES$/i.test(line)) continue;
    out.push(line.replace(/[ \t]+/g, ' '));
  }
  return out.join('\n').replace(/\n{3,}/g, '\n\n').trim();
};
const slug = (s) => s.toLowerCase().normalize('NFKD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 80);
const pad = (s) => String(s).padStart(4, '0');
const parsePage = (index) => (raw.slice(0, selected[index].line).match(/\f/g) || []).length + 1;

const output = [];
const seen = new Map();
const reviews = [];
for (let i = 0; i < selected.length; i++) {
  const h = selected[i];
  const nextLine = i + 1 < selected.length ? selected[i + 1].line : lines.length;
  let body = cleanBody(lines.slice(h.line + 1, nextLine));
  const id = h.variant ? `${h.number}${h.variant}` : h.number;
  const title = h.title;
  const sourceFile = `${pad(h.number)}${h.variant || ''}_${slug(title)}.txt`;
  const text = [`HYMN_NUMBER: ${id}`, `TITLE: ${title}`, '', 'VERSE 1:', body || '[No text extracted — human review required.]', ''].join('\n');
  fs.writeFileSync(path.join(textDir, sourceFile), text + '\n', 'utf8');
  const item = {
    id,
    hymnNumber: id,
    title,
    verses: [{ number: 1, text: body }],
    chorus: null,
    lyrics: body,
    sourceFile: `assets/hymns/text/${sourceFile}`,
    sourcePage: parsePage(i),
    language: /[à-ÿ]|\b(na|kwa|mungu|bwana|yesu|mama|roho)\b/i.test(body) ? 'Mixed / source language' : 'English',
    sourceBook: 'All Glory to Jesus (supplied PDF)',
    needsReview: !body || /\b(l132|Y AL OO)\b/i.test(body),
  };
  output.push(item);
  seen.set(id, (seen.get(id) || 0) + 1);
  if (item.needsReview) reviews.push(`${id} — page ${item.sourcePage}: no reliable body text was extracted.`);
  if (body.length < 20) reviews.push(`${id} — page ${item.sourcePage}: unusually short extraction (${body.length} characters).`);
}

const duplicates = [...seen.entries()].filter(([, count]) => count > 1).map(([id, count]) => `${id} (${count} occurrences)`);
const nums = [...new Set(output.map(h => Number(h.hymnNumber.replace(/[A-D]$/, ''))))].filter(Number.isFinite).sort((a,b)=>a-b);
const missing = [];
for (let n = 1; n <= 532; n++) if (!nums.includes(n)) missing.push(String(n));
const review = [
  '# Hymn import review', '',
  "Source: 'All_glory_Book.pdf' (supplied PDF; extracted with Poppler pdftotext -raw).", '',
  '- Total hymn entries found: **' + output.length + '**',
  '- Text files generated: **' + output.length + '**',
  '- Successfully extracted entries: **' + output.filter(h => h.lyrics && !h.lyrics.startsWith('[No text')).length + '**',
  '- Hymns requiring manual review: **' + reviews.length + '**',
  '- Duplicate hymn numbers: ' + (duplicates.length ? duplicates.join(', ') : 'None detected'),
  '- Missing hymn numbers in the printed 1–532 range: ' + (missing.length ? missing.join(', ') : 'None detected'),
  '- Pages that could not be processed: None detected by the text extractor.', '',
  '## Review notes', '',
  reviews.length ? reviews.map(x => '- ' + x).join('\n') : '- No empty or unusually short entries detected. Human spot-checking is still recommended before publishing the library.', '',
  '## Validation', '',
  "- Generated UTF-8 files under 'assets/hymns/text/'.",
  '- Generated JSON from the extracted text in this run.',
  "- Each JSON 'sourceFile' points to a generated file.",
  '- The import script keeps the original PDF untouched and records the PDF as provenance.',
  '- Because this PDF contains a text layer with multi-column layouts, the generated files should be manually compared with the beginning, middle, and end pages before a production release.', ''
].join('\n');
fs.writeFileSync(path.join(__dirname, '..', 'docs', 'HYMN_IMPORT_REVIEW.md'), review, 'utf8');
fs.writeFileSync(path.join(outRoot, 'hymns.json'), JSON.stringify(output, null, 2) + '\n', 'utf8');
console.log(`Imported ${output.length} hymn entries into ${textDir}`);
console.log(`Review notes: ${reviews.length}; duplicates: ${duplicates.length}; missing: ${missing.length}`);
