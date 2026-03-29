const CACHE = 'leads-v1';
const OFFLINE_ASSETS = [
  '/leads-system/',
  '/leads-system/index.html',
  'https://fonts.googleapis.com/css2?family=Heebo:wght@300;400;500;600;700;800;900&display=swap',
  'https://cdnjs.cloudflare.com/ajax/libs/exceljs/4.4.0/exceljs.min.js',
  'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2'
];

// Install — cache assets
self.addEventListener('install', e=>{
  e.waitUntil(
    caches.open(CACHE).then(c=>c.addAll(OFFLINE_ASSETS).catch(()=>{}))
  );
  self.skipWaiting();
});

// Activate — clean old caches
self.addEventListener('activate', e=>{
  e.waitUntil(
    caches.keys().then(keys=>
      Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Fetch — network first, fallback to cache
self.addEventListener('fetch', e=>{
  // Skip Supabase API calls (always need network)
  if(e.request.url.includes('supabase.co')) return;
  
  e.respondWith(
    fetch(e.request)
      .then(res=>{
        // Cache successful GET responses
        if(res.ok && e.request.method==='GET'){
          const clone = res.clone();
          caches.open(CACHE).then(c=>c.put(e.request, clone));
        }
        return res;
      })
      .catch(()=>caches.match(e.request))
  );
});
