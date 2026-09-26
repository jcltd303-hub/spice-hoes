import {
  InfluencerPersona,
  TrendAnalysisResult,
  MoAResult,
  CYOAScene,
  CYOAChoice,
  FanPsychProfile,
  RLPolicy,
} from '../types';

let audioCtx: AudioContext | null = null;

function getAudioContext(): AudioContext {
  if (!audioCtx) {
    const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
    audioCtx = new AudioContextClass({ sampleRate: 24000 });
  }
  if (audioCtx.state === 'suspended') {
    audioCtx.resume();
  }
  return audioCtx;
}

export async function playTtsVoice(text: string, voiceName: string = 'Kore'): Promise<void> {
  try {
    const res = await fetch('/api/tts/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, voiceName }),
    });

    const data = await res.json();

    if (data.success && data.base64Audio) {
      await playRawPcmAudio(data.base64Audio, data.sampleRate || 24000);
      return;
    }

    // Fallback to Web Speech API
    playBrowserSpeech(text, voiceName);
  } catch (err) {
    console.warn('TTS request error, using browser speech fallback:', err);
    playBrowserSpeech(text, voiceName);
  }
}

export async function playRawPcmAudio(base64: string, sampleRate = 24000): Promise<void> {
  const binaryString = atob(base64);
  const len = binaryString.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) {
    bytes[i] = binaryString.charCodeAt(i);
  }

  // Gemini returns 16-bit PCM little-endian
  const int16Array = new Int16Array(bytes.buffer);
  const float32Array = new Float32Array(int16Array.length);
  for (let i = 0; i < int16Array.length; i++) {
    float32Array[i] = int16Array[i] / 32768.0;
  }

  const ctx = getAudioContext();
  const audioBuffer = ctx.createBuffer(1, float32Array.length, sampleRate);
  audioBuffer.copyToChannel(float32Array, 0);

  const source = ctx.createBufferSource();
  source.buffer = audioBuffer;
  source.connect(ctx.destination);
  source.start(0);
}

export function playBrowserSpeech(text: string, voiceArchetype = 'Kore') {
  if (!('speechSynthesis' in window)) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  
  if (voiceArchetype === 'Fenrir') {
    utterance.rate = 1.15;
    utterance.pitch = 1.1;
  } else if (voiceArchetype === 'Zephyr') {
    utterance.rate = 0.92;
    utterance.pitch = 1.25;
  } else if (voiceArchetype === 'Charon') {
    utterance.rate = 0.95;
    utterance.pitch = 0.85;
  } else if (voiceArchetype === 'Puck') {
    utterance.rate = 1.1;
    utterance.pitch = 1.05;
  } else {
    // Kore
    utterance.rate = 1.0;
    utterance.pitch = 0.95;
  }

  window.speechSynthesis.speak(utterance);
}

export async function fetchHealth() {
  const res = await fetch('/api/health');
  return res.json();
}

export async function analyzeTrends(category?: string): Promise<TrendAnalysisResult> {
  const res = await fetch('/api/trends/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ category }),
  });
  if (!res.ok) throw new Error('Failed to analyze trends');
  return res.json();
}

export async function orchestrateMoA(persona: InfluencerPersona, objective?: string): Promise<MoAResult> {
  const res = await fetch('/api/moa/orchestrate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ persona, objective }),
  });
  if (!res.ok) throw new Error('Failed to orchestrate MoA');
  return res.json();
}

export async function requestCYOAStep(params: {
  persona: InfluencerPersona;
  fanProfile: FanPsychProfile;
  previousSceneId?: string;
  choiceTaken?: CYOAChoice;
  history?: any[];
  creditsAvailable?: number;
}): Promise<CYOAScene> {
  const res = await fetch('/api/cyoa/step', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error('Failed to generate CYOA step');
  return res.json();
}

export async function executeDeepRLStep(params: {
  persona: InfluencerPersona;
  currentPolicy: RLPolicy;
  actionCode: string;
}) {
  const res = await fetch('/api/deeprl/step', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error('DeepRL step failed');
  return res.json();
}

export async function generatePersona(params: {
  spiceArchetype: string;
  niche: string;
  customPrompt?: string;
  allureTarget?: number;
}): Promise<InfluencerPersona> {
  const res = await fetch('/api/personas/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error('Failed to generate persona');
  return res.json();
}
