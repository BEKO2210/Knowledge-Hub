/* Service Worker der Hub-PWA.
 *
 * Regeln (Sicherheit vor Komfort):
 *  - /ui/api/* und /mcp werden NIE angefasst: kein Cache, kein Fallback — Secrets,
 *    Tokens und Live-Daten gehen ausschließlich ans Netz.
 *  - Gecacht werden nur eigene statische Assets (CSS, JS, Icons, Fonts) — versioniert
 *    über die Asset-Version, alte Caches werden beim Aktivieren gelöscht.
 *  - Die App-Shell (/ui) ist network-first mit Cache-Fallback: offline öffnet die
 *    Oberfläche, Anmeldung und Daten brauchen naturgemäß das Netz.
 */
'use strict';

const VERSION = '__V__';
const CACHE = 'kmcp-ui-' + VERSION;
const PRECACHE = [
  '/ui',
  '/ui/asset/app.css?v=' + VERSION,
  '/ui/asset/app.js?v=' + VERSION,
  '/ui/static/icon-192.png?v=' + VERSION,
  '/ui/static/icon-512.png?v=' + VERSION,
  '/ui/static/favicon.png?v=' + VERSION,
  '/ui/manifest.json?v=' + VERSION,
];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      // Nur eigene kmcp-ui-*-Caches räumen — fremde Caches derselben Origin bleiben unangetastet.
      .then((keys) => Promise.all(keys.filter((k) => k.startsWith('kmcp-ui-') && k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== self.location.origin) return;
  // Live-Daten und alles Sensible: immer Netz, nie Cache.
  if (url.pathname.startsWith('/ui/api/') || url.pathname.startsWith('/mcp')
      || url.pathname.startsWith('/oauth') || url.pathname.startsWith('/healthz')) return;

  if (url.pathname === '/ui' || url.pathname === '/ui/') {
    // App-Shell: frisch, wenn möglich — offline aus dem Cache.
    // Nur r.ok cachen: /ui kann auch 409 (Recovery) oder den Setup-Wizard liefern —
    // das darf die gecachte Shell nicht überschreiben.
    e.respondWith(
      fetch(e.request)
        .then((r) => {
          if (r.ok) { const copy = r.clone(); caches.open(CACHE).then((c) => c.put('/ui', copy)); }
          return r;
        })
        .catch(() => caches.match('/ui'))
    );
    return;
  }
  if (url.pathname.startsWith('/ui/asset/') || url.pathname.startsWith('/ui/static/')
      || url.pathname === '/ui/manifest.json') {
    // Statische Assets: cache-first (versioniert), Netz füllt nach.
    e.respondWith(
      caches.match(e.request).then((hit) => hit || fetch(e.request).then((r) => {
        const copy = r.clone();
        if (r.ok) caches.open(CACHE).then((c) => c.put(e.request, copy));
        return r;
      }))
    );
  }
});
