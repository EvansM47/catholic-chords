const fs = require('fs');
const path = require('path');

const root = path.join(__dirname, '..');
const input = path.resolve(process.argv[2] || path.join(root, 'assets/sauti/sauti_songs.json'));
const hymnPath = path.join(root, 'assets/hymns/hymns.json');
const catalogPath = path.join(root, 'assets/sauti/catalog.json');
const siteName = 'Sauti za Kuimba';
const sourceTaxonomy = {
  'Alhamisi Kuu': { seasonIds: ['HOLY_THURSDAY'] },
  'Anthem': { categoryIds: ['ANTHEMS'] },
  'Bikira Maria': { categoryIds: ['MARIAN_SONGS'] },
  'Church': { categoryIds: ['CHURCH'] },
  'Ekaristia (Eucharist)': { categoryIds: ['EUCHARIST_COMMUNION'] },
  'Entrance / Mwanzo': { categoryIds: ['ENTRANCE'] },
  'Epiphany': { seasonIds: ['EPIPHANY'] },
  'Faith': { categoryIds: ['FAITH'] },
  'Familia': { categoryIds: ['FAMILY'] },
  'General': { categoryIds: ['GENERAL'] },
  'Harusi': { categoryIds: ['MARRIAGE_WEDDING'] },
  'Injili na Miito (Gospel)': { categoryIds: ['GOSPEL', 'VOCATION'] },
  'Jumapili ya Matawi (Palm Sunday)': { seasonIds: ['PALM_SUNDAY'] },
  'Kristu Mfalme (Christ the King)': { seasonIds: ['CHRIST_THE_KING'] },
  'Kupaa kwa Bwana (Ascension)': { seasonIds: ['ASCENSION'] },
  'Kwaresma na Toba (Lent & Repentance)': { categoryIds: ['REPENTANCE'], seasonIds: ['LENT'] },
  'Love': { categoryIds: ['LOVE_OF_GOD'] },
  'Mafundisho ya Yesu': { categoryIds: ['TEACHINGS_OF_JESUS'] },
  'Majilio (Advent)': { seasonIds: ['ADVENT'] },
  'Mazishi': { categoryIds: ['FUNERAL'] },
  'Misa (Sung Mass)': { categoryIds: ['SUNG_MASS'] },
  'Moyo wa Yesu': { categoryIds: ['SACRED_HEART'], seasonIds: ['SACRED_HEART'] },
  'Noeli (Christmas Carols)': { seasonIds: ['CHRISTMAS'] },
  'Offertory/Sadaka': { categoryIds: ['OFFERTORY'] },
  'Pasaka (Easter)': { seasonIds: ['EASTER'] },
  'Peace': { categoryIds: ['PEACE'] },
  'Recession': { categoryIds: ['RECESSION'] },
  'Roho Mtakatifu (Pentecoste)': { categoryIds: ['HOLY_SPIRIT'], seasonIds: ['PENTECOST'] },
  'Sign of Peace/Kutakiana Amani': { categoryIds: ['PEACE'] },
  'Tafakari': { categoryIds: ['REFLECTION'] },
  'TBA': { categoryIds: ['GENERAL'] },
  'Thanksgiving / Shukrani': { categoryIds: ['THANKSGIVING'] },
  'Ubatizo': { categoryIds: ['BAPTISM'] },
  'Utatu Mtakatifu (Holy Trinity)': { seasonIds: ['HOLY_TRINITY'] },
  'Utume wa Uimbaji': { categoryIds: ['CHOIR_MINISTRY'] },
  'Watakatifu': { categoryIds: ['SAINTS'] },
  'Wito': { categoryIds: ['VOCATION'] },
  'Zaburi': { categoryIds: ['PSALMS'] }
};

function normalize(value) {
  return String(value || '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '')
    .toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
}

function lyricTokens(value) {
  return normalize(String(value || '').replace(/\[[^\]]*\]/g, ' '))
    .split(/\s+/).filter(Boolean);
}

function similarity(left, right) {
  const a = lyricTokens(left);
  const b = lyricTokens(right);
  const aSet = new Set(a);
  const bSet = new Set(b);
  const union = new Set([...aSet, ...bSet]);
  let overlap = 0;
  for (const word of aSet) if (bSet.has(word)) overlap++;
  const jaccard = union.size ? overlap / union.size : 0;
  if (!a.length || !b.length) return { jaccard, sequence: 0, words: union.size };

  let previous = new Uint16Array(b.length + 1);
  for (const word of a) {
    const current = new Uint16Array(b.length + 1);
    for (let j = 1; j <= b.length; j++) {
      current[j] = word === b[j - 1] ? previous[j - 1] + 1 : Math.max(previous[j], current[j - 1]);
    }
    previous = current;
  }
  return { jaccard, sequence: (2 * previous[b.length]) / (a.length + b.length), words: union.size };
}

function sourceUrl(song) {
  try {
    const candidate = new URL(song.source_url || song.url || '');
    if (candidate.protocol === 'https:' && candidate.hostname === 'sauti.gafkosoft.com') return candidate.href;
  } catch {}
  if (song.id && song.slug) return `https://sauti.gafkosoft.com/songs/${encodeURIComponent(song.id)}/${encodeURIComponent(song.slug)}`;
  return 'https://sauti.gafkosoft.com/songs/';
}

const songs = JSON.parse(fs.readFileSync(input, 'utf8'));
const hymns = JSON.parse(fs.readFileSync(hymnPath, 'utf8'));
const catalog = songs.map(song => {
  const category = String(song.category || '');
  const taxonomy = sourceTaxonomy[category] || {};
  const categoryIds = taxonomy.categoryIds || [];
  return {
    id: String(song.id || ''),
    title: String(song.title || ''),
    slug: String(song.slug || ''),
    composer: String(song.composer || ''),
    choir: String(song.choir || ''),
    album: String(song.album || ''),
    category,
    categoryIds,
    categoryId: categoryIds[0] || '',
    seasonIds: taxonomy.seasonIds || [],
    source_url: sourceUrl(song)
  };
});

const byTitle = new Map();
for (const song of songs) {
  const key = normalize(song.title);
  if (!key) continue;
  if (!byTitle.has(key)) byTitle.set(key, []);
  byTitle.get(key).push(song);
}

let matched = 0;
for (const hymn of hymns) {
  const candidates = byTitle.get(normalize(hymn.title)) || [];
  const ranked = candidates.map(song => ({ song, ...similarity(hymn.lyrics, song.lyrics) }))
    .sort((a, b) => (b.jaccard + b.sequence) - (a.jaccard + a.sequence));
  const best = ranked[0];
  if (!best || best.words < 8 || (best.jaccard < 0.6 && best.sequence < 0.75)) {
    if (hymn.source2 && hymn.source2.name === siteName) delete hymn.source2;
    continue;
  }
  const song = best.song;
  hymn.source2 = {
    name: siteName,
    id: String(song.id || ''),
    title: String(song.title || hymn.title),
    url: sourceUrl(song),
    composer: String(song.composer || ''),
    choir: String(song.choir || ''),
    category: String(song.category || ''),
    match: 'title-and-lyrics'
  };
  matched++;
}

fs.mkdirSync(path.dirname(catalogPath), { recursive: true });
fs.writeFileSync(catalogPath, JSON.stringify(catalog, null, 2) + '\n');
fs.writeFileSync(hymnPath, JSON.stringify(hymns, null, 2) + '\n');
console.log(`Prepared ${catalog.length} Sauti listings and added Source 2 links to ${matched} matching hymns.`);
console.log('The app catalog contains titles, credits, categories, and source links only; lyrics stay on the original site.');
