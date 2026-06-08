const SUPABASE_URL = "https://brvutpegdjgwobjsyfgz.supabase.co";
const SUPABASE_ANON_KEY = "YOUR-ANON-KEY";

const hasSupabaseConfig =
  SUPABASE_URL.startsWith("https://") &&
  !SUPABASE_URL.includes("YOUR-PROJECT") &&
  SUPABASE_ANON_KEY &&
  !SUPABASE_ANON_KEY.includes("YOUR-ANON-KEY");

if (window.supabase && hasSupabaseConfig) {
  window.supabaseClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
} else {
  window.supabaseClient = null;
  window.supabaseConfigMissing = true;
}
