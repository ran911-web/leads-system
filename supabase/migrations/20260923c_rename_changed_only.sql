-- סבב 7 (פערי ביקורת df2ce6f, סעיף 17): שינוי שם איש קשר מעדכן updated_at רק בלידים שערכיהם באמת משתנים.
-- חל על שתי הגרסאות (v2 החדשה, והישנה שהגרסה הקודמת של האפליקציה עוד קוראת לה). חתימות ותוצאות ללא שינוי.

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
       AND (COALESCE(l.data->>'name',''), COALESCE(l.data->>'phone',''), COALESCE(l.data->>'email',''))
           IS DISTINCT FROM (COALESCE(p_new_name,''), COALESCE(p_new_phone,''), COALESCE(p_new_email,''))
     RETURNING l.id, l.updated_at, merged;
  END IF;
  IF NOT FOUND OR p_old_name IS NULL OR p_old_name = '' THEN
    lead_id := NULL; updated_at := NULL; contacts := merged; RETURN NEXT;
  END IF;
  RETURN;
END $fn$;

CREATE OR REPLACE FUNCTION public.rename_contact_and_leads(p_contacts jsonb, p_deleted jsonb, p_old_name text, p_new_name text, p_new_phone text, p_new_email text)
RETURNS TABLE(lead_id bigint, updated_at timestamptz)
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public', 'pg_temp' AS $fn$
BEGIN
  IF auth.uid() IS NULL OR auth.uid() <> 'dc7c3190-93e3-462b-8b32-910c469a77a6'::uuid THEN RAISE EXCEPTION 'unauthorized'; END IF;
  IF p_contacts IS NULL THEN RAISE EXCEPTION 'contacts payload required'; END IF;
  INSERT INTO public.app_meta(key, value) VALUES ('contacts', p_contacts::text)
    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
  IF p_deleted IS NOT NULL THEN
    INSERT INTO public.app_meta(key, value) VALUES ('deleted_contacts', p_deleted::text)
      ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
  END IF;
  IF p_old_name IS NOT NULL AND p_old_name <> '' THEN
    RETURN QUERY UPDATE public.leads l
      SET data = l.data || jsonb_build_object('name', COALESCE(p_new_name,'')) || jsonb_build_object('phone', COALESCE(p_new_phone,'')) || jsonb_build_object('email', COALESCE(p_new_email,'')),
          updated_at = now()
      WHERE l.data->>'name' = p_old_name
        AND (COALESCE(l.data->>'name',''), COALESCE(l.data->>'phone',''), COALESCE(l.data->>'email',''))
            IS DISTINCT FROM (COALESCE(p_new_name,''), COALESCE(p_new_phone,''), COALESCE(p_new_email,''))
      RETURNING l.id, l.updated_at;
  END IF;
  RETURN;
END $fn$;
