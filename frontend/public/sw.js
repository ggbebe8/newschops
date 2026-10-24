const CACHE = "newschops-shell-v1";
self.addEventListener("install", (event) =>
  event.waitUntil(
    caches
      .open(CACHE)
      .then((c) =>
        c.addAll(["/offline.html", "/icon-192.png", "/icon-512.png"]),
      ),
  ),
);
self.addEventListener("activate", (event) =>
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)),
        ),
      ),
  ),
);
self.addEventListener("fetch", (event) => {
  const u = new URL(event.request.url);
  if (
    u.origin !== self.location.origin ||
    u.pathname.startsWith("/api/") ||
    event.request.method !== "GET"
  )
    return;
  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request).catch(() => caches.match("/offline.html")),
    );
    return;
  }
  if (u.pathname.startsWith("/assets/") || u.pathname.startsWith("/icon-"))
    event.respondWith(
      fetch(event.request)
        .then((r) => {
          if (r.ok) {
            const copy = r.clone();
            caches.open(CACHE).then((c) => c.put(event.request, copy));
          }
          return r;
        })
        .catch(() => caches.match(event.request)),
    );
});

self.addEventListener("message", (event) => {
  if (event.data?.type === "ACTIVATE_UPDATE") self.skipWaiting();
});
self.addEventListener("activate", (event) =>
  event.waitUntil(self.clients.claim()),
);
