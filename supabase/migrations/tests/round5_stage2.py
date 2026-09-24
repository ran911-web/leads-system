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
    # 8. מילוי מהיר
    r=pg.evaluate("""(()=>{unlockAppShell(); try{localStorage.setItem('statsPeriod','all')}catch(e){}
      window.saveData=function(i){ (window.__saved=window.__saved||[]).push(i); }; window.saveData._ps=new Set();
      leads.length=0; const I='לא רלוונטי ❌';
      for(let i=1;i<=4;i++) leads.push({id:i,address:'ר'+i,city:'תא',name:'x',status:I,irrelReason:'',date:'2026-05-01',replied:'לא'});
      leads.push({id:9,address:'ז',city:'תא',name:'x',status:I,irrelReason:'לא כלכלי',date:'2026-05-01',replied:'לא'});
      refresh(); renderAnalytics();
      showReasonLeads('');
      const sels=document.querySelectorAll('#tableBody .row-reason').length;
      const s=document.querySelector('#tableBody .row-reason[data-lid="1"]'); s.value='לא כלכלי'; s.dispatchEvent(new Event('change'));
      const after={left:filteredLeads().length, reason:leads.find(l=>l.id===1).irrelReason, hist:(leads.find(l=>l.id===1).history||[]).length, saved:(window.__saved||[]).slice()};
      const s2=document.querySelector('#tableBody .row-reason[data-lid="2"]'); s2.value='אחר'; s2.dispatchEvent(new Event('change'));
      const modal=!!document.getElementById('_rnNote');
      document.querySelector('#_statusModal .btn-save').click();
      const blocked=!!document.getElementById('_statusModal') && !leads.find(l=>l.id===2).irrelReason;
      document.getElementById('_rnNote').value='הבעלים מכרו'; document.querySelector('#_statusModal .btn-save').click();
      const l2=leads.find(l=>l.id===2);
      const banner=document.querySelector('#_qualityBanner span').textContent;
      clearQualityFilter();
      const normal=document.querySelectorAll('#tableBody .row-reason').length;
      return {sels, after, modal, blocked, l2:{r:l2.irrelReason,n:l2.irrelReasonNote}, banner, normal};})()""")
    ck("8. במצב סינון 'ללא סיבה' מופיעה בחירת סיבה בכל שורה", r['sels']==4)
    ck("8. בחירה שומרת מיד והליד יוצא מהרשימה (נותרו 3)", r['after']['left']==3 and r['after']['reason']=='לא כלכלי')
    ck("8. נרשם ביומן השינויים ונשמר רק הליד הזה ("+str(r['after']['saved'])+")", r['after']['hist']==1 and r['after']['saved']==[1])
    ck("8. 'אחר' פותח חלונית פירוט", r['modal'])
    ck("8. פירוט ריק נחסם", r['blocked'])
    ck("8. 'אחר' + פירוט נשמרים", r['l2']=={'r':'אחר','n':'הבעלים מכרו'})
    ck("8. הבאנר מתעדכן במספר שנותר", 'נותרו 2' in r['banner'])
    ck("8. מחוץ למצב הסינון — בורר סטטוס רגיל", r['normal']==0)
    # גם מכרטיס איכות הנתונים
    r=pg.evaluate("""(()=>{showIncomplete('reason'); const n=document.querySelectorAll('#tableBody .row-reason').length; clearQualityFilter(); return n;})()""")
    ck("8. עובד גם מכרטיס 'איכות הנתונים'", r==2)
    # 9. תאריכי זכייה
    r=pg.evaluate("""(()=>{leads.length=0; window.__saved=[]; const W='התקבלה הודעת זכייה 🏆';
      for(let i=1;i<=6;i++) leads.push({id:i,address:'ב'+i,city:'תא',status:W,date:'2025-03-01',statusChangedAt:'2026-04-09'});
      leads.push({id:7,address:'x',city:'תא',status:W,date:'2026-01-01',statusChangedAt:'2026-07-16'});
      document.getElementById('tab-analytics').click();
      renderAnalytics(); renderWinsMonthly();
      const btn=[...document.querySelectorAll('#anWinsMonthly button')].find(b=>b.textContent.includes('עדכן תאריכי'));
      btn.click();
      const rows=document.querySelectorAll('#_winDateModal .wd-in').length;
      const i1=document.querySelector('#_winDateModal .wd-in[data-lid="1"]'); i1.value='2025-02-01';   // לפני תאריך הקבלה
      document.querySelector('#_winDateModal .btn-save').click();
      const errShown=document.getElementById('_wdErr').style.display==='block' && !leads[0].winDate;
      i1.value='2025-11-20'; document.querySelector('#_winDateModal .wd-in[data-lid="2"]').value='2026-02-10';
      document.querySelector('#_winDateModal .btn-save').click();
      renderWinsMonthly();
      const el=document.getElementById('anWinsMonthly');
      const years=[...el.querySelectorAll('.wm-y')].map(y=>y.textContent);
      const tot=[...el.querySelectorAll('.wm-t')].map(t=>t.textContent);
      return {rows, errShown, w1:leads[0].winDate, w2:leads[1].winDate, saved:window.__saved, years, tot,
              stillBulk:el.textContent.includes('4 זכיות רשומות ב-9.4.2026'), cells:[...el.querySelectorAll('.wm-c')].map(c=>c.textContent),  btnCount:(el.textContent.match(/עדכן תאריכי זכייה \\((\\d+)\\)/)||[])[1]};})()""")
    ck("9. הכלי מציג את 6 הזכיות מיום ההזנה המרוכזת", r['rows']==6)
    ck("9. תאריך לפני תאריך הקבלה נחסם", r['errShown'])
    ck("9. שני תאריכים נשמרו", r['w1']=='2025-11-20' and r['w2']=='2026-02-10' and sorted(r['saved'][-1])==[1,2])
    # שורות: 2026 (ינו..דצמ), 2025 — נובמבר 2025 = 1, פברואר 2026 = 1; 4 הנותרות עדיין נספרות באפריל (עד סימון)
    ck("9. הזכיות שתוקנו נכנסו לחודשים הנכונים", r['years']==['2026','2025'] and r['cells'][1]=='1' and r['cells'][12+10]=='1' and r['cells'][3]=='4')
    ck("9. 4 הנותרות עדיין מסומנות לבירור, והכפתור מציג 4", r['stillBulk'] and r['btnCount']=='4')
    b.close()
for n,c in P: print(("  ✅ " if c else "  ❌ ")+n)
print(f"\n  עברו: {sum(1 for _,x in P if x)}/{len(P)} | שגיאות: {[e for e in errs if 'supabase' not in e][:3]}")
