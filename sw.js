/* Service worker.
 *
 * Online:  every request goes to the network first, so the pages always load the
 *          newest data files (data/history.csv and data/status.json).
 * Offline: the same requests are answered from the cache, so the site still opens
 *          and shows the last data it loaded. Cached data answers carry the header
 *          "x-from-cache: 1" so the pages can say they are showing saved data.
 */
const CACHE = "nba-awards-v1";

const SHELL = [
  "./",
  "index.html",
  "browse.html",
  "trends.html",
  "manifest.webmanifest",
  "assets/style.css",
  "assets/common.js",
  "assets/charts.js",
  "assets/index.js",
  "assets/browse.js",
  "assets/trends.js",
  "assets/icon-192.png",
  "assets/icon-512.png",
  "data/history.csv",
  "data/status.json",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE)
      // addAll would fail the whole install if one file is missing; add them one by one
      .then((cache) => Promise.all(SHELL.map((url) => cache.add(new Request(url, { cache: "reload" })).catch(() => {}))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

function withMarker(response) {
  const headers = new Headers(response.headers);
  headers.set("x-from-cache", "1");
  return new Response(response.body, { status: response.status, statusText: response.statusText, headers });
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  event.respondWith((async () => {
    const cache = await caches.open(CACHE);
    try {
      const fresh = await fetch(request, { cache: "no-store" });
      if (fresh && fresh.ok) cache.put(request, fresh.clone());
      return fresh;
    } catch (error) {
      const saved = await cache.match(request, { ignoreSearch: true });
      if (saved) return withMarker(saved);
      if (request.mode === "navigate") {
        const home = await cache.match("index.html");
        if (home) return home;
      }
      return new Response("Offline and not cached yet.", { status: 503, headers: { "content-type": "text/plain" } });
    }
  })());
});
