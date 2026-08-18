/* Translation Studio — service worker (installable PWA).
   Strategy:
   - Never touch /api/*  → always go to the network (translations/auth must be live).
   - Navigations (HTML)  → network-first, fall back to the cached app shell offline.
   - Static assets       → cache-first (hashed filenames make this safe).
   Bump CACHE to invalidate old caches on the next deploy. */
const CACHE = 'ts-cache-v1';
const SHELL = ['/translation', '/manifest.webmanifest', '/icons/icon-192.png', '/icons/icon-512.png'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).catch(() => {}));
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;      // third-party (fonts CDN) → default
  if (url.pathname.startsWith('/api/')) return;          // live data — never cache

  // HTML navigations: network-first, cache fallback (offline).
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(request, copy)).catch(() => {});
          return res;
        })
        .catch(() => caches.match(request).then((r) => r || caches.match('/translation')))
    );
    return;
  }

  // Static assets: cache-first, then network (and cache it).
  event.respondWith(
    caches.match(request).then(
      (cached) =>
        cached ||
        fetch(request).then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(request, copy)).catch(() => {});
          return res;
        }).catch(() => cached)
    )
  );
});
