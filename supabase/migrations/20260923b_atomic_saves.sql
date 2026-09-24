-- סבב 6 (ביקורת df2ce6f): F10/F11 — שמירת לידים עם השוואת גרסה אטומית; F05 — מיזוג אנשי קשר לפי מזהה.
-- תוספתי בלבד: לא משנה טבלאות, לא משנה נתונים, לא מסיר פונקציה שהגרסה החיה משתמשת בה.

-- ── upsert_leads_checked: לכל שורה — נעילה, השוואת גרסת בסיס, וכתיבה, באותה טרנזקציה ──
-- שורה: {id, data, base, force}. base = updated_at שעליו התבססה העריכה (null לליד חדש).
-- תוצאה לכל שורה: ok (נשמר, עם updated_at חדש) | conflict (השתנה בשרת; מוחזרים הגרסה והנתונים) | deleted (נמחק בשרת).
-- שורה לא תקינה → חריגה → כל הקריאה מתבטלת (rollback).
CREATE OR REPLACE FUNCTION public.upsert_leads_checked(p_rows jsonb)
RETURNS TABLE(o_id bigint, o_status text, o_updated_at timestamptz, o_server_data jsonb)
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public', 'pg_temp' AS $fn$
DECLARE r jsonb; v_id bigint; v_base timestamptz; v_force boolean; v_cur timestamptz; v_data jsonb; v_new timestamptz;
BEGIN
  IF auth.uid() IS NULL OR auth.uid() <> 'dc7c3190-93e3-462b-8b32-910c469a77a6'::uuid THEN RAISE EXCEPTION 'unauthorized'; END IF;
  IF p_rows IS NULL OR jsonb_typeof(p_rows) <> 'array' THEN RAISE EXCEPTION 'rows array required'; END IF;
  IF jsonb_array_length(p_rows) > 200 THEN RAISE EXCEPTION 'too many rows'; END IF;
  FOR r IN SELECT e FROM jsonb_array_elements(p_rows) AS t(e) LOOP
    v_id := (r->>'id')::bigint;
    IF v_id IS NULL OR v_id <= 0 OR jsonb_typeof(r->'data') IS DISTINCT FROM 'object' THEN RAISE EXCEPTION 'invalid row'; END IF;
    v_base  := NULLIF(r->>'base','')::timestamptz;
    v_force := COALESCE((r->>'force')::boolean, false);
    SELECT l.updated_at, l.data INTO v_cur, v_data FROM public.leads l WHERE l.id = v_id FOR UPDATE;
    IF FOUND THEN
      IF NOT v_force AND (v_base IS NULL OR v_cur IS DISTINCT FROM v_base) THEN
        o_id := v_id; o_status := 'conflict'; o_updated_at := v_cur; o_server_data := v_data; RETURN NEXT; CONTINUE;
      END IF;
      UPDATE public.leads l SET data = r->'data', updated_at = clock_timestamp() WHERE l.id = v_id RETURNING l.updated_at INTO v_new;
    ELSE
      IF v_base IS NOT NULL AND NOT v_force THEN
        o_id := v_id; o_status := 'deleted'; o_updated_at := NULL; o_server_data := NULL; RETURN NEXT; CONTINUE;
      END IF;
      INSERT INTO public.leads AS l (id, data, updated_at) VALUES (v_id, r->'data', clock_timestamp()) RETURNING l.updated_at INTO v_new;
    END IF;
    o_id := v_id; o_status := 'ok'; o_updated_at := v_new; o_server_data := NULL; RETURN NEXT;
  END LOOP;
END $fn$;
REVOKE ALL ON FUNCTION public.upsert_leads_checked(jsonb) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.upsert_leads_checked(jsonb) TO authenticated;

