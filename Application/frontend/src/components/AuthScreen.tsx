import { FormEvent, useEffect, useState } from "react";
import { supabase } from "../auth/client";

export function AuthScreen({ configured, initialError = "" }: { configured: boolean; initialError?: string }) {
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [awaitingCode, setAwaitingCode] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(initialError);
  const [notice, setNotice] = useState("");

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = window.setTimeout(() => setCooldown((value) => value - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [cooldown]);

  useEffect(() => setError(initialError), [initialError]);

  const sendCode = async () => {
    if (!supabase) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const { error: authError } = await supabase.auth.signInWithOtp({
        email: email.trim(),
        options: { shouldCreateUser: true },
      });
      if (authError) throw authError;
      setAwaitingCode(true);
      setCooldown(60);
      setNotice("If that address can sign in, a six-digit code is on its way.");
    } catch {
      setError("We could not send a code. Check the address and try again shortly.");
    } finally {
      setBusy(false);
    }
  };

  const verifyCode = async (event: FormEvent) => {
    event.preventDefault();
    if (!supabase) return;
    setBusy(true);
    setError("");
    try {
      const { error: authError } = await supabase.auth.verifyOtp({
        email: email.trim(),
        token: code.trim(),
        type: "email",
      });
      if (authError) throw authError;
    } catch {
      setError("That code is invalid or expired. Request a new code and try again.");
    } finally {
      setBusy(false);
    }
  };

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
        <div className="auth-brand">MILES</div>
        <p className="auth-eyebrow">VOICE SPARRING</p>
        <h1 id="auth-title">Sign in to continue</h1>
        <p className="auth-description">Practice high-stakes conversations with a sparring partner built to push back.</p>

        {!configured ? (
          <div className="auth-setup-message" role="status">
            Sign-in is not configured yet. Set the Supabase frontend and backend values, then enable Google and email OTP in Supabase Auth.
          </div>
        ) : (
          <>
            <button className="auth-google-button" type="button" onClick={() => void signInWithGoogle()} disabled={busy}>
              <span aria-hidden="true" className="google-mark">G</span>
              Continue with Google
            </button>

            <div className="auth-divider"><span>or use email</span></div>

            {!awaitingCode ? (
              <form className="auth-form" onSubmit={(event) => { event.preventDefault(); void sendCode(); }}>
                <label htmlFor="auth-email">Email address</label>
                <input
                  id="auth-email"
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="you@example.com"
                  maxLength={254}
                  required
                />
                <button className="auth-submit-button" type="submit" disabled={busy}>
                  {busy ? "Sending code…" : "Email me a code"}
                </button>
              </form>
            ) : (
              <form className="auth-form" onSubmit={(event) => void verifyCode(event)}>
                <label htmlFor="auth-code">Six-digit code</label>
                <input
                  id="auth-code"
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  pattern="[0-9]{6}"
                  maxLength={6}
                  value={code}
                  onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
                  placeholder="000000"
                  required
                />
                <button className="auth-submit-button" type="submit" disabled={busy || code.length !== 6}>
                  {busy ? "Verifying…" : "Verify and sign in"}
                </button>
                <div className="auth-code-actions">
                  <button type="button" onClick={() => { setAwaitingCode(false); setCode(""); setNotice(""); }}>
                    Change email
                  </button>
                  <button type="button" disabled={busy || cooldown > 0} onClick={() => void sendCode()}>
                    {cooldown > 0 ? `Resend in ${cooldown}s` : "Resend code"}
                  </button>
                </div>
              </form>
            )}
            {notice && <p className="auth-notice" role="status">{notice}</p>}
            {error && <p className="auth-error" role="alert">{error}</p>}
          </>
        )}
        <p className="auth-privacy">Your sign-in session stays in this browser tab.</p>
      </section>
    </main>
  );
}
