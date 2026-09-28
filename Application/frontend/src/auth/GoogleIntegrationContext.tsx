import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { apiFetch, BACKEND_URL } from "../api";
import { useAuth } from "./AuthContext";

type GooglePurpose = "drive" | "calendar";
type GoogleToken = { value: string; expiresAt: number } | null;

type GoogleIntegrationValue = {
  driveAccessToken: string | null;
  calendarAccessToken: string | null;
  connectingPurpose: GooglePurpose | null;
  integrationError: string;
  connectDrive: () => Promise<void>;
  connectCalendar: () => Promise<void>;
  clearIntegrationError: () => void;
};

const CALLBACK_PATH = "/google-integration-callback";
const OAUTH_STATE_KEY = "miles_google_oauth_pending";
const GoogleIntegrationContext = createContext<GoogleIntegrationValue | null>(null);

export function GoogleIntegrationProvider({ children }: { children: ReactNode }) {
  const { loading: authLoading, user } = useAuth();
  const [driveToken, setDriveToken] = useState<GoogleToken>(null);
  const [calendarToken, setCalendarToken] = useState<GoogleToken>(null);
  const [connectingPurpose, setConnectingPurpose] = useState<GooglePurpose | null>(null);
  const [integrationError, setIntegrationError] = useState("");

  const connect = useCallback(async (purpose: GooglePurpose) => {
    if (!user) {
      setIntegrationError("Sign in before connecting a Google account.");
      return;
    }

    const state = crypto.randomUUID();
    sessionStorage.setItem(OAUTH_STATE_KEY, JSON.stringify({ state, purpose, createdAt: Date.now() }));
    setConnectingPurpose(purpose);
    setIntegrationError("");

    try {
      const query = new URLSearchParams({ purpose, state });
      const response = await apiFetch(`${BACKEND_URL}/api/auth/google/url?${query}`);
      const data = await response.json();
      if (!response.ok || typeof data.auth_url !== "string") {
        throw new Error(data.detail || "Google authorization is not configured.");
      }
      window.location.assign(data.auth_url);
    } catch (error) {
      sessionStorage.removeItem(OAUTH_STATE_KEY);
      setConnectingPurpose(null);
      setIntegrationError(error instanceof Error ? error.message : "Could not connect Google.");
    }
  }, [user]);

  useEffect(() => {
    if (authLoading || window.location.pathname !== CALLBACK_PATH) return;

    const callbackUrl = new URL(window.location.href);
    const code = callbackUrl.searchParams.get("code");
    const returnedState = callbackUrl.searchParams.get("state");
    const providerError = callbackUrl.searchParams.get("error_description") || callbackUrl.searchParams.get("error");
    window.history.replaceState({}, "", "/");

    const pending = sessionStorage.getItem(OAUTH_STATE_KEY);
    sessionStorage.removeItem(OAUTH_STATE_KEY);
    if (providerError) {
      setIntegrationError("Google authorization was cancelled or denied.");
      return;
    }

    let expected: { state: string; purpose: GooglePurpose; createdAt: number } | null = null;
    try {
      expected = pending ? JSON.parse(pending) : null;
    } catch {
      expected = null;
    }
    if (!user || !code || !returnedState || !expected || expected.state !== returnedState
      || !["drive", "calendar"].includes(expected.purpose)
      || Date.now() - expected.createdAt > 10 * 60 * 1000) {
      setIntegrationError("Google authorization expired or could not be verified. Please connect again.");
      return;
    }

    let active = true;
    setConnectingPurpose(expected.purpose);
    void (async () => {
      try {
        const response = await apiFetch(`${BACKEND_URL}/api/auth/google/callback`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ code }),
        });
        const data = await response.json();
        if (!response.ok || typeof data.access_token !== "string") {
          throw new Error(data.detail || "Google authorization could not be completed.");
        }
        const expiresAt = Date.now() + Math.max(60, Number(data.expires_in || 3600) - 60) * 1000;
        const token = { value: data.access_token, expiresAt };
        if (active) {
          if (expected?.purpose === "drive") setDriveToken(token);
          else setCalendarToken(token);
          setIntegrationError("");
        }
      } catch (error) {
        if (active) setIntegrationError(error instanceof Error ? error.message : "Google authorization failed.");
      } finally {
        if (active) setConnectingPurpose(null);
      }
    })();

    return () => { active = false; };
  }, [authLoading, user]);

  useEffect(() => {
    if (!authLoading && !user) {
      setDriveToken(null);
      setCalendarToken(null);
    }
  }, [authLoading, user]);

  useEffect(() => {
    const now = Date.now();
    const expiries = [driveToken?.expiresAt, calendarToken?.expiresAt].filter((value): value is number => Boolean(value));
    if (expiries.length === 0) return;
    const timer = window.setTimeout(() => {
      if (driveToken && driveToken.expiresAt <= Date.now()) setDriveToken(null);
      if (calendarToken && calendarToken.expiresAt <= Date.now()) setCalendarToken(null);
    }, Math.max(1, Math.min(...expiries) - now));
    return () => window.clearTimeout(timer);
  }, [driveToken, calendarToken]);

  const value = useMemo<GoogleIntegrationValue>(() => ({
    driveAccessToken: driveToken && driveToken.expiresAt > Date.now() ? driveToken.value : null,
    calendarAccessToken: calendarToken && calendarToken.expiresAt > Date.now() ? calendarToken.value : null,
    connectingPurpose,
    integrationError,
    connectDrive: () => connect("drive"),
    connectCalendar: () => connect("calendar"),
    clearIntegrationError: () => setIntegrationError(""),
  }), [calendarToken, connect, connectingPurpose, driveToken, integrationError]);

  return <GoogleIntegrationContext.Provider value={value}>{children}</GoogleIntegrationContext.Provider>;
}

export function useGoogleIntegrations() {
  const value = useContext(GoogleIntegrationContext);
  if (!value) throw new Error("useGoogleIntegrations must be used inside GoogleIntegrationProvider.");
  return value;
}
