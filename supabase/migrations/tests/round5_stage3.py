import os, sys
from playwright.sync_api import sync_playwright
TARGET=os.environ.get('LEADS_TARGET') or sys.argv[1]
HERE=os.path.dirname(os.path.abspath(__file__))
P=[]
def ck(n,c): P.append((n,bool(c)))
with sync_playwright() as p:
    b=p.chromium.launch(); ctx=b.new_context(viewport={'width':412,'height':915}); pg=ctx.new_page()
    errs=[]; pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.on('dialog', lambda d: d.dismiss())
    pg.route('**://*.supabase.co/**', lambda r: r.fulfill(status=200, body='[]', content_type='application/json'))
    pg.route('**://cdn*/**', lambda r: r.abort())
    pg.goto('file://'+TARGET); pg.wait_for_timeout(1300)
    # 10. טופס
    r=pg.evaluate("""(()=>{unlockAppShell(); localStorage.removeItem('leadDraft_v1'); openForm();
      const g=[...document.querySelectorAll('#formOverlay .form-grid input, #formOverlay .form-grid select, #formOverlay .form-grid textarea')].map(e=>e.id);
      return {noSubmit:!document.getElementById('f_submitDeadline')&&!document.getElementById('f_extendable')&&!document.getElementById('e_submitDeadline'),
              addrFirst:g.indexOf('f_address')<g.indexOf('f_city'), order:g.slice(0,4)};})()""")
    ck("10. 'מועד הגשה' ו'הארכה' הוסרו משני הטפסים", r['noSubmit'])
    ck("10. הכתובת לפני העיר ("+",".join(r['order'])+")", r['addrFirst'])
    r=pg.evaluate("""(async()=>{ window.saveData=function(){}; window.saveData._ps=new Set();
      window.allocIds=async n=>{const a=[];for(let i=0;i<n;i++)a.push(500+i);return a;};
      leads.length=0; openForm();
      document.getElementById('f_address').value='הרצל 10'; document.getElementById('f_city').value='תל אביב';
      await saveLead();
      const l=leads[0];
      const e=(openEdit(l.id), true); saveEdit(); if(window.closeEdit) closeEdit();
      return {created:leads.length, sd:('submitDeadline' in l)?l.submitDeadline:'none'};})()""")
    ck("10. יצירת ליד ועריכה עובדות בלי השדות שהוסרו", r['created']==1)
    r=pg.evaluate("""(()=>{ leads.length=0; leads.push({id:9,address:'ישן',city:'תא',status:'חדש',date:'2026-01-01',replied:'לא',submitDeadline:'2026-12-01',extendable:true});
      openEdit(9); saveEdit(); if(window.closeEdit) closeEdit(); return {sd:leads[0].submitDeadline, ex:leads[0].extendable};})()""")
    ck("10. ערכים קיימים של מועד הגשה נשמרים בעריכה", r['sd']=='2026-12-01' and r['ex']==True)
    # 11. טיוטה — הקלדה, "אין קליטה", סגירת האפליקציה
    pg.evaluate("localStorage.removeItem('leadDraft_v1'); openForm()")
    pg.fill('#f_address','סירקין 36-38'); pg.fill('#f_city','הרצליה'); pg.fill('#f_name','הורן עזיז'); pg.fill('#f_phone','0521234567')
    pg.wait_for_timeout(700)
    saved=pg.evaluate("JSON.parse(localStorage.getItem('leadDraft_v1')||'null')")
    ck("11. הטיוטה נשמרת תוך כדי הקלדה", saved and saved['v']['f_address']=='סירקין 36-38')
    pg.evaluate("window.allocIds=async()=>null; saveLead()"); pg.wait_for_timeout(300)
    ck("11. כשל שמירה (אין קליטה) — הטיוטה נשארת", pg.evaluate("!!localStorage.getItem('leadDraft_v1')"))
    # "סגירת האפליקציה" = טעינה מחדש של הדף
    pg.reload(); pg.wait_for_timeout(1300)
    r=pg.evaluate("""(()=>{unlockAppShell(); openForm();
      return {a:document.getElementById('f_address').value, c:document.getElementById('f_city').value, n:document.getElementById('f_name').value,
              ph:document.getElementById('f_phone').value, note:!!document.getElementById('_draftNote')};})()""")
    ck("11. אחרי סגירה ופתיחה — הטיוטה משוחזרת", r['a']=='סירקין 36-38' and r['c']=='הרצליה' and r['n']=='הורן עזיז' and r['ph']=='0521234567')
    ck("11. מוצגת הודעת 'שוחזרה טיוטה'", r['note'])
    r=pg.evaluate("""(async()=>{ window.saveData=function(){}; window.saveData._ps=new Set();
      window.allocIds=async n=>{const a=[];for(let i=0;i<n;i++)a.push(700+i);return a;};
      leads.length=0; await saveLead();
      return {created:leads.length, draft:localStorage.getItem('leadDraft_v1')};})()""")
    ck("11. אחרי שמירה מוצלחת — הטיוטה נמחקת", r['created']==1 and r['draft'] is None)
    r=pg.evaluate("""(()=>{openForm(); return {a:document.getElementById('f_address').value, note:!!document.getElementById('_draftNote')};})()""")
    ck("11. פתיחה הבאה — טופס נקי", r['a']=='' and not r['note'])
    pg.evaluate("closeForm()")
    pg.evaluate("openForm()"); pg.fill('#f_address','טיוטה לניקוי'); pg.wait_for_timeout(600); pg.evaluate("closeForm(); openForm()")
    pg.evaluate("document.querySelector('#_draftNote button').click()")
    r=pg.evaluate("({a:document.getElementById('f_address').value, d:localStorage.getItem('leadDraft_v1')})")
    ck("11. כפתור 'נקה' מוחק את הטיוטה", r['a']=='' and r['d'] is None)
    pg.evaluate("closeForm()")
    # 13. כפתורי חיוג / וואטסאפ הוסרו לבקשת המשתמש
    r=pg.evaluate("""(()=>{leads.length=0;
      leads.push({id:1,address:'א',city:'תא',name:'טל עזיז',phone:'052-123-4567',status:'חדש',date:'2026-05-01',replied:'לא'});
      document.querySelectorAll('#statusDropdown .st-opt input[type=checkbox]').forEach(cb=>cb.checked=true);
      document.getElementById('searchInput').value=''; refresh();
      return {none:!document.querySelector('#tableBody .qa, #tableBody a[href^="tel:"]'),
              fn:typeof _quickContact==='undefined' && typeof quickWhatsApp==='undefined',
              copy:!!document.querySelector('#row_1 .addr-copy-btn')};})()""")
    ck("13. אין כפתורי חיוג/וואטסאפ בשורה", r['none'])
    ck("13. הפונקציות שלהם הוסרו", r['fn'])
    ck("13. כפתור העתקת הכתובת נשאר", r['copy'])
    rh=pg.evaluate("Math.round([...document.querySelectorAll('#tableBody tr')].reduce((s,r)=>s+r.getBoundingClientRect().height,0)/document.querySelectorAll('#tableBody tr').length)")
    ck("13. גובה השורה נשאר קומפקטי ("+str(rh)+"px)", rh<=70)
    ctx.close(); b.close()
for n,c in P: print(("  ✅ " if c else "  ❌ ")+n)
print(f"\n  עברו: {sum(1 for _,x in P if x)}/{len(P)} | שגיאות: {[e for e in errs if 'supabase' not in e][:3]}")
