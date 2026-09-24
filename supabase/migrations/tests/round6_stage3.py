# -*- coding: utf-8 -*-
# סבב 6, שלב 3: ארכיטקטורת סנכרון (F02/D04/D06/F10/F11/D01/D02/D07/D08/F05) — קוד המערכת האמיתי
# מול שרת מדומה בתוך הדף (sb מזויף עם "שערים" שמאפשרים לעכב/לשחרר כל בקשה). סמנטיקת upsert_leads_checked
# זהה לפונקציה ב-PostgreSQL (נבדקה בנפרד מול PostgreSQL אמיתי ב-pg_rpc_tests.py).
import os, sys, json
from playwright.sync_api import sync_playwright
TARGET=os.environ.get('LEADS_TARGET') or sys.argv[1]
FAKE=r"""
window.__srv={leads:{}, meta:{contacts:'[]', deleted_contacts:'[]'}, fail:{}, calls:[], seq:0};
window.__gates={};
window.__gate=(k)=>{ let rel; const p=new Promise(r=>rel=r); window.__gates[k]={p, rel}; };
window.__open=(k)=>{ const g=window.__gates[k]; if(g){ delete window.__gates[k]; g.rel(); } };
const __ts=()=>new Date(Date.UTC(2026,8,1)+(++__srv.seq)*1000).toISOString();
async function __wait(k){ const g=window.__gates[k]; if(g) await g.p; }
function __exec(table, ops){
  return (async()=>{
    const names=ops.map(o=>o[0]);
    const eq=ops.find(o=>o[0]==='eq'), inn=ops.find(o=>o[0]==='in');
    if(table==='leads'){
      if(names.includes('delete')){ __srv.calls.push('DELETE '+eq[1][1]); await __wait('del');
        if(__srv.fail.del) return {error:{message:'simulated delete failure'}};
        delete __srv.leads[eq[1][1]]; return {error:null}; }
      if(names.includes('upsert')){ const rows=ops.find(o=>o[0]==='upsert')[1][0]; __srv.calls.push('LEGACY '+rows.map(r=>r.id));
        rows.forEach(r=>{ __srv.leads[r.id]={data:r.data, updated_at:__ts()}; }); return {error:null}; }
      __srv.calls.push('GET'); await __wait('get');
      if(__srv.fail.get){ const f=__srv.fail.get; if(typeof f==='number'){ __srv.fail.get--; } return {data:null,error:{message:'simulated GET failure'}}; }
      let rows=Object.entries(__srv.leads).map(([id,v])=>({id:+id, data:v.data, updated_at:v.updated_at}));
      if(inn) rows=rows.filter(r=>inn[1][1].includes(r.id));
      return {data:JSON.parse(JSON.stringify(rows)), error:null};
    }
    if(table==='app_meta'){
      if(names.includes('upsert')){ ops.find(o=>o[0]==='upsert')[1][0].forEach(r=>{ __srv.meta[r.key]=r.value; }); return {error:null}; }
      const key=eq?eq[1][1]:null; return {data: key&&__srv.meta[key]!=null?{value:__srv.meta[key]}:null, error:null};
    }
    return {data:[], error:null};
  })();
}
function __chain(table){ const ops=[]; const p=new Proxy(function(){},{ get(t,k){ if(k==='then') return (a,b)=>__exec(table,ops).then(a,b);
  return (...args)=>{ ops.push([k,args]); return p; }; }}); return p; }
sb={
  from:(t)=>__chain(t),
  auth:{ getSession:async()=>({data:{session:{}}}), getUser:async()=>({data:{user:{id:'u1'}},error:null}),
         refreshSession:async()=>({data:{session:{}}}), signOut:async()=>({}), onAuthStateChange:()=>({data:{subscription:{unsubscribe(){}}}}) },
  rpc: async(name, params)=>{
    __srv.calls.push('RPC '+name+' '+JSON.stringify((params.p_rows||[]).map(r=>[r.id,r.force?'F':''])));
    if(name==='upsert_leads_checked'){
      await __wait('rpc'); if(__srv.fail.rpc){ __srv.fail.rpc--; return {data:null,error:{message:'simulated save failure'}}; }
      const out=[];
      params.p_rows.forEach(r=>{ const cur=__srv.leads[r.id];
        if(cur){ if(!r.force && (r.base==null || cur.updated_at!==r.base)){ out.push({o_id:r.id,o_status:'conflict',o_updated_at:cur.updated_at,o_server_data:cur.data}); return; } }
        else if(r.base!=null && !r.force){ out.push({o_id:r.id,o_status:'deleted',o_updated_at:null,o_server_data:null}); return; }
        const ts=__ts(); __srv.leads[r.id]={data:JSON.parse(JSON.stringify(r.data)), updated_at:ts}; out.push({o_id:r.id,o_status:'ok',o_updated_at:ts,o_server_data:null}); });
      return {data:out, error:null};
    }
    if(name==='merge_contacts'){
      let cur=JSON.parse(__srv.meta.contacts||'[]'); const ups=params.p_upserts||[], del=params.p_deleted_ids||[];
      cur=cur.filter(c=>!del.includes(String(c.id))).map(c=>ups.find(u=>String(u.id)===String(c.id))||c);
      ups.forEach(u=>{ if(!cur.some(c=>String(c.id)===String(u.id)) && !del.includes(String(u.id))) cur.push(u); });
      __srv.meta.contacts=JSON.stringify(cur); __srv.lastMerge=params; return {data:cur, error:null};
    }
    return {data:null, error:{message:'unknown rpc'}};
  }
};
window.initSupabase=()=>{};
"""
P=[]
def ck(n,c): P.append((n,bool(c)))
dlg={'answers':[]}
def on_dialog(d):
    a=dlg['answers'].pop(0) if dlg['answers'] else 'accept'
    d.accept() if a=='accept' else d.dismiss()
