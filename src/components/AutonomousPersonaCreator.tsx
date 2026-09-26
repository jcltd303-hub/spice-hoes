import React, { useState } from 'react';
import confetti from 'canvas-confetti';
import {
  X,
  Sparkles,
  PlusCircle,
  Sliders,
  Flame,
  Crown,
  Volume2,
  DollarSign,
  Cpu,
} from 'lucide-react';
import { InfluencerPersona, SpiceArchetype } from '../types';
import { generatePersona } from '../services/api';

interface AutonomousPersonaCreatorProps {
  onClose: () => void;
  onPersonaCreated: (newPersona: InfluencerPersona) => void;
  initialArchetype?: SpiceArchetype;
  initialNiche?: string;
}

export const AutonomousPersonaCreator: React.FC<AutonomousPersonaCreatorProps> = ({
  onClose,
  onPersonaCreated,
  initialArchetype = 'Ginger',
  initialNiche = 'Late-Night Confessionals & Taboo Banter',
}) => {
  const [archetype, setArchetype] = useState<SpiceArchetype>(initialArchetype);
  const [niche, setNiche] = useState(initialNiche);
  const [customPrompt, setCustomPrompt] = useState('');
  const [allureTarget, setAllureTarget] = useState(94);
  const [isGenerating, setIsGenerating] = useState(false);

  const archetypes: { type: SpiceArchetype; desc: string }[] = [
    { type: 'Sporty', desc: 'Kinetic, biohacking athlete, tough-love dopamine dispenser' },
    { type: 'Posh', desc: 'Cold quiet luxury aristocrat, aloof exclusivity, high-society wit' },
    { type: 'Ginger', desc: 'Fiery provocateur, dangerous banter, emotional roller-coaster' },
    { type: 'Scary', desc: 'Cyber-rebel siren, underground rave queen, maximalist dominance' },
    { type: 'Baby', desc: 'Coquette angelcore disarming sweetness, ruthless monetization mastermind' },
  ];

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsGenerating(true);

    try {
      const created = await generatePersona({
        spiceArchetype: archetype,
        niche,
        customPrompt,
        allureTarget,
      });

      confetti({
        particleCount: 100,
        spread: 80,
        origin: { y: 0.6 },
        colors: ['#ec4899', '#f43f5e', '#a855f7', '#fbbf24'],
      });

      onPersonaCreated(created);
      onClose();
    } catch (err) {
      console.error('Failed to generate persona:', err);
      alert('Failed to synthesize persona. Please try again.');
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fadeIn">
      <div className="relative w-full max-w-2xl bg-[#0f111a] border border-white/10 rounded-3xl overflow-hidden shadow-2xl flex flex-col text-white">
        {/* Header */}
        <div className="p-6 border-b border-white/10 flex items-center justify-between bg-gradient-to-r from-pink-500/10 via-[#0f111a] to-purple-500/10">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-pink-500/20 text-pink-300 font-bold border border-pink-500/30">
                Persona Foundry v3.8
              </span>
            </div>
            <h2 className="text-xl font-black text-white flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-pink-400" />
              Synthesize Autonomous AI Influencer
            </h2>
            <p className="text-xs text-zinc-400">
              Generates complete psych matrix, DeepRL policy weights, voice archetype, and monetization tiers.
            </p>
          </div>

          <button
            onClick={onClose}
            className="p-2 rounded-full bg-white/5 hover:bg-white/10 text-zinc-400 hover:text-white transition cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleGenerate} className="p-6 space-y-5 overflow-y-auto max-h-[75vh]">
          {/* Archetype Selector */}
          <div>
            <label className="block text-xs uppercase font-mono tracking-wider text-zinc-400 mb-2">
              Select Core Spice Archetype
            </label>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {archetypes.map((arch) => (
                <button
                  type="button"
                  key={arch.type}
                  onClick={() => setArchetype(arch.type)}
                  className={`p-3 rounded-2xl text-left border transition cursor-pointer flex flex-col justify-between ${
                    archetype === arch.type
                      ? 'bg-pink-500/20 border-pink-500/60 text-white shadow-md'
                      : 'bg-white/5 border-white/5 text-zinc-400 hover:text-zinc-200'
                  }`}
                >
                  <span className="text-xs font-bold text-white">{arch.type} Archetype</span>
                  <span className="text-[10px] text-zinc-400 mt-0.5 leading-snug">{arch.desc}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Trending Niche */}
          <div>
            <label className="block text-xs uppercase font-mono tracking-wider text-zinc-400 mb-2">
              Trending Niche & Aesthetic Vector
            </label>
            <input
              type="text"
              value={niche}
              onChange={(e) => setNiche(e.target.value)}
              className="w-full px-4 py-2.5 rounded-xl bg-black/40 border border-white/10 text-xs text-white focus:outline-none focus:border-pink-500"
              placeholder="e.g. Quiet Luxury Couture & Penthouse Etiquette"
              required
            />
          </div>

          {/* Custom Concept Prompt */}
          <div>
            <label className="block text-xs uppercase font-mono tracking-wider text-zinc-400 mb-2">
              Custom Persona Narrative / Persona Prompt (Optional)
            </label>
            <textarea
              value={customPrompt}
              onChange={(e) => setCustomPrompt(e.target.value)}
              rows={3}
              className="w-full px-4 py-2.5 rounded-xl bg-black/40 border border-white/10 text-xs text-white focus:outline-none focus:border-pink-500"
              placeholder="Add specific backstory details, conversational quirks, or monetization hooks..."
            />
          </div>

          {/* Allure Index Target */}
          <div>
            <div className="flex justify-between text-xs mb-2">
              <span className="text-zinc-300 font-medium">Target Allure & Feminine Wiles Index</span>
              <span className="text-pink-400 font-mono font-bold">{allureTarget}%</span>
            </div>
            <input
              type="range"
              min="60"
              max="100"
              value={allureTarget}
              onChange={(e) => setAllureTarget(Number(e.target.value))}
              className="w-full accent-pink-500 cursor-pointer"
            />
            <p className="text-[10px] text-zinc-500 mt-1">
              Higher values maximize emotional hook pull, parasocial intensity, and paywall conversion.
            </p>
          </div>

          {/* Submit */}
          <div className="pt-4 border-t border-white/10 flex items-center justify-end gap-3">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-xl bg-white/5 hover:bg-white/10 text-zinc-300 text-xs font-medium cursor-pointer transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isGenerating}
              className="px-6 py-2.5 rounded-xl bg-gradient-to-r from-pink-500 to-rose-600 hover:from-pink-400 hover:to-rose-500 text-white font-bold text-xs shadow-lg shadow-pink-500/25 transition cursor-pointer flex items-center gap-2 disabled:opacity-50 active:scale-95"
            >
              <Sparkles className={`w-4 h-4 ${isGenerating ? 'animate-spin' : ''}`} />
              <span>{isGenerating ? 'Synthesizing Persona...' : 'Synthesize & Deploy'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
