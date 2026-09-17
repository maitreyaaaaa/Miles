import React, { useState, useEffect } from 'react';
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
  const [activeTab, setActiveTab] = useState<'schedule' | 'history'>('schedule');
  const [meetUrl, setMeetUrl] = useState('');
  const [personaId, setPersonaId] = useState('vc_pitch');
  const [difficulty, setDifficulty] = useState('hard');
  const [maxDuration, setMaxDuration] = useState(1800);
  const [meetings, setMeetings] = useState<MeetingSession[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [providerNotice, setProviderNotice] = useState<string | null>(null);
  const apiBase = backendUrl.replace(/\/$/, '');

  useEffect(() => {
    if (isOpen) {
      fetchMeetings();
      if (!meetUrl) {
        handleGenerateLink();
      }
    }
  }, [isOpen]);

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

  const handleScheduleAndStart = async () => {
    if (!meetUrl.trim()) {
      setStatusMessage('Please enter or generate a Google Meet link.');
      return;
    }

    setIsLoading(true);
    setStatusMessage('Scheduling local Meet simulation session...');

    try {
      // 1. Schedule session
      const schedRes = await fetch(`${apiBase}/api/meeting/schedule`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          meet_url: meetUrl.trim(),
          context_id: activeContext ? activeContext.context_id : null,
          persona_id: personaId,
          difficulty: difficulty,
          max_duration_seconds: maxDuration,
        }),
      });

      if (!schedRes.ok) {
        throw new Error('Failed to schedule meeting.');
      }

      const sessionData: MeetingSession = await schedRes.json();
      setProviderNotice(sessionData.provider_notice || providerNotice);
      setStatusMessage(
        sessionData.provider_mode === 'mock' || sessionData.provider_mode === 'mock_fallback'
          ? 'Starting local meeting simulation. No external bot will join the Google Meet room.'
          : `Deploying Miles bot into ${sessionData.meet_url}...`
      );

      // 2. Launch bot into call
      const startRes = await fetch(`${apiBase}/api/meeting/${sessionData.meeting_id}/start`, {
        method: 'POST',
      });

      if (!startRes.ok) {
        throw new Error('Failed to start meeting session.');
      }

      setStatusMessage(
        sessionData.provider_mode === 'mock' || sessionData.provider_mode === 'mock_fallback'
          ? 'Miles simulation is running locally. Use this for workflow rehearsal; live Meet audio is not connected.'
          : 'Miles has joined the Google Meet. Camera is off, listening via AssemblyAI.'
      );
      await fetchMeetings();
      setActiveTab('history');
    } catch (err: any) {
      setStatusMessage(`Error: ${err.message || 'Failed to start meeting.'}`);
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
            <div className="meet-icon-badge">
              <span className="meet-camera-icon">🎥</span>
            </div>
            <div>
              <div className="meeting-title-row">
                <h2 className="modal-title">Meet Sparring Simulation</h2>
                <span className="audio-only-badge">Local Mock Mode</span>
              </div>
              <p className="modal-subtitle">
                Rehearse the Google Meet workflow locally. Live external bot join/audio requires a real meeting provider.
              </p>
            </div>
          </div>
          <button className="modal-close-btn" onClick={onClose} aria-label="Close meeting simulation">&times;</button>
        </div>

        {/* Tab switcher */}
        <div className="meeting-tab-bar">
          <button
            className={`meeting-tab-btn ${activeTab === 'schedule' ? 'active' : ''}`}
            onClick={() => setActiveTab('schedule')}
          >
            🚀 Schedule Simulation
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

        {activeTab === 'schedule' ? (
          <div className="meeting-tab-content">
            {/* Meet URL input */}
            <div className="form-group">
              <label className="form-label">Google Meet Link or Demo Link</label>
              <div className="meet-url-input-row">
                <input
                  type="text"
                  className="form-input meet-input"
                  placeholder="https://meet.google.com/abc-defg-hij"
                  value={meetUrl}
                  onChange={(e) => setMeetUrl(e.target.value)}
                  disabled={isLoading}
                />
                <button
                  type="button"
                  className="secondary-btn instant-link-btn"
                  onClick={handleGenerateLink}
                  disabled={isLoading}
                >
                  ⚡ Generate Demo Link
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
                  <strong>Ground-Truth Context:</strong>
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
                  Miles will cross-examine you against exact numbers: {activeContext.numeric_metrics.slice(0, 3).map(m => `${m.name}: ${m.raw_value}`).join(' • ')}...
                </div>
              ) : (
                <div className="context-empty-hint">
                  Attach a deck or CV to let Miles fact-check and rectify your numbers in the simulated meeting flow.
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
                Cancel
              </button>
              <button
                type="button"
                className="primary-btn launch-meet-btn"
                onClick={handleScheduleAndStart}
                disabled={isLoading}
              >
                {isLoading ? (
                  <>
                    <span className="spinner-sm"></span> Starting Simulation...
                  </>
                ) : (
                  <>🚀 Start Local Simulation</>
                )}
              </button>
            </div>
          </div>
        ) : (
          <div className="meeting-history-tab">
            {meetings.length === 0 ? (
              <div className="empty-history-state">
                <span className="empty-history-icon">📅</span>
                <p>No meeting simulations yet.</p>
                <button
                  type="button"
                  className="secondary-btn"
                  onClick={() => setActiveTab('schedule')}
                >
                  Schedule Your First Simulation
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
                          {actionLoadingId === m.meeting_id ? 'Concluding...' : 'End Simulation & Generate Debrief'}
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
                            setActiveTab('schedule');
                          }}
                        >
                          Start Simulation
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
