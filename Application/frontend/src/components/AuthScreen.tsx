import { useEffect, useState } from "react";
import { supabase } from "../auth/client";

export function AuthScreen({ configured, initialError = "", onBack }: { configured: boolean; initialError?: string; onBack?: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(initialError);

  useEffect(() => setError(initialError), [initialError]);

  const signInWithGoogle = async () => {
    if (!supabase) return;
    setBusy(true);
    setError("");
    try {
      const { error: authError } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: { redirectTo: `${window.location.origin}/auth/callback` },
      });
      if (authError) throw authError;
    } catch {
      setBusy(false);
      setError("Google sign-in could not start. Please try again.");
    }
  };

  return (
    <main className="auth-screen">
      <section className="auth-card" aria-labelledby="auth-title">
        {onBack && <button type="button" className="auth-back-button" onClick={onBack}>← Back to Miles</button>}
        <div className="auth-brand">MILES</div>
        <p className="auth-eyebrow">VOICE SPARRING</p>
        <h1 id="auth-title">Sign in to continue</h1>
        <p className="auth-description">Practice high-stakes conversations with a sparring partner built to push back.</p>

        {!configured ? (
          <div className="auth-setup-message" role="status">
            Sign-in is temporarily unavailable. Please try again later.
          </div>
        ) : (
          <>
            <button className="auth-google-button" type="button" onClick={() => void signInWithGoogle()} disabled={busy}>
              <span aria-hidden="true" className="google-mark">G</span>
              {busy ? "Opening Google…" : "Continue with Google"}
            </button>

            {error && <p className="auth-error" role="alert">{error}</p>}
          </>
        )}
        <p className="auth-privacy">Your sign-in session stays in this browser tab.</p>
      </section>
    </main>
  );
}
