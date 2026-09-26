import React, { useState } from 'react';
import {
  Sparkles,
  Flame,
  Cpu,
  Layers,
  Radio,
  Share2,
  DollarSign,
  TrendingUp,
  PlusCircle,
  Play,
  Heart,
  ShieldCheck,
  Zap,
} from 'lucide-react';
import { InfluencerPersona, SpiceArchetype, RLPolicy } from './types';
import { DEFAULT_PERSONAS } from './data/defaultPersonas';
import { Header } from './components/Header';
import { PersonaCard } from './components/PersonaCard';
import { PersonaDetailModal } from './components/PersonaDetailModal';
import { CYOANarrativeStudio } from './components/CYOANarrativeStudio';
import { DeepRLOrchestrator } from './components/DeepRLOrchestrator';
import { MoAPipelineViewer } from './components/MoAPipelineViewer';
import { TrendRadar } from './components/TrendRadar';
import { MultiChannelHub } from './components/MultiChannelHub';
import { AutonomousPersonaCreator } from './components/AutonomousPersonaCreator';
import { ApiDeploymentModal } from './components/ApiDeploymentModal';

export default function App() {
  const [personas, setPersonas] = useState<InfluencerPersona[]>(DEFAULT_PERSONAS);
  const [selectedPersona, setSelectedPersona] = useState<InfluencerPersona>(DEFAULT_PERSONAS[0]);
  const [activeTab, setActiveTab] = useState<string>('roster');
  const [userCredits, setUserCredits] = useState<number>(250);

  // Modals
  const [isDetailModalOpen, setIsDetailModalOpen] = useState(false);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isApiModalOpen, setIsApiModalOpen] = useState(false);

  // Pre-seed creation from trend radar
  const [creatorInitialArchetype, setCreatorInitialArchetype] = useState<SpiceArchetype>('Ginger');
  const [creatorInitialNiche, setCreatorInitialNiche] = useState<string>('Late-Night Confessionals');

  const handleUpdatePersona = (updated: InfluencerPersona) => {
    setPersonas((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
    if (selectedPersona.id === updated.id) {
      setSelectedPersona(updated);
    }
  };

  const handleUpdatePolicy = (personaId: string, updatedPolicy: RLPolicy) => {
    setPersonas((prev) =>
      prev.map((p) => (p.id === personaId ? { ...p, rlPolicy: updatedPolicy } : p))
    );
    if (selectedPersona.id === personaId) {
      setSelectedPersona((prev) => ({ ...prev, rlPolicy: updatedPolicy }));
    }
  };

  const handlePersonaCreated = (newPersona: InfluencerPersona) => {
    setPersonas((prev) => [newPersona, ...prev]);
    setSelectedPersona(newPersona);
    setActiveTab('cyoa');
  };

  const handleSynthesizeFromTrend = (archetype: SpiceArchetype, niche: string) => {
    setCreatorInitialArchetype(archetype);
    setCreatorInitialNiche(niche);
    setIsCreateModalOpen(true);
  };

  return (
    <div className="min-h-screen bg-[#090a10] text-zinc-100 flex flex-col font-sans selection:bg-pink-500 selection:text-white">
      {/* Universal App Header */}
      <Header
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        personas={personas}
        selectedPersona={selectedPersona}
        setSelectedPersona={setSelectedPersona}
        userCredits={userCredits}
        setUserCredits={setUserCredits}
        onOpenCreateModal={() => {
          setCreatorInitialArchetype('Ginger');
          setCreatorInitialNiche('Sensory ASMR & Late-Night Banter');
          setIsCreateModalOpen(true);
        }}
        onOpenApiModal={() => setIsApiModalOpen(true)}
      />

      {/* Main Workspace Body */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 py-8">
        {/* TAB 1: THE SPICE QUINTET ROSTER */}
        {activeTab === 'roster' && (
          <div className="space-y-8 animate-fadeIn">
            {/* Hero / Studio Banner */}
            <div className="relative rounded-3xl p-8 overflow-hidden bg-gradient-to-r from-[#171226] via-[#151528] to-[#111320] border border-white/10 shadow-2xl">
              <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-gradient-to-bl from-pink-500/15 via-rose-500/10 to-transparent rounded-full blur-3xl pointer-events-none" />

              <div className="relative z-10 max-w-2xl space-y-3">
                <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-pink-500/10 border border-pink-500/30 text-pink-300 text-xs font-mono font-medium">
                  <Sparkles className="w-3.5 h-3.5 text-pink-400" />
                  THE MODERN SPICE QUINTET • AUTONOMOUS INFLUENCER ENGINE
                </div>

                <h1 className="text-3xl sm:text-4xl font-black text-white tracking-tight leading-tight">
                  Maximize Parasocial Profit with DeepRL & Multi-Agent Charisma.
                </h1>

                <p className="text-xs sm:text-sm text-zinc-300 leading-relaxed">
                  Five autonomous AI personas inspired by iconic archetypes (Sporty, Posh, Ginger, Scary, Baby). Powered by real-time trend web-grounding, Mixture-of-Agents consensus, Q-learning policy loops, and interactive Choose-Your-Own-Adventure dynamic monetization.
                </p>

                <div className="flex flex-wrap items-center gap-3 pt-2">
                  <button
                    onClick={() => setActiveTab('cyoa')}
                    className="px-5 py-2.5 rounded-2xl bg-gradient-to-r from-pink-500 via-rose-500 to-amber-400 hover:from-pink-400 hover:to-amber-300 text-black font-extrabold text-xs shadow-lg shadow-pink-500/25 transition cursor-pointer flex items-center gap-2 active:scale-95"
                  >
                    <Flame className="w-4 h-4 fill-black" />
                    <span>Launch Choose-Your-Own-Adventure</span>
                  </button>

                  <button
                    onClick={() => setActiveTab('deeprl')}
                    className="px-4 py-2.5 rounded-2xl bg-white/5 hover:bg-white/10 text-zinc-200 border border-white/10 text-xs font-semibold transition cursor-pointer flex items-center gap-2"
                  >
                    <Cpu className="w-4 h-4 text-emerald-400" />
                    <span>Inspect DeepRL Policy Engine</span>
                  </button>

                  <button
                    onClick={() => setActiveTab('moa')}
                    className="px-4 py-2.5 rounded-2xl bg-white/5 hover:bg-white/10 text-zinc-200 border border-white/10 text-xs font-semibold transition cursor-pointer flex items-center gap-2"
                  >
                    <Layers className="w-4 h-4 text-purple-400" />
                    <span>View MoA Pipeline</span>
                  </button>
                </div>
              </div>
            </div>

            {/* Persona Cards Grid */}
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-xl font-black text-white flex items-center gap-2">
                    Active Persona Roster ({personas.length})
                  </h2>
                  <p className="text-xs text-zinc-400">
                    Select a persona to test branching narratives, adjust feminine wiles, and optimize Bellman Q-values.
                  </p>
                </div>

                <button
                  onClick={() => setIsCreateModalOpen(true)}
                  className="px-3.5 py-2 rounded-xl bg-pink-500/20 hover:bg-pink-500/30 text-pink-300 border border-pink-500/40 text-xs font-semibold flex items-center gap-1.5 transition cursor-pointer"
                >
                  <PlusCircle className="w-4 h-4" />
                  <span>Add Custom Persona</span>
                </button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {personas.map((p) => (
                  <PersonaCard
                    key={p.id}
                    persona={p}
                    isSelected={p.id === selectedPersona.id}
                    onSelect={() => setSelectedPersona(p)}
                    onOpenDetails={() => {
                      setSelectedPersona(p);
                      setIsDetailModalOpen(true);
                    }}
                    onStartCYOA={() => {
                      setSelectedPersona(p);
                      setActiveTab('cyoa');
                    }}
                  />
                ))}
              </div>
            </div>
          </div>
        )}

        {/* TAB 2: CYOA STORY STUDIO */}
        {activeTab === 'cyoa' && (
          <CYOANarrativeStudio
            selectedPersona={selectedPersona}
            allPersonas={personas}
            onSelectPersona={setSelectedPersona}
            userCredits={userCredits}
            setUserCredits={setUserCredits}
          />
        )}

        {/* TAB 3: DEEPRL POLICY ENGINE */}
        {activeTab === 'deeprl' && (
          <DeepRLOrchestrator
            selectedPersona={selectedPersona}
            onUpdatePersonaPolicy={handleUpdatePolicy}
          />
        )}

        {/* TAB 4: MOA MULTI-MODEL AGENT */}
        {activeTab === 'moa' && (
          <MoAPipelineViewer selectedPersona={selectedPersona} />
        )}

        {/* TAB 5: TREND RADAR */}
        {activeTab === 'trends' && (
          <TrendRadar onSynthesizeFromTrend={handleSynthesizeFromTrend} />
        )}

        {/* TAB 6: MULTI-CHANNEL HUB */}
        {activeTab === 'channels' && (
          <MultiChannelHub
            selectedPersona={selectedPersona}
            userCredits={userCredits}
            setUserCredits={setUserCredits}
          />
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-white/10 bg-[#07080d] py-6 px-4 text-xs text-zinc-500 text-center">
        <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <span className="font-bold text-zinc-400">SpiceCore AI Engine</span>
            <span>•</span>
            <span>Autonomous Influencer DeepRL Studio</span>
          </div>

          <div className="flex items-center gap-4 text-zinc-400">
            <span>Server-side Gemini 3.8 Flash</span>
            <span>•</span>
            <span>Gemini TTS Lite</span>
            <span>•</span>
            <span>Google Search Grounding</span>
          </div>
        </div>
      </footer>

      {/* Modals */}
      {isDetailModalOpen && (
        <PersonaDetailModal
          persona={selectedPersona}
          onClose={() => setIsDetailModalOpen(false)}
          onUpdatePersona={handleUpdatePersona}
          onStartCYOA={() => {
            setIsDetailModalOpen(false);
            setActiveTab('cyoa');
          }}
        />
      )}

      {isCreateModalOpen && (
        <AutonomousPersonaCreator
          initialArchetype={creatorInitialArchetype}
          initialNiche={creatorInitialNiche}
          onClose={() => setIsCreateModalOpen(false)}
          onPersonaCreated={handlePersonaCreated}
        />
      )}

      {isApiModalOpen && (
        <ApiDeploymentModal onClose={() => setIsApiModalOpen(false)} />
      )}
    </div>
  );
}
