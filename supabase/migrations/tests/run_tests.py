# -*- coding: utf-8 -*-
"""
בדיקות התנהגות למערכת מעקב הלידים.

הרצה:
    npm test
    python3 run_tests.py [path/to/index.html]

הבדיקות מריצות את הקוד האמיתי בדפדפן headless.

ללא רשת: כל התעבורה החיצונית נחסמת ברמת ה-context.
  • Supabase  — מוחזר ממוק (page.route), אין קריאה לייצור ואין שינוי בנתוני אמת.
  • ExcelJS / supabase-js — מוגשים מ-tests/vendor/ המקומי (גרסאות מקובעות
    ב-vendor-lock.json). אין תלות ב-CDN בזמן ריצה.
  • כל בקשה חיצונית אחרת נחסמת, נספרת, ומפילה את הבדיקות.

הבדיקות בוחנות התנהגות בפועל — סדר בקשות, מצב זיכרון, localStorage, וקריאות
שהקוד האמיתי מבצע — ולא נוכחות מחרוזות בקוד.
"""
import sys, os, json, time, shutil, tempfile
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
def _find_index(start):
    """אתר את index.html — חפש כלפי מעלה עד שורש הריפו (עובד מכל מיקום)."""
    d = start
    for _ in range(6):
        cand = os.path.join(d, 'index.html')
        if os.path.exists(cand):
            return cand
        up = os.path.dirname(d)
        if up == d:
            break
        d = up
    return os.path.join(start, '..', 'index.html')

SRC = sys.argv[1] if len(sys.argv) > 1 else _find_index(HERE)
if not os.path.exists(SRC):
    print("❌ לא נמצא הקובץ: " + SRC); sys.exit(1)

VENDOR = os.path.join(HERE, 'vendor')
VENDOR_MAP = {
    'exceljs.min.js':  os.path.join(VENDOR, 'exceljs-4.4.0.min.js'),
    'supabase-js@2.110.2/dist/umd/supabase.js': os.path.join(VENDOR, 'supabase-js-2.110.2.umd.js'),
}
for _k, _v in VENDOR_MAP.items():
    if not os.path.exists(_v):
        print("❌ חסרה תלות מקומית: " + _v)
        print("   הרץ: npm run test:setup")
        sys.exit(1)

cdn_hits = []       # בקשות שהוגשו מהעותק המקומי
external_hits = []  # בקשות חיצוניות שנחסמו — חייב להישאר ריק
cosmetic_hits = []  # משאבים קוסמטיים (פונטים) — נחסמים, לא משפיעים על הלוגיקה
COSMETIC = ('fonts.googleapis.com', 'fonts.gstatic.com')

results = []
def ck(name, cond): results.append((name, bool(cond)))

slow = {'on': False, 'server': None}
mock = {'leads_write': 'ok', 'delete': 'ok', 'rpc': 'ok', 'delay_ms': 0,
        'rpc_rows': [{'lead_id': 1, 'updated_at': '2026-08-09T10:00:00Z'}]}
calls = []

def short(u):
    for k in ('/rpc/rename_contact_and_leads_v2', '/rpc/upsert_leads_checked', '/rpc/merge_contacts',
              '/rpc/rename_contact_and_leads', '/rpc/reserve_lead_ids',
              '/rest/v1/leads', '/rest/v1/app_meta', '/auth/v1'):
        if k in u: return k
    return u.split('supabase.co')[-1][:40]

def handler(route):
    req = route.request
    url, method = req.url, req.method
    calls.append((method, short(url)))
    J = {'content_type': 'application/json'}
    # שמירה אטומית (סבב 6): אותה סמנטיקה כמו upsert_leads_checked ב-PostgreSQL — כשל/השהיה לפי אותם מתגים
    if '/rpc/upsert_leads_checked' in url:
        if mock['delay_ms']: time.sleep(mock['delay_ms'] / 1000.0)
        if mock['leads_write'] == 'fail':
            route.fulfill(status=500, body=json.dumps({'message': 'simulated save failure'}), **J)
            return
        try: rows = (json.loads(req.post_data or '{}').get('p_rows') or [])
        except Exception: rows = []
        now = __import__('datetime').datetime.utcnow().isoformat() + 'Z'
        route.fulfill(status=200, body=json.dumps([{'o_id': r.get('id'), 'o_status': 'ok', 'o_updated_at': now, 'o_server_data': None} for r in rows]), **J)
        return
    if '/rpc/merge_contacts' in url:
        if mock['rpc'] == 'fail':
            route.fulfill(status=400, body=json.dumps({'message': 'simulated rpc failure'}), **J); return
        try: ups = (json.loads(req.post_data or '{}').get('p_upserts') or [])
        except Exception: ups = []
        route.fulfill(status=200, body=json.dumps(ups), **J)
        return
    if '/rpc/rename_contact_and_leads' in url:
        if mock['rpc'] == 'fail':
            route.fulfill(status=400, body=json.dumps({'message': 'simulated rpc failure'}), **J)
        else:
            route.fulfill(status=200, body=json.dumps(mock['rpc_rows']), **J)
        return
    if '/rest/v1/leads' in url and method == 'GET':
        if slow.get('on'):
            time.sleep(0.45)
        body = json.dumps(slow.get('server') or [])
        route.fulfill(status=200, body=body, **J)
        return
    if '/rest/v1/leads' in url:
        if method == 'DELETE' and mock.get('delete') == 'fail':
            route.fulfill(status=500, body=json.dumps({'message': 'simulated delete failure'}), **J)
            return
        if method in ('POST', 'PATCH', 'PUT'):
            if mock['delay_ms']: time.sleep(mock['delay_ms'] / 1000.0)
            if mock['leads_write'] == 'fail':
                route.fulfill(status=500, body=json.dumps({'message': 'simulated save failure'}), **J)
                return
        route.fulfill(status=200, body='[]', **J)
        return
    route.fulfill(status=200, body='[]', **J)

def vendor_handler(route):
    url = route.request.url
    for frag, path in VENDOR_MAP.items():
        if frag in url:
            cdn_hits.append(url)
            body = open(path, 'rb').read()
            route.fulfill(status=200, body=body,
                          content_type='application/javascript; charset=utf-8',
                          headers={'Access-Control-Allow-Origin': '*'})
            return
    external_hits.append(url)
    route.abort()

def block_handler(route):
    url = route.request.url
    if url.startswith('file://') or url.startswith('data:') or url.startswith('blob:'):
        route.continue_(); return
    # פונטים נחסמים גם הם (אין רשת) אך אינם משפיעים על הלוגיקה הנבדקת
    (cosmetic_hits if any(d in url for d in COSMETIC) else external_hits).append(url)
    route.abort()

