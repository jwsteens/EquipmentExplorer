/**
 * Equipment Explorer - Service Worker
 * Provides offline caching for static assets only
 * HTML pages are always fetched from network to respect authentication
 */

const CACHE_NAME = 'equipment-explorer-v2';

// Only cache static assets, NOT HTML pages
const STATIC_ASSETS = [
    '/static/css/main.css',
    '/static/js/main.js',
    '/static/js/search.js',
    '/manifest.json'
];

// External resources to cache
const EXTERNAL_ASSETS = [
    'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&family=Space+Grotesk:wght@500;600;700&display=swap',
    'https://code.jquery.com/jquery-3.7.1.min.js',
    'https://cdn.datatables.net/1.13.7/js/jquery.dataTables.min.js',
    'https://cdn.datatables.net/1.13.7/css/jquery.dataTables.min.css'
];

// Install event - cache static assets
self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => {
                console.log('Caching static assets');
                return cache.addAll(STATIC_ASSETS);
            })
            .then(() => self.skipWaiting())
    );
});

// Activate event - clean up old caches
self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys()
            .then(cacheNames => {
                return Promise.all(
                    cacheNames
                        .filter(name => name !== CACHE_NAME)
                        .map(name => caches.delete(name))
                );
            })
            .then(() => self.clients.claim())
    );
});

// Fetch event - different strategies for different content types
self.addEventListener('fetch', event => {
    const { request } = event;
    const url = new URL(request.url);
    
    // Skip non-GET requests
    if (request.method !== 'GET') {
        return;
    }
    
    // HTML pages and navigation - ALWAYS network first, no caching
    // This ensures authentication state is always respected
    if (request.mode === 'navigate' || 
        request.headers.get('accept')?.includes('text/html') ||
        url.pathname === '/' ||
        url.pathname === '/search' ||
        url.pathname === '/cables' ||
        url.pathname === '/documents' ||
        url.pathname === '/help' ||
        url.pathname === '/login' ||
        url.pathname === '/logout' ||
        url.pathname === '/profile' ||
        url.pathname.startsWith('/admin')) {
        event.respondWith(
            fetch(request)
                .catch(() => {
                    // If offline, show a simple offline message
                    return new Response(
                        '<!DOCTYPE html><html><head><title>Offline</title></head><body style="font-family:sans-serif;text-align:center;padding:50px;"><h1>You are offline</h1><p>Please check your connection and try again.</p></body></html>',
                        { headers: { 'Content-Type': 'text/html' } }
                    );
                })
        );
        return;
    }
    
    // API requests - network only, no caching (auth required)
    if (url.pathname.startsWith('/api/')) {
        event.respondWith(fetch(request));
        return;
    }
    
    // PDF requests - network only (too large to cache, auth required)
    if (url.pathname.startsWith('/pdf/')) {
        event.respondWith(fetch(request));
        return;
    }
    
    // Static assets (CSS, JS, fonts) - cache first, then network
    if (url.pathname.startsWith('/static/') || 
        url.hostname === 'fonts.googleapis.com' ||
        url.hostname === 'fonts.gstatic.com' ||
        url.hostname === 'code.jquery.com' ||
        url.hostname === 'cdn.datatables.net') {
        event.respondWith(
            caches.match(request)
                .then(cachedResponse => {
                    if (cachedResponse) {
                        // Return cached version and update cache in background
                        fetch(request).then(response => {
                            if (response.ok) {
                                caches.open(CACHE_NAME).then(cache => {
                                    cache.put(request, response);
                                });
                            }
                        }).catch(() => {});
                        return cachedResponse;
                    }
                    
                    // Not in cache - fetch from network
                    return fetch(request).then(response => {
                        // Cache successful responses
                        if (response.ok) {
                            const responseClone = response.clone();
                            caches.open(CACHE_NAME).then(cache => {
                                cache.put(request, responseClone);
                            });
                        }
                        return response;
                    });
                })
        );
        return;
    }
    
    // Everything else - network only
    event.respondWith(fetch(request));
});

// Handle messages from the main thread
self.addEventListener('message', event => {
    if (event.data && event.data.type === 'SKIP_WAITING') {
        self.skipWaiting();
    }
    
    // Allow clearing cache from main thread
    if (event.data && event.data.type === 'CLEAR_CACHE') {
        caches.delete(CACHE_NAME).then(() => {
            console.log('Cache cleared');
        });
    }
});
