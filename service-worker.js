const CACHE_NAME = 'nova-shell-2026-08-16-tailscale-v1';
const SHELL_ASSETS = [
  '/assets/nova_app_icon.svg',
  '/assets/nova_companion/companion-api.js',
  '/assets/nova_companion/companion-app.js',
  '/assets/nova_companion/companion-composer.js',
  '/assets/nova_companion/companion-conversation.js',
  '/assets/nova_companion/companion-presence.js',
  '/assets/nova_companion/companion-senses.js',
  '/assets/nova_companion/companion-shell.css',
  '/assets/nova_companion/companion-spark.js',
  '/assets/nova_companion/companion-store.js',
  '/assets/nova_companion/companion-trust.js',
  '/assets/nova_foundation_ui.js',
  '/companion',
  '/manifest.webmanifest',
  '/offline.html'
];
const SHELL_ASSET_PATHS = new Set(SHELL_ASSETS);

function isPrivateRuntimePath(pathname){
  return pathname.startsWith('/api/')
    || pathname.startsWith('/nova/')
    || pathname === '/status'
    || pathname === '/health'
    || pathname === '/healthz';
}

function hasAuthorization(request){
  return Boolean(
    request.headers
    && typeof request.headers.has === 'function'
    && request.headers.has('Authorization')
  );
}

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(SHELL_ASSETS)));
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(key => key.startsWith('nova-shell-') && key !== CACHE_NAME).map(key => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

async function matchCurrentShell(pathname){
  try {
    const cache = await caches.open(CACHE_NAME);
    return await cache.match(pathname);
  } catch(error) {
    return undefined;
  }
}

async function networkFirstShell(request, cacheKey, fallbackPath){
  let response;
  try {
    response = await fetch(request);
  } catch(error) {
    const cached = await matchCurrentShell(cacheKey);
    if(cached) return cached;
    if(fallbackPath !== cacheKey){
      const fallback = await matchCurrentShell(fallbackPath);
      if(fallback) return fallback;
    }
    return Response.error();
  }

  if(response && response.ok){
    try {
      const cache = await caches.open(CACHE_NAME);
      await cache.put(cacheKey, response.clone());
    } catch(error) {
      // A full or unavailable cache must never hide a fresh network response.
    }
  }
  return response;
}

async function navigationWithOfflineFallback(request){
  try {
    return await fetch(request);
  } catch(error) {
    return (await matchCurrentShell('/offline.html')) || Response.error();
  }
}

self.addEventListener('fetch', event => {
  const request = event.request;
  if(request.method !== 'GET') return;
  const url = new URL(request.url);
  if(url.origin !== self.location.origin) return;
  if(
    hasAuthorization(request)
    || url.pathname.startsWith('/api/')
    || isPrivateRuntimePath(url.pathname)
  ) return;

  if(request.mode === 'navigate'){
    if(url.pathname === '/companion'){
      event.respondWith(networkFirstShell(request, '/companion', '/companion'));
      return;
    }
    event.respondWith(navigationWithOfflineFallback(request));
    return;
  }

  if(SHELL_ASSET_PATHS.has(url.pathname) && url.pathname !== '/companion'){
    event.respondWith(networkFirstShell(request, url.pathname, url.pathname));
  }
});
