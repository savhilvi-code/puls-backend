-- Run in the production Supabase SQL Editor as the function owner.
-- Changes only the signup function's FREE quota literal. No existing row updates.
BEGIN;

DO $migration$
DECLARE
    function_oid oid := to_regprocedure('public.handle_new_auth_user()');
    definition text;
    prefix_pattern text := $pattern$(insert[[:space:]]+into[[:space:]]+public\.subscriptions[[:space:]]*\([[:space:]]*user_id[[:space:]]*,[[:space:]]*plan[[:space:]]*,[[:space:]]*status[[:space:]]*,[[:space:]]*quota_limit[[:space:]]*,[[:space:]]*quota_used[[:space:]]*\)[[:space:]]*values[[:space:]]*\([[:space:]]*new\.id[[:space:]]*,[[:space:]]*'free'[[:space:]]*,[[:space:]]*'active'[[:space:]]*,[[:space:]]*)$pattern$;
    suffix_pattern text := $pattern$([[:space:]]*,[[:space:]]*0[[:space:]]*\)[[:space:]]*on[[:space:]]+conflict[[:space:]]*\([[:space:]]*user_id[[:space:]]*\)[[:space:]]*do[[:space:]]+nothing[[:space:]]*;)$pattern$;
    old_pattern text := prefix_pattern || '3' || suffix_pattern;
    new_pattern text := prefix_pattern || '5' || suffix_pattern;
    match_count integer;
    parts text[];
BEGIN
    IF function_oid IS NULL THEN
        RAISE EXCEPTION 'Expected public.handle_new_auth_user() was not found; no changes made.';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgrelid = 'auth.users'::regclass
          AND tgname = 'on_auth_user_created'
          AND tgfoid = function_oid AND NOT tgisinternal
    ) THEN
        RAISE EXCEPTION 'Registration trigger does not match the inspected contract; no changes made.';
    END IF;

    definition := pg_get_functiondef(function_oid);
    SELECT count(*) INTO match_count FROM regexp_matches(definition, old_pattern, 'gi');
    IF match_count = 0 THEN
        SELECT count(*) INTO match_count FROM regexp_matches(definition, new_pattern, 'gi');
        IF match_count = 1 THEN
            RAISE NOTICE 'Signup FREE quota is already 5; no changes made.';
            RETURN;
        END IF;
        RAISE EXCEPTION 'Expected signup INSERT was not found; inspect the live function before proceeding.';
    ELSIF match_count <> 1 THEN
        RAISE EXCEPTION 'Ambiguous signup INSERT matches; no changes made.';
    END IF;

    parts := regexp_match(definition, old_pattern, 'i');
    -- pg_get_functiondef retains the full profile logic, security attributes,
    -- and function settings. CREATE OR REPLACE retains ownership and grants.
    EXECUTE replace(definition, parts[1] || '3' || parts[2], parts[1] || '5' || parts[2]);

    definition := pg_get_functiondef(function_oid);
    SELECT count(*) INTO match_count FROM regexp_matches(definition, new_pattern, 'gi');
    IF match_count <> 1 OR definition ~* old_pattern THEN
        RAISE EXCEPTION 'Signup quota verification failed; transaction will roll back.';
    END IF;
END;
$migration$;

COMMIT;

-- Read back the complete definition for review after application.
SELECT pg_get_functiondef('public.handle_new_auth_user()'::regprocedure);
