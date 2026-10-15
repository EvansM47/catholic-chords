/* Offline-first service worker for Hymns (Android PWA installable). */
const CACHE = 'choir-hymns-v43';
const CORE = [
  './',
  './index.html',
  './styles.css',
  './src/app.js',
  './assets/vendor/qrcode.js',
  './manifest.webmanifest',
  './assets/images/logo.png',
  './assets/images/vinventian-logo.png',
  './assets/images/holy-rosary.png',
  './assets/images/regina-caeli-catholic-church.png',
  './assets/images/prayer-common.jpg',
  './assets/images/prayer-eucharist.jpg',
  './assets/images/prayer-cross.jpg',
  './assets/images/prayer-other.jpg',
  './assets/icons/icon-192.png',
  './assets/icons/icon-512.png',
  './assets/hymns/hymns.json',
  './assets/hymns/table_of_contents.json',
  './assets/prayers/prayers.json',
];
self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(CORE)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim())
  );
});
self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || !url.origin.startsWith(self.location.origin)) return;
  e.respondWith(
    caches.match(e.request, { ignoreSearch: true }).then((hit) => {
      const net = fetch(e.request).then((res) => {
        if (res.ok) { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(e.request, copy)); }
        return res;
      }).catch(() => hit);
      return hit || net;
    })
  );
});
