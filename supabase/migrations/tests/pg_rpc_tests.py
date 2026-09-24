# בדיקות פונקציות השרת מול PostgreSQL אמיתי ומבודד (pgserver — שרת מקומי, בלי רשת ובלי הייצור).
# הסביבה נבנית מקובצי הריפו: baseline + atomic saves; auth.uid() ותפקידי Supabase מדומים.
import pgserver, subprocess, os, shutil, json, tempfile, sys
HERE=os.path.dirname(os.path.abspath(__file__)); MIG=os.path.dirname(HERE)
_dir=tempfile.mkdtemp(prefix='leads-pg-')
srv=pgserver.get_server(_dir, cleanup_mode='delete')
uri=srv.get_uri()
def q(sql, role=None, uid=None, expect_error=False):
    pre=''
    if uid: pre+=f"SELECT set_config('request.jwt.claim.sub','{uid}',false);"
    if role: pre+=f"SET ROLE {role};"
    p=subprocess.run(['psql',uri,'-X','-q','-t','-A','-v','ON_ERROR_STOP=1','-c',pre+sql],capture_output=True,text=True,
                     env=dict(os.environ,PATH=os.path.dirname(srv.pg_bin if hasattr(srv,'pg_bin') else '')+':'+os.environ['PATH']))
    out=(p.stdout+p.stderr).strip()
    return out
# psql binary location
import glob
pg_bin=os.path.dirname(glob.glob(os.path.join(os.path.dirname(pgserver.__file__),'**','bin','psql'),recursive=True)[0])
os.environ['PATH']=pg_bin+':'+os.environ['PATH']
setup="""
CREATE ROLE anon NOLOGIN; CREATE ROLE authenticated NOLOGIN;
CREATE SCHEMA auth;
CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT nullif(current_setting('request.jwt.claim.sub', true),'')::uuid $$;
GRANT USAGE ON SCHEMA auth TO anon, authenticated; GRANT EXECUTE ON FUNCTION auth.uid() TO anon, authenticated;
GRANT USAGE ON SCHEMA public TO anon, authenticated;
"""
print("setup:", q(setup) or "ok")
for f in ['00000000000000_baseline_schema.sql','20260809_rename_contact_and_leads.sql','20260923b_atomic_saves.sql','20260923c_rename_changed_only.sql','20260923d_caller_rules.sql']:
    p=subprocess.run(['psql',uri,'-X','-q','-v','ON_ERROR_STOP=1'],input=open(os.path.join(MIG,f),encoding='utf-8').read(),capture_output=True,text=True)
    print(f+":", (p.stdout+p.stderr).strip() or "ok")
    if p.returncode: sys.exit(1)
q("REVOKE ALL ON public.leads, public.app_meta, public.lead_audit FROM authenticated")
q("""INSERT INTO public.leads VALUES (1,'{"address":"א"}','2026-09-01 10:00:00.123456+00'),(2,'{"address":"ב"}','2026-09-01 10:00:00.5+00')""")
q("INSERT INTO public.app_meta VALUES ('nextId','100')")
q("""INSERT INTO public.app_meta VALUES ('contacts','[{"id":"c1","name":"רותם","phone":"1"},{"id":"c2","name":"טל","phone":"2"}]')""")

OWN='dc7c3190-93e3-462b-8b32-910c469a77a6'; OTH='00000000-0000-0000-0000-000000000001'
R=[]
def ck(n,c,info=''): R.append((n,bool(c),info))
F="SELECT json_agg(t) FROM public.upsert_leads_checked('%s'::jsonb) t;"
def up(rows,uid=OWN,role='authenticated'):
    out=q(F % json.dumps(rows,ensure_ascii=False).replace("'","''"),role,uid)
    try: return json.loads(out.splitlines()[-1])
    except Exception: return out
