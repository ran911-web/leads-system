-- סבב 7 (פער V02): החלטות משתמש על זהות פונים (פיצול ליד משותף / איחוד שם פרטי לשם מלא).
-- נשמרות ב-app_meta['caller_rules'] כאובייקט {approved:{שם:ערך}, rejected:{שם:true}}; עדכון אטומי לפי מפתח (לא דריסת האובייקט).
CREATE OR REPLACE FUNCTION public.merge_caller_rules(p_set jsonb, p_unset jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public', 'pg_temp' AS $fn$
DECLARE cur jsonb; k text; sect text;
BEGIN
  IF auth.uid() IS NULL OR auth.uid() <> 'dc7c3190-93e3-462b-8b32-910c469a77a6'::uuid THEN RAISE EXCEPTION 'unauthorized'; END IF;
  IF p_set IS NOT NULL AND jsonb_typeof(p_set) <> 'object' THEN RAISE EXCEPTION 'p_set object required'; END IF;
  IF p_unset IS NOT NULL AND jsonb_typeof(p_unset) <> 'object' THEN RAISE EXCEPTION 'p_unset object required'; END IF;
  INSERT INTO public.app_meta(key, value) VALUES ('caller_rules', '{"approved":{},"rejected":{}}') ON CONFLICT (key) DO NOTHING;
  SELECT value::jsonb INTO cur FROM public.app_meta WHERE key = 'caller_rules' FOR UPDATE;
  IF cur IS NULL OR jsonb_typeof(cur) <> 'object' THEN cur := '{"approved":{},"rejected":{}}'::jsonb; END IF;
  FOREACH sect IN ARRAY ARRAY['approved','rejected'] LOOP
    IF p_unset ? sect THEN
      FOR k IN SELECT jsonb_array_elements_text(p_unset->sect) LOOP cur := jsonb_set(cur, ARRAY[sect], COALESCE(cur->sect,'{}'::jsonb) - k); END LOOP;
    END IF;
    IF p_set ? sect THEN
      cur := jsonb_set(cur, ARRAY[sect], COALESCE(cur->sect,'{}'::jsonb) || (p_set->sect));
    END IF;
  END LOOP;
  UPDATE public.app_meta SET value = cur::text WHERE key = 'caller_rules';
  RETURN cur;
END $fn$;
REVOKE ALL ON FUNCTION public.merge_caller_rules(jsonb, jsonb) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.merge_caller_rules(jsonb, jsonb) TO authenticated;
