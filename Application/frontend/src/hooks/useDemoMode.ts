import { useCallback, useEffect, useState } from "react";

export interface DemoLogEntry {
  id: string;
  timestamp: string;
  category: "stt" | "tts" | "barge_in" | "ai_cut" | "telemetry" | "system";
  label: string;
  detail: string;
  metrics?: Record<string, number | string>;
}

export function useDemoMode() {
  const [isDemoActive, setIsDemoActive] = useState<boolean>(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      return params.get("demo") === "1" || params.get("judge") === "1";
    }
    return false;
  });

  const [eventLog, setEventLog] = useState<DemoLogEntry[]>([]);

  const toggleDemo = useCallback(() => {
    setIsDemoActive((prev) => !prev);
  }, []);

  const logEvent = useCallback(
    (
      category: DemoLogEntry["category"],
      label: string,
      detail: string,
      metrics?: Record<string, number | string>,
    ) => {
      const entry: DemoLogEntry = {
        id: `${Date.now()}-${Math.random().toString(36).substr(2, 5)}`,
        timestamp: new Date().toISOString().split("T")[1].slice(0, 11),
        category,
        label,
        detail,
        metrics,
      };
      setEventLog((prev) => [entry, ...prev.slice(0, 99)]);
    },
    [],
  );

  const clearLog = useCallback(() => {
    setEventLog([]);
  }, []);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ignore if user is currently typing in an input or textarea
      const target = e.target as HTMLElement;
      if (
        target &&
        (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)
      ) {
        return;
      }

      // 1. Ctrl + Shift + D (or Cmd + Shift + D on Mac)
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === "D" || e.key === "d")) {
        e.preventDefault();
        toggleDemo();
      }

      // 2. Tilde / Backtick (` or ~)
      if (e.key === "`" || e.key === "~") {
        e.preventDefault();
        toggleDemo();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [toggleDemo]);

  return {
    isDemoActive,
    toggleDemo,
    setIsDemoActive,
    eventLog,
    logEvent,
    clearLog,
  };
}
