import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { Session, User } from "@supabase/supabase-js";
import { authConfigured, supabase } from "./client";

type AuthContextValue = {
  configured: boolean;
  loading: boolean;
  authError: string;
  session: Session | null;
  user: User | null;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [authError, setAuthError] = useState("");
  const [loading, setLoading] = useState(authConfigured);

  useEffect(() => {
    if (!supabase) return;

    let active = true;
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      if (active) {
        setSession(nextSession);
        if (nextSession) setAuthError("");
      }
    });

    void (async () => {
      try {
        if (window.location.pathname === "/auth/callback") {
          const code = new URLSearchParams(window.location.search).get("code");
          if (code) {
            const { error } = await supabase.auth.exchangeCodeForSession(code);
            if (error) throw error;
            window.history.replaceState({}, "", "/");
          }
        }
        const { data, error } = await supabase.auth.getSession();
        if (!active) return;
        setSession(error ? null : data.session);
      } catch {
        if (active) {
          setSession(null);
          setAuthError("Google sign-in could not be completed. Please try again.");
          window.history.replaceState({}, "", "/");
        }
      } finally {
        if (active) setLoading(false);
      }
    })();

    return () => {
      active = false;
      subscription.unsubscribe();
    };
  }, []);

  const value = useMemo<AuthContextValue>(() => ({
    configured: authConfigured,
    loading,
    authError,
    session,
    user: session?.user ?? null,
    signOut: async () => {
      if (!supabase) return;
      const { error } = await supabase.auth.signOut();
      if (error) throw error;
    },
  }), [authError, loading, session]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider.");
  return value;
}
