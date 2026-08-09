-- ============================================================================
-- 20260809_rename_contact_and_leads.sql
-- עדכון אטומי של איש קשר + כל הלידים המקושרים, בטרנזקציה אחת.
--
-- ✅ הורץ בפועל על פרויקט Supabase eemepnirijolwbwvokin (גרסה v3).
--    אומת מקצה לקצה עם רשומת TEST זמנית שנמחקה. לא שונו נתוני ייצור.
--    הרצה חוזרת בטוחה.
--
-- מה זה פותר:
--   עדכון שם פונה היה שתי בקשות נפרדות (app_meta ואז leads). אם השנייה נכשלה,
--   איש הקשר נשאר עם נתונים חדשים והלידים עם ישנים. כאן: או שהכול מצליח, או
--   ששום דבר לא משתנה.
--
-- הערות טיפוסים (הותאמו לסכימה האמיתית):
--   • app_meta.value הוא text  → ולכן p_contacts::text
--   • leads.id      הוא bigint → ולכן RETURNS TABLE(lead_id bigint, ...)
--     (גרסה קודמת השתמשה ב-integer ונכשלה בשגיאת התאמת טיפוסים.)
--
-- אבטחה: לא שונתה מדיניות ההתחברות או ההרשאות הקיימת.
--   SECURITY DEFINER + בדיקת auth.uid() פנימית + search_path קבוע.
--   EXECUTE ל-authenticated בלבד; anon חסום.
-- ============================================================================

DROP FUNCTION IF EXISTS public.rename_contact_and_leads(jsonb,jsonb,text,text,text,text);

CREATE OR REPLACE FUNCTION public.rename_contact_and_leads(
  p_contacts  jsonb,   -- מצב אנשי הקשר המוצע במלואו
  p_deleted   jsonb,   -- רשימת נמחקים; NULL = אל תיגע
  p_old_name  text,    -- השם הישן של הפונה
  p_new_name  text,
  p_new_phone text,
  p_new_email text
)
RETURNS TABLE(lead_id bigint, updated_at timestamptz)  -- לעדכון _leadTs בלקוח
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
  IF auth.uid() IS NULL OR auth.uid() <> 'dc7c3190-93e3-462b-8b32-910c469a77a6'::uuid THEN
    RAISE EXCEPTION 'unauthorized';
  END IF;
  IF p_contacts IS NULL THEN RAISE EXCEPTION 'contacts payload required'; END IF;

  INSERT INTO public.app_meta(key, value) VALUES ('contacts', p_contacts::text)
  ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;

  IF p_deleted IS NOT NULL THEN
    INSERT INTO public.app_meta(key, value) VALUES ('deleted_contacts', p_deleted::text)
    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
  END IF;

  IF p_old_name IS NOT NULL AND p_old_name <> '' THEN
    RETURN QUERY
    UPDATE public.leads l
    SET data = l.data
          || jsonb_build_object('name',  COALESCE(p_new_name,''))
          || jsonb_build_object('phone', COALESCE(p_new_phone,''))
          || jsonb_build_object('email', COALESCE(p_new_email,'')),
        updated_at = now()
    WHERE l.data->>'name' = p_old_name
    RETURNING l.id, l.updated_at;
  END IF;
  RETURN;
END; $$;

REVOKE ALL     ON FUNCTION public.rename_contact_and_leads(jsonb,jsonb,text,text,text,text) FROM PUBLIC;
REVOKE ALL     ON FUNCTION public.rename_contact_and_leads(jsonb,jsonb,text,text,text,text) FROM anon;
GRANT  EXECUTE ON FUNCTION public.rename_contact_and_leads(jsonb,jsonb,text,text,text,text) TO authenticated;

-- ── אימות (לא חובה) ──
-- SELECT p.proname, pg_get_function_result(p.oid) AS returns, p.prosecdef,
--        has_function_privilege('authenticated', p.oid,'EXECUTE') AS auth_can,
--        has_function_privilege('anon',          p.oid,'EXECUTE') AS anon_can
-- FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
-- WHERE n.nspname='public' AND p.proname='rename_contact_and_leads';
