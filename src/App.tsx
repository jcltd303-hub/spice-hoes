import React, { useState, useEffect } from 'react';
import { 
  Flame, 
  CheckCircle2, 
  XCircle, 
  RotateCcw, 
  Sparkles, 
  Video, 
  Calendar, 
  DollarSign, 
  Users, 
  BarChart3, 
  ShieldCheck, 
  TrendingUp, 
  Send, 
  Play, 
  AlertCircle,
  Clock,
  ExternalLink,
  RefreshCw,
  Search,
  BookOpen
} from 'lucide-react';
import { Persona, Candidate, PersonaStats, PolicyRecommendation, SystemEvent } from './types';

export default function App() {
  const [activeTab, setActiveTab] = useState<'review' | 'media' | 'scheduler' | 'personas' | 'engine' | 'ledger' | 'events'>('review');
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [stats, setStats] = useState<PersonaStats[]>([]);
  const [recommendation, setRecommendation] = useState<PolicyRecommendation | null>(null);
  const [thompsonRecommendation, setThompsonRecommendation] = useState<PolicyRecommendation | null>(null);
  const [capabilities, setCapabilities] = useState<any | null>(null);
  const [events, setEvents] = useState<SystemEvent[]>([]);
  const [mediaJobs, setMediaJobs] = useState<any[]>([]);
  const [schedules, setSchedules] = useState<any[]>([]);
  const [runtimePolicy, setRuntimePolicy] = useState<any | null>(null);
  const [rlStatus, setRlStatus] = useState<any | null>(null);
  const [autopilotStatus, setAutopilotStatus] = useState<any | null>(null);
  const [doctorStatus, setDoctorStatus] = useState<any | null>(null);
  const [autopilotForm, setAutopilotForm] = useState({
    objective: 'Choose the next measurable content experiment that maximizes attributable net revenue',
    channel: 'Instagram',
    offer: 'affiliate',
    variants: 3,
    cost_cents_per_asset: 0,
    seed: '',
  });
  const [autopilotResult, setAutopilotResult] = useState<any | null>(null);
  const [controlBusy, setControlBusy] = useState(false);
  const [controlError, setControlError] = useState('');
  const [loading, setLoading] = useState(true);

  // Review form state
  const [reviewerName, setReviewerName] = useState('lead_operator');
  const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({});

  // Media Job creator form
  const [selectedPersona, setSelectedPersona] = useState('zara_voss');
  const [videoScript, setVideoScript] = useState('The night market comes alive when the bass drops. Never slow down. Tap link for backstage guest list.');

  const fetchData = async () => {
    try {
      const [pRes, cRes, sRes, rRes, thompsonRes, eRes, mRes, schRes, policyRes, rlRes, autopilotRes, doctorRes, capabilitiesRes] = await Promise.all([
        fetch('/api/personas').then(r => r.json()),
        fetch('/api/candidates').then(r => r.json()),
        fetch('/api/stats').then(r => r.json()),
        fetch('/api/recommend').then(r => r.json()),
        fetch('/api/recommend/thompson').then(r => r.json()),
        fetch('/api/events?limit=50').then(r => r.json()),
        fetch('/api/media-jobs').then(r => r.json()),
        fetch('/api/schedules').then(r => r.json()),
        fetch('/api/runtime-policy').then(r => r.json()),
        fetch('/api/rl/status').then(r => r.json()),
        fetch('/api/autopilot/status').then(r => r.json()),
        fetch('/api/doctor').then(r => r.json()),
        fetch('/api/capabilities').then(r => r.json()),
      ]);
      setPersonas(pRes || []);
      setCandidates(cRes || []);
      setStats(sRes || []);
      setRecommendation(rRes || null);
      setThompsonRecommendation(thompsonRes?.error ? null : thompsonRes);
      setEvents(eRes || []);
      setMediaJobs(mRes || []);
      setSchedules(schRes || []);
      setRuntimePolicy(policyRes?.error ? null : policyRes);
      setRlStatus(rlRes?.error ? null : rlRes);
      setAutopilotStatus(autopilotRes?.error ? null : autopilotRes);
      setDoctorStatus(doctorRes?.error ? null : doctorRes);
      setCapabilities(capabilitiesRes?.error ? null : capabilitiesRes);
    } catch (err) {
      console.error('Error fetching data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleReviewCandidate = async (cid: string, decision: 'approved' | 'rejected' | 'revise') => {
    const note = reviewNotes[cid] || '';
    try {
      const res = await fetch(`/api/candidates/${cid}/review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision, reviewer: reviewerName, note })
      });
      if (res.ok) {
        await fetchData();
      }
    } catch (err) {
      console.error('Review failed:', err);
    }
  };

  const handleCreateMediaJob = async () => {
    const cand = candidates.find(c => c.persona_id === selectedPersona) || candidates[0];
    if (!cand) return;

    try {
      const res = await fetch('/api/media-jobs/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          persona_id: selectedPersona,
          candidate_id: cand.id,
          source_asset_uri: cand.asset_uri || 'https://images.unsplash.com/photo-1514525253161-7a46d19cd819?w=800',
          script: videoScript,
          aspect_ratio: '9:16'
        })
      });
      if (res.ok) {
        const newJob = await res.json();
        // Trigger render
        await fetch(`/api/media-jobs/${newJob.id}/render`, { method: 'POST' });
        await fetchData();
        setActiveTab('media');
      }
    } catch (err) {
      console.error('Failed to create media job:', err);
    }
  };

  const handleReviewMediaJob = async (id: string, decision: 'approved' | 'rejected' | 'revise') => {
    try {
      const res = await fetch(`/api/media-jobs/${id}/review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision, reviewer: reviewerName, note: 'Reviewed via web operator desk' })
      });
      if (res.ok) {
        await fetchData();
      }
    } catch (err) {
      console.error('Media review failed:', err);
    }
  };

  const handleScheduleMedia = async (jobId: string) => {
    try {
      const res = await fetch('/api/schedules/schedule', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          media_job_id: jobId,
          platform: 'instagram',
          account_id: 'official',
          scheduled_at: new Date(Date.now() + 60000).toISOString()
        })
      });
      if (res.ok) {
        await fetchData();
        setActiveTab('scheduler');
      } else {
        const data = await res.json();
        alert(data.error || 'Cannot schedule');
      }
    } catch (err) {
      console.error('Schedule failed:', err);
    }
  };

  const handleProcessOutbox = async () => {
    try {
      const res = await fetch('/api/schedules/process-outbox', { method: 'POST' });
      if (res.ok) {
        await fetchData();
      }
    } catch (err) {
      console.error('Outbox process failed:', err);
    }
  };

  const handleSimulateTraffic = async (cid: string) => {
    try {
      await fetch(`/api/candidates/${cid}/simulate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          impressions: 40,
          clicks: 6,
          purchases: 1,
          purchaseCents: 2900
        })
      });
      await fetchData();
    } catch (err) {
      console.error('Simulation failed:', err);
    }
  };

  const handlePolicyChange = async (key: string, value: number) => {
    if (!runtimePolicy) return;
    setControlBusy(true);
    setControlError('');
    try {
      const res = await fetch('/api/runtime-policy', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          changes: { [key]: value },
          actor: reviewerName || 'web_operator',
          note: 'Updated from operator control plane',
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Policy update failed');
      setRuntimePolicy(data);
      await fetchData();
    } catch (err: any) {
      setControlError(err.message || 'Policy update failed');
    } finally {
      setControlBusy(false);
    }
  };

  const handleTrainRL = async () => {
    setControlBusy(true);
    setControlError('');
    try {
      const res = await fetch('/api/rl/train', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ epochs: 20, learning_rate: 0.01 }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'RL training failed');
      await fetchData();
    } catch (err: any) {
      setControlError(err.message || 'RL training failed');
    } finally {
      setControlBusy(false);
    }
  };

  const handleAutopilotRun = async () => {
    setControlBusy(true);
    setControlError('');
    setAutopilotResult(null);
    try {
      const res = await fetch('/api/autopilot/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...autopilotForm,
          seed: autopilotForm.seed === '' ? null : Number(autopilotForm.seed),
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Autopilot run failed');
      setAutopilotResult(data);
      await fetchData();
    } catch (err: any) {
      setControlError(err.message || 'Autopilot run failed');
    } finally {
      setControlBusy(false);
    }
  };

  const totalNet = stats.reduce((acc, s) => acc + s.net_cents, 0);
  const totalRevenue = stats.reduce((acc, s) => acc + s.revenue_cents, 0);
  const totalPublished = stats.reduce((acc, s) => acc + s.published, 0);
  const pendingReviews = candidates.filter(c => c.status === 'proposed').length + mediaJobs.filter(m => m.status === 'review_ready').length;

  const getPersonaColor = (type?: string) => {
    switch (type) {
      case 'Scary': return 'text-rose-400 bg-rose-500/10 border-rose-500/30';
      case 'Sporty': return 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30';
      case 'Baby': return 'text-pink-400 bg-pink-500/10 border-pink-500/30';
      case 'Ginger': return 'text-amber-400 bg-amber-500/10 border-amber-500/30';
      case 'Posh': return 'text-purple-400 bg-purple-500/10 border-purple-500/30';
      default: return 'text-gray-400 bg-gray-500/10 border-gray-500/30';
    }
  };

  return (
    <div className="min-h-screen bg-[#120e1a] text-[#f7f1fb] flex flex-col font-sans">
      {/* Top Navbar */}
      <header className="border-b border-[#292135] bg-[#171320]/80 backdrop-blur sticky top-0 z-50 px-6 py-4 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-rose-600 via-pink-600 to-amber-500 flex items-center justify-center text-xl shadow-lg shadow-rose-900/30">
            🌶️
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-bold text-lg tracking-tight text-white">Spice Hoes</h1>
              <span className="text-xs px-2 py-0.5 rounded-full bg-rose-500/20 text-rose-300 font-mono border border-rose-500/30">
                Core Loop v0.2.0
              </span>
            </div>
            <p className="text-xs text-gray-400">Autonomous Adult AI Influencer Portfolio &amp; Review Desk</p>
          </div>
        </div>

        {/* Global KPIs */}
        <div className="flex items-center gap-3 overflow-x-auto text-xs font-mono">
          <div className="px-3 py-1.5 rounded-lg bg-[#211a2f] border border-[#3b2e52] flex items-center gap-2">
            <span className="text-gray-400">Net:</span>
            <span className={`font-semibold ${totalNet >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              ${(totalNet / 100).toFixed(2)}
            </span>
          </div>
          <div className="px-3 py-1.5 rounded-lg bg-[#211a2f] border border-[#3b2e52] flex items-center gap-2">
            <span className="text-gray-400">Gross:</span>
            <span className="font-semibold text-white">${(totalRevenue / 100).toFixed(2)}</span>
          </div>
          <div className="px-3 py-1.5 rounded-lg bg-[#211a2f] border border-[#3b2e52] flex items-center gap-2">
            <span className="text-gray-400">Published:</span>
            <span className="font-semibold text-white">{totalPublished}</span>
          </div>
          <div className="px-3 py-1.5 rounded-lg bg-pink-500/10 border border-pink-500/30 flex items-center gap-2">
            <span className="text-pink-300">Pending Review:</span>
            <span className="font-semibold text-pink-400">{pendingReviews}</span>
          </div>
          <button 
            onClick={fetchData} 
            className="p-2 rounded-lg bg-[#211a2f] hover:bg-[#2b223d] border border-[#3b2e52] text-gray-300 transition-colors"
            title="Refresh All Data"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>
      </header>

      {/* Navigation Sub-header */}
      <nav className="border-b border-[#292135] bg-[#140f1d] px-6 flex gap-1 overflow-x-auto text-sm">
        <button
          onClick={() => setActiveTab('review')}
          className={`py-3 px-4 border-b-2 font-medium flex items-center gap-2 transition-colors ${
            activeTab === 'review'
              ? 'border-pink-500 text-white font-semibold'
              : 'border-transparent text-gray-400 hover:text-gray-200'
          }`}
        >
          <ShieldCheck className="w-4 h-4 text-pink-400" />
          Review Desk
          {pendingReviews > 0 && (
            <span className="px-1.5 py-0.2 rounded-full bg-pink-500 text-white text-[10px] font-bold">
              {pendingReviews}
            </span>
          )}
        </button>

        <button
          onClick={() => setActiveTab('media')}
          className={`py-3 px-4 border-b-2 font-medium flex items-center gap-2 transition-colors ${
            activeTab === 'media'
              ? 'border-purple-500 text-white font-semibold'
              : 'border-transparent text-gray-400 hover:text-gray-200'
          }`}
        >
          <Video className="w-4 h-4 text-purple-400" />
          Video &amp; Voice Studio
        </button>

        <button
          onClick={() => setActiveTab('scheduler')}
          className={`py-3 px-4 border-b-2 font-medium flex items-center gap-2 transition-colors ${
            activeTab === 'scheduler'
              ? 'border-indigo-500 text-white font-semibold'
              : 'border-transparent text-gray-400 hover:text-gray-200'
          }`}
        >
          <Calendar className="w-4 h-4 text-indigo-400" />
          Publishing Outbox
        </button>

        <button
          onClick={() => setActiveTab('personas')}
          className={`py-3 px-4 border-b-2 font-medium flex items-center gap-2 transition-colors ${
            activeTab === 'personas'
              ? 'border-rose-500 text-white font-semibold'
              : 'border-transparent text-gray-400 hover:text-gray-200'
          }`}
        >
          <Users className="w-4 h-4 text-rose-400" />
          5 Persona Dossiers
        </button>

        <button
          onClick={() => setActiveTab('engine')}
          className={`py-3 px-4 border-b-2 font-medium flex items-center gap-2 transition-colors ${
            activeTab === 'engine'
              ? 'border-amber-500 text-white font-semibold'
              : 'border-transparent text-gray-400 hover:text-gray-200'
          }`}
        >
          <TrendingUp className="w-4 h-4 text-amber-400" />
          Contextual Bandit RL
        </button>

        <button
          onClick={() => setActiveTab('ledger')}
          className={`py-3 px-4 border-b-2 font-medium flex items-center gap-2 transition-colors ${
            activeTab === 'ledger'
              ? 'border-emerald-500 text-white font-semibold'
              : 'border-transparent text-gray-400 hover:text-gray-200'
          }`}
        >
          <BarChart3 className="w-4 h-4 text-emerald-400" />
          Commerce Ledger
        </button>

        <button
          onClick={() => setActiveTab('events')}
          className={`py-3 px-4 border-b-2 font-medium flex items-center gap-2 transition-colors ${
            activeTab === 'events'
              ? 'border-blue-500 text-white font-semibold'
              : 'border-transparent text-gray-400 hover:text-gray-200'
          }`}
        >
          <Clock className="w-4 h-4 text-blue-400" />
          Audit Event Vault ({events.length})
        </button>
      </nav>

      {/* Main Content Area */}
      <main className="flex-1 p-6 max-w-7xl w-full mx-auto">
        {/* TAB 1: REVIEW DESK */}
        {activeTab === 'review' && (
          <div className="space-y-6">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-[#1a1424] p-5 rounded-2xl border border-[#2e233d]">
              <div>
                <h2 className="text-xl font-bold flex items-center gap-2">
                  <ShieldCheck className="w-5 h-5 text-pink-400" />
                  Human-in-the-Loop Review Desk
                </h2>
                <p className="text-sm text-gray-400 mt-1">
                  Proposed media experiments require authenticated human operator approval before scheduling or publishing.
                </p>
              </div>
              <div className="flex items-center gap-2 text-sm bg-[#120e1a] px-3 py-2 rounded-xl border border-[#3b2e52]">
                <span className="text-gray-400 font-mono text-xs">Reviewer:</span>
                <input
                  type="text"
                  value={reviewerName}
                  onChange={(e) => setReviewerName(e.target.value)}
                  className="bg-transparent text-pink-300 font-medium focus:outline-none text-sm w-32"
                  placeholder="Reviewer ID"
                />
              </div>
            </div>

            {/* Candidate Cards Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {candidates.filter(c => c.status === 'proposed').map(candidate => {
                const persona = personas.find(p => p.id === candidate.persona_id);
                const colorClass = getPersonaColor(persona?.type);

                return (
                  <div key={candidate.id} className="bg-[#1b1526] rounded-2xl border border-[#362a4a] overflow-hidden flex flex-col justify-between shadow-xl">
                    <div>
                      {/* Card Header */}
                      <div className="p-4 border-b border-[#292038] flex items-center justify-between bg-[#151020]">
                        <div className="flex items-center gap-2">
                          <span className={`px-2 py-0.5 rounded-full text-xs font-semibold border ${colorClass}`}>
                            {persona?.type || 'Persona'} · {candidate.persona_name}
                          </span>
                          <span className="text-xs text-gray-400 font-mono">{candidate.theme}</span>
                        </div>
                        <span className="text-xs px-2 py-0.5 rounded bg-yellow-500/20 text-yellow-300 border border-yellow-500/30 font-mono">
                          Proposed
                        </span>
                      </div>

                      {/* Card Body */}
                      <div className="p-5 space-y-4">
                        {candidate.asset_uri && (
                          <div className="relative rounded-xl overflow-hidden aspect-[16/9] bg-black/40 border border-[#2e233d]">
                            <img 
                              src={candidate.asset_uri} 
                              alt={candidate.theme}
                              className="w-full h-full object-cover" 
                            />
                            <div className="absolute bottom-2 left-2 px-2 py-1 rounded bg-black/70 backdrop-blur text-[11px] font-mono text-gray-300">
                              Format: {candidate.format} · Channel: {candidate.channel}
                            </div>
                          </div>
                        )}

                        <div>
                          <div className="text-xs text-gray-400 mb-1 flex items-center justify-between font-mono">
                            <span>Generation Prompt &amp; Lineage</span>
                            <span>Cost: ${((candidate.cost_cents || 15) / 100).toFixed(2)}</span>
                          </div>
                          <pre className="text-xs bg-[#100c17] p-3 rounded-xl border border-[#292038] text-gray-300 whitespace-pre-wrap font-mono leading-relaxed">
                            {candidate.prompt || 'No generation prompt provided'}
                          </pre>
                        </div>

                        <div className="text-xs text-gray-400 flex flex-wrap gap-3 font-mono">
                          <div><span className="text-gray-500">Offer:</span> {candidate.offer}</div>
                          <div><span className="text-gray-500">Model:</span> {candidate.model || 'diffusion-xl'}</div>
                          <div><span className="text-gray-500">Seed:</span> {candidate.seed}</div>
                        </div>

                        <div>
                          <label className="text-xs text-gray-400 block mb-1">Operator Notes / Rationale:</label>
                          <input
                            type="text"
                            placeholder="Add evaluation note (e.g. anatomy checked, good lighting)"
                            value={reviewNotes[candidate.id] || ''}
                            onChange={(e) => setReviewNotes({ ...reviewNotes, [candidate.id]: e.target.value })}
                            className="w-full text-xs bg-[#120e1a] border border-[#3b2e52] rounded-xl px-3 py-2 text-white focus:outline-none focus:border-pink-500"
                          />
                        </div>
                      </div>
                    </div>

                    {/* Action Buttons */}
                    <div className="p-4 border-t border-[#292038] bg-[#140f1f] flex items-center justify-end gap-2">
                      <button
                        onClick={() => handleReviewCandidate(candidate.id, 'rejected')}
                        className="px-3 py-1.5 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 border border-rose-500/30 text-xs font-semibold flex items-center gap-1.5 transition-colors"
                      >
                        <XCircle className="w-3.5 h-3.5" />
                        Reject
                      </button>
                      <button
                        onClick={() => handleReviewCandidate(candidate.id, 'revise')}
                        className="px-3 py-1.5 rounded-xl bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/30 text-xs font-semibold flex items-center gap-1.5 transition-colors"
                      >
                        <RotateCcw className="w-3.5 h-3.5" />
                        Revise
                      </button>
                      <button
                        onClick={() => handleReviewCandidate(candidate.id, 'approved')}
                        className="px-4 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold flex items-center gap-1.5 shadow-lg shadow-emerald-900/40 transition-colors"
                      >
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        Approve Candidate
                      </button>
                    </div>
                  </div>
                );
              })}

              {candidates.filter(c => c.status === 'proposed').length === 0 && (
                <div className="col-span-full py-16 text-center bg-[#181223] rounded-2xl border border-dashed border-[#342747]">
                  <CheckCircle2 className="w-12 h-12 text-emerald-400 mx-auto mb-3 opacity-60" />
                  <h3 className="text-lg font-semibold text-white">Review Desk Queue is Clear</h3>
                  <p className="text-sm text-gray-400 mt-1 max-w-md mx-auto">
                    All currently proposed candidates have been reviewed. Generate new briefs in the studio or check the approved archive below.
                  </p>
                </div>
              )}
            </div>

            {/* Approved & Historical Candidates List */}
            <div className="mt-8 bg-[#181223] rounded-2xl border border-[#2e233d] p-5">
              <h3 className="text-sm font-bold text-gray-300 uppercase tracking-wider mb-4 flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                Approved &amp; Published Candidates ({candidates.filter(c => c.status !== 'proposed').length})
              </h3>
              <div className="space-y-3">
                {candidates.filter(c => c.status !== 'proposed').map(c => (
                  <div key={c.id} className="p-3 bg-[#130f1c] rounded-xl border border-[#292038] flex flex-wrap items-center justify-between gap-3 text-xs">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-lg overflow-hidden bg-black/40 flex-shrink-0">
                        {c.asset_uri ? <img src={c.asset_uri} alt="" className="w-full h-full object-cover" /> : <div className="w-full h-full flex items-center justify-center text-gray-600">🖼️</div>}
                      </div>
                      <div>
                        <div className="font-semibold text-white">{c.persona_name} · {c.theme}</div>
                        <div className="text-gray-400 font-mono text-[11px]">{c.channel} · Offer: {c.offer}</div>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className={`px-2 py-0.5 rounded text-[11px] font-mono capitalize ${
                        c.status === 'published' ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30' :
                        c.status === 'approved' ? 'bg-blue-500/20 text-blue-300 border border-blue-500/30' :
                        'bg-gray-500/20 text-gray-300'
                      }`}>
                        {c.status}
                      </span>
                      {c.status === 'published' && (
                        <button
                          onClick={() => handleSimulateTraffic(c.id)}
                          className="px-2.5 py-1 rounded-lg bg-pink-500/10 hover:bg-pink-500/20 text-pink-300 border border-pink-500/30 text-[11px] font-mono flex items-center gap-1"
                        >
                          <Flame className="w-3 h-3 text-pink-400" />
                          Simulate Traffic (+$$)
                        </button>
                      )}
                      {c.reviewer && (
                        <span className="text-gray-400 text-[11px] font-mono">
                          by @{c.reviewer}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* TAB 2: VIDEO & MEDIA STUDIO */}
        {activeTab === 'media' && (
          <div className="space-y-6">
            <div className="bg-[#1a1424] p-5 rounded-2xl border border-[#2e233d] flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
              <div>
                <h2 className="text-xl font-bold flex items-center gap-2">
                  <Video className="w-5 h-5 text-purple-400" />
                  Media, Voice &amp; Video Pipeline Studio
                </h2>
                <p className="text-sm text-gray-400 mt-1">
                  Transforms approved still candidate + persona voice profile into compliant 9:16 vertical video assets with automated technical QA.
                </p>
              </div>
            </div>

            {/* Pipeline Generator Panel */}
            <div className="bg-[#1b1526] p-6 rounded-2xl border border-[#362a4a] grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="space-y-4">
                <label className="text-xs font-bold text-gray-300 block uppercase tracking-wider">
                  Target Adult Persona
                </label>
                <div className="space-y-2">
                  {personas.map(p => (
                    <button
                      key={p.id}
                      onClick={() => setSelectedPersona(p.id)}
                      className={`w-full text-left p-3 rounded-xl border flex items-center justify-between text-xs transition-colors ${
                        selectedPersona === p.id 
                          ? 'border-purple-500 bg-purple-500/15 text-white' 
                          : 'border-[#2d223f] bg-[#140f1e] text-gray-400 hover:border-gray-600'
                      }`}
                    >
                      <div>
                        <div className="font-semibold text-white">{p.name} ({p.age})</div>
                        <div className="text-[11px] text-gray-400">{p.type} archetype · {p.hobbies[0]}</div>
                      </div>
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-black/40 text-purple-300">
                        9:16
                      </span>
                    </button>
                  ))}
                </div>
              </div>

              <div className="md:col-span-2 space-y-4">
                <div>
                  <label className="text-xs font-bold text-gray-300 block uppercase tracking-wider mb-2">
                    Video Voiceover Script (15-20s duration)
                  </label>
                  <textarea
                    rows={4}
                    value={videoScript}
                    onChange={(e) => setVideoScript(e.target.value)}
                    className="w-full text-xs font-mono bg-[#110d19] border border-[#3b2e52] rounded-xl p-3 text-white focus:outline-none focus:border-purple-500 leading-relaxed"
                    placeholder="Enter short-form script..."
                  />
                </div>

                <div className="bg-[#120e1a] p-4 rounded-xl border border-[#2b203c] text-xs font-mono space-y-2">
                  <div className="text-gray-400 font-bold">Standard 3-Scene Render Architecture:</div>
                  <div className="grid grid-cols-3 gap-2 text-[11px]">
                    <div className="p-2 rounded bg-[#1a1426] border border-[#312544]">
                      <div className="text-purple-300 font-semibold">1. Hook / Intro (5s)</div>
                      <div className="text-gray-400">Subtle push-in · Voice intro</div>
                    </div>
                    <div className="p-2 rounded bg-[#1a1426] border border-[#312544]">
                      <div className="text-purple-300 font-semibold">2. Core Action (6s)</div>
                      <div className="text-gray-400">Hand motion · Product / demo</div>
                    </div>
                    <div className="p-2 rounded bg-[#1a1426] border border-[#312544]">
                      <div className="text-purple-300 font-semibold">3. CTA Close (5s)</div>
                      <div className="text-gray-400">Direct address · Audio ducking</div>
                    </div>
                  </div>
                </div>

                <button
                  onClick={handleCreateMediaJob}
                  className="w-full py-3 rounded-xl bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-500 hover:to-pink-500 text-white font-semibold text-xs flex items-center justify-center gap-2 shadow-lg shadow-purple-900/30 transition-all"
                >
                  <Sparkles className="w-4 h-4" />
                  Generate 9:16 Video Asset &amp; Run Automated QA
                </button>
              </div>
            </div>

            {/* Media Jobs List */}
            <div className="space-y-4">
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <Video className="w-4 h-4 text-purple-400" />
                Rendered Media Jobs ({mediaJobs.length})
              </h3>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {mediaJobs.map(job => (
                  <div key={job.id} className="bg-[#1b1526] rounded-2xl border border-[#362a4a] p-5 space-y-4 flex flex-col justify-between">
                    <div>
                      <div className="flex items-center justify-between border-b border-[#2a203b] pb-3 mb-3">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-bold text-white uppercase">{job.persona_id}</span>
                          <span className="text-[11px] font-mono text-gray-400">{job.aspect_ratio} MP4</span>
                        </div>
                        <span className={`text-[11px] font-mono px-2 py-0.5 rounded capitalize ${
                          job.status === 'review_ready' ? 'bg-pink-500/20 text-pink-300 border border-pink-500/30' :
                          job.status === 'approved' ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30' :
                          job.status === 'scheduled' ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/30' :
                          'bg-gray-500/20 text-gray-300'
                        }`}>
                          {job.status.replace('_', ' ')}
                        </span>
                      </div>

                      <div className="grid grid-cols-3 gap-3 mb-3">
                        <div className="col-span-1 rounded-xl overflow-hidden aspect-[9/16] bg-black border border-[#2d223f] relative flex items-center justify-center">
                          {job.source_asset_uri && (
                            <img src={job.source_asset_uri} alt="" className="w-full h-full object-cover" />
                          )}
                          <div className="absolute inset-0 bg-black/40 flex items-center justify-center">
                            <Play className="w-8 h-8 text-white/90 drop-shadow" />
                          </div>
                        </div>

                        <div className="col-span-2 space-y-2 text-xs">
                          <div className="text-gray-300 font-mono text-[11px] bg-[#120e1a] p-2 rounded-lg border border-[#2a2039] line-clamp-3">
                            "{job.script}"
                          </div>

                          {/* Technical QA Badges */}
                          {job.qa_report && (
                            <div className="bg-[#140f20] p-2.5 rounded-lg border border-purple-500/20 text-[11px] font-mono space-y-1">
                              <div className="flex items-center justify-between text-emerald-400 font-semibold">
                                <span>Technical QA Score</span>
                                <span>{(job.qa_report.score * 100).toFixed(0)}% PASSED</span>
                              </div>
                              <div className="grid grid-cols-2 gap-1 text-[10px] text-gray-400">
                                <div>✓ 1080x1920 (9:16)</div>
                                <div>✓ Stereo AAC audio</div>
                                <div>✓ 30 FPS H.264</div>
                                <div>✓ Integrity valid</div>
                              </div>
                            </div>
                          )}

                          <div className="text-[11px] font-mono text-gray-400 space-y-0.5">
                            <div>Generation: ${((job.generation_cost_cents || 30) / 100).toFixed(2)}</div>
                            <div>Render &amp; FFmpeg: ${((job.render_cost_cents || 10) / 100).toFixed(2)}</div>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Media Actions */}
                    <div className="pt-3 border-t border-[#2a203b] flex items-center justify-between gap-2">
                      {job.status === 'review_ready' && (
                        <div className="flex items-center gap-2 w-full justify-end">
                          <button
                            onClick={() => handleReviewMediaJob(job.id, 'rejected')}
                            className="px-3 py-1.5 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 border border-rose-500/30 text-xs font-semibold"
                          >
                            Reject
                          </button>
                          <button
                            onClick={() => handleReviewMediaJob(job.id, 'approved')}
                            className="px-4 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold shadow-lg shadow-emerald-900/30"
                          >
                            Approve for Scheduling
                          </button>
                        </div>
                      )}

                      {job.status === 'approved' && (
                        <button
                          onClick={() => handleScheduleMedia(job.id)}
                          className="w-full py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold flex items-center justify-center gap-1.5 shadow-lg shadow-indigo-900/30"
                        >
                          <Calendar className="w-3.5 h-3.5" />
                          Schedule to Publishing Outbox
                        </button>
                      )}

                      {job.status === 'scheduled' && (
                        <div className="text-xs text-indigo-300 font-mono flex items-center gap-1.5">
                          <Clock className="w-3.5 h-3.5" />
                          Queued in Outbox for automated publication
                        </div>
                      )}

                      {job.status === 'published' && (
                        <div className="text-xs text-emerald-300 font-mono flex items-center gap-1.5">
                          <CheckCircle2 className="w-3.5 h-3.5" />
                          Published to social platforms
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* TAB 3: SCHEDULER & PUBLISHING OUTBOX */}
        {activeTab === 'scheduler' && (
          <div className="space-y-6">
            <div className="bg-[#1a1424] p-5 rounded-2xl border border-[#2e233d] flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
              <div>
                <h2 className="text-xl font-bold flex items-center gap-2">
                  <Calendar className="w-5 h-5 text-indigo-400" />
                  Publishing Outbox &amp; Review-Gated Scheduler
                </h2>
                <p className="text-sm text-gray-400 mt-1">
                  Enforces strict review gates: only human-approved media can be scheduled, published, or retried.
                </p>
              </div>
              <button
                onClick={handleProcessOutbox}
                className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs flex items-center gap-2 shadow-lg shadow-indigo-900/30"
              >
                <Send className="w-3.5 h-3.5" />
                Process Outbox Worker (Publish Due)
              </button>
            </div>

            <div className="space-y-3">
              {schedules.map(post => (
                <div key={post.schedule_id} className="p-4 bg-[#1b1526] rounded-xl border border-[#362a4a] flex flex-wrap items-center justify-between gap-4 text-xs font-mono">
                  <div className="flex items-center gap-4">
                    <div className="w-10 h-10 rounded-lg bg-indigo-500/10 border border-indigo-500/30 flex items-center justify-center text-indigo-300 font-bold">
                      IG
                    </div>
                    <div>
                      <div className="font-semibold text-white flex items-center gap-2">
                        <span>Platform: {post.platform.toUpperCase()}</span>
                        <span className="text-gray-400">@{post.account_id}</span>
                      </div>
                      <div className="text-gray-400 text-[11px] mt-0.5">
                        Scheduled for: {new Date(post.scheduled_at).toLocaleString()}
                      </div>
                      {post.canonical_url && (
                        <a 
                          href={post.canonical_url} 
                          target="_blank" 
                          rel="noreferrer" 
                          className="text-pink-400 hover:underline flex items-center gap-1 text-[11px] mt-1"
                        >
                          <ExternalLink className="w-3 h-3" />
                          {post.canonical_url}
                        </a>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-3">
                    <span className={`px-2.5 py-1 rounded-full text-xs font-semibold capitalize ${
                      post.status === 'published' ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30' :
                      post.status === 'scheduled' ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30' :
                      'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                    }`}>
                      {post.status}
                    </span>
                  </div>
                </div>
              ))}

              {schedules.length === 0 && (
                <div className="py-16 text-center bg-[#181223] rounded-2xl border border-dashed border-[#342747]">
                  <Calendar className="w-10 h-10 text-gray-500 mx-auto mb-2 opacity-60" />
                  <div className="text-sm font-semibold text-white">Outbox is Empty</div>
                  <p className="text-xs text-gray-400 mt-1">Approve a video job in the Video Studio to schedule it for publication.</p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* TAB 4: PERSONAS */}
        {activeTab === 'personas' && (
          <div className="space-y-6">
            <div className="bg-[#1a1424] p-5 rounded-2xl border border-[#2e233d]">
              <h2 className="text-xl font-bold flex items-center gap-2">
                <Users className="w-5 h-5 text-rose-400" />
                The 5 Starting Personas (Fictional Adult Dossiers)
              </h2>
              <p className="text-sm text-gray-400 mt-1">
                Strict adherence to spec: clearly disclosed adult fictional canon (ages 27-32), original likenesses, distinct interests, zero youth-coded styling.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {personas.map(persona => {
                const colorClass = getPersonaColor(persona.type);
                const personaStats = stats.find(s => s.persona_id === persona.id);

                return (
                  <div key={persona.id} className="bg-[#1b1526] rounded-2xl border border-[#362a4a] p-6 space-y-4 flex flex-col justify-between shadow-xl">
                    <div className="space-y-3">
                      <div className="flex items-center justify-between">
                        <span className={`px-2.5 py-0.5 rounded-full text-xs font-bold border ${colorClass}`}>
                          {persona.type} Archetype
                        </span>
                        <span className="text-xs text-gray-400 font-mono">Age {persona.age} · {persona.height_cm}cm</span>
                      </div>

                      <h3 className="text-xl font-bold text-white">{persona.name}</h3>

                      <div className="text-xs text-gray-300 font-medium">
                        <span className="text-gray-400 block mb-0.5 font-bold uppercase tracking-wider text-[10px]">Backstory</span>
                        {persona.backstory}
                      </div>

                      <div className="text-xs text-gray-300">
                        <span className="text-gray-400 block mb-0.5 font-bold uppercase tracking-wider text-[10px]">Visual Anchors</span>
                        {persona.visual}
                      </div>

                      <div className="text-xs text-gray-300">
                        <span className="text-gray-400 block mb-0.5 font-bold uppercase tracking-wider text-[10px]">Voice Style</span>
                        {persona.voice}
                      </div>

                      <div className="text-xs text-gray-300">
                        <span className="text-gray-400 block mb-0.5 font-bold uppercase tracking-wider text-[10px]">Fictional Heartbreak</span>
                        {persona.heartbreak}
                      </div>

                      <div className="flex flex-wrap gap-1.5 pt-2">
                        {persona.hobbies.map((h, i) => (
                          <span key={i} className="text-[11px] px-2 py-0.5 rounded-lg bg-[#251d33] text-gray-300 border border-[#3d2f54]">
                            {h}
                          </span>
                        ))}
                      </div>
                    </div>

                    <div className="pt-4 border-t border-[#292038] text-xs font-mono flex items-center justify-between text-gray-400">
                      <div>Published: <span className="text-white font-bold">{personaStats?.published || 0}</span></div>
                      <div>Net: <span className={`font-bold ${(personaStats?.net_cents || 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                        ${((personaStats?.net_cents || 0) / 100).toFixed(2)}
                      </span></div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* TAB 5: DECISION ENGINE */}
        {activeTab === 'engine' && recommendation && (
          <div className="space-y-6">
            <div className="bg-[#1a1424] p-5 rounded-2xl border border-[#2e233d] flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
              <div>
                <h2 className="text-xl font-bold flex items-center gap-2">
                  <TrendingUp className="w-5 h-5 text-amber-400" />
                  Allocation &amp; Autonomy Engine
                </h2>
                <p className="text-sm text-gray-400 mt-1">
                  Canonical runtime limits, DeepRL readiness, budget pressure, and transparent allocation estimates.
                </p>
              </div>
              <div className="text-xs font-mono px-3 py-1.5 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300">
                Policy: {recommendation.policy_version} ({recommendation.method})
              </div>
            </div>

            {capabilities && (
              <div className="bg-[#1b1526] p-5 rounded-2xl border border-[#362a4a]">
                <div className="flex items-center justify-between gap-3 mb-4">
                  <div>
                    <h3 className="text-sm font-bold text-white uppercase tracking-wider">Adapter Readiness</h3>
                    <p className="text-xs text-gray-400 mt-1">Reports configuration only; no external provider calls are made by this check.</p>
                  </div>
                  <span className="text-[11px] font-mono text-gray-400">fail-closed</span>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                  {[
                    ['Instagram', capabilities.distribution?.instagram],
                    ['TikTok', capabilities.distribution?.tiktok],
                    ['YouTube', capabilities.distribution?.youtube],
                    ['FFmpeg', capabilities.media?.ffmpeg],
                    ['Luma', capabilities.media?.luma],
                    ['ElevenLabs', capabilities.media?.elevenlabs],
                    ['SyncLabs', capabilities.media?.synclabs],
                    ['Local Dream', capabilities.media?.local_dream],
                  ].map(([label, ready]) => (
                    <div key={String(label)} className="bg-[#120e1a] border border-[#2d223f] rounded-lg px-3 py-2 flex items-center justify-between gap-2">
                      <span className="text-gray-300">{String(label)}</span>
                      <span className={`font-mono ${ready ? 'text-emerald-300' : 'text-gray-500'}`}>{ready ? 'ready' : 'off'}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {thompsonRecommendation && (
              <div className="bg-[#1b1526] p-5 rounded-2xl border border-[#4a365f]">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="text-[11px] uppercase tracking-wider text-purple-300 font-bold">Bayesian Thompson Allocation</div>
                    <div className="text-lg font-bold text-white mt-1">{thompsonRecommendation.name} ({thompsonRecommendation.persona_id})</div>
                    <div className="text-xs text-gray-400 mt-1">
                      {(thompsonRecommendation.selection_probability * 100).toFixed(1)}% selection probability · USD {(thompsonRecommendation.estimated_net_cents_per_published / 100).toFixed(2)} estimated net / published
                    </div>
                  </div>
                  <span className="text-[11px] font-mono px-2 py-1 rounded bg-purple-500/15 border border-purple-500/30 text-purple-300">
                    {thompsonRecommendation.policy_version}
                  </span>
                </div>
                {(thompsonRecommendation as any).ci_95 && (
                  <div className="mt-3 text-xs font-mono text-gray-400">
                    95% credible interval: USD {((thompsonRecommendation as any).ci_95.lower / 100).toFixed(2)} to USD {((thompsonRecommendation as any).ci_95.upper / 100).toFixed(2)}
                  </div>
                )}
              </div>
            )}

            {doctorStatus && (
              <div className={`p-4 rounded-2xl border ${doctorStatus.healthy ? 'bg-emerald-500/5 border-emerald-500/20' : 'bg-rose-500/10 border-rose-500/30'}`}>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="text-xs font-bold uppercase tracking-wider text-gray-300">Operations Doctor</div>
                    <div className="text-xs text-gray-400 mt-1">
                      DB {doctorStatus.integrity?.quick_check} · {doctorStatus.counts?.events || 0} events · {doctorStatus.counts?.knowledge_unembedded || 0} unembedded knowledge items
                    </div>
                  </div>
                  <span className={`text-xs font-mono px-2 py-1 rounded border ${doctorStatus.healthy ? 'text-emerald-300 border-emerald-500/30' : 'text-rose-300 border-rose-500/30'}`}>
                    {doctorStatus.healthy ? 'healthy' : 'attention required'}
                  </span>
                </div>
                {doctorStatus.warnings?.length > 0 && (
                  <div className="text-xs text-amber-300 mt-2 font-mono">Warnings: {doctorStatus.warnings.join(', ')}</div>
                )}
              </div>
            )}

            {autopilotStatus && (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="bg-[#1b1526] p-4 rounded-2xl border border-[#362a4a]">
                  <div className="text-[11px] uppercase tracking-wider text-gray-400 font-bold">Review Queue Pressure</div>
                  <div className="text-xl font-bold text-white mt-1">{autopilotStatus.pending_review} / {autopilotStatus.max_pending_review}</div>
                  <div className="h-2 bg-[#120e1a] rounded-full overflow-hidden mt-3">
                    <div className="h-full bg-gradient-to-r from-emerald-500 to-amber-500" style={{ width: `${Math.min(100, (autopilotStatus.pending_review / Math.max(1, autopilotStatus.max_pending_review)) * 100)}%` }} />
                  </div>
                </div>
                <div className="bg-[#1b1526] p-4 rounded-2xl border border-[#362a4a]">
                  <div className="text-[11px] uppercase tracking-wider text-gray-400 font-bold">Spend Today</div>
                  <div className="text-xl font-bold text-white mt-1">USD {(autopilotStatus.spent_today_cents / 100).toFixed(2)} <span className="text-xs text-gray-500 font-normal">/ USD {(autopilotStatus.daily_budget_cents / 100).toFixed(2)}</span></div>
                  <div className="h-2 bg-[#120e1a] rounded-full overflow-hidden mt-3">
                    <div className="h-full bg-gradient-to-r from-purple-500 to-pink-500" style={{ width: `${Math.min(100, (autopilotStatus.spent_today_cents / Math.max(1, autopilotStatus.daily_budget_cents)) * 100)}%` }} />
                  </div>
                </div>
                <div className="bg-[#1b1526] p-4 rounded-2xl border border-[#362a4a]">
                  <div className="text-[11px] uppercase tracking-wider text-gray-400 font-bold">Recent Autopilot Runs</div>
                  <div className="text-xl font-bold text-white mt-1">{autopilotStatus.recent_runs?.length || 0}</div>
                  <div className="text-xs text-gray-400 mt-2">{autopilotStatus.recent_runs?.[0] ? `Latest: ${autopilotStatus.recent_runs[0].status}` : "No recorded runs yet"}</div>
                </div>
              </div>
            )}

            {(runtimePolicy || rlStatus) && (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {runtimePolicy && (
                  <div className="bg-[#1b1526] p-6 rounded-2xl border border-[#362a4a] space-y-4">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <h3 className="text-sm font-bold text-white uppercase tracking-wider">Runtime Operating Policy</h3>
                        <p className="text-xs text-gray-400 mt-1">Version {runtimePolicy.version} · actor {runtimePolicy.actor}</p>
                      </div>
                      <span className="text-[11px] font-mono px-2 py-1 rounded bg-purple-500/15 border border-purple-500/30 text-purple-300">canonical</span>
                    </div>
                    <div className="space-y-3">
                      {[
                        ['daily_budget_cents', 'Daily budget', 100],
                        ['max_pending_review', 'Max pending review', 1],
                        ['min_impressions_to_learn', 'Min impressions to learn', 10],
                        ['rl_min_experiences', 'RL min experiences', 1],
                      ].map(([key, label, step]) => (
                        <label key={String(key)} className="block">
                          <div className="flex items-center justify-between text-xs mb-1">
                            <span className="text-gray-300">{String(label)}</span>
                            <span className="font-mono text-white">{String(key).includes("cents") ? `USD ${((runtimePolicy.values?.[String(key)] || 0) / 100).toFixed(2)}` : runtimePolicy.values?.[String(key)]}</span>
                          </div>
                          <input
                            type="number"
                            min={String(key) === 'max_pending_review' || String(key) === 'rl_min_experiences' ? 1 : 0}
                            step={Number(step)}
                            disabled={controlBusy}
                            value={runtimePolicy.values?.[String(key)] ?? ""}
                            onChange={(e) => setRuntimePolicy({ ...runtimePolicy, values: { ...runtimePolicy.values, [String(key)]: Number(e.target.value) } })}
                            onBlur={(e) => handlePolicyChange(String(key), Number(e.target.value))}
                            className="w-full bg-[#120e1a] border border-[#3b2e52] rounded-lg px-3 py-2 text-xs font-mono text-white focus:outline-none focus:border-purple-500 disabled:opacity-50"
                          />
                        </label>
                      ))}
                    </div>
                    <div className="grid grid-cols-3 gap-2 pt-2 border-t border-[#2b203c]">
                      {[
                        ['identity_threshold', 'Identity'],
                        ['quality_threshold', 'Quality'],
                        ['reference_strength', 'Reference'],
                      ].map(([key, label]) => (
                        <label key={String(key)} className="text-[11px] text-gray-400">
                          {String(label)}
                          <input
                            type="number" min="0" max="1" step="0.01" disabled={controlBusy}
                            value={runtimePolicy.values?.[String(key)] ?? ""}
                            onChange={(e) => setRuntimePolicy({ ...runtimePolicy, values: { ...runtimePolicy.values, [String(key)]: Number(e.target.value) } })}
                            onBlur={(e) => handlePolicyChange(String(key), Number(e.target.value))}
                            className="mt-1 w-full bg-[#120e1a] border border-[#3b2e52] rounded-lg px-2 py-1.5 text-xs font-mono text-white focus:outline-none focus:border-purple-500 disabled:opacity-50"
                          />
                        </label>
                      ))}
                    </div>
                  </div>
                )}

                {rlStatus && (
                  <div className="bg-[#1b1526] p-6 rounded-2xl border border-[#362a4a] space-y-4">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <h3 className="text-sm font-bold text-white uppercase tracking-wider">Persistent DeepRL</h3>
                        <p className="text-xs text-gray-400 mt-1">{rlStatus.policy_version}</p>
                      </div>
                      <span className={`text-[11px] font-mono px-2 py-1 rounded border ${rlStatus.ready ? "bg-emerald-500/15 border-emerald-500/30 text-emerald-300" : "bg-amber-500/15 border-amber-500/30 text-amber-300"}`}>{rlStatus.ready ? "ready" : "gated"}</span>
                    </div>
                    <div className="bg-[#120e1a] border border-[#2d223f] rounded-xl p-4">
                      <div className="flex items-center justify-between text-xs font-mono mb-2"><span className="text-gray-400">Replay experience</span><span className="text-white font-bold">{rlStatus.experiences} / {rlStatus.minimum_experiences}</span></div>
                      <div className="h-3 bg-[#211a2f] rounded-full overflow-hidden"><div className="h-full bg-gradient-to-r from-purple-600 to-amber-500 rounded-full" style={{ width: `${Math.min(100, (rlStatus.experiences / Math.max(1, rlStatus.minimum_experiences)) * 100)}%` }} /></div>
                    </div>
                    <button onClick={handleTrainRL} disabled={!rlStatus.ready || controlBusy} className="w-full py-2.5 rounded-xl bg-amber-600 hover:bg-amber-500 disabled:bg-[#2a2333] disabled:text-gray-500 text-white text-xs font-semibold transition-colors">
                      {rlStatus.ready ? (controlBusy ? "Training…" : "Train & Save RL Snapshot") : `Need ${Math.max(0, rlStatus.minimum_experiences - rlStatus.experiences)} more experiences`}
                    </button>
                  </div>
                )}
              </div>
            )}

            {controlError && <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs font-mono">{controlError}</div>}

            <div className="bg-[#1b1526] p-6 rounded-2xl border border-[#362a4a] space-y-4">
              <div>
                <h3 className="text-sm font-bold text-white uppercase tracking-wider">Guarded Autopilot Launch</h3>
                <p className="text-xs text-gray-400 mt-1">Uses the active budget and review-queue limits. External Azure/local-dream calls occur only when you run it.</p>
              </div>
              <textarea
                rows={3}
                value={autopilotForm.objective}
                onChange={(e) => setAutopilotForm({ ...autopilotForm, objective: e.target.value })}
                className="w-full bg-[#120e1a] border border-[#3b2e52] rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-pink-500"
              />
              <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
                <input value={autopilotForm.channel} onChange={(e) => setAutopilotForm({ ...autopilotForm, channel: e.target.value })} placeholder="Channel" className="bg-[#120e1a] border border-[#3b2e52] rounded-lg px-2 py-2 text-xs text-white" />
                <input value={autopilotForm.offer} onChange={(e) => setAutopilotForm({ ...autopilotForm, offer: e.target.value })} placeholder="Offer" className="bg-[#120e1a] border border-[#3b2e52] rounded-lg px-2 py-2 text-xs text-white" />
                <input type="number" min="2" max="6" value={autopilotForm.variants} onChange={(e) => setAutopilotForm({ ...autopilotForm, variants: Number(e.target.value) })} aria-label="Variants" className="bg-[#120e1a] border border-[#3b2e52] rounded-lg px-2 py-2 text-xs text-white" />
                <input type="number" min="0" value={autopilotForm.cost_cents_per_asset} onChange={(e) => setAutopilotForm({ ...autopilotForm, cost_cents_per_asset: Number(e.target.value) })} aria-label="Cost cents per asset" className="bg-[#120e1a] border border-[#3b2e52] rounded-lg px-2 py-2 text-xs text-white" />
                <input type="number" value={autopilotForm.seed} onChange={(e) => setAutopilotForm({ ...autopilotForm, seed: e.target.value })} placeholder="Seed optional" className="bg-[#120e1a] border border-[#3b2e52] rounded-lg px-2 py-2 text-xs text-white" />
              </div>
              <button
                onClick={handleAutopilotRun}
                disabled={controlBusy || !autopilotForm.objective.trim() || !autopilotForm.channel.trim() || !autopilotForm.offer.trim()}
                className="w-full py-3 rounded-xl bg-gradient-to-r from-rose-600 to-amber-600 hover:from-rose-500 hover:to-amber-500 disabled:opacity-40 text-white text-xs font-bold"
              >
                {controlBusy ? 'Running guarded cycle…' : 'Run Guarded Autopilot Cycle'}
              </button>
              {autopilotResult && (
                <pre className="max-h-64 overflow-auto whitespace-pre-wrap text-[11px] font-mono bg-[#100c17] border border-[#292038] rounded-xl p-3 text-gray-300">{JSON.stringify(autopilotResult, null, 2)}</pre>
              )}
            </div>

            <div className="bg-gradient-to-r from-amber-500/10 via-purple-500/10 to-transparent p-6 rounded-2xl border border-amber-500/30">
              <div className="text-xs text-amber-400 font-bold uppercase tracking-wider mb-1">Next Candidate Allocation Pick</div>
              <div className="text-2xl font-bold text-white flex items-center gap-3">
                {recommendation.name} ({recommendation.persona_id})
                <span className="text-sm font-mono px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40">{(recommendation.selection_probability * 100).toFixed(1)}% Selection Probability</span>
              </div>
              <p className="text-xs text-gray-300 mt-2 font-mono">Estimated Net Outcome: USD {(recommendation.estimated_net_cents_per_published / 100).toFixed(2)} / publication · {recommendation.supporting_published_count} previous tests</p>
              <div className="text-xs text-gray-400 mt-3 pt-3 border-t border-[#3b2e52] font-mono">{recommendation.uncertainty_note} · {recommendation.ranking_change_condition}</div>
            </div>

            <div className="bg-[#1b1526] p-6 rounded-2xl border border-[#362a4a] space-y-4">
              <h3 className="text-sm font-bold text-gray-300 uppercase tracking-wider">Current Bandit Arm Probabilities &amp; Estimated Returns</h3>
              <div className="space-y-4">
                {recommendation.all_arms.map(arm => {
                  const persona = personas.find(p => p.id === arm.persona_id);
                  const isLeader = arm.persona_id === recommendation.persona_id;
                  return (
                    <div key={arm.persona_id} className="space-y-1.5">
                      <div className="flex items-center justify-between text-xs font-mono">
                        <span className={`font-semibold ${isLeader ? "text-amber-300" : "text-gray-300"}`}>{persona?.name || arm.persona_id} ({persona?.type})</span>
                        <div className="flex items-center gap-4 text-gray-400"><span>Est: USD {(arm.estimated_net_cents_per_published / 100).toFixed(2)}/pub</span><span className="font-bold text-white">{(arm.selection_probability * 100).toFixed(1)}%</span></div>
                      </div>
                      <div className="h-3 w-full bg-[#120e1a] rounded-full overflow-hidden border border-[#2d223f]">
                        <div className={`h-full rounded-full transition-all duration-500 ${isLeader ? "bg-gradient-to-r from-amber-500 to-pink-500" : "bg-purple-600"}`} style={{ width: `${Math.max(5, arm.selection_probability * 100)}%` }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        {/* TAB 6: COMMERCE LEDGER */}
        {activeTab === 'ledger' && (
          <div className="space-y-6">
            <div className="bg-[#1a1424] p-5 rounded-2xl border border-[#2e233d]">
              <h2 className="text-xl font-bold flex items-center gap-2">
                <BarChart3 className="w-5 h-5 text-emerald-400" />
                Observed Experiment &amp; Commerce Ledger
              </h2>
              <p className="text-sm text-gray-400 mt-1">
                Attributable revenue minus generation, compute, and distribution costs. Repeat purchases and refunds explicitly factored.
              </p>
            </div>

            <div className="bg-[#1b1526] rounded-2xl border border-[#362a4a] overflow-hidden shadow-xl">
              <table className="w-full text-left text-xs font-mono border-collapse">
                <thead>
                  <tr className="bg-[#140f1f] text-gray-400 border-b border-[#292038]">
                    <th className="p-4">Persona</th>
                    <th className="p-4">Archetype</th>
                    <th className="p-4">Published</th>
                    <th className="p-4">Impressions</th>
                    <th className="p-4">Clicks</th>
                    <th className="p-4">Revenue</th>
                    <th className="p-4">Refunds</th>
                    <th className="p-4">Costs</th>
                    <th className="p-4 text-right">Net Profit</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#241c33]">
                  {stats.map(s => {
                    const persona = personas.find(p => p.id === s.persona_id);
                    return (
                      <tr key={s.persona_id} className="hover:bg-[#20192e] transition-colors">
                        <td className="p-4 font-bold text-white">{s.name}</td>
                        <td className="p-4 text-gray-300">{persona?.type}</td>
                        <td className="p-4 text-gray-300">{s.published}</td>
                        <td className="p-4 text-gray-300">{s.impressions}</td>
                        <td className="p-4 text-gray-300">{s.clicks}</td>
                        <td className="p-4 text-white font-semibold">${(s.revenue_cents / 100).toFixed(2)}</td>
                        <td className="p-4 text-rose-300">${(s.refund_cents / 100).toFixed(2)}</td>
                        <td className="p-4 text-gray-400">${(s.cost_cents / 100).toFixed(2)}</td>
                        <td className={`p-4 text-right font-bold ${s.net_cents >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                          ${(s.net_cents / 100).toFixed(2)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* TAB 7: AUDIT EVENTS */}
        {activeTab === 'events' && (
          <div className="space-y-6">
            <div className="bg-[#1a1424] p-5 rounded-2xl border border-[#2e233d]">
              <h2 className="text-xl font-bold flex items-center gap-2">
                <Clock className="w-5 h-5 text-blue-400" />
                Immutable Append-Only Audit Trail
              </h2>
              <p className="text-sm text-gray-400 mt-1">
                Every candidate proposed, asset reviewed, video rendered, post published, and metric ingested records an auditable event.
              </p>
            </div>

            <div className="space-y-2 font-mono text-xs">
              {events.map(ev => (
                <div key={ev.id} className="p-3 bg-[#171122] rounded-xl border border-[#2c203d] flex flex-col md:flex-row md:items-center justify-between gap-2">
                  <div className="flex items-center gap-3">
                    <span className="text-gray-500 font-bold">#{ev.seq}</span>
                    <span className="px-2 py-0.5 rounded bg-blue-500/20 text-blue-300 border border-blue-500/30 text-[11px]">
                      {ev.kind}
                    </span>
                    <span className="text-gray-400 text-[11px] truncate max-w-md">
                      {JSON.stringify(ev.payload)}
                    </span>
                  </div>
                  <div className="text-gray-500 text-[11px]">
                    {new Date(ev.ts).toLocaleTimeString()}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