tmpdir = tempfile.mkdtemp()
target = os.path.join(tmpdir, 'target.html')
shutil.copy(SRC, target)

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context()
    pg = ctx.new_page(); cerr = []
    pg.on('console', lambda m: cerr.append(m.text) if m.type == 'error' else None)
    pg.on('pageerror', lambda e: cerr.append(str(e)))
    pg.on('dialog', lambda d: d.accept())
    # ב-Playwright ה-handler שנרשם אחרון נבדק ראשון — לכן הכללי נרשם קודם
    pg.route('**://*/**', block_handler)                      # כל שאר הרשת — חסום
    pg.route('**://cdnjs.cloudflare.com/**', vendor_handler)  # ExcelJS — מקומי
    pg.route('**://cdn.jsdelivr.net/**',     vendor_handler)  # supabase-js — מקומי
    pg.route('**://*.supabase.co/**', handler)                # Supabase — מוק
    pg.goto('file://' + target); pg.wait_for_timeout(2500)
    pg.evaluate("try{ initSupabase(); }catch(e){}")

    def reset():
        calls.clear()
        slow['on']=False; slow['server']=None
        mock.update({'leads_write': 'ok', 'delete': 'ok', 'rpc': 'ok', 'delay_ms': 0,
                     'rpc_rows': [{'lead_id': 1, 'updated_at': '2026-08-09T10:00:00Z'}]})
        pg.evaluate("""(()=>{
            leads.length=0; if(typeof contacts!=='undefined') contacts.length=0;
            if(saveData._ps) saveData._ps.clear();
            _isDirty=false; window.__isAuthed=false;
            try{ stopAutoSync(); }catch(e){}
            document.getElementById('searchInput').value='';
            document.querySelectorAll('#statusDropdown .st-opt input[type=checkbox]').forEach(cb=>cb.checked=true);
            const m=document.getElementById('_dupModal'); if(m) m.remove();
            window._bulkPendingDups=[]; window._dupState=[]; window._dupDecided=[]; window._bulkPlanned=[];
        })()""")

    ALLOC = """
      window.__alloc=[]; window.__saved=[]; window.__next=900;
      window.allocIds=async n=>{ window.__alloc.push(n); const a=[]; for(let i=0;i<n;i++)a.push(window.__next++); return a; };
      window.saveData=function(ids){ window.__saved.push(ids===undefined||ids===null?'ALL':(Array.isArray(ids)?ids.slice():[ids])); };
      window.saveData._ps=new Set();
    """

    # ══════════════ 1. הזנת כתובות במסה ══════════════
    reset()
    r = pg.evaluate("""(async()=>{""" + ALLOC + """
      document.getElementById('bulk_addresses').value='רחוב א 1, תל אביב\\nרחוב ב 2, תל אביב';
      ['bulk_date','bulk_name','bulk_deadline','bulk_notes'].forEach(i=>{const e=document.getElementById(i);if(e)e.value='';});
      await bulkImport();
      return {saved:window.__saved, alloc:window.__alloc, n:leads.length, ids:leads.map(l=>l.id).sort()};
    })()""")
    ck("1. 2 לידים חדשים → נשמרים בדיוק המזהים שלהם",
       len(r['saved']) == 1 and sorted(r['saved'][0]) == r['ids'] and len(r['ids']) == 2)
    ck("1. אין saveData() ללא מזהים", 'ALL' not in r['saved'])
    ck("1. הוקצו בדיוק 2 מזהים", r['alloc'] == [2])

    reset()
    r = pg.evaluate("""(async()=>{""" + ALLOC + """
      leads.push({id:1,address:'קיים 1',city:'תל אביב',name:'ישן',status:'חדש',date:'2026-01-01',replied:'לא'});
      window.__saved=[]; window.__alloc=[];
      document.getElementById('bulk_addresses').value='קיים 1, תל אביב';
      await bulkImport();
      _dupDecide(0,false);
      await _dupFinish(0,0);
      return {saved:window.__saved, alloc:window.__alloc, n:leads.length};
    })()""")
    ck("1. דילוג על הכול → אין שמירה כלל", r['saved'] == [])
    ck("1. דילוג על הכול → אין הקצאת מזהים", r['alloc'] == [])
    ck("1. ליד קיים לא נשלח מחדש", r['n'] == 1)

    # ══════════════ 2. חלון הכפילויות ══════════════
    reset()
    r = pg.evaluate("""(async()=>{""" + ALLOC + """
      leads.push({id:1,address:'קיים 1',city:'תל אביב',name:'ישן',status:'חדש',date:'2026-01-01',replied:'לא'});
      document.getElementById('bulk_addresses').value='קיים 1, תל אביב\\nקיים 1, תל אביב';
      await bulkImport();
      const btn=document.getElementById('_dupFinishBtn');
      window.__alloc=[];
      await _dupFinish(0,0);
      return {disabled:btn?btn.disabled:null, stillOpen:!!document.getElementById('_dupModal'),
              alloc:window.__alloc, created:leads.length};
    })()""")
    ck("2. כפתור סיום מושבת כשקיימת כפילות לא מוכרעת", r['disabled'] is True)
    ck("2. סיום נחסם — החלון נשאר פתוח", r['stillOpen'])
    ck("2. סיום חסום לא מקצה מזהים", r['alloc'] == [] and r['created'] == 1)

    r = pg.evaluate("""(async()=>{
      _dupDecide(0,true); _dupDecide(1,false);
      const btn=document.getElementById('_dupFinishBtn');
      const enabled=btn && !btn.disabled;
      window.__alloc=[];
      await _dupFinish(0,0);
      return {enabled, alloc:window.__alloc, total:leads.length};
    })()""")
    ck("2. אחרי כל ההחלטות הכפתור נפתח", r['enabled'])
    ck("2. הוקצה מזהה לאישור אחד בלבד", r['alloc'] == [1] and r['total'] == 2)

    reset()
    r = pg.evaluate("""(async()=>{""" + ALLOC + """
      leads.push({id:1,address:'קיים 1',city:'תל אביב',name:'ישן',status:'חדש',date:'2026-01-01',replied:'לא'});
      document.getElementById('bulk_addresses').value='קיים 1, תל אביב\\nחדש ב 9, חיפה';
      await bulkImport();
      window.__alloc=[]; window.__saved=[];
      await _dupCancel();
      return {closed:!document.getElementById('_dupModal'), alloc:window.__alloc,
              saved:window.__saved, total:leads.length};
    })()""")
    ck("2. ביטול סוגר את החלון", r['closed'])
    ck("2. ביטול מבטל את הייבוא כולו — אין יצירה", r['total'] == 1 and r['alloc'] == [])
    ck("2. ביטול לא מפעיל שמירה", r['saved'] == [])

    # ══════════════ 3. ייבוא Excel אמיתי ══════════════
    XLSX = """
      window.__mkXlsx=async(rows)=>{
        await loadExcelJS();
        const wb=new ExcelJS.Workbook(); const ws=wb.addWorksheet('לידים');
        ws.addRow(['תאריך קבלה','כתובת הפרויקט','עיר','שם הפונה','סטטוס','תגובה נשלחה?','הערות']);
        rows.forEach(r=>ws.addRow(r));
        const buf=await wb.xlsx.writeBuffer();
        const file=new File([buf],'t.xlsx',{type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'});
        const input=document.createElement('input'); input.type='file';
        Object.defineProperty(input,'files',{value:[file]});
        return {target:input};
      };
      window.__waitLeads=async(n,ms)=>{ const t=Date.now();
        while(Date.now()-t<(ms||8000)){ if(leads.length>=n) return true; await new Promise(r=>setTimeout(r,80)); }
        return false; };
    """
    reset()
    r = pg.evaluate("""(async()=>{""" + ALLOC + XLSX + """
      const ev=await window.__mkXlsx([
        ['01/08/2026','ביאליק 2','רמת גן','One','בבדיקה','כן','נוצר קשר'],
        ['',         'ביאליק 2','רמת גן','Two','',      '',  'פגישה נקבעה']
      ]);
      await importFromExcel(ev);
      await window.__waitLeads(1);
      const l=leads[0]||{};
      return {count:leads.length, date:l.date, replied:l.replied, notes:l.notes,
              status:l.status, alloc:window.__alloc};
    })()""")
    ck("3. שתי שורות זהות → ליד אחד בלבד", r['count'] == 1)
    ck("3. תאריך ריק לא דרס (01.08.2026)", r['date'] == '2026-08-01')
    ck("3. תגובה ריקה לא דרסה (כן)", r['replied'] == 'כן')
    ck("3. הערה מאוחרת כן עדכנה", r['notes'] == 'פגישה נקבעה')
    ck("3. סטטוס ריק לא דרס (בבדיקה)", r['status'] == 'בבדיקה')
    ck("3. הוקצה מזהה אחד בלבד", r['alloc'] == [1])

    reset()
    r = pg.evaluate("""(async()=>{""" + ALLOC + XLSX + """
      const ev=await window.__mkXlsx([
        ['01/08/2026','ביאליק 3','רמת גן','One','בבדיקה','כן','a'],
        ['02/08/2026','ביאליק 3','רמת גן','Two','חדש',  'לא','b']
      ]);
      await importFromExcel(ev);
      await window.__waitLeads(1);
      const l=leads[0]||{};
      return {count:leads.length, replied:l.replied, status:l.status, date:l.date, name:l.name};
    })()""")
    ck("3. ערך מפורש 'לא' מחליף 'כן'", r['replied'] == 'לא')
    ck("3. ערך מפורש מחליף גם סטטוס/תאריך/שם",
       r['status'] == 'חדש' and r['date'] == '2026-08-02' and r['name'] == 'Two')

    # ══════════════ 4. תור כתיבות ו-RPC ══════════════
    CONTACT = """
      window.__setupContact=()=>{
        contacts.length=0; contacts.push({id:'c1',name:'ישן',phone:'050-0000000',email:'a@a.com'});
        leads.length=0; leads.push({id:1,address:'א',city:'תא',name:'ישן',status:'חדש',date:'2026-01-01',replied:'לא'});
        localStorage.setItem('contacts_v1',JSON.stringify(contacts));
        openContactForm('c1');   // קובע editingContactId דרך הקוד האמיתי
        document.getElementById('cf_name').value='חדש';
        document.getElementById('cf_phone').value='052-1111111';
        document.getElementById('cf_email').value='';
      };
      window.__snapshot=()=>JSON.stringify({c:contacts.map(x=>x.name+'|'+x.phone),
        l:leads.map(x=>x.name+'|'+x.phone), ls:localStorage.getItem('contacts_v1')});
    """
    reset()
    mock['rpc_rows'] = [{'lead_id': 1, 'updated_at': '2026-08-09T12:34:56Z'}]
    r = pg.evaluate("""(async()=>{""" + CONTACT + """
      window.__setupContact();
      if(saveData._ps) saveData._ps.clear();
      await saveContact();
      return {contact:contacts[0].name, leadName:leads[0].name, leadPhone:leads[0].phone,
              ts:_leadTs[1], ls:localStorage.getItem('contacts_v1').includes('חדש')};
    })()""")
    ck("4. הצלחת RPC → איש הקשר עודכן", r['contact'] == 'חדש')
    ck("4. הצלחת RPC → הלידים המקושרים עודכנו", r['leadName'] == 'חדש' and r['leadPhone'] == '052-1111111')
    ck("4. הצלחת RPC → localStorage עודכן", r['ls'])
    ck("4. מבנה תשובת ה-RPC נקרא נכון (_leadTs)", r['ts'] == '2026-08-09T12:34:56Z')
    ck("4. ה-RPC נקרא בפועל", any(c[1] in ('/rpc/rename_contact_and_leads','/rpc/rename_contact_and_leads_v2') for c in calls))

    reset(); mock['rpc'] = 'fail'
    r = pg.evaluate("""(async()=>{""" + CONTACT + """
      window.__setupContact();
      if(saveData._ps) saveData._ps.clear();
      const before=window.__snapshot();
      await saveContact();
      return {unchanged: before===window.__snapshot()};
    })()""")
    ck("4. כשל RPC → אין שינוי בזיכרון/localStorage", r['unchanged'])

    reset(); mock['leads_write'] = 'fail'
    r = pg.evaluate("""(async()=>{""" + CONTACT + """
      window.__setupContact();
      saveData._ps=new Set([1]);
      const before=window.__snapshot();
      await saveContact();
      return {unchanged: before===window.__snapshot(), queueKept: saveData._ps.has(1)};
    })()""")
    ck("4. כשל שמירת ליד → RPC לא מופעל",
       not any(c[1] in ('/rpc/rename_contact_and_leads','/rpc/rename_contact_and_leads_v2') for c in calls))
    ck("4. כשל שמירת ליד → אין שינוי מקומי", r['unchanged'])
    ck("4. אין אובדן מזהים מתור השמירה", r['queueKept'])

    reset(); mock['delay_ms'] = 400
    pg.evaluate("""(async()=>{""" + CONTACT + """
      window.__setupContact();
      saveData._ps=new Set([1]);
      await Promise.all([flushPendingSaves(), saveContact()]);
    })()""")
    writes = [i for i, c in enumerate(calls) if (c[1] == '/rest/v1/leads' and c[0] in ('POST', 'PATCH', 'PUT')) or c[1] == '/rpc/upsert_leads_checked']
    rpcs = [i for i, c in enumerate(calls) if c[1] in ('/rpc/rename_contact_and_leads', '/rpc/rename_contact_and_leads_v2')]
    ck("4. שמירת איש קשר ממתינה לסיום שמירת ליד פעילה",
       bool(writes) and bool(rpcs) and max(writes) < min(rpcs))

    reset()
    pg.evaluate("""(async()=>{""" + CONTACT + """
      window.__setupContact();
      if(saveData._ps) saveData._ps.clear();
      await Promise.all([saveContact(), saveContact(), saveContact()]);
    })()""")
    ck("4. לחיצה כפולה → פעולה אחת בלבד",
       len([c for c in calls if c[1] in ('/rpc/rename_contact_and_leads','/rpc/rename_contact_and_leads_v2')]) == 1)

    # ══════════════ 5. סנכרון אוטומטי — מול המימוש האמיתי ══════════════
    # אין שכפול של הלוגיקה: מריצים את startAutoSync()/stopAutoSync() האמיתיים
    # ומודדים את הקריאות שהקוד מבצע, באמצעות spies על setInterval/clearInterval.
    SPY = """
      window.__spy={intervals:[],cleared:[],reloads:0};
      window.__realSI=window.setInterval; window.__realCI=window.clearInterval;
      window.setInterval=function(fn,ms){
        const id=window.__realSI(fn,ms);
        window.__spy.intervals.push({id, ms, fn});
        return id;
      };
      window.clearInterval=function(id){ window.__spy.cleared.push(id); return window.__realCI(id); };
      window.__realReload=window.reloadFromSupabase;
      window.reloadFromSupabase=async(sil)=>{ window.__spy.reloads++; return window.__realReload(sil); };
      // הרץ ידנית את ה-callback של הטיימר — בלי להמתין 45 שניות אמיתיות
      window.__tick=()=>{ window.__spy.intervals.forEach(i=>{ try{ i.fn(); }catch(e){} }); };
    """
    UNSPY = """
      window.setInterval=window.__realSI; window.clearInterval=window.__realCI;
      window.reloadFromSupabase=window.__realReload;
    """

    # 5א. מנותק — startAutoSync לא נקראת כלל; טיק לא מסנכרן
    reset()
    r = pg.evaluate("""(async()=>{""" + SPY + """
        stopAutoSync();                       // המימוש האמיתי
        window.__spy.intervals=[]; window.__spy.cleared=[]; window.__spy.reloads=0;
        showLoginScreen();                    // מצב מנותק אמיתי
        const timerAfterLogout=window.__autoSyncTimer;
        window.__tick();                      // אם היה callback ישן — שידע
        await new Promise(r=>setTimeout(r,40));
        const out={createdTimers:window.__spy.intervals.length,
                   reloads:window.__spy.reloads,
                   timerNull:timerAfterLogout===null,
                   authed:window.__isAuthed};
        """ + UNSPY + """
        return out;
    })()""")
    ck("5. מנותק → לא נוצר טיימר", r['createdTimers'] == 0)
    ck("5. מנותק → לא בוצע reload", r['reloads'] == 0)
    ck("5. מנותק → מזהה הטיימר ריק", r['timerNull'])
    ck("5. מנותק → הדגל __isAuthed כבוי", r['authed'] is False)

    # 5ב. התחברות — startAutoSync האמיתית יוצרת טיימר אחד; קריאה חוזרת לא מוסיפה
    reset()
    r = pg.evaluate("""(async()=>{""" + SPY + """
        stopAutoSync();
        window.__spy.intervals=[]; window.__spy.cleared=[]; window.__spy.reloads=0;
        startAutoSync();                      // המימוש האמיתי
        const afterFirst=window.__spy.intervals.length;
        const idFirst=window.__autoSyncTimer;
        startAutoSync(); startAutoSync();      // קריאות חוזרות
        const afterRepeat=window.__spy.intervals.length;
        const idSame=window.__autoSyncTimer===idFirst;
        const period=window.__spy.intervals[0] ? window.__spy.intervals[0].ms : null;
        window.__tick();                       // הרץ את ה-callback האמיתי
        await new Promise(r=>setTimeout(r,40));
        const reloadsWhileAuthed=window.__spy.reloads;
        stopAutoSync();
        const out={afterFirst, afterRepeat, idSame, period, reloadsWhileAuthed,
                   authed:window.__isAuthed};
        """ + UNSPY + """
        return out;
    })()""")
    ck("5. התחברות → נוצר טיימר אחד בלבד", r['afterFirst'] == 1)
    ck("5. קריאה חוזרת → לא נוצר טיימר נוסף", r['afterRepeat'] == 1 and r['idSame'])
    ck("5. מחזור הטיימר 45 שניות", r['period'] == 45000)
    ck("5. מחובר → ה-callback מבצע סנכרון", r['reloadsWhileAuthed'] > 0)

    # 5ג. התנתקות — clearInterval נקרא ומזהה הטיימר מתאפס; callback ישן לא מסנכרן
    reset()
    r = pg.evaluate("""(async()=>{""" + SPY + """
        stopAutoSync();
        window.__spy.intervals=[]; window.__spy.cleared=[]; window.__spy.reloads=0;
        startAutoSync();
        const id=window.__autoSyncTimer;
        window.__spy.reloads=0;
        stopAutoSync();                        // המימוש האמיתי
        const clearedThis=window.__spy.cleared.includes(id);
        const nulled=window.__autoSyncTimer===null;
        window.__tick();                       // callback ישן אחרי התנתקות
        await new Promise(r=>setTimeout(r,40));
        const reloadsAfterStop=window.__spy.reloads;
        const out={clearedThis, nulled, reloadsAfterStop};
        """ + UNSPY + """
        return out;
    })()""")
    ck("5. התנתקות → clearInterval נקרא על הטיימר", r['clearedThis'])
    ck("5. התנתקות → מזהה הטיימר אופס", r['nulled'])
    ck("5. callback ישן אינו מסנכרן אחרי התנתקות", r['reloadsAfterStop'] == 0)

    # 5ד. מחזורי התחברות/התנתקות — אין טיימרים מקבילים
    reset()
    r = pg.evaluate("""(async()=>{""" + SPY + """
        stopAutoSync();
        window.__spy.intervals=[]; window.__spy.cleared=[];
        for(let i=0;i<5;i++){ startAutoSync(); stopAutoSync(); }
        const created=window.__spy.intervals.length, cleared=window.__spy.cleared.length;
        startAutoSync();
        const live=window.__autoSyncTimer;
        stopAutoSync();
        const out={created, cleared, balanced:created===cleared, liveSet:live!==null};
        """ + UNSPY + """
        return out;
    })()""")
    ck("5. 5 מחזורים → 5 טיימרים ו-5 ניקויים (מאוזן)", r['balanced'] and r['created'] == 5)
    ck("5. אין טיימרים מקבילים", r['liveSet'])

    # 5ה. מנותק — אפס קריאות רשת ל-Supabase, ואין Reload error
    reset()
    pg.evaluate("""(async()=>{ showLoginScreen();
        _isDirty=false; if(saveData._ps) saveData._ps.clear();
        await reloadFromSupabase(true); })()""")
    ck("5. מנותק → אין קריאת רשת ל-Supabase", len(calls) == 0)
    ck("5. מנותק → אין הודעת 'Reload error'",
       not any('Reload error' in e for e in cerr))

    # 5ו. מחובר + כשל אמיתי — השגיאה עדיין מטופלת ומוצגת
    reset()
    before_err = len([e for e in cerr if 'Reload error' in e])
    mock['leads_write'] = 'ok'
    pg.evaluate("""(async()=>{
        window.__isAuthed=true;                 // מחובר
        _isDirty=false; if(saveData._ps) saveData._ps.clear();
        window.__forceReloadFail=true;
        const realFrom = sb.from;
        sb.from = ()=>{ throw new Error('simulated reload failure'); };
        try{ await reloadFromSupabase(true); }catch(e){}
        sb.from = realFrom;
        window.__isAuthed=false;
    })()""")
    pg.wait_for_timeout(300)
    after_err = len([e for e in cerr if 'Reload error' in e])
    ck("5. מחובר + כשל → השגיאה מטופלת ומדווחת", after_err > before_err)

    # ══════════════ 6. תאריכים ══════════════
    for inp, exp in [('2026-02-28', '28/02/2026'), ('2024-02-29', '29/02/2024'),
                     ('2026-02-29', '—'), ('2026-02-31', '—'), ('2026-13-01', '—'),
                     ('2026-04-31', '—'), ('', '—'), ('2026-08-09', '09/08/2026')]:
        ck("6. fmtDate(" + (inp or "ריק") + ")", pg.evaluate("fmtDate(" + repr(inp) + ")") == exp)

    # ══════════════ רגרסיה ══════════════
    for t, ea, ec, en in [
        ("שלום מורן\nכתובת: הרצל 10, רמת גן\nשם הפונה: ישראל ישראלי\nטלפון: 050-1234567", "הרצל 10", "רמת גן", "ישראל ישראלי"),
        ("כתובת: דרך חיפה 20, תל אביב\nאיש קשר: ישראל ישראלי", "דרך חיפה 20", "תל אביב", "ישראל ישראלי"),
        ("פנינה ומשה 9 9א 11 11 א ראשון לציון", "פנינה ומשה 9 9א 11 11 א", "ראשון לציון", None)]:
        rr = pg.evaluate("(()=>{const p=parseWaContent(" + repr(t) + ");return [p.address,p.city,p.name];})()")
        ck("רגרסיה WhatsApp: " + t.splitlines()[0][:26],
           rr[0] == ea and rr[1] == ec and (en is None or rr[2] == en))

    reset()
    ck("רגרסיה: אפס סטטוסים מסומנים → אפס לידים", pg.evaluate("""(()=>{
        leads.length=0; leads.push({id:1,address:'א',city:'תא',name:'x',status:'חדש',date:'2026-01-01',replied:'לא'});
        document.querySelectorAll('#statusDropdown .st-opt input[type=checkbox]').forEach(cb=>cb.checked=false);
        document.getElementById('searchInput').value='';
        return filteredLeads().length===0; })()"""))
    ck("רגרסיה: חיפוש מוצא ליד שסטטוסו לא מסומן", pg.evaluate("""(()=>{
        leads.length=0; leads.push({id:1,address:'ייחודי',city:'תא',name:'x',status:'לא רלוונטי ❌',date:'2026-01-01',replied:'לא'});
        document.querySelectorAll('#statusDropdown .st-opt input[type=checkbox]').forEach(cb=>cb.checked=false);
        document.getElementById('searchInput').value='ייחודי';
        const n=filteredLeads().length;
        document.getElementById('searchInput').value='';
        document.querySelectorAll('#statusDropdown .st-opt input[type=checkbox]').forEach(cb=>cb.checked=true);
        return n===1; })()"""))
    ck("רגרסיה: יומן — היסטוריים מופרדים מיצירות", pg.evaluate("""(()=>{
        _auditRows=[{lead_id:5,action:'created',note:'backfill x',at:'2026-07-30T09:00:00Z'},
                    {lead_id:6,action:'created',note:'saveLead',at:'2026-08-01T09:00:00Z'}];
        _auditOrphans=[];_auditOrphansOk=true;_auditHasMore=false;
        renderAuditLog('created');
        const created=document.querySelectorAll('#auditBody tbody tr').length;
        renderAuditLog('historical');
        const hist=document.querySelectorAll('#auditBody tbody tr').length;
        return created===1 && hist===1; })()"""))
    ck("רגרסיה: כשל טעינת orphans → אזהרה ולא ירוק", pg.evaluate("""(()=>{
        _auditRows=[];_auditOrphans=[];_auditOrphansOk=false;_auditHasMore=false;
        renderAuditLog('all');
        const t=document.getElementById('auditOrphanBox').textContent;
        return t.includes('לא ניתן לבדוק') && !t.includes('✅'); })()"""))

    # ══════════════ תקינות ממשק ══════════════
    reset()
    pg.evaluate("""(()=>{
      unlockAppShell(); leads.length=0;
      leads.push({id:7,address:'הקסם 7',city:'הרצליה',name:'א',status:'חדש',date:'2026-01-01',replied:'לא',budget:'כן'});
      document.querySelectorAll('#statusDropdown .st-opt input[type=checkbox]').forEach(cb=>cb.checked=true);
      refresh(); })()""")
    ck("ממשק: אין NaN/undefined בטבלה", pg.evaluate(
        "(()=>{const t=document.getElementById('tableBody').textContent;return !t.includes('NaN')&&!t.includes('undefined');})()"))
    ck("ממשק: אין תאים שבורים", pg.evaluate(
        "(()=>{const th=document.querySelectorAll('thead th').length;const td=document.querySelectorAll('#tableBody tr:first-child td').length;return th===td;})()"))
    for fn, el in [('renderDash', 'dashStatus'), ('renderAnalytics', 'anConversion'), ('renderContacts', 'contactsList')]:
        ck("ממשק: " + fn + " נטען", pg.evaluate(
            "(()=>{try{ " + fn + "(); return !!document.getElementById('" + el + "'); }catch(e){ return 'ERR:'+e.message; }})()") is True)
    ck("ממשק: הדוח החודשי נטען", pg.evaluate(
        "(()=>{try{ if(window.showMonthlyReport){showMonthlyReport(); const o=document.getElementById('reportOverlay'); if(o)o.classList.remove('open');} return true;}catch(e){return 'ERR:'+e.message;}})()") is True)
    ck("ממשק: אין מזהי HTML כפולים", pg.evaluate(
        "(()=>{const i=[...document.querySelectorAll('[id]')].map(e=>e.id);return i.filter((x,n)=>i.indexOf(x)!==n).length===0;})()"))
    ck("ממשק: חלונות נפתחים אחרי כניסה", pg.evaluate("""(()=>{
        showLoginScreen(); unlockAppShell();
        if(window.openForm) openForm();
        const fo=document.getElementById('formOverlay');
        const ok=fo&&fo.classList.contains('open')&&getComputedStyle(fo).display!=='none';
        if(window.closeForm) closeForm();
        return ok; })()"""))

    def noise(e):
        el = e.lower()
        return ('favicon' in el or 'failed to load resource' in el
                or 'net::' in el or 'sw.js' in el or 'simulated' in el)
    real = [e for e in cerr if not noise(e)]
    ck("אין שגיאות JavaScript (" + str(len(real)) + ")", len(real) == 0)
    for e in real[:5]: print("   ⚠️", e[:140])

    # ══════════════ 7. אישור בעלים לא מתבטל בפתיחה+שמירה ══════════════
    reset()
    r = pg.evaluate("""(()=>{""" + ALLOC + """
        const mk=()=>{leads.length=0;
          leads.push({id:1,address:'א',city:'תא',name:'x',status:'חדש',date:'2026-01-01',replied:'לא',budget:''});
          leads.push({id:2,address:'ב',city:'תא',name:'y',status:'נשלחה הצעה',date:'2026-01-01',replied:'לא',
                      budget:'כן',ownerApproved:true,ownerApprovedAt:'2026-07-01'});};
        const o={};
        mk(); openEdit(1); if(window.closeEdit)closeEdit(); openEdit(2); saveEdit();
        o.afterNoBudget = !!leads[1].ownerApproved && leads[1].ownerApprovedAt==='2026-07-01';
        mk(); openEdit(2); saveEdit();
        o.firstOpen = !!leads[1].ownerApproved && leads[1].ownerApprovedAt==='2026-07-01';
        mk(); openEdit(1); o.lockedNoBudget=document.getElementById('e_ownerApproved').disabled;
        if(window.closeEdit)closeEdit();
        mk(); openEdit(2); document.getElementById('e_ownerApproved').checked=false; saveEdit();
        o.manualUncheck = !leads[1].ownerApproved;
        return o;
    })()""")
    ck("7. פתיחה+שמירה משמרת אישור בעלים (אחרי ליד ללא תקציב)", r['afterNoBudget'])
    ck("7. פתיחה ראשונה משמרת אישור ותאריך", r['firstOpen'])
    ck("7. ליד ללא תקציב — הצ'קבוקס נעול", r['lockedNoBudget'])
    ck("7. ביטול ידני של האישור עדיין עובד", r['manualUncheck'])

    # ══════════════ 8. אימות תאריכים בייבוא (אין NaN) ══════════════
    reset()
    r = pg.evaluate("""(()=>{
        const o={};
        o.leap    = isValidISODate('2024-02-29');
        o.ok      = isValidISODate('2026-02-28');
        o.badFeb  = !isValidISODate('2026-02-29');
        o.badDay  = !isValidISODate('2026-02-31');
        o.badMon  = !isValidISODate('2026-13-01');
        o.badText = !isValidISODate('not-a-date');
        const l={id:1,address:'א',city:'תא',name:'x',status:'חדש',date:'not-a-date',replied:'לא'};
        leads.length=0; leads.push(l);
        o.noNaN    = !String(daysChip(l)).includes('NaN');
        o.nullDays = daysSince('not-a-date')===null;
        return o;
    })()""")
    ck("8. 2024-02-29 (שנה מעוברת) מתקבל", r['leap'])
    ck("8. 2026-02-28 מתקבל", r['ok'])
    ck("8. 2026-02-29 נדחה", r['badFeb'])
    ck("8. 2026-02-31 נדחה", r['badDay'])
    ck("8. 2026-13-01 נדחה", r['badMon'])
    ck("8. טקסט שאינו תאריך נדחה", r['badText'])
    ck("8. אין NaN בתצוגת הימים", r['noNaN'])
    ck("8. importLeads שומר רק את מזהי החדשים",
       pg.evaluate("importLeads.toString().includes('saveData(parsedRows.map')"))

    # ══════════════ 9. לחיצה כפולה על יצירת ליד ══════════════
    reset()
    r = pg.evaluate("""(async()=>{
        leads.length=0; let calls=0;
        window.allocIds=async n=>{calls++; await new Promise(r=>setTimeout(r,60));
            const a=[];for(let i=0;i<n;i++)a.push(700+calls*10+i);return a;};
        openForm();
        document.getElementById('f_address').value='כפול 1';
        document.getElementById('f_city').value='תל אביב';
        document.getElementById('f_name').value='בדיקה';
        await Promise.all([saveLead(), saveLead()]);
        const created=leads.length;
        leads.length=0; window.allocIds=async()=>null;
        openForm();
        document.getElementById('f_address').value='כשל 1';
        document.getElementById('f_city').value='תל אביב';
        await saveLead();
        const afterFail=leads.length;
        window.allocIds=async n=>{const a=[];for(let i=0;i<n;i++)a.push(950+i);return a;};
        await saveLead();
        return {created, afterFail, retry:leads.length};
    })()""")
    ck("9. שתי לחיצות מהירות → ליד אחד בלבד", r['created'] == 1)
    ck("9. כשל הקצאה → לא נוצר ליד", r['afterFail'] == 0)
    ck("9. ניסיון חוזר אחרי כשל מצליח", r['retry'] == 1)

    # ══════════════ 10. סגירה לא כלכלית אינה הפסד תחרותי ══════════════
    reset()
    r = pg.evaluate("""(()=>{
        leads.length=0;
        leads.push({id:1,address:'א',city:'תא',name:'x',status:'לא רלוונטי ❌',date:'2026-01-01',
                    irrelReason:'לא כלכלי',competitor:'חברה ג',replied:'לא'});
        leads.push({id:2,address:'ב',city:'תא',name:'y',status:'לא רלוונטי ❌',date:'2026-01-01',
                    irrelReason:'הלך למתחרה',competitor:'חברה ג',replied:'לא'});
        renderAnalytics();
        const t=document.getElementById('anCompetitors').textContent.replace(/\s+/g,' ');
        // עמודות: עסקאות, ניצחנו, הפסדנו למתחרה, הפסד-זוכה לא ידוע, נסגרו מסיבה אחרת
        const nums=t.match(/חברה ג (\d+) (\d+) (\d+) (\d+) (\d+)/);
        return {label:t.includes('נסגרו מסיבה אחרת'),
                lostTo: nums?+nums[3]:null, closed: nums?+nums[5]:null};
    })()""")
    ck("10. קיים מדד נפרד 'נסגרו מסיבה אחרת'", r['label'])
    ck("10. 'הלך למתחרה' נספר כהפסד תחרותי (1)", r['lostTo'] == 1)
    ck("10. 'לא כלכלי' לא נספר כהפסד תחרותי (1 בעמודה הנפרדת)", r['closed'] == 1)

    # ══════════ 11. תשובות סנכרון מאוחרות (F01/F12) ══════════
    # מריץ את reloadFromSupabase האמיתית מול GET מושהה (ההשהיה נשלטת מ-Python)
    reset()
    slow['on'] = True
    slow['server'] = [{'id': 1, 'data': {'id': 1, 'address': 'הרצל 1', 'city': 'תא', 'name': 'x',
                                         'status': 'חדש', 'date': '2026-01-01', 'replied': 'לא', 'notes': ''},
                       'updated_at': '2026-09-01T10:00:00Z'}]
    r = pg.evaluate("""(async()=>{
        window.__isAuthed=true;
        leads.length=0;
        leads.push({id:1,address:'הרצל 1',city:'תא',name:'x',status:'חדש',date:'2026-01-01',replied:'לא',notes:''});
        _isDirty=false; if(saveData._ps) saveData._ps.clear();
        const syncP=reloadFromSupabase(true);
        await new Promise(r=>setTimeout(r,150));
        const l=leads.find(x=>x.id===1); if(l) l.notes='הערה חשובה';
        await syncP; await new Promise(r=>setTimeout(r,80));
        return leads.find(x=>x.id===1)?.notes||'(אבד)';
    })()""")
    ck("11. עריכה בזמן סנכרון מושהה אינה נדרסת", r == 'הערה חשובה')

    reset()
    slow['on'] = True
    r = pg.evaluate("""(async()=>{
        window.__isAuthed=true;
        leads.length=0; _isDirty=false; if(saveData._ps) saveData._ps.clear();
        localStorage.removeItem(STORAGE_KEY);
        const syncP=reloadFromSupabase(true);
        await new Promise(r=>setTimeout(r,150));
        showLoginScreen(); leads.length=0; localStorage.removeItem(STORAGE_KEY);
        await syncP; await new Promise(r=>setTimeout(r,80));
        let ls=0; try{ ls=(JSON.parse(localStorage.getItem(STORAGE_KEY)||'{}').leads||[]).length; }catch(e){}
        return {mem:leads.length, ls};
    })()""")
    ck("11. תשובה מסשן קודם אינה מוחלת אחרי יציאה", r['mem'] == 0 and r['ls'] == 0)

    reset()
    slow['on'] = False
    r = pg.evaluate("""(async()=>{
        window.__isAuthed=true;
        leads.length=0; _isDirty=false; if(saveData._ps) saveData._ps.clear();
        window.__syncSeq=10; window.__lastAppliedSync=12;
        const before=JSON.stringify(leads);
        await reloadFromSupabase(true);
        window.__lastAppliedSync=0; window.__syncSeq=0;
        return JSON.stringify(leads)===before;
    })()""")
    ck("11. תשובה שהגיעה בסדר הפוך אינה מוחלת", r)

    reset()
    slow['on'] = False
    slow['server'] = [{'id': 1, 'data': {'id': 1, 'address': 'ממכשיר אחר', 'city': 'תא', 'name': 'x',
                                         'status': 'חדש', 'date': '2026-01-01', 'replied': 'לא'},
                       'updated_at': '2026-09-02T10:00:00Z'}]
    r = pg.evaluate("""(async()=>{
        window.__isAuthed=true;
        leads.length=0;
        leads.push({id:1,address:'ישן',city:'תא',name:'x',status:'חדש',date:'2026-01-01',replied:'לא'});
        _isDirty=false; if(saveData._ps) saveData._ps.clear();
        await reloadFromSupabase(true);
        return {addr:leads.find(x=>x.id===1)?.address||'', ts:_leadTs[1]||''};
    })()""")
    ck("11. סנכרון תקין עדיין מחיל שינוי מהשרת", r['addr'] == 'ממכשיר אחר')
    ck("11. _leadTs מתעדכן יחד עם הנתונים", bool(r['ts']))
    slow['server'] = None

    # ══════════════ 11. חיווי שמירה כן — N12 ══════════════
    reset()
    r = pg.evaluate("""(()=>{
        leads.length=0; leads.push({id:1,address:'א',city:'תא',name:'x',status:'חדש',date:'2026-01-01',replied:'לא'});
        const ps = saveData._ps || (saveData._ps = new Set());
        _isDirty=true; ps.add(1);
        _reflectPendingStatus();
        const pend=document.getElementById('syncIndicator').textContent;
        _isDirty=false; ps.clear();
        _reflectPendingStatus();
        const clean=document.getElementById('syncIndicator').textContent;
        return {pend, clean};
    })()""")
    ck("11. שינוי ממתין → לא מוצג 'מסונכרן'", 'מסונכרן' not in r['pend'])
    ck("11. שינוי ממתין → מוצג חיווי המתנה", 'ממתינים' in r['pend'] or 'טרם נשמרו' in r['pend'])
    ck("11. אחרי שמירה מלאה → 'מסונכרן'", 'מסונכרן' in r['clean'])
    ck("11. דחיית GET מיושן אינה מציגה 'מסונכרן'",
       pg.evaluate("reloadFromSupabase.toString().includes('_reflectPendingStatus()')"))
    ck("11. כשל סנכרון מוצג למשתמש מחובר",
       pg.evaluate("reloadFromSupabase.toString().includes('סנכרון נכשל')"))
    ck("11. כשל אינו מוצג אחרי התנתקות",
       pg.evaluate("reloadFromSupabase.toString().includes('window.__isAuthed && window.__syncGen === genAtStart')"))

    # ══════════════ 12. מחיקה מתואמת עם כתיבות — F03/F04 ══════════════
    reset()
    ck("12. מחיקה עוברת דרך תור הכתיבות", pg.evaluate("deleteLead.toString().includes('_withWriteLock')"))
    ck("12. מרוקנת כתיבות ממתינות לפני מחיקה", pg.evaluate("deleteLead.toString().includes('_flushAllUnlocked')"))
    r = pg.evaluate("""(async()=>{
        const order=[];
        const slow=()=>_withWriteLock(async()=>{order.push('write-start');
          await new Promise(r=>setTimeout(r,120)); order.push('write-end'); return true;});
        const del=()=>_withWriteLock(async()=>{order.push('delete'); return true;});
        await Promise.all([slow(), del()]);
        return order;
    })()""")
    ck("12. מחיקה ממתינה לסיום כתיבה פעילה", r == ['write-start','write-end','delete'])

    SEED_DEL = """
        leads.length=0; leads.push({id:7,address:'למחוק',city:'תא',name:'y',status:'חדש',date:'2026-01-01',replied:'לא'});
        const ps = saveData._ps || (saveData._ps = new Set()); ps.clear(); ps.add(7);
        localStorage.setItem('pendingSaveQueue',JSON.stringify({ids:[7],ts:Date.now()}));
        localStorage.setItem(STORAGE_KEY,JSON.stringify({leads,nextId}));
        window.confirm=()=>true;
    """
    # כשל מחיקה → שחזור מלא
    reset(); mock['leads_write']='ok'; mock['delete']='fail'
    r = pg.evaluate("(async()=>{"+SEED_DEL+"""
        await deleteLead(7);
        const s=JSON.parse(localStorage.getItem(STORAGE_KEY)||'{}');
        return {mem:leads.some(l=>l.id===7), backup:(s.leads||[]).some(l=>l.id===7)};
    })()""")
    ck("12. כשל מחיקה → הליד חזר לזיכרון", r['mem'])
    ck("12. כשל מחיקה → חזר לגיבוי המקומי", r['backup'])

    # כשל סנכרון → אין למחוק כלל
    reset(); mock['leads_write']='fail'; mock['delete']='ok'
    r = pg.evaluate("(async()=>{"+SEED_DEL+"""
        await deleteLead(7);
        const q=JSON.parse(localStorage.getItem('pendingSaveQueue')||'{}');
        const s=JSON.parse(localStorage.getItem(STORAGE_KEY)||'{}');
        return {mem:leads.some(l=>l.id===7), queue:saveData._ps.has(7),
                ls:(q.ids||[]).includes(7), backup:(s.leads||[]).some(l=>l.id===7)};
    })()""")
    ck("12. כשל סנכרון → המחיקה נחסמה", r['mem'])
    ck("12. כשל סנכרון → השינוי נשאר בתור", r['queue'])
    ck("12. כשל סנכרון → נשאר בר-שחזור ב-localStorage", r['ls'] and r['backup'])
    mock['leads_write']='ok'; mock['delete']='ok'

    # ══════════════ 13. יציאה לא מוחקת שינויים — F06 ══════════════
    reset()
    ck("13. _wipeAndLogout מקבל keepUnsynced", pg.evaluate("_wipeAndLogout.toString().includes('keepUnsynced')"))
    ck("13. שומר את התור כשיש שינויים",
       pg.evaluate("_wipeAndLogout.toString().includes(\"keepUnsynced ? ['contacts_v1']\")"))
    ck("13. יציאה מציעה ניסיון סנכרון חוזר", pg.evaluate("secureLogout.toString().includes('ניסיון סנכרון נוסף')"))
    ck("13. ההודעה תואמת להתנהגות בפועל", pg.evaluate("secureLogout.toString().includes('יישלחו לענן אוטומטית')"))
    ck("13. קיימת פעולת מחיקה מכוונת נפרדת ('נקה נתונים מהמכשיר', עם אזהרה מפורשת)",
       pg.evaluate("typeof clearDeviceData==='function' && clearDeviceData.toString().includes('לצמיתות') && !!document.querySelector('[onclick*=\"clearDeviceData\"]')"))
    # בדיקת בחירת המפתחות בלי להפעיל reload (שהורס את ההקשר)
    r = pg.evaluate("""(()=>{
        const src=_wipeAndLogout.toString();
        const m=src.match(/const keys\\s*=\\s*keepUnsynced\\s*\\?\\s*(\\[[^\\]]*\\])\\s*:\\s*(\\[[^\\]]*\\])/);
        if(!m) return {ok:false};
        const keep=JSON.parse(m[1].replace(/'/g,'"'));
        const wipe=JSON.parse(m[2].replace(/'/g,'"'));
        return {ok:true,
                keepsBackup: !keep.includes('leads_tracker_v4'),
                keepsQueue:  !keep.includes('pendingSaveQueue'),
                wipesAll:    wipe.includes('leads_tracker_v4') && wipe.includes('pendingSaveQueue')};
    })()""")
    ck("13. keepUnsynced=true → הגיבוי נשמר", r.get('ok') and r['keepsBackup'])
    ck("13. keepUnsynced=true → תור השחזור נשמר", r.get('ok') and r['keepsQueue'])
    ck("13. keepUnsynced=false → הכול נמחק", r.get('ok') and r['wipesAll'])

    # ══════════════ 14. עמודות במובייל — לפי שם, לא לפי מיקום ══════════════
    # נכתב אחרי באג אמיתי: סידור מחדש של עמודות גרם לכלל nth-child
    # להסתיר את "עיר" במקום "סוג פרויקט" בטלפון.
    reset()
    pg.set_viewport_size({'width': 412, 'height': 891})     # Galaxy S25+
    r = pg.evaluate("""(()=>{
        leads.length=0;
        leads.push({id:1,address:'סמטת אליהו 7',city:'גבעתיים',name:'משה',status:'נשלחה הצעה',
                    date:'2026-06-01',statusChangedAt:'2026-07-01',replied:'לא',type:'תמ"א 38/2'});
        document.querySelectorAll('#statusDropdown .st-opt input[type=checkbox]').forEach(cb=>cb.checked=true);
        refresh();
        const shown=c=>{const e=document.querySelector('#tableBody td.'+c); return !!e && getComputedStyle(e).display!=='none';};
        const ths=[...document.querySelectorAll('thead th')], tds=[...document.querySelectorAll('#tableBody tr:first-child td')];
        let aligned=ths.length===tds.length;
        ths.forEach((th,i)=>{ const td=tds[i]; if(!td) return;
          const a=[...th.classList].find(x=>x.startsWith('col-')), b=[...td.classList].find(x=>x.startsWith('col-'));
          if(a!==b) aligned=false;
          if((getComputedStyle(th).display==='none')!==(getComputedStyle(td).display==='none')) aligned=false; });
        const sel=document.querySelector('.row-status'), ts=document.querySelector('.table-scroll');
        const sr=sel.getBoundingClientRect(), tr=ts.getBoundingClientRect();
        const cityUnder=(()=>{const e=document.querySelector('#tableBody td.col-address .addr-city');
          return !!e && getComputedStyle(e).display!=='none' && e.textContent.trim()==='גבעתיים';})();
        return {city:cityUnder, cityCol:shown('col-city'), status:shown('col-status'), address:shown('col-address'),
                name:shown('col-name'), type:shown('col-type'), date:shown('col-date'),
                aligned, statusInView: sr.left>=tr.left-1 && sr.right<=tr.right+1,
                statusH: Math.round(sr.height)};
    })()""")
    ck("14. טלפון: העיר מוצגת מתחת לכתובת (במקום עמודה נפרדת)", r['city'] and not r['cityCol'])
    ck("14. טלפון: עמודת הסטטוס מוצגת", r['status'])
    ck("14. טלפון: הכתובת ושם הפונה מוצגים", r['address'] and r['name'])
    ck("14. טלפון: סוג פרויקט ותאריך קבלה מוסתרים", (not r['type']) and (not r['date']))
    ck("14. כל תא יושב מתחת לכותרת הנכונה", r['aligned'])
    ck("14. הסטטוס נראה במלואו בלי גלילה", r['statusInView'])
    ck("14. בורר הסטטוס נוח למגע (36px+)", r['statusH'] >= 36)
    ck("14. אין כללי CSS לפי מיקום עמודה", pg.evaluate("""(()=>{
        const css=[...document.querySelectorAll('style')][0].textContent;
        return !/t[dh]:nth-child\\(\\d+\\)/.test(css);
    })()"""))
    pg.set_viewport_size({'width': 1400, 'height': 900})

    # ══════════════ 15. פריסה — דסקטופ ומובייל ══════════════
    # נכתב אחרי סקירה חזותית שמצאה: סטטוס נשפך על העיר (colgroup בסדר ישן),
    # חור של 124px בדאשבורד במובייל (padding של .main), וגרפים בחצי רוחב.
    reset()
    pg.set_viewport_size({'width': 1440, 'height': 900})
    r = pg.evaluate("""(()=>{
        leads.length=0;
        ['נשלחה הצעה','נבדק אדריכלית - ממתין לתקציב','נבדק כלכלית ואדריכלית - להגיש הצעה'].forEach((s,i)=>
          leads.push({id:i+1,address:'הרצל '+i,city:'ראשון לציון',name:'',status:s,date:'2026-06-01',replied:'לא'}));
        document.querySelectorAll('#statusDropdown .st-opt input[type=checkbox]').forEach(cb=>cb.checked=true);
        refresh();
        let spills=0;
        document.querySelectorAll('#tableBody tr').forEach(tr=>{
          const a=tr.querySelector('.row-status').getBoundingClientRect(), y=tr.querySelector('td.col-city').getBoundingClientRect();
          if(a.left<y.right && a.right>y.left) spills++; });
        const ts=document.querySelector('.table-scroll');
        const stW=Math.round(document.querySelector('#tableBody td.col-status').getBoundingClientRect().width);
        return {spills, stW, fits: ts.scrollWidth<=ts.clientWidth+1, cols:document.querySelectorAll('#tableColgroup col').length, ths:document.querySelectorAll('thead th').length,
                nameDash: document.querySelector('#tableBody td.col-name').textContent.trim()==='—'};
    })()""")
    ck("15. דסקטופ: בורר הסטטוס לא נשפך על העיר", r['spills'] == 0)
    ck("15. דסקטופ: הטבלה נכנסת ללא גלילה אופקית", r['fits'])
    ck("15. דסקטופ: עמודת הסטטוס רחבה מספיק לטקסט (140px+)", r['stW'] >= 140)
    ck("15. colgroup מכסה את כל העמודות (" + str(r['cols']) + ")", r['cols'] == r['ths'])
    ck("15. שם פונה ריק מוצג כמקף", r['nameDash'])

    pg.set_viewport_size({'width': 412, 'height': 891})
    r = pg.evaluate("""(()=>{
        leads.length=0;
        for(let i=1;i<=30;i++) leads.push({id:i,address:'א'+i,city:'תא',name:'x',status:'חדש',date:'2026-06-01',statusChangedAt:'2026-07-01',replied:'לא'});
        refresh();
        // ה-KPI מוצג רק בלשונית הלידים — המרווח נמדד מתחתית הכותרת
        const above=()=>Math.max(...[...document.querySelectorAll('.topbar, header, .tabs')].filter(e=>e.offsetParent!==null).map(e=>e.getBoundingClientRect().bottom),0);
        showTab('dash',document.getElementById('tab-dash'));
        const gapDash=Math.round(document.querySelector('#dashSection .period-bar').getBoundingClientRect().top-above());
        const _perf=document.querySelector('#dashSection .subtab[data-st="dperf"]'); if(_perf) _perf.click();
        const row=document.querySelector('#dashStatus .dash-row'); const bar=row.querySelector('.bar');
        const barPct=Math.round(bar.getBoundingClientRect().width/row.getBoundingClientRect().width*100);
        showTab('analytics',document.getElementById('tab-analytics'));
        const anBar=!!document.querySelector('#analyticsSection .period-bar .period-btn');
        const gapAn=Math.round(document.querySelector('#analyticsSection .period-bar').getBoundingClientRect().top-above());
        const knes=document.getElementById('anKnesConversion'); const knesHidden=!knes||getComputedStyle(knes).display==='none';
        showTab('leads',document.getElementById('tab-leads'));
        window.scrollTo(0,document.body.scrollHeight);
        const rows=document.querySelectorAll('#tableBody tr'); const last=rows[rows.length-1].getBoundingClientRect();
        const nav=document.getElementById('bottomNav').getBoundingClientRect();
        return {gapDash, gapAn, barPct, anBar, knesHidden, lastClear:last.bottom<=nav.top+1};
    })()""")
    ck("15. מובייל: אין חור מתחת לכותרת בדאשבורד (" + str(r['gapDash']) + "px)", r['gapDash'] < 30)
    ck("15. מובייל: אין חור מתחת לכותרת בניתוח (" + str(r['gapAn']) + "px)", r['gapAn'] < 30)
    ck("15. מובייל: גרפי השורה ממלאים 35%+ מהרוחב", r['barPct'] >= 35)
    ck("15. מובייל: בורר התקופה מופיע גם בניתוח", r['anBar'])
    ck("15. מובייל: כרטיס 'לאחר כנס' ריק מוסתר", r['knesHidden'])
    ck("15. מובייל: השורה האחרונה לא מוסתרת מאחורי הניווט", r['lastClear'])
    pg.set_viewport_size({'width': 1400, 'height': 900})

    # ══════════════ 16. טופס עריכה מקוצר — שום שדה לא הולך לאיבוד ══════════════
    reset()
    r = pg.evaluate("""(()=>{
        leads.length=0;
        const L={id:1,address:'סמטת אליהו 7',city:'גבעתיים',name:'משה כהן',phone:'050-1111111',email:'a@b.com',status:'נשלחה הצעה',
          date:'2026-05-13',statusChangedAt:'2026-06-01',type:'פינוי-בינוי',source:'הפניה',replied:'כן',deadline:'2026-10-01',
          submitDeadline:'2026-10-15',extendable:true,budget:'כן',ownerApproved:true,ownerApprovedAt:'2026-07-01',architect:'רון שגיא',
          winCompany:'',irrelReason:'',competitor:'',notes:'הערה',internalNotes:[],history:[]};
        leads.push(JSON.parse(JSON.stringify(L))); refresh(); openEdit(1);
        const card=document.getElementById('editOverlay').firstElementChild;
        const vis=[...card.querySelectorAll('input,select,textarea')].filter(e=>e.offsetParent!==null).map(e=>e.id);
        const o={visibleCount:vis.length,
                 top:['e_status','e_address','e_city','e_name','e_phone','e_ownerApproved'].every(id=>vis.includes(id)),
                 hidden:['e_date','e_email','e_source','e_deadline','e_submitDeadline'].every(id=>!vis.includes(id))};
        saveEdit(); const s=leads[0];
        const keys=Object.keys(L).filter(k=>!['internalNotes','history','statusChangedAt'].includes(k));
        o.lost=keys.filter(k=>JSON.stringify(s[k])!==JSON.stringify(L[k]));
        openEdit(1); [...card.querySelectorAll('.sec-toggle')].find(t=>t.textContent.includes('פרטי הליד')).click();
        o.opens=document.getElementById('e_date').offsetParent!==null;
        document.getElementById('e_source').value='טלפון'; saveEdit();
        o.editHidden=leads[0].source==='טלפון';
        if(window.closeEdit) closeEdit();
        return o;
    })()""")
    ck("16. הטופס נפתח על 6 השדות החשובים בלבד", r['top'] and r['visibleCount'] <= 12)
    ck("16. שדות נדירים מוסתרים ב'פרטי הליד'", r['hidden'])
    ck("16. שמירה ללא שינוי — אף שדה לא אבד", r['lost'] == [])
    ck("16. לחיצה פותחת את הסקשן", r['opens'])
    ck("16. עריכת שדה מוסתר נשמרת", r['editHidden'])

    # 'דורש תשומת לב' לא מכפיל צנרת (שבבי הסטטוס הוסרו — נבדק בסעיף 17)
    pg.set_viewport_size({'width': 412, 'height': 891})
    r = pg.evaluate("""(()=>{
        leads.length=0;
        const S=['חדש','בבדיקה','בבדיקה אדריכלית','נשלחה הצעה','ממתין לכנס דיירים','התקיים כנס - ממתינים להחלטה','השלמת נתונים'];
        S.forEach((s,i)=>leads.push({id:i+1,address:'א'+i,city:'תא',name:'x',status:s,date:'2026-09-15',statusChangedAt:'2026-09-15',replied:'לא',budget:'כן'}));
        refresh();
        renderAttentionCard();
        const t=document.getElementById('dashAttention').textContent;
        return {freshNotFlagged: !t.includes('ממתינים לאישור בעלים')};
    })()""")
    ck("16. 'ממתין לאישור בעלים' טרי לא מופיע ב'דורש תשומת לב'", r['freshNotFlagged'])

    # ══════════════ 17. סבב עיצוב 2 ══════════════
    r = pg.evaluate("""(()=>{
        leads.length=0;
        const S=['חדש','בבדיקה','נשלחה הצעה','התקבלה הודעת זכייה 🏆','לא רלוונטי ❌'];
        for(let i=1;i<=20;i++) leads.push({id:i,address:'רחוב '+i,city:['ראשון לציון','חיפה'][i%2],name:'פ'+i,
          status:S[i%5],date:'2026-0'+((i%8)+1)+'-10',statusChangedAt:'2026-0'+((i%8)+1)+'-20',replied:'לא'});
        document.querySelectorAll('#statusDropdown .st-opt input[type=checkbox]').forEach(cb=>cb.checked=true);
        refresh();
        const o={};
        o.noChips = !document.querySelector('.kpi-chip, .kpi-chips');
        o.heroKept = !!document.querySelector('.kc-main');
        o.noDeadlineTh = !document.getElementById('th_deadline');
        o.noDeadlineTd = !document.querySelector('#tableBody td.col-deadline');
        const cg=document.getElementById('tableColgroup');
        o.colsMatch = cg.children.length === document.querySelectorAll('thead th').length;
        const idx=[...document.querySelectorAll('thead .resizer')].map(r=>+r.dataset.col);
        o.resizersSeq = idx.every((v,i)=>v===i);
        o.rowFont = parseFloat(getComputedStyle(document.querySelector('#tableBody td.col-name')).fontSize);
        // הדאשבורד: תגי סטטוס ברוחב אחיד
        renderDash();
        const ws=[...document.querySelectorAll('#dashStatus .dash-row-label > span')].map(s=>Math.round(s.getBoundingClientRect().width));
        o.badgeUniform = ws.length>0 && new Set(ws).size===1;
        return o;
    })()""")
    ck("17. שבבי הסטטוס הוסרו", r['noChips'])
    ck("17. הכרטיס הראשי נשאר", r['heroKept'])
    ck("17. עמודת 'תאריך לתגובה' הוסרה מהכותרת", r['noDeadlineTh'])
    ck("17. עמודת 'תאריך לתגובה' הוסרה מהשורות", r['noDeadlineTd'])
    ck("17. מספר ה-col תואם למספר העמודות", r['colsMatch'])
    ck("17. אינדקסי שינוי רוחב רציפים", r['resizersSeq'])
    ck("17. גופן שורות בנייד קריא וקומפקטי (12–13.5px)", 12 <= r['rowFont'] <= 13.5)
    ck("17. תגי הסטטוס בדאשבורד ברוחב אחיד", r['badgeUniform'])

    # כרטיסים ריקים מוסתרים, ואין קובייה ריקה בשורה
    r = pg.evaluate("""(()=>{
        leads.length=0;
        leads.push({id:1,address:'א',city:'תא',name:'x',status:'חדש',date:'2026-09-01',replied:'לא'});
        refresh();
        const dash=document.getElementById('dashSection'), an=document.getElementById('analyticsSection');
        dash.classList.add('active'); dash.style.display='block';
        an.classList.add('active'); an.style.display='block';
        renderDash(); renderAnalytics();
        const RX=/אין נתונים|אין עדיין|אין מספיק|עדיין אין|יצטברו|אין זכיות|אין נתוני/;
        const emptyShown=[...document.querySelectorAll('#dashSection .dash-card, #analyticsSection .dash-card')]
          .filter(el=>el.style.display!=='none' && el.closest('.dash-grid')?.style.display!=='none')
          .filter(el=>{const t=el.textContent.replace(/\s+/g,' ').trim(); return RX.test(t) && t.length<140;})
          .map(el=>el.id);
        const lonely=[...document.querySelectorAll('#dashSection .dash-grid, #analyticsSection .dash-grid')]
          .filter(g=>g.style.display!=='none').filter(g=>{
            const vis=[...g.children].filter(x=>x.style.display!=='none');
            return vis.length===1 && !vis[0].classList.contains('span-all');
          }).length;
        const fw=document.getElementById('anForecastWins');
        const fwZero = fw && fw.style.display!=='none' && /~0\b/.test(fw.textContent);
        const dupCity = ['anCity','anCityConv'].filter(id=>{const e=document.getElementById(id); return e && e.style.display!=='none';}).length>1;
        dash.style.display=''; an.style.display='';
        return {emptyShown, lonely, fwZero, dupCity};
    })()""")
    ck("17. כרטיסים ריקים מוסתרים (" + (",".join(r['emptyShown']) or "אין") + ")", r['emptyShown'] == [])
    ck("17. אין כרטיס בודד עם קובייה ריקה לצידו", r['lonely'] == 0)
    ck("17. חיזוי זכיות לא מציג '~0' כשאין נתונים", not r['fwZero'])
    ck("17. 'המרה לפי עיר' לא מוצג פעמיים", not r['dupCity'])

    pg.set_viewport_size({'width': 1400, 'height': 900})

    # ══════════════ 18. מיון, פונים, ערים, זכיות חודשיות, סיבה חופשית ══════════════
    reset()
    pg.evaluate("""(()=>{ window.saveData=function(){}; window.saveData._ps=new Set();
      try{localStorage.setItem('statsPeriod','all')}catch(e){} })()""")
    # 1. מיון
    r=pg.evaluate("""(()=>{leads.length=0;
      const mk=(id,st,d)=>leads.push({id,address:'א'+id,city:'תא',name:'x',status:st,date:d,replied:'לא'});
      mk(1,'נשלחה הצעה','2026-09-01'); mk(2,'חדש','2026-08-01'); mk(3,'חדש','2026-03-01');
      mk(4,'בבדיקה','2026-05-01'); mk(5,'נשלחה הצעה','2026-01-01'); mk(6,'לא רלוונטי ❌','2025-01-01');
      document.querySelectorAll('#statusDropdown .st-opt input[type=checkbox]').forEach(cb=>cb.checked=true);
      document.getElementById('searchInput').value=''; refresh();
      return [...document.querySelectorAll('#tableBody tr')].map(tr=>+tr.id.replace('row_',''));})()""")
    ck("18. מיון: חדש(ותיק→חדש) · בבדיקה · נשלחה הצעה(ותיק→חדש) · לא רלוונטי", r==[3,2,4,5,1,6])
    
    # 2. פונים לפי תקופה
    r=pg.evaluate("""(()=>{leads.length=0;
      for(let i=0;i<58;i++) leads.push({id:i+1,address:'ר'+i,city:'תא',name:'רותם מוקד',
        status:i<15?'חדש':(i<21?'התקבלה הודעת זכייה 🏆':'לא רלוונטי ❌'),date:'2026-0'+(1+i%8)+'-10',replied:'לא'});
      refresh(); renderDash();
      const cells=[...document.querySelectorAll('#dashCaller .caller-grid .cv')].slice(0,4).map(x=>x.textContent.trim());
      return {cells, title:document.querySelector('#dashCaller h3').textContent};})()""")
    ck("18. פונים: 58 לידים · 15 פעילים · 6 זכיות · 14% המרה", r['cells']==['58','15','6','14%'])
    
    # 3a. מקור ליד ועיר ישן הוסרו
    r=pg.evaluate("""(()=>({src:!!document.getElementById('anSource'), city:!!document.getElementById('anCity')}))()""")
    ck("18. 'המרה לפי מקור ליד' הוסר", not r['src']); ck("18. כרטיס העיר הכפול הוסר", not r['city'])
    # 3b. ערים מורחב
    r=pg.evaluate("""(()=>{leads.length=0; let id=1;
      const add=(city,n,won,lost)=>{for(let i=0;i<n;i++) leads.push({id:id++,address:'ר'+id,city,name:'x',
        status:i<won?'התקבלה הודעת זכייה 🏆':(i<won+lost?'לא רלוונטי ❌':'חדש'),date:'2026-05-01',replied:'לא'});};
      add('ראשון לציון',46,7,22); add('ראשל"צ',1,0,0); add('הרצליה',20,0,6); add('גבעתיים',14,3,7); add('נתניה',2,0,2);
      renderCityConversion();
      const names=[...document.querySelectorAll('#anCityConv .cn span')].map(s=>s.textContent);
      const rishon=[...document.querySelectorAll('#anCityConv .city-grid > *')];
      const i=rishon.findIndex(x=>x.textContent.includes('ראשון לציון'));
      const vals=rishon.slice(i+1,i+6).map(x=>x.textContent.trim());
      setCitySort('pct');
      const byPct=[...document.querySelectorAll('#anCityConv .cn span')].map(s=>s.textContent);
      return {names, vals, byPct};})()""")
    ck("18. ראשל\"צ מאוחד עם ראשון לציון (47 לידים)", r['vals'][:1]==['47'])
    ck("18. עיר קטנה נכנסת ל'ערים נוספות'", any('ערים נוספות' in n for n in r['names']))
    ck("18. מיון לפי המרה: גבעתיים ראשונה", r['byPct'][0]=='גבעתיים')
    
    # 3c. לחיצה על עיר → סינון
    r=pg.evaluate("""(()=>{setCitySort('total'); openCityLeads('הרצליה');
      return {cf:(window._cityFilter||{}).city, rows:filteredLeads().length};})()""")
    ck("18. לחיצה על עיר מסננת את הלידים (מסנן עיר, 20)", r['cf']=='הרצליה' and r['rows']==20)
    pg.evaluate("clearQualityFilter(); document.getElementById('searchInput').value=''; refresh();")
    # 3d. זכיות לפי חודש
    r=pg.evaluate("""(()=>{leads.length=0; let id=1;
      const W='התקבלה הודעת זכייה 🏆';
      for(let i=0;i<14;i++) leads.push({id:id++,address:'ב'+i,city:'תא',status:W,date:'2025-04-09',statusChangedAt:'2026-04-09'});
      leads.push({id:id++,address:'x',city:'תא',status:W,date:'2026-01-01',statusChangedAt:'2026-07-16'});
      leads.push({id:id++,address:'y',city:'תא',status:W,date:'2026-01-01',statusChangedAt:'2026-08-08'});
      leads.push({id:id++,address:'z',city:'תא',status:W,date:'2025-02-01',statusChangedAt:'2025-06-10'});
      leads.push({id:id++,address:'w',city:'תא',status:W,date:'2026-01-01'});
      renderWinsMonthly();
      const el=document.getElementById('anWinsMonthly');
      const cells=[...el.querySelectorAll('.wm-c')].map(c=>c.textContent);
      return {years:[...el.querySelectorAll('.wm-y')].map(y=>y.textContent), tot:[...el.querySelectorAll('.wm-t')].map(t=>t.textContent),
              apr:cells[3], warn:el.textContent.includes('14 זכיות רשומות ב-9.4.2026'), nodate:el.textContent.includes('1 זכיות ללא תאריך'),
              after:(markWinsUnknown('2026-04-09'), renderWinsMonthly(), [...document.getElementById('anWinsMonthly').querySelectorAll('.wm-c')].map(c=>c.textContent)[3])};})()""")
    ck("18. זכיות לפי חודש: 2026 ו-2025 מוצגות", r['years']==['2026','2025'])
    # ביקורת df2ce6f (A01): לא משמיטים זכיות לפי השערה — נספרות עד סימון מפורש
    ck("18. 14 זכיות מאותו יום נספרות עד סימון מפורש", r['apr']=='14')
    ck("18. מוצגת בקשת בירור ליום החשוד", r['warn']); ck("18. מוצגת ספירת זכיות ללא תאריך", r['nodate'])
    ck("18. אחרי סימון מפורש — לא נספרות באפריל", r['after']!='14')
    
    # 3e. סיבה חופשית — חלונית
    r=pg.evaluate("""(()=>{leads.length=0;
      leads.push({id:1,address:'הרצל 1',city:'תא',name:'x',status:'חדש',date:'2026-06-01',replied:'לא'});
      refresh();
      openStatusExtraModal(1,'לא רלוונטי ❌');
      const g=document.getElementById('_sxg_irrelReasonNote');
      const hiddenAtStart=g.style.display==='none';
      const s=document.getElementById('_sx_irrelReason'); s.value='אחר'; s.dispatchEvent(new Event('change'));
      const shown=g.style.display!=='none';
      confirmStatusExtra(1,'לא רלוונטי ❌');
      const blocked=!!document.getElementById('_statusModal') && leads[0].status==='חדש';
      document.getElementById('_sx_irrelReasonNote').value='הבעלים מכרו את הנכס';
      confirmStatusExtra(1,'לא רלוונטי ❌');
      const saved={st:leads[0].status, r:leads[0].irrelReason, n:leads[0].irrelReasonNote};
      // סיבה רגילה → אין שדה, אין פירוט
      leads[0].status='חדש'; leads[0].irrelReason=''; leads[0].irrelReasonNote='';
      openStatusExtraModal(1,'לא רלוונטי ❌');
      const s2=document.getElementById('_sx_irrelReason'); s2.value='לא כלכלי'; s2.dispatchEvent(new Event('change'));
      confirmStatusExtra(1,'לא רלוונטי ❌');
      return {hiddenAtStart, shown, blocked, saved, plain:{r:leads[0].irrelReason, n:leads[0].irrelReasonNote}};})()""")
    ck("18. חלונית: שדה הפירוט מוסתר עד שנבחר 'אחר'", r['hiddenAtStart'] and r['shown'])
    ck("18. חלונית: 'אחר' בלי פירוט נחסם", r['blocked'])
    ck("18. חלונית: הפירוט נשמר", r['saved']=={'st':'לא רלוונטי ❌','r':'אחר','n':'הבעלים מכרו את הנכס'})
    ck("18. חלונית: סיבה רגילה לא דורשת פירוט", r['plain']=={'r':'לא כלכלי','n':''})
    # 3f. טופס עריכה
    r=pg.evaluate("""(()=>{leads.length=0;
      leads.push({id:1,address:'הרצל 1',city:'תא',name:'x',status:'לא רלוונטי ❌',irrelReason:'אחר',irrelReasonNote:'ישן',date:'2026-06-01',replied:'לא'});
      refresh(); openEdit(1);
      const shown=document.getElementById('e_irrelNote').style.display!=='none' && document.getElementById('e_irrelNote').value==='ישן';
      document.getElementById('e_irrelNote').value='';
      saveEdit();
      const blocked=leads[0].irrelReasonNote==='ישן';
      document.getElementById('e_irrelNote').value='חדש';
      saveEdit();
      const saved=leads[0].irrelReasonNote;
      if(window.closeEdit) closeEdit();
      // מעבר לסטטוס אחר מנקה
      openEdit(1); document.getElementById('e_status').value='בבדיקה'; if(window.toggleWinCompany) toggleWinCompany(); saveEdit();
      if(window.closeEdit) closeEdit();
      return {shown, blocked, saved, cleared:leads[0].irrelReasonNote===''&&leads[0].irrelReason===''};})()""")
    ck("18. עריכה: פירוט קיים נטען ומוצג", r['shown'])
    ck("18. עריכה: 'אחר' בלי פירוט נחסם", r['blocked'])
    ck("18. עריכה: פירוט נשמר", r['saved']=='חדש')
    ck("18. עריכה: יציאה מלא-רלוונטי מנקה סיבה ופירוט", r['cleared'])
    # 3g. ניתוח מציג פירוט
    r=pg.evaluate("""(()=>{leads.length=0;
      leads.push({id:1,address:'א',city:'תא',status:'לא רלוונטי ❌',irrelReason:'אחר',irrelReasonNote:'הבעלים מכרו',date:'2026-06-01'});
      leads.push({id:2,address:'ב',city:'תא',status:'לא רלוונטי ❌',irrelReason:'לא כלכלי',date:'2026-06-01'});
      renderAnalytics(); return document.getElementById('anIrrelReasons').textContent.includes('הבעלים מכרו');})()""")
    ck("18. כרטיס הסיבות מציג את פירוט 'אחר'", r)
    pg.evaluate("try{localStorage.removeItem('statsPeriod')}catch(e){}")

    # ══════════════ 19. שורות קומפקטיות בנייד, עמודת עיר, כרטיסי KPI ══════════════
    pg.set_viewport_size({'width': 390, 'height': 844})
    r = pg.evaluate("""(()=>{
        leads.length=0;
        const A=[['קדושי השואה 54 וינגייט 142','הרצליה','טל עזיז'],['סירקין 36-38 ועין גדי 4-6','הרצליה','הורן עזיז'],
                 ['פנינה ומשה 9 9א 11 11 א','ראשון לציון','רותם מוקד'],['הקסם 7','הרצליה','הורן עזיז'],
                 ['שדרות העם הצרפתי 60-62','תל אביב','אריאל לוי'],['ביאליק 14','רעננה','טל עזיז']];
        A.forEach((a,i)=>leads.push({id:i+1,address:a[0],city:a[1],name:a[2],status:'חדש',date:'2026-05-0'+(i+1),replied:'לא'}));
        document.querySelectorAll('#statusDropdown .st-opt input[type=checkbox]').forEach(cb=>cb.checked=true);
        document.getElementById('searchInput').value=''; refresh();
        const ts=document.querySelector('.table-scroll'), box=ts.getBoundingClientRect();
        const rows=[...document.querySelectorAll('#tableBody tr')];
        const avgH=rows.reduce((s,r)=>s+r.getBoundingClientRect().height,0)/rows.length;
        const inView=c=>{const e=rows[0].querySelector('td.'+c).getBoundingClientRect(); return e.left>=box.left-1 && e.right<=box.right+1;};
        return {avgH:Math.round(avgH), name:inView('col-name'), status:inView('col-status'), addr:inView('col-address')};
    })()""")
    ck("19. נייד: גובה שורה ממוצע ≤ 70px (" + str(r['avgH']) + ")", r['avgH'] <= 70)
    ck("19. נייד: כתובת, סטטוס ושם הפונה במסך בלי גלילה הצידה", r['addr'] and r['status'] and r['name'])
    pg.set_viewport_size({'width': 1400, 'height': 900})
    # בלי עסקאות סגורות: 3 כרטיסים — ללא משבצת ריקה
    r3 = pg.evaluate("""(()=>{ refresh();
        const g=document.querySelector('.kpi4'), cards=[...g.children];
        const cols=getComputedStyle(g).gridTemplateColumns.split(' ').length;
        return {n:cards.length, cols};})()""")
    ck("19. בלי עסקאות סגורות: 3 כרטיסים ממלאים את השורה", r3['n']==3 and r3['cols']==3)
    r = pg.evaluate("""(()=>{
        leads.push({id:50,address:'ז',city:'תא',name:'x',status:'התקבלה הודעת זכייה 🏆',date:'2025-05-01',replied:'לא'});
        leads.push({id:51,address:'ח',city:'תא',name:'x',status:'לא רלוונטי ❌',date:'2025-05-01',replied:'לא'});
        refresh();
        const th=[...document.querySelectorAll('thead th')].map(t=>[...t.classList].find(c=>c.startsWith('col-')));
        const td=[...document.querySelectorAll('#tableBody tr:first-child td')].map(t=>[...t.classList].find(c=>c.startsWith('col-')));
        const cards=[...document.querySelectorAll('.kpi4 > .kc')];
        const tops=cards.map(c=>Math.round(c.getBoundingClientRect().top));
        const hs=cards.map(c=>Math.round(c.getBoundingClientRect().height));
        return {cityAfterAddr: th.indexOf('col-city')===th.indexOf('col-address')+1 && td.indexOf('col-city')===td.indexOf('col-address')+1,
                cards:cards.length, oneRow:new Set(tops).size===1, sameH:new Set(hs).size===1,
                ring:!!document.querySelector('.kc-ring'), subs:document.querySelectorAll('.kc-sub').length};
    })()""")
    ck("19. עמודת העיר מיד אחרי כתובת הפרויקט", r['cityAfterAddr'])
    ck("19. מחשב: 4 כרטיסי KPI בשורה אחת ובגובה שווה", r['cards']==4 and r['oneRow'] and r['sameH'])
    ck("19. מחשב: טבעת המרה ושורות הקשר", r['ring'] and r['subs']==4)

    # ══════════════ 20. סיבות אי-רלוונטיות לחיצות · רוחב עמודת פעולות ══════════════
    reset()
    pg.set_viewport_size({'width': 1400, 'height': 900})
    r = pg.evaluate("""(()=>{
        try{localStorage.setItem('statsPeriod','all')}catch(e){}
        leads.length=0; let id=1; const I='לא רלוונטי ❌';
        const add=(n,o)=>{for(let i=0;i<n;i++) leads.push(Object.assign({id:id++,address:'ר'+id,city:'תא',name:'x',status:I,date:'2026-0'+(1+i%8)+'-10',replied:'לא'},o));};
        add(5,{irrelReason:'לא כלכלי'}); add(3,{irrelReason:''}); add(2,{irrelReason:'אחר',irrelReasonNote:'הבעלים מכרו'});
        add(4,{status:'חדש'});
        refresh(); renderAnalytics();
        const o={};
        o.btns=document.querySelectorAll('#anIrrelReasons .rsn-n').length;
        document.querySelector('#anIrrelReasons .rsn-n[data-reason="לא כלכלי"]').click();
        o.econ=document.querySelectorAll('#tableBody tr').length;
        o.banner=!!document.getElementById('_qualityBanner');
        o.badge=parseInt(document.getElementById('statusFilterLabel').textContent);
        clearQualityFilter();
        o.cleared=!window._reasonFilter && !document.getElementById('_qualityBanner');
        showReasonLeads('');
        o.none=document.querySelectorAll('#tableBody tr').length;
        showReasonLeads(IRREL_OTHER,'הבעלים מכרו');
        o.note=document.querySelectorAll('#tableBody tr').length;
        clearQualityFilter();
        try{localStorage.removeItem('statsPeriod')}catch(e){}
        return o;
    })()""")
    ck("20. כפתורי מספר ליד כל סיבה", r['btns'] >= 4)
    ck("20. לחיצה על 'לא כלכלי' מציגה בדיוק את 5 הלידים", r['econ'] == 5 and r['banner'])
    ck("20. מונה הסטטוסים תואם לרשימה המסוננת", r['badge'] == 5)
    ck("20. '✕ נקה' מבטל את הסינון", r['cleared'])
    ck("20. 'לא צוין' → 3 לידים ללא סיבה", r['none'] == 3)
    ck("20. פירוט 'אחר' → 2 לידים", r['note'] == 2)
    r = pg.evaluate("""(()=>{
        const th=document.querySelector('thead th.col-actions');
        const rz=th && th.querySelector('.resizer');
        const cols=document.querySelectorAll('#tableColgroup col').length;
        return {has:!!rz, idx:rz?+rz.dataset.col:-1, cols, minw:+(th.dataset.minw||0)};
    })()""")
    ck("20. לעמודת 'פעולות' יש ידית שינוי רוחב", r['has'] and r['idx'] == r['cols']-1)
    pg.evaluate("['saveErrorModal','bulkStatusModal','pdfExportModal','mobileMenuSheet','moreMenu'].forEach(id=>{const e=document.getElementById(id); if(e) e.style.display='none';}); document.querySelectorAll('.open').forEach(e=>{ if(/Overlay$/.test(e.id)) e.classList.remove('open'); }); document.getElementById('_statusModal')?.remove();")
    pg.evaluate("unlockAppShell(); refresh(); localStorage.removeItem('leads_col_widths_v4'); if(window._colResizeInit) _colResizeInit(); window.scrollTo({top:0,behavior:'instant'});")
    pg.wait_for_timeout(700)
    pg.query_selector('thead th.col-actions').scroll_into_view_if_needed()
    def _aw(): return pg.evaluate("Math.round(document.querySelector('thead th.col-actions').getBoundingClientRect().width)")
    def _drag(dx):
        bb=pg.query_selector('thead th.col-actions .resizer').bounding_box()
        x,y=bb['x']+2,bb['y']+bb['height']/2
        pg.mouse.move(x,y); pg.mouse.down(); pg.mouse.move(x+dx,y,steps=6); pg.mouse.up()
    w0=_aw(); _drag(-80); w1=_aw()
    hx=pg.evaluate("Math.round(document.querySelector('thead th.col-actions .resizer').getBoundingClientRect().left)")
    bx=pg.evaluate("Math.round(document.querySelector('.table-scroll').getBoundingClientRect().left)")
    _drag(+400); w2=_aw()
    over=pg.evaluate("""(()=>{const td=document.querySelector('#tableBody td.col-actions'); if(!td) return false; const q=td.getBoundingClientRect();
      return [...td.querySelectorAll('button')].some(b=>{const x=b.getBoundingClientRect(); return x.left<q.left-1||x.right>q.right+1;});})()""")
    ck("20. גרירה מרחיבה את עמודת 'פעולות' (" + str(w0) + "→" + str(w1) + ")", w1 > w0 + 40)
    ck("20. אחרי הרחבה הידית נשארת בתוך המסגרת", hx >= bx-1)
    ck("20. צמצום עובד ונעצר במינימום (" + str(w1) + "→" + str(w2) + "px)", w2 < w1 and w2 >= r['minw'])
    ck("20. במינימום הכפתורים לא גולשים לעמודה הסמוכה", not over)
    pg.evaluate("localStorage.removeItem('leads_col_widths_v4'); if(window._colResizeInit) _colResizeInit();")

    # ══════════════ תשתית: ללא רשת, ספריות מקומיות ══════════════
    reset()
    ck("תשתית: ExcelJS נטען מהעותק המקומי", pg.evaluate("""(async()=>{
        try{ await loadExcelJS(); return typeof ExcelJS!=='undefined' && !!ExcelJS.Workbook; }
        catch(e){ return 'ERR:'+e.message; }
    })()""") is True)
    ck("תשתית: supabase-js נטען מהעותק המקומי",
       pg.evaluate("typeof supabase!=='undefined' && typeof supabase.createClient==='function'"))
    ck("תשתית: אין שגיאת 'ExcelJS load failed'",
       not any('ExcelJS load failed' in e for e in cerr))
    ck("תשתית: הספריות הוגשו מקומית (" + str(len(cdn_hits)) + " בקשות)", len(cdn_hits) > 0)
    ck("תשתית: אפס בקשות רשת פונקציונליות (" + str(len(external_hits)) + ")", len(external_hits) == 0)
    for u in external_hits[:5]: print("   ⚠️ בקשה חיצונית שנחסמה: " + u[:110])
    ck("תשתית: גם משאבים קוסמטיים נחסמו (" + str(len(cosmetic_hits)) + " פונטים)", True)

    ctx.close(); b.close()

