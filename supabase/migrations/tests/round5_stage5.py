# -*- coding: utf-8 -*-
# שלב 5: ייצוא ל-Excel וטעינה חזרה (הלוך-חזור). נבנה אחרי שנמצא שטעינת קובץ מיוצא
# שיבשה נתונים: "נענו: כן" → "לא", דריסת הערות, שורת סיכום כליד, וגיליון שגוי.
import os, sys, json, base64, tempfile
from playwright.sync_api import sync_playwright
TARGET=os.environ.get('LEADS_TARGET') or sys.argv[1]
HERE=os.path.dirname(os.path.abspath(__file__))
VENDOR=os.path.join(HERE,'vendor')
VMAP={'exceljs.min.js':'exceljs-4.4.0.min.js','supabase.js':'supabase-js-2.110.2.umd.js'}
def vend(route):
    u=route.request.url
    for f,pth in VMAP.items():
        if f in u:
            route.fulfill(status=200, body=open(os.path.join(VENDOR,pth),'rb').read(),
                          content_type='application/javascript', headers={'Access-Control-Allow-Origin':'*'}); return
    route.abort()
P=[]
def ck(n,c): P.append((n,bool(c)))
tmp=tempfile.mkdtemp()
seed=open(os.path.join(HERE,'fixture_big.js'),encoding='utf-8').read()
with sync_playwright() as p:
    b=p.chromium.launch(); ctx=b.new_context(accept_downloads=True); pg=ctx.new_page()
    errs=[]; pg.on('pageerror', lambda e: errs.append(str(e)[:150])); pg.on('dialog', lambda d: d.accept())
    pg.route('**://*.supabase.co/**', lambda r: r.fulfill(status=200, body='[]', content_type='application/json'))
    pg.route('**://cdnjs.cloudflare.com/**', vend); pg.route('**://cdn.jsdelivr.net/**', vend)
    pg.goto('file://'+TARGET); pg.wait_for_timeout(1500); pg.evaluate(seed)
    pg.evaluate("""(()=>{ window.saveData=function(){}; window.saveData._ps=new Set();
      window.allocIds=async n=>{window.__alloc=(window.__alloc||0)+n; const a=[];for(let i=0;i<n;i++)a.push(9000+i);return a;};
      leads[1].address='=HYPERLINK("http://evil","x")'; refresh(); })()""")
    with pg.expect_download(timeout=30000) as dl: pg.evaluate("exportExcel()")
    f0=os.path.join(tmp,'export.xlsx'); dl.value.save_as(f0)
    # הזרקת נוסחה נוטרלה בקובץ
    r=pg.evaluate("""(async(b64)=>{ const wb=new ExcelJS.Workbook(); await wb.xlsx.load(Uint8Array.from(atob(b64),c=>c.charCodeAt(0)).buffer);
      let formula=0, guarded=0; wb.worksheets.forEach(ws=>ws.eachRow(row=>row.eachCell(c=>{ if(c.formula) formula++;
        if(typeof c.value==='string' && c.value.startsWith("'=")) guarded++; })));
      return {formula, guarded, sheets:wb.worksheets.map(s=>s.name)}; })""", base64.b64encode(open(f0,'rb').read()).decode())
    ck("ייצוא: אין נוסחאות פעילות בקובץ", r['formula']==0)
    ck("ייצוא: כתובת שמתחילה ב-= נשמרה כטקסט מוגן", r['guarded']>=1)
    ck("ייצוא: קיים גיליון 'כל הלידים'", 'כל הלידים' in r['sheets'])
    DIFF="""(()=>{const B=new Map(window.__before.map(l=>[l.id,l])); const diff={}; let neu=0;
      leads.forEach(l=>{const o=B.get(l.id); if(!o){neu++;return;}
        ['date','address','city','type','source','name','status','replied','notes'].forEach(k=>{ if(String(o[k]??'')!==String(l[k]??'')) diff[k]=(diff[k]||0)+1; });});
      return {diff, neu};})()"""
    pg.evaluate("window.__before=JSON.parse(JSON.stringify(leads)); window.__alloc=0;")
    pg.set_input_files('#xlsxUploadInput', f0); pg.wait_for_timeout(3500)
    r=pg.evaluate(DIFF)
    ck("טעינת קובץ מיוצא ללא שינוי: 0 לידים חדשים (כולל שורת סיכום וכתובת עם =)", r['neu']==0 and pg.evaluate("window.__alloc||0")==0)
    ck("טעינת קובץ מיוצא ללא שינוי: אף שדה לא השתנה "+json.dumps(r['diff'],ensure_ascii=False), r['diff']=={})
    # שינוי בקובץ עצמו (ב-ExcelJS): סטטוס, תאריך כתאריך אמיתי, "תגובה?"
    b64=pg.evaluate("""(async(b64)=>{ const wb=new ExcelJS.Workbook(); await wb.xlsx.load(Uint8Array.from(atob(b64),c=>c.charCodeAt(0)).buffer);
      const ws=wb.getWorksheet('כל הלידים'); const hdr=ws.getRow(2).values.map(v=>String(v||'').trim());
      const col=h=>hdr.indexOf(h);
      let done=false;
      ws.eachRow((row,rn)=>{ if(done||rn<3) return; if(String(row.getCell(col('כתובת')).value||'').startsWith('הקסם 7')){
        row.getCell(col('סטטוס')).value='נשלחה הצעה';
        row.getCell(col('תאריך')).value=new Date(Date.UTC(2026,2,15));
        row.getCell(col('תגובה?')).value='כן'; done=true; } });
      const buf=await wb.xlsx.writeBuffer(); let s=''; new Uint8Array(buf).forEach(x=>s+=String.fromCharCode(x)); return btoa(s); })""",
      base64.b64encode(open(f0,'rb').read()).decode())
    f1=os.path.join(tmp,'export_mod.xlsx'); open(f1,'wb').write(base64.b64decode(b64))
    pg.evaluate("window.__before=JSON.parse(JSON.stringify(leads));")
    pg.set_input_files('#xlsxUploadInput', f1); pg.wait_for_timeout(3500)
    r=pg.evaluate(DIFF)
    hk=pg.evaluate("(()=>{const l=leads.find(x=>x.address.startsWith('הקסם 7')); return {s:l.status,d:l.date,r:l.replied,h:(l.history||[]).length};})()")
    ck("שינוי סטטוס בגיליון 'כל הלידים' נקלט", hk['s']=='נשלחה הצעה')
    ck("תאריך שנערך ב-Excel (תאריך אמיתי) נקלט כ-2026-03-15 (התקבל: "+str(hk["d"])+")", hk["d"]=="2026-03-15")
    ck("'תגובה?' נקרא מהעמודה הנכונה (לא 'תגובה עד')", hk['r']=='כן')
    ck("רק הליד ששונה עודכן "+json.dumps(r['diff'],ensure_ascii=False), r['neu']==0 and all(v<=1 for v in r['diff'].values()))
    ck("העדכון תועד ביומן השינויים", hk['h']>=1)
    ck("אין שגיאות JS", not errs)
    b.close()
for n,c in P: print(("  ✅ " if c else "  ❌ ")+n)
print(f"\n  עברו: {sum(1 for _,x in P if x)}/{len(P)}")
