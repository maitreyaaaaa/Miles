import { useEffect, useState } from "react";
import { BACKEND_URL } from "../api";

type SharedDebrief = {
  topic?: string;
  scenario?: string;
  overall_score?: number;
  verdict?: string;
  verdict_description?: string;
  executive_summary?: string;
  coaching_tips?: string[];
};

export function SharedDebriefView({ shareId }: { shareId: string }) {
  const [report, setReport] = useState<SharedDebrief | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    if (!/^[A-Za-z0-9_-]{1,64}$/.test(shareId)) {
      setError("This share link is invalid or unavailable.");
      return () => controller.abort();
    }

    void fetch(`${BACKEND_URL}/api/debrief/share/${encodeURIComponent(shareId)}`, {
      signal: controller.signal,
      cache: "no-store",
    })
      .then(async (response) => {
        if (!response.ok) throw new Error("This report is unavailable or its link has expired.");
        setReport(await response.json());
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setError(reason instanceof Error ? reason.message : "This report could not be loaded.");
        }
      });

    return () => controller.abort();
  }, [shareId]);

  return (
    <main className="auth-screen">
      <article className="shared-report-card">
        <div className="auth-brand">MILES</div>
        <p className="auth-eyebrow">SHARED DEBRIEF</p>
        {error ? (
          <p className="shared-report-error" role="alert">{error}</p>
        ) : !report ? (
          <p className="auth-loading" role="status">Loading shared report…</p>
        ) : (
          <>
            <h1>{report.topic || "Sparring debrief"}</h1>
            {report.verdict && <p className="shared-report-verdict">{report.verdict}</p>}
            {typeof report.overall_score === "number" && (
              <p className="shared-report-score">{Math.round(report.overall_score)}<span> / 100</span></p>
            )}
            {report.verdict_description && <p className="shared-report-summary">{report.verdict_description}</p>}
            {report.executive_summary && <p className="shared-report-summary">{report.executive_summary}</p>}
            {!!report.coaching_tips?.length && (
              <section className="shared-report-tips">
                <h2>Coaching points</h2>
                <ul>{report.coaching_tips.map((tip, index) => <li key={`${index}-${tip}`}>{tip}</li>)}</ul>
              </section>
            )}
            <p className="auth-privacy">Read-only report. Anyone with this link can view it.</p>
          </>
        )}
      </article>
    </main>
  );
}