base1=q("SELECT to_json(updated_at)#>>'{}' FROM leads WHERE id=1")
r=up([{"id":1,"data":{"address":"א-עודכן"},"base":base1}])
ck("עדכון עם גרסת בסיס נכונה → ok", isinstance(r,list) and r[0]['o_status']=='ok', r)
new_ts=r[0]['o_updated_at'] if isinstance(r,list) else None
r2=up([{"id":1,"data":{"address":"דריסה"},"base":base1}])
ck("עדכון עם גרסת בסיס ישנה → conflict, בלי כתיבה", isinstance(r2,list) and r2[0]['o_status']=='conflict' and q("SELECT data->>'address' FROM leads WHERE id=1")=='א-עודכן', r2)
ck("conflict מחזיר את גרסת השרת ונתוניו", isinstance(r2,list) and r2[0]['o_server_data']['address']=='א-עודכן')
r3=up([{"id":1,"data":{"address":"עם בסיס חדש"},"base":new_ts}])
ck("עדכון מבוסס על הגרסה שהוחזרה → ok (השוואת זמן מדויקת)", isinstance(r3,list) and r3[0]['o_status']=='ok', r3)
r4=up([{"id":1,"data":{"address":"כפוי"},"base":base1,"force":True}])
ck("force (בחירת משתמש 'לשמור את שלי') → ok", isinstance(r4,list) and r4[0]['o_status']=='ok')
r5=up([{"id":50,"data":{"address":"חדש"},"base":None}])
ck("ליד חדש (בלי בסיס) → נוצר", isinstance(r5,list) and r5[0]['o_status']=='ok' and q("SELECT count(*) FROM leads WHERE id=50")=='1')
r6=up([{"id":77,"data":{"address":"נמחק"},"base":"2026-09-01T10:00:00+00:00"}])
ck("ליד שנמחק בשרת (עם בסיס) → deleted, לא נוצר מחדש", isinstance(r6,list) and r6[0]['o_status']=='deleted' and q("SELECT count(*) FROM leads WHERE id=77")=='0')
r7=up([{"id":2,"data":{"address":"ב"},"base":None}])
ck("ליד קיים בלי בסיס → conflict (לא דריסה עיוורת)", isinstance(r7,list) and r7[0]['o_status']=='conflict')
# rollback: שורה תקינה ואחריה שורה לא תקינה → כלום לא נכתב
b2=q("SELECT to_json(updated_at)#>>'{}' FROM leads WHERE id=2")
r8=up([{"id":2,"data":{"address":"לא אמור להישמר"},"base":b2},{"id":3,"data":"לא אובייקט"}])
ck("שורה לא תקינה בקריאה → rollback מלא (גם השורה התקינה לא נשמרה)", 'invalid row' in str(r8) and q("SELECT data->>'address' FROM leads WHERE id=2")=='ב', str(r8)[:120])
# הרשאות
r9=up([{"id":60,"data":{"a":1},"base":None}],uid=OTH)
ck("משתמש אחר → unauthorized", 'unauthorized' in str(r9))
r10=q(F % '[]','anon',None)
ck("anon → אין הרשאה להפעיל", 'permission denied' in r10, r10[:100])
ck("בלי הרשאת טבלה — אין עקיפה של הפונקציות", 'permission denied' in q("SELECT * FROM leads",'authenticated',OWN))
# אנשי קשר: שני "מכשירים" עם רשימות ישנות
M="SELECT public.merge_contacts('%s'::jsonb,'%s'::jsonb,NULL)::text;"
q(M % ('[{"id":"c1","name":"רותם","phone":"111"}]','[]'),'authenticated',OWN)       # מכשיר א: טלפון של c1
q(M % ('[{"id":"c2","name":"טל","phone":"222"}]','[]'),'authenticated',OWN)         # מכשיר ב: טלפון של c2
cur=json.loads(q("SELECT value FROM app_meta WHERE key='contacts'"))
ck("F05: שני מכשירים שמשנים אנשי קשר שונים — שני השינויים נשמרים", {c['id']:c['phone'] for c in cur}=={'c1':'111','c2':'222'}, cur)
q(M % ('[{"id":"c3","name":"חדש"}]','["c2"]'),'authenticated',OWN)
cur=json.loads(q("SELECT value FROM app_meta WHERE key='contacts'"))
ck("F05: מחיקה לפי מזהה והוספה — הסדר נשמר", [c['id'] for c in cur]==['c1','c3'], cur)
rb=q(M % ('[{"name":"בלי מזהה"}]','[]'),'authenticated',OWN)
ck("F05: איש קשר בלי מזהה → חריגה, בלי שינוי", 'contact id required' in rb and [c['id'] for c in json.loads(q("SELECT value FROM app_meta WHERE key='contacts'"))]==['c1','c3'])
ck("F05: anon לא יכול להפעיל", 'permission denied' in q(M % ('[]','[]'),'anon',None))
ck("F05: הפונקציה הפנימית לא נגישה ל-authenticated", 'permission denied' in q("SELECT public._merge_contacts_locked('[]','[]')",'authenticated',OWN))
# rename v2
q("INSERT INTO leads VALUES (90,'{\"name\":\"רותם\",\"address\":\"x\"}',now()),(91,'{\"name\":\"רותם\",\"address\":\"y\"}',now())")
out=q("SELECT json_agg(json_build_object('lead_id',t.lead_id)) FROM public.rename_contact_and_leads_v2('[{\"id\":\"c1\",\"name\":\"רותם מוקד\",\"phone\":\"111\"}]','[]',NULL,'רותם','רותם מוקד','111','') t",'authenticated',OWN)
print('   rename raw:', out[:200]); res=json.loads(out.splitlines()[-1])
ck("rename v2: שני הלידים עודכנו, איש הקשר מוזג (לא הוחלפה הרשימה)",
   sorted(r['lead_id'] for r in res)==[90,91] and q("SELECT count(*) FROM leads WHERE data->>'name'='רותם מוקד'")=='2'
   and [c['id'] for c in json.loads(q("SELECT value FROM app_meta WHERE key='contacts'"))]==['c1','c3'], res)
