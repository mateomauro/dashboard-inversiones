// Service worker minimo, sin cache: existe solo para que el navegador
// (sobre todo Android/Chrome) ofrezca "Instalar app" en vez de un simple
// acceso directo. Nunca guarda nada — siempre va a la red, para no correr
// el riesgo de mostrar precios o datos viejos.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", (e) => { e.respondWith(fetch(e.request)); });