-- ── עוזר פנימי: מיזוג רשימת אנשי קשר לפי id (נעילת השורה ב-app_meta) ──
CREATE OR REPLACE FUNCTION public._merge_contacts_locked(p_upserts jsonb, p_deleted_ids jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public', 'pg_temp' AS $fn$
DECLARE cur jsonb; merged jsonb; ups jsonb := COALESCE(p_upserts, '[]'::jsonb); del jsonb := COALESCE(p_deleted_ids, '[]'::jsonb);
BEGIN
  IF jsonb_typeof(ups) <> 'array' OR jsonb_typeof(del) <> 'array' THEN RAISE EXCEPTION 'arrays required'; END IF;
  IF EXISTS (SELECT 1 FROM jsonb_array_elements(ups) u(v) WHERE jsonb_typeof(u.v) <> 'object' OR COALESCE(u.v->>'id','') = '') THEN
    RAISE EXCEPTION 'contact id required'; END IF;
  INSERT INTO public.app_meta(key, value) VALUES ('contacts', '[]') ON CONFLICT (key) DO NOTHING;
  SELECT value::jsonb INTO cur FROM public.app_meta WHERE key = 'contacts' FOR UPDATE;
  IF cur IS NULL OR jsonb_typeof(cur) <> 'array' THEN cur := '[]'::jsonb; END IF;
  -- קיימים: מוחלפים אם עודכנו, מושמטים אם נמחקו; הסדר נשמר
  SELECT COALESCE(jsonb_agg(COALESCE(u.v, c.v) ORDER BY c.ord), '[]'::jsonb) INTO merged
    FROM jsonb_array_elements(cur) WITH ORDINALITY c(v, ord)
    LEFT JOIN LATERAL (SELECT x.v FROM jsonb_array_elements(ups) x(v) WHERE x.v->>'id' = c.v->>'id' LIMIT 1) u ON true
   WHERE NOT EXISTS (SELECT 1 FROM jsonb_array_elements_text(del) d(t) WHERE d.t = c.v->>'id');
  -- חדשים: מתווספים בסוף
  merged := merged || COALESCE((SELECT jsonb_agg(x.v) FROM jsonb_array_elements(ups) x(v)
             WHERE NOT EXISTS (SELECT 1 FROM jsonb_array_elements(cur) c(v) WHERE c.v->>'id' = x.v->>'id')
               AND NOT EXISTS (SELECT 1 FROM jsonb_array_elements_text(del) d(t) WHERE d.t = x.v->>'id')), '[]'::jsonb);
  UPDATE public.app_meta SET value = merged::text WHERE key = 'contacts';
  RETURN merged;
END $fn$;
REVOKE ALL ON FUNCTION public._merge_contacts_locked(jsonb, jsonb) FROM PUBLIC, anon, authenticated;

-- ── merge_contacts: שמירת אנשי קשר — רק מה שהשתנה, בלי לדרוס שינויים ממכשיר אחר ──
CREATE OR REPLACE FUNCTION public.merge_contacts(p_upserts jsonb, p_deleted_ids jsonb, p_deleted_names jsonb DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public', 'pg_temp' AS $fn$
DECLARE merged jsonb;
BEGIN
  IF auth.uid() IS NULL OR auth.uid() <> 'dc7c3190-93e3-462b-8b32-910c469a77a6'::uuid THEN RAISE EXCEPTION 'unauthorized'; END IF;
  merged := public._merge_contacts_locked(p_upserts, p_deleted_ids);
  IF p_deleted_names IS NOT NULL THEN
    INSERT INTO public.app_meta(key, value) VALUES ('deleted_contacts', p_deleted_names::text)
      ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
  END IF;
  RETURN merged;
END $fn$;
REVOKE ALL ON FUNCTION public.merge_contacts(jsonb, jsonb, jsonb) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.merge_contacts(jsonb, jsonb, jsonb) TO authenticated;

-- ── rename_contact_and_leads_v2: שינוי שם איש קשר + הלידים שלו, אטומי, עם מיזוג (לא החלפת רשימה) ──
CREATE OR REPLACE FUNCTION public.rename_contact_and_leads_v2(p_upserts jsonb, p_deleted_ids jsonb, p_deleted_names jsonb,
  p_old_name text, p_new_name text, p_new_phone text, p_new_email text)
RETURNS TABLE(lead_id bigint, updated_at timestamptz, contacts jsonb)
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public', 'pg_temp' AS $fn$
DECLARE merged jsonb;
BEGIN
  IF auth.uid() IS NULL OR auth.uid() <> 'dc7c3190-93e3-462b-8b32-910c469a77a6'::uuid THEN RAISE EXCEPTION 'unauthorized'; END IF;
  merged := public._merge_contacts_locked(p_upserts, p_deleted_ids);
  IF p_deleted_names IS NOT NULL THEN
    INSERT INTO public.app_meta(key, value) VALUES ('deleted_contacts', p_deleted_names::text)
      ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
  END IF;
  IF p_old_name IS NOT NULL AND p_old_name <> '' THEN
    RETURN QUERY UPDATE public.leads l
       SET data = l.data || jsonb_build_object('name', COALESCE(p_new_name,''), 'phone', COALESCE(p_new_phone,''), 'email', COALESCE(p_new_email,'')),
           updated_at = clock_timestamp()
     WHERE l.data->>'name' = p_old_name
     RETURNING l.id, l.updated_at, merged;
  END IF;
  IF NOT FOUND OR p_old_name IS NULL OR p_old_name = '' THEN
    lead_id := NULL; updated_at := NULL; contacts := merged; RETURN NEXT;
  END IF;
  RETURN;
END $fn$;
REVOKE ALL ON FUNCTION public.rename_contact_and_leads_v2(jsonb, jsonb, jsonb, text, text, text, text) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.rename_contact_and_leads_v2(jsonb, jsonb, jsonb, text, text, text, text) TO authenticated;
