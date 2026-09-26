import React, { useState } from 'react';
import {
  Layers,
  Sparkles,
  Zap,
  Cpu,
  Clock,
  Coins,
  CheckCircle2,
  TrendingUp,
  ShieldCheck,
  Play,
  RotateCw,
  Search,
  MessageSquare,
  DollarSign,
  BookOpen,
} from 'lucide-react';
import { InfluencerPersona, MoAResult } from '../types';
import { orchestrateMoA } from '../services/api';

interface MoAPipelineViewerProps {
  selectedPersona: InfluencerPersona;
}

export const MoAPipelineViewer: React.FC<MoAPipelineViewerProps> = ({ selectedPersona }) => {
  const [objective, setObjective] = useState(
    'Maximize Q4 subscription conversion and viral parasocial engagement without triggering audience fatigue'
  );
  const [isLoading, setIsLoading] = useState(false);
  const [moaResult, setMoaResult] = useState<MoAResult | null>(null);

  const handleRunMoA = async () => {
    setIsLoading(true);
    try {
      const result = await orchestrateMoA(selectedPersona, objective);
      setMoaResult(result);
    } catch (err) {
      console.error('Failed to run MoA orchestration:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const getAgentIcon = (name: string) => {
    switch (name) {
      case 'Trend Scout':
        return <Search className="w-4 h-4 text-cyan-400" />;
      case 'Psych Architect':
        return <Sparkles className="w-4 h-4 text-purple-400" />;
      case 'Monetization Tactician':
        return <DollarSign className="w-4 h-4 text-emerald-400" />;
      case 'CYOA Synthesizer':
        return <BookOpen className="w-4 h-4 text-pink-400" />;
      default:
        return <ShieldCheck className="w-4 h-4 text-amber-400" />;
    }
  };

  return (
    <div className="max-w-7xl mx-auto space-y-6 animate-fadeIn pb-12">
      {/* Top Deck */}
      <div className="bg-[#11131c] border border-white/10 rounded-3xl p-6 shadow-xl relative overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="px-2.5 py-0.5 rounded-full text-[10px] font-mono uppercase bg-purple-500/20 text-purple-300 border border-purple-500/30 flex items-center gap-1">
                <Layers className="w-3 h-3" />
                Mixture of Agents (MoA) Orchestrator
              </span>
              <span className="text-xs text-zinc-400">Multi-Model Specialized Delegation & Consensus</span>
            </div>
            <h1 className="text-2xl font-black text-white flex items-center gap-2">
              MoA Execution Pipeline: {selectedPersona.name}
            </h1>
            <p className="text-xs text-zinc-300 mt-0.5">
              Routes domain sub-tasks to specialized agent nodes, optimizing token efficiency and reducing overall operational latency.
            </p>
          </div>

          <button
            onClick={handleRunMoA}
            disabled={isLoading}
            className="px-5 py-2.5 rounded-2xl bg-gradient-to-r from-purple-600 via-pink-600 to-rose-600 hover:from-purple-500 hover:to-rose-500 text-white text-xs font-semibold shadow-lg shadow-purple-500/25 transition cursor-pointer flex items-center gap-2 disabled:opacity-50"
          >
            {isLoading ? <RotateCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4 fill-current" />}
            <span>{isLoading ? 'Orchestrating Agents...' : 'Execute MoA Consensus'}</span>
          </button>
        </div>

        {/* Objective Input */}
        <div className="mt-5 pt-4 border-t border-white/10 flex items-center gap-3">
          <span className="text-xs font-mono text-zinc-400 shrink-0">Current Objective:</span>
          <input
            type="text"
            value={objective}
            onChange={(e) => setObjective(e.target.value)}
            className="flex-1 px-3 py-2 rounded-xl bg-black/40 border border-white/10 text-xs text-white focus:outline-none focus:border-pink-500 font-mono"
            placeholder="Specify campaign or monetization objective..."
          />
        </div>
      </div>

      {/* MoA Results View */}
      {moaResult && (
        <div className="space-y-6">
          {/* Top Performance Telemetry */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 font-mono">
            <div className="p-4 rounded-2xl bg-[#11131c] border border-white/10">
              <div className="text-[10px] text-zinc-500 uppercase flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                Consensus Score
              </div>
              <div className="text-2xl font-black text-emerald-400 mt-1">
                {moaResult.consensusScore}%
              </div>
              <div className="text-[10px] text-zinc-400">High agent alignment</div>
            </div>

            <div className="p-4 rounded-2xl bg-[#11131c] border border-white/10">
              <div className="text-[10px] text-zinc-500 uppercase flex items-center gap-1">
                <Clock className="w-3.5 h-3.5 text-cyan-400" />
                Total Latency
              </div>
              <div className="text-2xl font-black text-cyan-400 mt-1">
                {moaResult.totalLatencyMs}ms
              </div>
              <div className="text-[10px] text-zinc-400">Under 600ms budget</div>
            </div>

            <div className="p-4 rounded-2xl bg-[#11131c] border border-white/10">
              <div className="text-[10px] text-zinc-500 uppercase flex items-center gap-1">
                <Cpu className="w-3.5 h-3.5 text-purple-400" />
                Token Economy
              </div>
              <div className="text-2xl font-black text-purple-400 mt-1">
                {moaResult.totalTokens}
              </div>
              <div className="text-[10px] text-zinc-400">Optimized context footprint</div>
            </div>

            <div className="p-4 rounded-2xl bg-[#11131c] border border-white/10">
              <div className="text-[10px] text-zinc-500 uppercase flex items-center gap-1">
                <Coins className="w-3.5 h-3.5 text-amber-400" />
                Operational Cost
              </div>
              <div className="text-2xl font-black text-amber-400 mt-1">
                ${moaResult.estimatedCostUsd}
              </div>
              <div className="text-[10px] text-zinc-400">Sub-cent execution</div>
            </div>
          </div>

          {/* Unified Consensus Synthesis Card */}
          <div className="p-6 rounded-3xl bg-gradient-to-r from-purple-500/10 via-pink-500/10 to-amber-500/10 border border-purple-500/30 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold uppercase tracking-wider text-pink-300 flex items-center gap-2">
                <Sparkles className="w-4 h-4" />
                Synthesized Action Strategy
              </h3>
              <span className="px-2.5 py-0.5 rounded-full text-xs font-mono font-bold bg-pink-500/20 text-pink-300 border border-pink-500/30">
                Action: {moaResult.finalSynthesis.recommendedAction}
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
              <div className="p-3.5 rounded-xl bg-black/40 border border-white/5 space-y-1">
                <div className="text-zinc-400 text-[10px] uppercase font-mono">Projected Uplift</div>
                <div className="text-emerald-400 font-bold text-sm">
                  {moaResult.finalSynthesis.projectedRevenueUplift}
                </div>
              </div>

              <div className="p-3.5 rounded-xl bg-black/40 border border-white/5 space-y-1">
                <div className="text-zinc-400 text-[10px] uppercase font-mono">Risk Assessment</div>
                <div className="text-zinc-300">
                  {moaResult.finalSynthesis.riskAssessment}
                </div>
              </div>

              <div className="p-3.5 rounded-xl bg-black/40 border border-white/5 space-y-1">
                <div className="text-zinc-400 text-[10px] uppercase font-mono">Recommended Narrative Hook</div>
                <div className="text-zinc-200 italic">
                  "{moaResult.finalSynthesis.narrativeHook}"
                </div>
              </div>
            </div>
          </div>

          {/* Deliberation Cards for Each Agent Node */}
          <div className="space-y-4">
            <h3 className="text-sm font-bold uppercase tracking-wider text-zinc-400">
              Specialized Agent Deliberations ({moaResult.agentDeliberations.length} Active Nodes)
            </h3>

            <div className="grid grid-cols-1 gap-4">
              {moaResult.agentDeliberations.map((agent, i) => (
                <div
                  key={i}
                  className="p-5 rounded-2xl bg-[#11131c] border border-white/10 hover:border-white/20 transition space-y-3"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/5 pb-2.5">
                    <div className="flex items-center gap-2.5">
                      <div className="p-2 rounded-xl bg-white/5 border border-white/10">
                        {getAgentIcon(agent.agentName)}
                      </div>
                      <div>
                        <h4 className="text-sm font-bold text-white leading-none">{agent.agentName}</h4>
                        <span className="text-[10px] text-zinc-500 font-mono">{agent.modelId}</span>
                      </div>
                    </div>

                    <div className="flex items-center gap-3 font-mono text-xs">
                      <span className="text-zinc-400">
                        Latency: <strong className="text-cyan-400">{agent.latencyMs}ms</strong>
                      </span>
                      <span className="text-zinc-600">|</span>
                      <span className="text-zinc-400">
                        Tokens: <strong className="text-purple-400">{agent.inputTokens + agent.outputTokens}</strong>
                      </span>
                      <span className="text-zinc-600">|</span>
                      <span className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 font-bold border border-emerald-500/20">
                        Score: {agent.score}/100
                      </span>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                    <div>
                      <div className="text-[10px] uppercase font-mono text-zinc-500 mb-1">Key Insights & Vector Data</div>
                      <p className="text-zinc-300 leading-relaxed">{agent.insights}</p>
                    </div>

                    <div>
                      <div className="text-[10px] uppercase font-mono text-pink-400 mb-1">Agent Recommendation</div>
                      <p className="text-zinc-200 leading-relaxed bg-white/5 p-2.5 rounded-xl border border-white/5">
                        {agent.recommendation}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {!moaResult && !isLoading && (
        <div className="p-12 rounded-3xl bg-[#11131c] border border-white/10 text-center space-y-4">
          <div className="w-12 h-12 rounded-2xl bg-purple-500/20 border border-purple-500/30 flex items-center justify-center mx-auto text-purple-300">
            <Layers className="w-6 h-6" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-white">MoA Pipeline Standing By</h3>
            <p className="text-xs text-zinc-400 max-w-md mx-auto mt-1">
              Click "Execute MoA Consensus" above to run the 5 specialized agent nodes on {selectedPersona.name}'s current state and target objective.
            </p>
          </div>
          <button
            onClick={handleRunMoA}
            className="px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold cursor-pointer transition shadow-md shadow-purple-500/20"
          >
            Run MoA Deliberation Now
          </button>
        </div>
      )}
    </div>
  );
};