# rollback של rename: איש קשר לא תקין → גם הלידים לא משתנים
bad=q("SELECT public.rename_contact_and_leads_v2('[{\"name\":\"בלי מזהה\"}]','[]',NULL,'רותם מוקד','שם חדש','','')",'authenticated',OWN)
ck("rename v2: כשל באנשי קשר → rollback, הלידים לא שונו", 'contact id required' in bad and q("SELECT count(*) FROM leads WHERE data->>'name'='שם חדש'")=='0')
for n,c,i in R: print(("  ✅ " if c else "  ❌ ")+n+("" if c else "  → "+str(i)[:160]))
print(f"\n  עברו: {sum(1 for _,c,_ in R if c)}/{len(R)}  (PostgreSQL מקומי מבודד)")
print("גרסה:", q("SHOW server_version"))

# ── F11: שני לקוחות במקביל, אותה גרסת בסיס ──
import threading, time
bX=q("SELECT to_json(updated_at)#>>'{}' FROM leads WHERE id=2")
res={}
def client(name, addr, delay):
    sql=(f"SELECT set_config('request.jwt.claim.sub','{OWN}',false); SET ROLE authenticated; BEGIN; "
         f"SELECT o_status FROM public.upsert_leads_checked('[{{\"id\":2,\"data\":{{\"address\":\"{addr}\"}},\"base\":\"{bX}\"}}]'::jsonb); "
         f"SELECT pg_sleep({delay}); COMMIT;")
    p=subprocess.run(['psql',uri,'-X','-q','-t','-A','-c',sql],capture_output=True,text=True)
    res[name]=[l for l in p.stdout.split('\n') if l.strip() in ('ok','conflict')]
