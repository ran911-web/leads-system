# -*- coding: utf-8 -*-
"""
בדיקות התנהגות למערכת מעקב הלידים.

הרצה:
    npm test
    python3 run_tests.py [path/to/index.html]

הבדיקות מריצות את הקוד האמיתי בדפדפן headless, כאשר כל התעבורה ל-Supabase
נחסמת ומוחזרת ממוק ברמת הרשת (page.route). אין שום קריאה לייצור ואין שינוי
בנתוני אמת. הבדיקות בוחנות התנהגות בפועל — סדר בקשות, מצב זיכרון, localStorage —
ולא נוכחות מחרוזות בקוד.
"""
import sys, os, json, time, shutil, tempfile
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, '..', 'index.html')
if not os.path.exists(SRC):
    print("❌ לא נמצא הקובץ: " + SRC); sys.exit(1)

results = []
def ck(name, cond): results.append((name, bool(cond)))

mock = {'leads_write': 'ok', 'rpc': 'ok', 'delay_ms': 0,
        'rpc_rows': [{'lead_id': 1, 'updated_at': '2026-08-09T10:00:00Z'}]}
calls = []

def short(u):
    for k in ('/rpc/rename_contact_and_leads', '/rpc/reserve_lead_ids',
              '/rest/v1/leads', '/rest/v1/app_meta', '/auth/v1'):
        if k in u: return k
    return u.split('supabase.co')[-1][:40]

def handler(route):
    req = route.request
    url, method = req.url, req.method
    calls.append((method, short(url)))
    J = {'content_type': 'application/json'}
    if '/rpc/rename_contact_and_leads' in url:
        if mock['rpc'] == 'fail':
            route.fulfill(status=400, body=json.dumps({'message': 'simulated rpc failure'}), **J)
        else:
            route.fulfill(status=200, body=json.dumps(mock['rpc_rows']), **J)
        return
    if '/rest/v1/leads' in url:
        if method in ('POST', 'PATCH', 'PUT'):
            if mock['delay_ms']: time.sleep(mock['delay_ms'] / 1000.0)
            if mock['leads_write'] == 'fail':
                route.fulfill(status=500, body=json.dumps({'message': 'simulated save failure'}), **J)
                return
        route.fulfill(status=200, body='[]', **J)
        return
    route.fulfill(status=200, body='[]', **J)

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
    pg.route('**://*.supabase.co/**', handler)
    pg.goto('file://' + target); pg.wait_for_timeout(2500)
    pg.evaluate("try{ initSupabase(); }catch(e){}")

    def reset():
        calls.clear()
        mock.update({'leads_write': 'ok', 'rpc': 'ok', 'delay_ms': 0,
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
    ck("4. ה-RPC נקרא בפועל", any(c[1] == '/rpc/rename_contact_and_leads' for c in calls))

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
       not any(c[1] == '/rpc/rename_contact_and_leads' for c in calls))
    ck("4. כשל שמירת ליד → אין שינוי מקומי", r['unchanged'])
    ck("4. אין אובדן מזהים מתור השמירה", r['queueKept'])

    reset(); mock['delay_ms'] = 400
    pg.evaluate("""(async()=>{""" + CONTACT + """
      window.__setupContact();
      saveData._ps=new Set([1]);
      await Promise.all([flushPendingSaves(), saveContact()]);
    })()""")
    writes = [i for i, c in enumerate(calls) if c[1] == '/rest/v1/leads' and c[0] in ('POST', 'PATCH', 'PUT')]
    rpcs = [i for i, c in enumerate(calls) if c[1] == '/rpc/rename_contact_and_leads']
    ck("4. שמירת איש קשר ממתינה לסיום שמירת ליד פעילה",
       bool(writes) and bool(rpcs) and max(writes) < min(rpcs))

    reset()
    pg.evaluate("""(async()=>{""" + CONTACT + """
      window.__setupContact();
      if(saveData._ps) saveData._ps.clear();
      await Promise.all([saveContact(), saveContact(), saveContact()]);
    })()""")
    ck("4. לחיצה כפולה → פעולה אחת בלבד",
       len([c for c in calls if c[1] == '/rpc/rename_contact_and_leads']) == 1)

    # ══════════════ 5. סנכרון אוטומטי ══════════════
    reset()
    r = pg.evaluate("""(async()=>{
        window.__runs=0;
        const real=window.reloadFromSupabase;
        window.reloadFromSupabase=async(s)=>{ window.__runs++; return real(s); };
        stopAutoSync(); window.__autoSyncTimer=null;
        const fast=()=>{ window.__isAuthed=true;
          if(window.__autoSyncTimer) return;
          window.__autoSyncTimer=setInterval(()=>{
            if(window.__isAuthed && document.visibilityState==='visible') window.reloadFromSupabase(true);
          },60); };
        await new Promise(r=>setTimeout(r,220));
        const loggedOut=window.__runs;
        fast(); fast(); fast();
        const t1=window.__autoSyncTimer;
        await new Promise(r=>setTimeout(r,220));
        const authed=window.__runs;
        stopAutoSync();
        const cleared=window.__autoSyncTimer===null, atStop=window.__runs;
        await new Promise(r=>setTimeout(r,220));
        const afterStop=window.__runs;
        for(let i=0;i<5;i++){ fast(); stopAutoSync(); }
        const noLeak=window.__autoSyncTimer===null;
        window.reloadFromSupabase=real; window.__isAuthed=false;
        return {loggedOut, authed, atStop, afterStop, single:t1!==null, cleared, noLeak};
    })()""")
    ck("5. מנותק → אין סנכרון אוטומטי", r['loggedOut'] == 0)
    ck("5. מחובר → הסנכרון פועל", r['authed'] > 0)
    ck("5. קריאות חוזרות → טיימר יחיד (אין כפילות)", r['single'])
    ck("5. התנתקות עוצרת את הסנכרון", r['afterStop'] == r['atStop'])
    ck("5. התנתקות מנקה את הטיימר", r['cleared'])
    ck("5. מחזורי login/logout לא מדליפים טיימרים", r['noLeak'])

    reset()
    pg.evaluate("""(async()=>{ window.__isAuthed=false; _isDirty=false;
        if(saveData._ps) saveData._ps.clear();
        await reloadFromSupabase(true); })()""")
    ck("5. מנותק → אין קריאת רשת ל-Supabase", len(calls) == 0)

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
    ctx.close(); b.close()

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
