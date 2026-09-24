# -*- coding: utf-8 -*-
# סבב 6, שלב 4: startAutoSync האמיתית (לא העתק) — שעון מבוקר של Playwright + spy על reloadFromSupabase
import os, sys
from playwright.sync_api import sync_playwright
TARGET=os.environ.get('LEADS_TARGET') or sys.argv[1]
P=[]
def ck(n,c): P.append((n,bool(c)))
with sync_playwright() as p:
    b=p.chromium.launch(); ctx=b.new_context()
    ctx.route('**://*.supabase.co/**', lambda r: r.abort()); ctx.route('**://cdn*/**', lambda r: r.abort())
    pg=ctx.new_page(); errs=[]
    pg.on('pageerror', lambda e: errs.append(str(e)[:150]) if 'supabase is not defined' not in str(e) else None)
    pg.clock.install()
    pg.goto('file://'+TARGET); pg.wait_for_timeout(800)
    pg.evaluate("""(()=>{ sb={from(){},auth:{},rpc(){}}; window.__calls=0; window.reloadFromSupabase=async()=>{ window.__calls++; };
      Object.defineProperty(document,'visibilityState',{configurable:true,get:()=>window.__vis||'visible'});
      stopAutoSync(); startAutoSync(); startAutoSync(); })()""")
    pg.clock.run_for(44000); a=pg.evaluate("window.__calls")
    pg.clock.run_for(2000);  b1=pg.evaluate("window.__calls")
    ck("startAutoSync: לא מסנכרן לפני 45 שניות", a==0)
    ck("startAutoSync: קריאה כפולה יוצרת טיימר אחד בלבד (סנכרון אחד ב-45 שניות)", b1==1)
    pg.evaluate("window.__vis='hidden'"); pg.clock.run_for(45000)
    ck("startAutoSync: לא מסנכרן כשהחלון ברקע", pg.evaluate("window.__calls")==1)
    pg.evaluate("window.__vis='visible'"); pg.clock.run_for(45000)
    ck("startAutoSync: חוזר לסנכרן כשהחלון בחזית", pg.evaluate("window.__calls")==2)
    pg.evaluate("stopAutoSync()"); pg.clock.run_for(100000)
    ck("stopAutoSync (יציאה): אין סנכרון נוסף ואין טיימר", pg.evaluate("window.__calls")==2 and pg.evaluate("window.__autoSyncTimer")==None)
    ck("אין שגיאות JS", not errs)
    b.close()
for n,c in P: print(("  ✅ " if c else "  ❌ ")+n)
print(f"\n  עברו: {sum(1 for _,x in P if x)}/{len(P)}")
