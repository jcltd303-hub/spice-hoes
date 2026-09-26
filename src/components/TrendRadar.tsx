import React, { useState, useEffect } from 'react';
import {
  Radio,
  TrendingUp,
  Search,
  Sparkles,
  Flame,
  Globe,
  RefreshCw,
  ArrowUpRight,
  PlusCircle,
  Zap,
} from 'lucide-react';
import { TrendAnalysisResult, SpiceArchetype } from '../types';
import { analyzeTrends } from '../services/api';

interface TrendRadarProps {
  onSynthesizeFromTrend: (archetype: SpiceArchetype, niche: string) => void;
}

export const TrendRadar: React.FC<TrendRadarProps> = ({ onSynthesizeFromTrend }) => {
  const [category, setCategory] = useState('Viral AI Influencer Aesthetics & Monetization');
  const [isLoading, setIsLoading] = useState(false);
  const [trends, setTrends] = useState<TrendAnalysisResult | null>(null);

  useEffect(() => {
    fetchTrends(category);
  }, []);

  const fetchTrends = async (cat: string) => {
    setIsLoading(true);
    try {
      const res = await analyzeTrends(cat);
      setTrends(res);
    } catch (err) {
      console.error('Failed to analyze trends:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const categories = [
    'Viral AI Influencer Aesthetics & Monetization',
    'Sensory Whispers & Coquette Boba ASMR',
    'Quiet Luxury & Old Money Minimalist Couture',
    'Biohacking Athleisure & High-Energy Gym Drip',
    'Uncensored Late-Night Podcast Confessionals',
    'Cyberpunk Underground Rave & Streetwear Drops',
  ];

  return (
    <div className="max-w-7xl mx-auto space-y-6 animate-fadeIn pb-12">
      {/* Header Deck */}
      <div className="bg-[#11131c] border border-white/10 rounded-3xl p-6 shadow-xl relative overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="px-2.5 py-0.5 rounded-full text-[10px] font-mono uppercase bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 flex items-center gap-1">
                <Globe className="w-3 h-3" />
                Google Search Grounding Engine
              </span>
              <span className="text-xs text-zinc-400">Live Web Vector Extraction & Trend Scout</span>
            </div>
            <h1 className="text-2xl font-black text-white flex items-center gap-2">
              Automated Trend Scout & Viral Aesthetic Radar
            </h1>
            <p className="text-xs text-zinc-300 mt-0.5">
              Continuously crawls TikTok, Instagram Reels, and VIP fan platforms to extract high-yield cultural tokens and profitable archetypes.
            </p>
          </div>

          <button
            onClick={() => fetchTrends(category)}
            disabled={isLoading}
            className="px-4 py-2.5 rounded-2xl bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 border border-cyan-500/40 text-xs font-semibold flex items-center gap-2 transition cursor-pointer disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
            <span>{isLoading ? 'Scanning Web...' : 'Refresh Trend Vectors'}</span>
          </button>
        </div>

        {/* Category Pills */}
        <div className="flex items-center gap-2 overflow-x-auto mt-5 pt-4 border-t border-white/10">
          {categories.map((cat) => (
            <button
              key={cat}
              onClick={() => {
                setCategory(cat);
                fetchTrends(cat);
              }}
              className={`px-3 py-1.5 rounded-xl text-xs font-medium whitespace-nowrap transition cursor-pointer border ${
                category === cat
                  ? 'bg-cyan-500/20 border-cyan-500/50 text-cyan-300 shadow-sm'
                  : 'bg-white/5 border-white/5 text-zinc-400 hover:text-zinc-200'
              }`}
            >
              {cat}
            </button>
          ))}
        </div>
      </div>

      {/* Main Trends Grid */}
      {isLoading ? (
        <div className="p-16 rounded-3xl bg-[#11131c] border border-white/10 text-center space-y-3">
          <div className="w-12 h-12 rounded-full border-4 border-cyan-500/20 border-t-cyan-500 animate-spin mx-auto" />
          <h3 className="text-base font-bold text-white">Extracting Grounded Web Vectors...</h3>
          <p className="text-xs text-zinc-400">
            Querying Google Search grounding models for emerging aesthetic signals and monetization velocity.
          </p>
        </div>
      ) : trends ? (
        <div className="space-y-6">
          {/* Macro Themes Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {trends.macroThemes.map((theme, i) => (
              <div
                key={i}
                className="p-5 rounded-3xl bg-[#11131c] border border-white/10 hover:border-cyan-500/40 transition flex flex-col justify-between space-y-4 group"
              >
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="px-2.5 py-0.5 rounded-full text-[10px] font-mono uppercase bg-pink-500/20 text-pink-300 font-bold border border-pink-500/30">
                      {theme.recommendedSpicePersona} Archetype
                    </span>
                    <span className="text-xs font-bold text-emerald-400 font-mono flex items-center gap-0.5">
                      <ArrowUpRight className="w-3.5 h-3.5" />
                      {theme.growthRate}
                    </span>
                  </div>

                  <h3 className="text-base font-bold text-white group-hover:text-cyan-300 transition">
                    {theme.theme}
                  </h3>

                  <div className="space-y-2 text-xs">
                    <div>
                      <div className="text-[10px] uppercase font-mono text-zinc-500">Viral Soundbites</div>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {theme.viralAudios.map((audio, aIdx) => (
                          <span
                            key={aIdx}
                            className="px-2 py-0.5 rounded bg-white/5 text-zinc-300 text-[10px] font-mono"
                          >
                            🎵 {audio}
                          </span>
                        ))}
                      </div>
                    </div>

                    <div className="pt-2 border-t border-white/5">
                      <div className="text-[10px] uppercase font-mono text-amber-400 mb-1">
                        Monetization Trigger
                      </div>
                      <p className="text-zinc-300 text-[11px] leading-snug">
                        {theme.monetizationTrigger}
                      </p>
                    </div>
                  </div>
                </div>

                <button
                  onClick={() => onSynthesizeFromTrend(theme.recommendedSpicePersona, theme.theme)}
                  className="w-full py-2 px-3 rounded-xl bg-gradient-to-r from-pink-500 to-rose-600 hover:from-pink-400 hover:to-rose-500 text-white text-xs font-semibold flex items-center justify-center gap-1.5 transition cursor-pointer shadow-md shadow-pink-500/20 active:scale-95"
                >
                  <PlusCircle className="w-3.5 h-3.5" />
                  <span>Synthesize Persona from Trend</span>
                </button>
              </div>
            ))}
          </div>

          {/* Aesthetic Keywords & Emerging Paywall Formats */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="p-5 rounded-3xl bg-[#11131c] border border-white/10 space-y-3">
              <h3 className="text-xs uppercase font-mono font-bold tracking-wider text-cyan-400 flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5" />
                Trending Aesthetic Hashtags & Visual Tokens
              </h3>
              <div className="flex flex-wrap gap-2">
                {trends.viralAestheticKeywords.map((kw, i) => (
                  <span
                    key={i}
                    className="px-3 py-1 rounded-xl bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 text-xs font-mono font-medium"
                  >
                    {kw}
                  </span>
                ))}
              </div>
            </div>

            <div className="p-5 rounded-3xl bg-[#11131c] border border-white/10 space-y-3">
              <h3 className="text-xs uppercase font-mono font-bold tracking-wider text-amber-400 flex items-center gap-1.5">
                <Flame className="w-3.5 h-3.5" />
                Emerging Paywall & High-Ticket Formats
              </h3>
              <div className="flex flex-wrap gap-2">
                {trends.emergingPaywallFormats.map((fmt, i) => (
                  <span
                    key={i}
                    className="px-3 py-1 rounded-xl bg-amber-500/10 text-amber-300 border border-amber-500/20 text-xs font-mono font-medium"
                  >
                    {fmt}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
};
