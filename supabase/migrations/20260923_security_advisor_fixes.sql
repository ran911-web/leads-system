-- הוחל בפועל על פרויקט הייצור eemepnirijolwbwvokin ב-23.9.2026 (apply_migration: security_advisor_fixes_20260923).
-- הקובץ כאן לתיעוד בריפו בלבד — אין להריץ שוב.

-- א1. התצוגה רצה בהרשאות המשתמש השואל (לא בהרשאות היוצר) — מדיניות "בעלים בלבד" חלה עליה
ALTER VIEW public.lead_audit_orphans SET (security_invoker = on);

-- א2. פונקציות ישנות משלבים קודמים שאינן בשימוש (הוחלפו ב-rename_contact_and_leads)
DROP FUNCTION IF EXISTS public.rename_contact_atomic(jsonb, jsonb, text, text, text, text);
DROP FUNCTION IF EXISTS public.update_contact_and_leads(jsonb, jsonb, text, text, text, text);

-- א3. פונקציית טריגר פנימית (הפעלת RLS אוטומטית לטבלאות חדשות) — לא נועדה לקריאה דרך ה-API
REVOKE EXECUTE ON FUNCTION public.rls_auto_enable() FROM PUBLIC, anon, authenticated;
