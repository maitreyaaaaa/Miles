import { supabase } from "./auth/client";

export const BACKEND_URL = import.meta.env.VITE_BACKEND_URL ?? "http://localhost:8000";

export async function apiFetch(input: RequestInfo | URL, init: RequestInit = {}) {
  if (!supabase) throw new Error("Sign-in is not configured for this deployment.");

  const { data, error } = await supabase.auth.getSession();
  const accessToken = data.session?.access_token;
  if (error || !accessToken) throw new Error("Your sign-in has expired. Sign in again to continue.");

  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${accessToken}`);
  const response = await fetch(input, { ...init, headers });

  if (response.status === 401) {
    await supabase.auth.signOut({ scope: "local" });
  }
  return response;
}

export async function openAuthenticatedWebSocket(url: string) {
  if (!supabase) throw new Error("Sign-in is not configured for this deployment.");

  const { data, error } = await supabase.auth.getSession();
  const accessToken = data.session?.access_token;
  if (error || !accessToken) throw new Error("Your sign-in has expired. Sign in again to continue.");

  // Browser WebSocket APIs cannot set Authorization headers. Send the token in
  // the first encrypted WebSocket frame so it never appears in the URL/logs.
  const socket = new WebSocket(url);
  socket.addEventListener("open", () => {
    socket.send(JSON.stringify({ type: "authenticate", access_token: accessToken }));
  }, { once: true });
  return socket;
}
