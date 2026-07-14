const CACHE = 'leads-v6';
self.addEventListener('install', e=>{ self.skipWaiting(); });
self.addEventListener('activate', e=>{
  e.waitUntil(caches.keys().then(keys=>
    Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))
  ));
  self.clients.claim();
});
self.addEventListener('fetch', e=>{
  // Share Target POST — קלוט את הטקסט המשותף בלי לחשוף אותו ב-URL
  const reqUrl = new URL(e.request.url);
  if(e.request.method==='POST' && reqUrl.pathname.endsWith('/share-target')){
    e.respondWith((async()=>{
      try{
        const form = await e.request.formData();
        const text = form.get('shared_text')||form.get('text')||'';
        const cache = await caches.open('share-temp');
        // מחק תוכן ישן קודם — לא להשאיר שאריות מ-share קודם
        try{ const keys=await cache.keys(); await Promise.all(keys.map(k=>cache.delete(k))); }catch(_){}
        // שמור עם חותמת זמן כדי שהאפליקציה תוכל להתעלם מתוכן ישן
        const payload=JSON.stringify({ text: text||'', ts: Date.now() });
        await cache.put('/leads-system/__shared', new Response(payload, {headers:{'Content-Type':'application/json'}}));
      }catch(err){}
      // הפניה נקייה, נבנית מ-origin האמיתי
      const redirectUrl = new URL('/leads-system/?shared=1', self.location.origin).href;
      return Response.redirect(redirectUrl, 303);
    })());
    return;
  }
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
