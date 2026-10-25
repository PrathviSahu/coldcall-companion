import React, { useEffect, useMemo, useState, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Check,
  ChevronRight,
  Clock3,
  CloudOff,
  FileText,
  Headphones,
  HelpCircle,
  History,
  Mail,
  MessageSquare,
  Phone,
  PhoneOff,
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

function resolveApiBaseUrl() {
  const configured = (import.meta.env.VITE_API_BASE_URL || '').trim().replace(/\/$/, '');
  if (configured) return configured;
  // In development, default to local backend server
  if (import.meta.env.DEV) {
    return 'http://localhost:8000';
  }
  // In production, NEVER silently fall back to localhost:8000 (which targets visitor's machine).
  // Return empty string for relative paths (/api or reverse proxy), and warn in console.
  if (typeof console !== 'undefined' && console.warn) {
    console.warn(
      '[Sidecall Deployment] VITE_API_BASE_URL is not configured in production. ' +
      'Requests will use relative endpoints. For separate backend deployments, configure VITE_API_BASE_URL in your hosting build variables.'
    );
  }
  return '';
}

const API = resolveApiBaseUrl();

// 8 authentic cold call stages derived from DeepThought structure & empirical analysis of 100 transcripts
const STAGE_SEED = [
  {
    id: 'opening',
    position: 1,
    title: 'Opening',
    purpose: 'Reach the right person and say who you are. The prospect decides in the first ten seconds whether this call is worth a minute.',
    guidance: 'Be brief, direct, and natural. Verify identity immediately; do not pitch to an assistant or switchboard.',
    prospect_patterns: ["“Could you clarify which company you represent?”", "“The concerned manager is someone else; I can share their direct extension.”", "“The person you are inquiring about has left the organization.”"],
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
    prospect_patterns: ["“Can you give me a one-sentence summary of what your company does?”", "“Where did you get my contact number?”", "“Is this an outbound sales inquiry?”"],
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
    prospect_patterns: ["“I am currently in a client meeting; please call back after 2 PM.”", "“I am currently in transit, but you have one minute to explain.”", "“Please share details on WhatsApp or email prior to a call.”"],
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
    prospect_patterns: ["“Tell me about your firm first before we discuss our operations.”", "“We are market leaders; that operational model does not apply to us.”", "“That falls under manufacturing; I only manage corporate strategy.”"],
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
    prospect_patterns: ["“Our current priority is improving plant capacity utilization and export margins.”", "“Our current business operations are completely stable; no advisory is required.”", "“We are an early-stage startup with limited budget for external consultants.”"],
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
    prospect_patterns: ["“We have a multi-year global contract with an enterprise advisory partner.”", "“We have a robust internal team and process for operational problem solving.”", "“This is not an active priority for us at this time.”"],
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
    prospect_patterns: ["“Please send a summary on WhatsApp and I will review it.”", "“Please send documentation to my official corporate email address.”", "“Call me on Tuesday at 11:30 AM following our management review.”"],
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
      '“Confirmed; send the email and we will speak next week.”',
      '“Thank you for reaching out; have a good day.”',
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

const CALLER_TOKEN_KEY = 'sidecall_caller_token';

function getCallerToken() {
  try {
    return (localStorage.getItem(CALLER_TOKEN_KEY) || '').trim();
  } catch {
    return '';
  }
}

async function request(path, options = {}) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 20000);
  try {
    const token = getCallerToken();
    const res = await fetch(`${API}${path}`, {
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(options.headers || {}),
      },
      signal: controller.signal,
      ...options,
    });
    clearTimeout(timeoutId);
    const contentType = res.headers.get('content-type') || '';
    if (!contentType.includes('application/json')) {
      const err = new Error(
        `Expected JSON response but received ${contentType || 'non-JSON'} from ${path}. ` +
        `Ensure VITE_API_BASE_URL is configured for your backend origin.`
      );
      err.status = res.status;
      throw err;
    }
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      const err = new Error(body.detail || `Request failed (${res.status})`);
      err.status = res.status;
      throw err;
    }
    return body;
  } catch (err) {
    clearTimeout(timeoutId);
    throw err;
  }
}

function generateClientCallId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

function localId() {
  return generateClientCallId();
}

