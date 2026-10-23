import React, { useEffect, useMemo, useState, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Activity,
  ArrowLeft,
  ArrowRight,
  Check,
  ChevronRight,
  Clock3,
  FileText,
  Headphones,
  History,
  MessageSquare,
  Phone,
  Plus,
  RefreshCw,
  Search,
  Shield,
  Sparkles,
  Wifi,
  WifiOff,
  X,
} from 'lucide-react';
import './styles.css';

const API = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');

// 8 authentic cold call stages derived from DeepThought structure & empirical analysis of 100 transcripts
const STAGE_SEED = [
  {
    id: 'opening',
    position: 1,
    title: 'Opening',
    purpose: 'Reach the right person and say who you are. The prospect decides in the first ten seconds whether this call is worth a minute.',
    guidance: 'Be brief, direct, and natural. Verify identity immediately; do not pitch to an assistant or switchboard.',
    prospect_patterns: [
      '“Can you please come again? From where are you calling?”',
      '“I’ll let you know the concerned person. You can call directly.”',
      '“The person you are asking for left the company last year.”',
    ],
    stage_taps: [
      'Reached right person',
      'Wrong person / referral',
      'Contact left company',
      'Switchboard / PA barrier',
    ],
  },
  {
    id: 'purpose',
    position: 2,
    title: 'Purpose',
    purpose: 'Say in one or two sentences why you called, in words the prospect can repeat to a colleague. A purpose they cannot repeat is a purpose they did not hear.',
    guidance: 'Give a concrete reason for calling without corporate jargon. Avoid sounding like a scripted telemarketer.',
    prospect_patterns: [
      '“What is this about? Can you just elaborate?”',
      '“Uh, from where? What does your company do?”',
      '“Who gave you this number? Where did you get my contact?”',
      '“Is this a sales call? What are you proposing?”',
    ],
    stage_taps: [
      'Asked what we do',
      'Asked where we got number',
      'Said it is a sales call',
      'Let me go on',
    ],
  },
  {
    id: 'permission',
    position: 3,
    title: 'Permission',
    purpose: 'Find out whether they are willing to talk now. A clear yes, a clear no, or a time to call back are all good outcomes. Talking on without one is not.',
    guidance: 'Test whether they have time right now. Never talk over a busy prospect; secure a specific callback window.',
    prospect_patterns: [
      '“Actually right now I’m in a customer meeting. Can you call after 2 PM?”',
      '“I am driving right now, but tell me quickly.”',
      '“Can you call me tomorrow afternoon? I will have a few minutes.”',
      '“Send it on WhatsApp first. Let me see it before we talk.”',
    ],
    stage_taps: [
      'Agreed to talk now',
      'Callback requested (named time)',
      'Driving / in meeting',
      'Send WhatsApp/Email first',
    ],
  },
  {
    id: 'their_business',
    position: 4,
    title: 'Their business',
    purpose: 'Ask about their company and their work before saying anything about yours. People talk about what they do; they rarely listen to what you do.',
    guidance: 'Ask an informed, open question about their operations or focus. Let them speak first; do not jump to the pitch.',
    prospect_patterns: [
      '“Tell me about your company first, then we can get into details.”',
      '“Our company is the market leader; we don’t fit that profile.”',
      '“That pertains to manufacturing; I only handle corporate strategy.”',
      '“We operate primarily through an authorized distributor network.”',
    ],
    stage_taps: [
      'Shared operations & setup',
      'Corrected business model',
      'Turned question to caller',
      'Gave minimal 1-line answer',
    ],
  },
  {
    id: 'their_need',
    position: 5,
    title: 'Their need, in their words',
    purpose: 'Hear what they are trying to do or struggling with, in their own words. This is the one stage where the caller writes down exactly what was said.',
    guidance: 'Log their exact words verbatim in the quote box. Do not summarize or paraphrase what they said.',
    prospect_patterns: [
      '“Our main priority right now is expanding export margins and plant utilization.”',
      '“We don’t believe in external experiments. We are fine with our current business.”',
      '“Because we are still an early startup, we don’t have the budget or requirement for that now.”',
      '“What exactly would you require from our side to make this work?”',
    ],
    stage_taps: [
      'Stated specific priority/bottleneck',
      'Said everything is fine / no need',
      'Startup / too early for advisory',
      'Asked what we can do for them',
    ],
  },
  {
    id: 'objection',
    position: 6,
    title: 'Objection',
    purpose: 'Hear the reason for a no and understand it. A reason you understand can be answered on this call or the next; a reason you talked over cannot.',
    guidance: 'Acknowledge the objection without becoming defensive. Clarify whether it is contract lock-in, internal capability, or bad timing.',
    prospect_patterns: [
      '“Because we are an MNC, we already have such consultants at a global level under a single contract.”',
      '“We already engaged a consultant last month; that’s going to run for two quarters.”',
      '“We have a robust process internally which we use for problem solving; we don’t outsource.”',
      '“I am not interested in this at the moment. Thank you for asking though.”',
    ],
    stage_taps: [
      'Global contract / locked vendor',
      'Internal team / robust process',
      'No budget / not a priority',
      'Send info in writing first',
    ],
  },
  {
    id: 'next_step',
    position: 7,
    title: 'Next step',
    purpose: 'Agree one concrete thing: a document on WhatsApp or email, a call at a named time, a meeting. One thing, named, with a time or a channel.',
    guidance: 'Lock down a specific channel or date/time. A time named by them is worth more than a time proposed by you.',
    prospect_patterns: [
      '“You send it on WhatsApp to this number. Let me have a look and come back to you.”',
      '“That’s my personal email; please send it to my official company ID.”',
      '“Give me a call sometime Tuesday morning around 11:30 AM after my meeting.”',
      '“You can send an email with your previous profiles and case studies for review.”',
    ],
    stage_taps: [
      'Specific callback time set',
      'Official email deck agreed',
      'WhatsApp brief requested',
      'Referred to colleague with contact',
    ],
  },
  {
    id: 'close',
    position: 8,
    title: 'Close',
    purpose: 'End the call clearly and record what happened: the outcome, the next step, and the prospect’s words from stage 5. The record is what the next call is built on.',
    guidance: 'End professionally and immediately record the honest outcome. Never log an outcome that contradicts what the prospect said.',
    prospect_patterns: [
      '“Sure, thank you Priya/Rohit. Send it over email and we will connect next week.”',
      '“All set. Thank you for your time, have a good day.”',
      '“Okay, fine, works. Bye.”',
      '[Call disconnected / line dropped]',
    ],
    stage_taps: [
      'Confirmed next step & closed clean',
      'Polite exit after objection',
      'Line dropped / hung up',
      'Logged discrepancy for next call',
    ],
  },
];

