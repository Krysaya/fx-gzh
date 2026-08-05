/* 留白禅意风排版 App —— Service Worker（离线缓存）
   策略：
   - index.html / 关键入口：network-first（网络优先，失败才用缓存）
     → 新版发布后，用户最多一次访问即拿到最新代码，不再被旧缓存锁死
   - 其余静态资源（icon.svg 等）：stale-while-revalidate（先缓存、后台更新）
   - 离线时全部回退到缓存，保证无网也能排版
   iOS 16.4+ 支持 PWA 离线；更早版本注册失败也不影响「添加到主屏幕」。 */
const CACHE = 'gzh-zen-v3';
const FILES = ['./', 'index.html', 'manifest.json', 'icon.svg'];
const NETWORK_FIRST = new Set(['./', 'index.html']);

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

function isNetworkFirst(url){
  const path = url.pathname;
  return NETWORK_FIRST.has(path) || path.endsWith('/') || path.endsWith('index.html');
}

self.addEventListener('fetch', function (e) {
  if (e.request.method !== 'GET') return;
  const url = new URL(e.request.url);
  if (url.origin !== self.location.origin) return; // 只代理同源资源

  if (isNetworkFirst(url)) {
    // network-first：先网络，失败回退缓存
    e.respondWith(
      fetch(e.request).then(function (resp) {
        if (resp && resp.status === 200) {
          const copy = resp.clone();
          caches.open(CACHE).then(function (c) { c.put(e.request, copy); });
        }
        return resp;
      }).catch(function () {
        return caches.match(e.request).then(function (hit) { return hit || caches.match('index.html'); });
      })
    );
    return;
  }

  // stale-while-revalidate：先给缓存，后台更新
  e.respondWith(
    caches.open(CACHE).then(function (c) {
      return c.match(e.request).then(function (hit) {
        const update = fetch(e.request).then(function (resp) {
          if (resp && resp.status === 200) c.put(e.request, resp.clone());
          return resp;
        }).catch(function () { return hit; });
        return hit || update;
      });
    })
  );
});
