/* PGR Analytics — Service Worker
   Strategy: Cache-first for static assets only.
   API routes are NEVER cached — live data must always be fresh.
*/
const SW_VERSION = "pgr-v1";
const STATIC_CACHE = `${SW_VERSION}-static`;

// Static assets to pre-cache on install
const PRECACHE_URLS = [
  "/",
  "/manifest.json",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/icons/icon-maskable-192.png",
  "/favicon.ico",
];

// ── Install: pre-cache static shell ──────────────────────────
self.addEventListener("install", (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => cache.addAll(PRECACHE_URLS))
  );
});

// ── Activate: remove old caches ───────────────────────────────
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k !== STATIC_CACHE)
          .map((k) => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

// ── Fetch: network-only for API, cache-first for static ──────
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // Never cache API calls — always fetch live
  if (url.pathname.startsWith("/api/")) {
    event.respondWith(fetch(event.request));
    return;
  }

  // For navigation requests (HTML pages): network first, fall back to cache
  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request)
        .then((res) => {
          // Update the cache with the fresh response
          const clone = res.clone();
          caches.open(STATIC_CACHE).then((c) => c.put(event.request, clone));
          return res;
        })
        .catch(() => caches.match("/"))
    );
    return;
  }

  // Static assets: cache-first
  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) return cached;
      return fetch(event.request).then((res) => {
        if (res && res.status === 200) {
          const clone = res.clone();
          caches.open(STATIC_CACHE).then((c) => c.put(event.request, clone));
        }
        return res;
      });
    })
  );
});
