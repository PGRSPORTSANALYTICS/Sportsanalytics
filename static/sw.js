/* PGR Analytics — Service Worker
   Strategy: Cache-first for static assets only.
   API routes use network-first with stale fallback for offline resilience.
*/
const SW_VERSION = "pgr-v5";
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

// ── Fetch: network-first for API (stale fallback), cache-first for static ──
self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  if (request.method !== "GET") return;

  // API routes: network-first with stale fallback for offline resilience
  if (url.pathname.startsWith("/api/")) {
    event.respondWith(networkFirstWithFallback(request));
    return;
  }

  // Navigation (HTML pages): network-first, fall back to cache
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((res) => {
          const clone = res.clone();
          caches.open(STATIC_CACHE).then((c) => c.put(request, clone));
          return res;
        })
        .catch(() => caches.match("/"))
    );
    return;
  }

  // Static assets: cache-first
  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached;
      return fetch(request).then((res) => {
        if (res && res.status === 200) {
          const clone = res.clone();
          caches.open(STATIC_CACHE).then((c) => c.put(request, clone));
        }
        return res;
      });
    })
  );
});

/* ── Push Notifications ─────────────────────────────────────── */
self.addEventListener("push", (event) => {
  let data = { title: "PGR Analytics", body: "New edge detected!", url: "/" };
  try { data = event.data.json(); } catch (_) {}

  event.waitUntil(
    self.registration.showNotification(data.title, {
      body:     data.body,
      icon:     "/static/icons/icon-192.png",
      badge:    "/static/icons/icon-192.png",
      data:     { url: data.url },
      vibrate:  [100, 50, 100],
      tag:      "pgr-pick",
      renotify: true,
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = event.notification.data?.url || "/";
  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((ws) => {
      for (const w of ws) {
        if (w.url.includes(self.location.origin)) {
          w.focus();
          w.navigate(target);
          return;
        }
      }
      return clients.openWindow(target);
    })
  );
});

async function networkFirstWithFallback(request) {
  const cache = await caches.open(STATIC_CACHE);
  try {
    const response = await fetch(request);
    if (response.ok) {
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await cache.match(request);
    if (cached) {
      const headers = new Headers(cached.headers);
      headers.set("X-SW-Offline", "1");
      const body = await cached.arrayBuffer();
      return new Response(body, { status: cached.status, statusText: cached.statusText, headers });
    }
    return new Response(JSON.stringify({ error: "offline", stale: true }), {
      status: 503,
      headers: { "Content-Type": "application/json", "X-SW-Offline": "1" },
    });
  }
}
