const CACHE = 'nova-v2';
const URLS = ['/', '/index.html', '/standalone.html', '/api/chat'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(URLS)));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(clients.claim());
});

self.addEventListener('fetch', e => {
  e.respondWith(
    caches.match(e.request).then(r => r || fetch(e.request).catch(() => {
      // Offline fallback
      if(e.request.headers.get('Accept')?.includes('text/html')){
        return caches.match('/index.html');
      }
    }))
  );
});
