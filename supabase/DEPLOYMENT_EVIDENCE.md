# ראיות פריסה — Supabase

- **סביבה:** פרויקט ייצור `eemepnirijolwbwvokin` (Supabase Pro). אין סביבת staging.
- **מועד הבדיקה:** 23.09.2026, 20:07 UTC. כל הבדיקות בייצור — **קריאה בלבד** (קטלוג, ספירות). לא הופעל RPC משנה נתונים לצורך הוכחה.
- **נתוני ייצור לא שונו לצורך בדיקות.** אחרי הפריסה: 301 לידים, `app_meta.contacts` באורך 11,979 תווים, עדכון ליד אחרון 14:38 UTC (לפני הפריסה).

## היסטוריית migrations בייצור (`list_migrations`)
| גרסה | שם | בריפו |
|---|---|---|
| 20260730043023 | add_lead_audit_log | חלקית — טבלת lead_audit ב-baseline |
| 20260808194644 | add_update_contact_and_leads_rpc | לא — הפונקציה הוסרה ב-20260923 |
| 20260808200913 | rename_contact_atomic_rpc | לא — הפונקציה הוסרה ב-20260923 |
| 20260808202021 / 20260809051608 / 20260809052244 | rename_contact_and_leads (3 גרסאות) | `20260809_rename_contact_and_leads.sql` (הגרסה הסופית) |
| 20260923144031 | security_advisor_fixes_20260923 | `20260923_security_advisor_fixes.sql` |
| 20260923200719 | atomic_saves_20260923b | `20260923b_atomic_saves.sql` |
| (24.09.2026) | rename_changed_only_20260923c | `20260923c_rename_changed_only.sql` |
| (24.09.2026) | caller_rules_20260923d | `20260923d_caller_rules.sql` |

**לא בהיסטוריה (נוצרו ידנית ב-SQL Editor בהקמה):** הטבלאות leads, app_meta, מדיניות ה-RLS, `reserve_lead_ids`, וה-event trigger `ensure_rls`.
ה-DDL שלהם שוחזר מהקטלוג ל-`00000000000000_baseline_schema.sql` — לשחזור סביבת בדיקה בלבד.

## אופן ההחלה
- `security_advisor_fixes_20260923`, `atomic_saves_20260923b` — הוחלו בייצור דרך Supabase MCP (`apply_migration`), אחרי בדיקה מול PostgreSQL 16.2 מקומי ומבודד (`npm run test:db`).
- `rename_changed_only_20260923c` — גוף חדש לשתי פונקציות השינוי-שם (חתימה ותוצאה ללא שינוי): updated_at רק ללידים שערכיהם משתנים. תואם לגרסה הקודמת של האפליקציה.
- `caller_rules_20260923d` — פונקציה חדשה `merge_caller_rules` להחלטות זהות פונים (app_meta['caller_rules']); לא יוצרת נתונים עד שהמשתמש מאשר החלטה.
- `atomic_saves_20260923b` תוספתי בלבד: 4 פונקציות חדשות; ללא שינוי טבלאות/נתונים/פונקציות קיימות. הגרסה הקודמת של האפליקציה ממשיכה לעבוד (משתמשת ב-`rename_contact_and_leads` הקיימת).

## קטלוג פונקציות (pg_proc, 23.09.2026 20:07 UTC)
| פונקציה | ארגומנטים | SECURITY DEFINER | anon | authenticated | בודקת auth.uid() |
|---|---|---|---|---|---|
| upsert_leads_checked | p_rows jsonb | ✔ | ✘ | ✔ | ✔ |
| merge_contacts | p_upserts jsonb, p_deleted_ids jsonb, p_deleted_names jsonb | ✔ | ✘ | ✔ | ✔ |
| _merge_contacts_locked | p_upserts jsonb, p_deleted_ids jsonb | ✔ | ✘ | ✘ (פנימית) | — (נקראת רק מפונקציות שבודקות) |
| rename_contact_and_leads_v2 | p_upserts, p_deleted_ids, p_deleted_names jsonb; p_old_name, p_new_name, p_new_phone, p_new_email text → (lead_id, updated_at, contacts) | ✔ | ✘ | ✔ | ✔ |
| rename_contact_and_leads | p_contacts jsonb, p_deleted jsonb, 4×text → (lead_id bigint, updated_at timestamptz) | ✔ | ✘ | ✔ | ✔ |
| reserve_lead_ids | n integer → integer | ✔ | ✘ | ✔ | ✔ |
| merge_caller_rules | p_set jsonb, p_unset jsonb → jsonb | ✔ | ✘ | ✔ | ✔ |

`get_advisors(security)` אחרי הפריסה: אין ERROR. אזהרות: 5 הפונקציות שהאפליקציה קוראת להן זמינות ל-authenticated (מכוון; כולן בודקות UID בעלים), והגנת סיסמאות שדלפו כבויה (הגדרה בלוח הבקרה — בידי בעל הפרויקט).

## בדיקה חוזרת — 24.09.2026 04:12 UTC (קריאה בלבד)
- rename_contact_and_leads / _v2: כוללות את תנאי "רק מה שהשתנה" (IS DISTINCT FROM); הרשאות נשמרו (anon ✘, authenticated ✔).
- merge_caller_rules: anon ✘, authenticated ✔. `app_meta['caller_rules']` עדיין לא קיים (נוצר רק בהחלטה ראשונה של המשתמש).
- 301 לידים — ללא שינוי.
- כל פונקציה נבדקה לפני ההחלה מול PostgreSQL 16.2 מקומי ומבודד (`npm run test:db`), כולל הפונקציות הקיימות (rename_contact_and_leads, reserve_lead_ids).
