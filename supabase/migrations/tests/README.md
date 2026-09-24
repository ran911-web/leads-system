# בדיקות — מערכת הלידים

## הרצה
```
npm run test:setup     # פעם אחת: Playwright + Chromium + pgserver (גרסאות מקובעות ב-requirements.txt)
npm run test:all       # תחביר/מבנה + בדיקות התנהגות + בדיקות PostgreSQL
```

| פקודה | מה נבדק | מול מה |
|---|---|---|
| `npm run test:syntax` | תחביר JS, איזון סוגריים/‏div/‏CSS, מזהים/פונקציות כפולים, אין service_role | סטטי |
| `npm test` | קוד המערכת האמיתי (index.html) בדפדפן: ממשק, זרימות, סנכרון, ייבוא/ייצוא Excel, PDF | שרת Supabase **מדומה** (ניתוב רשת / sb מזויף). אין פנייה לרשת: כל בקשה חיצונית נחסמת, ExcelJS ו-supabase-js מוגשים מ-`vendor/` (נעילה ב-`vendor/vendor-lock.json`) |
| `npm run test:db` | פונקציות השרת: השוואת גרסה אטומית, התנגשות, כתיבה מקבילה, rollback, הרשאות, מיזוג אנשי קשר | **PostgreSQL 16 אמיתי ומבודד** (pgserver), נבנה מקובצי ה-migrations שבריפו (baseline, rename, atomic saves, rename-changed-only, caller rules); כולל גם את הפונקציות הקיימות rename_contact_and_leads ו-reserve_lead_ids. לא נוגע בייצור |

## קבצים
- `run_tests.py` — בדיקות ההתנהגות הראשיות (סעיפים 1–20), ומריץ את השלבים `round5_stage1-6`, `round6_stage1-4` (סעיף 21).
- `round6_stage1.py` — תיקוני ביקורת df2ce6f (V01–V07, W01/W02, A01/A03, D05, D09, I01, N04, N06).
- `round6_stage2.py` — הגדרות סטטיסטיקה (F16, A04, N07, A05).
- `round6_stage3.py` — סנכרון: תור עמיד, tombstones, התנגשויות, חיווי (F02, D04, D06, D01, D02, F10, D07, D08, F05). קוד המערכת האמיתי מול `sb` מזויף עם "שערים" לעיכוב/שחרור בקשות; סמנטיקת upsert_leads_checked זהה לזו שנבדקת ב-`pg_rpc_tests.py`.
- `round6_stage4.py` — `startAutoSync` האמיתית עם שעון מבוקר (לא העתק של הלוגיקה).
- `round7_stage1.py` — סגירת פערים: זהות פונים מפורשת (ללא הסקה; מפריד " + "; הצעות לאישור/דחייה/ביטול), עדכון סטטוס במסה, מדדים לפי תאריכי אירוע + שורת הגדרה, ולידציה משותפת לכל מסלולי היצירה.
- `pg_rpc_tests.py` — פונקציות השרת מול PostgreSQL.
- רגישות: כל שלב נבדק גם מול הגרסה הקודמת (df2ce6f) ונכשל שם — ראה test-results.txt.

## הרצה ללא רשת
אחרי `npm run test:setup` כל הבדיקות רצות בלי גישה לרשת (נבדק: `unshare -n npm run test:all`). ראה test-results.txt.
