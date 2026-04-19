/* PGR Analytics — Service Worker UNINSTALLER
   This SW immediately unregisters itself and reloads all clients.
   Purpose: remove all stale SW caches from previous versions.
*/
self.addEventListener('install', () => {
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.map(k => caches.delete(k))))
      .then(() => self.registration.unregister())
      .then(() => self.clients.matchAll({ type: 'window', includeUncontrolled: true }))
      .then(clients => {
        clients.forEach(c => c.navigate(c.url));
      })
  );
});
