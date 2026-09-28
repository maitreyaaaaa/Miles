import React, { useState, useEffect, useRef } from 'react';
import { ContextDossier, DebateReportEvent, MeetingSession } from '../types';
import { apiFetch } from '../api';
import { useGoogleIntegrations } from '../auth/GoogleIntegrationContext';
import { useAccessibleDialog } from '../hooks/useAccessibleDialog';

interface MeetingSchedulerModalProps {
  isOpen: boolean;
  onClose: () => void;
  activeContext: ContextDossier | null;
  onOpenContextUpload: () => void;
  onViewDebrief: (report: DebateReportEvent) => void;
  backendUrl?: string;
}

function toDateTimeLocalValue(timestamp: number) {
  const localDate = new Date(timestamp - new Date(timestamp).getTimezoneOffset() * 60_000);
  return localDate.toISOString().slice(0, 16);
}

function isSupportedMeetingUrl(value: string) {
  try {
    const url = new URL(value.trim());
    const host = url.hostname.toLowerCase().replace(/\.$/, '');
    const supported = host === 'meet.google.com'
      || host === 'zoom.us'
      || host.endsWith('.zoom.us')
      || host === 'teams.microsoft.com'
      || host.endsWith('.teams.microsoft.com')
      || host === 'teams.live.com'
      || host === 'webex.com'
      || host.endsWith('.webex.com');
    return url.protocol === 'https:' && supported && !url.username && !url.password;
  } catch {
    return false;
  }
}

