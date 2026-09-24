# -*- coding: utf-8 -*-
# סבב 6, שלב 2: הגדרות סטטיסטיקה (F16, A04, N07, A05) — לפי תרחישי הביקורת df2ce6f
import os, sys, re
from playwright.sync_api import sync_playwright
TARGET=os.environ.get('LEADS_TARGET') or sys.argv[1]
P=[]
def ck(n,c): P.append((n,bool(c)))
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={'width':1400,'height':900}); errs=[]
    pg.on('pageerror', lambda e: errs.append(str(e)[:150]) if 'supabase is not defined' not in str(e) else None)
    pg.route('**://*.supabase.co/**', lambda r: r.fulfill(status=200, body='[]', content_type='application/json'))
    pg.route('**://cdn*/**', lambda r: r.abort())
    pg.goto('file://'+TARGET); pg.wait_for_timeout(1300)
    pg.evaluate("unlockAppShell(); try{localStorage.setItem('statsPeriod','all')}catch(e){}")
    W="'התקבלה הודעת זכייה 🏆'"
    # F16: ליד חדש אחד השנה + 3 זכיות השנה בלידים מהשנה הקודמת
    r=pg.evaluate("""(()=>{ const W=%s; leads.length=0;
      leads.push({id:1,address:'א',city:'תא',status:'חדש',date:'2026-02-01'});
      for(let i=0;i<3;i++) leads.push({id:10+i,address:'ז'+i,city:'תא',status:W,date:'2025-06-01',statusChangedAt:'2026-03-01'});
      renderAnalytics(); const el=document.getElementById('anConversion');
      const ws=[...el.querySelectorAll('[style*="width"]')].map(e=>parseFloat(e.style.width)).filter(x=>!isNaN(x));
      return {ws, txt:el.innerText.replace(/\\s+/g,' ')};})()""" % W)
    ck("F16: אין רוחב מעל 100% או שלילי ("+str(r['ws'])+")", all(0<=w<=100 for w in r['ws']))
    ck("F16: 2026 מציג לידים שהתקבלו (1) בנפרד מזכיות השנה (3)", 'לידים שהתקבלו: 1' in r['txt'] and '3 זכיות' in r['txt'])
    ck("F16: מוצגת הגדרת המדד", 'לפי שנת קבלה' in r['txt'])
    # שנת זכייה בלי לידים חדשים מופיעה
    r=pg.evaluate("""(()=>{ const W=%s; leads.length=0;
      leads.push({id:1,address:'א',city:'תא',status:W,date:'2024-05-01',statusChangedAt:'2025-02-01'});
      renderAnalytics(); return document.getElementById('anConversion').innerText;})()""" % W)
    ck("F16: שנת זכייה שאין בה לידים חדשים מופיעה (2025)", '2025' in r)
    # A04: ליד מ-2025 שזכה החודש — בבחירת "החודש" שני הכרטיסים מסכימים
    r=pg.evaluate("""(()=>{ const W=%s; leads.length=0; const t=todayIL();
      leads.push({id:1,address:'א',city:'תא',status:W,date:'2025-03-01',statusChangedAt:t,winCompany:'עמיסף'});
      setPeriod('month'); renderDash();
      const conv=document.getElementById('dashConversion').innerText, yr=document.getElementById('dashWinsYear').innerText;
      setPeriod('all'); return {conv, yr};})()""" % W)
    ck("A04: כרטיס ההמרה סופר את הזכייה החודשית", '1 זכיות' in r['conv'])
    ck("A04: 'זכיות לפי שנה' מסכים (לא 'אין זכיות')", 'אין זכיות' not in r['yr'] and re.search(r'סה"כ זכיות:\s*1', r['yr']))
    # A04: תאריך זכייה שתוקן ידנית משפיע גם על כרטיס ההמרה
    r=pg.evaluate("""(()=>{ const W=%s; leads.length=0; const t=todayIL();
      leads.push({id:1,address:'א',city:'תא',status:W,date:'2024-03-01',statusChangedAt:t,winDate:'2024-06-01'});
      setPeriod('month'); renderDash(); const conv=document.getElementById('dashConversion').innerText; setPeriod('all'); return conv;})()""" % W)
    ck("A04: זכייה שתאריכה תוקן לעבר לא נספרת 'החודש'", '1 זכיות' not in r)
    # N07
    r=pg.evaluate("""(()=>{ leads.length=0;
      leads.push({id:1,address:'א',city:'תא',status:'לא רלוונטי ❌',irrelReason:'הלך למתחרה',competitor:'Company A, Company B',date:'2026-05-01'});
      leads.push({id:2,address:'ב',city:'תא',status:'לא רלוונטי ❌',irrelReason:'הלך למתחרה',competitor:'Company A',date:'2026-05-01'});
      leads.push({id:3,address:'ג',city:'תא',status:'לא רלוונטי ❌',irrelReason:'לא כלכלי',competitor:'Company B',date:'2026-05-01'});
      renderAnalytics(); const cells=[...document.querySelectorAll('#anCompetitors div[style*="grid"] > div')].map(e=>e.textContent.trim());
      const row=n=>{const i=cells.indexOf(n); return cells.slice(i+1,i+6);}; return {A:row('Company A'),B:row('Company B')};})()""")
    # עמודות: עסקאות, ניצחנו, הפסדנו למתחרה, הפסד-זוכה לא ידוע, נסגרו מסיבה אחרת
    ck("N07: הפסד עם שני מתחרים לא מיוחס לאף אחד כהפסד ודאי", r['A'][2]=='1' and r['B'][2]=='0')
    ck("N07: נספר כ'זוכה לא ידוע' אצל שניהם", r['A'][3]=='1' and r['B'][3]=='1')
    ck("N07: 'לא כלכלי' לא נספר כהפסד למתחרה", r['B'][4]=='1')
    # A05
    r=pg.evaluate("""(()=>{ window._auditRows=Array.from({length:200},(_,i)=>({lead_id:i,action:'created',at:'2026-05-01T10:00:00Z',address:'x',city:'y'}));
      window._auditHasMore=true; try{ _auditRows=window._auditRows; _auditHasMore=true; }catch(e){}
      const ov=document.getElementById('auditOverlay'); if(ov) ov.classList.add('open');
      renderAuditLog('deleted'); return document.getElementById('auditBody').innerHTML;})()""")
    ck("A05: יומן מסונן בלי התאמות — כפתור 'טען עוד' נשאר", 'loadAuditPage()' in r and 'אין רשומות מתאימות' in r)
    ck("אין שגיאות JS", not errs)
    b.close()
for n,c in P: print(("  ✅ " if c else "  ❌ ")+n)
print(f"\n  עברו: {sum(1 for _,x in P if x)}/{len(P)}")
if errs: print("שגיאות:", errs[:3])
