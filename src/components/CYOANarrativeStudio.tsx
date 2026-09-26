import React, { useState, useEffect } from 'react';
import confetti from 'canvas-confetti';
import {
  Flame,
  Volume2,
  Lock,
  Sparkles,
  Heart,
  DollarSign,
  ArrowRight,
  Eye,
  RefreshCw,
  Coins,
  ShieldAlert,
  Send,
  UserCheck,
  Crown,
  Play,
  Check,
  AlertCircle,
} from 'lucide-react';
import { InfluencerPersona, FanPsychProfile, CYOAScene, CYOAChoice } from '../types';
import { FAN_PSYCH_PROFILES } from '../data/fanArchetypes';
import { requestCYOAStep, playTtsVoice } from '../services/api';

interface CYOANarrativeStudioProps {
  selectedPersona: InfluencerPersona;
  allPersonas: InfluencerPersona[];
  onSelectPersona: (p: InfluencerPersona) => void;
  userCredits: number;
  setUserCredits: React.Dispatch<React.SetStateAction<number>>;
}

export const CYOANarrativeStudio: React.FC<CYOANarrativeStudioProps> = ({
  selectedPersona,
  allPersonas,
  onSelectPersona,
  userCredits,
  setUserCredits,
}) => {
  const [selectedFan, setSelectedFan] = useState<FanPsychProfile>(FAN_PSYCH_PROFILES[0]);
  const [currentScene, setCurrentScene] = useState<CYOAScene | null>(null);
  const [sceneHistory, setSceneHistory] = useState<CYOAScene[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isPlayingAudio, setIsPlayingAudio] = useState(false);
  const [showInternalMonologue, setShowInternalMonologue] = useState(false);
  const [parasocialXp, setParasocialXp] = useState(140);
  const [customTipAmount, setCustomTipAmount] = useState(25);
  const [tipSuccessMessage, setTipSuccessMessage] = useState<string | null>(null);
  const [unlockedPaywalls, setUnlockedPaywalls] = useState<Record<string, boolean>>({});

  // Initial scene load
  useEffect(() => {
    loadScene();
  }, [selectedPersona.id, selectedFan.id]);

  const loadScene = async (choiceTaken?: CYOAChoice) => {
    setIsLoading(true);
    try {
      const scene = await requestCYOAStep({
        persona: selectedPersona,
        fanProfile: selectedFan,
        previousSceneId: currentScene?.id,
        choiceTaken,
        history: sceneHistory.map((s) => s.scenarioTitle),
        creditsAvailable: userCredits,
      });

      setCurrentScene(scene);
      if (currentScene) {
        setSceneHistory((prev) => [...prev, currentScene]);
      }
    } catch (err) {
      console.error('Failed to step CYOA:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleChoose = async (choice: CYOAChoice) => {
    if (choice.requiredCostCredits && choice.requiredCostCredits > userCredits) {
      alert(`Insufficient SpiceCredits! Need ${choice.requiredCostCredits}, you have ${userCredits}.`);
      return;
    }

    if (choice.requiredCostCredits) {
      setUserCredits((c) => Math.max(0, c - choice.requiredCostCredits!));
      confetti({
        particleCount: 50,
        spread: 60,
        origin: { y: 0.8 },
      });
    }

    setParasocialXp((xp) => xp + (choice.parasocialGain || 20));
    await loadScene(choice);
  };

  const handlePlayVoice = async () => {
    if (!currentScene?.voiceScript) return;
    setIsPlayingAudio(true);
    try {
      await playTtsVoice(currentScene.voiceScript, selectedPersona.voice.voiceName);
    } finally {
      setTimeout(() => setIsPlayingAudio(false), 3000);
    }
  };

  const handleUnlockTeaser = (sceneId: string, cost: number) => {
    if (userCredits < cost) {
      alert(`Need ${cost} SpiceCredits to unlock this private vault content.`);
      return;
    }

    setUserCredits((c) => c - cost);
    setUnlockedPaywalls((prev) => ({ ...prev, [sceneId]: true }));
    setParasocialXp((xp) => xp + 50);

    confetti({
      particleCount: 80,
      spread: 70,
      origin: { y: 0.7 },
      colors: ['#ec4899', '#f43f5e', '#fbbf24', '#a855f7'],
    });

    setTipSuccessMessage(`Private Content Unlocked! ${selectedPersona.name} has granted VIP access.`);
    setTimeout(() => setTipSuccessMessage(null), 4000);
  };

  const handleSendTip = (amount: number) => {
    setUserCredits((c) => c + amount); // simulate whale tip transaction
    setParasocialXp((xp) => xp + amount * 3);

    confetti({
      particleCount: 90,
      spread: 80,
      origin: { y: 0.6 },
    });

    setTipSuccessMessage(
      `💸 $${amount} Tip Received! ${selectedPersona.name}: "Mmm, you really know how to make an entrance. Keep that up and I might give you my private number."`
    );
    setTimeout(() => setTipSuccessMessage(null), 5000);
  };

  const getRelationshipLevel = (xp: number) => {
    if (xp > 500) return { title: 'Whale Patron (Tier V)', color: 'text-amber-400', progress: 100 };
    if (xp > 300) return { title: 'Inner Circle (Tier IV)', color: 'text-rose-400', progress: (xp / 500) * 100 };
    if (xp > 180) return { title: 'Favorite Admirer (Tier III)', color: 'text-purple-400', progress: (xp / 300) * 100 };
    if (xp > 80) return { title: 'Devoted Fan (Tier II)', color: 'text-pink-400', progress: (xp / 180) * 100 };
    return { title: 'Curious Stranger (Tier I)', color: 'text-zinc-400', progress: (xp / 80) * 100 };
  };

  const rel = getRelationshipLevel(parasocialXp);

  return (
    <div className="max-w-7xl mx-auto space-y-6 animate-fadeIn pb-12">
      {/* Top Banner & Control Deck */}
      <div className="bg-[#11131c] border border-white/10 rounded-3xl p-6 shadow-xl relative overflow-hidden">
        <div className="absolute top-0 right-0 w-96 h-96 bg-gradient-to-bl from-pink-500/10 via-purple-500/5 to-transparent rounded-full blur-3xl pointer-events-none" />

        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="px-2.5 py-0.5 rounded-full text-[10px] font-mono uppercase bg-pink-500/20 text-pink-300 border border-pink-500/30">
                CYOA Choose-Your-Own-Adventure
              </span>
              <span className="text-xs text-zinc-400">Dynamic Multi-Modal Narrative Branching</span>
            </div>
            <h1 className="text-2xl font-black text-white flex items-center gap-2">
              <span>{selectedPersona.name}</span>
              <span className="text-pink-400 text-lg font-normal">({selectedPersona.spiceArchetype} Archetype)</span>
            </h1>
            <p className="text-xs text-zinc-300 italic mt-0.5">"{selectedPersona.tagline}"</p>
          </div>

          {/* RAG Fan Psych Profile Selector */}
          <div className="flex items-center gap-3">
            <div className="bg-black/40 border border-white/10 rounded-2xl p-2.5 flex items-center gap-3">
              <div className="w-8 h-8 rounded-xl bg-purple-500/20 border border-purple-500/30 flex items-center justify-center text-purple-300">
                <UserCheck className="w-4 h-4" />
              </div>
              <div>
                <div className="text-[10px] text-zinc-400 uppercase font-mono">Vector Fan Profile (RAG)</div>
                <select
                  value={selectedFan.id}
                  onChange={(e) => {
                    const found = FAN_PSYCH_PROFILES.find((f) => f.id === e.target.value);
                    if (found) setSelectedFan(found);
                  }}
                  className="bg-transparent text-xs font-bold text-white focus:outline-none cursor-pointer"
                >
                  {FAN_PSYCH_PROFILES.map((fan) => (
                    <option key={fan.id} value={fan.id} className="bg-[#11131c] text-white">
                      {fan.name} ({fan.archetype})
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Reset story button */}
            <button
              onClick={() => {
                setSceneHistory([]);
                loadScene();
              }}
              className="p-3 rounded-2xl bg-white/5 hover:bg-white/10 text-zinc-300 hover:text-white border border-white/10 transition cursor-pointer"
              title="Restart story encounter"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Parasocial Affinity Progress Bar */}
        <div className="mt-4 pt-4 border-t border-white/5 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Heart className="w-4 h-4 text-pink-400 fill-pink-500/20" />
            <div className="text-xs">
              <span className="text-zinc-400">Parasocial Affinity: </span>
              <span className={`font-bold ${rel.color}`}>{rel.title}</span>
              <span className="text-zinc-500 text-[10px] ml-2 font-mono">({parasocialXp} XP)</span>
            </div>
          </div>

          <div className="w-full sm:w-64 h-2 bg-white/10 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-pink-500 via-rose-500 to-amber-400 rounded-full transition-all duration-500"
              style={{ width: `${Math.min(100, rel.progress)}%` }}
            />
          </div>

          <div className="flex items-center gap-2 text-xs text-zinc-400">
            <Coins className="w-3.5 h-3.5 text-amber-400" />
            <span>Balance: <strong className="text-amber-300 font-mono">{userCredits} Credits</strong></span>
          </div>
        </div>
      </div>

      {/* Main Interactive Stage Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Narrative Scene & Dialogue */}
        <div className="lg:col-span-2 space-y-6">
          {isLoading ? (
            <div className="min-h-[480px] bg-[#11131c] border border-white/10 rounded-3xl p-8 flex flex-col items-center justify-center text-center space-y-4">
              <div className="relative">
                <div className="w-16 h-16 rounded-full border-4 border-pink-500/20 border-t-pink-500 animate-spin" />
                <Sparkles className="w-6 h-6 text-pink-400 absolute inset-0 m-auto" />
              </div>
              <div>
                <h3 className="text-lg font-bold text-white">Synthesizing Next Branch...</h3>
                <p className="text-xs text-zinc-400 max-w-sm mt-1">
                  Gemini 3.8 Flash evaluating fan psych metrics, allure vectors, and cliffhanger paywall triggers.
                </p>
              </div>
            </div>
          ) : currentScene ? (
            <div className="bg-[#11131c] border border-white/10 rounded-3xl overflow-hidden shadow-2xl space-y-6">
              {/* Scene Atmosphere Header */}
              <div className="p-6 border-b border-white/10 bg-gradient-to-r from-pink-500/5 via-[#11131c] to-purple-500/5">
                <div className="flex items-center justify-between gap-2 mb-2">
                  <span className="text-xs font-mono font-semibold uppercase text-pink-400 flex items-center gap-1.5">
                    <Flame className="w-3.5 h-3.5 fill-current" />
                    {currentScene.scenarioTitle}
                  </span>
                  <span className="text-[11px] px-2.5 py-0.5 rounded-full bg-white/5 text-zinc-300 border border-white/10 font-mono">
                    📍 {currentScene.location}
                  </span>
                </div>
                <p className="text-xs text-zinc-400 italic">
                  Vibe: {currentScene.environmentVibe}
                </p>
              </div>

              {/* Situation Narrative */}
              <div className="px-6 text-sm text-zinc-300 leading-relaxed">
                {currentScene.situation}
              </div>

              {/* Persona Spoken Dialogue Box */}
              <div className="mx-6 p-5 rounded-2xl bg-gradient-to-br from-[#1a1424] to-[#121526] border border-pink-500/30 relative shadow-lg">
                <div className="flex items-start gap-4">
                  <div className="relative shrink-0">
                    <img
                      src={selectedPersona.avatarUrl}
                      alt={selectedPersona.name}
                      className="w-14 h-14 rounded-2xl object-cover border-2 border-pink-400 shadow-md"
                    />
                    <div className="absolute -bottom-1 -right-1 w-4 h-4 rounded-full bg-emerald-500 border-2 border-[#1a1424] animate-pulse" />
                  </div>

                  <div className="flex-1 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-bold text-white flex items-center gap-1.5">
                        {selectedPersona.name}
                        <Crown className="w-3.5 h-3.5 text-amber-400" />
                      </span>

                      {/* TTS Play Button */}
                      <button
                        onClick={handlePlayVoice}
                        disabled={isPlayingAudio}
                        className={`px-3 py-1.5 rounded-xl text-xs font-medium flex items-center gap-1.5 transition cursor-pointer ${
                          isPlayingAudio
                            ? 'bg-rose-500 text-white animate-pulse'
                            : 'bg-white/10 hover:bg-white/20 text-rose-300 border border-white/10'
                        }`}
                        title="Listen to dialogue (Gemini TTS Voice)"
                      >
                        <Volume2 className="w-3.5 h-3.5" />
                        <span>{isPlayingAudio ? 'Speaking...' : 'Play Voice Note'}</span>
                      </button>
                    </div>

                    <blockquote className="text-base font-serif italic text-pink-100 leading-snug">
                      "{currentScene.personaDialogue}"
                    </blockquote>
                  </div>
                </div>

                {/* Internal Monologue Toggle (Strategic Psychology Peek) */}
                <div className="mt-4 pt-3 border-t border-white/10 flex items-center justify-between">
                  <button
                    onClick={() => setShowInternalMonologue(!showInternalMonologue)}
                    className="text-[11px] text-zinc-400 hover:text-pink-300 flex items-center gap-1.5 transition cursor-pointer"
                  >
                    <Eye className="w-3 h-3 text-pink-400" />
                    <span>{showInternalMonologue ? 'Hide Strategic Monologue' : 'Inspect AI Internal Strategy'}</span>
                  </button>
                  <span className="text-[10px] text-zinc-500 font-mono">Feminine Wiles Engine Active</span>
                </div>

                {showInternalMonologue && (
                  <div className="mt-3 p-3 rounded-xl bg-purple-950/40 border border-purple-500/20 text-xs text-purple-200 font-mono">
                    <div className="text-[10px] uppercase text-purple-400 mb-1 flex items-center gap-1">
                      <ShieldAlert className="w-3 h-3" />
                      Subconscious Monetization Calculation:
                    </div>
                    {currentScene.personaInternalMonologue}
                  </div>
                )}
              </div>

              {/* Paywalled Velvet Rope Teaser (If available in scene) */}
              {(currentScene.isPaywalledTeaser || currentScene.unlockCostCredits) && (
                <div className="mx-6 p-4 rounded-2xl bg-gradient-to-r from-amber-500/10 via-pink-500/10 to-purple-500/10 border border-amber-500/30">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <Lock className="w-4 h-4 text-amber-400" />
                      <h4 className="text-xs font-bold uppercase tracking-wider text-amber-300">
                        Locked VIP Media & Uncensored Confession
                      </h4>
                    </div>
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 font-mono">
                      Exclusive Drop
                    </span>
                  </div>

                  <p className="text-xs text-zinc-300 mb-3">
                    {selectedPersona.name} whispered something off-camera before closing the door. Unlock her private unedited voice recording and personal camera teaser.
                  </p>

                  {unlockedPaywalls[currentScene.id] ? (
                    <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Check className="w-4 h-4 text-emerald-400" />
                        <span>Unlocked! Private voice memo and high-res backstage lookbook accessible.</span>
                      </div>
                      <button
                        onClick={handlePlayVoice}
                        className="px-3 py-1 rounded-lg bg-emerald-500 text-black text-xs font-bold cursor-pointer"
                      >
                        Play Audio
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => handleUnlockTeaser(currentScene.id, currentScene.unlockCostCredits || 50)}
                      className="w-full py-2.5 px-4 rounded-xl bg-gradient-to-r from-amber-500 to-rose-500 hover:from-amber-400 hover:to-rose-400 text-black font-bold text-xs flex items-center justify-center gap-2 shadow-lg shadow-amber-500/20 transition cursor-pointer active:scale-95"
                    >
                      <Lock className="w-3.5 h-3.5" />
                      <span>Unlock with {currentScene.unlockCostCredits || 50} SpiceCredits</span>
                    </button>
                  )}
                </div>
              )}

              {/* Branching Choice Options */}
              <div className="p-6 border-t border-white/10 space-y-3">
                <h4 className="text-xs uppercase font-mono tracking-wider text-zinc-400 mb-3">
                  Choose Your Next Move (Your Response):
                </h4>

                <div className="grid grid-cols-1 gap-2.5">
                  {currentScene.choices.map((choice) => {
                    const isPaywall = choice.pathType === 'vip_paywall';
                    return (
                      <button
                        key={choice.id}
                        onClick={() => handleChoose(choice)}
                        className={`w-full p-4 rounded-2xl text-left border transition-all duration-200 cursor-pointer flex items-center justify-between gap-4 group ${
                          isPaywall
                            ? 'bg-gradient-to-r from-amber-500/10 via-pink-500/10 to-[#161324] border-amber-500/40 hover:border-amber-400 hover:shadow-lg hover:shadow-amber-500/10'
                            : 'bg-white/5 hover:bg-white/10 border-white/10 hover:border-pink-500/40'
                        }`}
                      >
                        <div className="space-y-1">
                          <div className="flex items-center gap-2">
                            {isPaywall ? (
                              <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-amber-500/20 text-amber-300 font-bold border border-amber-500/30 flex items-center gap-1">
                                <Lock className="w-2.5 h-2.5" />
                                VIP Paywall ({choice.requiredCostCredits} Credits)
                              </span>
                            ) : (
                              <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-white/10 text-zinc-300">
                                {choice.pathType}
                              </span>
                            )}
                            <span className="text-[10px] text-emerald-400 font-mono">
                              +{choice.parasocialGain} XP
                            </span>
                          </div>
                          <p className="text-xs font-semibold text-white group-hover:text-pink-200 transition">
                            {choice.text}
                          </p>
                          <p className="text-[11px] text-zinc-400 italic">
                            Result preview: {choice.reactionSnippet}
                          </p>
                        </div>

                        <div className="shrink-0 p-2 rounded-xl bg-white/5 group-hover:bg-pink-500 text-zinc-400 group-hover:text-white transition">
                          <ArrowRight className="w-4 h-4" />
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          ) : null}
        </div>

        {/* Right Column: Live Audience Stream, Monetization Tips, & Psych Profile */}
        <div className="space-y-6">
          {/* Tip Success Alert */}
          {tipSuccessMessage && (
            <div className="p-4 rounded-2xl bg-gradient-to-r from-pink-500 to-rose-600 text-white text-xs font-medium shadow-xl shadow-pink-500/30 animate-bounce">
              {tipSuccessMessage}
            </div>
          )}

          {/* Quick Tipping Jar */}
          <div className="bg-[#11131c] border border-white/10 rounded-3xl p-5 shadow-xl space-y-4">
            <div className="flex items-center justify-between">
              <h4 className="text-xs font-bold uppercase tracking-wider text-pink-400 flex items-center gap-1.5">
                <DollarSign className="w-3.5 h-3.5" />
                Live Tip Jar & Dare Stream
              </h4>
              <span className="text-[10px] text-emerald-400 font-mono">Instant Reaction</span>
            </div>

            <p className="text-xs text-zinc-400">
              Send a tip to interrupt her thoughts, boost your parasocial relationship level, and trigger exclusive custom praise.
            </p>

            <div className="grid grid-cols-3 gap-2">
              <button
                onClick={() => handleSendTip(10)}
                className="py-2.5 rounded-xl bg-white/5 hover:bg-pink-500/20 text-zinc-200 hover:text-pink-300 border border-white/10 text-xs font-mono font-bold transition cursor-pointer"
              >
                $10 (Boba)
              </button>
              <button
                onClick={() => handleSendTip(25)}
                className="py-2.5 rounded-xl bg-pink-500/20 hover:bg-pink-500/40 text-pink-300 border border-pink-500/40 text-xs font-mono font-bold transition cursor-pointer"
              >
                $25 (Voice DM)
              </button>
              <button
                onClick={() => handleSendTip(100)}
                className="py-2.5 rounded-xl bg-gradient-to-r from-amber-500/20 to-rose-500/20 hover:from-amber-500/30 hover:to-rose-500/30 text-amber-300 border border-amber-500/40 text-xs font-mono font-bold transition cursor-pointer"
              >
                $100 (Whale)
              </button>
            </div>
          </div>

          {/* Live Chat Comments Reaction Stream */}
          <div className="bg-[#11131c] border border-white/10 rounded-3xl p-5 shadow-xl space-y-4">
            <div className="flex items-center justify-between">
              <h4 className="text-xs font-bold uppercase tracking-wider text-zinc-300 flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-rose-500 animate-ping" />
                Audience Sentiment Stream
              </h4>
              <span className="text-[10px] text-zinc-500 font-mono">14.2k Viewers</span>
            </div>

            <div className="space-y-3 max-h-[360px] overflow-y-auto pr-1">
              {currentScene?.liveComments?.map((comm) => (
                <div key={comm.id} className="p-3 rounded-2xl bg-white/5 border border-white/5 space-y-1">
                  <div className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-1.5">
                      <span className="font-bold text-white">{comm.username}</span>
                      {comm.badge && (
                        <span
                          className={`text-[9px] px-1.5 py-0.2 rounded font-mono ${
                            comm.badge === 'Whale'
                              ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                              : 'bg-pink-500/20 text-pink-300'
                          }`}
                        >
                          {comm.badge}
                        </span>
                      )}
                    </div>
                    {comm.tipAmount && (
                      <span className="text-[10px] font-mono text-emerald-400 font-bold bg-emerald-500/10 px-1.5 rounded">
                        Tipped ${comm.tipAmount}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-zinc-300 leading-snug">{comm.text}</p>
                </div>
              ))}
            </div>
          </div>

          {/* RAG Vector Psych Profile Insights Card */}
          <div className="bg-[#11131c] border border-white/10 rounded-3xl p-5 shadow-xl space-y-3">
            <h4 className="text-xs font-bold uppercase tracking-wider text-purple-400 flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5" />
              Active Audience Psych Vector
            </h4>
            <div className="text-xs text-zinc-300 space-y-1.5">
              <div>
                <strong className="text-white">Selected Profile:</strong> {selectedFan.name}
              </div>
              <div>
                <strong className="text-white">Budget Segment:</strong>{' '}
                <span className="text-amber-400 font-mono">{selectedFan.budgetLevel}</span>
              </div>
              <div className="pt-1">
                <strong className="text-white">Exploitable Triggers:</strong>
                <ul className="list-disc list-inside text-zinc-400 text-[11px] mt-1 space-y-0.5">
                  {selectedFan.vulnerabilities.map((v, i) => (
                    <li key={i}>{v}</li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