with sync_playwright() as p:
    b=p.chromium.launch(); ctx=b.new_context(viewport={'width':1400,'height':900})
    ctx.route('**://*.supabase.co/**', lambda r: r.abort()); ctx.route('**://cdn*/**', lambda r: r.abort())
    pg=ctx.new_page(); errs=[]
    pg.on('pageerror', lambda e: errs.append(str(e)[:160]) if 'supabase is not defined' not in str(e) else None)
    pg.on('dialog', on_dialog)
    def fresh(setup_js=''):
        pg.goto('file://'+TARGET); pg.wait_for_timeout(900)
        pg.evaluate("localStorage.clear()"); pg.reload(); pg.wait_for_timeout(900)
        pg.evaluate(FAKE)
        pg.evaluate("""(async()=>{ window.__isAuthed=true; unlockAppShell();
          for(let i=1;i<=4;i++) __srv.leads[i]={data:{id:i,address:'רחוב '+i,city:'תא',name:'x',status:'חדש',date:'2026-05-01',replied:'לא'}, updated_at:'2026-09-0'+i+'T10:00:00.000Z'};
          %s
          await loadFromSupabase(); })()""" % setup_js)
        pg.wait_for_timeout(200)
    OB="JSON.parse(localStorage.getItem('leadOutbox_v1')||'{}')"
    # ── F02: כתיבה בדרך + עריכה נוספת → התור העמיד כולל את שתיהן ──
    fresh()
    r=pg.evaluate("""(async()=>{ __gate('rpc');
      leads.find(l=>l.id===1).notes='שינוי 1'; saveData(1);
      const f=flushPendingSaves(); await new Promise(r=>setTimeout(r,100));
      leads.find(l=>l.id===2).notes='שינוי 2'; saveData(2);
      const disk=Object.keys(%s).map(Number).sort();
      __open('rpc'); await f; await new Promise(r=>setTimeout(r,1200)); await flushPendingSaves();
      return {disk, after:Object.keys(%s).length, s1:__srv.leads[1].data.notes, s2:__srv.leads[2].data.notes};})()""" % (OB,OB))
    ck("F02: בזמן שכתיבת ליד 1 בדרך ועורכים את 2 — התור בדיסק מכיל את שניהם", r['disk']==[1,2])
    ck("F02: אחרי אישור — שני השינויים בשרת והתור ריק", r['s1']=='שינוי 1' and r['s2']=='שינוי 2' and r['after']==0)
    # ── F02b: רענון לפני אישור → שחזור מלא, עם תוכן ──
    fresh()
    pg.evaluate("""(async()=>{ __gate('rpc'); leads.find(l=>l.id===1).notes='לפני רענון'; saveData(1); flushPendingSaves(); await new Promise(r=>setTimeout(r,100)); })()""")
    pg.reload(); pg.wait_for_timeout(900); pg.evaluate(FAKE)
    r=pg.evaluate("""(async()=>{ window.__isAuthed=true; unlockAppShell();
      for(let i=1;i<=4;i++) __srv.leads[i]={data:{id:i,address:'רחוב '+i,city:'תא',status:'חדש',date:'2026-05-01'}, updated_at:'2026-09-0'+i+'T10:00:00.000Z'};
      await loadFromSupabase(); recoverPendingSaves(); await new Promise(r=>setTimeout(r,1200)); await flushPendingSaves();
      return {mem:leads.find(l=>l.id===1).notes, srv:__srv.leads[1].data.notes, ob:Object.keys(%s).length};})()""" % OB)
    ck("F02: רענון לפני אישור — השינוי שוחזר ונשמר", r['mem']=='לפני רענון' and r['srv']=='לפני רענון' and r['ob']==0)
    # ── F02c: כשל וניסיון חוזר ──
    fresh()
    r=pg.evaluate("""(async()=>{ __srv.fail.rpc=2; leads.find(l=>l.id===3).notes='אחרי כשל'; saveData(3);
      const ok1=await flushPendingSaves(); const kept=Object.keys(%s).length;
      const ok2=await flushPendingSaves();
      return {ok1, kept, ok2, srv:__srv.leads[3].data.notes, ob:Object.keys(%s).length};})()""" % (OB,OB))
    ck("F02: כשל שמירה — השינוי נשאר בתור; ניסיון חוזר שומר", r['ok1']==False and r['kept']==1 and r['ok2']==True and r['srv']=='אחרי כשל' and r['ob']==0)
    # ── F02d: שני שינויים עוקבים באותו ליד בזמן שהראשון בדרך ──
    fresh()
    r=pg.evaluate("""(async()=>{ __gate('rpc');
      leads.find(l=>l.id===1).notes='ראשון'; saveData(1); const f=flushPendingSaves(); await new Promise(r=>setTimeout(r,100));
      leads.find(l=>l.id===1).notes='שני'; saveData(1);
      __open('rpc'); __gate('rpc');                       // הסבב השני (השינוי השני) ייעצר — כדי לראות את מצב הביניים
      await new Promise(r=>setTimeout(r,120));
      const mid=%s[1]; __open('rpc'); await f; await new Promise(r=>setTimeout(r,1200)); await flushPendingSaves();
      return {midKept:!!mid && mid.payload.notes==='שני', srv:__srv.leads[1].data.notes, ob:Object.keys(%s).length, conflicts:localStorage.getItem('leadConflicts_v1')};})()""" % (OB,OB))
    ck("F02: שינוי שני באותו ליד בזמן שהראשון בדרך — לא נמחק מהתור עם אישור הראשון", r['midKept'])
    ck("F02: השינוי האחרון הוא שבשרת, בלי התנגשות מדומה", r['srv']=='שני' and r['ob']==0 and r['conflicts'] is None)
    # ── D04: מחיקה נכשלת בזמן שנערך ליד אחר → התור ממוזג, לא snapshot ──
    fresh()
    r=pg.evaluate("""(async()=>{ __gate('del'); __srv.fail.del=true;
      const d=deleteLead(1); await new Promise(r=>setTimeout(r,150));
      leads.find(l=>l.id===2).notes='בזמן מחיקה'; saveData(2);
      __open('del'); await d; await new Promise(r=>setTimeout(r,100));
      return {ob:Object.keys(%s).map(Number).sort(), back:leads.some(l=>l.id===1)};})()""" % OB)
    ck("D04: כשל מחיקה בזמן עריכת ליד אחר — העריכה נשארת בתור והליד חוזר", 2 in r['ob'] and r['back'])
    # ── D06: שחזור ישן שנדחה לא נדרס ע"י עריכה אחרת ──
    fresh("""localStorage.setItem('leadOutbox_v1', JSON.stringify({4:{payload:{id:4,address:'רחוב 4',city:'תא',status:'חדש',notes:'ישן מאוד'},base:'2026-09-04T10:00:00.000Z',rev:1,ts:Date.now()-72*3600e3}}));""")
    dlg['answers']=['dismiss']
    r=pg.evaluate("""(async()=>{ _outbox=JSON.parse(localStorage.getItem('leadOutbox_v1')); recoverPendingSaves();
      leads.find(l=>l.id===2).notes='עריכה אחרת'; saveData(2); await flushPendingSaves();
      const ob=%s; return {kept:!!ob[4] && ob[4].payload.notes==='ישן מאוד', srv4:__srv.leads[4].data.notes||''};})()""" % OB)
    ck("D06: שחזור ישן שנדחה נשאר שמור עם התוכן שלו גם אחרי עריכות אחרות", r['kept'] and r['srv4']=='')
    # ── D01: כתיבה בדרך + מחיקת כפולים → הליד לא חוזר בשרת ──
    fresh()
    r=pg.evaluate("""(async()=>{ __gate('rpc'); leads.find(l=>l.id===1).notes='בדרך'; saveData(1); const f=flushPendingSaves(); await new Promise(r=>setTimeout(r,100));
      window._dupMarkedDelete=[1]; window._dupGroups=[[1,2]];
      const d=deleteDupMarked(); await new Promise(r=>setTimeout(r,150)); const deletedBeforeWrite=!__srv.leads[1];
      __open('rpc'); await f; await d; await new Promise(r=>setTimeout(r,200));
      return {deletedBeforeWrite, srv:!!__srv.leads[1], local:leads.some(l=>l.id===1)};})()""")
    ck("D01: מחיקת כפולים ממתינה לכתיבה שבדרך (לא רצה במקביל)", not r['deletedBeforeWrite'])
    ck("D01: בסוף — הליד לא קיים בשרת ולא מקומית", not r['srv'] and not r['local'])
    # ── D02: קריאה שיצאה לפני המחיקה לא מחזירה את הליד ──
    fresh()
    r=pg.evaluate("""(async()=>{ __gate('get'); const rl=reloadFromSupabase(true); await new Promise(r=>setTimeout(r,100));
      await deleteLead(1);
      __open('get'); await rl; await new Promise(r=>setTimeout(r,100));
      const bak=JSON.parse(localStorage.getItem('leads_tracker_v4')||'{}');
      return {mem:leads.some(l=>l.id===1), disk:(bak.leads||[]).some(l=>l.id===1), srv:!!__srv.leads[1]};})()""")
    ck("D02: קריאה ישנה שחזרה אחרי המחיקה לא מחזירה את הליד (זיכרון וגיבוי)", not r['mem'] and not r['disk'] and not r['srv'])
    r=pg.evaluate("""(async()=>{ await reloadFromSupabase(true); return leads.some(l=>l.id===1); })()""")
    ck("D02: קריאה חדשה אחרי המחיקה — הליד לא חוזר", not r)
    # ── F10: שחזור ישן מול גרסת שרת חדשה → התנגשות, לא דריסה ──
    fresh("""localStorage.setItem('leadOutbox_v1', JSON.stringify({2:{payload:{id:2,address:'רחוב 2',city:'תא',status:'חדש',notes:'מקומי ישן'},base:'2026-08-01T10:00:00.000Z',rev:1,ts:Date.now()}}));""")
    dlg['answers']=['dismiss']   # ביטול = לקבל את גרסת השרת
    r=pg.evaluate("""(async()=>{ __srv.leads[2].data.notes='חדש ממכשיר אחר';
      _outbox=JSON.parse(localStorage.getItem('leadOutbox_v1')); recoverPendingSaves(); await new Promise(r=>setTimeout(r,1200)); await flushPendingSaves();
      const bk=JSON.parse(localStorage.getItem('leadConflicts_v1')||'[]');
      return {srv:__srv.leads[2].data.notes, mem:leads.find(l=>l.id===2).notes, backup:bk.length&&bk[0].local.notes, ob:Object.keys(%s).length};})()""" % OB)
    ck("F10: שחזור מבוסס גרסה ישנה לא דורס את גרסת השרת החדשה", r['srv']=='חדש ממכשיר אחר')
    ck("F10: בבחירת 'גרסת השרת' — הזיכרון מתעדכן והגרסה המקומית נשמרת בגיבוי", r['mem']=='חדש ממכשיר אחר' and r['backup']=='מקומי ישן' and r['ob']==0)
    fresh("""localStorage.setItem('leadOutbox_v1', JSON.stringify({2:{payload:{id:2,address:'רחוב 2',city:'תא',status:'חדש',notes:'שלי'},base:'2026-08-01T10:00:00.000Z',rev:1,ts:Date.now()}}));""")
    dlg['answers']=['accept']    # אישור = לשמור את שלי
    r=pg.evaluate("""(async()=>{ __srv.leads[2].data.notes='של אחר'; _outbox=JSON.parse(localStorage.getItem('leadOutbox_v1')); recoverPendingSaves();
      await new Promise(r=>setTimeout(r,1200)); await flushPendingSaves();
      return {srv:__srv.leads[2].data.notes, forced:__srv.calls.some(c=>c.includes('"F"'))};})()""")
    ck("F10: בבחירת 'שמור את שלי' — נשמר בכוונה (force), לא בטעות", r['srv']=='שלי' and r['forced'])
    # ── D07: אחרי שחזור לתור לא מוצג 'מסונכרן' ──
    fresh("""localStorage.setItem('leadOutbox_v1', JSON.stringify({3:{payload:{id:3,address:'רחוב 3',city:'תא',status:'חדש',notes:'ממתין'},base:'2026-09-03T10:00:00.000Z',rev:1,ts:Date.now()}}));""")
    r=pg.evaluate("""(async()=>{ _outbox=JSON.parse(localStorage.getItem('leadOutbox_v1')); __gate('rpc'); await loadFromSupabase(); recoverPendingSaves();
      const t=document.getElementById('syncIndicator').textContent; __open('rpc'); return t;})()""")
    ck("D07: טעינה עם שינוי שלא אושר — לא מוצג 'מסונכרן' ("+r+")", 'מסונכרן' not in r)
    # ── D08: כשל של קריאה ישנה לא דורס הצלחה של קריאה חדשה ──
    fresh()
    r=pg.evaluate("""(async()=>{ __gate('get'); __srv.fail.get=1; const old=reloadFromSupabase(true); await new Promise(r=>setTimeout(r,80));
      const g=__gates['get']; delete __gates['get'];
      await reloadFromSupabase(true);   // קריאה חדשה — אמורה להיכשל בגלל fail.get? לא: fail מוגדר לפעם אחת — נצרך ע"י החדשה
      g.rel(); await old; return document.getElementById('syncIndicator').textContent;})()""")
    # בתרחיש זה: הבקשה הישנה (אחרונה לחזור) — אסור שתציג כשל אחרי שבקשה חדשה יותר כבר הושלמה
    r2=pg.evaluate("""(async()=>{ __srv.fail.get=0; __gate('get'); const old=reloadFromSupabase(true); await new Promise(r=>setTimeout(r,80));
      const g=__gates['get']; delete __gates['get']; __srv.fail.get=0;
      await reloadFromSupabase(true); const afterNew=document.getElementById('syncIndicator').textContent;
      __srv.fail.get=1; g.rel(); await old; return {afterNew, final:document.getElementById('syncIndicator').textContent};})()""")
    ck("D08: כשל של קריאה ישנה לא מחליף הצלחה של קריאה חדשה ("+r2['final']+")", 'נכשל' not in r2['final'])
    # ── F05: אנשי קשר — נשלח רק מה שהשתנה ──
    fresh("""__srv.meta.contacts=JSON.stringify([{id:'a',name:'א',phone:'1'},{id:'b',name:'ב',phone:'2'}]);""")
    r=pg.evaluate("""(async()=>{ await loadContacts();
      __srv.meta.contacts=JSON.stringify([{id:'a',name:'א',phone:'1'},{id:'b',name:'ב',phone:'999'}]);   // מכשיר אחר שינה את ב
      const next=contacts.map(c=>c.id==='a'?{...c,phone:'111'}:c);                                           // כאן משנים את א (עם רשימה ישנה של ב)
      await persistContactsState(next);
      const s=JSON.parse(__srv.meta.contacts);
      return {sent:((__srv.lastMerge||{}).p_upserts||[]).map(c=>c.id), a:s.find(c=>c.id==='a').phone, b:s.find(c=>c.id==='b').phone, mem:contacts.find(c=>c.id==='b').phone};})()""")
    ck("F05: נשלח רק איש הקשר ששונה", r['sent']==['a'])
    ck("F05: השינוי של המכשיר האחר לא נדרס, ומוצג גם כאן", r['a']=='111' and r['b']=='999' and r['mem']=='999')
    ck("אין שגיאות JS", not errs)
    b.close()
for n,c in P: print(("  ✅ " if c else "  ❌ ")+n)
print(f"\n  עברו: {sum(1 for _,x in P if x)}/{len(P)}")
if errs: print("שגיאות:", errs[:4])
