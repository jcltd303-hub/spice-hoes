import React from 'react';
import {
  Sparkles,
  Zap,
  TrendingUp,
  DollarSign,
  Cpu,
  Layers,
  Flame,
  Radio,
  Share2,
  PlusCircle,
  Coins,
} from 'lucide-react';
import { InfluencerPersona } from '../types';

interface HeaderProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  personas: InfluencerPersona[];
  selectedPersona: InfluencerPersona;
  setSelectedPersona: (p: InfluencerPersona) => void;
  userCredits: number;
  setUserCredits: React.Dispatch<React.SetStateAction<number>>;
  onOpenCreateModal: () => void;
  onOpenApiModal: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  activeTab,
  setActiveTab,
  personas,
  selectedPersona,
  setSelectedPersona,
  userCredits,
  setUserCredits,
  onOpenCreateModal,
  onOpenApiModal,
}) => {
  const totalMrr = personas.reduce((acc, p) => acc + p.mrr, 0);

  const tabs = [
    { id: 'roster', label: 'The Quintet', icon: Sparkles },
    { id: 'cyoa', label: 'CYOA Story Studio', icon: Flame, badge: 'Live AI' },
    { id: 'deeprl', label: 'DeepRL Policy Engine', icon: Cpu },
    { id: 'moa', label: 'MoA Multi-Model Agent', icon: Layers },
    { id: 'trends', label: 'Trend Scout Radar', icon: Radio },
    { id: 'channels', label: 'Multi-Channel Vault', icon: Share2 },
  ];

  return (
    <header className="sticky top-0 z-40 bg-[#0d0f17]/90 backdrop-blur-xl border-b border-white/10 text-white">
      {/* Top Banner / Ticker */}
      <div className="px-4 py-2 border-b border-white/5 flex flex-wrap items-center justify-between gap-4 text-xs">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 font-mono font-medium">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            DEEPRL POLICY LOOP ACTIVE (v3.8)
          </div>
          <div className="hidden md:flex items-center gap-2 text-zinc-400">
            <span>MoA Consensus:</span>
            <span className="text-zinc-200 font-mono font-semibold">96.4%</span>
            <span className="text-zinc-600">|</span>
            <span>RL Exploration Rate (ε):</span>
            <span className="text-amber-400 font-mono font-semibold">0.11</span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* User SpiceCredits */}
          <div className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-300 font-mono">
            <Coins className="w-3.5 h-3.5 text-amber-400" />
            <span className="font-bold">{userCredits}</span>
            <span className="text-amber-400/80 text-[10px]">SpiceCredits</span>
            <button
              onClick={() => setUserCredits((c) => c + 100)}
              className="ml-1 text-[10px] bg-amber-500/20 hover:bg-amber-500/40 text-amber-200 px-1.5 py-0.5 rounded cursor-pointer transition"
              title="Add 100 test credits"
            >
              +100
            </button>
          </div>

          {/* Aggregate Network MRR */}
          <div className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-pink-500/10 border border-pink-500/20 text-pink-300 font-mono">
            <DollarSign className="w-3.5 h-3.5 text-pink-400" />
            <span className="font-bold text-sm">${totalMrr.toLocaleString()}</span>
            <span className="text-zinc-400 text-[10px]">/mo Network ARR $10.3M</span>
          </div>

          {/* Quick API Modal */}
          <button
            onClick={onOpenApiModal}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-white/5 hover:bg-white/10 text-zinc-300 text-xs border border-white/10 cursor-pointer transition"
          >
            <Cpu className="w-3 h-3 text-cyan-400" />
            <span>REST API</span>
          </button>
        </div>
      </div>

      {/* Main Nav */}
      <div className="max-w-7xl mx-auto px-4 py-3 flex flex-wrap items-center justify-between gap-4">
        {/* Brand */}
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-pink-600 via-rose-500 to-amber-400 flex items-center justify-center shadow-lg shadow-pink-500/25 border border-pink-400/30">
            <Sparkles className="w-5 h-5 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xl font-black tracking-tight bg-gradient-to-r from-pink-400 via-rose-300 to-amber-200 bg-clip-text text-transparent">
                SPICECORE
              </span>
              <span className="px-1.5 py-0.5 text-[10px] uppercase font-mono tracking-widest bg-pink-500/20 text-pink-300 border border-pink-500/30 rounded">
                AI Studio
              </span>
            </div>
            <p className="text-[11px] text-zinc-400">Autonomous Influencer & DeepRL Monetization Engine</p>
          </div>
        </div>

        {/* Navigation Tabs */}
        <nav className="flex items-center gap-1 overflow-x-auto py-1">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-medium transition cursor-pointer relative whitespace-nowrap ${
                  isActive
                    ? 'bg-gradient-to-r from-pink-500/20 to-rose-500/20 text-white border border-pink-500/40 shadow-sm'
                    : 'text-zinc-400 hover:text-zinc-200 hover:bg-white/5 border border-transparent'
                }`}
              >
                <Icon className={`w-4 h-4 ${isActive ? 'text-pink-400' : 'text-zinc-400'}`} />
                <span>{tab.label}</span>
                {tab.badge && (
                  <span className="px-1.5 py-0.2 rounded-full text-[9px] bg-rose-500/30 text-rose-300 font-mono">
                    {tab.badge}
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        {/* Action Button: Create New Persona */}
        <div className="flex items-center gap-2">
          <button
            onClick={onOpenCreateModal}
            className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-gradient-to-r from-pink-500 to-rose-600 hover:from-pink-400 hover:to-rose-500 text-white text-xs font-semibold shadow-md shadow-pink-500/25 transition cursor-pointer active:scale-95"
          >
            <PlusCircle className="w-4 h-4" />
            <span>Synthesize Persona</span>
          </button>
        </div>
      </div>

      {/* Persona Quick Switcher Bar */}
      <div className="bg-[#08090f] border-t border-white/5 px-4 py-2">
        <div className="max-w-7xl mx-auto flex items-center justify-between gap-4 overflow-x-auto">
          <div className="flex items-center gap-2 text-xs text-zinc-400 shrink-0">
            <span className="font-mono text-[10px] uppercase text-zinc-500">Active Persona:</span>
          </div>

          <div className="flex items-center gap-2 overflow-x-auto py-0.5">
            {personas.map((p) => {
              const isSelected = p.id === selectedPersona.id;
              return (
                <button
                  key={p.id}
                  onClick={() => setSelectedPersona(p)}
                  className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs transition cursor-pointer border shrink-0 ${
                    isSelected
                      ? 'bg-white/10 border-pink-500/50 text-white shadow-sm'
                      : 'bg-white/5 border-white/5 text-zinc-400 hover:text-zinc-200 hover:border-white/10'
                  }`}
                >
                  <img
                    src={p.avatarUrl}
                    alt={p.name}
                    className="w-5 h-5 rounded-full object-cover border border-white/20"
                  />
                  <span className="font-medium">{p.name}</span>
                  <span className="text-[10px] px-1 rounded bg-black/40 text-pink-400 font-mono">
                    {p.spiceArchetype}
                  </span>
                  <span className="text-[10px] text-emerald-400 font-mono">
                    ${(p.mrr / 1000).toFixed(0)}k/mo
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </header>
  );
};
