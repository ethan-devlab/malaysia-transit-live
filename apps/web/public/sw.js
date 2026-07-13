const CACHE_NAME = "malaysia-transit-shell-v1"

self.addEventListener("install", () => {
  self.skipWaiting()
})

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim())
})

self.addEventListener("fetch", (event) => {
  const request = event.request
  const url = new URL(request.url)
  if (request.method !== "GET" || url.origin !== self.location.origin) {
    return
  }
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/stream/")) {
    return
  }
  if (request.mode === "navigate") {
    event.respondWith(networkFirstNavigation(request))
    return
  }
  event.respondWith(cacheFirstAsset(request))
})

async function networkFirstNavigation(request) {
  const cache = await caches.open(CACHE_NAME)
  try {
    const response = await fetch(request)
    if (response.ok) {
      await cache.put(request, response.clone())
    }
    return response
  } catch {
    return (await cache.match(request)) || Response.error()
  }
}

async function cacheFirstAsset(request) {
  const cache = await caches.open(CACHE_NAME)
  const cached = await cache.match(request)
  if (cached) {
    return cached
  }
  const response = await fetch(request)
  if (response.ok) {
    await cache.put(request, response.clone())
  }
  return response
}
