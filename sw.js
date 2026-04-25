const CACHE = 'leads-v2';
self.addEventListener('install', e=>{
  self.skipWaiting();
});
self.addEventListener('activate', e=>{
  e.waitUntil(caches.keys().then(keys=>
    Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))
  ));
  self.clients.claim();
});
self.addEventListener('fetch', e=>{
  if(e.request.url.includes('supabase.co')) return;
  e.respondWith(
    fetch(e.request).then(res=>{
      if(res.ok && e.request.method==='GET'){
        const clone=res.clone();
        caches.open(CACHE).then(c=>c.put(e.request,clone));
      }
      return res;
    }).catch(()=>caches.match(e.request))
  );
});
