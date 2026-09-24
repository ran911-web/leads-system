-- ============================================================================
-- 00000000000000_baseline_schema.sql — סכימת הבסיס של מערכת הלידים
--
-- ⚠️ שחזור מקטלוג: האובייקטים כאן נוצרו בייצור ידנית (SQL Editor) בהקמת המערכת,
--    לפני שהחל תיעוד migrations; הם אינם מופיעים בהיסטוריית ה-migrations של הפרויקט.
--    ה-DDL שוחזר בקריאה בלבד מהקטלוג של eemepnirijolwbwvokin ב-23.09.2026 (ראה supabase/DEPLOYMENT_EVIDENCE.md).
--    מיועד להקמת סביבת בדיקה / שחזור. אין להריץ על הייצור (הכול כבר קיים שם).
--    גרסת הייצור של lead_audit_orphans כוללת security_invoker=on (הוחל ב-20260923_security_advisor_fixes).
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.leads (id bigint NOT NULL, data jsonb NOT NULL, updated_at timestamptz DEFAULT now(), PRIMARY KEY (id));
CREATE TABLE IF NOT EXISTS public.app_meta (key text NOT NULL, value text, PRIMARY KEY (key));
CREATE SEQUENCE IF NOT EXISTS public.lead_audit_audit_id_seq;
CREATE TABLE IF NOT EXISTS public.lead_audit (audit_id bigint NOT NULL DEFAULT nextval('public.lead_audit_audit_id_seq'::regclass),
  lead_id integer NOT NULL, action text NOT NULL, address text, city text, status text, note text,
  at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (audit_id));
ALTER TABLE public.leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.app_meta ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lead_audit ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "owner_only_leads" ON public.leads;
CREATE POLICY "owner_only_leads" ON public.leads AS PERMISSIVE FOR ALL TO authenticated
  USING ((auth.uid() IS NOT NULL) AND (auth.uid() = 'dc7c3190-93e3-462b-8b32-910c469a77a6'::uuid))
  WITH CHECK ((auth.uid() IS NOT NULL) AND (auth.uid() = 'dc7c3190-93e3-462b-8b32-910c469a77a6'::uuid));
DROP POLICY IF EXISTS "owner_only_meta" ON public.app_meta;
CREATE POLICY "owner_only_meta" ON public.app_meta AS PERMISSIVE FOR ALL TO authenticated
  USING ((auth.uid() IS NOT NULL) AND (auth.uid() = 'dc7c3190-93e3-462b-8b32-910c469a77a6'::uuid))
  WITH CHECK ((auth.uid() IS NOT NULL) AND (auth.uid() = 'dc7c3190-93e3-462b-8b32-910c469a77a6'::uuid));
DROP POLICY IF EXISTS "owner_only_audit" ON public.lead_audit;
CREATE POLICY "owner_only_audit" ON public.lead_audit AS PERMISSIVE FOR ALL TO authenticated
  USING ((auth.uid() IS NOT NULL) AND (auth.uid() = 'dc7c3190-93e3-462b-8b32-910c469a77a6'::uuid))
  WITH CHECK ((auth.uid() IS NOT NULL) AND (auth.uid() = 'dc7c3190-93e3-462b-8b32-910c469a77a6'::uuid));
GRANT SELECT, INSERT, UPDATE, DELETE ON public.leads, public.app_meta, public.lead_audit TO authenticated;
GRANT USAGE ON SEQUENCE public.lead_audit_audit_id_seq TO authenticated;
CREATE OR REPLACE VIEW public.lead_audit_orphans WITH (security_invoker = on) AS
  SELECT lead_id, min(at) AS reserved_at FROM public.lead_audit r
   WHERE action = 'reserved'
     AND NOT EXISTS (SELECT 1 FROM public.lead_audit c WHERE c.lead_id = r.lead_id AND c.action = 'created')
     AND NOT EXISTS (SELECT 1 FROM public.leads l WHERE l.id = r.lead_id)
   GROUP BY lead_id ORDER BY lead_id;
GRANT SELECT ON public.lead_audit_orphans TO authenticated;
CREATE OR REPLACE FUNCTION public.reserve_lead_ids(n integer) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public', 'pg_temp' AS $function$
DECLARE start_id integer; i integer;
BEGIN
  IF auth.uid() IS NULL OR auth.uid() <> 'dc7c3190-93e3-462b-8b32-910c469a77a6'::uuid THEN RAISE EXCEPTION 'unauthorized'; END IF;
  IF n IS NULL OR n < 1 OR n > 10000 THEN RAISE EXCEPTION 'invalid n'; END IF;
  UPDATE public.app_meta SET value = ((value::integer) + n)::text WHERE key = 'nextId' RETURNING (value::integer - n) INTO start_id;
  IF start_id IS NULL THEN RAISE EXCEPTION 'nextId row missing'; END IF;
  FOR i IN 0..(n-1) LOOP
    INSERT INTO public.lead_audit(lead_id, action, note) VALUES (start_id + i, 'reserved', 'reserve_lead_ids');
  END LOOP;
  RETURN start_id;
END; $function$;
REVOKE ALL ON FUNCTION public.reserve_lead_ids(integer) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.reserve_lead_ids(integer) TO authenticated;
