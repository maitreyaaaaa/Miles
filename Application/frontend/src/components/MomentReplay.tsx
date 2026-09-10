import React, { useState } from "react";
import { ChevronLeft, ChevronRight, PlayCircle, Zap } from "lucide-react";
import type { MomentBookmark } from "../types";

interface MomentReplayProps {
  bookmarks?: MomentBookmark[];
}

export const MomentReplay: React.FC<MomentReplayProps> = ({ bookmarks = [] }) => {
  const [selectedIndex, setSelectedIndex] = useState<number>(0);

  if (!bookmarks || bookmarks.length === 0) {
    return null;
  }

  const selected = bookmarks[Math.min(selectedIndex, bookmarks.length - 1)];

  const getTypeMeta = (type: MomentBookmark["type"]) => {
    switch (type) {
      case "hesitation":
        return { color: "#f59e0b", badge: "Hesitation", icon: "🟡" };
      case "ai_cut_in":
        return { color: "#ef4444", badge: "AI Cut-in", icon: "🔴" };
      case "barge_in":
        return { color: "#10b981", badge: "Barge-in", icon: "🟢" };
      case "breakdown":
        return { color: "#ec4899", badge: "Breakdown", icon: "💥" };
      default:
        return { color: "#6366f1", badge: "Moment", icon: "⚡" };
    }
  };

  const meta = getTypeMeta(selected.type);

  return (
    <div className="moment-replay-card">
      <div className="replay-header">
        <div className="replay-title">
          <Zap size={14} className="text-amber-400" />
          <span>Interactive Moment Replay</span>
          <span className="replay-count">
            {selectedIndex + 1} / {bookmarks.length}
          </span>
        </div>
        <div className="replay-nav">
          <button
            type="button"
            className="replay-arrow"
            onClick={() => setSelectedIndex((prev) => Math.max(0, prev - 1))}
            disabled={selectedIndex === 0}
            title="Previous key moment"
          >
            <ChevronLeft size={16} />
          </button>
          <button
            type="button"
            className="replay-arrow"
            onClick={() => setSelectedIndex((prev) => Math.min(bookmarks.length - 1, prev + 1))}
            disabled={selectedIndex === bookmarks.length - 1}
            title="Next key moment"
          >
            <ChevronRight size={16} />
          </button>
        </div>
      </div>

      {/* Interactive Timeline Track */}
      <div className="replay-track-wrap">
        <div className="replay-track">
          {bookmarks.map((b, idx) => {
            const bMeta = getTypeMeta(b.type);
            const isSelected = idx === selectedIndex;
            return (
              <button
                key={b.id || idx}
                type="button"
                className={`replay-pin ${isSelected ? "active" : ""}`}
                style={{
                  backgroundColor: isSelected ? bMeta.color : "rgba(255, 255, 255, 0.15)",
                  borderColor: bMeta.color,
                }}
                onClick={() => setSelectedIndex(idx)}
                title={`${b.label} (+${b.timestamp.toFixed(1)}s)`}
              >
                <span className="pin-tooltip">
                  {bMeta.icon} +{b.timestamp.toFixed(0)}s: {b.label}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Active Moment Detail */}
      <div className="replay-detail" style={{ borderLeftColor: meta.color }}>
        <div className="detail-top">
          <span
            className="detail-badge"
            style={{
              color: meta.color,
              backgroundColor: `${meta.color}18`,
              borderColor: `${meta.color}40`,
            }}
          >
            {meta.icon} {selected.label}
          </span>
          <span className="detail-meta">
            +{selected.timestamp.toFixed(1)}s • Round {selected.round}
            {selected.latency_ms !== undefined && ` • ${selected.latency_ms.toFixed(0)}ms latency`}
          </span>
        </div>

        {selected.quote && (
          <div className="detail-quote">
            <PlayCircle size={13} className="quote-icon" />
            <p>"{selected.quote}"</p>
          </div>
        )}

        <div className="detail-why">
          <strong>Tactical Trigger:</strong> <span>{selected.why}</span>
        </div>

        {selected.reframe && (
          <div className="detail-reframe">
            <strong>Winning Reframe:</strong> <span>{selected.reframe}</span>
          </div>
        )}
      </div>
    </div>
  );
};