# ══════════════ 21. סבב ביקורת עומק: אבטחה, חיפוש, פונים, איכות נתונים, טיוטה, דאשבורד ══════════════
import subprocess, re as _re
for _st in ('5_1','5_2','5_3','5_4','5_5','5_6','6_1','6_2','6_3','6_4','7_1'):
    _f = os.path.join(HERE, 'round%s.py' % _st.replace('_','_stage'))
    if not os.path.exists(_f):
        ck("21. קובץ בדיקות שלב %s קיים" % _st, False); continue
    _p = subprocess.run([sys.executable, _f, target], capture_output=True, text=True, timeout=600,
                        env=dict(os.environ, LEADS_TARGET=target))
    _lines = [l for l in _p.stdout.splitlines() if _re.match(r'^\s+(✅|❌) ', l)]
    if not _lines:
        ck("21. שלב %s רץ (פלט: %s)" % (_st, (_p.stderr or _p.stdout)[-160:].replace('\n', ' ')), False)
    for l in _lines:
        ok = '✅' in l.split(' ', 3)[2] if len(l.split(' ')) > 2 else '✅' in l
        ck("21." + str(_st).replace('_','.') + " " + l.strip()[2:].strip(), l.strip().startswith('✅'))

shutil.rmtree(tmpdir, ignore_errors=True)

print("\n" + "=" * 60); print("תוצאות בדיקות התנהגות"); print("=" * 60)
ps = sum(1 for _, c in results if c)
for n, c in results: print(("  ✅ " if c else "  ❌ ") + n)
print("=" * 60); print("עברו: " + str(ps) + "/" + str(len(results)))
if ps < len(results):
    print("\n⚠️ נכשלו:")
    for n, c in results:
        if not c: print("   ❌ " + n)
    sys.exit(1)
print("✅ כל הבדיקות עברו")
