{% load static %}// plane-history service worker —— network-first：online 永遠攞最新（唔會 stale），
// offline 先 fallback cache（殼 + 已瀏覽過嘅 static / 首頁）。只 cache /static/ 同 '/'，
// 唔 cache /api/ 同 login-gated 內容。serve 喺 root（/sw.js）所以 scope = 全站。
const CACHE = 'ph-v1';
const SHELL = [
  '/',
  '{% static "css/base.css" %}',
  '{% static "img/favicon.svg" %}',
  '{% static "img/icon-192.png" %}'
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()).catch(() => {})
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;
  const cacheable = url.pathname.startsWith('/static/') || url.pathname === '/';
  e.respondWith(
    fetch(req).then((res) => {
      if (cacheable && res && res.ok) {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(req, copy));
      }
      return res;
    }).catch(() => caches.match(req).then((m) => m || (req.mode === 'navigate' ? caches.match('/') : Response.error())))
  );
});
