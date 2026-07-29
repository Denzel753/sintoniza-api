// Sintoniza Concursos — Service Worker
// Cache offline + notificações push
var CACHE = 'sintoniza-v2';

self.addEventListener('install', function(e) {
  self.skipWaiting();
  e.waitUntil(
    caches.open(CACHE).then(function(cache) {
      return cache.addAll([
        '/',
        'index.html',
        'css/style.css',
        'js/app.js',
        'js/classifier.js',
        'js/search.js',
        'js/settings.js',
        'js/data.js'
      ]);
    })
  );
});

self.addEventListener('activate', function(e) {
  e.waitUntil(clients.claim());
  // Limpa caches antigos
  caches.keys().then(function(keys) {
    keys.forEach(function(k) { if (k !== CACHE) caches.delete(k); });
  });
});

self.addEventListener('fetch', function(e) {
  e.respondWith(
    caches.match(e.request).then(function(r) {
      return r || fetch(e.request).then(function(res) {
        if (res.ok) {
          var clone = res.clone();
          caches.open(CACHE).then(function(c) { c.put(e.request, clone); });
        }
        return res;
      }).catch(function() {
        // Offline fallback — retorna cache
        return caches.match(e.request);
      });
    })
  );
});

self.addEventListener('push', function(e) {
  var data = e.data ? e.data.text() : 'Novos concursos encontrados!';
  e.waitUntil(
    self.registration.showNotification('📡 Sintoniza Concursos', {
      body: data,
      icon: 'assets/favicon.svg',
      tag: 'sintoniza',
      vibrate: [200, 100, 200]
    })
  );
});
