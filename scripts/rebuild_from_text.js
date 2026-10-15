#!/usr/bin/env node
/**
 * Rebuild hymns.json (+ hymns.db via seed script) from edited text files.
 * Edit: assets/hymns/text/*.txt  (keep HYMN_NUMBER: and TITLE: headers)
 *   **bold**, ***bold+italic***, *italic*, blank line = stanza break
 * Then run: node scripts/rebuild_from_text.js && python3 scripts/seed_sqlite.py
 */
const fs = require('fs');
const path = require('path');
const root = path.join(__dirname, '..');
const textDir = path.join(root, 'assets', 'hymns', 'text');
const jsonPath = path.join(root, 'assets', 'hymns', 'hymns.json');

const old = JSON.parse(fs.readFileSync(jsonPath, 'utf8'));
const meta = new Map(old.map(h => [h.sourceFile, h]));

const files = fs.readdirSync(textDir).filter(f => f.endsWith('.txt')).sort();
const out = [];
for (const f of files) {
  const raw = fs.readFileSync(path.join(textDir, f), 'utf8');
  const num = (/^HYMN_NUMBER:\s*(.+?)\s*$/m.exec(raw)?.[1] || '').trim();
  const title = (/^TITLE:\s*(.+?)\s*$/m.exec(raw)?.[1] || '').trim();
  // Body = everything after the first blank line following VERSE header (or after headers)
  let body = raw.split(/\r?\n/).filter((_, i, a) => i >= 0);
  // drop header lines
  const idx = body.findIndex(l => /^VERSE\s+\d+\s*:/i.test(l));
  body = (idx >= 0 ? body.slice(idx + 1) : body.slice(2)).join('\n').replace(/^\n+/, '').replace(/\s+$/, '');
  body = body.replace(/\n{3,}/g, '\n\n');
  const key = `assets/hymns/text/${f}`;
  const prev = meta.get(key) || {};
  const boldCount = (body.match(/\*\*/g) || []).length / 2;
  out.push({
    id: num, hymnNumber: num, title,
    verses: [{ number: 1, text: body }],
    chorus: null, lyrics: body,
    sourceFile: key,
    sourcePage: prev.sourcePage ?? null,
    language: prev.language ?? '',
    sourceBook: prev.sourceBook ?? 'All Glory to Jesus (supplied PDF)',
    needsReview: !body,
    formatted: true, boldLines: Math.round(boldCount),
  });
}
fs.writeFileSync(jsonPath, JSON.stringify(out, null, 2) + '\n', 'utf8');
console.log(`Rebuilt ${out.length} hymns from text/ into hymns.json`);
