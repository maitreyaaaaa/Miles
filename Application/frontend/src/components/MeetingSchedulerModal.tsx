import React, { useState, useEffect, useRef } from 'react';
import { ContextDossier, DebateReportEvent, MeetingSession } from '../types';

interface MeetingSchedulerModalProps {
  isOpen: boolean;
  onClose: () => void;
  activeContext: ContextDossier | null;
  onOpenContextUpload: () => void;
  onViewDebrief: (report: DebateReportEvent) => void;
  backendUrl?: string;
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
  const [isLoading, setIsLoading] = useState(false);
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [providerNotice, setProviderNotice] = useState<string | null>(null);

  // Recall.ai State
  const [activeBotId, setActiveBotId] = useState<string | null>(null);
  const [activeBotStatus, setActiveBotStatus] = useState<string | null>(null);
  const [isBotPolling, setIsBotPolling] = useState(false);
  const [isScheduleMode, setIsScheduleMode] = useState(false);
  const [scheduledJoinAt, setScheduledJoinAt] = useState('');

  const pollIntervalRef = useRef<any>(null);
  const apiBase = backendUrl.replace(/\/$/, '');

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
    return { name: 'Live Meeting', icon: '🌐', color: '#6366f1' };
  };

  const platformInfo = getPlatformInfo(meetUrl);

  useEffect(() => {
    if (isOpen) {
      fetchMeetings();
      if (!meetUrl) {
        handleGenerateLink();
      }
    } else {
      stopBotPolling();
    }
    return () => stopBotPolling();
  }, [isOpen]);

  const stopBotPolling = () => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
    setIsBotPolling(false);
  };

  const startBotPolling = (botId: string) => {
    stopBotPolling();
    setIsBotPolling(true);

    const poll = async () => {
      try {
        const res = await fetch(`${apiBase}/api/meeting/bot/${botId}`);
        if (res.ok) {
          const data = await res.json();
          const changes = data.status_changes || [];
          const latestStatus = changes.length > 0 ? changes[changes.length - 1].code : 'ready';
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
    pollIntervalRef.current = setInterval(poll, 3000);
  };

  const fetchMeetings = async () => {
    try {
      const res = await fetch(`${apiBase}/api/meetings`);
      if (res.ok) {
        const data = await res.json();
        setMeetings(data.meetings || []);
      }
    } catch (err) {
      console.error('Failed to fetch meetings', err);
    }
  };

  const handleGenerateLink = async () => {
    try {
      const res = await fetch(`${apiBase}/api/meeting/generate-link`);
      if (res.ok) {
        const data = await res.json();
        setMeetUrl(data.meet_url);
        setProviderNotice(data.provider_notice || null);
      }
    } catch (err) {
      setMeetUrl('https://meet.google.com/abc-defg-hij');
      setProviderNotice('Local simulation link. No external Google Meet room was provisioned.');
    }
  };

  // Launch Recall.ai Cloud Bot into the call
  const handleLaunchRecallBot = async () => {
    if (!meetUrl.trim()) {
      setStatusMessage('Please enter a valid meeting URL (Google Meet, Zoom, Teams).');
      return;
    }

    setIsLoading(true);
    setStatusMessage('Deploying Miles bot via Recall.ai cloud (Tokyo ap-northeast-1)...');

    try {
      const payload: any = {
        meeting_url: meetUrl.trim(),
        persona_id: personaId,
        difficulty: difficulty,
        topic: activeContext ? `Cross-Exam on ${activeContext.title}` : 'Voice Sparring',
        context_id: activeContext ? activeContext.context_id : null,
      };

      if (isScheduleMode && scheduledJoinAt) {
        payload.join_at = new Date(scheduledJoinAt).toISOString();
      }

      const res = await fetch(`${apiBase}/api/meeting/bot/launch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || 'Failed to dispatch Recall bot.');
      }

      const data = await res.json();
      setActiveBotId(data.bot_id);
      setActiveBotStatus(data.join_at ? 'scheduled' : 'joining_call');
      setStatusMessage(
        data.join_at
          ? `Bot successfully scheduled to join at ${new Date(data.join_at).toLocaleTimeString()}`
          : `Bot dispatched (ID: ${data.bot_id}). Connecting to ${platformInfo.name}...`
      );

      if (data.bot_id && !data.join_at) {
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
      const res = await fetch(`${apiBase}/api/meeting/bot/${activeBotId}/leave`, {
        method: 'POST',
      });
      if (res.ok) {
        setStatusMessage('Bot has been instructed to leave the meeting call.');
        setActiveBotStatus('call_ended');
        stopBotPolling();
        await fetchMeetings();
      }
    } catch (err: any) {
      setStatusMessage(`Error dismissing bot: ${err.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  const handleStopMeeting = async (meetingId: string) => {
    setActionLoadingId(meetingId);
    try {
      const res = await fetch(`${apiBase}/api/meeting/${meetingId}/stop`, {
        method: 'POST',
      });
      if (res.ok) {
        const data = await res.json();
        await fetchMeetings();
        if (data.debrief_report) {
          onViewDebrief(data.debrief_report);
          onClose();
        }
      }
    } catch (err) {
      console.error('Failed to stop meeting', err);
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleViewDebrief = async (meetingId: string) => {
    setActionLoadingId(meetingId);
    try {
      const res = await fetch(`${apiBase}/api/meeting/${meetingId}/debrief`);
      if (res.ok) {
        const report = await res.json();
        onViewDebrief(report);
        onClose();
      }
    } catch (err) {
      console.error('Failed to fetch debrief', err);
    } finally {
      setActionLoadingId(null);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-card meeting-modal-card" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="modal-header">
          <div className="modal-header-left">
            <div className="meet-icon-badge" style={{ backgroundColor: `${platformInfo.color}15`, borderColor: platformInfo.color }}>
              <span className="meet-camera-icon">{platformInfo.icon}</span>
            </div>
            <div>
              <div className="meeting-title-row">
                <h2 className="modal-title">Meeting Bot & Voice Sparring</h2>
                <span className="audio-only-badge" style={{ borderColor: platformInfo.color, color: platformInfo.color }}>
                  {platformInfo.name}
                </span>
                <span className="recall-workspace-tag">
                  Recall.ai • Tokyo (ap-northeast-1)
                </span>
              </div>
              <p className="modal-subtitle">
                Deploy Miles into your Google Meet, Zoom, or Teams call to spar live, audit facts against your dossier, and produce an executive debrief.
              </p>
            </div>
          </div>
          <button className="modal-close-btn" onClick={onClose} aria-label="Close meeting modal">&times;</button>
        </div>

        {/* Tab switcher */}
        <div className="meeting-tab-bar">
          <button
            className={`meeting-tab-btn ${activeTab === 'launch' ? 'active' : ''}`}
            onClick={() => setActiveTab('launch')}
          >
            🤖 Launch & Schedule Bot
          </button>
          <button
            className={`meeting-tab-btn ${activeTab === 'history' ? 'active' : ''}`}
            onClick={() => {
              setActiveTab('history');
              fetchMeetings();
            }}
          >
            📋 Sessions & Debriefs ({meetings.length})
          </button>
        </div>

        {activeTab === 'launch' ? (
          <div className="meeting-tab-content">
            {/* Active Bot Status Banner (if running) */}
            {activeBotId && (
              <div className="active-bot-banner">
                <div className="bot-banner-left">
                  <span className={`status-dot-pulse ${activeBotStatus === 'in_call_recording' ? 'live' : 'pending'}`}></span>
                  <div>
                    <strong>Recall.ai Bot Active: <code>{activeBotId}</code></strong>
                    <div className="bot-status-sub">
                      Status: <span className="bot-status-code">{activeBotStatus?.replace(/_/g, ' ').toUpperCase()}</span>
                      {isBotPolling && ' • Polling live...'}
                    </div>
                  </div>
                </div>
                <button
                  type="button"
                  className="danger-btn action-sm-btn"
                  onClick={handleLeaveRecallBot}
                  disabled={isLoading}
                >
                  Disconnect Bot
                </button>
              </div>
            )}

            {/* Meet URL input */}
            <div className="form-group">
              <label className="form-label">
                Meeting Room URL (Google Meet, Zoom, or Microsoft Teams)
              </label>
              <div className="meet-url-input-row">
                <input
                  type="text"
                  className="form-input meet-input"
                  placeholder="https://meet.google.com/xyz or https://zoom.us/j/123"
                  value={meetUrl}
                  onChange={(e) => setMeetUrl(e.target.value)}
                  disabled={isLoading}
                />
                <button
                  type="button"
                  className="secondary-btn instant-link-btn"
                  onClick={handleGenerateLink}
                  disabled={isLoading}
                  title="Generate a fresh Google Meet link via Google Calendar"
                >
                  ⚡ Provision Google Meet
                </button>
              </div>
              {providerNotice && (
                <div className="meeting-status-callout">
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
                  disabled={isLoading}
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
                  disabled={isLoading}
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
                  disabled={isLoading}
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
                  disabled={isLoading}
                />
                <span>Schedule bot for a future date/time</span>
              </label>

              {isScheduleMode && (
                <div className="schedule-input-box">
                  <label className="form-label">Target Join Time (Must be &gt;10 min in advance)</label>
                  <input
                    type="datetime-local"
                    className="form-input"
                    value={scheduledJoinAt}
                    onChange={(e) => setScheduledJoinAt(e.target.value)}
                    disabled={isLoading}
                  />
                  <span className="schedule-hint">
                    Recall.ai guarantees on-time machine warm-up when scheduled &gt;10 minutes ahead.
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
                    disabled={isLoading}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Status message */}
            {statusMessage && (
              <div className="meeting-status-callout">
                {statusMessage}
              </div>
            )}

            {/* Action buttons */}
            <div className="modal-actions">
              <button
                type="button"
                className="secondary-btn"
                onClick={onClose}
                disabled={isLoading}
              >
                Close
              </button>
              <button
                type="button"
                className="primary-btn launch-meet-btn"
                onClick={handleLaunchRecallBot}
                disabled={isLoading}
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
          <div className="meeting-history-tab">
            {meetings.length === 0 ? (
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
                      {m.context_filename && (
                        <span className="meta-item">📄 {m.context_filename}</span>
                      )}
                      <span className="meta-item">⏱ {Math.round(m.duration_seconds)}s</span>
                      <span className="meta-item">
                        📅 {new Date(m.created_at * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                    </div>

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

                      {m.status === 'scheduled' && (
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
