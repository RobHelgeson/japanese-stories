// The whole published tree, kept on the device so the stories read with no
// network at all — a flight, a train through a tunnel.
//
// Cache-first, and versioned by a hash of every file it holds, so offline.py
// regenerates this file whenever anything in docs/ changes. That byte change is
// what makes the browser install a new worker; the new one fetches the whole
// tree before it takes over, and if any file fails it never does, so the device
// keeps a complete old copy rather than a half-new one. Online, a publish shows
// up one launch late: the launch that finds it is served from the old cache
// while the new one fills behind it.
//
// Generated into docs/ by offline.py. Edit scripts/sw.js, never docs/sw.js.
const VERSION = "__VERSION__";
const FILES = __FILES__;
const PREFIX = "japanese-stories-";
const CACHE = PREFIX + VERSION;

self.addEventListener("install", (e) => {
  // The query defeats GitHub Pages' CDN, which can go on serving a file for
  // several minutes after a push. Without it a worker installed in that window
  // would pin the old file under the new version until the next publish.
  // match() ignores the query, so it costs nothing on the way out.
  e.waitUntil(
    caches
      .open(CACHE)
      .then((c) => c.addAll(FILES.map((f) => new Request(f + "?v=" + VERSION, { cache: "reload" }))))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((k) => k.startsWith(PREFIX) && k !== CACHE).map((k) => caches.delete(k))),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  const url = new URL(req.url);
  // The gist sync talks to api.github.com and has to stay live.
  if (req.method !== "GET" || url.origin !== location.origin) return;
  // ignoreSearch also covers ?nosync and ?nostore, which are the same page.
  const key = url.pathname.endsWith("/") ? new URL("index.html", url) : url;
  e.respondWith(
    caches
      .open(CACHE)
      .then((c) => c.match(key, { ignoreSearch: true }))
      .then((hit) => hit || fetch(req)),
  );
});
