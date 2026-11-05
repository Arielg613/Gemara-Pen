// Offline cache for the Gemara Scanner. Bump CACHE when any file changes.
const CACHE = "gemara-scan-v2";
const FILES = [
  "./",
  "index.html",
  "manifest.json",
  "Berakhot.json",
  "jastrow.js",
  "jastrow.json",
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

// Cache first, then network (and remember what we fetched).
self.addEventListener("fetch", e => {
  if (e.request.method !== "GET") return;
  e.respondWith(
    caches.match(e.request, { ignoreSearch: true }).then(hit => hit || fetch(e.request).then(res => {
      if (res.ok && new URL(e.request.url).origin === location.origin) {
        const copy = res.clone();
        caches.open(CACHE).then(c => c.put(e.request, copy));
      }
      return res;
    }))
  );
});
