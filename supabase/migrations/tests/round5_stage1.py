import os, sys
from playwright.sync_api import sync_playwright
TARGET=os.environ.get('LEADS_TARGET') or sys.argv[1]
HERE=os.path.dirname(os.path.abspath(__file__))
P=[]
def ck(n,c): P.append((n,bool(c)))
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={'width':412,'height':915})
    errs=[]; pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.on('dialog', lambda d: d.dismiss())
    pg.route('**://*.supabase.co/**', lambda r: r.fulfill(status=200, body='[]', content_type='application/json'))
    pg.route('**://cdn*/**', lambda r: r.abort())
    pg.goto('file://'+TARGET); pg.wait_for_timeout(1300)
    # 1. XSS
    r=pg.evaluate("""(()=>{unlockAppShell(); try{localStorage.setItem('statsPeriod','all')}catch(e){}
      window.__pwned=0; leads.length=0; const bad="x');window.__pwned=1;//";
      for(let i=0;i<4;i++) leads.push({id:i+1,address:'ר'+i,city:bad,name:'n',status:'חדש',date:'2026-05-01',replied:'לא'});
      refresh(); renderAnalytics();
      const cell=document.querySelector('#anCityConv .cn.clk'); cell&&cell.click();
      const r={pwned:window.__pwned, cf:(window._cityFilter||{}).label, n:filteredLeads().length}; clearQualityFilter(); return r;})()""")
    ck("1. פרצת העיר נסגרה (הקוד לא רץ)", r['pwned']==0)
    ck("1. הלחיצה על העיר עדיין מסננת לפי העיר", r['cf']=="x');window.__pwned=1;//" and r['n']==4)
    ck("2. seedSupabase הוסרה", pg.evaluate("typeof seedSupabase==='undefined'"))
    # 3. חיפוש
    r=pg.evaluate("""(()=>{leads.length=0;
      leads.push({id:1,address:'איתמר בן אב"י 9-13',city:'ראשון לציון',name:'ירין דיגה',phone:'052-1234567',email:'yarin@mail.com',
        architect:'רון שגיא',status:'חדש',date:'2026-05-01',replied:'לא',internalNotes:[{ts:'x',text:'דיברתי עם הוועד'}]});
      leads.push({id:2,address:'הרצל 5',city:'רמת גן',name:'רותם מוקד',phone:'+972-50-7654321',status:'בבדיקה',date:'2026-05-01',replied:'לא'});
      leads.push({id:3,address:'ביאליק 2052',city:'חולון',name:'x',status:'חדש',date:'2026-05-01',replied:'לא'});
      document.querySelectorAll('#statusDropdown .st-opt input[type=checkbox]').forEach(cb=>cb.checked=true);
      const q=s=>{document.getElementById('searchInput').value=s; refresh(); return [...document.querySelectorAll('#tableBody tr[id^=row_]')].map(t=>+t.id.slice(4));};
      const o={p1:q('0521234567'),p2:q('052-1234567'),p3:q('1234567'),p4:q('0507654321'),p5:q('972507654321'),
               mail:q('yarin'),arch:q('שגיא'),note:q('הוועד'),q1:q('בן אבי'),q2:q('בן אב"י'),addrnum:q('2052'),city:q('רמת גן')};
      document.getElementById('searchInput').value=''; refresh(); return o;})()""")
    ck("3. טלפון בלי מקף", r['p1']==[1]); ck("3. טלפון עם מקף", r['p2']==[1]); ck("3. חלק מטלפון", r['p3']==[1])
    ck("3. טלפון +972 נמצא בחיפוש 050...", r['p4']==[2]); ck("3. 972... נמצא", r['p5']==[2])
    ck("3. מייל", r['mail']==[1]); ck("3. אדריכל", r['arch']==[1]); ck("3. הערה פנימית", r['note']==[1])
    ck("3. 'בן אבי' בלי גרשיים", r['q1']==[1]); ck("3. 'בן אב\"י' עם גרשיים", r['q2']==[1])
    ck("3. מספר בית (2052) עדיין נמצא בכתובת", r['addrnum']==[3]); ck("3. עיר עם רווח", r['city']==[2])
    # 5. תפריט טלפון
    r=pg.evaluate("[...document.querySelectorAll('#mobileMenuSheet .msheet-item')].map(b=>b.textContent)")
    ck("5. בתפריט הטלפון: יומן יצירה/מחיקה", any('יומן' in x for x in r)); ck("5. בתפריט הטלפון: טען מ-Excel", any('טען מ-Excel' in x for x in r))
    # 6. פונים
    r=pg.evaluate("""(()=>{leads.length=0; let id=1;
      const add=(n,name,st)=>{for(let i=0;i<n;i++) leads.push({id:id++,address:'ר'+id,city:'תא',name,status:st||'חדש',date:'2026-05-01',replied:'לא'});};
      add(58,'רותם מוקד'); add(1,'אריאל יוסף'); add(1,'ירין דיגה'); add(1,'טל עזיז'); add(3,'רותם מוקד ואריאל יוסף'); add(1,'ירין דיגה ורותם מוקד'); add(1,'טל עזיז ורותם מוקד'); add(1,'רותם');
      // ביקורת df2ce6f (V02): אין הסקה אוטומטית — ההחלטות מאושרות במפורש
      window._callerRules={approved:{'רותם מוקד ואריאל יוסף':['רותם מוקד','אריאל יוסף'],'ירין דיגה ורותם מוקד':['ירין דיגה','רותם מוקד'],'טל עזיז ורותם מוקד':['טל עזיז','רותם מוקד'],'רותם':'רותם מוקד'},rejected:{}}; _callerCache=null;
      add(2,'אמיר כספי'); add(2,'אמיר שטיינהרץ'); add(3,'אמיר');
      refresh(); renderDash();
      const g=[...document.querySelectorAll('#dashCaller .caller-grid > *')].map(x=>x.textContent.trim());
      const idx=g.findIndex(t=>t.startsWith('רותם מוקד'));
      const amir=g.findIndex(t=>t==='אמיר');
      document.getElementById('filterCaller').value='רותם מוקד'; refresh();
      const rows=filteredLeads().length;
      document.getElementById('filterCaller').value=''; refresh();
      return {rotem:g[idx+1], amirKept:amir>=0, ariel:g.some(t=>t.startsWith('אריאל יוסף')), rows,
              opts:[...document.getElementById('filterCaller').options].map(o=>o.value)};})()""")
    ck("6. רותם מוקד נספר 64 (58+3+1+1+1)", r['rotem']=='64')
    ck("6. 'אמיר' נשאר נפרד (שני אמירים)", r['amirKept'])
    ck("6. אריאל יוסף נספר מהליד המשותף (אדם קיים במערכת)", r['ariel'])
    ck("6. מסנן 'רותם מוקד' בטבלה מציג 64", r['rows']==64)
    ck("6. אין שמות משותפים ברשימת המסנן", not any(' ו' in o and 'רותם מוקד ו' in o for o in r['opts']))
    # 7. דליי גיל
    r=pg.evaluate("""(()=>{const lbl=[...document.querySelectorAll('#dashActivity .dash-row-label')].map(x=>x.textContent.trim()); return lbl;})()""")
    ck("7. דליי גיל חדשים", r==['עד 30 ימים','31–60 ימים','61–90 ימים','91–180 ימים','מעל חצי שנה'])
    b.close()
for n,c in P: print(("  ✅ " if c else "  ❌ ")+n)
print(f"\n  עברו: {sum(1 for _,x in P if x)}/{len(P)} | שגיאות: {[e for e in errs if 'supabase' not in e][:3]}")
