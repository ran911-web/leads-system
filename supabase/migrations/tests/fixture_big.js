(()=>{ unlockAppShell(); try{localStorage.setItem('statsPeriod','all')}catch(e){}
  leads.length=0; let id=1;
  const S=['חדש','בבדיקה','בבדיקה אדריכלית','נבדק אדריכלית - ממתין לתקציב','נבדק כלכלית ואדריכלית - להגיש הצעה','נשלחה הצעה','ממתין לכנס דיירים','התקיים כנס - ממתינים להחלטה','השלמת נתונים'];
  const C=['ראשון לציון','רעננה','הרצליה','תל אביב','גבעתיים','רמת גן','חיפה','נתניה','פתח תקווה','חולון'];
  const N=['רותם מוקד','טל עזיז','הורן עזיז','ירין דיגה','אריאל לוי','אמיר כספי','דניאל דיין'];
  const A=['קדושי השואה 54 וינגייט 142','סירקין 36-38 ועין גדי 4-6','הקסם 7','ביאליק 14','דרך מנחם בגין 132','שדרות העם הצרפתי 60-62','הבילויים 36-38 והמעפילים 5'];
  const R=['לא כלכלי','אחר','הלך למתחרה','תנאי שוק',''];
  const pad=n=>String(n).padStart(2,'0');
  for(let i=0;i<301;i++){
    const y= i<120?2025:2026, m=1+(i*7)%12, d=1+(i*5)%27;
    let st= i<70?S[i%9]:(i<94?'התקבלה הודעת זכייה 🏆':'לא רלוונטי ❌');
    leads.push({id:id++,address:A[i%7]+' '+i,city:C[i%10],name:N[i%7],status:st,type:i%4?'תמ"א 38/2':'פינוי-בינוי',source:['וואטספ','מייל','טלפון'][i%3],
      date:`${y}-${pad(m)}-${pad(d)}`, statusChangedAt: i%3?`${y}-${pad(Math.min(12,m+1))}-${pad(d)}`:'',
      replied:i%2?'כן':'לא',budget:i%3?'כן':'',ownerApproved:i%9===0,architect:st.includes('אדריכל')?'רון שגיא':'',
      irrelReason: st==='לא רלוונטי ❌'?R[i%5]:'', irrelReasonNote: (st==='לא רלוונטי ❌'&&R[i%5]==='אחר')?'הבעלים מכרו':'',
      winCompany: st.includes('זכייה')?'עמיסף':'', notes:i%4?'':'דיירים מעוניינים, לחזור אחרי החגים',
      internalNotes: i%5?[]:[{ts:'01/05/2026 10:00',text:'שיחה ראשונה'}],
      history: i%2?[{ts:'01/05/2026 10:00',iso:`${y}-${pad(m)}-${pad(d)}T10:00:00Z`,changes:[{field:'סטטוס',from:'חדש',to:st}]}]:[] });
  }
  document.querySelectorAll('#statusDropdown .st-opt input[type=checkbox]').forEach(cb=>cb.checked=true);
  refresh();
})()
