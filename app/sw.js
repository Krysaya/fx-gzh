/* 留白禅意风排版 App —— Service Worker（离线缓存）
   缓存 App 自身资源，使手机无网也能打开使用。
   iOS 16.4+ 支持 PWA 离线；更早版本注册失败也不影响「添加到主屏幕」。 */
const CACHE = 'gzh-zen-v1';
const FILES = ['./', 'index.html', 'manifest.json', 'icon.svg'];

self.addEventListener('install', function (e) {
  e.waitUntil(
    caches.open(CACHE).then(function (c) {
      return c.addAll(FILES);
    }).then(function () {
      return self.skipWaiting();
    })
  );
});

self.addEventListener('activate', function (e) {
  e.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.map(function (k) {
        if (k !== CACHE) return caches.delete(k);
      }));
    }).then(function () {
      return self.clients.claim();
    })
  );
});

self.addEventListener('fetch', function (e) {
  if (e.request.method !== 'GET') return;
  e.respondWith(
    caches.match(e.request).then(function (hit) {
      if (hit) return hit;
      return fetch(e.request).then(function (resp) {
        if (resp && resp.status === 200 && resp.type === 'basic') {
          const copy = resp.clone();
          caches.open(CACHE).then(function (c) { c.put(e.request, copy); });
        }
        return resp;
      }).catch(function () {
        return caches.match('index.html');
      });
    })
  );
});
