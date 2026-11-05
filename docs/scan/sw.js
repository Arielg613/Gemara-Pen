// Offline cache for the Gemara Scanner. Bump CACHE when any file changes
// (and CACHE_NAME in index.html with it).
const CACHE = "gemara-scan-v10";
const FILES = [
  "./",
  "index.html",
  "manifest.json",
  "icon.png",
  "Berakhot.json",
  "vendor/tesseract.min.js",
  "vendor/worker.min.js",
  "vendor/tesseract-core-lstm.wasm.js",
  "vendor/tesseract-core-simd-lstm.wasm.js",
  "vendor/lang/heb.traineddata.gz",
];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(FILES)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

// Cache first, then network (and remember what we fetched). Any page load
// with no network falls back to the cached app, whatever URL it came in on.
self.addEventListener("fetch", e => {
  if (e.request.method !== "GET") return;
  if (new URL(e.request.url).pathname.includes("/api/")) return;
  e.respondWith((async () => {
    const hit = await caches.match(e.request, { ignoreSearch: true });
    if (hit) return hit;
    try {
      const res = await fetch(e.request);
      if (res.ok && new URL(e.request.url).origin === location.origin) {
        const copy = res.clone();
        caches.open(CACHE).then(c => c.put(e.request, copy));
      }
      return res;
    } catch (err) {
      if (e.request.mode === "navigate") {
        const app = await caches.match("index.html");
        if (app) return app;
      }
      throw err;
    }
  })());
});
