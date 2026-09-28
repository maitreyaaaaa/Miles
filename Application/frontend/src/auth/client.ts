import { createClient } from "@supabase/supabase-js";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL?.trim();
const supabasePublishableKey = import.meta.env.VITE_SUPABASE_ANON_KEY?.trim();

export const authConfigured = Boolean(supabaseUrl && supabasePublishableKey);

export const supabase = authConfigured
  ? createClient(supabaseUrl!, supabasePublishableKey!, {
      auth: {
        flowType: "pkce",
        persistSession: true,
        storage: window.sessionStorage,
        autoRefreshToken: true,
        // Process only the Supabase callback route. Google Drive/Calendar use
        // their own callback path and must not be mistaken for a Supabase code.
        detectSessionInUrl: false,
      },
    })
  : null;
