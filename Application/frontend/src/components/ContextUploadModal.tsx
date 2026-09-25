import React, { useState, useRef, useEffect } from "react";
import {
  FileText,
  Upload,
  Clipboard,
  CheckCircle2,
  AlertTriangle,
  HelpCircle,
  Hash,
  X,
  Trash2,
  ArrowRight,
  ShieldAlert,
  Loader2,
  FileCheck,
  Globe,
  ExternalLink,
} from "lucide-react";
import type { ContextDossier } from "../types";

interface ContextUploadModalProps {
  isOpen: boolean;
  onClose: () => void;
  activeContext: ContextDossier | null;
  onSelectContext: (dossier: ContextDossier) => void;
  onClearContext: () => void;
  backendUrl: string;
}

export const ContextUploadModal: React.FC<ContextUploadModalProps> = ({
  isOpen,
  onClose,
  activeContext,
  onSelectContext,
  onClearContext,
  backendUrl,
}) => {
  const [tab, setTab] = useState<"upload" | "paste" | "gdrive" | "preview">("upload");
  const [dragOver, setDragOver] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [pastedText, setPastedText] = useState("");
  const [pastedTitle, setPastedTitle] = useState("");
  const [driveUrl, setDriveUrl] = useState("");
  const [googleAccessToken, setGoogleAccessToken] = useState("");
  const [googleConfig, setGoogleConfig] = useState<{ client_id?: string; drive_enabled?: boolean } | null>(null);
  const [previewDossier, setPreviewDossier] = useState<ContextDossier | null>(activeContext);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (activeContext) {
      setPreviewDossier(activeContext);
    }
  }, [activeContext]);

  useEffect(() => {
    if (isOpen) {
      fetch(`${backendUrl}/api/auth/google/config`)
        .then((res) => res.json())
        .then((data) => setGoogleConfig(data))
        .catch(() => setGoogleConfig(null));
    }
  }, [isOpen, backendUrl]);

  if (!isOpen) return null;

  const handleFileUpload = async (file: File) => {
    setIsLoading(true);
    setErrorMsg(null);
    try {
      const formData = new FormData();
      formData.append("file", file);

      const resp = await fetch(`${backendUrl}/api/context/upload`, {
        method: "POST",
        body: formData,
      });

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: "Upload failed" }));
        throw new Error(err.detail || `Upload failed with HTTP ${resp.status}`);
      }

      const dossier: ContextDossier = await resp.json();
      setPreviewDossier(dossier);
      setTab("preview");
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to process uploaded file");
    } finally {
      setIsLoading(false);
    }
  };

  const handlePasteSubmit = async () => {
    if (!pastedText.trim()) {
      setErrorMsg("Please paste your document text or notes.");
      return;
    }
    setIsLoading(true);
    setErrorMsg(null);
    try {
      const resp = await fetch(`${backendUrl}/api/context/paste`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: pastedText.trim(),
          filename: pastedTitle.trim() || "Pasted Notes.txt",
        }),
      });

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: "Analysis failed" }));
        throw new Error(err.detail || `Analysis failed with HTTP ${resp.status}`);
      }

      const dossier: ContextDossier = await resp.json();
      setPreviewDossier(dossier);
      setTab("preview");
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to analyze pasted context");
    } finally {
      setIsLoading(false);
    }
  };

  const handleDriveImport = async () => {
    if (!driveUrl.trim()) {
      setErrorMsg("Please enter a Google Drive, Docs, Sheets, or Slides link or file ID.");
      return;
    }
    setIsLoading(true);
    setErrorMsg(null);
    try {
      const resp = await fetch(`${backendUrl}/api/context/google-drive/import`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url_or_id: driveUrl.trim(),
          access_token: googleAccessToken.trim() || undefined,
        }),
      });

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: "Drive import failed" }));
        throw new Error(err.detail || `Google Drive import failed with HTTP ${resp.status}`);
      }

      const dossier: ContextDossier = await resp.json();
      setPreviewDossier(dossier);
      setTab("preview");
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to import from Google Drive");
    } finally {
      setIsLoading(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      void handleFileUpload(e.dataTransfer.files[0]);
    }
  };

  const confirmActiveContext = () => {
    if (previewDossier) {
      onSelectContext(previewDossier);
      onClose();
    }
  };

  return (
    <div className="context-modal-backdrop" onClick={onClose}>
      <div
        className="context-modal-dialog"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        {/* Header */}
        <div className="context-modal-header">
          <div className="context-modal-title-wrap">
            <div className="context-modal-icon">
              <FileCheck size={18} />
            </div>
            <div>
              <h3>Add Your Pitch Deck, CV, or Notes</h3>
              <p>
                Upload or connect your document. Miles will pull out your key numbers and challenge you on them.
              </p>
            </div>
          </div>
          <button type="button" className="context-modal-close" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        {/* Tab Switcher */}
        <div className="context-modal-tabs">
          <button
            type="button"
            className={`context-tab ${tab === "upload" ? "active" : ""}`}
            onClick={() => setTab("upload")}
          >
            <Upload size={14} />
            <span>Upload Document</span>
          </button>
          <button
            type="button"
            className={`context-tab ${tab === "paste" ? "active" : ""}`}
            onClick={() => setTab("paste")}
          >
            <Clipboard size={14} />
            <span>Paste Text / Notes</span>
          </button>
          <button
            type="button"
            className={`context-tab ${tab === "gdrive" ? "active" : ""}`}
            onClick={() => setTab("gdrive")}
          >
            <Globe size={14} />
            <span>Google Drive</span>
          </button>
          {previewDossier && (
            <button
              type="button"
              className={`context-tab ${tab === "preview" ? "active" : ""}`}
              onClick={() => setTab("preview")}
            >
              <Hash size={14} />
              <span>Extracted Fact-Sheet ({previewDossier.numeric_metrics.length})</span>
            </button>
          )}
        </div>

        {/* Error Notification */}
        {errorMsg && (
          <div className="context-error-banner">
            <AlertTriangle size={15} />
            <span>{errorMsg}</span>
          </div>
        )}

        {/* Body Content */}
        <div className="context-modal-body">
          {isLoading ? (
            <div className="context-loading-state">
              <Loader2 size={32} className="context-spinner" />
              <h4>Auditing Document & Extracting Ground-Truth</h4>
              <p>
                Identifying core claims, categorizing financial & operational metrics, and compiling lethal cross-examination traps...
              </p>
            </div>
          ) : tab === "upload" ? (
            <div className="context-upload-container">
              <div
                className={`context-dropzone ${dragOver ? "drag-active" : ""}`}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragOver(true);
                }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
              >
                <input
                  type="file"
                  ref={fileInputRef}
                  style={{ display: "none" }}
                  accept=".pdf,.docx,.doc,.txt,.md,.csv"
                  onChange={(e) => {
                    if (e.target.files && e.target.files.length > 0) {
                      void handleFileUpload(e.target.files[0]);
                    }
                  }}
                />
                <div className="dropzone-icon">
                  <Upload size={28} />
                </div>
                <h4>Drag & Drop your Document here</h4>
                <p>Supports PDF, DOCX, TXT, Markdown, or CSV (Pitch decks, Resumes, Financial sheets)</p>
                <button type="button" className="dropzone-browse-btn">
                  Browse Files
                </button>
              </div>

              <div className="context-tips-box">
                <div className="tips-header">
                  <ShieldAlert size={14} />
                  <span>How Miles uses this document</span>
                </div>
                <ul>
                  <li><strong>Numeric Verification:</strong> Tracks CAC, LTV, revenue, dates, headcounts, percentages.</li>
                  <li><strong>Active Rectification:</strong> If you misquote or contradict your document, Miles cuts in immediately.</li>
                  <li><strong>Debrief Audit:</strong> Grades your factual accuracy and lists any caught bluffs in the post-debate report.</li>
                </ul>
              </div>
            </div>
          ) : tab === "paste" ? (
            <div className="context-paste-container">
              <div className="paste-field-group">
                <label htmlFor="context-paste-title">Document Title / Label</label>
                <input
                  id="context-paste-title"
                  type="text"
                  placeholder="e.g. Series A Pitch Deck Notes, Jane Doe CV, Q3 Financials"
                  value={pastedTitle}
                  onChange={(e) => setPastedTitle(e.target.value)}
                />
              </div>
              <div className="paste-field-group">
                <label htmlFor="context-paste-content">Paste Document Text, Slide Content, or Bullets</label>
                <textarea
                  id="context-paste-content"
                  rows={9}
                  placeholder="Paste raw text here... e.g.
Company: Acme AI.
Current ARR is $2.4M with 82% gross margin.
Blended CAC is $45 across B2B channels.
Team of 15 distributed engineers.
Churn is 1.8% monthly."
                  value={pastedText}
                  onChange={(e) => setPastedText(e.target.value)}
                />
              </div>
              <button
                type="button"
                className="paste-analyze-btn"
                onClick={handlePasteSubmit}
                disabled={!pastedText.trim()}
              >
                <span>Extract Metrics & Traps</span>
                <ArrowRight size={14} />
              </button>
            </div>
          ) : tab === "gdrive" ? (
            <div className="context-drive-container">
              <div className="drive-header-card">
                <div className="drive-icon-pill">
                  <Globe size={24} style={{ color: "#0284c7" }} />
                </div>
                <div>
                  <h4>Import from Google Drive</h4>
                  <p>Paste any Google Doc, Sheet, Slide, or shared Drive file to extract numbers and traps.</p>
                </div>
              </div>

              <div className="paste-field-group">
                <label htmlFor="context-drive-url">Google Drive, Doc, or Sheet Link</label>
                <div className="drive-input-row">
                  <input
                    id="context-drive-url"
                    type="text"
                    placeholder="https://docs.google.com/document/d/... or https://drive.google.com/file/d/..."
                    value={driveUrl}
                    onChange={(e) => setDriveUrl(e.target.value)}
                    disabled={isLoading}
                  />
                  <button
                    type="button"
                    className="paste-analyze-btn drive-import-btn"
                    onClick={handleDriveImport}
                    disabled={isLoading || !driveUrl.trim()}
                  >
                    <span>Import & Audit</span>
                    <ArrowRight size={14} />
                  </button>
                </div>
              </div>

              {googleConfig && !googleConfig.drive_enabled && (
                <div style={{ padding: "10px 14px", background: "#fef3c7", border: "1px solid #fde68a", borderRadius: "8px", fontSize: "0.82rem", color: "#92400e" }}>
                  💡 <strong>Public Link Mode:</strong> You can paste any publicly shared Google Doc or Sheet link ("Anyone with the link can view") immediately. To access private files, add your <code>GOOGLE_CLIENT_ID</code> and <code>GOOGLE_CLIENT_SECRET</code> to <code>.env</code>.
                </div>
              )}

              <div className="context-tips-box">
                <div className="tips-header">
                  <ShieldAlert size={14} />
                  <span>Supported Google Drive Formats</span>
                </div>
                <ul>
                  <li><strong>Google Docs:</strong> Automatically converted to clean text for forensic ground-truth extraction.</li>
                  <li><strong>Google Sheets:</strong> Parsed as tabular CSV data to verify revenue, CAC, unit economics, and margins.</li>
                  <li><strong>Google Slides:</strong> Extracted slide-by-slide to test your presentation claims under pressure.</li>
                  <li><strong>Sharing:</strong> Set link sharing to <em>"Anyone with the link can view"</em> for instant import.</li>
                </ul>
              </div>
            </div>
          ) : previewDossier ? (
            <div className="context-preview-container">
              {/* Dossier Meta Summary */}
              <div className="context-preview-meta">
                <div className="meta-left">
                  <span className="doc-type-pill">{previewDossier.doc_type.replace("_", " ").toUpperCase()}</span>
                  <h4>{previewDossier.title}</h4>
                  <p>{previewDossier.executive_summary}</p>
                </div>
                <span className="metrics-count-badge">
                  {previewDossier.numeric_metrics.length} Verified Metrics Tracked
                </span>
              </div>

              {/* Numeric Metrics Grid */}
              <div className="preview-section">
                <div className="preview-section-title">
                  <Hash size={14} style={{ color: "#38bdf8" }} />
                  <span>Extracted Numeric Fact-Sheet (Opponent Ground-Truth)</span>
                </div>
                <div className="numeric-metrics-grid">
                  {previewDossier.numeric_metrics.map((m, idx) => (
                    <div key={idx} className="metric-chip">
                      <div className="metric-chip-top">
                        <span className="metric-chip-name">{m.name}</span>
                        <span className="metric-chip-val">{m.raw_value}</span>
                      </div>
                      {m.context && <p className="metric-chip-ctx">{m.context}</p>}
                    </div>
                  ))}
                </div>
              </div>

              {/* Vulnerabilities Section */}
              {previewDossier.vulnerabilities.length > 0 && (
                <div className="preview-section">
                  <div className="preview-section-title">
                    <AlertTriangle size={14} style={{ color: "#fb7185" }} />
                    <span>Identified Vulnerabilities Under Audit</span>
                  </div>
                  <div className="vuln-list">
                    {previewDossier.vulnerabilities.map((v, idx) => (
                      <div key={idx} className="vuln-item">
                        <span className="vuln-cat">{v.category}</span>
                        <span className="vuln-issue">{v.issue}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Cross-Exam Traps Preview */}
              {previewDossier.cross_exam_traps.length > 0 && (
                <div className="preview-section">
                  <div className="preview-section-title">
                    <HelpCircle size={14} style={{ color: "#fbbf24" }} />
                    <span>Pre-Computed Numeric Cross-Exam Traps</span>
                  </div>
                  <div className="traps-list">
                    {previewDossier.cross_exam_traps.map((t, idx) => (
                      <div key={idx} className="trap-item">
                        <span className="trap-num">{idx + 1}.</span>
                        <span className="trap-text">"{t}"</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : null}
        </div>

        {/* Footer Actions */}
        <div className="context-modal-footer">
          {activeContext && (
            <button
              type="button"
              className="context-clear-btn"
              onClick={() => {
                onClearContext();
                setPreviewDossier(null);
                setTab("upload");
              }}
            >
              <Trash2 size={14} />
              <span>Remove Active Context</span>
            </button>
          )}

          <div style={{ marginLeft: "auto", display: "flex", gap: "0.5rem" }}>
            <button type="button" className="context-cancel-btn" onClick={onClose}>
              Cancel
            </button>
            {previewDossier && (
              <button type="button" className="context-confirm-btn" onClick={confirmActiveContext}>
                <CheckCircle2 size={14} />
                <span>Arm Adversary with this Context</span>
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