export const MeetingSchedulerModal: React.FC<MeetingSchedulerModalProps> = ({
  isOpen,
  onClose,
  activeContext,
  onOpenContextUpload,
  onViewDebrief,
  backendUrl = 'http://localhost:8000',
}) => {
  const [activeTab, setActiveTab] = useState<'launch' | 'history'>('launch');
  const [meetUrl, setMeetUrl] = useState('');
  const [personaId, setPersonaId] = useState('vc_pitch');
  const [difficulty, setDifficulty] = useState('hard');
  const [maxDuration, setMaxDuration] = useState(1800);
  const [meetings, setMeetings] = useState<MeetingSession[]>([]);
  const [isHistoryLoading, setIsHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isProvisioning, setIsProvisioning] = useState(false);
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [providerNotice, setProviderNotice] = useState<string | null>(null);

  // Recall.ai State
  const [activeBotId, setActiveBotId] = useState<string | null>(null);
  const [activeBotStatus, setActiveBotStatus] = useState<string | null>(null);
  const [isBotPolling, setIsBotPolling] = useState(false);
  const [recallRegion, setRecallRegion] = useState('ap-northeast-1');
  const [isScheduleMode, setIsScheduleMode] = useState(false);
  const [scheduledJoinAt, setScheduledJoinAt] = useState('');
  const { calendarAccessToken, connectCalendar, connectingPurpose, integrationError, clearIntegrationError } = useGoogleIntegrations();

  const historyPollIntervalRef = useRef<number | null>(null);
  const botPollIntervalRef = useRef<number | null>(null);
  const apiBase = backendUrl.replace(/\/$/, '');
  const busy = isLoading || isProvisioning || actionLoadingId !== null;
  const dialogRef = useAccessibleDialog<HTMLDivElement>(isOpen, onClose, !busy);
  const earliestJoin = toDateTimeLocalValue(Date.now() + 11 * 60_000);
  const latestJoin = toDateTimeLocalValue(Date.now() + 30 * 24 * 60 * 60_000);

  // Detect Meeting Platform from URL
  const getPlatformInfo = (url: string) => {
    const lower = url.toLowerCase();
    if (lower.includes('zoom.us')) {
      return { name: 'Zoom Meeting', icon: '🔷', color: '#2d8cff' };
    }
    if (lower.includes('teams.microsoft.com') || lower.includes('teams.live.com')) {
      return { name: 'Microsoft Teams', icon: '👥', color: '#6264a7' };
    }
    if (lower.includes('meet.google.com')) {
      return { name: 'Google Meet', icon: '🎥', color: '#00ac47' };
    }
    if (lower.includes('webex.com')) {
      return { name: 'Webex', icon: '🎥', color: '#6f2da8' };
    }
    return { name: 'Live Meeting', icon: '🌐', color: '#6366f1' };
  };

  const platformInfo = getPlatformInfo(meetUrl);

  useEffect(() => {
    if (isOpen) {
      void fetchMeetings(activeTab === 'history');
      if (activeTab === 'history') {
        historyPollIntervalRef.current = window.setInterval(() => void fetchMeetings(), 5000);
      }
    } else {
      stopBotPolling();
    }
    return () => {
      if (historyPollIntervalRef.current !== null) {
        window.clearInterval(historyPollIntervalRef.current);
        historyPollIntervalRef.current = null;
      }
    };
  }, [isOpen, activeTab]);

  useEffect(() => () => {
    if (botPollIntervalRef.current !== null) window.clearInterval(botPollIntervalRef.current);
    if (historyPollIntervalRef.current !== null) window.clearInterval(historyPollIntervalRef.current);
  }, []);

  const stopBotPolling = () => {
    if (botPollIntervalRef.current !== null) {
      window.clearInterval(botPollIntervalRef.current);
      botPollIntervalRef.current = null;
    }
    setIsBotPolling(false);
  };

  const startBotPolling = (botId: string) => {
    stopBotPolling();
    setIsBotPolling(true);

    const poll = async () => {
      try {
        const res = await apiFetch(`${apiBase}/api/meeting/bot/${botId}`);
        if (res.ok) {
          const data = await res.json();
          const latestStatus = data.status || 'ready';
          setActiveBotStatus(latestStatus);

          if (['done', 'fatal', 'call_ended'].includes(latestStatus)) {
            stopBotPolling();
            fetchMeetings();
          }
        }
      } catch (err) {
        console.error('Bot polling error', err);
      }
    };

    poll();
    // This endpoint reads database state updated by Recall's signed webhooks.
    botPollIntervalRef.current = window.setInterval(() => void poll(), 5000);
  };

  const fetchMeetings = async (showLoading = false) => {
    if (showLoading) setIsHistoryLoading(true);
    try {
      const res = await apiFetch(`${apiBase}/api/meetings`);
      if (!res.ok) throw new Error(`Unable to load sessions (${res.status}).`);
      const data = await res.json();
      setMeetings(data.meetings || []);
      setHistoryError(null);
    } catch (err) {
      console.error('Failed to fetch meetings', err);
      setHistoryError(err instanceof Error ? err.message : 'Unable to load sessions.');
    } finally {
      if (showLoading) setIsHistoryLoading(false);
    }
  };

  const handleGenerateLink = async () => {
    setStatusMessage(null);
    setIsProvisioning(true);
    try {
      const res = await apiFetch(`${apiBase}/api/meeting/generate-link`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ access_token: calendarAccessToken || undefined }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Could not generate a meeting link.');
      setMeetUrl(data.meet_url);
      setProviderNotice(data.provider_notice || null);
    } catch (err) {
      setStatusMessage(err instanceof Error ? err.message : 'Could not generate a meeting link.');
    } finally {
      setIsProvisioning(false);
    }
  };

  // Launch Recall.ai Cloud Bot into the call
  const handleLaunchRecallBot = async () => {
    if (!isSupportedMeetingUrl(meetUrl)) {
      setStatusMessage('Enter a secure Google Meet, Zoom, Microsoft Teams, or Webex meeting URL.');
      return;
    }
    if (isScheduleMode) {
      const selectedTime = scheduledJoinAt ? new Date(scheduledJoinAt).getTime() : NaN;
      if (!Number.isFinite(selectedTime) || selectedTime <= Date.now() + 10 * 60_000) {
        setStatusMessage('Choose a join time more than 10 minutes from now.');
        return;
      }
      if (selectedTime > Date.now() + 30 * 24 * 60 * 60_000) {
        setStatusMessage('Choose a join time within the next 30 days.');
        return;
      }
    }

    setIsLoading(true);
    setStatusMessage(isScheduleMode ? 'Scheduling Miles with Recall.ai…' : 'Connecting Miles to Recall.ai…');

    try {
      const payload: {
        meeting_url: string;
        persona_id: string;
        difficulty: string;
        topic: string;
        context_id: string | null;
        max_duration_seconds: number;
        join_at?: string;
      } = {
        meeting_url: meetUrl.trim(),
        persona_id: personaId,
        difficulty: difficulty,
        topic: activeContext ? `Cross-Exam on ${activeContext.title}` : 'Voice Sparring',
        context_id: activeContext ? activeContext.context_id : null,
        max_duration_seconds: maxDuration,
      };

      if (isScheduleMode && scheduledJoinAt) {
        payload.join_at = new Date(scheduledJoinAt).toISOString();
      }

      const res = await apiFetch(`${apiBase}/api/meeting/bot/launch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || 'Failed to dispatch Recall bot.');
      }

      const data = await res.json();
      setRecallRegion(data.region || recallRegion);
      setActiveBotId(data.bot_id);
      setActiveBotStatus(data.recall_status || 'ready');
      setStatusMessage(
        data.join_at
          ? `Recall accepted the bot schedule for ${new Date(data.join_at).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}. Waiting for its join status…`
          : `Recall accepted the bot request for ${platformInfo.name}. Waiting for its join status…`
      );

      if (data.bot_id) {
        startBotPolling(data.bot_id);
      }
      await fetchMeetings();
    } catch (err: any) {
      setStatusMessage(`Error launching bot: ${err.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  // Instruct Recall bot to leave meeting
  const handleLeaveRecallBot = async () => {
    if (!activeBotId) return;
    setIsLoading(true);
    try {
      const res = await apiFetch(`${apiBase}/api/meeting/bot/${activeBotId}/leave`, {
        method: 'POST',
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Recall did not accept the leave request.');
      }
      setStatusMessage('Recall accepted the request for Miles to leave the meeting.');
      setActiveBotStatus('bot_leave_call_requested');
      await fetchMeetings();
    } catch (err: any) {
      setStatusMessage(`Error dismissing bot: ${err.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  const handleStopMeeting = async (meetingId: string) => {
    setActionLoadingId(meetingId);
    try {
      const res = await apiFetch(`${apiBase}/api/meeting/${meetingId}/stop`, {
        method: 'POST',
      });
      if (res.ok) {
        const data = await res.json();
        await fetchMeetings();
        if (data.debrief_report) {
          onViewDebrief(data.debrief_report);
          onClose();
        } else if (data.status === 'cancelled') {
          setStatusMessage('The scheduled Recall bot was cancelled.');
        } else if (data.status === 'leave_requested') {
          setStatusMessage('Recall accepted the leave request. The meeting status and debrief update after the bot disconnects.');
        }
      } else {
        const error = await res.json().catch(() => ({}));
        setStatusMessage(error.detail || 'Could not stop the meeting bot. Try again.');
      }
    } catch (err) {
      setStatusMessage(err instanceof Error ? err.message : 'Could not stop the meeting. Try again.');
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleViewDebrief = async (meetingId: string) => {
    setActionLoadingId(meetingId);
    try {
      const res = await apiFetch(`${apiBase}/api/meeting/${meetingId}/debrief`);
      if (res.ok) {
        const report = await res.json();
        onViewDebrief(report);
        onClose();
      } else {
        const error = await res.json().catch(() => ({}));
        setStatusMessage(error.detail || 'Could not load this debrief. Try again.');
      }
    } catch (err) {
      setStatusMessage(err instanceof Error ? err.message : 'Could not load this debrief. Try again.');
    } finally {
      setActionLoadingId(null);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="modal-backdrop meeting-modal-backdrop" role="presentation" onClick={() => { if (!busy) onClose(); }}>
      <div
        ref={dialogRef}
        className="modal-card meeting-modal-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="meeting-modal-title"
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="modal-header">
          <div className="modal-header-left">
            <div className="meet-icon-badge" style={{ backgroundColor: `${platformInfo.color}15`, borderColor: platformInfo.color }}>
              <span className="meet-camera-icon">{platformInfo.icon}</span>
            </div>
            <div>
              <div className="meeting-title-row">
                <h2 id="meeting-modal-title" className="modal-title">Meeting Bot &amp; Voice Sparring</h2>
                <span className="audio-only-badge" style={{ borderColor: platformInfo.color, color: platformInfo.color }}>
                  {platformInfo.name}
                </span>
                <span className="recall-workspace-tag">
                  Recall.ai • {recallRegion}
                </span>
              </div>
              <p className="modal-subtitle">
                Deploy Miles into your Google Meet, Zoom, Teams, or Webex call to spar live, audit facts against your dossier, and produce an executive debrief.
              </p>
            </div>
          </div>
          <button type="button" className="modal-close-btn" onClick={onClose} aria-label="Close meeting modal" disabled={busy}>&times;</button>
        </div>

        {/* Tab switcher */}
      <div className="meeting-tab-bar" role="tablist" aria-label="Meeting sessions">
          <button
            type="button"
            className={`meeting-tab-btn ${activeTab === 'launch' ? 'active' : ''}`}
            onClick={() => setActiveTab('launch')}
            role="tab"
            aria-selected={activeTab === 'launch'}
          >
            🤖 Launch & Schedule Bot
          </button>
          <button
            type="button"
            className={`meeting-tab-btn ${activeTab === 'history' ? 'active' : ''}`}
            onClick={() => {
              setActiveTab('history');
            }}
            role="tab"
            aria-selected={activeTab === 'history'}
          >
            📋 Sessions & Debriefs ({meetings.length})
          </button>
        </div>

        {activeTab === 'launch' ? (
          <div className="meeting-tab-content" role="tabpanel">
            {/* Active Bot Status Banner (if running) */}
            {activeBotId && (
              <div className="active-bot-banner">
                <div className="bot-banner-left">
                <span className={`status-dot-pulse ${['in_call_recording', 'in_call_not_recording'].includes(activeBotStatus || '') ? 'live' : 'pending'}`}></span>
                  <div>
                    <strong>{['in_call_recording', 'in_call_not_recording'].includes(activeBotStatus || '') ? 'Miles is in the meeting' : 'Recall.ai request accepted'}</strong>
                    <div className="bot-status-sub">
                      Status: <span className="bot-status-code">{activeBotStatus?.replace(/_/g, ' ').toUpperCase()}</span>
                      {isBotPolling && ' • Waiting for webhook updates…'}
                    </div>
                  </div>
                </div>
                {!['done', 'fatal', 'call_ended', 'bot_leave_call_requested'].includes(activeBotStatus || '') && <button
                  type="button"
                  className="danger-btn action-sm-btn"
                  onClick={handleLeaveRecallBot}
                  disabled={busy}
                >
                  Disconnect Bot
                </button>}
              </div>
            )}

            {/* Meet URL input */}
            <div className="form-group">
              <label className="form-label" htmlFor="meeting-room-url">
                Meeting Room URL (Google Meet, Zoom, Microsoft Teams, or Webex)
              </label>
              <div className="meet-url-input-row">
                <input
                  type="text"
                  id="meeting-room-url"
                  autoComplete="url"
                  className="form-input meet-input"
                  placeholder="https://meet.google.com/abc-defg-hij"
                  value={meetUrl}
                  onChange={(e) => { setMeetUrl(e.target.value); setStatusMessage(null); }}
                  aria-invalid={!!meetUrl.trim() && !isSupportedMeetingUrl(meetUrl)}
                  disabled={busy}
                />
                <button
                  type="button"
                  className="secondary-btn instant-link-btn"
                  onClick={() => { clearIntegrationError(); void connectCalendar(); }}
                  disabled={busy || connectingPurpose !== null}
                  title="Give Miles access to create Meet links in your Google Calendar"
                >
                  {calendarAccessToken ? 'Reconnect Calendar' : connectingPurpose === 'calendar' ? 'Connecting…' : 'Connect Calendar'}
                </button>
                <button
                  type="button"
                  className="secondary-btn instant-link-btn"
                  onClick={() => void handleGenerateLink()}
                  disabled={busy}
                  title="Create a Google Calendar event with a Meet link when Calendar is connected"
                >
                  {isProvisioning ? 'Creating Meet link…' : 'Provision Meet'}
                </button>
              </div>
              {integrationError && <p className="integration-error" role="alert">{integrationError}</p>}
              {!!meetUrl.trim() && !isSupportedMeetingUrl(meetUrl) && (
                <p className="integration-error" role="alert">Enter a secure link from Google Meet, Zoom, Microsoft Teams, or Webex.</p>
              )}
              {providerNotice && (
                <div className="meeting-status-callout" role="status">
                  {providerNotice}
                </div>
              )}
            </div>

            {/* Persona & Difficulty */}
            <div className="form-row-2col">
              <div className="form-group">
                <label className="form-label">Adversary Persona</label>
                <select
                  className="form-select"
                  value={personaId}
                  onChange={(e) => setPersonaId(e.target.value)}
                  disabled={busy}
                >
                  <option value="vc_pitch">VC Partner (Silicon Valley VC)</option>
                  <option value="salary_negotiation">VP of Engineering (Salary Negotiation)</option>
                  <option value="hostile_boardroom">Hostile Boardroom Activist</option>
                  <option value="senior_interview">Distinguished Architect (Technical Interview)</option>
                  <option value="sales_objections">Ruthless Enterprise Procurement</option>
                  <option value="media_crisis">Hostile Investigative Journalist</option>
                  <option value="hostile_cross_exam">Federal Prosecutor (Cross-Exam)</option>
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">Difficulty Intensity</label>
                <select
                  className="form-select"
                  value={difficulty}
                  onChange={(e) => setDifficulty(e.target.value)}
                  disabled={busy}
                >
                  <option value="easy">Easy (Constructive)</option>
                  <option value="medium">Medium (Challenging)</option>
                  <option value="hard">Hard (Adversarial)</option>
                  <option value="ruthless">Ruthless (Relentless Interruption)</option>
                </select>
              </div>
            </div>

            {/* Attached Context Dossier Card */}
            <div className="meeting-context-preview-card">
              <div className="context-card-top">
                <div className="context-card-title">
                  <span className="context-card-icon">📄</span>
                  <strong>Ground-Truth Dossier:</strong>
                  {activeContext ? (
                    <span className="context-active-name">{activeContext.title} ({activeContext.numeric_metrics.length} metrics)</span>
                  ) : (
                    <span className="context-none-name">None Attached (Generic Sparring)</span>
                  )}
                </div>
                <button
                  type="button"
                  className="text-link-btn"
                  onClick={onOpenContextUpload}
                  disabled={busy}
                >
                  {activeContext ? 'Change Context' : '+ Attach Pitch Deck / CV'}
                </button>
              </div>
              {activeContext ? (
                <div className="context-fact-preview">
                  Miles bot will cross-examine you against exact metrics: {activeContext.numeric_metrics.slice(0, 3).map(m => `${m.name}: ${m.raw_value}`).join(' • ')}...
                </div>
              ) : (
                <div className="context-empty-hint">
                  Attach a deck or Google Doc so the bot can audit your numbers during the call.
                </div>
              )}
            </div>

            {/* Scheduling Toggle */}
            <div className="schedule-toggle-section">
              <label className="schedule-toggle-label">
                <input
                  type="checkbox"
                  checked={isScheduleMode}
                  onChange={(e) => setIsScheduleMode(e.target.checked)}
                  disabled={busy}
                />
                <span>Schedule bot for a future date/time</span>
              </label>

              {isScheduleMode && (
                <div className="schedule-input-box">
                  <label className="form-label" htmlFor="scheduled-join-time">Target Join Time (More than 10 minutes from now)</label>
                  <input
                    type="datetime-local"
                    id="scheduled-join-time"
                    className="form-input"
                    value={scheduledJoinAt}
                    onChange={(e) => { setScheduledJoinAt(e.target.value); setStatusMessage(null); }}
                    min={earliestJoin}
                    max={latestJoin}
                    disabled={busy}
                  />
                  <span className="schedule-hint">
                    Schedule at least 10 minutes ahead to give the bot time to warm up.
                  </span>
                </div>
              )}
            </div>

            {/* Call Duration */}
            <div className="form-group">
              <label className="form-label">Maximum Duration</label>
              <div className="duration-pill-selector">
                {[
                  { label: '15 Min', val: 900 },
                  { label: '30 Min (Standard)', val: 1800 },
                  { label: '45 Min', val: 2700 },
                ].map((item) => (
                  <button
                    key={item.val}
                    type="button"
                    className={`duration-pill ${maxDuration === item.val ? 'active' : ''}`}
                    onClick={() => setMaxDuration(item.val)}
                    disabled={busy}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Status message */}
            {statusMessage && (
              <div className="meeting-status-callout" role="status" aria-live="polite">
                {statusMessage}
              </div>
            )}

            {/* Action buttons */}
            <div className="modal-actions">
              <button
                type="button"
                className="secondary-btn"
                onClick={onClose}
                disabled={busy}
              >
                Close
              </button>
              <button
                type="button"
                className="primary-btn launch-meet-btn"
                onClick={handleLaunchRecallBot}
                disabled={busy}
              >
                {isLoading ? (
                  <>
                    <span className="spinner-sm"></span> Dispatching Cloud Bot...
                  </>
                ) : (
                  <>🤖 {isScheduleMode ? 'Schedule Recall Bot' : 'Launch Recall Bot Now'}</>
                )}
              </button>
            </div>
          </div>
        ) : (
          <div className="meeting-history-tab" role="tabpanel">
            {historyError && (
              <div className="meeting-status-callout history-error" role="alert">
                <span>{historyError}</span>
                <button type="button" className="text-link-btn" onClick={() => void fetchMeetings(true)}>Try again</button>
              </div>
            )}
            {isHistoryLoading && meetings.length === 0 ? (
              <div className="empty-history-state" role="status">Loading meeting sessions…</div>
            ) : meetings.length === 0 && !historyError ? (
              <div className="empty-history-state">
                <span className="empty-history-icon">📅</span>
                <p>No meeting sessions or bot records yet.</p>
                <button
                  type="button"
                  className="secondary-btn"
                  onClick={() => setActiveTab('launch')}
                >
                  Launch Your First Meeting Bot
                </button>
              </div>
            ) : (
              <div className="meeting-cards-list">
                {meetings.map((m) => (
                  <div key={m.meeting_id} className={`meeting-card status-${m.status}`}>
                    <div className="meeting-card-header">
                      <div className="meeting-info">
                        <span className="meeting-persona-tag">{m.persona_id}</span>
                        <a
                          href={m.meet_url}
                          target="_blank"
                          rel="noreferrer"
                          className="meeting-url-link"
                        >
                          {m.meet_url} ↗
                        </a>
                      </div>
                      <div className="meeting-status-badge">
                        {m.status === 'in_call' && <span className="pulsing-red-dot"></span>}
                        <span className={`badge-text badge-${m.status}`}>{m.status.toUpperCase()}</span>
                      </div>
                    </div>

                    <div className="meeting-card-meta">
                      {m.recall_bot_id && (
                        <span className="meta-item recall-bot-tag">🤖 Recall: {m.recall_bot_id.slice(0, 8)}...</span>
                      )}
                      {m.provider_mode && (
                        <span className="meta-item">Mode: {m.provider_mode.replace('_', ' ')}</span>
                      )}
                      {m.recall_status && (
                        <span className="meta-item">Recall: {m.recall_status.replace(/_/g, ' ')}</span>
                      )}
                      {m.context_filename && (
                        <span className="meta-item">📄 {m.context_filename}</span>
                      )}
                      <span className="meta-item">⏱ {Math.round(m.duration_seconds)}s</span>
                      <span className="meta-item">
                        📅 {new Date(m.created_at * 1000).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}
                      </span>
                    </div>

                    {(m.recall_status_message || m.error_message) && (
                      <p className="meeting-status-callout" role="status">
                        {m.error_message || m.recall_status_message}
                      </p>
                    )}

                    <div className="meeting-card-actions">
                      {m.status === 'in_call' && (
                        <button
                          type="button"
                          className="danger-btn action-sm-btn"
                          onClick={() => handleStopMeeting(m.meeting_id)}
                          disabled={actionLoadingId === m.meeting_id}
                        >
                          {actionLoadingId === m.meeting_id ? 'Concluding...' : 'End Call & Generate Debrief'}
                        </button>
                      )}

                      {m.status === 'completed' && m.has_debrief && (
                        <button
                          type="button"
                          className="primary-btn action-sm-btn"
                          onClick={() => handleViewDebrief(m.meeting_id)}
                          disabled={actionLoadingId === m.meeting_id}
                        >
                          {actionLoadingId === m.meeting_id ? 'Loading...' : '📊 View Debrief Report'}
                        </button>
                      )}

                      {(m.status === 'scheduled' || m.status === 'connecting') && m.recall_bot_id && (
                        <button
                          type="button"
                          className="danger-btn action-sm-btn"
                          onClick={() => handleStopMeeting(m.meeting_id)}
                          disabled={actionLoadingId === m.meeting_id}
                        >
                          {actionLoadingId === m.meeting_id ? 'Cancelling…' : m.status === 'scheduled' ? 'Cancel Scheduled Bot' : 'Stop Joining Bot'}
                        </button>
                      )}

                      {m.status === 'scheduled' && !m.recall_bot_id && (
                        <button
                          type="button"
                          className="primary-btn action-sm-btn"
                          onClick={() => {
                            setMeetUrl(m.meet_url);
                            setPersonaId(m.persona_id);
                            setActiveTab('launch');
                          }}
                        >
                          Launch Bot
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
