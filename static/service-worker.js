// PWA 核心缓存机制 (此处为不限制在线操作的占位基本安装模式)
const CACHE_NAME = 'video-snap-v1';

self.addEventListener('install', (event) => {
    // 强制立即接管不等待刷新
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(clients.claim());
});

self.addEventListener('fetch', (event) => {
    // PWA: 以网络优先（不对大文件和爬虫 API 强行缓存，保持数据最新）
    event.respondWith(fetch(event.request).catch(() => console.log('Fetch failed in PWA Service Worker')));
});
