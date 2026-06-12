const CACHE = 'gestionale-v1';
const STATIC = [
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/manifest.json',
];

self.addEventListener('install', e => {
  // Non bloccare l'installazione se un asset non carica
  e.waitUntil(
    caches.open(CACHE)
      .then(c => Promise.allSettled(STATIC.map(url =>
        c.add(url).catch(() => {})
      )))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const { request } = e;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);

  // Cache-first per asset statici
  if (url.pathname.startsWith('/static/')) {
    e.respondWith(
      caches.match(request).then(cached => cached || fetch(request).then(res => {
        if (res.ok) {
          const clone = res.clone();
          caches.open(CACHE).then(c => c.put(request, clone));
        }
        return res;
      }).catch(() => cached))
    );
    return;
  }

  // Salta chiamate API e WebSocket
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/ws')) return;

  // Network-first per le pagine HTML
  e.respondWith(
    fetch(request)
      .then(res => {
        if (res.ok && (request.headers.get('accept') || '').includes('text/html')) {
          const clone = res.clone();
          caches.open(CACHE).then(c => c.put(request, clone));
        }
        return res;
      })
      .catch(() => caches.match(request).then(cached => cached || caches.match('/')))
  );
});
