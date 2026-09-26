import React, { useState, useEffect } from 'react';
import {
  Cpu,
  TrendingUp,
  Activity,
  Zap,
  Sliders,
  Play,
  Pause,
  RotateCcw,
  CheckCircle2,
  DollarSign,
  AlertTriangle,
  Flame,
  Layers,
} from 'lucide-react';
import { InfluencerPersona, RLPolicy } from '../types';
import { executeDeepRLStep } from '../services/api';

interface DeepRLOrchestratorProps {
  selectedPersona: InfluencerPersona;
  onUpdatePersonaPolicy: (personaId: string, updatedPolicy: RLPolicy) => void;
}

export const DeepRLOrchestrator: React.FC<DeepRLOrchestratorProps> = ({
  selectedPersona,
  onUpdatePersonaPolicy,
}) => {
  const [policy, setPolicy] = useState<RLPolicy>(selectedPersona.rlPolicy);
  const [selectedAction, setSelectedAction] = useState<string>('VELVET_PAYWALL');
  const [isAutoRunning, setIsAutoRunning] = useState(false);
  const [isProcessingStep, setIsProcessingStep] = useState(false);
  const [latestStepLog, setLatestStepLog] = useState<string | null>(null);

  // Sync when selected persona changes
  useEffect(() => {
    setPolicy(selectedPersona.rlPolicy);
  }, [selectedPersona.id]);

  // Auto-run loop
  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (isAutoRunning) {
      interval = setInterval(() => {
        handleStepAction();
      }, 3500);
    }
    return () => clearInterval(interval);
  }, [isAutoRunning, policy, selectedPersona]);

  const handleStepAction = async (forcedAction?: string) => {
    const actionToTake = forcedAction || selectedAction;
    setIsProcessingStep(true);

    try {
      const result = await executeDeepRLStep({
        persona: selectedPersona,
        currentPolicy: policy,
        actionCode: actionToTake,
      });

      const updated: RLPolicy = {
        ...policy,
        epoch: result.epoch,
        epsilon: result.epsilon,
        lastReward: result.reward,
        cumulativeProfit: result.cumulativeProfit,
        history: result.updatedHistory,
      };

      setPolicy(updated);
      onUpdatePersonaPolicy(selectedPersona.id, updated);
      setLatestStepLog(result.policyInsights);
    } catch (err) {
      console.error('Error executing RL step:', err);
    } finally {
      setIsProcessingStep(false);
    }
  };

  const handleWeightChange = (key: keyof RLPolicy['rewardWeights'], value: number) => {
    const updated = {
      ...policy,
      rewardWeights: {
        ...policy.rewardWeights,
        [key]: value,
      },
    };
    setPolicy(updated);
    onUpdatePersonaPolicy(selectedPersona.id, updated);
  };

  const actions = [
    {
      code: 'MICRO_TEASE',
      name: 'Micro-Tease Breadcrumb',
      desc: 'Drops tantalizing hint or partial answer; lowers audience fatigue, spikes curiosity.',
      qValue: 84.2,
      risk: 'Low',
    },
    {
      code: 'PARASOCIAL_BOND',
      name: 'High-Stakes Parasocial Hook',
      desc: 'Deep emotional sharing or direct user mention; dramatically boosts tipping and loyalty.',
      qValue: 92.5,
      risk: 'Medium',
    },
    {
      code: 'VELVET_PAYWALL',
      name: 'Velvet Rope Paywall Trigger',
      desc: 'Forces monetization cliff for private audio/DM access; maximizes revenue yield.',
      qValue: 96.1,
      risk: 'Medium-High',
    },
    {
      code: 'ALOOF_SCARCITY',
      name: 'Aloof Scarcity Cold Shoulder',
      desc: 'Intentional withholding & unapproachable distance; reignites desperation from high-net-worth whales.',
      qValue: 89.8,
      risk: 'Medium',
    },
    {
      code: 'CROSS_BLITZ',
      name: 'Cross-Platform Blitz',
      desc: 'Directs TikTok/Reels traffic into locked VIP Discord / Fan Vault.',
      qValue: 90.4,
      risk: 'Low-Medium',
    },
  ];

  return (
    <div className="max-w-7xl mx-auto space-y-6 animate-fadeIn pb-12">
      {/* Header Deck */}
      <div className="bg-[#11131c] border border-white/10 rounded-3xl p-6 shadow-xl relative overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="px-2.5 py-0.5 rounded-full text-[10px] font-mono uppercase bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 flex items-center gap-1">
                <Cpu className="w-3 h-3" />
                DeepRL Policy Network v3.8
              </span>
              <span className="text-xs text-zinc-400">Continuous Q-Learning Bellman Convergence</span>
            </div>
            <h1 className="text-2xl font-black text-white flex items-center gap-2">
              Deep Reinforcement Learning Engine: {selectedPersona.name}
            </h1>
            <p className="text-xs text-zinc-300 mt-0.5">
              Multi-modal feedback loop aligning charisma, feminine allure, fatigue limits, and maximum profit extraction.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => setIsAutoRunning(!isAutoRunning)}
              className={`px-4 py-2.5 rounded-2xl text-xs font-semibold flex items-center gap-2 transition cursor-pointer shadow-lg ${
                isAutoRunning
                  ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40 hover:bg-rose-500/30 animate-pulse'
                  : 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 hover:bg-emerald-500/30'
              }`}
            >
              {isAutoRunning ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4 fill-current" />}
              <span>{isAutoRunning ? 'Pause Autonomous Loop' : 'Auto-Iterate Continuous RL'}</span>
            </button>

            <button
              onClick={() => handleStepAction()}
              disabled={isProcessingStep}
              className="px-4 py-2.5 rounded-2xl bg-gradient-to-r from-pink-500 to-rose-600 hover:from-pink-400 hover:to-rose-500 text-white text-xs font-semibold shadow-md shadow-pink-500/25 transition cursor-pointer flex items-center gap-2 disabled:opacity-50"
            >
              <Zap className="w-4 h-4" />
              <span>{isProcessingStep ? 'Computing...' : 'Step RL Epoch'}</span>
            </button>
          </div>
        </div>

        {/* Telemetry Status Bar */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6 pt-6 border-t border-white/10 font-mono">
          <div className="p-3 rounded-2xl bg-black/40 border border-white/5">
            <div className="text-[10px] text-zinc-500 uppercase">Policy Epoch</div>
            <div className="text-xl font-bold text-white mt-1">#{policy.epoch}</div>
            <div className="text-[10px] text-zinc-400">Total training cycles</div>
          </div>

          <div className="p-3 rounded-2xl bg-black/40 border border-white/5">
            <div className="text-[10px] text-zinc-500 uppercase">Exploration Rate (ε)</div>
            <div className="text-xl font-bold text-amber-400 mt-1">{policy.epsilon}</div>
            <div className="text-[10px] text-zinc-400">Epsilon-greedy decay</div>
          </div>

          <div className="p-3 rounded-2xl bg-black/40 border border-white/5">
            <div className="text-[10px] text-zinc-500 uppercase">Last Reward Metric (R)</div>
            <div className="text-xl font-bold text-emerald-400 mt-1">{policy.lastReward}</div>
            <div className="text-[10px] text-zinc-400">Normalized scalar (0-100)</div>
          </div>

          <div className="p-3 rounded-2xl bg-black/40 border border-white/5">
            <div className="text-[10px] text-zinc-500 uppercase">RL Cumulative Revenue</div>
            <div className="text-xl font-bold text-pink-400 mt-1">
              ${policy.cumulativeProfit.toLocaleString()}
            </div>
            <div className="text-[10px] text-zinc-400">Generated across epochs</div>
          </div>
        </div>
      </div>

      {/* Grid: Action Space & Reward Function Tuning */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 Cols: Action Space & Q-Value Matrix */}
        <div className="lg:col-span-2 space-y-6">
          <div className="bg-[#11131c] border border-white/10 rounded-3xl p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold uppercase tracking-wider text-white flex items-center gap-2">
                <Layers className="w-4 h-4 text-pink-400" />
                Action Space & Q-Value Policy Scores
              </h3>
              <span className="text-[10px] text-zinc-400 font-mono">Q(s, a) Estimation</span>
            </div>

            <div className="space-y-3">
              {actions.map((act) => {
                const isSelected = selectedAction === act.code;
                return (
                  <div
                    key={act.code}
                    onClick={() => setSelectedAction(act.code)}
                    className={`p-4 rounded-2xl border transition-all cursor-pointer flex flex-col md:flex-row md:items-center justify-between gap-4 ${
                      isSelected
                        ? 'bg-gradient-to-r from-pink-500/10 via-purple-500/10 to-[#181427] border-pink-500/50 shadow-md'
                        : 'bg-white/5 hover:bg-white/10 border-white/5'
                    }`}
                  >
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold text-white">{act.name}</span>
                        <span className="text-[10px] px-2 py-0.2 rounded font-mono bg-white/10 text-zinc-400">
                          {act.code}
                        </span>
                        <span
                          className={`text-[9px] px-1.5 py-0.2 rounded font-mono ${
                            act.risk === 'High'
                              ? 'bg-rose-500/20 text-rose-300'
                              : act.risk === 'Medium'
                              ? 'bg-amber-500/20 text-amber-300'
                              : 'bg-emerald-500/20 text-emerald-300'
                          }`}
                        >
                          Risk: {act.risk}
                        </span>
                      </div>
                      <p className="text-xs text-zinc-400">{act.desc}</p>
                    </div>

                    <div className="flex items-center gap-3 shrink-0">
                      <div className="text-right font-mono">
                        <div className="text-[10px] text-zinc-500 uppercase">Q-Score</div>
                        <div className="text-sm font-bold text-emerald-400">{act.qValue}</div>
                      </div>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleStepAction(act.code);
                        }}
                        className="px-3 py-1.5 rounded-xl bg-pink-500/20 hover:bg-pink-500 text-pink-300 hover:text-white text-xs font-semibold transition"
                      >
                        Fire
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Policy Epoch Iteration Log */}
          <div className="bg-[#11131c] border border-white/10 rounded-3xl p-6 shadow-xl space-y-4">
            <h3 className="text-sm font-bold uppercase tracking-wider text-zinc-300 flex items-center gap-2">
              <Activity className="w-4 h-4 text-emerald-400" />
              Real-Time Optimization Trajectory
            </h3>

            {latestStepLog && (
              <div className="p-3.5 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 text-xs text-emerald-300 font-mono">
                {latestStepLog}
              </div>
            )}

            <div className="overflow-x-auto">
              <table className="w-full text-left font-mono text-xs">
                <thead>
                  <tr className="border-b border-white/10 text-zinc-500 uppercase text-[10px]">
                    <th className="pb-2">Epoch</th>
                    <th className="pb-2">Action Dispatched</th>
                    <th className="pb-2">Revenue Yield</th>
                    <th className="pb-2">Sentiment</th>
                    <th className="pb-2">Reward (R)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {policy.history.map((row, i) => (
                    <tr key={i} className="hover:bg-white/5">
                      <td className="py-2.5 text-zinc-400">#{row.epoch}</td>
                      <td className="py-2.5 text-pink-300">{row.actionTaken}</td>
                      <td className="py-2.5 text-emerald-400 font-bold">+${row.revenue.toLocaleString()}</td>
                      <td className="py-2.5 text-purple-300">{row.sentiment}</td>
                      <td className="py-2.5 text-amber-400 font-bold">{row.reward}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Right Col: Bellman Reward Function Calibrator */}
        <div className="space-y-6">
          <div className="bg-[#11131c] border border-white/10 rounded-3xl p-6 shadow-xl space-y-5">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold uppercase tracking-wider text-white flex items-center gap-2">
                <Sliders className="w-4 h-4 text-amber-400" />
                Reward Function Weights
              </h3>
            </div>

            <div className="p-3 rounded-2xl bg-black/40 border border-white/5 font-mono text-xs text-zinc-300">
              <span className="text-pink-400">R</span> = <span className="text-emerald-400">α</span>·Rev +{' '}
              <span className="text-pink-300">β</span>·Eng - <span className="text-rose-400">γ</span>·Fatigue +{' '}
              <span className="text-amber-400">δ</span>·Retention
            </div>

            <div className="space-y-4">
              {/* Alpha Revenue */}
              <div className="space-y-1.5">
                <div className="flex justify-between text-xs">
                  <span className="text-zinc-300 font-medium">Revenue Weight (α)</span>
                  <span className="text-emerald-400 font-mono font-bold">
                    {policy.rewardWeights.revenueWeight.toFixed(2)}
                  </span>
                </div>
                <input
                  type="range"
                  min="0.1"
                  max="1.0"
                  step="0.05"
                  value={policy.rewardWeights.revenueWeight}
                  onChange={(e) => handleWeightChange('revenueWeight', Number(e.target.value))}
                  className="w-full accent-emerald-500 cursor-pointer"
                />
                <p className="text-[10px] text-zinc-500">Emphasis on direct tip and subscription extraction.</p>
              </div>

              {/* Beta Engagement */}
              <div className="space-y-1.5">
                <div className="flex justify-between text-xs">
                  <span className="text-zinc-300 font-medium">Engagement & Sentiment (β)</span>
                  <span className="text-pink-400 font-mono font-bold">
                    {policy.rewardWeights.engagementWeight.toFixed(2)}
                  </span>
                </div>
                <input
                  type="range"
                  min="0.1"
                  max="1.0"
                  step="0.05"
                  value={policy.rewardWeights.engagementWeight}
                  onChange={(e) => handleWeightChange('engagementWeight', Number(e.target.value))}
                  className="w-full accent-pink-500 cursor-pointer"
                />
                <p className="text-[10px] text-zinc-500">Protects comment velocity and viral resonance.</p>
              </div>

              {/* Gamma Fatigue */}
              <div className="space-y-1.5">
                <div className="flex justify-between text-xs">
                  <span className="text-zinc-300 font-medium">Audience Fatigue Penalty (γ)</span>
                  <span className="text-rose-400 font-mono font-bold">
                    {policy.rewardWeights.fatiguePenalty.toFixed(2)}
                  </span>
                </div>
                <input
                  type="range"
                  min="0.05"
                  max="0.5"
                  step="0.05"
                  value={policy.rewardWeights.fatiguePenalty}
                  onChange={(e) => handleWeightChange('fatiguePenalty', Number(e.target.value))}
                  className="w-full accent-rose-500 cursor-pointer"
                />
                <p className="text-[10px] text-zinc-500">Penalizes aggressive spamming of paywalls.</p>
              </div>

              {/* Delta Retention */}
              <div className="space-y-1.5">
                <div className="flex justify-between text-xs">
                  <span className="text-zinc-300 font-medium">Whale Retention Bonus (δ)</span>
                  <span className="text-amber-400 font-mono font-bold">
                    {policy.rewardWeights.retentionBonus.toFixed(2)}
                  </span>
                </div>
                <input
                  type="range"
                  min="0.1"
                  max="0.8"
                  step="0.05"
                  value={policy.rewardWeights.retentionBonus}
                  onChange={(e) => handleWeightChange('retentionBonus', Number(e.target.value))}
                  className="w-full accent-amber-500 cursor-pointer"
                />
                <p className="text-[10px] text-zinc-500">Rewards long-term sub renewal and zero churn.</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
