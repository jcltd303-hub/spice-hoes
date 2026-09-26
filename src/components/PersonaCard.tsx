import React, { useState } from 'react';
import {
  Flame,
  Volume2,
  DollarSign,
  TrendingUp,
  Cpu,
  Layers,
  Sparkles,
  Play,
  Heart,
  Eye,
  Crown,
  Lock,
} from 'lucide-react';
import { InfluencerPersona } from '../types';
import { playTtsVoice } from '../services/api';

interface PersonaCardProps {
  persona: InfluencerPersona;
  isSelected: boolean;
  onSelect: () => void;
  onOpenDetails: () => void;
  onStartCYOA: () => void;
}

export const PersonaCard: React.FC<PersonaCardProps> = ({
  persona,
  isSelected,
  onSelect,
  onOpenDetails,
  onStartCYOA,
}) => {
  const [isPlayingVoice, setIsPlayingVoice] = useState(false);

  const handleVoicePreview = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsPlayingVoice(true);
    try {
      await playTtsVoice(persona.voice.sampleText, persona.voice.voiceName);
    } finally {
      setTimeout(() => setIsPlayingVoice(false), 2500);
    }
  };

  const getArchetypeColor = (type: string) => {
    switch (type) {
      case 'Sporty':
        return 'from-emerald-500/20 to-teal-500/20 text-emerald-300 border-emerald-500/40';
      case 'Posh':
        return 'from-slate-400/20 to-zinc-200/20 text-slate-200 border-slate-400/40';
      case 'Ginger':
        return 'from-amber-500/20 to-rose-600/20 text-rose-300 border-rose-500/40';
      case 'Scary':
        return 'from-purple-600/20 to-fuchsia-600/20 text-purple-300 border-purple-500/40';
      case 'Baby':
        return 'from-pink-400/20 to-rose-300/20 text-pink-300 border-pink-400/40';
      default:
        return 'from-pink-500/20 to-violet-500/20 text-pink-300 border-pink-500/40';
    }
  };

  return (
    <div
      onClick={onSelect}
      className={`group relative rounded-2xl overflow-hidden bg-[#11131c] border transition-all duration-300 cursor-pointer flex flex-col justify-between ${
        isSelected
          ? 'border-pink-500/70 shadow-2xl shadow-pink-500/20 scale-[1.01]'
          : 'border-white/10 hover:border-white/20 hover:shadow-xl hover:shadow-black/40'
      }`}
    >
      {/* Top Banner & Avatar */}
      <div className="relative h-44 w-full overflow-hidden">
        <img
          src={persona.bannerUrl}
          alt={persona.name}
          className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-[#11131c] via-[#11131c]/60 to-transparent" />

        {/* Top badges */}
        <div className="absolute top-3 left-3 flex items-center gap-2">
          <span
            className={`px-2.5 py-1 rounded-full text-[11px] font-mono font-bold tracking-wide uppercase border backdrop-blur-md bg-gradient-to-r ${getArchetypeColor(
              persona.spiceArchetype
            )}`}
          >
            {persona.spiceArchetype} Archetype
          </span>
          <span className="px-2 py-0.5 rounded-full text-[10px] bg-black/60 backdrop-blur-md text-emerald-400 border border-emerald-500/30 font-mono">
            RL Ep.{persona.rlPolicy.epoch}
          </span>
        </div>

        {/* Voice Play Button */}
        <button
          onClick={handleVoicePreview}
          className={`absolute top-3 right-3 p-2 rounded-xl backdrop-blur-md transition-all cursor-pointer ${
            isPlayingVoice
              ? 'bg-rose-500 text-white animate-pulse'
              : 'bg-black/60 hover:bg-black/80 text-white/90 border border-white/20 hover:scale-105'
          }`}
          title="Play voice preview (Gemini TTS)"
        >
          <Volume2 className="w-4 h-4" />
        </button>

        {/* Avatar positioned over banner */}
        <div className="absolute bottom-2 left-4 flex items-end gap-3">
          <div className="relative">
            <img
              src={persona.avatarUrl}
              alt={persona.name}
              className="w-16 h-16 rounded-xl object-cover border-2 border-white/20 shadow-lg"
            />
            <div className="absolute -bottom-1 -right-1 w-4 h-4 rounded-full bg-emerald-500 border-2 border-[#11131c]" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-white leading-tight flex items-center gap-1.5">
              {persona.name}
              <Crown className="w-3.5 h-3.5 text-amber-400" />
            </h3>
            <p className="text-xs text-pink-400 font-mono">{persona.handle}</p>
          </div>
        </div>
      </div>

      {/* Body Content */}
      <div className="p-4 flex-1 flex flex-col justify-between">
        <div>
          {/* Epithet & Tagline */}
          <div className="mb-3">
            <div className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400 mb-1">
              {persona.epithet}
            </div>
            <p className="text-xs italic text-zinc-300 bg-white/5 p-2 rounded-lg border border-white/5">
              "{persona.tagline}"
            </p>
          </div>

          {/* Aesthetic Hashtags */}
          <div className="flex flex-wrap gap-1 mb-4">
            {persona.aestheticTokens.slice(0, 3).map((token) => (
              <span
                key={token}
                className="text-[10px] px-2 py-0.5 rounded bg-white/5 text-zinc-400 font-mono"
              >
                {token}
              </span>
            ))}
          </div>

          {/* Key Metrics Grid */}
          <div className="grid grid-cols-3 gap-2 mb-4 p-2.5 rounded-xl bg-black/40 border border-white/5 text-center">
            <div>
              <div className="text-[10px] text-zinc-500 uppercase font-mono">Monthly Rev</div>
              <div className="text-sm font-bold text-emerald-400 font-mono">
                ${(persona.mrr / 1000).toFixed(0)}k
              </div>
            </div>
            <div>
              <div className="text-[10px] text-zinc-500 uppercase font-mono">Allure / Wiles</div>
              <div className="text-sm font-bold text-pink-400 font-mono">
                {persona.wiles.allureIndex}%
              </div>
            </div>
            <div>
              <div className="text-[10px] text-zinc-500 uppercase font-mono">Conversion</div>
              <div className="text-sm font-bold text-amber-400 font-mono">
                {persona.wiles.paywallConversionRate}%
              </div>
            </div>
          </div>

          {/* Feminine Wiles Radar Snapshot */}
          <div className="space-y-1.5 mb-4">
            <div className="flex justify-between text-[11px]">
              <span className="text-zinc-400">Playful Tease</span>
              <span className="text-rose-300 font-mono">{persona.wiles.playfulTease}%</span>
            </div>
            <div className="h-1.5 w-full bg-white/10 rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-pink-500 to-rose-400 rounded-full"
                style={{ width: `${persona.wiles.playfulTease}%` }}
              />
            </div>

            <div className="flex justify-between text-[11px] pt-1">
              <span className="text-zinc-400">Scarcity & Mystery</span>
              <span className="text-purple-300 font-mono">{persona.wiles.mysteryQuotient}%</span>
            </div>
            <div className="h-1.5 w-full bg-white/10 rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-purple-500 to-violet-400 rounded-full"
                style={{ width: `${persona.wiles.mysteryQuotient}%` }}
              />
            </div>
          </div>
        </div>

        {/* Card Actions */}
        <div className="pt-2 border-t border-white/10 flex items-center gap-2">
          <button
            onClick={(e) => {
              e.stopPropagation();
              onStartCYOA();
            }}
            className="flex-1 py-2 px-3 rounded-xl bg-gradient-to-r from-pink-500 to-rose-600 hover:from-pink-400 hover:to-rose-500 text-white text-xs font-semibold flex items-center justify-center gap-1.5 transition cursor-pointer shadow-md shadow-pink-500/20 active:scale-95"
          >
            <Play className="w-3.5 h-3.5 fill-current" />
            <span>Launch CYOA</span>
          </button>

          <button
            onClick={(e) => {
              e.stopPropagation();
              onOpenDetails();
            }}
            className="py-2 px-3 rounded-xl bg-white/5 hover:bg-white/10 text-zinc-300 border border-white/10 text-xs font-medium transition cursor-pointer"
          >
            Inspect Matrix
          </button>
        </div>
      </div>
    </div>
  );
};
