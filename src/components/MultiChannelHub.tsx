import React, { useState } from 'react';
import confetti from 'canvas-confetti';
import {
  Share2,
  Instagram,
  Twitter,
  Video,
  Lock,
  Heart,
  MessageCircle,
  Repeat2,
  Send,
  Volume2,
  DollarSign,
  Sparkles,
  Flame,
  CheckCircle2,
} from 'lucide-react';
import { InfluencerPersona } from '../types';
import { playTtsVoice } from '../services/api';

interface MultiChannelHubProps {
  selectedPersona: InfluencerPersona;
  userCredits: number;
  setUserCredits: React.Dispatch<React.SetStateAction<number>>;
}

export const MultiChannelHub: React.FC<MultiChannelHubProps> = ({
  selectedPersona,
  userCredits,
  setUserCredits,
}) => {
  const [activePlatform, setActivePlatform] = useState<'instagram' | 'tiktok' | 'twitter' | 'vip_vault'>('instagram');
  const [unlockedMedia, setUnlockedMedia] = useState<Record<string, boolean>>({});
  const [isPlayingVoice, setIsPlayingVoice] = useState(false);

  const handleUnlock = (key: string, cost: number) => {
    if (userCredits < cost) {
      alert(`Need ${cost} SpiceCredits to unlock this exclusive vault post.`);
      return;
    }
    setUserCredits((c) => c - cost);
    setUnlockedMedia((prev) => ({ ...prev, [key]: true }));

    confetti({
      particleCount: 60,
      spread: 70,
      origin: { y: 0.7 },
      colors: ['#ec4899', '#f43f5e', '#fbbf24'],
    });
  };

  const handlePlayVoice = async (text: string) => {
    setIsPlayingVoice(true);
    try {
      await playTtsVoice(text, selectedPersona.voice.voiceName);
    } finally {
      setTimeout(() => setIsPlayingVoice(false), 2500);
    }
  };

  return (
    <div className="max-w-7xl mx-auto space-y-6 animate-fadeIn pb-12">
      {/* Top Deck */}
      <div className="bg-[#11131c] border border-white/10 rounded-3xl p-6 shadow-xl relative overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="px-2.5 py-0.5 rounded-full text-[10px] font-mono uppercase bg-pink-500/20 text-pink-300 border border-pink-500/30 flex items-center gap-1">
                <Share2 className="w-3 h-3" />
                Cross-Platform Omnichannel Engine
              </span>
              <span className="text-xs text-zinc-400">Autonomous Multi-Surface Publishing</span>
            </div>
            <h1 className="text-2xl font-black text-white flex items-center gap-2">
              Multi-Channel Live Vault: {selectedPersona.name}
            </h1>
            <p className="text-xs text-zinc-300 mt-0.5">
              Simulates content deployment and micro-monetization across Instagram, TikTok, X, and the locked VIP Vault.
            </p>
          </div>

          {/* Platform Switcher Buttons */}
          <div className="flex items-center gap-1.5 bg-black/40 p-1.5 rounded-2xl border border-white/10">
            <button
              onClick={() => setActivePlatform('instagram')}
              className={`px-3 py-1.5 rounded-xl text-xs font-medium flex items-center gap-1.5 transition cursor-pointer ${
                activePlatform === 'instagram'
                  ? 'bg-gradient-to-r from-pink-500 to-rose-600 text-white font-bold shadow-md'
                  : 'text-zinc-400 hover:text-white'
              }`}
            >
              <Instagram className="w-3.5 h-3.5" />
              <span>Instagram Reel</span>
            </button>
            <button
              onClick={() => setActivePlatform('tiktok')}
              className={`px-3 py-1.5 rounded-xl text-xs font-medium flex items-center gap-1.5 transition cursor-pointer ${
                activePlatform === 'tiktok'
                  ? 'bg-gradient-to-r from-cyan-500 to-blue-600 text-white font-bold shadow-md'
                  : 'text-zinc-400 hover:text-white'
              }`}
            >
              <Video className="w-3.5 h-3.5" />
              <span>TikTok Script</span>
            </button>
            <button
              onClick={() => setActivePlatform('twitter')}
              className={`px-3 py-1.5 rounded-xl text-xs font-medium flex items-center gap-1.5 transition cursor-pointer ${
                activePlatform === 'twitter'
                  ? 'bg-gradient-to-r from-sky-500 to-blue-500 text-white font-bold shadow-md'
                  : 'text-zinc-400 hover:text-white'
              }`}
            >
              <Twitter className="w-3.5 h-3.5" />
              <span>X / Twitter</span>
            </button>
            <button
              onClick={() => setActivePlatform('vip_vault')}
              className={`px-3 py-1.5 rounded-xl text-xs font-medium flex items-center gap-1.5 transition cursor-pointer ${
                activePlatform === 'vip_vault'
                  ? 'bg-gradient-to-r from-amber-500 to-rose-500 text-black font-bold shadow-md'
                  : 'text-amber-400 hover:text-amber-300'
              }`}
            >
              <Lock className="w-3.5 h-3.5" />
              <span>Locked VIP Vault</span>
            </button>
          </div>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 Cols: Platform Preview */}
        <div className="lg:col-span-2">
          {activePlatform === 'instagram' && (
            <div className="bg-[#11131c] border border-white/10 rounded-3xl overflow-hidden shadow-2xl space-y-4">
              {/* Instagram Post Header */}
              <div className="p-4 flex items-center justify-between border-b border-white/10">
                <div className="flex items-center gap-3">
                  <img
                    src={selectedPersona.avatarUrl}
                    alt={selectedPersona.name}
                    className="w-10 h-10 rounded-full object-cover border border-pink-500/50"
                  />
                  <div>
                    <div className="text-xs font-bold text-white flex items-center gap-1">
                      {selectedPersona.handle}
                      <span className="w-1.5 h-1.5 rounded-full bg-pink-500" />
                    </div>
                    <p className="text-[10px] text-zinc-400">Audio: Original Sound • {selectedPersona.name}</p>
                  </div>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-white/5 text-zinc-400 font-mono">
                  Sponsored Stealth
                </span>
              </div>

              {/* Media image */}
              <div className="relative h-96 w-full overflow-hidden bg-black">
                <img
                  src={selectedPersona.bannerUrl}
                  alt="Post"
                  className="w-full h-full object-cover"
                />
                <button
                  onClick={() => handlePlayVoice(selectedPersona.viralHooks[0] || selectedPersona.voice.sampleText)}
                  className="absolute bottom-4 right-4 p-3 rounded-2xl bg-black/70 backdrop-blur-md text-white hover:scale-105 transition cursor-pointer border border-white/20 flex items-center gap-2 text-xs font-semibold"
                >
                  <Volume2 className="w-4 h-4 text-pink-400" />
                  <span>Listen to Reel Audio</span>
                </button>
              </div>

              {/* Engagement Bar */}
              <div className="p-4 space-y-3">
                <div className="flex items-center justify-between text-zinc-300">
                  <div className="flex items-center gap-4">
                    <button className="flex items-center gap-1.5 text-xs text-rose-400 font-mono">
                      <Heart className="w-4 h-4 fill-rose-500" />
                      <span>{(selectedPersona.followersCount * 0.082).toFixed(0)}</span>
                    </button>
                    <button className="flex items-center gap-1.5 text-xs text-zinc-300 font-mono">
                      <MessageCircle className="w-4 h-4" />
                      <span>{(selectedPersona.followersCount * 0.014).toFixed(0)}</span>
                    </button>
                    <button className="flex items-center gap-1.5 text-xs text-zinc-300">
                      <Send className="w-4 h-4" />
                    </button>
                  </div>
                  <span className="text-[10px] text-emerald-400 font-mono font-bold">
                    Est. Revenue: $4,850
                  </span>
                </div>

                {/* Caption with stealth monetization */}
                <div className="text-xs text-zinc-200 space-y-1.5">
                  <p>
                    <strong className="text-white mr-1.5">{selectedPersona.handle}</strong>
                    {selectedPersona.viralHooks[0]}. You can pretend you don't care, but I already saw you watch this twice.
                  </p>
                  <p className="text-pink-400">
                    {selectedPersona.aestheticTokens.join(' ')} #SpiceCore
                  </p>
                  <p className="text-zinc-500 text-[10px] pt-1">
                    View all 1,420 comments • Link in bio for unedited audio drop
                  </p>
                </div>
              </div>
            </div>
          )}

          {activePlatform === 'tiktok' && (
            <div className="bg-[#11131c] border border-white/10 rounded-3xl p-6 shadow-2xl space-y-6">
              <div className="flex items-center justify-between border-b border-white/10 pb-4">
                <div>
                  <h3 className="text-base font-bold text-white flex items-center gap-2">
                    <Video className="w-4 h-4 text-cyan-400" />
                    Viral TikTok Script & Retention Blueprint
                  </h3>
                  <p className="text-xs text-zinc-400">Optimized for 82% 3-second hook rate & cliffhanger loop</p>
                </div>
                <span className="px-2.5 py-0.5 rounded-full text-xs bg-cyan-500/20 text-cyan-300 font-mono font-bold">
                  Duration: 18s
                </span>
              </div>

              <div className="space-y-4 text-xs font-mono">
                {/* 0-3s Hook */}
                <div className="p-4 rounded-2xl bg-cyan-500/5 border border-cyan-500/20 space-y-1.5">
                  <div className="flex justify-between text-cyan-400 font-bold uppercase text-[10px]">
                    <span>[00:00 - 00:03] Sensory Hook (Visual & Audio)</span>
                    <span>Retention: 96%</span>
                  </div>
                  <p className="text-zinc-200">
                    <strong>Visual:</strong> Close-up eye contact directly into camera lens with micro-smirk.
                  </p>
                  <p className="text-zinc-200">
                    <strong>Voiceover:</strong> "{selectedPersona.viralHooks[1] || selectedPersona.tagline}"
                  </p>
                </div>

                {/* 3-12s Narrative Climax */}
                <div className="p-4 rounded-2xl bg-purple-500/5 border border-purple-500/20 space-y-1.5">
                  <div className="flex justify-between text-purple-400 font-bold uppercase text-[10px]">
                    <span>[00:03 - 00:12] Emotional Provocation & Challenge</span>
                    <span>Retention: 84%</span>
                  </div>
                  <p className="text-zinc-200">
                    <strong>Visual:</strong> Rapid cut to aesthetic environment ({selectedPersona.trendingNiches[0]}).
                  </p>
                  <p className="text-zinc-200">
                    <strong>Voiceover:</strong> "Most people scroll right past because they can't handle being held to a higher standard. But you're still watching."
                  </p>
                </div>

                {/* 12-18s Cliffhanger Call to Action */}
                <div className="p-4 rounded-2xl bg-pink-500/5 border border-pink-500/20 space-y-1.5">
                  <div className="flex justify-between text-pink-400 font-bold uppercase text-[10px]">
                    <span>[00:12 - 00:18] Cliffhanger Loop & Velvet Paywall</span>
                    <span>Retention: 78% (Loop Trigger)</span>
                  </div>
                  <p className="text-zinc-200">
                    <strong>Visual:</strong> She leans in, turns off mic abruptly with sound cut.
                  </p>
                  <p className="text-zinc-200">
                    <strong>Voiceover:</strong> "If you want the unedited audio memo... you know where the door is."
                  </p>
                </div>
              </div>

              <button
                onClick={() => handlePlayVoice(selectedPersona.viralHooks[1] || selectedPersona.tagline)}
                className="w-full py-3 rounded-2xl bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white font-bold text-xs flex items-center justify-center gap-2 cursor-pointer transition shadow-lg shadow-cyan-500/20"
              >
                <Volume2 className="w-4 h-4" />
                <span>Test Synthesized Audio Hook</span>
              </button>
            </div>
          )}

          {activePlatform === 'twitter' && (
            <div className="bg-[#11131c] border border-white/10 rounded-3xl p-6 shadow-2xl space-y-4">
              <div className="flex items-start gap-3">
                <img
                  src={selectedPersona.avatarUrl}
                  alt={selectedPersona.name}
                  className="w-12 h-12 rounded-full object-cover border border-sky-400"
                />
                <div className="flex-1 space-y-2">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-bold text-white">{selectedPersona.name}</span>
                    <span className="text-xs text-zinc-500 font-mono">{selectedPersona.handle}</span>
                    <span className="text-xs text-zinc-600">· 2h</span>
                  </div>

                  <p className="text-sm text-zinc-100 leading-normal">
                    The reason you're frustrated isn't that you lack discipline. It's that you're seeking validation from people whose lifestyle you wouldn't even accept for free.
                    <br /><br />
                    Unlocking the 2 AM confessional on the private feed tonight. Don't complain if you miss it.
                  </p>

                  <div className="flex items-center justify-between pt-2 border-t border-white/10 text-zinc-400 text-xs font-mono">
                    <span className="flex items-center gap-1.5 hover:text-sky-400 cursor-pointer">
                      <MessageCircle className="w-4 h-4" /> 482
                    </span>
                    <span className="flex items-center gap-1.5 hover:text-emerald-400 cursor-pointer">
                      <Repeat2 className="w-4 h-4" /> 1,290
                    </span>
                    <span className="flex items-center gap-1.5 hover:text-rose-400 cursor-pointer">
                      <Heart className="w-4 h-4" /> 8,410
                    </span>
                    <span className="text-emerald-400 font-bold">
                      Tip Jar Active
                    </span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {activePlatform === 'vip_vault' && (
            <div className="bg-[#11131c] border border-amber-500/30 rounded-3xl p-6 shadow-2xl space-y-6">
              <div className="flex items-center justify-between border-b border-white/10 pb-4">
                <div>
                  <div className="flex items-center gap-2">
                    <Lock className="w-4 h-4 text-amber-400" />
                    <h3 className="text-base font-bold text-white">
                      The Velvet Sanctum: Locked Media Vault
                    </h3>
                  </div>
                  <p className="text-xs text-zinc-400">Exclusive pay-to-unlock audio journals and personal DMs</p>
                </div>
                <span className="px-3 py-1 rounded-full text-xs font-mono uppercase bg-amber-500/20 text-amber-300 font-bold border border-amber-500/30">
                  Subscribers Only
                </span>
              </div>

              {/* Locked Drop 1 */}
              <div className="p-5 rounded-2xl bg-black/40 border border-amber-500/20 space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="text-sm font-bold text-white">
                    Private Midnight Audio Journal: "What I didn't say on stream"
                  </h4>
                  <span className="text-[10px] text-zinc-400 font-mono">Duration: 4m 12s</span>
                </div>

                <p className="text-xs text-zinc-300">
                  {selectedPersona.name} recorded this alone in her suite at 2:14 AM. Whispered, candid, and strictly for VIP patrons.
                </p>

                {unlockedMedia['audio_1'] ? (
                  <div className="p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                      <span>Audio Unlocked! Full fidelity recording available.</span>
                    </div>
                    <button
                      onClick={() => handlePlayVoice(selectedPersona.voice.sampleText)}
                      className="px-3 py-1.5 rounded-lg bg-emerald-500 text-black text-xs font-bold cursor-pointer hover:bg-emerald-400 transition"
                    >
                      Play Uncut Memo
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => handleUnlock('audio_1', 40)}
                    className="w-full py-2.5 rounded-xl bg-gradient-to-r from-amber-500 to-rose-500 hover:from-amber-400 hover:to-rose-400 text-black font-bold text-xs flex items-center justify-center gap-2 transition cursor-pointer shadow-md shadow-amber-500/20 active:scale-95"
                  >
                    <Lock className="w-3.5 h-3.5" />
                    <span>Unlock for 40 SpiceCredits</span>
                  </button>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Right Col: Omnichannel Analytics & Monetization Velocity */}
        <div className="space-y-6">
          <div className="bg-[#11131c] border border-white/10 rounded-3xl p-5 shadow-xl space-y-4">
            <h4 className="text-xs font-bold uppercase tracking-wider text-pink-400 flex items-center gap-1.5">
              <DollarSign className="w-3.5 h-3.5" />
              Omnichannel Revenue Velocity
            </h4>

            <div className="space-y-3 font-mono text-xs">
              <div className="flex items-center justify-between p-2.5 rounded-xl bg-black/40 border border-white/5">
                <span className="text-zinc-400">Locked Vault Subs:</span>
                <span className="text-emerald-400 font-bold">${(selectedPersona.mrr * 0.65).toLocaleString()}/mo</span>
              </div>
              <div className="flex items-center justify-between p-2.5 rounded-xl bg-black/40 border border-white/5">
                <span className="text-zinc-400">Micro-Tipping Streams:</span>
                <span className="text-pink-400 font-bold">${(selectedPersona.mrr * 0.22).toLocaleString()}/mo</span>
              </div>
              <div className="flex items-center justify-between p-2.5 rounded-xl bg-black/40 border border-white/5">
                <span className="text-zinc-400">Stealth Brand Integrations:</span>
                <span className="text-amber-400 font-bold">${(selectedPersona.mrr * 0.13).toLocaleString()}/mo</span>
              </div>
            </div>
          </div>

          <div className="bg-[#11131c] border border-white/10 rounded-3xl p-5 shadow-xl space-y-3">
            <h4 className="text-xs font-bold uppercase tracking-wider text-purple-400 flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5" />
              Multimodal Audio/Video Status
            </h4>
            <p className="text-xs text-zinc-300">
              Gemini TTS model <code className="text-pink-300">gemini-3.8-flash-lite-tts</code> is hooked to voice preset <strong className="text-white">{selectedPersona.voice.voiceName}</strong>.
            </p>
            <div className="p-3 rounded-xl bg-white/5 text-[11px] text-zinc-400 font-mono">
              Pitch: {selectedPersona.voice.pitch > 0 ? `+${selectedPersona.voice.pitch}` : selectedPersona.voice.pitch} | Cadence: {selectedPersona.voice.cadence}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
