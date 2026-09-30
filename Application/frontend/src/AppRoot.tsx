import React from "react";
import { useEffect, useState } from "react";
import App from "./App";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import { GoogleIntegrationProvider } from "./auth/GoogleIntegrationContext";
import { AuthScreen } from "./components/AuthScreen";
import { SharedDebriefView } from "./components/SharedDebriefView";
import { MarketingLanding } from "./components/MarketingLanding";
import { clearPracticeIntent, readPracticeIntent, savePracticeIntent } from "./practiceIntent";
import type { PracticeIntent } from "./practiceIntent";
import type { ScenarioId } from "./types";

export function AppRoot() {
  const { configured, loading, authError, user, signOut } = useAuth();
  const [authRequested, setAuthRequested] = useState(() =>
    ["#sign-in", "#arena"].includes(window.location.hash) || !!readPracticeIntent() || window.location.pathname === "/auth/callback",
  );
  useEffect(() => {
    const syncRoute = () => setAuthRequested(["#sign-in", "#arena"].includes(window.location.hash));
    window.addEventListener("hashchange", syncRoute);
    return () => window.removeEventListener("hashchange", syncRoute);
  }, []);
  const shareId = new URLSearchParams(window.location.search).get("share");

  if (shareId) return <SharedDebriefView shareId={shareId} />;

  const requestPractice = (scenario: ScenarioId = "vc_pitch", topic = "", action: PracticeIntent["action"] = "practice") => {
    savePracticeIntent({ scenario, topic, action });
    window.location.hash = "sign-in";
    setAuthRequested(true);
  };

  if (!user && !authRequested) return (
    <main className="marketing-view-shell">
      <MarketingLanding
        onStartDebate={(scenario, topic) => requestPractice(scenario, topic)}
        onOpenContextModal={() => requestPractice("vc_pitch", "", "context")}
        onOpenPreflight={() => requestPractice("vc_pitch", "", "audio")}
        onOpenMeetModal={() => requestPractice()}
      />
    </main>
  );

  if (loading) {
    return <main className="auth-screen"><p className="auth-loading">Restoring your sign-in…</p></main>;
  }
  if (!configured || !user) return <AuthScreen configured={configured} initialError={authError} onBack={() => {
    clearPracticeIntent();
    window.location.hash = "";
    setAuthRequested(false);
  }} />;

  return (
    <>
      <App />
      <div className="account-control">
        <span title={user.email ?? "Signed in"}>{user.email ?? "Signed in"}</span>
        <button type="button" onClick={() => void signOut().catch(console.error)} aria-label="Sign out">Sign out</button>
      </div>
    </>
  );
}
