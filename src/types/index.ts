export type PersonaType = 'Scary' | 'Sporty' | 'Baby' | 'Ginger' | 'Posh';

export interface Persona {
  id: string;
  name: string;
  type: PersonaType;
  age: number;
  height_cm: number;
  fictional: boolean;
  disclosure: string;
  hobbies: string[];
  favorite_book: string;
  backstory: string;
  heartbreak: string;
  voice: string;
  visual: string;
  themes: string[];
  version: string;
}

export type CandidateStatus = 'proposed' | 'approved' | 'rejected' | 'revise' | 'published';

export interface Candidate {
  id: string;
  persona_id: string;
  persona_name?: string;
  persona_version: string;
  theme: string;
  format: string;
  channel: string;
  offer: string;
  asset_uri: string | null;
  prompt: string | null;
  model: string | null;
  seed: string | null;
  cost_cents: number;
  status: CandidateStatus;
  created_at: string;
  reviewer?: string;
  review_note?: string;
  published_url?: string;
}

export interface SystemEvent {
  seq: number;
  id: string;
  ts: string;
  kind: string;
  external_id?: string | null;
  payload: Record<string, any>;
}

export interface PersonaStats {
  persona_id: string;
  name: string;
  published: number;
  impressions: number;
  clicks: number;
  revenue_cents: number;
  refund_cents: number;
  cost_cents: number;
  net_cents: number;
}

export interface PolicyArm {
  persona_id: string;
  published: number;
  estimated_net_cents_per_published: number;
  selection_probability: number;
}

export interface PolicyRecommendation {
  policy_version: string;
  method: string;
  persona_id: string;
  name: string;
  selection_probability: number;
  estimated_net_cents_per_published: number;
  supporting_published_count: number;
  uncertainty_note: string;
  ranking_change_condition: string;
  all_arms: PolicyArm[];
}

export interface Brief {
  persona_id: string;
  persona_name: string;
  reference_version: string;
  theme: string;
  channel: string;
  interest: string;
  format: string;
  evidence_level: string;
  prompt: string;
  test_question: string;
  disclosure: string;
}

export interface KnowledgeItem {
  id: string;
  ts: string;
  source: string;
  title: string;
  body: string;
  tags: string[];
  approved: boolean;
}
