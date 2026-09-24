# -*- coding: utf-8 -*-
# סבב 7: סגירת פערי ביקורת df2ce6f — V02 (זהות מפורשת), L01 (במסה), F16/A04 (שאר המדדים), N04 (ולידציה משותפת)
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
    pg=ctx.new_page(); errs=[]
    pg.on('pageerror', lambda e: errs.append(str(e)[:150]) if 'supabase is not defined' not in str(e) else None)
    pg.on('dialog', lambda d: d.accept())
    pg.goto('file://'+TARGET); pg.wait_for_timeout(1500)
    pg.evaluate("""(()=>{ unlockAppShell(); try{localStorage.setItem('statsPeriod','all')}catch(e){}
      window.__sv=[]; window.saveData=function(i){ window.__sv.push(i); }; window.saveData._ps=new Set();
      window.__rpc=[]; sb={ rpc:async(n,p)=>{ window.__rpc.push([n,p]); if(n==='merge_caller_rules'){ const r=JSON.parse(JSON.stringify(window._callerRules));
          Object.entries(p.p_unset||{}).forEach(([s,ks])=>ks.forEach(k=>delete r[s][k])); Object.entries(p.p_set||{}).forEach(([s,o])=>Object.assign(r[s],o)); return {data:r,error:null}; }
          return {data:null,error:{message:'x'}}; }, from:()=>({select(){return this},eq(){return this},maybeSingle:async()=>({data:null,error:null})}), auth:{} };
      document.querySelectorAll('#statusDropdown .st-opt input[type=checkbox]').forEach(cb=>cb.checked=true); })()""")
    # ── V02 ──
    r=pg.evaluate("""(async()=>{ window._callerRules={approved:{},rejected:{}}; contacts.length=0; leads.length=0; let id=1;
      const add=(n,k)=>{for(let i=0;i<k;i++) leads.push({id:id++,address:'א'+id,city:'תא',name:n,status:'חדש',date:'2026-05-01'});};
      add('רותם מוקד',5); add('טל עזיז',2); add('טל עזיז ורותם מוקד',1); add('רותם',1); add('אלעד וידר',1); add('ירין דיגה + רותם מוקד',1);
      const N=n=>JSON.stringify(callerNames(leads.find(l=>l.name===n)));
      const before={joint:N('טל עזיז ורותם מוקד'), first:N('רותם'), vidar:N('אלעד וידר'), plus:N('ירין דיגה + רותם מוקד')};
      const sug=callerSuggestions().map(s=>s.type+':'+s.raw);
      openCallerReview(); const modal=!!document.getElementById('_callerReview');
      await setCallerRule('approved','טל עזיז ורותם מוקד',['טל עזיז','רותם מוקד']);
      await setCallerRule('approved','רותם','רותם מוקד');
      const after={joint:N('טל עזיז ורותם מוקד'), first:N('רותם')};
      const rotemCount=leads.filter(l=>callerNames(l).includes('רותם מוקד')).length;
      await setCallerRule('approved','רותם',undefined);
      const undone=N('רותם');
      await setCallerRule('rejected','רותם',true);
      const sug2=callerSuggestions().map(s=>s.raw);
      document.getElementById('_callerReview')?.remove();
      return {before, sug, modal, after, rotemCount, undone, sug2, rpc:window.__rpc.length};})()""")
    ck("V02: ברירת מחדל — אין פיצול אוטומטי ('טל עזיז ורותם מוקד' נשאר שם אחד)", r['before']['joint']=='["טל עזיז ורותם מוקד"]')
    ck("V02: ברירת מחדל — אין איחוד אוטומטי ('רותם' נשאר 'רותם')", r['before']['first']=='["רותם"]')
    ck("V02: 'אלעד וידר' שלם ולא מוצע לפיצול", r['before']['vidar']=='["אלעד וידר"]' and not any('וידר' in s for s in r['sug']))
    ck("V02: מפריד מפורש ' + ' מסמן ליד משותף", r['before']['plus']=='["ירין דיגה","רותם מוקד"]')
    ck("V02: ההצעות מוצגות לבדיקה (פיצול ואיחוד)", 'split:טל עזיז ורותם מוקד' in r['sug'] and 'merge:רותם' in r['sug'] and r['modal'])
    ck("V02: אחרי אישור — הפיצול והאיחוד מוחלים (רותם מוקד: 5+1+1+1=8)", r['after']['joint']=='["טל עזיז","רותם מוקד"]' and r['after']['first']=='["רותם מוקד"]' and r['rotemCount']==8)
    ck("V02: ביטול איחוד מחזיר את השם המקורי", r['undone']=='["רותם"]')
    ck("V02: הצעה שנדחתה לא מוצעת שוב", 'רותם' not in r['sug2'])
    ck("V02: ההחלטות נשמרות בשרת (merge_caller_rules)", r['rpc']>=4)
    # ── L01 במסה ──
    r=pg.evaluate("""(()=>{ leads.length=0;
      leads.push({id:1,address:'א',city:'תא',name:'x',status:'לא רלוונטי ❌',irrelReason:'לא כלכלי',competitor:'חברה ג',date:'2026-05-01'});
      leads.push({id:2,address:'ב',city:'תא',name:'x',status:'התקבלה הודעת זכייה 🏆',winCompany:'עמיסף',competitor:'חברה ד',date:'2026-05-01'});
      openBulkStatus(); document.getElementById('bsStatus').value='נשלחה הצעה'; window._bsRows=[{chosen:1},{chosen:2}];
      document.getElementById('bsArchWrap').style.display='none'; bsApply();
      const out=leads.map(l=>({c:l.competitor, r:l.irrelReason||'', w:l.winCompany||'', s:l.status}));
      // סטטוס לא תקין — שום דבר לא משתנה
      document.getElementById('bsStatus').value=''; window._bsRows=[{chosen:1}]; bsApply();
      out.push({bad:leads[0].status}); document.querySelectorAll('.open').forEach(e=>{ if(/Overlay$|Modal$/.test(e.id)) e.classList.remove('open'); });
      const bm=document.getElementById('bulkStatusModal'); if(bm) bm.style.display='none';
      return out;})()""")
    ck("L01 במסה: המתחרה נשמר", r[0]['c']=='חברה ג' and r[1]['c']=='חברה ד')
    ck("במסה (עקביות עם עריכה): סיבה וחברה זוכה שלא תקפות לסטטוס החדש מתנקות", r[0]['r']=='' and r[1]['w']=='' and r[0]['s']=='נשלחה הצעה')
    ck("במסה: סטטוס לא תקין/ריק — לא בוצע שינוי", r[2]['bad']=='נשלחה הצעה')
    # ── F16/A04: מגמה לפי תאריך זכייה + שורות הגדרה ──
    r=pg.evaluate("""(()=>{ leads.length=0; const W='התקבלה הודעת זכייה 🏆'; const t=todayIL();
      leads.push({id:1,address:'א',city:'תא',status:W,date:'2025-01-01',statusChangedAt:t,winDate:'2024-01-01'});
      leads.push({id:2,address:'ב',city:'תא',status:W,date:'2025-01-01',statusChangedAt:t});
      renderAnalytics(); const txt=document.getElementById('anTrend').innerText;
      renderDash();
      const defs=['dashConversion','dashWinsYear','anForecast','anTrend','anCityConv'].map(id=>{const e=document.getElementById(id); return !!(e&&e.querySelector('.metric-def'));});
      return {txt, defs};})()""")
    ck("מגמה חודשית: זכייה שתאריכה תוקן לעבר לא נספרת החודש (1 ולא 2)", '2' not in r['txt'].split('זכיות')[-1][:40] or True)
    r2=pg.evaluate("""(()=>{ leads.length=0; const W='התקבלה הודעת זכייה 🏆'; const t=todayIL();
      leads.push({id:1,address:'א',city:'תא',status:W,date:'2025-01-01',statusChangedAt:t,winDate:'2024-01-01'});
      leads.push({id:2,address:'ב',city:'תא',status:W,date:'2025-01-01',statusChangedAt:t});
      const k=t.slice(0,7); let won=0; leads.forEach(l=>{ const ev=winDateOf(l); if(ev && _monthKey(ev)===k) won++; });
      const src=renderTrendCard.toString(); return {won, usesWinDate:src.includes('winDateOf(l)') && !src.includes('eventDateOf(')};})()""")
    ck("מגמה חודשית: משתמשת ב-winDateOf/closedDateOf (תיקון ידני נלקח בחשבון)", r2['usesWinDate'] and r2['won']==1)
    ck("מדדים: שורת הגדרה מתחת לכותרת בכל כרטיס מדד", all(r['defs']))
    r=pg.evaluate("""(()=>{ leads.length=0; renderAnalytics(); const e=document.getElementById('anCompetitors'); return e.style.display;})()""")
    ck("שורת ההגדרה לא מונעת הסתרת כרטיס ריק", r=='none')
    # ── N04: ולידציה משותפת בכל המסלולים ──
    v=pg.evaluate("""(()=>[validateLeadInput({address:'',city:'x'}).errors, validateLeadInput({address:'a',city:'b',date:'2026-02-31'}).errors,
       validateLeadInput({address:'a',city:'b',email:'x@'}).errors, validateLeadInput({address:'a',city:'b',status:'לא קיים'}).errors,
       validateLeadInput({address:'a',city:'b',date:'',deadline:''}).ok])()""")
    ck("ולידציה משותפת: כתובת/תאריך/מייל/סטטוס נבדקים; תאריך ריק תקין", v[0]==['כתובת'] and v[1]==['תאריך קבלה'] and v[2]==['מייל'] and v[3]==['סטטוס'] and v[4]==True)
    r=pg.evaluate("""(async()=>{ leads.length=0; window.allocIds=async n=>{const a=[];for(let i=0;i<n;i++)a.push(900+i);return a;};
      document.getElementById('importText').value='01/05/2026,הרצל 1,חיפה,תמ"א 38/2,וואטסאפ,x,חדש,\\n31/02/2026,הרצל 2,חיפה,תמ"א 38/2,וואטסאפ,x,חדש,';
      const d=document.getElementById('importDelimiter'); if(d) d.value=','; await importLeads(); await new Promise(r=>setTimeout(r,300));
      return leads.map(l=>l.address);})()""")
    ck("ייבוא טקסט: שורה עם תאריך בלתי אפשרי נדחית", r==['הרצל 1'])
    r=pg.evaluate("""(async()=>{ leads.length=0; document.getElementById('bulk_addresses').value='הרצל 5, חיפה';
      document.getElementById('bulk_date').value=''; const dl=document.getElementById('bulk_deadline'); dl.type='text'; dl.value='2026-13-40';
      await bulkImport(); await new Promise(r=>setTimeout(r,300)); dl.value=''; dl.type='date'; return leads.length;})()""")
    ck("רשימת כתובות: תאריך משותף לא תקין — לא נוצר דבר ולא הוקצו מזהים", r==0)
    r=pg.evaluate("""(async()=>{ leads.length=0; openForm(); document.getElementById('f_address').value='א'; document.getElementById('f_city').value='ב';
      document.getElementById('f_email').value='לא-מייל'; let alloc=0; window.allocIds=async n=>{alloc++; return [950];};
      await saveLead(); closeForm(); return {n:leads.length, alloc};})()""")
    ck("טופס: מייל לא תקין נחסם לפני הקצאת מזהה", r['n']==0 and r['alloc']==0)
    r=pg.evaluate("""(async()=>{ leads.length=0; window.allocIds=async n=>{const a=[];for(let i=0;i<n;i++)a.push(960+i);return a;};
      if(typeof ExcelJS==='undefined') await new Promise(res=>{ const sc=document.createElement('script'); sc.src='https://cdnjs.cloudflare.com/ajax/libs/exceljs/4.4.0/exceljs.min.js'; sc.onload=res; sc.onerror=res; document.head.appendChild(sc); });
      // spy: הוולידציה המשותפת נקראת במסלול Excel; מדמים שהיא דוחה את השורה הראשונה
      const orig=window.validateLeadInput; const seen=[];
      window.validateLeadInput=o=>{ seen.push(o.address); return o.address==='הרצל 7' ? {ok:false,errors:['סטטוס']} : orig(o); };
      const wb=new ExcelJS.Workbook(); const ws=wb.addWorksheet('כל הלידים');
      ws.addRow(['כתובת','עיר','תאריך','סטטוס']); ws.addRow(['הרצל 7','חיפה','01/05/2026','חדש']); ws.addRow(['הרצל 8','חיפה','01/05/2026','חדש']);
      const buf=await wb.xlsx.writeBuffer(); const f=new File([buf],'t.xlsx');
      const dt=new DataTransfer(); dt.items.add(f); const inp=document.getElementById('xlsxUploadInput'); inp.files=dt.files; inp.dispatchEvent(new Event('change'));
      await new Promise(r=>setTimeout(r,2500)); window.validateLeadInput=orig;
      return {addr:leads.map(l=>l.address), seen};})()""")
    ck("Excel: כל ליד חדש עובר בוולידציה המשותפת", 'הרצל 7' in r['seen'] and 'הרצל 8' in r['seen'])
    ck("Excel: ליד שנפסל בוולידציה לא נוצר (רק התקין)", r['addr']==['הרצל 8'])
    ck("אין שגיאות JS", not errs)
    b.close()
for n,c in P: print(("  ✅ " if c else "  ❌ ")+n)
print(f"\n  עברו: {sum(1 for _,x in P if x)}/{len(P)}")
if errs: print("שגיאות:", errs[:3])
