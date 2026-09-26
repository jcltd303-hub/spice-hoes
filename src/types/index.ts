export type SpiceArchetype = 'Sporty' | 'Posh' | 'Ginger' | 'Scary' | 'Baby' | 'Custom';

export interface FeminineWilesMatrix {
  allureIndex: number; // 0-100: Raw magnetic attraction
  mysteryQuotient: number; // 0-100: Scarcity & aloofness
  playfulTease: number; // 0-100: Flirtatious banter & wit
  emotionalVulnerability: number; // 0-100: Weaponized intimacy / parasocial depth
  dominanceVsSweetness: number; // 0-100: 0=pure angelcore submissive, 100=commanding alpha
  paywallConversionRate: number; // 0-100: Propensity to trigger financial shellout
}

export interface VoiceConfig {
  voiceName: 'Kore' | 'Puck' | 'Fenrir' | 'Zephyr' | 'Charon';
  pitch: number; // -10 to +10
  cadence: string; // e.g. "Silky, low-pitch, aloof with cutting pause"
  sampleText: string;
}

export interface MonetizationTier {
  id: string;
  name: string;
  pricePerMonth: number;
  perks: string[];
  subscriberCount: number;
  churnRate: number;
  highlight?: boolean;
}

export interface DeepRLState {
  sentimentScore: number; // -1 to +1
  audienceFatigue: number; // 0 to 1
  exclusivityIndex: number; // 0 to 1
  fomoPressure: number; // 0 to 1
  parasocialDepth: number; // 0 to 1
  whaleEngagementRatio: number; // 0 to 1
}

export interface RLAction {
  id: string;
  name: string;
  code: 'MICRO_TEASE' | 'PARASOCIAL_BOND' | 'VELVET_PAYWALL' | 'ALOOF_SCARCITY' | 'CROSS_BLITZ';
  description: string;
  expectedReward: number;
  qValue: number;
  riskFactor: number;
}

export interface RLPolicy {
  epoch: number;
  epsilon: number; // Exploration rate
  learningRateAlpha: number;
  discountFactorGamma: number;
  rewardWeights: {
    revenueWeight: number; // alpha
    engagementWeight: number; // beta
    fatiguePenalty: number; // gamma
    retentionBonus: number; // delta
  };
  lastReward: number;
  cumulativeProfit: number;
  history: Array<{
    epoch: number;
    actionTaken: string;
    reward: number;
    revenue: number;
    sentiment: number;
  }>;
}

export interface InfluencerPersona {
  id: string;
  name: string;
  handle: string;
  spiceArchetype: SpiceArchetype;
  epithet: string;
  tagline: string;
  avatarUrl: string;
  bannerUrl: string;
  bio: string;
  aestheticTokens: string[];
  trendingNiches: string[];
  followersCount: number;
  mrr: number; // Monthly Recurring Revenue
  viralityIndex: number; // 0-100
  wiles: FeminineWilesMatrix;
  voice: VoiceConfig;
  monetizationTiers: MonetizationTier[];
  rlPolicy: RLPolicy;
  status: 'active' | 'optimizing' | 'idle';
  secretBackstory: string;
  targetDemographic: string;
  viralHooks: string[];
  paywallHooks: string[];
}

export interface FanPsychProfile {
  id: string;
  name: string;
  archetype: 'Whale Collector' | 'Devoted Simp' | 'High-Ticket Sponsor' | 'Skeptical Critic' | 'Casual Lurker';
  budgetLevel: 'Ultra-High ($1,000+/mo)' | 'High ($200-$500/mo)' | 'Mid ($50-$100/mo)' | 'Low/Free ($0-$15/mo)';
  vulnerabilities: string[];
  sentiment: number; // -1 to 1
  relationshipTier: 'Stranger' | 'Casual Fan' | 'Admirer' | 'Inner Circle' | 'Whale Patron';
  pastInteractions: string[];
}

export interface CYOAChoice {
  id: string;
  text: string;
  pathType: 'free' | 'flirt' | 'vip_paywall' | 'chaotic';
  requiredCostCredits?: number;
  requiredCostDollars?: number;
  sentimentImpact: number; // e.g. +12
  allureCheckRequirement?: number; // e.g. wiles.allureIndex > 70
  parasocialGain: number; // e.g. +25 XP
  reactionSnippet: string;
}

export interface LiveAudienceComment {
  id: string;
  username: string;
  avatar: string;
  badge?: 'Whale' | 'VIP' | 'Mod' | 'Sub';
  text: string;
  tipAmount?: number;
  timestamp: string;
}

export interface CYOAScene {
  id: string;
  scenarioTitle: string;
  location: string;
  environmentVibe: string;
  situation: string;
  personaDialogue: string;
  personaInternalMonologue: string;
  voiceScript: string;
  mediaTeaserUrl?: string;
  mediaType?: 'image' | 'audio' | 'locked_video';
  isPaywalledTeaser?: boolean;
  unlockCostCredits?: number;
  choices: CYOAChoice[];
  liveComments: LiveAudienceComment[];
}

export interface AgentDeliberation {
  agentName: 'Trend Scout' | 'Psych Architect' | 'Monetization Tactician' | 'CYOA Synthesizer' | 'Critic Evaluator';
  modelId: string;
  latencyMs: number;
  inputTokens: number;
  outputTokens: number;
  insights: string;
  recommendation: string;
  score: number; // 0-100
}

export interface MoAResult {
  orchestrationId: string;
  timestamp: string;
  objective: string;
  consensusScore: number;
  totalLatencyMs: number;
  totalTokens: number;
  estimatedCostUsd: number;
  agentDeliberations: AgentDeliberation[];
  finalSynthesis: {
    recommendedAction: string;
    projectedRevenueUplift: string;
    riskAssessment: string;
    narrativeHook: string;
  };
}

export interface TrendAnalysisResult {
  source: 'Google Search Grounding' | 'Real-Time Vector Scout';
  timestamp: string;
  macroThemes: Array<{
    theme: string;
    growthRate: string;
    sentimentScore: number;
    recommendedSpicePersona: SpiceArchetype;
    viralAudios: string[];
    monetizationTrigger: string;
  }>;
  viralAestheticKeywords: string[];
  emergingPaywallFormats: string[];
}

export interface ChannelPost {
  id: string;
  platform: 'instagram' | 'tiktok' | 'twitter' | 'vip_vault';
  personaId: string;
  title: string;
  mediaUrl: string;
  content: string;
  audioTrack?: string;
  likes: number;
  commentsCount: number;
  sharesCount: number;
  revenueGenerated: number;
  isLocked?: boolean;
  unlockPrice?: number;
  timestamp: string;
}