function initials(name) {
  const safeName = (typeof name === 'string' ? name : '').trim();
  if (!safeName) return 'PC';
  return safeName.split(/\s+/).slice(0, 2).map(x => x[0]?.toUpperCase()).join('') || 'PC';
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
  const [callerToken, setCallerToken] = useState(getCallerToken());
  const [authModalOpen, setAuthModalOpen] = useState(false);
  const [tokenInput, setTokenInput] = useState(getCallerToken());

  // Pre-launch checklist: Privacy modal & contact form state
  const [privacyModalOpen, setPrivacyModalOpen] = useState(false);
  const [contactModalOpen, setContactModalOpen] = useState(false);
  const [contactForm, setContactForm] = useState({ name: '', email: '', message: '', honeypot: '' });
  const [contactStatus, setContactStatus] = useState({ state: 'idle', message: '' }); // 'idle' | 'submitting' | 'success' | 'error'

  // Status & communication
  const [busy, setBusy] = useState(false);
  const [savingStage, setSavingStage] = useState(false);
  const [syncError, setSyncError] = useState('');
  const [hasUnsyncedStage, setHasUnsyncedStage] = useState(false);
  const [error, setError] = useState('');
  const [apiState, setApiState] = useState('checking'); // 'connected' | 'local' | 'offline' | 'checking'
  const [aiBusy, setAiBusy] = useState(false);
  const [aiNotice, setAiNotice] = useState('');
  const [closeError, setCloseError] = useState('');
  const [closeOfflineConfirm, setCloseOfflineConfirm] = useState(false);
  const [syncingCallId, setSyncingCallId] = useState(null);
  const [syncingAllOffline, setSyncingAllOffline] = useState(false);

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

  // Pre-launch checklist: Dynamic SEO page titles reflecting actual view & call context
  useEffect(() => {
    if (screen === 'call') {
      if (activeCall) {
        const prospect = activeCall.prospect_name || 'Prospect';
        const company = activeCall.company_name ? ` (${activeCall.company_name})` : '';
        document.title = `Live: ${prospect}${company} — Sidecall`;
      } else {
        document.title = 'Sidecall — Cold Call Companion';
      }
    } else if (screen === 'history') {
      document.title = 'Call History & Records — Sidecall';
    } else if (screen === 'detail') {
      if (detailCall) {
        const prospect = detailCall.prospect_name || 'Prospect';
        document.title = `Record: ${prospect} — Sidecall`;
      } else {
        document.title = 'Record Not Found — Sidecall';
      }
    }
  }, [screen, activeCall, detailCall]);

  // Pre-launch checklist: Privacy-conscious Google Analytics loader (only if operator configured ID)
  useEffect(() => {
    const gaId = import.meta.env.VITE_GA_MEASUREMENT_ID;
    if (!gaId || window.__gaLoaded) return;
    window.__gaLoaded = true;
    const script = document.createElement('script');
    script.async = true;
    script.src = `https://www.googletagmanager.com/gtag/js?id=${gaId}`;
    document.head.appendChild(script);

    window.dataLayer = window.dataLayer || [];
    function gtag() {
      window.dataLayer.push(arguments);
    }
    gtag('js', new Date());
    gtag('config', gaId, { anonymize_ip: true });
  }, []);

  // Pre-launch checklist: Working contact form submission via server-side endpoint or public provider
  async function handleContactSubmit(e) {
    e.preventDefault();
    if (contactForm.honeypot) {
      setContactStatus({ state: 'success', message: 'Thank you! Your feedback has been received.' });
      return;
    }
    const cleanEmail = contactForm.email.trim();
    const cleanMsg = contactForm.message.trim();
    if (!cleanEmail || !cleanEmail.includes('@') || !cleanEmail.includes('.')) {
      setContactStatus({ state: 'error', message: 'Please enter a valid email address.' });
      return;
    }
    if (!cleanMsg || cleanMsg.length < 5) {
      setContactStatus({ state: 'error', message: 'Please enter a message of at least 5 characters.' });
      return;
    }

    setContactStatus({ state: 'submitting', message: '' });

    // Option A: Provider-supported public form endpoint if explicitly defined (e.g. Formspree ID)
    const publicEndpoint = import.meta.env.VITE_PUBLIC_CONTACT_ENDPOINT;
    const targetUrl = publicEndpoint ? publicEndpoint : `${API}/contact`;

    try {
      const resp = await fetch(targetUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: contactForm.name.trim() || undefined,
          email: cleanEmail,
          message: cleanMsg,
          honeypot: contactForm.honeypot || undefined,
        }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        if (resp.status === 503) {
          setContactStatus({
            state: 'unconfigured',
            message: 'Contact support is not configured yet. The operator has not connected a verified support destination.'
          });
          return;
        }
        if (resp.status === 429) {
          setContactStatus({
            state: 'error',
            message: 'Too many messages sent. Please wait several minutes before submitting again.'
          });
          return;
        }
        throw new Error(data.detail || 'Contact support destination could not be reached.');
      }
      setContactStatus({ state: 'success', message: 'Thank you! Your message has been received.' });
      setContactForm({ name: '', email: '', message: '', honeypot: '' });
    } catch (err) {
      setContactStatus({
        state: 'unconfigured',
        message: 'Contact support is not configured yet. The server or endpoint is currently unreachable.'
      });
    }
  }

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
      if (err.status === 401) {
        setHistoryError('Authentication required (401): Valid caller token is missing or unauthorized. Click Caller Profile in the topbar to enter your secret access token.');
        setHistory([]);
      } else if (localCalls.length > 0) {
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

  // Evaluates unsynced status across all stages in stageResults
  function evaluateUnsyncedState(resultsMap, call) {
    if (!call) {
      setHasUnsyncedStage(false);
      setSyncError('');
      return false;
    }
    const stageItems = Object.values(resultsMap || {});
    const unsyncedList = stageItems.filter(s => s && s.synced === false);

    if (call.isLocal) {
      setHasUnsyncedStage(true);
      setSyncError('Call running in offline mode. Notes saved locally; cloud sync pending.');
      return true;
    } else if (unsyncedList.length > 0) {
      setHasUnsyncedStage(true);
      const stageNames = unsyncedList.map(s => s.stage_id).join(', ');
      setSyncError(`${unsyncedList.length} stage record(s) pending cloud sync (${stageNames}).`);
      return true;
    } else {
      setHasUnsyncedStage(false);
      setSyncError('');
      return false;
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
      synced: false,
      sync_error: null,
    };

    setSavingStage(true);
    let updated = stageResultsRef.current;
    try {
      let syncSucceeded = false;
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
          syncSucceeded = true;
        } catch (e) {
          console.warn('Backend stage sync failed, draft preserved locally:', e.message);
          stagePayload.sync_error = e.message;
        }
      }
      stagePayload.synced = syncSucceeded;

      // Update local state map
      updated = {
        ...stageResultsRef.current,
        [currentStageId]: stagePayload,
      };
      stageResultsRef.current = updated;
      setStageResults(updated);

      // Re-evaluate unsynced status across all stages
      try {
        evaluateUnsyncedState(updated, call);
      } catch (e) {
        console.warn('evaluateUnsyncedState failed:', e);
      }

      // Mirror to localStorage
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
    } finally {
      setSavingStage(false);
    }
    return updated;
  }

  // Retries syncing ALL pending records (provisions call on server if offline, then syncs every unsynced stage)
  async function retrySyncAllPending() {
    const call = activeCallRef.current;
    if (!call) return true;
    setSavingStage(true);
    setSyncError('');

    let currentCall = call;

    // 1. If call was created offline, first establish persistent call on server
    if (currentCall.isLocal) {
      try {
        const created = await request('/calls', {
          method: 'POST',
          body: JSON.stringify({
            client_call_id: currentCall.client_call_id || currentCall.id,
            prospect_name: currentCall.prospect_name?.trim() || null,
            company_name: currentCall.company_name?.trim() || null,
            started_at: currentCall.started_at || new Date().toISOString(),
          }),
        });
        currentCall = { ...created, isLocal: false };
        activeCallRef.current = currentCall;
        setActiveCall(currentCall);
        setApiState('connected');
      } catch (e) {
        setSavingStage(false);
        setSyncError(`Could not establish server call: ${e.message}. Draft preserved locally.`);
        setHasUnsyncedStage(true);
        return false;
      }
    }

    // 2. Retry every stage in stageResults where synced !== true
    const currentResults = { ...stageResultsRef.current };
    const stageEntries = Object.entries(currentResults);

    for (const [stId, sData] of stageEntries) {
      if (sData.synced !== true) {
        try {
          await request(`/calls/${currentCall.id}/stage-results`, {
            method: 'POST',
            body: JSON.stringify({
              stage_id: stId,
              result: sData.result || 'completed',
              prospect_words: sData.prospect_words || '',
              notes: sData.notes || '',
            }),
          });
          currentResults[stId] = {
            ...sData,
            synced: true,
            sync_error: null,
          };
        } catch (e) {
          currentResults[stId] = {
            ...sData,
            synced: false,
            sync_error: e.message,
          };
        }
      }
    }

    stageResultsRef.current = currentResults;
    setStageResults(currentResults);

    // Mirror updated state to localStorage
    try {
      const existingHistory = JSON.parse(localStorage.getItem('sidecall-history') || '[]');
      const updatedRecord = {
        ...currentCall,
        current_stage_id: stage?.id || currentCall.current_stage_id,
        stage_results: Object.values(currentResults),
      };
      const filtered = existingHistory.filter(c => c.id !== currentCall.id && c.id !== call.id);
      localStorage.setItem('sidecall-history', JSON.stringify([updatedRecord, ...filtered]));
    } catch (e) {
      console.warn('LocalStorage write failed:', e);
    }

    const stillUnsynced = evaluateUnsyncedState(currentResults, currentCall);
    setSavingStage(false);
    return !stillUnsynced;
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

    let freshResults;
    try {
      freshResults = await performSaveStage(currentWords, currentNotes, currentTap);
    } catch (e) {
      console.warn('performSaveStage failed:', e);
      freshResults = stageResultsRef.current;
    } finally {
      setSavingStage(false);
    }

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

    const token = getCallerToken();
    setBusy(true);

    const firstStage = stages[0] || STAGE_SEED[0];
    const clientCallId = generateClientCallId();
    const localCallRecord = {
      id: clientCallId,
      client_call_id: clientCallId,
      prospect_name: fields.prospect_name.trim() || 'Unnamed prospect',
      company_name: fields.company_name.trim() || '',
      started_at: new Date().toISOString(),
      current_stage_id: firstStage.id,
      stage_results: [],
      isLocal: true,
      sync_status: 'unsynced',
    };

    if (token) {
      try {
        const created = await request('/calls', {
          method: 'POST',
          body: JSON.stringify({
            client_call_id: clientCallId,
            prospect_name: fields.prospect_name.trim() || null,
            company_name: fields.company_name.trim() || null,
          }),
        });
        setActiveCall({ ...created, isLocal: false });
        setApiState('connected');
        setHasUnsyncedStage(false);
        setSyncError('');
      } catch (err) {
        if (err.status === 401) {
          console.warn('Caller token unauthorized (401), running in local offline mode:', err.message);
          setActiveCall(localCallRecord);
          setApiState('offline');
          setHasUnsyncedStage(true);
          setError('Caller token unauthorized (401). Call running locally in offline mode — notes preserved in browser.');
        } else {
          setActiveCall(localCallRecord);
          setApiState('offline');
          setHasUnsyncedStage(true);
          setSyncError('Backend unavailable. Call running in offline mode. Notes will be preserved in browser memory.');
          setError('Backend unavailable. Call is running locally in this browser and will be stored securely in local memory.');
        }
      }
    } else {
      // Offline / guest mode when no caller token configured
      setActiveCall(localCallRecord);
      setApiState('local');
      setHasUnsyncedStage(true);
      setSyncError('Running in local offline mode. To sync call history to the cloud, configure your Caller Token in Caller Profile.');
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
    setCloseError('');

    // 1. Ensure current stage is saved locally
    await performSaveStage(words, notes, selectedTap);

    // 2. Ensure all pending stage records are synced to the cloud
    const allSynced = await retrySyncAllPending();
    const currentCall = activeCallRef.current;

    // 3. Block silent closing if cloud writes failed or call is still offline
    if (!allSynced || currentCall.isLocal) {
      setBusy(false);
      setCloseError('Cloud write failed: One or more stage records could not be synchronized to Supabase. To protect data integrity, this call has not been marked closed on the server.');
      setCloseOfflineConfirm(true);
      return;
    }

    // 4. Close the server record (with ambiguous network recovery)
    const endedAt = new Date().toISOString();
    let closeConfirmed = false;
    try {
      await request(`/calls/${currentCall.id}/close`, {
        method: 'POST',
        body: JSON.stringify({
          outcome,
          outcome_notes: outcomeNotes,
          ended_at: endedAt,
        }),
      });
      closeConfirmed = true;
    } catch (e) {
      // Ambiguous network check: verify if the server actually closed the call
      try {
        const verified = await request(`/calls/${currentCall.id}`);
        if (verified && verified.ended_at && verified.outcome === outcome) {
          closeConfirmed = true;
        }
      } catch {}

      if (!closeConfirmed) {
        setBusy(false);
        setCloseError(`Cloud close failed (${e.message}). The call stages are preserved in Supabase, but the closing status could not be finalized on the server.`);
        setCloseOfflineConfirm(true);
        return;
      }
    }

    // 5. Cloud close succeeded! Persist to local history
    const finalRecord = {
      ...currentCall,
      ended_at: endedAt,
      outcome,
      outcome_notes: outcomeNotes,
      stage_results: Object.values(stageResultsRef.current),
      current_stage_id: stage.id,
      isLocal: false,
      sync_status: 'synced',
    };

    try {
      const local = JSON.parse(localStorage.getItem('sidecall-history') || '[]');
      const filtered = local.filter(c => c.id !== currentCall.id);
      localStorage.setItem('sidecall-history', JSON.stringify([finalRecord, ...filtered]));
    } catch (e) {
      console.warn('LocalStorage write failed:', e);
    }

    setFinishOpen(false);
    setCloseOfflineConfirm(false);
    setCloseError('');
    setActiveCall(null);
    setScreen('history');
    await loadHistory();
    setBusy(false);
  }

  function closeCallLocally() {
    const call = activeCallRef.current;
    if (!call) return;

    const endedAt = new Date().toISOString();
    const finalRecord = {
      ...call,
      ended_at: endedAt,
      outcome,
      outcome_notes: outcomeNotes,
      stage_results: Object.values(stageResultsRef.current).map(s => ({
        ...s,
        synced: s.synced || false,
      })),
      current_stage_id: stage.id,
      isLocal: true,
      sync_status: 'unsynced',
    };

    try {
      const local = JSON.parse(localStorage.getItem('sidecall-history') || '[]');
      const filtered = local.filter(c => c.id !== call.id);
      localStorage.setItem('sidecall-history', JSON.stringify([finalRecord, ...filtered]));
    } catch (e) {
      console.warn('LocalStorage write failed:', e);
    }

    setFinishOpen(false);
    setCloseOfflineConfirm(false);
    setCloseError('');
    setActiveCall(null);
    setScreen('history');
    loadHistory();
  }

  // Uploads an entire offline-recorded call to Supabase cloud
  async function syncOfflineCallRecord(offlineRecord) {
    setSyncingCallId(offlineRecord.id);
    setError('');
    try {
      const payload = {
        client_call_id: offlineRecord.client_call_id || offlineRecord.id,
        prospect_name: offlineRecord.prospect_name || null,
        company_name: offlineRecord.company_name || null,
        started_at: offlineRecord.started_at,
        ended_at: offlineRecord.ended_at,
        outcome: offlineRecord.outcome || null,
        outcome_notes: offlineRecord.outcome_notes || '',
        current_stage_id: offlineRecord.current_stage_id || 'opening',
        stage_results: (offlineRecord.stage_results || []).map(sr => ({
          stage_id: sr.stage_id,
          result: sr.result || 'completed',
          prospect_words: sr.prospect_words || '',
          notes: sr.notes || '',
        })),
      };

      const synced = await request('/calls/sync-offline', {
        method: 'POST',
        body: JSON.stringify(payload),
      });

      // Update local storage record
      const local = JSON.parse(localStorage.getItem('sidecall-history') || '[]');
      const updatedLocal = local.map(item => {
        if (item.id === offlineRecord.id) {
          return { ...synced, isLocal: false, sync_status: 'synced' };
        }
        return item;
      });
      localStorage.setItem('sidecall-history', JSON.stringify(updatedLocal));

      if (detailCall && detailCall.id === offlineRecord.id) {
        setDetailCall({ ...synced, isLocal: false, sync_status: 'synced' });
      }

      await loadHistory();
    } catch (e) {
      alert(`Sync failed: ${e.message}`);
    } finally {
      setSyncingCallId(null);
    }
  }

  // Batch syncs all offline calls currently stored locally
  async function syncAllOfflineCalls() {
    const offlineCalls = history.filter(c => c.isLocal || c.sync_status === 'unsynced');
    if (offlineCalls.length === 0) return;
    setSyncingAllOffline(true);
    for (const c of offlineCalls) {
      try {
        const payload = {
          client_call_id: c.client_call_id || c.id,
          prospect_name: c.prospect_name || null,
          company_name: c.company_name || null,
          started_at: c.started_at,
          ended_at: c.ended_at,
          outcome: c.outcome || null,
          outcome_notes: c.outcome_notes || '',
          current_stage_id: c.current_stage_id || 'opening',
          stage_results: (c.stage_results || []).map(sr => ({
            stage_id: sr.stage_id,
            result: sr.result || 'completed',
            prospect_words: sr.prospect_words || '',
            notes: sr.notes || '',
          })),
        };
        const synced = await request('/calls/sync-offline', {
          method: 'POST',
          body: JSON.stringify(payload),
        });
        const local = JSON.parse(localStorage.getItem('sidecall-history') || '[]');
        const updatedLocal = local.map(item => item.id === c.id ? { ...synced, isLocal: false, sync_status: 'synced' } : item);
        localStorage.setItem('sidecall-history', JSON.stringify(updatedLocal));
      } catch (err) {
        console.warn('Failed to sync offline record:', c.id, err);
      }
    }
    setSyncingAllOffline(false);
    await loadHistory();
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
          <button
            type="button"
            className="rail-btn-subtle"
            title="Privacy Policy"
            aria-label="Privacy Policy"
            onClick={() => setPrivacyModalOpen(true)}
          >
            <HelpCircle size={18} />
          </button>
          <button
            type="button"
            className="rail-btn-subtle"
            title="Contact & Support"
            aria-label="Contact & Support"
            onClick={() => {
              setContactStatus({ state: 'idle', message: '' });
              setContactModalOpen(true);
            }}
          >
            <Mail size={18} />
          </button>
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
          <nav className="crumb" aria-label="Breadcrumb navigation">
            <button
              type="button"
              className="crumb-btn"
              onClick={() => setScreen('call')}
            >
              COLDCALL COMPANION
            </button>
            {screen === 'detail' && (
              <>
                <span className="slash">/</span>
                <button
                  type="button"
                  className="crumb-btn"
                  onClick={() => {
                    setScreen('history');
                    loadHistory();
                  }}
                >
                  History
                </button>
              </>
            )}
            <span className="slash">/</span>
            <strong aria-current="page">
              {screen === 'call'
                ? activeCall
                  ? 'Live Call in Progress'
                  : 'Start Call'
                : screen === 'detail'
                ? (detailCall ? `${detailCall.prospect_name || 'Prospect'} (${detailCall.company_name || 'Organization'})` : 'Record Not Found')
                : 'Call History'}
            </strong>
          </nav>
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
            <button
              type="button"
              className={`avatar ${callerToken ? 'authed' : 'unauthed'}`}
              title={callerToken ? `Caller Token Configured (${callerToken.slice(0, 3)}•••). Click to change.` : 'No caller token configured! Click to authenticate.'}
              onClick={() => {
                setTokenInput(getCallerToken());
                setAuthModalOpen(true);
              }}
              aria-label="Caller Profile and Authentication"
            >
              {callerToken ? 'FDE' : '!'}
            </button>
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
              <div className="lc-workspace">
                <h1 className="visually-hidden">Live Call Workspace — {activeCall.prospect_name || 'Active Call'}</h1>
                {/* ── LIVE CALL HEADER BAR ── */}
                <div className="lc-header">
                  <div className="lc-header-left">
                    <div className="lc-live-badge">
                      <span className="lc-live-dot" />
                      LIVE
                    </div>
                    <div className="lc-prospect-block">
                      <span className="lc-prospect-name">
                        {activeCall.prospect_name || 'Unnamed prospect'}
                      </span>
                      {activeCall.company_name && (
                        <span className="lc-company-name">{activeCall.company_name}</span>
                      )}
                    </div>
                  </div>
                  <div className="lc-header-center">
                    <span className="lc-timer">{formatTimer(elapsedSeconds)}</span>
                    <span className="lc-timer-label">ELAPSED</span>
                  </div>
                  <div className="lc-header-right">
                    {activeCall.isLocal ? (
                      <span className="lc-conn-badge lc-conn-local">
                        <span className="lc-conn-dot lc-conn-dot--local" /> LOCAL ONLY
                      </span>
                    ) : (hasUnsyncedStage || syncError) ? (
                      <span className="lc-conn-badge lc-conn-pending" title="Draft saved locally; cloud sync pending">
                        <span className="lc-conn-dot lc-conn-dot--pending" /> PENDING SYNC
                      </span>
                    ) : apiState === 'connected' ? (
                      <span className="lc-conn-badge lc-conn-synced">
                        <span className="lc-conn-dot lc-conn-dot--synced" /> SYNCED
                      </span>
                    ) : (
                      <span className="lc-conn-badge lc-conn-offline">
                        <span className="lc-conn-dot lc-conn-dot--offline" /> OFFLINE
                      </span>
                    )}
                    <button
                      type="button"
                      className="lc-end-header-btn"
                      onClick={() => setFinishOpen(true)}
                      aria-label="End call"
                    >
                      <PhoneOff size={13} />
                      END CALL
                    </button>
                  </div>
                </div>

                {/* ── STAGE PROGRESS RAIL ── */}
                <div className="lc-stage-rail" role="tablist">
                  {stages.map((s, i) => {
                    const isCurrent = i === activeIndex;
                    const isSaved = Boolean(stageResults[s.id]?.result);
                    return (
                      <button
                        key={s.id}
                        type="button"
                        role="tab"
                        aria-selected={isCurrent}
                        disabled={savingStage && !isCurrent}
                        className={`lc-stage-pip ${isCurrent ? 'current' : isSaved ? 'done' : 'pending'}`}
                        onClick={() => goToStage(i)}
                        title={`${i + 1}. ${s.title}`}
                      >
                        <span className="lc-pip-num">{i + 1}</span>
                        <span className="lc-pip-label">{s.title}</span>
                      </button>
                    );
                  })}
                </div>

                {/* ── MAIN TWO-COLUMN AREA ── */}
                <div className="lc-body">

                  {/* ── LEFT COLUMN: Stage guidance + quick taps ── */}
                  <div className="lc-left">
                    <div className="lc-stage-intro">
                      <div className="lc-stage-kicker">STAGE {activeIndex + 1} OF 8</div>
                      <h2 className="lc-stage-title">{stage.title}</h2>
                      <p className="lc-stage-purpose">{stage.purpose}</p>
                      {stage.guidance && (
                        <p className="lc-stage-guidance">{stage.guidance}</p>
                      )}
                    </div>

                    <div className="lc-section-label lc-section-label--flex">
                      <span>THEY MAY SAY</span>
                      <span className="lc-cues-tag">OBSERVED CUES (READ-ONLY)</span>
                    </div>
                    <div className="lc-cues-list">
                      {(stage.prospect_patterns || []).map((pat, idx) => (
                        <div className="lc-cue-row lc-cue-row--readonly" key={idx}>
                          <span className="lc-cue-text">{pat}</span>
                        </div>
                      ))}
                    </div>

                    <div className="lc-section-label lc-section-label--mt">WHAT HAPPENED</div>
                    <div className="lc-taps-grid">
                      {(stage.stage_taps || []).map((tapText, idx) => {
                        const isPressed = selectedTap === tapText;
                        return (
                          <button
                            key={idx}
                            type="button"
                            className={`lc-tap-btn ${isPressed ? 'pressed' : ''}`}
                            onClick={() => setSelectedTap(tapText)}
                          >
                            {tapText}
                          </button>
                        );
                      })}
                    </div>

                    {savingStage && (
                      <div className="lc-saving-bar">
                        <RefreshCw size={11} className="spin-icon" /> Saving stage…
                      </div>
                    )}

                    {syncError && (
                      <div className="lc-unsynced-banner" role="alert">
                        <div className="lc-unsynced-content">
                          <span className="lc-unsynced-dot" />
                          <span>{syncError}</span>
                        </div>
                        <button
                          type="button"
                          className="lc-retry-sync-btn"
                          onClick={retrySyncAllPending}
                          disabled={savingStage}
                          title="Retry syncing all pending stage records to cloud"
                        >
                          <RefreshCw size={11} className={savingStage ? 'spin-icon' : ''} />
                          {savingStage ? 'Syncing…' : 'Retry All Pending'}
                        </button>
                      </div>
                    )}

                    {/* Bottom nav controls */}
                    <div className="lc-nav-actions">
                      {activeIndex > 0 && (
                        <button
                          type="button"
                          className="lc-prev-btn"
                          onClick={() => goToStage(activeIndex - 1)}
                          disabled={savingStage}
                          title={`Back to ${stages[activeIndex - 1]?.title}`}
                        >
                          <ArrowLeft size={14} /> {stages[activeIndex - 1]?.title?.toUpperCase()}
                        </button>
                      )}
                      {activeIndex < 7 ? (
                        <button
                          type="button"
                          className="lc-next-btn"
                          onClick={() => goToStage(activeIndex + 1)}
                          disabled={savingStage}
                        >
                          NEXT: {stages[activeIndex + 1]?.title?.toUpperCase()} <ArrowRight size={14} />
                        </button>
                      ) : (
                        <button
                          type="button"
                          className="lc-next-btn"
                          onClick={() => setFinishOpen(true)}
                        >
                          WRAP UP &amp; OUTCOME <ArrowRight size={14} />
                        </button>
                      )}
                    </div>
                  </div>

                  {/* ── RIGHT COLUMN: Verbatim words + caller notes ── */}
                  <div className="lc-right">
                    <div className="lc-right-section lc-words-section">
                      <div className="lc-right-label lc-words-label">
                        <span>
                          {stage.id === 'their_need' ? (
                            <>STAGE 5 · EXACT WORDS <span className="lc-critical-flag">★ VERBATIM</span></>
                          ) : (
                            'HER / PROSPECT\'S WORDS'
                          )}
                        </span>
                        {stage.id !== 'their_need' && (
                          <span className="lc-right-sublabel">AS CLOSE TO VERBATIM AS POSSIBLE</span>
                        )}
                      </div>
                      <textarea
                        id="prospect-words-input"
                        className={`lc-textarea lc-words-textarea ${stage.id === 'their_need' ? 'verbatim-highlight' : ''}`}
                        value={words}
                        onChange={e => setWords(e.target.value)}
                        placeholder={stage.id === 'their_need'
                          ? 'Write their exact words here — do not paraphrase…'
                          : '"accounting for what, we already have a CA who files everything…"'}
                        maxLength={10000}
                      />
                    </div>

                    <div className="lc-right-section">
                      <div className="lc-right-label">
                        <span>YOUR NOTES</span>
                        <span className="lc-right-sublabel">PRIVATE · OPTIONAL</span>
                      </div>
                      <textarea
                        id="extra-notes-input"
                        className="lc-textarea lc-notes-textarea"
                        value={notes}
                        onChange={e => setNotes(e.target.value)}
                        placeholder="Context, follow-up specifics, timing details to remember…"
                        maxLength={4000}
                      />
                    </div>

                    <div className="lc-progress-line">
                      <Clock3 size={12} />
                      <span>{completedCount} of 8 stages logged</span>
                      {completedCount > 0 && (
                        <div className="lc-progress-track">
                          <div className="lc-progress-fill" style={{width: `${(completedCount/8)*100}%`}} />
                        </div>
                      )}
                    </div>
                  </div>
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
                    {(detailCall.isLocal || detailCall.sync_status === 'unsynced') && (
                      <button
                        type="button"
                        className="sync-row-btn"
                        style={{ marginLeft: 10 }}
                        disabled={syncingCallId === detailCall.id}
                        onClick={() => syncOfflineCallRecord(detailCall)}
                      >
                        <RefreshCw size={11} className={syncingCallId === detailCall.id ? 'spin-icon' : ''} />
                        {syncingCallId === detailCall.id ? 'Syncing…' : 'Sync to Cloud'}
                      </button>
                    )}
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
            {!detailCall && (
              <div className="error-404-container">
                <div className="error-404-icon">
                  <AlertTriangle size={28} />
                </div>
                <h2>Call Record Not Found</h2>
                <p>
                  The call record you are trying to view does not exist or has been removed from your local history.
                </p>
                <button
                  type="button"
                  className="primary-button"
                  onClick={() => {
                    setScreen('history');
                    loadHistory();
                  }}
                >
                  Return to Call History
                </button>
              </div>
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

            {history.some(c => c.isLocal || c.sync_status === 'unsynced') && (
              <div className="history-offline-banner">
                <div className="history-offline-info">
                  <CloudOff size={16} />
                  <span>
                    <strong>
                      {history.filter(c => c.isLocal || c.sync_status === 'unsynced').length} offline call record(s) stored locally.
                    </strong>{' '}
                    Cloud persistence pending.
                  </span>
                </div>
                <button
                  type="button"
                  className="sync-all-btn"
                  onClick={syncAllOfflineCalls}
                  disabled={syncingAllOffline}
                >
                  <RefreshCw size={12} className={syncingAllOffline ? 'spin-icon' : ''} />
                  {syncingAllOffline ? 'Syncing…' : 'Sync All to Cloud'}
                </button>
              </div>
            )}

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
                        {c.isLocal || c.sync_status === 'unsynced' ? (
                          <div className="storage-action-wrap" onClick={e => e.stopPropagation()}>
                            <span className="unsynced-badge">Offline Draft</span>
                            <button
                              type="button"
                              className="sync-row-btn"
                              title="Upload this offline call to Supabase cloud"
                              disabled={syncingCallId === c.id}
                              onClick={(e) => {
                                e.stopPropagation();
                                syncOfflineCallRecord(c);
                              }}
                            >
                              <RefreshCw size={10} className={syncingCallId === c.id ? 'spin-icon' : ''} />
                              {syncingCallId === c.id ? '…' : 'Sync'}
                            </button>
                          </div>
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

            {closeError && (
              <div className="finish-error-banner" role="alert">
                <div className="finish-error-icon">
                  <AlertTriangle size={16} />
                </div>
                <div className="finish-error-text">
                  <strong>Persistence Warning:</strong> {closeError}
                </div>
              </div>
            )}

            <div className="modal-footer">
              <button
                className="quiet-button"
                type="button"
                onClick={() => {
                  setFinishOpen(false);
                  setCloseError('');
                  setCloseOfflineConfirm(false);
                }}
              >
                Return to call
              </button>

              {closeOfflineConfirm ? (
                <div className="finish-dual-actions">
                  <button
                    className="secondary-button"
                    type="button"
                    onClick={closeCallLocally}
                  >
                    Save as Offline Draft
                  </button>
                  <button
                    className="primary-button"
                    type="button"
                    onClick={closeCall}
                    disabled={busy || savingStage}
                  >
                    <RefreshCw size={14} className={busy ? 'spin-icon' : ''} />
                    {busy ? 'Retrying…' : 'Retry Cloud Close'}
                  </button>
                </div>
              ) : (
                <button
                  className="primary-button"
                  type="button"
                  onClick={closeCall}
                  disabled={busy}
                >
                  <span>{busy ? 'Saving…' : 'Save and close call'}</span>
                  <Check size={16} />
                </button>
              )}
            </div>
          </section>
        </div>
      )}

      {/* CALLER AUTHENTICATION & ACCESS TOKEN MODAL */}
      {authModalOpen && (
        <div
          className="modal-backdrop"
          onMouseDown={e => {
            if (e.target === e.currentTarget) setAuthModalOpen(false);
          }}
        >
          <section className="finish-modal auth-modal" role="dialog" aria-modal="true">
            <div className="modal-icon">
              <Shield size={19} />
            </div>
            <button
              className="modal-close"
              type="button"
              onClick={() => setAuthModalOpen(false)}
              aria-label="Close modal"
            >
              <X size={17} />
            </button>

            <div className="eyebrow">CALLER AUTHENTICATION</div>
            <h2>Caller Access Token</h2>
            <p>
              Enter the secret Bearer token configured in your server environment (<code>CALLER_AUTH_TOKENS</code>). Call records and history are strictly isolated to your verified identity.
            </p>

            <label className="textarea-label" htmlFor="modal-auth-token-input">
              BEARER TOKEN <span>REQUIRED</span>
            </label>
            <input
              id="modal-auth-token-input"
              type="password"
              className="extra-input token-input"
              value={tokenInput}
              onChange={e => setTokenInput(e.target.value)}
              placeholder="e.g. paste-your-secret-caller-token"
              autoComplete="off"
            />

            <div className="modal-footer">
              <button
                className="quiet-button"
                type="button"
                onClick={() => {
                  localStorage.removeItem(CALLER_TOKEN_KEY);
                  setCallerToken('');
                  setTokenInput('');
                  setAuthModalOpen(false);
                  loadHistory();
                }}
              >
                Clear Token
              </button>
              <button
                className="primary-button"
                type="button"
                onClick={() => {
                  const clean = tokenInput.trim();
                  if (clean) {
                    localStorage.setItem(CALLER_TOKEN_KEY, clean);
                    setCallerToken(clean);
                    setError('');
                    setHistoryError('');
                    setAuthModalOpen(false);
                    loadHistory();
                  }
                }}
                disabled={!tokenInput.trim()}
              >
                <span>Save Token</span>
                <Check size={16} />
              </button>
            </div>
          </section>
        </div>
      )}

      {/* ── PRIVACY POLICY MODAL ── */}
      {privacyModalOpen && (
        <div className="modal-backdrop" onClick={() => setPrivacyModalOpen(false)}>
          <section
            className="modal-card policy-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="privacy-modal-title"
            onClick={e => e.stopPropagation()}
          >
            <div className="modal-header">
              <div className="eyebrow">
                <span className="eyebrow-dot" /> DRAFT · TRANSPARENCY & DATA GOVERNANCE
              </div>
              <h2 id="privacy-modal-title">[DRAFT] Privacy Policy & Data Architecture</h2>
              <p>Draft pre-launch policy pending legal review and verified company details.</p>
            </div>

            <div className="policy-body">
              <h3>1. Local-First Storage Architecture</h3>
              <p>
                ColdCall Companion operates as a client-first productivity tool. When you start an outbound call and log prospect details, conversation stages, or verbatim notes, all data is immediately written to your browser’s local storage (<code>localStorage</code>).
              </p>

              <h3>2. Cloud Synchronization & Token Isolation</h3>
              <p>
                When cloud connectivity is configured, your completed calls are synchronized to a private PostgreSQL database (Supabase) via secure HTTPS RPC transactions. Access is strictly isolated by your secret Caller Bearer Token (<code>X-Caller-Token</code>). There is no public or unauthenticated read access to your call history.
              </p>

              <h3>3. No Audio or Voice Recording</h3>
              <p>
                ColdCall Companion is a manual visual guide and notes companion. The application does not intercept phone calls, does not record audio, and does not access your microphone. All logged quotes and stages are typed or selected manually by the caller.
              </p>

              <h3>4. Optional AI Advisory Analysis</h3>
              <p>
                If the operator requests an AI post-call review, the typed notes and stage progression are sent to an LLM provider (Anthropic Claude API) solely to generate the structured coaching summary. These summaries are advisory only.
              </p>

              <h3>5. Analytics & Cookies</h3>
              <p>
                ColdCall Companion does not track you across other websites or sell caller data. Optional Google Analytics is completely disabled by default and only activates if a measurement ID is explicitly configured by the site operator, with IP anonymization enabled.
              </p>

              <h3>6. Data Retention, Clearing, and Erasure</h3>
              <p>
                <strong>Local Caller Token:</strong> Clicking “Clear Token” in the Caller Token settings removes your credentials from this browser session to prevent unauthorized access to cloud records. <em>Clearing your token does not delete existing local or cloud call records.</em>
              </p>
              <p>
                <strong>Local Call Storage:</strong> Offline call history and stage progress are retained in your browser’s <code>localStorage</code>. To delete all local records from this device, clear your browser’s site storage/cookies for this domain.
              </p>
              <p>
                <strong>Server-Side Cloud Records:</strong> For permanent erasure of synced call records from the remote PostgreSQL database, contact your organization’s system administrator with your Caller ID.
              </p>

              <h3>7. Contact & Support Submissions</h3>
              <p>
                When you submit an inquiry through the Contact & Support modal:
              </p>
              <ul>
                <li><strong>Information Collected:</strong> Your name (optional), email address (required), and message text along with a submission timestamp.</li>
                <li><strong>Destination & Dispatch:</strong> Inquiries are transmitted via secure HTTPS to the operator’s designated server-side support webhook (such as a private Slack channel or support desk). Secrets and endpoints are kept strictly server-side.</li>
                <li><strong>Purpose & Retention:</strong> Submissions are used solely to answer inquiries, debug technical issues, and review feedback. Contact details are retained according to the operator’s internal support schedule and are never sold or shared with third-party advertisers.</li>
              </ul>

              <div className="policy-meta-box">
                <strong>DRAFT — OPERATOR INPUT REQUIRED BEFORE PUBLIC LAUNCH:</strong><br />
                • Organization Legal Name: <em>[Needs User/Operator Input]</em><br />
                • Contact/Privacy Email: <em>[Needs User/Operator Input]</em><br />
                • Registered Business Address: <em>[Needs User/Operator Input]</em><br />
                • Effective Date: Draft — Pending Launch Approval
              </div>
            </div>

            <div className="modal-footer">
              <button
                className="primary-button"
                type="button"
                onClick={() => setPrivacyModalOpen(false)}
              >
                <span>Close</span>
              </button>
            </div>
          </section>
        </div>
      )}

      {/* ── CONTACT & FEEDBACK MODAL ── */}
      {contactModalOpen && (
        <div className="modal-backdrop" onClick={() => setContactModalOpen(false)}>
          <section
            className="modal-card contact-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="contact-modal-title"
            onClick={e => e.stopPropagation()}
          >
            <div className="modal-header">
              <div className="eyebrow">
                <span className="eyebrow-dot" /> SUPPORT & FEEDBACK
              </div>
              <h2 id="contact-modal-title">Contact ColdCall Companion</h2>
              <p>Send a question, feature request, or report an issue with the companion.</p>
            </div>

            {contactStatus.state === 'success' && (
              <div className="contact-success-banner" role="status">
                <Check size={16} />
                <span>{contactStatus.message}</span>
              </div>
            )}

            {contactStatus.state === 'unconfigured' && (
              <div className="contact-unconfigured-banner" style={{ background: '#fdf8ea', border: '1px solid #ebd99f', padding: '10px 14px', borderRadius: 4, color: '#7c5e10', fontSize: 13, marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }} role="alert">
                <AlertTriangle size={16} />
                <span>{contactStatus.message}</span>
              </div>
            )}

            {contactStatus.state === 'error' && (
              <div className="contact-error-banner" style={{ color: '#b33924', marginBottom: 12, fontSize: 13 }} role="alert">
                <AlertTriangle size={15} style={{ verticalAlign: 'middle', marginRight: 6 }} />
                <span>{contactStatus.message}</span>
              </div>
            )}

            <form onSubmit={handleContactSubmit}>
              {/* Spam Protection Honeypot field (hidden from real users) */}
              <input
                type="text"
                name="b_website"
                className="visually-hidden"
                tabIndex={-1}
                autoComplete="off"
                value={contactForm.honeypot}
                onChange={e => setContactForm({ ...contactForm, honeypot: e.target.value })}
              />

              <label className="textarea-label" htmlFor="contact-name-input">
                YOUR NAME <span>OPTIONAL</span>
              </label>
              <input
                id="contact-name-input"
                type="text"
                className="contact-input"
                placeholder="e.g. Alex Morgan"
                value={contactForm.name}
                onChange={e => setContactForm({ ...contactForm, name: e.target.value })}
              />

              <label className="textarea-label" htmlFor="contact-email-input">
                YOUR EMAIL <span>REQUIRED</span>
              </label>
              <input
                id="contact-email-input"
                type="email"
                required
                className="contact-input"
                placeholder="e.g. alex@company.com"
                value={contactForm.email}
                onChange={e => setContactForm({ ...contactForm, email: e.target.value })}
              />

              <label className="textarea-label" htmlFor="contact-message-input">
                MESSAGE <span>REQUIRED</span>
              </label>
              <textarea
                id="contact-message-input"
                required
                className="contact-textarea"
                placeholder="Tell us how we can help or what you would like improved…"
                value={contactForm.message}
                onChange={e => setContactForm({ ...contactForm, message: e.target.value })}
              />

              <div className="modal-footer">
                <button
                  className="quiet-button"
                  type="button"
                  onClick={() => setContactModalOpen(false)}
                >
                  Cancel
                </button>
                <button
                  className="primary-button"
                  type="submit"
                  disabled={contactStatus.state === 'submitting'}
                >
                  {contactStatus.state === 'submitting' ? (
                    <>
                      <RefreshCw size={15} className="spin" />
                      <span>Sending…</span>
                    </>
                  ) : (
                    <>
                      <Mail size={15} />
                      <span>Send Message</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
    </div>
  );
}

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }
  static getDerivedStateFromError() {
    return { hasError: true };
  }
  componentDidCatch(error, info) {
    console.error('Sidecall view error caught by boundary:', error, info);
  }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: '60px 20px', textAlign: 'center', fontFamily: 'Inter, system-ui, sans-serif', maxWidth: '520px', margin: '80px auto' }}>
          <h2 style={{ fontSize: '20px', color: '#111827', marginBottom: '8px' }}>Something went wrong</h2>
          <p style={{ color: '#6b7280', fontSize: '14px', marginBottom: '20px' }}>Your saved notes and call records are intact. Please reload to continue.</p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            style={{ padding: '10px 18px', background: '#0f172a', color: '#fff', borderRadius: '6px', border: 'none', cursor: 'pointer', fontWeight: 500 }}
          >
            Reload Companion
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

createRoot(document.getElementById('root')).render(
  <ErrorBoundary>
    <App />
  </ErrorBoundary>
);
