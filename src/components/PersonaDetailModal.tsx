import React, { useState } from 'react';
import {
  X,
  Volume2,
  Sliders,
  DollarSign,
  TrendingUp,
  Cpu,
  ShieldAlert,
  Sparkles,
  Lock,
  Heart,
  Flame,
  CheckCircle2,
  RefreshCw,
  Zap,
} from 'lucide-react';
import { InfluencerPersona } from '../types';
import { playTtsVoice } from '../services/api';

interface PersonaDetailModalProps {
  persona: InfluencerPersona;
  onClose: () => void;
  onUpdatePersona: (updated: InfluencerPersona) => void;
  onStartCYOA: () => void;
}

export const PersonaDetailModal: React.FC<PersonaDetailModalProps> = ({
  persona,
  onClose,
  onUpdatePersona,
  onStartCYOA,
}) => {
  const [activeSubTab, setActiveSubTab] = useState<'profile' | 'wiles' | 'monetization' | 'rl'>('profile');
  const [isPlayingTts, setIsPlayingTts] = useState(false);
  const [ttsInput, setTtsInput] = useState(persona.voice.sampleText);

  // Editable copy of wiles
  const [wiles, setWiles] = useState(persona.wiles);

  const handleSaveWiles = () => {
    onUpdatePersona({
      ...persona,
      wiles,
    });
  };

  const handleTestTts = async () => {
    setIsPlayingTts(true);
    try {
      await playTtsVoice(ttsInput, persona.voice.voiceName);
    } finally {
      setTimeout(() => setIsPlayingTts(false), 2000);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fadeIn">
      <div className="relative w-full max-w-4xl max-h-[90vh] bg-[#0f111a] border border-white/10 rounded-3xl overflow-hidden shadow-2xl flex flex-col text-white">
        {/* Header Bar */}
        <div className="relative h-44 w-full overflow-hidden shrink-0">
          <img
            src={persona.bannerUrl}
            alt={persona.name}
            className="w-full h-full object-cover"
          />
          <div className="absolute inset-0 bg-gradient-to-t from-[#0f111a] via-[#0f111a]/70 to-transparent" />

          {/* Close button */}
          <button
            onClick={onClose}
            className="absolute top-4 right-4 p-2 rounded-full bg-black/60 hover:bg-black/90 text-white/80 hover:text-white transition cursor-pointer border border-white/10"
          >
            <X className="w-5 h-5" />
          </button>

          {/* Persona Header Info */}
          <div className="absolute bottom-4 left-6 flex items-end gap-4">
            <img
              src={persona.avatarUrl}
              alt={persona.name}
              className="w-20 h-20 rounded-2xl object-cover border-2 border-pink-500/50 shadow-xl"
            />
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-2xl font-black">{persona.name}</h2>
                <span className="px-2.5 py-0.5 rounded-full text-xs font-mono uppercase bg-pink-500/20 text-pink-300 border border-pink-500/30">
                  {persona.spiceArchetype}
                </span>
                <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 font-mono">
                  ${(persona.mrr / 1000).toFixed(0)}k MRR
                </span>
              </div>
              <p className="text-xs text-zinc-400">{persona.epithet}</p>
            </div>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="flex items-center gap-2 px-6 pt-3 border-b border-white/10 bg-[#0c0d14] text-xs font-medium">
          <button
            onClick={() => setActiveSubTab('profile')}
            className={`pb-3 px-3 border-b-2 transition cursor-pointer ${
              activeSubTab === 'profile'
                ? 'border-pink-500 text-pink-300 font-semibold'
                : 'border-transparent text-zinc-400 hover:text-zinc-200'
            }`}
          >
            Dense Psych Profile
          </button>
          <button
            onClick={() => setActiveSubTab('wiles')}
            className={`pb-3 px-3 border-b-2 transition cursor-pointer ${
              activeSubTab === 'wiles'
                ? 'border-pink-500 text-pink-300 font-semibold'
                : 'border-transparent text-zinc-400 hover:text-zinc-200'
            }`}
          >
            Feminine Wiles & Allure Matrix
          </button>
          <button
            onClick={() => setActiveSubTab('monetization')}
            className={`pb-3 px-3 border-b-2 transition cursor-pointer ${
              activeSubTab === 'monetization'
                ? 'border-pink-500 text-pink-300 font-semibold'
                : 'border-transparent text-zinc-400 hover:text-zinc-200'
            }`}
          >
            Monetization & VIP Tiers
          </button>
          <button
            onClick={() => setActiveSubTab('rl')}
            className={`pb-3 px-3 border-b-2 transition cursor-pointer ${
              activeSubTab === 'rl'
                ? 'border-pink-500 text-pink-300 font-semibold'
                : 'border-transparent text-zinc-400 hover:text-zinc-200'
            }`}
          >
            DeepRL Policy Weights
          </button>
        </div>

        {/* Modal Scrollable Body */}
        <div className="p-6 overflow-y-auto flex-1 space-y-6">
          {activeSubTab === 'profile' && (
            <div className="space-y-6">
              {/* Bio & Tagline */}
              <div className="p-4 rounded-2xl bg-white/5 border border-white/10">
                <h4 className="text-xs uppercase font-mono tracking-wider text-pink-400 mb-2">
                  Autonomous Identity & Narrative
                </h4>
                <p className="text-sm text-zinc-200 leading-relaxed mb-3">{persona.bio}</p>
                <div className="p-2.5 rounded-xl bg-black/40 border border-white/5 italic text-xs text-zinc-300">
                  Tagline: "{persona.tagline}"
                </div>
              </div>

              {/* Secret Backstory & Demographic */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-4 rounded-2xl bg-purple-500/5 border border-purple-500/20">
                  <h4 className="text-xs uppercase font-mono tracking-wider text-purple-300 mb-2 flex items-center gap-1.5">
                    <ShieldAlert className="w-3.5 h-3.5" />
                    Classified Backstory
                  </h4>
                  <p className="text-xs text-zinc-300 leading-relaxed">{persona.secretBackstory}</p>
                </div>

                <div className="p-4 rounded-2xl bg-amber-500/5 border border-amber-500/20">
                  <h4 className="text-xs uppercase font-mono tracking-wider text-amber-300 mb-2">
                    Target High-Ticket Audience
                  </h4>
                  <p className="text-xs text-zinc-300 leading-relaxed">{persona.targetDemographic}</p>
                </div>
              </div>

              {/* Voice Synthesis Playground */}
              <div className="p-4 rounded-2xl bg-gradient-to-br from-rose-500/10 to-pink-500/5 border border-rose-500/20">
                <div className="flex items-center justify-between mb-3">
                  <h4 className="text-xs uppercase font-mono tracking-wider text-rose-300 flex items-center gap-1.5">
                    <Volume2 className="w-3.5 h-3.5" />
                    Gemini TTS Voice Persona ({persona.voice.voiceName})
                  </h4>
                  <span className="text-[10px] text-zinc-400 font-mono">
                    Cadence: {persona.voice.cadence}
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  <input
                    type="text"
                    value={ttsInput}
                    onChange={(e) => setTtsInput(e.target.value)}
                    className="flex-1 px-3 py-2 rounded-xl bg-black/50 border border-white/10 text-xs text-white focus:outline-none focus:border-pink-500"
                    placeholder="Enter dialogue to speak..."
                  />
                  <button
                    onClick={handleTestTts}
                    disabled={isPlayingTts}
                    className="px-4 py-2 rounded-xl bg-gradient-to-r from-pink-500 to-rose-600 hover:from-pink-400 hover:to-rose-500 text-white text-xs font-semibold flex items-center gap-1.5 transition cursor-pointer disabled:opacity-50"
                  >
                    <Volume2 className={`w-3.5 h-3.5 ${isPlayingTts ? 'animate-bounce' : ''}`} />
                    <span>{isPlayingTts ? 'Synthesizing...' : 'Speak'}</span>
                  </button>
                </div>
              </div>

              {/* Viral Hooks */}
              <div className="p-4 rounded-2xl bg-white/5 border border-white/10">
                <h4 className="text-xs uppercase font-mono tracking-wider text-zinc-400 mb-3">
                  Automated Viral Hooks
                </h4>
                <div className="space-y-2">
                  {persona.viralHooks.map((hook, i) => (
                    <div
                      key={i}
                      className="px-3 py-2 rounded-xl bg-black/40 border border-white/5 text-xs text-zinc-200 flex items-center gap-2"
                    >
                      <Sparkles className="w-3.5 h-3.5 text-pink-400 shrink-0" />
                      <span>{hook}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {activeSubTab === 'wiles' && (
            <div className="space-y-6">
              <div className="p-4 rounded-2xl bg-white/5 border border-white/10">
                <h4 className="text-xs uppercase font-mono tracking-wider text-pink-400 mb-1">
                  Feminine Wiles & Allure Orchestrator
                </h4>
                <p className="text-xs text-zinc-400 mb-4">
                  Adjust her psychological allure sliders to calibrate how she manages boundary-pushing, romantic suspense, and conversion pressure.
                </p>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {/* Allure Index */}
                  <div className="space-y-1.5">
                    <div className="flex justify-between text-xs">
                      <span className="text-zinc-300 font-medium">Raw Magnetic Allure</span>
                      <span className="text-pink-400 font-mono font-bold">{wiles.allureIndex}%</span>
                    </div>
                    <input
                      type="range"
                      min="50"
                      max="100"
                      value={wiles.allureIndex}
                      onChange={(e) => setWiles({ ...wiles, allureIndex: Number(e.target.value) })}
                      className="w-full accent-pink-500 cursor-pointer"
                    />
                    <p className="text-[10px] text-zinc-500">Unfiltered charisma and visual fascination.</p>
                  </div>

                  {/* Mystery / Aloofness */}
                  <div className="space-y-1.5">
                    <div className="flex justify-between text-xs">
                      <span className="text-zinc-300 font-medium">Mystery & Scarcity (Aloofness)</span>
                      <span className="text-purple-400 font-mono font-bold">{wiles.mysteryQuotient}%</span>
                    </div>
                    <input
                      type="range"
                      min="30"
                      max="100"
                      value={wiles.mysteryQuotient}
                      onChange={(e) => setWiles({ ...wiles, mysteryQuotient: Number(e.target.value) })}
                      className="w-full accent-purple-500 cursor-pointer"
                    />
                    <p className="text-[10px] text-zinc-500">Withholding information to increase perceived value.</p>
                  </div>

                  {/* Playful Tease */}
                  <div className="space-y-1.5">
                    <div className="flex justify-between text-xs">
                      <span className="text-zinc-300 font-medium">Playful Tease & Banter</span>
                      <span className="text-amber-400 font-mono font-bold">{wiles.playfulTease}%</span>
                    </div>
                    <input
                      type="range"
                      min="40"
                      max="100"
                      value={wiles.playfulTease}
                      onChange={(e) => setWiles({ ...wiles, playfulTease: Number(e.target.value) })}
                      className="w-full accent-amber-500 cursor-pointer"
                    />
                    <p className="text-[10px] text-zinc-500">Flirtatious verbal sparring and daring games.</p>
                  </div>

                  {/* Emotional Vulnerability */}
                  <div className="space-y-1.5">
                    <div className="flex justify-between text-xs">
                      <span className="text-zinc-300 font-medium">Weaponized Intimacy (Vulnerability)</span>
                      <span className="text-rose-400 font-mono font-bold">{wiles.emotionalVulnerability}%</span>
                    </div>
                    <input
                      type="range"
                      min="20"
                      max="100"
                      value={wiles.emotionalVulnerability}
                      onChange={(e) => setWiles({ ...wiles, emotionalVulnerability: Number(e.target.value) })}
                      className="w-full accent-rose-500 cursor-pointer"
                    />
                    <p className="text-[10px] text-zinc-500">Selective emotional sharing to hook whale patrons.</p>
                  </div>

                  {/* Dominance vs Sweetness */}
                  <div className="space-y-1.5">
                    <div className="flex justify-between text-xs">
                      <span className="text-zinc-300 font-medium">Dominance vs Angelcore Sweetness</span>
                      <span className="text-cyan-400 font-mono font-bold">{wiles.dominanceVsSweetness}%</span>
                    </div>
                    <input
                      type="range"
                      min="10"
                      max="100"
                      value={wiles.dominanceVsSweetness}
                      onChange={(e) => setWiles({ ...wiles, dominanceVsSweetness: Number(e.target.value) })}
                      className="w-full accent-cyan-500 cursor-pointer"
                    />
                    <p className="text-[10px] text-zinc-500">Low = innocent soft coquette; High = alpha commanding queen.</p>
                  </div>

                  {/* Paywall Conversion Propensity */}
                  <div className="space-y-1.5">
                    <div className="flex justify-between text-xs">
                      <span className="text-zinc-300 font-medium">Paywall Conversion Aggressiveness</span>
                      <span className="text-emerald-400 font-mono font-bold">{wiles.paywallConversionRate}%</span>
                    </div>
                    <input
                      type="range"
                      min="50"
                      max="100"
                      value={wiles.paywallConversionRate}
                      onChange={(e) => setWiles({ ...wiles, paywallConversionRate: Number(e.target.value) })}
                      className="w-full accent-emerald-500 cursor-pointer"
                    />
                    <p className="text-[10px] text-zinc-500">Frequency and psychological pull of monetization prompts.</p>
                  </div>
                </div>

                <div className="mt-6 flex justify-end">
                  <button
                    onClick={handleSaveWiles}
                    className="px-4 py-2 rounded-xl bg-pink-500 hover:bg-pink-400 text-white text-xs font-semibold shadow-lg shadow-pink-500/25 transition cursor-pointer"
                  >
                    Apply Wiles Calibration
                  </button>
                </div>
              </div>
            </div>
          )}

          {activeSubTab === 'monetization' && (
            <div className="space-y-6">
              {/* Tiers List */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {persona.monetizationTiers.map((tier) => (
                  <div
                    key={tier.id}
                    className={`p-4 rounded-2xl border flex flex-col justify-between ${
                      tier.highlight
                        ? 'bg-gradient-to-b from-pink-500/10 to-[#121422] border-pink-500/50 shadow-lg shadow-pink-500/10'
                        : 'bg-white/5 border-white/10'
                    }`}
                  >
                    <div>
                      {tier.highlight && (
                        <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-pink-500 text-white font-bold mb-2 inline-block">
                          Top Tier Performer
                        </span>
                      )}
                      <h4 className="text-base font-bold text-white mb-1">{tier.name}</h4>
                      <div className="text-xl font-black text-pink-400 font-mono mb-3">
                        ${tier.pricePerMonth}
                        <span className="text-xs text-zinc-400 font-normal">/mo</span>
                      </div>

                      <div className="space-y-1.5 mb-4">
                        {tier.perks.map((perk, i) => (
                          <div key={i} className="flex items-start gap-1.5 text-xs text-zinc-300">
                            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-0.5" />
                            <span>{perk}</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="pt-3 border-t border-white/10 text-xs text-zinc-400 flex justify-between font-mono">
                      <span>{tier.subscriberCount.toLocaleString()} subs</span>
                      <span className="text-emerald-400 font-bold">
                        ${(tier.pricePerMonth * tier.subscriberCount).toLocaleString()}/mo
                      </span>
                    </div>
                  </div>
                ))}
              </div>

              {/* Paywall Hooks */}
              <div className="p-4 rounded-2xl bg-white/5 border border-white/10">
                <h4 className="text-xs uppercase font-mono tracking-wider text-amber-400 mb-3 flex items-center gap-1.5">
                  <Lock className="w-3.5 h-3.5" />
                  Active Velvet Rope Paywall Triggers
                </h4>
                <div className="space-y-2">
                  {persona.paywallHooks.map((phook, i) => (
                    <div
                      key={i}
                      className="px-3 py-2 rounded-xl bg-amber-500/5 border border-amber-500/20 text-xs text-amber-200 flex items-center justify-between"
                    >
                      <span>{phook}</span>
                      <span className="text-[10px] font-mono text-amber-400/80 px-2 py-0.5 rounded bg-amber-500/20">
                        High Conversion
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {activeSubTab === 'rl' && (
            <div className="space-y-6">
              <div className="p-4 rounded-2xl bg-white/5 border border-white/10">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <h4 className="text-xs uppercase font-mono tracking-wider text-emerald-400 flex items-center gap-1.5">
                      <Cpu className="w-3.5 h-3.5" />
                      DeepRL Bellman Policy Status (Epoch {persona.rlPolicy.epoch})
                    </h4>
                    <p className="text-xs text-zinc-400">
                      Optimizing Q-matrix for maximum lifetime value (LTV) and minimum audience fatigue.
                    </p>
                  </div>
                  <span className="px-3 py-1 rounded-lg bg-emerald-500/20 text-emerald-300 font-mono text-xs border border-emerald-500/30">
                    Reward: {persona.rlPolicy.lastReward}
                  </span>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6 font-mono text-center">
                  <div className="p-3 rounded-xl bg-black/40 border border-white/5">
                    <div className="text-[10px] text-zinc-500">Revenue Weight (α)</div>
                    <div className="text-sm font-bold text-emerald-400">
                      {persona.rlPolicy.rewardWeights.revenueWeight}
                    </div>
                  </div>
                  <div className="p-3 rounded-xl bg-black/40 border border-white/5">
                    <div className="text-[10px] text-zinc-500">Engagement Weight (β)</div>
                    <div className="text-sm font-bold text-pink-400">
                      {persona.rlPolicy.rewardWeights.engagementWeight}
                    </div>
                  </div>
                  <div className="p-3 rounded-xl bg-black/40 border border-white/5">
                    <div className="text-[10px] text-zinc-500">Fatigue Penalty (γ)</div>
                    <div className="text-sm font-bold text-rose-400">
                      {persona.rlPolicy.rewardWeights.fatiguePenalty}
                    </div>
                  </div>
                  <div className="p-3 rounded-xl bg-black/40 border border-white/5">
                    <div className="text-[10px] text-zinc-500">Retention Bonus (δ)</div>
                    <div className="text-sm font-bold text-amber-400">
                      {persona.rlPolicy.rewardWeights.retentionBonus}
                    </div>
                  </div>
                </div>

                <h5 className="text-xs font-semibold uppercase text-zinc-400 mb-2">
                  Recent Policy Iteration History
                </h5>
                <div className="space-y-1.5 font-mono text-xs">
                  {persona.rlPolicy.history.map((hist, i) => (
                    <div
                      key={i}
                      className="p-2 rounded-lg bg-black/30 border border-white/5 flex items-center justify-between text-zinc-300"
                    >
                      <span className="text-zinc-500">Ep.{hist.epoch}</span>
                      <span className="text-pink-400">{hist.actionTaken}</span>
                      <span className="text-emerald-400">+${hist.revenue}</span>
                      <span className="text-amber-400">R: {hist.reward}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="px-6 py-4 border-t border-white/10 bg-[#0a0b12] flex items-center justify-between">
          <span className="text-xs text-zinc-400 font-mono">
            ID: {persona.id} • Status: {persona.status.toUpperCase()}
          </span>

          <div className="flex items-center gap-3">
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-xl bg-white/5 hover:bg-white/10 text-zinc-300 text-xs font-medium transition cursor-pointer"
            >
              Close
            </button>
            <button
              onClick={() => {
                onClose();
                onStartCYOA();
              }}
              className="px-5 py-2 rounded-xl bg-gradient-to-r from-pink-500 to-rose-600 hover:from-pink-400 hover:to-rose-500 text-white text-xs font-semibold shadow-lg shadow-pink-500/25 transition cursor-pointer flex items-center gap-1.5"
            >
              <Flame className="w-3.5 h-3.5 fill-current" />
              <span>Launch CYOA Story Mode</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
