import os, sys
from playwright.sync_api import sync_playwright
TARGET=os.environ.get('LEADS_TARGET') or sys.argv[1]
HERE=os.path.dirname(os.path.abspath(__file__))
P=[]
def ck(n,c): P.append((n,bool(c)))
seed=open(os.path.join(HERE,'fixture_big.js'),encoding='utf-8').read()
with sync_playwright() as p:
    b=p.chromium.launch()
    for W in [412,1790]:
        pg=b.new_page(viewport={'width':W,'height':915})
        errs=[]; pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.on('dialog', lambda d: d.dismiss())
        pg.route('**://*.supabase.co/**', lambda r: r.fulfill(status=200, body='[]', content_type='application/json'))
        pg.route('**://cdn*/**', lambda r: r.abort())
        pg.goto('file://'+TARGET); pg.wait_for_timeout(1300)
        pg.evaluate("localStorage.removeItem('dashSubtab'); localStorage.removeItem('importMode');")
        pg.evaluate(seed)
        tag=f"[{W}] "
        vis=lambda sel: pg.evaluate(f"(()=>{{const e=document.querySelector('{sel}'); return !!e && e.offsetParent!==null && e.getBoundingClientRect().height>0;}})()")
        ck(tag+"14. החלק העליון מוצג בלידים", vis('#kpiGrid .kpi4'))
        # 12. דאשבורד
        pg.evaluate("document.getElementById('tab-dash').click()"); pg.wait_for_timeout(400)
        ck(tag+"14. החלק העליון לא מוצג בדאשבורד", not vis('#kpiGrid .kpi4'))
        ck(tag+"12. נפתח על 'עכשיו' עם 'דורש תשומת לב'", vis('#dashAttention') and not vis('#dashStatus'))
        h_now=pg.evaluate("document.getElementById('dashSection').scrollHeight")
        pg.evaluate("document.querySelector('#dashSection .subtab[data-st=\"dperf\"]').click()"); pg.wait_for_timeout(300)
        ck(tag+"12. 'ביצועים' מציג פונים וסטטוסים", vis('#dashCaller') and vis('#dashStatus') and not vis('#dashAttention'))
        pg.evaluate("document.querySelector('#dashSection .subtab[data-st=\"dwins\"]').click()"); pg.wait_for_timeout(300)
        ck(tag+"12. 'זכיות' מציג המרה וזכיות", vis('#dashConversion') and vis('#dashWinsYear'))
        # הלשוניות של הניתוח לא הושפעו
        pg.evaluate("document.getElementById('tab-analytics').click()"); pg.wait_for_timeout(300)
        ck(tag+"12. בניתוח עדיין מוצג 'המרות' (לא הושפע מהדאשבורד)", vis('#anIrrelReasons'))
        pg.evaluate("[...document.querySelectorAll('#analyticsSection .subtab')].find(b=>b.dataset.st==='speed').click()"); pg.wait_for_timeout(200)
        pg.evaluate("document.getElementById('tab-dash').click()"); pg.wait_for_timeout(300)
        ck(tag+"12. חזרה לדאשבורד — נשמרה לשונית 'זכיות'", vis('#dashConversion') and not vis('#dashAttention'))
        ck(tag+"12. הדאשבורד עדיין עם כרטיסים גם בניתוח ('חיזוי' נשאר)", pg.evaluate("document.getElementById('st_speed').style.display==='block'"))
        dup=pg.evaluate("[...document.querySelectorAll('#dashStats .dash-row, #dashStats div')].some(e=>e.textContent.includes('לידים פעילים סה'))")
        ck(tag+"12. השורה הכפולה 'לידים פעילים סה\"כ' הוסרה", not dup)
        ck(tag+"12. אורך 'עכשיו' ("+str(h_now)+"px)", h_now>0)
        # 15. ייבוא
        if W==1790:
            tabs=pg.evaluate("[...document.querySelectorAll('.tab')].map(t=>t.textContent.trim())")
            ck(tag+"15. לשונית ייבוא אחת ("+str(len(tabs))+" לשוניות)", sum('ייבוא' in t or 'הזנת' in t for t in tabs)==1 and not pg.evaluate("!!document.getElementById('tab-bulk')"))
            pg.evaluate("document.getElementById('tab-import').click()"); pg.wait_for_timeout(300)
            ck(tag+"15. נפתח על 'רשימת כתובות'", vis('#bulk_addresses') and pg.evaluate("document.getElementById('tab-import').classList.contains('active')"))
            pg.evaluate("document.querySelector('#bulkSection .imp-opt[data-mode=\"import\"]').click()"); pg.wait_for_timeout(300)
            ck(tag+"15. מעבר ל'טבלת לידים'", vis('#importText') and not vis('#bulk_addresses'))
            ck(tag+"15. הלשונית נשארת מסומנת", pg.evaluate("document.getElementById('tab-import').classList.contains('active')"))
            ck(tag+"15. בורר המצב מסמן 'טבלת לידים'", pg.evaluate("document.querySelector('#importSection .imp-opt.on').dataset.mode==='import'"))
            pg.evaluate("document.getElementById('tab-leads').click()"); pg.wait_for_timeout(200)
            pg.evaluate("document.getElementById('tab-import').click()"); pg.wait_for_timeout(300)
            ck(tag+"15. חזרה לייבוא זוכרת את המצב האחרון", vis('#importText'))
        ck(tag+"שגיאות JS: "+str(len([e for e in errs if 'supabase' not in e])), len([e for e in errs if 'supabase' not in e])==0)
        pg.close()
    b.close()
for n,c in P: print(("  ✅ " if c else "  ❌ ")+n)
print(f"\n  עברו: {sum(1 for _,x in P if x)}/{len(P)}")
