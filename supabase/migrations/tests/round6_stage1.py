# -*- coding: utf-8 -*-
# סבב 6, שלב 1: תיקוני ביקורת df2ce6f — לפי תנאי הקבלה בדוח
import os, sys, json
from playwright.sync_api import sync_playwright
TARGET=os.environ.get('LEADS_TARGET') or sys.argv[1]
HERE=os.path.dirname(os.path.abspath(__file__)); VENDOR=os.path.join(HERE,'vendor')
def vend(route):
    u=route.request.url
    for f,pth in {'exceljs.min.js':'exceljs-4.4.0.min.js','supabase.js':'supabase-js-2.110.2.umd.js'}.items():
        if f in u:
            route.fulfill(status=200, body=open(os.path.join(VENDOR,pth),'rb').read(), content_type='application/javascript', headers={'Access-Control-Allow-Origin':'*'}); return
    route.abort()
P=[]
def ck(n,c): P.append((n,bool(c)))
with sync_playwright() as p:
    b=p.chromium.launch(); ctx=b.new_context(viewport={'width':1400,'height':900})
    ctx.route('**://*.supabase.co/**', lambda r: r.fulfill(status=200, body='[]', content_type='application/json'))
    ctx.route('**://cdnjs.cloudflare.com/**', vend); ctx.route('**://cdn.jsdelivr.net/**', vend)
    pg=ctx.new_page(); errs=[]; dialogs=[]
    pg.on('pageerror', lambda e: errs.append(str(e)[:150]) if 'supabase is not defined' not in str(e) else None)
    state={'dlg':'accept'}
    def on_dialog(d):
        dialogs.append(d.message); (d.accept() if state['dlg']=='accept' else d.dismiss())
    pg.on('dialog', on_dialog)
    pg.goto('file://'+TARGET); pg.wait_for_timeout(1500)
    BASE="""unlockAppShell(); try{localStorage.setItem('statsPeriod','all')}catch(e){}
      window.__sv=[]; window.saveData=function(i){ window.__sv.push(i); }; window.saveData._ps=new Set();
      document.querySelectorAll('#statusDropdown .st-opt input[type=checkbox]').forEach(cb=>cb.checked=true);
      document.getElementById('searchInput').value=''; if(window.clearQualityFilter) clearQualityFilter();"""
    J=lambda js: pg.evaluate("(()=>{"+BASE+js+"})()")
    JA=lambda js: pg.evaluate("(async()=>{"+BASE+js+"})()")

    # ── V02 ──
    r=J("""leads.length=0; contacts.length=0; let id=1;
      ['דנה ויס','מורן וייס','אלעד וידר','רון ורדי','מכרז עזרה ובצרון','רותם מוקד','טל עזיז','טל עזיז ורותם מוקד']
        .forEach(n=>leads.push({id:id++,address:'א'+id,city:'תא',name:n,status:'חדש',date:'2026-05-01'}));
      window._callerRules={approved:{},rejected:{}}; _callerCache=null; const m={}; leads.forEach(l=>m[l.name]=callerNames(l));
      const sug=callerSuggestions().some(s=>s.type==='split' && s.raw==='טל עזיז ורותם מוקד');
      populateCallerFilter(); const opts=[...document.getElementById('filterCaller').options].map(o=>o.value);
      renderDash(); const dash=[...document.querySelectorAll('#dashCaller .caller-grid .cn')].map(e=>e.getAttribute('title'));
      return {m, opts, dash, sug};""")
    ck("V02: 'דנה ויס', 'מורן וייס', 'אלעד וידר', 'רון ורדי' נשארים שלמים",
       all(r['m'][n]==[n] for n in ['דנה ויס','מורן וייס','אלעד וידר','רון ורדי']))
    ck("V02: 'מכרז עזרה ובצרון' נשאר שלם", r['m']['מכרז עזרה ובצרון']==['מכרז עזרה ובצרון'])
    ck("V02: ליד משותף של שני אנשים קיימים לא מתפצל לבד (רק מוצע לאישור)", r['m']['טל עזיז ורותם מוקד']==['טל עזיז ורותם מוקד'] and r['sug'])
    ck("V02: אין שמות מומצאים במסנן ובדאשבורד", not any(x in r['opts']+r['dash'] for x in ['יס','ייס','ידר','רדי','בצרון']))
    # ── L01 ──
    r=J("""leads.length=0; leads.push({id:1,address:'א',city:'תא',name:'x',status:'נשלחה הצעה',competitor:'חברה ג',date:'2026-05-01'});
      _applyStatusChange(1,'ממתין לכנס דיירים',[]); const a=leads[0].competitor;
      _applyStatusChange(1,'התקבלה הודעת זכייה 🏆',[{key:'winCompany',label:'x',value:'עמיסף'}]); return {a, b:leads[0].competitor};""")
    ck("L01: מתחרה נשמר במעבר בין שלבים פעילים ובזכייה", r['a']=='חברה ג' and r['b']=='חברה ג')
    # ── V01 ──
    r=J("""leads.length=0; const W='התקבלה הודעת זכייה 🏆';
      leads.push({id:1,address:'א',city:'תא',status:W,date:'2026-09-01',history:[]}); leads.push({id:2,address:'ב',city:'תא',status:W,date:'2026-09-01',history:[]});
      leads.push({id:3,address:'ג',city:'תא',status:W,date:'2026-09-01',history:[]});
      window._winsToFix=[1,2,3]; openWinDateTool();
      document.querySelector('.wd-in[data-lid="1"]').value='2026-09-10'; document.querySelector('.wd-in[data-lid="2"]').value='2026-08-31';
      saveWinDates();
      const after1={w1:leads[0].winDate||'', h1:leads[0].history.length, sv:window.__sv.length, open:!!document.getElementById('_winDateModal')};
      document.querySelector('.wd-in[data-lid="2"]').value='2026-09-12'; saveWinDates();
      return {after1, w1:leads[0].winDate, w2:leads[1].winDate, w3:leads[2].winDate||'', h1:leads[0].history.length, sv:window.__sv};""")
    ck("V01: שורה מאוחרת לא תקינה — שום שינוי בזיכרון, בהיסטוריה ובשמירה", r['after1']=={'w1':'','h1':0,'sv':0,'open':True})
    ck("V01: תיקון ושמירה חוזרת — כל השינויים נשמרים פעם אחת", r['w1']=='2026-09-10' and r['w2']=='2026-09-12' and r['h1']==1 and len(r['sv'])==1 and sorted(r['sv'][0])==[1,2])
    ck("V01: ליד שלא שונה לא הושפע", r['w3']=='')
    # ── V04 + V07 ──
    r=J("""leads.length=0; const W='התקבלה הודעת זכייה 🏆';
      leads.push({id:1,address:'א',city:'תא',status:W,date:'2025-01-01',winDate:'2025-03-01',history:[]});
      _applyStatusChange(1,'נשלחה הצעה',[]); _applyStatusChange(1,W,[{key:'winCompany',label:'x',value:'עמיסף'}]);
      const d=winDateOf(leads[0]); const iso=d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');
      return {iso, today:todayIL(), hist:leads[0].history.length, wd:leads[0].winDate};""")
    ck("V04: זכייה חוזרת היא אירוע חדש (תאריך היום, התיקון הישן לא נתקע)", r['iso']==r['today'] and r['wd']=='')
    ck("V04: ההיסטוריה של הזכייה הקודמת נשמרת", r['hist']>=2)
    r=J("""leads.length=0; const W='התקבלה הודעת זכייה 🏆';
      leads.push({id:1,address:'א',city:'תא',name:'x',status:W,date:'2026-01-01',statusChangedAt:'2026-04-09',winCompany:'עמיסף',replied:'לא',history:[]});
      openEdit(1); const wd=document.getElementById('e_winDate'); const shown=!!wd && wd.value==='2026-04-09';
      wd.value='2025-12-01'; saveEdit(); const blocked=!leads[0].winDate;
      wd.value='2026-03-15'; saveEdit(); const w1=leads[0].winDate;
      if(window.closeEdit) closeEdit();
      openEdit(1); const again=document.getElementById('e_winDate').value; document.getElementById('e_winDate').value='2026-03-20'; saveEdit(); if(window.closeEdit) closeEdit();
      return {shown, blocked, w1, again, w2:leads[0].winDate, hist:leads[0].history.filter(h=>h.changes.some(c=>c.field==='תאריך זכייה')).length};""")
    ck("V07: בטופס העריכה יש תאריך זכייה (ממולא)", r['shown'])
    ck("V07: תאריך לפני הקבלה נחסם", r['blocked'])
    ck("V07: תיקון ותיקון חוזר דרך הטופס, מתועדים", r['w1']=='2026-03-15' and r['again']=='2026-03-15' and r['w2']=='2026-03-20' and r['hist']==2)
    # ── V05 ──
    r=J("""leads.length=0; leads.push({id:1,address:'הרצל 5',city:'תא',name:'x',phone:'0541234567',status:'חדש',date:'2026-05-01'});
      leads.push({id:2,address:'ביאליק 054',city:'תא',name:'y',status:'חדש',date:'2026-05-01'});
      const q=s=>{document.getElementById('searchInput').value=s; return filteredLeads().map(l=>l.id);};
      const o={a:q('054 1234567'),b:q('(054) 123-4567'),c:q('+972 54 123 4567'),d:q('054-1234567'),e:q('הרצל 5'),f:q('1234567')};
      document.getElementById('searchInput').value=''; return o;""")
    ck("V05: '054 1234567', '(054) 123-4567', '+972 54 123 4567', '054-1234567' מוצאים",
       r['a']==[1] and r['b']==[1] and r['c']==[1] and r['d']==[1])
    ck("V05: חיפוש מילולי וחלקי לא נשבר", r['e']==[1] and r['f']==[1])
    # ── A01 ──
    r=J("""leads.length=0; const W='התקבלה הודעת זכייה 🏆';
      for(let i=1;i<=5;i++) leads.push({id:i,address:'ז'+i,city:'תא',status:W,date:'2026-08-01',statusChangedAt:'2026-09-10',history:[]});
      renderWinsMonthly(); const el=document.getElementById('anWinsMonthly');
      const tot=[...el.querySelectorAll('.wm-t')].map(t=>t.textContent); const warn=el.textContent.includes('5 זכיות רשומות ב-10.9.2026');
      markWinsUnknown('2026-09-10'); renderWinsMonthly();
      const el2=document.getElementById('anWinsMonthly').textContent;
      return {tot, warn, marked:leads.every(l=>l.winDateUnknown), after:el2.includes('5 זכיות בתאריך לא ידוע'), sv:window.__sv};""")
    ck("A01: 5 זכיות אמיתיות באותו יום נספרות (לא מושמטות לפי השערה)", r['tot']==['5'])
    ck("A01: מוצגת בקשת בירור, לא הסתרה", r['warn'])
    ck("A01: סימון מפורש בלבד מוציא אותן מהפילוח, ונשמר", r['marked'] and r['after'] and len(r['sv'])==1)
    # ── A03 ──
    r=J("""leads.length=0; for(let i=0;i<3;i++) leads.push({id:i+1,address:'א'+i,city:'ראשל"צ',name:'x',status:'חדש',date:'2026-05-01'});
      leads.push({id:9,address:'ב',city:'ראשון לציון',name:'x',status:'חדש',date:'2026-05-01'});
      renderCityConversion(); const card=+[...document.querySelectorAll('#anCityConv .city-grid > *')][7].textContent;
      openCityLeads('ראשון לציון'); const n=filteredLeads().length; const banner=(document.getElementById('_qualityBanner')||{}).textContent||'';
      clearQualityFilter(); return {card, n, banner};""")
    ck("A03: לחיצה על עיר מאוחדת מציגה את כל לידיה (4), כמו בכרטיס", r['n']==4 and r['card']==4 and 'מציג 4' in r['banner'])
    # ── D05 ──
    ck("D05: אין הבטחת הצפנה בהודעת היציאה", pg.evaluate("!secureLogout.toString().includes('יישמרו מוצפנים') && secureLogout.toString().includes('(לא מוצפנים)')"))
    # ── N04 ──
    r=JA("""leads.length=0; window.allocIds=async n=>{const a=[];for(let i=0;i<n;i++)a.push(500+i);return a;};
      document.getElementById('importText').value='01/05/2026,,חיפה,תמ"א 38/2,וואטסאפ,x,חדש,\\n01/05/2026,הרצל 3,חיפה,תמ"א 38/2,וואטסאפ,x,חדש,';
      const d=document.getElementById('importDelimiter'); if(d) d.value=',';
      await importLeads(); await new Promise(r=>setTimeout(r,300));
      return {n:leads.length, addr:leads.map(l=>l.address)};""")
    ck("N04: שורה בלי כתובת לא יוצרת ליד (רק השורה התקינה)", r['n']==1 and r['addr']==['הרצל 3'])
    # ── N06 ──
    r=JA("""leads.length=0; openForm();
      document.getElementById('f_address').value='הרצל 10'; document.getElementById('f_city').value='תא';
      document.getElementById('f_email').value='ok@mail.com';
      window.allocIds=async n=>{ document.getElementById('f_email').value='not-an-email'; document.getElementById('f_name').value='שונה'; return [700]; };
      await saveLead(); return {email:leads[0]&&leads[0].email, name:leads[0]&&leads[0].name};""")
    ck("N06: שדות שהשתנו בזמן ההמתנה לא נכנסים לליד (נשמר המאומת)", r['email']=='ok@mail.com' and r['name']=='')
    # ── I01 ──
    r=JA("""leads.length=0; document.getElementById('bulk_addresses').value='הרצל 1, תל אביב\\nביאליק 2, חיפה';
      document.getElementById('bulk_name').value='x';
      window.allocIds=async n=>{ await new Promise(r=>setTimeout(r,250)); const a=[];for(let i=0;i<n;i++)a.push(800+i+(window.__k=(window.__k||0)+10));return a;};
      await Promise.all([bulkImport(), bulkImport()]); await new Promise(r=>setTimeout(r,400));
      return {n:leads.length};""")
    ck("I01: לחיצה כפולה בייבוא כתובות יוצרת כל כתובת פעם אחת", r['n']==2)
    b.close()
    # ── V03 / V06 / D09 — דף נפרד ──
    b=p.chromium.launch(); ctx=b.new_context(viewport={'width':412,'height':915})
    ctx.route('**://*.supabase.co/**', lambda r: r.fulfill(status=200, body='[]', content_type='application/json'))
    ctx.route('**://cdn*/**', lambda r: r.abort())
    pg=ctx.new_page(); pg.on('dialog', on_dialog)
    pg.on('pageerror', lambda e: errs.append(str(e)[:150]) if 'supabase is not defined' not in str(e) else None)
    pg.goto('file://'+TARGET); pg.wait_for_timeout(1300)
    pg.evaluate("unlockAppShell(); window.__authUserId='u1'; localStorage.removeItem('leadDraft_v1');")
    pg.evaluate("openForm()"); pg.fill('#f_address','כתובת ישנה'); pg.wait_for_timeout(600); pg.evaluate("closeForm()")
    pg.evaluate("openForm()"); pg.fill('#f_address','כתובת חדשה'); pg.evaluate("closeForm()")      # סגירה מיד (<400ms)
    pg.wait_for_timeout(700)
    pg.evaluate("openForm()")
    ck("V03: הקלדה וסגירה מהירה — נשמרת הכתובת החדשה", pg.evaluate("document.getElementById('f_address').value")=='כתובת חדשה')
    pg.fill('#f_address','בEscape'); pg.keyboard.press('Escape'); pg.evaluate("openForm()")
    ck("V03: Escape שומר טיוטה", pg.evaluate("document.getElementById('f_address').value")=='בEscape')
    pg.fill('#f_address','מחוץ'); pg.evaluate("closeFormOutside({target:document.getElementById('formOverlay')})"); pg.evaluate("openForm()")
    ck("V03: לחיצה מחוץ לטופס שומרת טיוטה", pg.evaluate("document.getElementById('f_address').value")=='מחוץ')
    pg.fill('#f_address','לניקוי'); pg.evaluate("clearLeadDraft()"); pg.wait_for_timeout(700)
    ck("V03: טיימר ישן לא יוצר מחדש טיוטה שנמחקה במכוון", pg.evaluate("localStorage.getItem('leadDraft_v1')") is None)
    pg.evaluate("closeForm()")
    ck("V06: טיוטה של משתמש אחר לא משוחזרת", pg.evaluate("""(()=>{ localStorage.setItem('leadDraft_v1',JSON.stringify({v:{f_address:'של אחר'},ts:Date.now(),u:'u2'}));
        openForm(); const v=document.getElementById('f_address').value; closeForm(); localStorage.removeItem('leadDraft_v1'); return v!=='של אחר'; })()"""))
    # יציאה עם טיוטה → אזהרה מפורשת; ביטול משאיר
    pg.evaluate("localStorage.setItem('leadDraft_v1',JSON.stringify({v:{f_address:'טיוטה'},ts:Date.now(),u:'u1'})); window._syncBeforeLogout=async()=>true;")
    dialogs.clear(); state['dlg']='sequence'
    seq=['accept','dismiss']
    def on_seq(d):
        dialogs.append(d.message); (d.accept() if (seq.pop(0) if seq else 'dismiss')=='accept' else d.dismiss())
    pg.remove_listener('dialog', on_dialog); pg.on('dialog', on_seq)
    pg.evaluate("secureLogout(false)"); pg.wait_for_timeout(500)
    ck("V06: ביציאה עם טיוטה מוצגת אזהרה מפורשת", any('טיוטת ליד' in m for m in dialogs))
    ck("V06: ביטול באזהרה — הטיוטה נשארת והמשתמש מחובר", pg.evaluate("!!localStorage.getItem('leadDraft_v1')"))
    ck("V06: יציאה אוטומטית (חוסר פעילות) לא מוחקת טיוטה", pg.evaluate("!_wipeAndLogout.toString().includes(\"'leadDraft_v1'\")"))
    # D09: יציאה בזמן ה-GET של כניסה ראשונית
    r=pg.evaluate("""(async()=>{ showLoginScreen(); leads.length=0;
      window.initSupabase=()=>{};
      let release; const gate=new Promise(r=>release=r);
      window.sb={auth:{getSession:async()=>({data:{session:{}}}), getUser:async()=>({data:{user:{id:'u1'}},error:null})},
        from:()=>{ const ch=new Proxy(function(){},{get:(t,k)=>k==='then'?((res,rej)=>gate.then(()=>res({data:[{id:1,data:{address:'סודי',city:'תא',status:'חדש'},updated_at:'x'}],error:null}))):(()=>ch), apply:()=>ch}); return ch; }};
      const p=checkSession();
      await new Promise(r=>setTimeout(r,50));
      showLoginScreen();                // אירוע יציאה בזמן שה-GET מושהה
      release(); await p; await new Promise(r=>setTimeout(r,100));
      return {locked:getComputedStyle(document.getElementById('loginScreen')).display!=='none', leak:leads.some(l=>l.address==='סודי')};})()""")
    ck("D09: יציאה בזמן טעינת כניסה — הממשק נשאר נעול", r['locked'])
    ck("D09: התשובה הישנה לא הוחלה לזיכרון", not r['leak'])
    ck("אין שגיאות JS", not errs)
    b.close()
for n,c in P: print(("  ✅ " if c else "  ❌ ")+n)
print(f"\n  עברו: {sum(1 for _,x in P if x)}/{len(P)}")
if errs: print("שגיאות:", errs[:3])