const OUTCOMES = [
  { id: 'meeting_booked', label: 'Meeting booked', tone: 'green' },
  { id: 'next_step_agreed', label: 'Next step agreed', tone: 'green' },
  { id: 'agreed_to_receive_report', label: 'Agreed to receive doc / WhatsApp', tone: 'blue' },
  { id: 'follow_up', label: 'Follow-up callback agreed', tone: 'blue' },
  { id: 'interested', label: 'Interested (general)', tone: 'blue' },
  { id: 'not_interested', label: 'Not interested', tone: 'gray' },
  { id: 'do_not_call', label: 'Do not call', tone: 'gray' },
  { id: 'wrong_person', label: 'Wrong person / referred', tone: 'amber' },
  { id: 'moved_company', label: 'Moved company', tone: 'amber' },
  { id: 'no_answer', label: 'No answer / dropped', tone: 'gray' },
  { id: 'other', label: 'Other', tone: 'gray' },
];

async function request(path, options = {}) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 8000);
  try {
    const res = await fetch(`${API}${path}`, {
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
      signal: controller.signal,
      ...options,
    });
    clearTimeout(timeoutId);
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(body.detail || `Request failed (${res.status})`);
    }
    return body;
  } catch (err) {
    clearTimeout(timeoutId);
    throw err;
  }
}

