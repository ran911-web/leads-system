# -*- coding: utf-8 -*-
# שלב 6: ייצוא PDF ומאגר פונים — עקביות עם הטבלה והדאשבורד (שמות מנורמלים, סדר מיון)
import os, sys, json
from playwright.sync_api import sync_playwright
TARGET=os.environ.get('LEADS_TARGET') or sys.argv[1]
P=[]
def ck(n,c): P.append((n,bool(c)))
with sync_playwright() as p:
    b=p.chromium.launch(); ctx=b.new_context(viewport={'width':412,'height':915})
    ctx.add_init_script("window.print=()=>{window.__printed=true;}")
    ctx.route('**://*.supabase.co/**', lambda r: r.fulfill(status=200, body='[]', content_type='application/json'))
    ctx.route('**://cdn*/**', lambda r: r.abort()); ctx.route('**://fonts.*/**', lambda r: r.abort())
    pg=ctx.new_page(); errs=[]
    pg.on('pageerror', lambda e: errs.append(str(e)[:140]) if 'supabase is not defined' not in str(e) else None)
    pg.on('dialog', lambda d: d.accept())
    pg.goto('file://'+TARGET); pg.wait_for_timeout(1300)
    pg.evaluate("""(()=>{unlockAppShell(); leads.length=0; let id=1;
      const add=(n,name,st,d)=>{for(let i=0;i<n;i++) leads.push({id:id++,address:'ר'+id,city:'תא',name,status:st,date:d,replied:'לא'});};
      add(3,'רותם מוקד','נשלחה הצעה','2026-05-01'); add(1,'אריאל יוסף','חדש','2026-01-02'); add(1,'רותם מוקד ואריאל יוסף','חדש','2026-01-01');
      add(1,'רותם','בבדיקה','2026-03-01'); add(1,'טל עזיז','חדש','2026-06-01'); add(1,'','בבדיקה','2026-02-01');
      window._callerRules={approved:{'רותם מוקד ואריאל יוסף':['רותם מוקד','אריאל יוסף'],'ירין דיגה ורותם מוקד':['ירין דיגה','רותם מוקד'],'טל עזיז ורותם מוקד':['טל עזיז','רותם מוקד'],'רותם':'רותם מוקד'},rejected:{}}; _callerCache=null;
      refresh();})()""")
    # PDF
    r=pg.evaluate("""(()=>{openPdfExport();
      const opts=[...document.querySelectorAll('#pdfNameBox input')].map(i=>i.value);
      const all=_pdfFiltered();
      const ordOk=all.every((l,i)=>i===0||STATUS_DEFINITIONS.findIndex(d=>d.name===all[i-1].status)<=STATUS_DEFINITIONS.findIndex(d=>d.name===l.status));
      document.querySelectorAll('#pdfNameBox input').forEach(i=>i.checked=(i.value==='רותם מוקד'));
      const rotem=_pdfFiltered().length;
      document.querySelectorAll('#pdfNameBox input').forEach(i=>i.checked=true);
      return {opts, n:all.length, ordOk, rotem, noJoint:!opts.some(o=>o.includes(' ו')&&o.includes('רותם מוקד ו'))};})()""")
    ck("PDF: רשימת המארגנים מנורמלת (אין שם משותף, 'רותם' אוחד)", r['noJoint'] and 'רותם' not in r['opts'] and 'אריאל יוסף' in r['opts'])
    ck("PDF: כל השמות מסומנים → כולל ליד בלי שם ("+str(r['n'])+"/8)", r['n']==8)
    ck("PDF: אותו סדר כמו הטבלה (לפי שלב בצנרת)", r['ordOk'])
    ck("PDF: סינון 'רותם מוקד' כולל משותף ו'רותם' ("+str(r['rotem'])+")", r['rotem']==5)
    with ctx.expect_page(timeout=8000) as newp: pg.evaluate("doPdfExport()")
    np=newp.value; np.wait_for_timeout(1200)
    info=np.evaluate("({rows:document.querySelectorAll('tbody tr').length, rtl:getComputedStyle(document.body).direction==='rtl', title:document.title})")
    ck("PDF: דף ההדפסה נפתח עם כל 8 הלידים, בכיוון ימין-לשמאל", info['rows']==8 and info['rtl'])
    np.close()
    # מאגר פונים
    r=pg.evaluate("""(()=>{ contacts.length=0;
      [['c1','רותם מוקד'],['c2','רותם'],['c3','אריאל יוסף'],['c4','טל עזיז']].forEach(([id,name])=>contacts.push({id,name,phone:'',email:'',company:'',notes:''}));
      document.getElementById('tab-contacts').click(); renderContacts();
      const out={}; document.querySelectorAll('.contact-name').forEach(n=>{ const name=n.childNodes[0].textContent.trim();
        out[name]={b:((n.querySelector('.contact-leads-badge')||{}).textContent||'').trim(), hint:n.textContent.includes('איש קשר כפול')}; });
      return out;})()""")
    ck("מאגר פונים: 'רותם מוקד' כולל משותף ו'רותם' (5)", r.get('רותם מוקד',{}).get('b')=='5 לידים')
    ck("מאגר פונים: 'אריאל יוסף' מקבל גם את הליד המשותף (2)", r.get('אריאל יוסף',{}).get('b')=='2 לידים')
    ck("מאגר פונים: 'רותם' מסומן כאיש קשר כפול אפשרי", r.get('רותם',{}).get('hint') and not r.get('רותם',{}).get('b'))
    ck("מאגר פונים: 'ליד אחד' בלשון תקינה", r.get('טל עזיז',{}).get('b')=='ליד אחד')
    ck("אין שגיאות JS", not errs)
    b.close()
for n,c in P: print(("  ✅ " if c else "  ❌ ")+n)
print(f"\n  עברו: {sum(1 for _,x in P if x)}/{len(P)}")