t1=threading.Thread(target=client,args=('A','מכשיר א',1.5)); t2=threading.Thread(target=client,args=('B','מכשיר ב',0))
t1.start(); time.sleep(0.3); t2.start(); t1.join(); t2.join()
final=q("SELECT data->>'address' FROM leads WHERE id=2")
ok_=res.get('A')==['ok'] and res.get('B')==['conflict'] and final=='מכשיר א'
print(("  ✅ " if ok_ else "  ❌ ")+f"F11: כתיבה מקבילה — הראשון נשמר, השני מקבל התנגשות ולא דורס (A={res.get('A')}, B={res.get('B')}, נשמר: {final})")

# ── סבב 7: הפונקציות הישנות + עדכון רק של לידים שהשתנו ──
R2=[]
def ck2(n,c,info=''): R2.append((n,bool(c),info))
q("INSERT INTO leads VALUES (201,'{\"name\":\"דנה\",\"phone\":\"050\",\"email\":\"\"}','2026-01-01T00:00:00Z'),(202,'{\"name\":\"דנה\",\"phone\":\"051\",\"email\":\"\"}','2026-01-01T00:00:00Z')")
out=q("SELECT json_agg(json_build_object('lead_id',t.lead_id,'updated_at',t.updated_at)) FROM public.rename_contact_and_leads('[{\"id\":\"c9\",\"name\":\"דנה\",\"phone\":\"050\"}]'::jsonb,NULL,'דנה','דנה','050','') t",'authenticated',OWN)
rows=json.loads(out.splitlines()[-1])
ck2("rename (ישנה): מחזירה lead_id ו-updated_at — המבנה שהאפליקציה קוראת", isinstance(rows,list) and set(rows[0].keys())=={'lead_id','updated_at'}, rows)
ck2("rename (ישנה): רק הליד שערכיו השתנו עודכן (202), 201 זהה ולא נגעו בו",
    [r['lead_id'] for r in rows]==[202] and q("SELECT updated_at FROM leads WHERE id=201")=='2026-01-01 00:00:00+00', rows)
bad=q("SELECT public.rename_contact_and_leads(NULL,NULL,'דנה','שם אחר','','')",'authenticated',OWN)
ck2("rename (ישנה): כשל (רשימה חסרה) → rollback, הלידים לא שונו", 'contacts payload required' in bad and q("SELECT count(*) FROM leads WHERE data->>'name'='שם אחר'")=='0')
ck2("rename (ישנה): משתמש אחר → unauthorized", 'unauthorized' in q("SELECT public.rename_contact_and_leads('[]',NULL,'x','y','','')",'authenticated',OTH))
ck2("rename (ישנה): anon → אין הרשאה", 'permission denied' in q("SELECT public.rename_contact_and_leads('[]',NULL,'x','y','','')",'anon',None))
q("INSERT INTO leads VALUES (203,'{\"name\":\"נועה\",\"phone\":\"1\",\"email\":\"\"}','2026-01-01T00:00:00Z'),(204,'{\"name\":\"נועה\",\"phone\":\"2\",\"email\":\"\"}','2026-01-01T00:00:00Z')")
out=q("SELECT json_agg(t.lead_id) FROM public.rename_contact_and_leads_v2('[]','[]',NULL,'נועה','נועה','1','') t WHERE t.lead_id IS NOT NULL",'authenticated',OWN)
ck2("rename v2: רק לידים שערכיהם השתנו מקבלים updated_at חדש", out.splitlines()[-1] in ('[204]',), out)
# reserve_lead_ids
r=q("SELECT public.reserve_lead_ids(3)",'authenticated',OWN).splitlines()[-1]
ck2("reserve_lead_ids: מחזירה את המזהה הראשון ומקדמת את המונה", r=='100' and q("SELECT value FROM app_meta WHERE key='nextId'")=='103', r)
ck2("reserve_lead_ids: כל מזהה מתועד ביומן", q("SELECT count(*) FROM lead_audit WHERE action='reserved' AND lead_id BETWEEN 100 AND 102")=='3')
ck2("reserve_lead_ids: n לא תקין נדחה בלי שינוי", 'invalid n' in q("SELECT public.reserve_lead_ids(0)",'authenticated',OWN) and q("SELECT value FROM app_meta WHERE key='nextId'")=='103')
ck2("reserve_lead_ids: משתמש אחר → unauthorized", 'unauthorized' in q("SELECT public.reserve_lead_ids(1)",'authenticated',OTH))
ck2("reserve_lead_ids: anon → אין הרשאה", 'permission denied' in q("SELECT public.reserve_lead_ids(1)",'anon',None))
got={}
def reserve(name):
    sql=f"SELECT set_config('request.jwt.claim.sub','{OWN}',false); SET ROLE authenticated; SELECT public.reserve_lead_ids(5);"
    pp=subprocess.run(['psql',uri,'-X','-q','-t','-A','-c',sql],capture_output=True,text=True)
    got[name]=int([l for l in pp.stdout.split('\n') if l.strip().isdigit()][-1])
