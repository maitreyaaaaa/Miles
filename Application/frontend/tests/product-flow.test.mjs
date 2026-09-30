import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { createServer } from "vite";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

let vite, Landing, scenarios, intent, AppRoot, AuthProvider, AuthScreen, App, GoogleIntegrationProvider, SessionPreparationModal, PreflightModal, prepare;
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
  AuthScreen = (await vite.ssrLoadModule("/src/components/AuthScreen.tsx")).AuthScreen;
  App = (await vite.ssrLoadModule("/src/App.tsx")).default;
  GoogleIntegrationProvider = (await vite.ssrLoadModule("/src/auth/GoogleIntegrationContext.tsx")).GoogleIntegrationProvider;
  SessionPreparationModal = (await vite.ssrLoadModule("/src/components/SessionPreparationModal.tsx")).SessionPreparationModal;
  PreflightModal = (await vite.ssrLoadModule("/src/components/PreflightModal.tsx")).PreflightModal;
  prepare = (await vite.ssrLoadModule("/src/sessionPreparation.ts")).sessionPreparationReducer;
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
  globalThis.window = {
    location: { hash: route, pathname: "/", search: "" },
    addEventListener() {}, removeEventListener() {},
  };
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

test("sign-in offers only Google and preserves error feedback", () => {
  const html = renderToStaticMarkup(React.createElement(AuthScreen, {
    configured: true, initialError: "Google sign-in could not start. Please try again.",
  }));
  assert.ok(html.includes("Continue with Google"));
  assert.ok(!html.includes('id="auth-email"'));
  assert.ok(!html.includes('id="auth-code"'));
  assert.ok(!html.includes("or use email"));
  assert.ok(!html.includes("Email me a code"));
  assert.ok(html.includes('role="alert"'));
});

test("corrupted or obsolete saved practice choices do not break the public page", () => {
  const store = withTab();
  store.set("miles_practice_intent", "not-json");
  assert.equal(intent.readPracticeIntent(), null);
  store.set("miles_practice_intent", JSON.stringify({ scenario: "unknown" }));
  assert.equal(intent.readPracticeIntent(), null);
});

test("session preparation offers optional documents for every scenario", () => {
  const props = {
    isOpen: true, activeContext: null, onAddContext() {}, onClearContext() {}, onContinue() {}, onClose() {},
  };
  for (const scenario of scenarios) {
    const html = renderToStaticMarkup(React.createElement(SessionPreparationModal, { ...props, scenarioLabel: scenario.label }));
    assert.ok(html.includes("Add pitch deck or notes"));
    assert.ok(html.includes("Continue without a document"));
    assert.ok(html.includes("Export slide decks as PDF"));
    assert.ok(html.includes('aria-modal="true"'));
  }
});

test("an attached document can be reviewed, replaced or removed before audio checks", () => {
  const html = renderToStaticMarkup(React.createElement(SessionPreparationModal, {
    isOpen: true, scenarioLabel: "VC Pitch", activeContext: { title: "Example deck.pdf", numeric_metrics: [{ name: "ARR" }] },
    onAddContext() {}, onClearContext() {}, onContinue() {}, onClose() {},
  }));
  assert.ok(html.includes("Example deck.pdf"));
  assert.ok(html.includes("1 extracted metric"));
  assert.ok(html.includes("Review or replace"));
  assert.ok(html.includes("Remove document"));
  assert.ok(html.includes("Continue to audio check"));
});

test("closing document upload returns to preparation and cannot skip the audio step", () => {
  let step = prepare("idle", "prepare");
  step = prepare(step, "upload");
  assert.equal(prepare(step, "continue"), "upload");
  assert.equal(prepare(step, "confirm"), "upload");
  step = prepare(step, "documentClosed");
  assert.equal(step, "materials");
  assert.equal(prepare(step, "confirm"), "materials");
  step = prepare(step, "continue");
  assert.equal(step, "audio");
  assert.equal(prepare(step, "confirm"), "idle");
});

test("cancelling preparation clears the pending session at every step", () => {
  for (const step of ["materials", "upload", "audio"]) {
    assert.equal(prepare(step, "cancel"), "idle");
    assert.equal(prepare(prepare(step, "cancel"), "confirm"), "idle");
  }
});

test("audio checks retain their start gate and standalone setup does not promise to start a session", () => {
  const props = { isOpen: true, onClose() {}, onConfirm() {} };
  const starting = renderToStaticMarkup(React.createElement(PreflightModal, { ...props, startingSession: true }));
  assert.ok(starting.includes("STEP 2 OF 2"));
  assert.match(starting, /class="preflight-submit-btn" disabled=""/);
  assert.ok(starting.includes("Start practice"));
  const standalone = renderToStaticMarkup(React.createElement(PreflightModal, props));
  assert.ok(standalone.includes("Finish audio check"));
});

test("the arena removes the top-right deck shortcut and has a keyboard-accessible overview link", () => {
  withTab("#arena");
  const html = renderToStaticMarkup(React.createElement(AuthProvider, null,
    React.createElement(GoogleIntegrationProvider, null, React.createElement(App))));
  assert.ok(!html.includes("Attach Deck"));
  assert.ok(!html.includes("Deck Armed"));
  assert.ok(html.includes("Start sparring session"));
  assert.ok(html.includes('aria-label="Return to Miles overview"'));
});
