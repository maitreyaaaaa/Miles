import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { createServer } from "vite";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

let vite, Landing, scenarios, intent, AppRoot, AuthProvider;
const callbacks = {
  onStartDebate() {}, onOpenContextModal() {}, onOpenPreflight() {}, onOpenMeetModal() {},
};

before(async () => {
  // Render actual components on the server. This is markup verification, not a
  // browser or a substitute for visual/audio acceptance.
  vite = await createServer({ logLevel: "error", server: { middlewareMode: true } });
  Landing = (await vite.ssrLoadModule("/src/components/MarketingLanding.tsx")).MarketingLanding;
  scenarios = (await vite.ssrLoadModule("/src/scenarios.ts")).scenarios;
  intent = await vite.ssrLoadModule("/src/practiceIntent.ts");
  AppRoot = (await vite.ssrLoadModule("/src/AppRoot.tsx")).AppRoot;
  AuthProvider = (await vite.ssrLoadModule("/src/auth/AuthContext.tsx")).AuthProvider;
});
after(async () => { await vite?.close(); });

test("the public landing presents all eight scenarios with equal card structure", () => {
  const html = renderToStaticMarkup(React.createElement(Landing, callbacks));
  assert.equal((html.match(/class="practice-scenario-card"/g) || []).length, 8);
  for (const scenario of scenarios) assert.ok(html.includes(`<h3>${scenario.label}</h3>`));
  assert.ok(html.includes("AI voice sparring partner"));
  assert.ok(html.includes("report showing what to improve"));
});

test("Meet is absent and previews are labelled as examples without fake audio controls", () => {
  const html = renderToStaticMarkup(React.createElement(Landing, callbacks));
  assert.ok(!html.includes("Google Meet"));
  assert.ok(!html.includes("Practice in Meet"));
  assert.ok(!html.includes("sample-play-btn"));
  assert.ok(html.includes("EXAMPLE CONVERSATION"));
  assert.ok(html.includes("values below are examples"));
  assert.ok(html.includes('href="#sample-report"'));
});

function withTab(route = "") {
  const store = new Map();
  globalThis.sessionStorage = {
    getItem: (key) => store.get(key) ?? null,
    setItem: (key, value) => store.set(key, value),
    removeItem: (key) => store.delete(key),
  };
  globalThis.window = { location: { hash: route, pathname: "/", search: "" } };
  return store;
}

test("a signed-out visitor sees the product before sign-in even without auth configuration", () => {
  withTab();
  const html = renderToStaticMarkup(React.createElement(AuthProvider, null, React.createElement(AppRoot)));
  assert.ok(html.includes("Practice difficult"));
  assert.ok(!html.includes('id="auth-title"'));
});

test("a direct arena request remains protected by sign-in", () => {
  withTab("#arena");
  const html = renderToStaticMarkup(React.createElement(AuthProvider, null, React.createElement(AppRoot)));
  assert.ok(html.includes("Sign in to continue"));
  assert.ok(!html.includes('class="debate-shell"'));
});

test("scenario and custom-topic choices survive the sign-in redirect", () => {
  withTab();
  intent.savePracticeIntent({ scenario: "custom_debate", topic: "Defend our pricing", action: "practice" });
  window.location.pathname = "/auth/callback";
  assert.deepEqual(intent.readPracticeIntent(), { scenario: "custom_debate", topic: "Defend our pricing", action: "practice" });
  intent.clearPracticeIntent();
  assert.equal(intent.readPracticeIntent(), null);
});

test("corrupted or obsolete saved practice choices do not break the public page", () => {
  const store = withTab();
  store.set("miles_practice_intent", "not-json");
  assert.equal(intent.readPracticeIntent(), null);
  store.set("miles_practice_intent", JSON.stringify({ scenario: "unknown" }));
  assert.equal(intent.readPracticeIntent(), null);
});
