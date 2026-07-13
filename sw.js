const CACHE = 'leads-v4';
self.addEventListener('install', e=>{ self.skipWaiting(); });
self.addEventListener('activate', e=>{
  e.waitUntil(caches.keys().then(keys=>
    Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))
  ));
  self.clients.claim();
});
self.addEventListener('fetch', e=>{
  if(e.request.url.includes('supabase.co')) return;
  let u; try{ u=new URL(e.request.url); }catch(_){ u=null; }
  // אל תשמור בקאש בקשות עם query string (share target / פרמטרים רגישים)
  const hasQuery = u && u.search && u.search.length>0;
  e.respondWith(
    fetch(e.request).then(res=>{
      if(res.ok && e.request.method==='GET' && !hasQuery){
        const clone=res.clone();
        caches.open(CACHE).then(c=>c.put(e.request,clone));
      }
      return res;
    }).catch(()=>caches.match(e.request))
  );
});
// Notification click — focus or open the app
self.addEventListener('notificationclick', e=>{
  e.notification.close();
  e.waitUntil(
    clients.matchAll({type:'window', includeUncontrolled:true}).then(list=>{
      for(const c of list){ if('focus' in c) return c.focus(); }
      if(clients.openWindow) return clients.openWindow('/leads-system/');
    })
  );
});
