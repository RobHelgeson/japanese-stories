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
const VERSION = "d358bd2572fa";
const FILES = [
  "apple-touch-icon.png",
  "chichi-no-hasami.html",
  "data/chichi-no-hasami.js",
  "data/endai-no-shougi.js",
  "data/entotsu-no-kemuri.js",
  "data/ikanakatta-hito-no-chizu.js",
  "data/juugonichi-no-shichifuda.js",
  "data/kairanban-no-henji.js",
  "data/maigo-no-tegami.js",
  "data/neko-o-sagasu-tantei.js",
  "data/rouka-no-kagami.js",
  "data/sanban-no-kansouki.js",
  "data/shio-no-tamagoyaki.js",
  "data/shiro-no-kane.js",
  "data/shuden.js",
  "data/suupu-o-nokosu-kyaku.js",
  "data/tokei-no-oto.js",
  "endai-no-shougi.html",
  "entotsu-no-kemuri.html",
  "icon-192.png",
  "icon-512.png",
  "icon-maskable-512.png",
  "ikanakatta-hito-no-chizu.html",
  "index.html",
  "juugonichi-no-shichifuda.html",
  "kairanban-no-henji.html",
  "maigo-no-tegami.html",
  "manifest.webmanifest",
  "neko-o-sagasu-tantei.html",
  "reader.css",
  "reader.js",
  "rouka-no-kagami.html",
  "sanban-no-kansouki.html",
  "shio-no-tamagoyaki.html",
  "shiro-no-kane.html",
  "shuden.html",
  "suupu-o-nokosu-kyaku.html",
  "sync.js",
  "tokei-no-oto.html",
  "versions/maigo-no-tegami.v1.html",
  "versions/neko-o-sagasu-tantei.v1.html",
  "versions/shiro-no-kane.v1.html",
  "versions/shuden.v1.html",
  "versions/tokei-no-oto.v1.html"
];
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
