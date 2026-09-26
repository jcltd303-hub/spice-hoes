import React, { useState } from 'react';
import {
  X,
  Cpu,
  Copy,
  Check,
  Terminal,
  Code2,
  Webhook,
  Layers,
  Sparkles,
} from 'lucide-react';

interface ApiDeploymentModalProps {
  onClose: () => void;
}

export const ApiDeploymentModal: React.FC<ApiDeploymentModalProps> = ({ onClose }) => {
  const [activeSnippet, setActiveSnippet] = useState<'curl' | 'ts' | 'python'>('curl');
  const [copied, setCopied] = useState(false);

  const curlSnippet = `# 1. Advance CYOA Narrative Step
curl -X POST https://your-spicecore-app.run.app/api/cyoa/step \\
  -H "Content-Type: application/json" \\
  -d '{
    "persona": { "id": "ruby-wren-ginger" },
    "fanProfile": { "archetype": "Whale Collector" },
    "choiceTaken": { "text": "Unlock private audio confessional", "pathType": "vip_paywall" },
    "creditsAvailable": 100
  }'

# 2. Execute DeepRL Optimization Epoch
curl -X POST https://your-spicecore-app.run.app/api/deeprl/step \\
  -H "Content-Type: application/json" \\
  -d '{
    "persona": { "id": "zara-voss-posh" },
    "actionCode": "VELVET_PAYWALL"
  }'

# 3. Synthesize Gemini TTS Persona Voice Note
curl -X POST https://your-spicecore-app.run.app/api/tts/generate \\
  -H "Content-Type: application/json" \\
  -d '{
    "text": "Access to my salon requires more than mere admiration.",
    "voiceName": "Kore"
  }'`;

  const tsSnippet = `import axios from 'axios';

const SPICECORE_API = 'https://your-spicecore-app.run.app/api';

// Advance Choose-Your-Own-Adventure Branch
export async function stepCYOA(personaId: string, choiceText: string) {
  const response = await axios.post(\`\${SPICECORE_API}/cyoa/step\`, {
    persona: { id: personaId },
    choiceTaken: { text: choiceText, pathType: 'vip_paywall' },
    creditsAvailable: 250
  });
  return response.data; // returns next scene, voiceScript, & paywall status
}

// Trigger DeepRL Policy Optimization
export async function optimizePolicy(personaId: string, action: 'VELVET_PAYWALL' | 'MICRO_TEASE') {
  const response = await axios.post(\`\${SPICECORE_API}/deeprl/step\`, {
    persona: { id: personaId },
    actionCode: action
  });
  return response.data; // returns new Q-value, reward scalar, and epoch
}`;

  const pythonSnippet = `import requests

BASE_URL = "https://your-spicecore-app.run.app/api"

def step_cyoa(persona_id, choice_text):
    payload = {
        "persona": {"id": persona_id},
        "choiceTaken": {"text": choice_text, "pathType": "vip_paywall"},
        "creditsAvailable": 250
    }
    r = requests.post(f"{BASE_URL}/cyoa/step", json=payload)
    return r.json()

def run_moa_orchestration(persona_id, objective):
    payload = {
        "persona": {"id": persona_id},
        "objective": objective
    }
    r = requests.post(f"{BASE_URL}/moa/orchestrate", json=payload)
    return r.json()`;

  const handleCopy = () => {
    let text = curlSnippet;
    if (activeSnippet === 'ts') text = tsSnippet;
    if (activeSnippet === 'python') text = pythonSnippet;

    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fadeIn">
      <div className="relative w-full max-w-3xl bg-[#0f111a] border border-white/10 rounded-3xl overflow-hidden shadow-2xl flex flex-col text-white">
        {/* Header */}
        <div className="p-6 border-b border-white/10 flex items-center justify-between bg-gradient-to-r from-cyan-500/10 via-[#0f111a] to-blue-500/10">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-cyan-500/20 text-cyan-300 font-bold border border-cyan-500/30">
                REST API & Webhooks v1
              </span>
            </div>
            <h2 className="text-xl font-black text-white flex items-center gap-2">
              <Cpu className="w-5 h-5 text-cyan-400" />
              Cross-Platform Deployment & Developer API
            </h2>
            <p className="text-xs text-zinc-400">
              Deploy autonomous AI influencers directly to Discord bots, Telegram VIP channels, and TikTok scheduling queues.
            </p>
          </div>

          <button
            onClick={onClose}
            className="p-2 rounded-full bg-white/5 hover:bg-white/10 text-zinc-400 hover:text-white transition cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Snippet selector */}
        <div className="p-6 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <button
                onClick={() => setActiveSnippet('curl')}
                className={`px-3 py-1.5 rounded-xl text-xs font-mono transition cursor-pointer ${
                  activeSnippet === 'curl'
                    ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 font-bold'
                    : 'text-zinc-400 hover:text-zinc-200'
                }`}
              >
                cURL
              </button>
              <button
                onClick={() => setActiveSnippet('ts')}
                className={`px-3 py-1.5 rounded-xl text-xs font-mono transition cursor-pointer ${
                  activeSnippet === 'ts'
                    ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 font-bold'
                    : 'text-zinc-400 hover:text-zinc-200'
                }`}
              >
                TypeScript / Node
              </button>
              <button
                onClick={() => setActiveSnippet('python')}
                className={`px-3 py-1.5 rounded-xl text-xs font-mono transition cursor-pointer ${
                  activeSnippet === 'python'
                    ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 font-bold'
                    : 'text-zinc-400 hover:text-zinc-200'
                }`}
              >
                Python 3
              </button>
            </div>

            <button
              onClick={handleCopy}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white/5 hover:bg-white/10 text-xs text-zinc-300 hover:text-white border border-white/10 transition cursor-pointer"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
              <span>{copied ? 'Copied!' : 'Copy Code'}</span>
            </button>
          </div>

          {/* Code View */}
          <div className="p-4 rounded-2xl bg-black/60 border border-white/10 font-mono text-xs text-zinc-300 overflow-x-auto max-h-80">
            <pre className="whitespace-pre">
              {activeSnippet === 'curl' && curlSnippet}
              {activeSnippet === 'ts' && tsSnippet}
              {activeSnippet === 'python' && pythonSnippet}
            </pre>
          </div>

          {/* Webhook Events */}
          <div className="pt-2 space-y-2">
            <h4 className="text-xs font-bold uppercase font-mono tracking-wider text-zinc-400 flex items-center gap-1.5">
              <Webhook className="w-3.5 h-3.5 text-purple-400" />
              Supported Real-Time Webhook Signals
            </h4>
            <div className="grid grid-cols-2 gap-2 text-xs font-mono">
              <div className="p-2.5 rounded-xl bg-white/5 border border-white/5">
                <span className="text-pink-400">paywall.unlocked</span>
                <p className="text-[10px] text-zinc-400 mt-0.5">Triggered when fan buys VIP audio/media</p>
              </div>
              <div className="p-2.5 rounded-xl bg-white/5 border border-white/5">
                <span className="text-emerald-400">tip.received</span>
                <p className="text-[10px] text-zinc-400 mt-0.5">Dispatches immediate TTS voice praise</p>
              </div>
              <div className="p-2.5 rounded-xl bg-white/5 border border-white/5">
                <span className="text-amber-400">cyoa.branch_chosen</span>
                <p className="text-[10px] text-zinc-400 mt-0.5">Updates fan psych vector history</p>
              </div>
              <div className="p-2.5 rounded-xl bg-white/5 border border-white/5">
                <span className="text-cyan-400">deeprl.epoch_converged</span>
                <p className="text-[10px] text-zinc-400 mt-0.5">Broadcasts new action policy weights</p>
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-white/10 bg-[#0a0b12] flex justify-end">
          <button
            onClick={onClose}
            className="px-5 py-2 rounded-xl bg-white/10 hover:bg-white/20 text-white text-xs font-semibold cursor-pointer transition"
          >
            Close API Docs
          </button>
        </div>
      </div>
    </div>
  );
};