function localId() {
  return `local-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
}

function initials(name = '') {
  return name.trim().split(/\s+/).slice(0, 2).map(x => x[0]?.toUpperCase()).join('') || 'PC';
}

function formatDate(value) {
  if (!value) return 'In progress';
  const d = new Date(value);
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) + ' · ' + d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
}

function formatTimer(totalSec) {
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function App() {
  const [stages, setStages] = useState(STAGE_SEED);
  const [screen, setScreen] = useState('call'); // 'call' | 'history' | 'detail'
  const [activeCall, setActiveCall] = useState(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const [fields, setFields] = useState({ prospect_name: '', company_name: '' });

  // Live call timer
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  // Current stage editor state
  const [selectedTap, setSelectedTap] = useState('');
  const [words, setWords] = useState('');
  const [notes, setNotes] = useState('');
  const [stageResults, setStageResults] = useState({});

  // History & detail state
  const [history, setHistory] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [historyError, setHistoryError] = useState('');
  const [search, setSearch] = useState('');
  const [outcome, setOutcome] = useState('meeting_booked');
  const [outcomeNotes, setOutcomeNotes] = useState('');
  const [finishOpen, setFinishOpen] = useState(false);
  const [detailCall, setDetailCall] = useState(null);

  // Status & communication
  const [busy, setBusy] = useState(false);
  const [savingStage, setSavingStage] = useState(false);
  const [error, setError] = useState('');
  const [apiState, setApiState] = useState('checking'); // 'connected' | 'local' | 'offline' | 'checking'
  const [aiBusy, setAiBusy] = useState(false);
  const [aiNotice, setAiNotice] = useState('');

  // Keep refs to avoid stale closure races during atomic transitions
  const activeCallRef = useRef(activeCall);
  activeCallRef.current = activeCall;
  const stageResultsRef = useRef(stageResults);
  stageResultsRef.current = stageResults;
  const currentStageRef = useRef({ words, notes, selectedTap, activeIndex });
  currentStageRef.current = { words, notes, selectedTap, activeIndex };

  // Timer loop for active call
  useEffect(() => {
    if (!activeCall || activeCall.ended_at) {
      setElapsedSeconds(0);
      return;
    }
    const startMs = new Date(activeCall.started_at).getTime();
    const updateTimer = () => {
      const now = Date.now();
      setElapsedSeconds(Math.max(0, Math.floor((now - startMs) / 1000)));
    };
    updateTimer();
    const interval = setInterval(updateTimer, 1000);
    return () => clearInterval(interval);
  }, [activeCall]);

  // Initial load
  useEffect(() => {
    request('/stages')
      .then(data => {
        if (Array.isArray(data) && data.length === 8) {
          setStages(data);
        }
      })
      .catch(() => {});

    request('/health')
      .then(data => {
        if (data.database === 'connected') {
          setApiState('connected');
        } else if (data.database === 'not_configured') {
          setApiState('local');
        } else {
          setApiState('offline');
        }
      })
      .catch(() => setApiState('offline'));

    loadHistory();
  }, []);

  const stage = stages[activeIndex] || STAGE_SEED[0];
  const completedCount = useMemo(() => Object.keys(stageResults).filter(k => stageResults[k]?.result).length, [stageResults]);

  // Load and merge history from server and localStorage without duplicates
  async function loadHistory() {
    setLoadingHistory(true);
    setHistoryError('');
    const raw = localStorage.getItem('sidecall-history');
    let localCalls = [];
    try {
      localCalls = raw ? JSON.parse(raw) : [];
    } catch {
      localCalls = [];
    }

    try {
      const serverCalls = await request('/calls');
      const mergedMap = new Map();

      // Put local calls in the map first
      for (const call of localCalls) {
        mergedMap.set(call.id, { ...call, isLocal: true });
      }

      // Merge server records; if matching id, server wins and marks as synced
      if (Array.isArray(serverCalls)) {
        for (const s of serverCalls) {
          const existing = mergedMap.get(s.id);
          mergedMap.set(s.id, {
            ...existing,
            ...s,
            isLocal: false,
          });
        }
      }

      const sorted = Array.from(mergedMap.values()).sort(
        (a, b) => new Date(b.started_at || 0) - new Date(a.started_at || 0)
      );
      setHistory(sorted);
    } catch (err) {
      if (localCalls.length > 0) {
        const localOnly = localCalls.map(c => ({ ...c, isLocal: true })).sort(
          (a, b) => new Date(b.started_at || 0) - new Date(a.started_at || 0)
        );
        setHistory(localOnly);
      } else {
        setHistoryError(err.message || 'Could not connect to backend database.');
      }
    } finally {
      setLoadingHistory(false);
    }
  }

  // Safe persistence worker that saves current stage data and returns updated results map
  async function performSaveStage(wordsToSave, notesToSave, tapToSave, targetStageId = null) {
    const call = activeCallRef.current;
    if (!call) return stageResultsRef.current;

    const currentStageId = targetStageId || stages[currentStageRef.current.activeIndex]?.id || 'opening';
    const chosenResult = tapToSave || (stage?.stage_taps?.[0] || 'completed');

    const stagePayload = {
      stage_id: currentStageId,
      result: chosenResult,
      prospect_words: wordsToSave || '',
      notes: notesToSave || '',
      updated_at: new Date().toISOString(),
    };

    setSavingStage(true);

    // Sync to backend if activeCall is a server-backed call
    if (!call.isLocal) {
      try {
        await request(`/calls/${call.id}/stage-results`, {
          method: 'POST',
          body: JSON.stringify({
            stage_id: currentStageId,
            result: chosenResult,
            prospect_words: wordsToSave || '',
            notes: notesToSave || '',
          }),
        });
      } catch (e) {
        console.warn('Backend sync failed, storing locally:', e.message);
      }
    }

    // Update local state map
    const updated = {
      ...stageResultsRef.current,
      [currentStageId]: stagePayload,
    };
    stageResultsRef.current = updated;
    setStageResults(updated);

    // Always mirror to localStorage
    try {
      const existingHistory = JSON.parse(localStorage.getItem('sidecall-history') || '[]');
      const updatedRecord = {
        ...call,
        current_stage_id: currentStageId,
        stage_results: Object.values(updated),
      };
      const filtered = existingHistory.filter(c => c.id !== call.id);
      localStorage.setItem('sidecall-history', JSON.stringify([updatedRecord, ...filtered]));
    } catch (e) {
      console.warn('LocalStorage write failed:', e);
    }

    setSavingStage(false);
    return updated;
  }

  // Atomic transition: strictly awaits save of active stage BEFORE switching
  async function goToStage(targetIndex) {
    if (busy || savingStage) return;
    const safeIndex = Math.max(0, Math.min(stages.length - 1, targetIndex));
    if (safeIndex === activeIndex) return;

    setError('');
    // 1. Await save of current stage
    const currentWords = words;
    const currentNotes = notes;
    const currentTap = selectedTap;

    const freshResults = await performSaveStage(currentWords, currentNotes, currentTap);

    // 2. Load the target stage's stored data
    const targetStage = stages[safeIndex];
    const targetData = freshResults[targetStage.id] || {};

    setActiveIndex(safeIndex);
    setWords(targetData.prospect_words || '');
    setNotes(targetData.notes || '');
    setSelectedTap(targetData.result || targetStage.stage_taps?.[0] || '');

    // 3. Inform server of active stage position
    const call = activeCallRef.current;
    if (call && !call.isLocal) {
      request(`/calls/${call.id}/stage`, {
        method: 'PATCH',
        body: JSON.stringify({ stage_id: targetStage.id }),
      }).catch(() => {});
    }
  }

  async function startCall(e) {
    e?.preventDefault();
    setError('');
    setBusy(true);

    const firstStage = stages[0] || STAGE_SEED[0];
    const localCallRecord = {
      id: localId(),
      prospect_name: fields.prospect_name.trim() || 'Unnamed prospect',
      company_name: fields.company_name.trim() || '',
      started_at: new Date().toISOString(),
      current_stage_id: firstStage.id,
      stage_results: [],
      isLocal: true,
    };

    try {
      const created = await request('/calls', {
        method: 'POST',
        body: JSON.stringify({
          prospect_name: fields.prospect_name.trim() || null,
          company_name: fields.company_name.trim() || null,
        }),
      });
      setActiveCall({ ...created, isLocal: false });
      setApiState('connected');
    } catch {
      setActiveCall(localCallRecord);
      setApiState('offline');
      setError('Backend unavailable. Call is running locally in this browser and will be stored securely in local memory.');
    }

    setActiveIndex(0);
    setStageResults({});
    setWords('');
    setNotes('');
    setSelectedTap(firstStage.stage_taps?.[0] || '');
    setScreen('call');
    setBusy(false);
  }

  async function handleManualSave() {
    await performSaveStage(words, notes, selectedTap);
  }

  async function closeCall() {
    const call = activeCallRef.current;
    if (!call) return;
    setBusy(true);
    setError('');

    // Ensure the current active stage is saved
    const finalResults = await performSaveStage(words, notes, selectedTap);

    const endedAt = new Date().toISOString();
    const finalRecord = {
      ...call,
      ended_at: endedAt,
      outcome,
      outcome_notes: outcomeNotes,
      stage_results: Object.values(finalResults),
      current_stage_id: stage.id,
    };

    if (!call.isLocal) {
      try {
        await request(`/calls/${call.id}/close`, {
          method: 'POST',
          body: JSON.stringify({ outcome, outcome_notes: outcomeNotes }),
        });
      } catch (e) {
        console.warn('Could not sync close to server:', e.message);
      }
    }

    // Persist final closed record in localStorage
    try {
      const local = JSON.parse(localStorage.getItem('sidecall-history') || '[]');
      const filtered = local.filter(c => c.id !== call.id);
      localStorage.setItem('sidecall-history', JSON.stringify([finalRecord, ...filtered]));
    } catch (e) {
      console.warn('LocalStorage write failed:', e);
    }

    setFinishOpen(false);
    setActiveCall(null);
    setScreen('history');
    await loadHistory();
    setBusy(false);
  }

  async function openCallDetail(c) {
    setDetailCall(c);
    setAiNotice('');
    setScreen('detail');
    if (!c.isLocal) {
      try {
        const full = await request(`/calls/${c.id}`);
        setDetailCall({ ...full, isLocal: false });
      } catch {}
    }
  }

  async function generateAiSummary() {
    if (!detailCall) return;
    setAiBusy(true);
    setAiNotice('');

    try {
      const data = await request(`/calls/${detailCall.id}/ai-summary`, {
        method: 'POST',
        body: JSON.stringify({ refresh: false }),
      });

      if (data.status === 'disabled' || !data.configured) {
        setAiNotice(data.message || 'AI debrief is not configured. Set LLM_API_KEY on the backend.');
      } else if (data.summary) {
        setDetailCall(prev => ({ ...prev, ai_summary: data.summary }));
      }
    } catch (e) {
      setAiNotice(e.message || 'Unable to generate AI debrief.');
    } finally {
      setAiBusy(false);
    }
  }

  const visibleHistory = history.filter(c => {
    const q = search.toLowerCase();
    const p = (c.prospect_name || '').toLowerCase();
    const comp = (c.company_name || '').toLowerCase();
    const o = (c.outcome || '').toLowerCase();
    return p.includes(q) || comp.includes(q) || o.includes(q);
  });

  return (
    <div className="app-shell">
      {/* Left Navigation Rail */}
      <aside className="rail" aria-label="Sidebar Navigation">
        <div className="brand-mark" title="ColdCall Companion">
          <Headphones size={20} />
        </div>
        <div className="rail-rule" />
        <button
          className={`rail-button ${screen === 'call' ? 'selected' : ''}`}
          title="Live Call Workspace"
          onClick={() => setScreen('call')}
          aria-label="Live Call"
        >
          <Phone size={19} />
        </button>
        <button
          className={`rail-button ${screen === 'history' ? 'selected' : ''}`}
          title="Call History & Records"
          onClick={() => {
            setScreen('history');
            loadHistory();
          }}
          aria-label="Call History"
        >
          <History size={19} />
        </button>
        <div className="rail-bottom">
          <span
            className={`api-dot ${apiState}`}
            title={`Database status: ${apiState}`}
          />
        </div>
      </aside>

      {/* Main Workspace Area */}
      <main className="main-area">
        {/* Top Header Bar */}
        <header className="topbar">
          <div className="crumb">
            <span>COLDCALL COMPANION</span>
            <span className="slash">/</span>
            <strong>
              {screen === 'call'
                ? activeCall
                  ? 'Live Call in Progress'
                  : 'Start Call'
                : screen === 'detail'
                ? 'Call Record Detail'
                : 'Call History'}
            </strong>
          </div>
          <div className="top-actions">
            <div className={`connection ${apiState}`}>
              {apiState === 'connected' ? (
                <>
                  <Wifi size={13} className="conn-icon" />
                  <span>Synced to Cloud</span>
                </>
              ) : apiState === 'local' ? (
                <>
                  <span className="api-dot local" />
                  <span>Local Mode (DB Unset)</span>
                </>
              ) : (
                <>
                  <WifiOff size={13} className="conn-icon" />
                  <span>Offline Mode</span>
                </>
              )}
            </div>
            <div className="avatar" title="Caller Profile">
              FDE
            </div>
          </div>
        </header>

        {/* SCREEN 1: LIVE CALL OR START FORM */}
        {screen === 'call' && (
          <section className="content-wrap">
            {!activeCall ? (
              <div className="welcome-layout">
                <div className="welcome-copy">
                  <div className="eyebrow">
                    <span className="eyebrow-dot" /> OUTBOUND COLD-CALL SIDE SCREEN
                  </div>
                  <h1>
                    Stay with the<br />
                    <em>conversation.</em>
                  </h1>
                  <p className="lede">
                    A calm, editorial guide for the call you’re in. Follow the 8 proven stages, anticipate prospect responses, log exact words, and never split your attention.
                  </p>
                  <div className="feature-line">
                    <div className="feature-icon">
                      <Activity size={17} />
                    </div>
                    <div>
                      <strong>Eight evidence-backed stages</strong>
                      <span>From Opening to Close, tailored from 100 actual outbound transcripts.</span>
                    </div>
                  </div>
                  <div className="feature-line">
                    <div className="feature-icon">
                      <MessageSquare size={17} />
                    </div>
                    <div>
                      <strong>Single-tap logging & verbatim quotes</strong>
                      <span>Four quick taps per stage keep typing minimal so you hear everything.</span>
                    </div>
                  </div>
                  <div className="welcome-footer">
                    <span className="mini-line" /> DESIGNED FOR LIVE CALL FOCUS
                  </div>
                </div>

                <form className="start-card" onSubmit={startCall}>
                  <div className="card-overline">
                    NEW CONVERSATION <span>STAGE 01 / 08</span>
                  </div>
                  <div className="card-icon">
                    <Phone size={19} />
                  </div>
                  <h2>Begin new call</h2>
                  <p>Optional details help you find and review this conversation later.</p>

                  <label htmlFor="prospect-name-input">
                    PROSPECT NAME <span>OPTIONAL</span>
                  </label>
                  <input
                    id="prospect-name-input"
                    autoComplete="off"
                    value={fields.prospect_name}
                    onChange={e => setFields({ ...fields, prospect_name: e.target.value })}
                    placeholder="e.g. Dr. Anjali Menon or Suresh Patel"
                    maxLength={160}
                  />

                  <label htmlFor="company-name-input">
                    COMPANY / ACCOUNT <span>OPTIONAL</span>
                  </label>
                  <input
                    id="company-name-input"
                    autoComplete="off"
                    value={fields.company_name}
                    onChange={e => setFields({ ...fields, company_name: e.target.value })}
                    placeholder="e.g. Kalyx Enterprises or Menon Clinic"
                    maxLength={180}
                  />

                  {error && <div className="inline-error">{error}</div>}

                  <button className="primary-button full" disabled={busy} type="submit">
                    <span>{busy ? 'Starting call…' : 'Open live call guide'}</span>
                    <ArrowRight size={17} />
                  </button>

                  <div className="start-note">
                    <Shield size={13} />
                    <span>Deterministic, privacy-safe & offline-resilient</span>
                  </div>
                </form>
              </div>
            ) : (
              <div className="call-layout">
                {/* Reference Screen Centered Container */}
                <div className="reference-screen-wrapper">
                  <div className="reference-card-surface">
                    {/* Top Guide Bar with Live Timer */}
                    <div className="reference-guide-bar">
                      <span className="reference-brand-label">
                        COLDCALL COMPANION · CALL GUIDE
                      </span>
                      <span className="reference-timer-label">
                        {formatTimer(elapsedSeconds)}
                      </span>
                    </div>

                    {/* Prospect Info Header */}
                    <div className="reference-prospect-bar">
                      <div className="reference-prospect-name">
                        {activeCall.prospect_name || 'Unnamed prospect'}
                      </div>
                      <div className="reference-prospect-sub">
                        {activeCall.company_name
                          ? `${activeCall.company_name} · first call`
                          : 'First call · outbound conversation'}
                        {activeCall.isLocal && (
                          <span className="offline-pill" title="Stored locally in this browser">
                            LOCAL
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Numbered Stage Stepper 1 - 8 */}
                    <div className="reference-stepper-bar" role="tablist">
                      {stages.map((s, i) => {
                        const isCurrent = i === activeIndex;
                        const isSaved = Boolean(stageResults[s.id]?.result);
                        return (
                          <button
                            key={s.id}
                            type="button"
                            role="tab"
                            aria-selected={isCurrent}
                            className={`reference-step-item ${isCurrent ? 'active' : isSaved ? 'saved' : 'pending'}`}
                            onClick={() => goToStage(i)}
                            title={`${i + 1}. ${s.title}`}
                          >
                            {i + 1}
                          </button>
                        );
                      })}
                    </div>

                    {/* Stage Details */}
                    <div className="reference-content-body">
                      <div className="reference-stage-kicker">
                        STAGE {activeIndex + 1} OF 8
                      </div>
                      <h2 className="reference-stage-title">{stage.title}</h2>
                      <p className="reference-stage-purpose">{stage.purpose}</p>

                      {/* THEY MAY SAY (Empirical Cues with Blue Accent Left Border) */}
                      <div className="reference-section-header">THEY MAY SAY</div>
                      <div className="reference-cues-list">
                        {(stage.prospect_patterns || []).map((pat, idx) => (
                          <div className="reference-cue-item" key={idx}>
                            <span>{pat}</span>
                            <button
                              type="button"
                              title="Append to prospect's words"
                              onClick={() => {
                                const clean = pat.replace(/^“|”$/g, '');
                                setWords(w => (w ? `${w}\n${clean}` : clean));
                              }}
                            >
                              <Plus size={13} />
                            </button>
                          </div>
                        ))}
                      </div>

                      {/* WHAT HAPPENED (2x2 Taps Grid) */}
                      <div className="reference-section-header">WHAT HAPPENED</div>
                      <div className="reference-taps-grid">
                        {(stage.stage_taps || ['Moved forward', 'Asked question', 'Objection', 'Let me go on']).map((tapText, idx) => {
                          const isPressed = selectedTap === tapText;
                          return (
                            <button
                              type="button"
                              key={idx}
                              className={`reference-tap-button ${isPressed ? 'pressed' : ''}`}
                              onClick={() => setSelectedTap(tapText)}
                            >
                              {tapText}
                            </button>
                          );
                        })}
                      </div>

                      {/* PROSPECT'S WORDS (HER WORDS) */}
                      <div className="reference-section-header flex-between">
                        <span>HER / PROSPECT’S WORDS</span>
                        {stage.id === 'their_need' ? (
                          <span className="crucial-callout">STAGE 5: WRITE EXACT WORDS</span>
                        ) : (
                          <span className="subtle-callout">AS CLOSE TO VERBATIM AS POSSIBLE</span>
                        )}
                      </div>
                      <textarea
                        id="prospect-words-input"
                        className={`reference-textarea ${stage.id === 'their_need' ? 'need-highlight' : ''}`}
                        value={words}
                        onChange={e => setWords(e.target.value)}
                        placeholder="“accounting for what, we already have a CA who files everything…”"
                        rows={3}
                        maxLength={10000}
                      />

                      {/* YOUR PRIVATE NOTES (Optional) */}
                      <div className="reference-section-header flex-between" style={{ marginTop: '16px' }}>
                        <span>YOUR NOTES</span>
                        <span className="subtle-callout">OPTIONAL</span>
                      </div>
                      <textarea
                        id="extra-notes-input"
                        className="reference-textarea notes-box"
                        value={notes}
                        onChange={e => setNotes(e.target.value)}
                        placeholder="Context, follow-up specifics, timing details to remember…"
                        rows={2}
                        maxLength={4000}
                      />

                      {/* Bottom Controls: NEXT: [STAGE] & END CALL */}
                      <div className="reference-bottom-actions">
                        {activeIndex < 7 ? (
                          <button
                            type="button"
                            className="reference-next-button"
                            onClick={() => goToStage(activeIndex + 1)}
                            disabled={savingStage}
                          >
                            <span>NEXT: {stages[activeIndex + 1]?.title?.toUpperCase()}</span>
                            <ArrowRight size={15} />
                          </button>
                        ) : (
                          <button
                            type="button"
                            className="reference-next-button"
                            onClick={() => setFinishOpen(true)}
                          >
                            <span>WRAP UP & OUTCOME</span>
                            <ArrowRight size={15} />
                          </button>
                        )}

                        <button
                          type="button"
                          className="reference-end-button"
                          onClick={() => setFinishOpen(true)}
                        >
                          END CALL
                        </button>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="call-bottomline">
                  <span>
                    <Clock3 size={14} /> {completedCount} of 8 stages logged
                  </span>
                  <span>Atomic saves prevent dropped notes when switching stages.</span>
                </div>
              </div>
            )}
          </section>
        )}

        {/* SCREEN 2: CALL DETAIL VIEW */}
        {screen === 'detail' && (
          <section className="content-wrap history-view detail-view">
            <button
              className="quiet-button back-history"
              onClick={() => {
                setScreen('history');
                loadHistory();
              }}
            >
              <ArrowLeft size={15} /> Back to call history
            </button>

            {detailCall && (
              <>
                <div className="detail-heading">
                  <div>
                    <div className="eyebrow">
                      <span className="eyebrow-dot" /> CALL RECORD
                      <span className="mid-dot">·</span> Started {formatDate(detailCall.started_at)}
                      {detailCall.isLocal && (
                        <span className="offline-pill" title="Stored in local browser memory">
                          OFFLINE / LOCAL
                        </span>
                      )}
                    </div>
                    <h1>
                      {detailCall.prospect_name || 'Unnamed prospect'}
                      <br />
                      <em>{detailCall.company_name || 'Company not recorded'}</em>
                    </h1>
                    <p>
                      {detailCall.ended_at
                        ? `Ended ${formatDate(detailCall.ended_at)}`
                        : 'Call currently in progress'}
                    </p>
                  </div>

                  <div className="detail-outcome">
                    <span
                      className={`outcome-dot ${
                        OUTCOMES.find(o => o.id === detailCall.outcome)?.tone || 'gray'
                      }`}
                    />
                    <strong>
                      {OUTCOMES.find(o => o.id === detailCall.outcome)?.label || detailCall.outcome || 'In progress'}
                    </strong>
                  </div>
                </div>

                <div className="detail-columns">
                  {/* Left Column: Stage by Stage Record */}
                  <section className="detail-card">
                    <div className="section-kicker">CONVERSATION RECORD</div>
                    <h2>Stage by stage</h2>

                    {(detailCall.stage_results || []).length === 0 ? (
                      <p className="detail-empty">No stage notes were recorded for this call.</p>
                    ) : (
                      (detailCall.stage_results || []).map((r, i) => {
                        const st = stages.find(x => x.id === r.stage_id);
                        return (
                          <div className="detail-stage" key={r.stage_id || i}>
                            <div className="detail-stage-title">
                              <span className="stage-reached">
                                {String(st?.position || i + 1).padStart(2, '0')}
                              </span>
                              <strong>{st?.title || r.stage_id}</strong>
                              <span className="detail-result">
                                {r.result?.replace(/_/g, ' ')}
                              </span>
                            </div>
                            {r.prospect_words && (
                              <blockquote>“{r.prospect_words}”</blockquote>
                            )}
                            {r.notes && <p className="caller-notes-text">{r.notes}</p>}
                          </div>
                        );
                      })
                    )}

                    {detailCall.outcome_notes && (
                      <div className="detail-outcome-notes">
                        <div className="section-kicker">NEXT STEP & CONTEXT NOTES</div>
                        <p>{detailCall.outcome_notes}</p>
                      </div>
                    )}
                  </section>

                  {/* Right Column: AI-Assisted Review */}
                  <section className="detail-card ai-card">
                    <div className="notes-icon">
                      <Sparkles size={16} />
                    </div>
                    <div className="section-kicker">POST-CALL REVIEW</div>
                    <h2>AI-Assisted Debrief</h2>
                    <p className="ai-intro">
                      Generates safe coaching insights based strictly on caller-recorded notes. Does not alter or invent prospect words.
                    </p>

                    {detailCall.ai_summary ? (
                      <div className="ai-summary">
                        <p className="ai-summary-text">{detailCall.ai_summary.summary}</p>

                        {detailCall.ai_summary.objection_classification && (
                          <>
                            <div className="section-kicker">OBJECTION CLASSIFICATION</div>
                            <div className="ai-objection-tag">
                              {detailCall.ai_summary.objection_classification}
                            </div>
                          </>
                        )}

                        {detailCall.ai_summary.signals?.length > 0 && (
                          <>
                            <div className="section-kicker">NOTABLE SIGNALS</div>
                            <ul>
                              {detailCall.ai_summary.signals.map((s, idx) => (
                                <li key={idx}>{s}</li>
                              ))}
                            </ul>
                          </>
                        )}

                        {detailCall.ai_summary.follow_up && (
                          <>
                            <div className="section-kicker">RECOMMENDED FOLLOW-UP</div>
                            <p>{detailCall.ai_summary.follow_up}</p>
                          </>
                        )}

                        {detailCall.ai_summary.data_gaps?.length > 0 && (
                          <>
                            <div className="section-kicker">DATA GAPS (FOR NEXT CALL)</div>
                            <ul>
                              {detailCall.ai_summary.data_gaps.map((g, idx) => (
                                <li key={idx}>{g}</li>
                              ))}
                            </ul>
                          </>
                        )}

                        <p className="ai-generated">
                          Model: {detailCall.ai_summary.model || 'Server-configured LLM'} ·{' '}
                          {formatDate(detailCall.ai_summary.generated_at)}
                        </p>
                      </div>
                    ) : (
                      <>
                        <div className="ai-empty-icon">
                          <Sparkles size={22} />
                        </div>
                        <p className="ai-empty">
                          Synthesize logged notes into signals, follow-up recommendations, and data gaps.
                        </p>
                        <button
                          className="primary-button full"
                          onClick={generateAiSummary}
                          disabled={aiBusy || detailCall.isLocal}
                        >
                          <span>{aiBusy ? 'Analyzing conversation…' : 'Generate AI debrief'}</span>
                          <ArrowRight size={15} />
                        </button>

                        {detailCall.isLocal && (
                          <p className="ai-warning">
                            This call is stored locally. AI debrief requires a synced cloud call and server-side LLM credentials.
                          </p>
                        )}
                      </>
                    )}

                    {aiNotice && <div className="inline-error ai-error">{aiNotice}</div>}

                    <div className="ai-footer">
                      <span>
                        <span className="eyebrow-dot" /> RAW NOTES REMAIN UNTOUCHED
                      </span>
                      <span>AI output is an advisory review.</span>
                    </div>
                  </section>
                </div>
              </>
            )}
          </section>
        )}

        {/* SCREEN 3: CALL HISTORY LIST */}
        {screen === 'history' && (
          <section className="content-wrap history-view">
            <div className="history-heading">
              <div>
                <div className="eyebrow">
                  <span className="eyebrow-dot" /> CALL MEMORY & AUDIT
                </div>
                <h1>
                  Every conversation,<br />
                  <em>kept in context.</em>
                </h1>
                <p>Review past calls, the terminal stage reached, verbatim quotes, and outcomes.</p>
              </div>
              <button
                className="primary-button"
                onClick={() => {
                  setActiveCall(null);
                  setScreen('call');
                }}
              >
                <Plus size={16} /> Start new call
              </button>
            </div>

            <div className="history-tools">
              <div className="searchbox">
                <Search size={17} />
                <input
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  placeholder="Search by prospect name, company, or outcome…"
                />
              </div>
              <div className="history-count">
                {visibleHistory.length} {visibleHistory.length === 1 ? 'CALL' : 'CALLS'}
              </div>
            </div>

            <div className="history-table">
              <div className="table-head">
                <span>PROSPECT / COMPANY</span>
                <span>STAGE REACHED</span>
                <span>OUTCOME</span>
                <span>STORAGE</span>
                <span>DATE</span>
                <span />
              </div>

              {loadingHistory ? (
                <div className="loading-history">
                  <RefreshCw size={24} className="spin-icon" />
                  <p>Loading call records from server and local storage…</p>
                </div>
              ) : historyError && visibleHistory.length === 0 ? (
                <div className="error-history">
                  <WifiOff size={24} />
                  <h3>Unable to reach server database</h3>
                  <p>{historyError}</p>
                  <button className="secondary-button" type="button" onClick={loadHistory}>
                    <RefreshCw size={14} /> Retry loading
                  </button>
                </div>
              ) : visibleHistory.length === 0 ? (
                <div className="empty-history">
                  <div className="empty-icon">
                    <History size={22} />
                  </div>
                  <h3>No call records found</h3>
                  <p>Start a conversation to see it listed here with its stage progression and verbatim quotes.</p>
                  <button className="secondary-button" onClick={() => setScreen('call')}>
                    Begin first call <ArrowRight size={15} />
                  </button>
                </div>
              ) : (
                visibleHistory.map(c => {
                  const stageIndex = stages.findIndex(s => s.id === c.current_stage_id);
                  const st = stages[Math.max(0, stageIndex)];
                  const out = OUTCOMES.find(o => o.id === c.outcome);
                  return (
                    <button
                      className="history-row"
                      key={c.id}
                      onClick={() => openCallDetail(c)}
                      type="button"
                    >
                      <span className="prospect-cell">
                        <span className="prospect-avatar">
                          {initials(c.prospect_name)}
                        </span>
                        <span>
                          <strong>{c.prospect_name || 'Unnamed prospect'}</strong>
                          <small>{c.company_name || 'No company specified'}</small>
                        </span>
                      </span>

                      <span>
                        <span className="stage-reached">
                          {String(Math.max(1, stageIndex + 1)).padStart(2, '0')}
                        </span>{' '}
                        {st?.title?.toUpperCase() || 'OPENING'}
                      </span>

                      <span>
                        <span className={`outcome-dot ${out?.tone || 'gray'}`} />
                        {out?.label || c.outcome || 'In progress'}
                      </span>

                      <span>
                        {c.isLocal ? (
                          <span className="offline-badge">Offline (Local)</span>
                        ) : (
                          <span className="synced-badge">Synced</span>
                        )}
                      </span>

                      <span className="date-cell">
                        {formatDate(c.ended_at || c.started_at)}
                      </span>

                      <span className="row-arrow">
                        <ChevronRight size={16} />
                      </span>
                    </button>
                  );
                })
              )}
            </div>

            <div className="history-foot">
              <span>COLDCALL COMPANION · CALL MEMORY</span>
              <span>Only records what was heard and confirmed.</span>
            </div>
          </section>
        )}
      </main>

      {/* CALL WRAP-UP MODAL */}
      {finishOpen && (
        <div
          className="modal-backdrop"
          onMouseDown={e => {
            if (e.target === e.currentTarget) setFinishOpen(false);
          }}
        >
          <section className="finish-modal" role="dialog" aria-modal="true">
            <div className="modal-icon">
              <Phone size={19} />
            </div>
            <button
              className="modal-close"
              type="button"
              onClick={() => setFinishOpen(false)}
              aria-label="Close modal"
            >
              <X size={17} />
            </button>

            <div className="eyebrow">CALL WRAP-UP</div>
            <h2>How did the conversation end?</h2>
            <p>
              Log the honest outcome. A polite exit or objection is valuable data for future targeting.
            </p>

            <div className="outcome-grid">
              {OUTCOMES.map(o => (
                <button
                  type="button"
                  key={o.id}
                  onClick={() => setOutcome(o.id)}
                  className={`outcome-choice ${outcome === o.id ? 'selected' : ''}`}
                >
                  <span className={`outcome-dot ${o.tone}`} />
                  <span>{o.label}</span>
                  {outcome === o.id && <Check size={14} className="choice-check" />}
                </button>
              ))}
            </div>

            <label className="textarea-label" htmlFor="modal-outcome-notes">
              NEXT STEP / CONTEXT <span>OPTIONAL</span>
            </label>
            <textarea
              id="modal-outcome-notes"
              className="extra-input outcome-notes"
              value={outcomeNotes}
              onChange={e => setOutcomeNotes(e.target.value)}
              placeholder="e.g. Agreed to receive deck on WhatsApp; follow-up call Tuesday 11:30 AM."
            />

            <div className="modal-footer">
              <button
                className="quiet-button"
                type="button"
                onClick={() => setFinishOpen(false)}
              >
                Return to call
              </button>
              <button
                className="primary-button"
                type="button"
                onClick={closeCall}
                disabled={busy}
              >
                <span>{busy ? 'Saving…' : 'Save and close call'}</span>
                <Check size={16} />
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

createRoot(document.getElementById('root')).render(<App />);
