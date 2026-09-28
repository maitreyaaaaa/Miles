import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import { GoogleIntegrationProvider } from "./auth/GoogleIntegrationContext";
import { AuthScreen } from "./components/AuthScreen";
import { SharedDebriefView } from "./components/SharedDebriefView";
import "./styles.css";

function AppRoot() {
  const { configured, loading, authError, user, signOut } = useAuth();
  const shareId = new URLSearchParams(window.location.search).get("share");

  if (shareId) return <SharedDebriefView shareId={shareId} />;

  if (loading) {
    return <main className="auth-screen"><p className="auth-loading">Restoring your sign-in…</p></main>;
  }
  if (!configured || !user) return <AuthScreen configured={configured} initialError={authError} />;

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

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AuthProvider>
      <GoogleIntegrationProvider>
        <AppRoot />
      </GoogleIntegrationProvider>
    </AuthProvider>
  </React.StrictMode>
);