ths=[threading.Thread(target=reserve,args=(i,)) for i in range(4)]
[t.start() for t in ths]; [t.join() for t in ths]
ranges=sorted((v,v+4) for v in got.values())
ck2("reserve_lead_ids: 4 הקצאות מקבילות — טווחים זרים, בלי חפיפה", all(ranges[i][1]<ranges[i+1][0] for i in range(len(ranges)-1)) and q("SELECT value FROM app_meta WHERE key='nextId'")=='123', ranges)
for n,c,i in R2: print(("  ✅ " if c else "  ❌ ")+n+("" if c else "  → "+str(i)[:160]))
print(f"  עברו (פונקציות קיימות): {sum(1 for _,c,_ in R2 if c)}/{len(R2)}")

# ── סבב 7: החלטות זהות פונים ──
R3=[]
def ck3(n,c,info=''): R3.append((n,bool(c),info))
MR="SELECT public.merge_caller_rules('%s'::jsonb,'%s'::jsonb)::text;"
q(MR % ('{"approved":{"רותם":"רותם מוקד"}}','{}'),'authenticated',OWN)                       # מכשיר א
q(MR % ('{"approved":{"טל עזיז ורותם מוקד":["טל עזיז","רותם מוקד"]}}','{}'),'authenticated',OWN)  # מכשיר ב
cur=json.loads(q("SELECT value FROM app_meta WHERE key='caller_rules'"))
ck3("caller_rules: שתי החלטות ממכשירים שונים נשמרות שתיהן", set(cur['approved'].keys())=={'רותם','טל עזיז ורותם מוקד'}, cur)
q(MR % ('{"rejected":{"אמיר":true}}','{"approved":["רותם"]}'),'authenticated',OWN)
cur=json.loads(q("SELECT value FROM app_meta WHERE key='caller_rules'"))
ck3("caller_rules: ביטול החלטה (unset) ודחייה", 'רותם' not in cur['approved'] and cur['rejected'].get('אמיר') is True, cur)
ck3("caller_rules: קלט לא תקין → חריגה בלי שינוי", 'object required' in q(MR % ('[]','{}'),'authenticated',OWN) and json.loads(q("SELECT value FROM app_meta WHERE key='caller_rules'"))==cur)
ck3("caller_rules: משתמש אחר / anon — חסומים", 'unauthorized' in q(MR % ('{}','{}'),'authenticated',OTH) and 'permission denied' in q(MR % ('{}','{}'),'anon',None))
for n,c,i in R3: print(("  ✅ " if c else "  ❌ ")+n+("" if c else "  → "+str(i)[:160]))
print(f"  עברו (החלטות זהות): {sum(1 for _,c,_ in R3 if c)}/{len(R3)}")

_ok=all(c for _,c,_ in R) and ok_ and all(c for _,c,_ in R2) and all(c for _,c,_ in R3)
print('\nexit:', 0 if _ok else 1)
sys.exit(0 if _ok else 1)
