import crypto from 'crypto';
import { Persona, Candidate, SystemEvent, PersonaStats, PolicyRecommendation, Brief, KnowledgeItem } from '../src/types/index.js';

export const INITIAL_PERSONAS: Persona[] = [
  {
    id: 'zara_voss',
    name: 'Zara Voss',
    type: 'Scary',
    age: 29,
    height_cm: 169,
    fictional: true,
    disclosure: 'Fictional AI-generated adult character',
    hobbies: ['percussion', 'night markets', 'urban sketching'],
    favorite_book: 'The City We Became',
    backstory: 'A percussionist and night-market organizer who built her own events after her first music collective dissolved.',
    heartbreak: 'Her first creative partnership ended when a collaborator took credit for their work.',
    voice: 'Direct, funny, kinetic',
    visual: 'Distinctive short curls, vivid color blocks, original streetwear',
    themes: ['city nights', 'rhythm', 'candid opinions'],
    version: '9f84a1e94812'
  },
  {
    id: 'tess_wilder',
    name: 'Tess Wilder',
    type: 'Sporty',
    age: 27,
    height_cm: 171,
    fictional: true,
    disclosure: 'Fictional AI-generated adult character',
    hobbies: ['climbing', 'recreational football', 'retro games'],
    favorite_book: 'Endure',
    backstory: 'A rec-league keeper who started teaching beginners after a team fallout.',
    heartbreak: 'A teammate she trusted quit their shared project without warning.',
    voice: 'Competitive, encouraging, quick-witted',
    visual: 'Functional training gear, cropped dark hair, original graphics',
    themes: ['training', 'challenges', 'practical gear'],
    version: '7b32cd415082'
  },
  {
    id: 'lila_hart',
    name: 'Lila Hart',
    type: 'Baby',
    age: 28,
    height_cm: 160,
    fictional: true,
    disclosure: 'Fictional AI-generated adult character',
    hobbies: ['ceramics', 'dinner parties', 'herb gardening'],
    favorite_book: 'The House in the Cerulean Sea',
    backstory: 'A ceramic artist who runs a small studio and hosts elaborate dinners.',
    heartbreak: 'She left a partner who wanted her to abandon her studio.',
    voice: 'Warm, witty, playful and unmistakably adult',
    visual: 'Pastel ceramics and adult contemporary styling; no childlike sexual styling',
    themes: ['studio work', 'hosting', 'small joys'],
    version: '5c83ea291410'
  },
  {
    id: 'ruby_wren',
    name: 'Ruby Wren',
    type: 'Ginger',
    age: 30,
    height_cm: 164,
    fictional: true,
    disclosure: 'Fictional AI-generated adult character',
    hobbies: ['zine writing', 'astronomy', 'karaoke'],
    favorite_book: 'The Dispossessed',
    backstory: 'A zine writer who began self-publishing after a failed gallery collaboration.',
    heartbreak: 'A gallery partner dismissed her writing just before an exhibition.',
    voice: 'Fiery, eloquent, irreverent',
    visual: 'Copper-toned hair, colorful modern silhouettes, unique iconography',
    themes: ['mini essays', 'stargazing', 'creative arguments'],
    version: '2e19ba670498'
  },
  {
    id: 'celeste_vale',
    name: 'Celeste Vale',
    type: 'Posh',
    age: 32,
    height_cm: 166,
    fictional: true,
    disclosure: 'Fictional AI-generated adult character',
    hobbies: ['boutique hotel design', 'jazz collecting', 'architecture'],
    favorite_book: 'The Secret History',
    backstory: 'A designer who chose an independent practice over a prestigious but controlling employer.',
    heartbreak: 'An old mentor claimed credit for a defining interior design.',
    voice: 'Precise, dryly funny, selective',
    visual: 'Original tailored looks, sculptural jewelry, deliberate composition',
    themes: ['design', 'curated portraits', 'jazz evenings'],
    version: '4d61fc882019'
  }
];

export class AppStore {
  private personas: Persona[] = [...INITIAL_PERSONAS];
  private candidates: Map<string, Candidate> = new Map();
  private events: SystemEvent[] = [];
  private knowledge: KnowledgeItem[] = [];
  private eventSeq = 1;

  constructor() {
    this.seedInitialData();
  }

  private recordEvent(kind: string, payload: Record<string, any>, externalId?: string | null): SystemEvent {
    if (externalId) {
      const existing = this.events.find(e => e.external_id === externalId);
      if (existing) {
        if (existing.kind !== kind || JSON.stringify(existing.payload) !== JSON.stringify(payload)) {
          throw new Error('External ID already used for a different event');
        }
        return existing;
      }
    }
    const event: SystemEvent = {
      seq: this.eventSeq++,
      id: crypto.randomUUID(),
      ts: new Date().toISOString(),
      kind,
      external_id: externalId || null,
      payload
    };
    this.events.push(event);
    return event;
  }

  private seedInitialData() {
    // Seed initial knowledge base
    this.addKnowledge(
      'Canon Dossier',
      'Original Archetype Principles',
      'The five characters are hypotheses. The look must arise from authentic adult interests rather than costumes. Strictly adult age >= 27. No youth-coded sexual styling.',
      ['guidelines', 'canon', 'safety']
    );
    this.addKnowledge(
      'Infrastructure Plan',
      'Compute and Attribution Strategy',
      'Exploration via contextual bandit before reinforcement learning. Disclosed fictional identities, adult-only audiences, original likenesses define the eligible action set.',
      ['bandit', 'infrastructure', 'compliance']
    );

    // Seed candidate 1: Proposed for Zara Voss
    const c1Id = crypto.randomUUID();
    this.candidates.set(c1Id, {
      id: c1Id,
      persona_id: 'zara_voss',
      persona_name: 'Zara Voss',
      persona_version: '9f84a1e94812',
      theme: 'night market percussion',
      format: 'still',
      channel: 'Instagram',
      offer: 'VIP soundcheck pass',
      asset_uri: 'https://images.unsplash.com/photo-1514525253161-7a46d19cd819?w=800&auto=format&fit=crop&q=80',
      prompt: 'Original fictional AI-generated adult character Zara Voss, age 29; distinctive original look: Distinctive short curls, vivid color blocks, original streetwear; engaged in percussion; theme: night market percussion; candid detail, coherent anatomy, same identity across the series. Do not resemble a public figure. No youth-coded sexual styling.',
      model: 'spice-diffusion-xl-v2',
      seed: '48201',
      cost_cents: 15,
      status: 'proposed',
      created_at: new Date(Date.now() - 3600000 * 4).toISOString()
    });
    this.recordEvent('candidate_proposed', {
      candidate_id: c1Id,
      persona_id: 'zara_voss',
      theme: 'night market percussion',
      channel: 'Instagram'
    });

    // Seed candidate 2: Proposed for Lila Hart
    const c2Id = crypto.randomUUID();
    this.candidates.set(c2Id, {
      id: c2Id,
      persona_id: 'lila_hart',
      persona_name: 'Lila Hart',
      persona_version: '5c83ea291410',
      theme: 'terracotta wheel throw',
      format: 'still',
      channel: 'Patreon',
      offer: 'Handmade glaze recipe guide',
      asset_uri: 'https://images.unsplash.com/photo-1565193566173-7a0ee3dbe261?w=800&auto=format&fit=crop&q=80',
      prompt: 'Original fictional AI-generated adult character Lila Hart, age 28; distinctive original look: Pastel ceramics and adult contemporary styling; engaged in ceramics; theme: terracotta wheel throw; candid detail, coherent anatomy, same identity across the series.',
      model: 'spice-diffusion-xl-v2',
      seed: '99214',
      cost_cents: 15,
      status: 'proposed',
      created_at: new Date(Date.now() - 3600000 * 2).toISOString()
    });
    this.recordEvent('candidate_proposed', {
      candidate_id: c2Id,
      persona_id: 'lila_hart',
      theme: 'terracotta wheel throw',
      channel: 'Patreon'
    });

    // Seed candidate 3: Published for Celeste Vale with historical clicks & revenue
    const c3Id = crypto.randomUUID();
    this.candidates.set(c3Id, {
      id: c3Id,
      persona_id: 'celeste_vale',
      persona_name: 'Celeste Vale',
      persona_version: '4d61fc882019',
      theme: 'brutalist hotel lounge',
      format: 'still',
      channel: 'Substack',
      offer: 'Curated architectural portfolio quarterly',
      asset_uri: 'https://images.unsplash.com/photo-1600585154340-be6161a56a0c?w=800&auto=format&fit=crop&q=80',
      prompt: 'Original fictional AI-generated adult character Celeste Vale, age 32; distinctive original look: Original tailored looks, sculptural jewelry, deliberate composition; engaged in boutique hotel design.',
      model: 'spice-diffusion-xl-v2',
      seed: '31049',
      cost_cents: 25,
      status: 'published',
      created_at: new Date(Date.now() - 86400000 * 2).toISOString(),
      reviewer: 'lead_operator',
      review_note: 'Approved. Exceptional composition and exact palette alignment.',
      published_url: 'https://substack.com/@celeste-vale/p/brutalist-escapes'
    });
    this.recordEvent('candidate_proposed', { candidate_id: c3Id, persona_id: 'celeste_vale' });
    this.recordEvent('asset_reviewed', { candidate_id: c3Id, decision: 'approved', reviewer: 'lead_operator' });
    this.recordEvent('content_published', { candidate_id: c3Id, url: 'https://substack.com/@celeste-vale/p/brutalist-escapes' });

    // Seed some impressions and purchases for Celeste Vale
    for (let i = 0; i < 48; i++) {
      this.recordEvent('impression', { candidate_id: c3Id, persona_id: 'celeste_vale', amount_cents: 0 });
    }
    for (let i = 0; i < 9; i++) {
      this.recordEvent('click', { candidate_id: c3Id, persona_id: 'celeste_vale', amount_cents: 0 });
    }
    this.recordEvent('purchase', { candidate_id: c3Id, persona_id: 'celeste_vale', amount_cents: 3500 });
    this.recordEvent('purchase', { candidate_id: c3Id, persona_id: 'celeste_vale', amount_cents: 2500 });

    // Seed candidate 4: Published for Tess Wilder
    const c4Id = crypto.randomUUID();
    this.candidates.set(c4Id, {
      id: c4Id,
      persona_id: 'tess_wilder',
      persona_name: 'Tess Wilder',
      persona_version: '7b32cd415082',
      theme: 'bouldering problem 5b',
      format: 'still',
      channel: 'TikTok',
      offer: 'Grip training mobility program',
      asset_uri: 'https://images.unsplash.com/photo-1522163182402-834f871fd851?w=800&auto=format&fit=crop&q=80',
      prompt: 'Original fictional AI-generated adult character Tess Wilder, age 27; distinctive original look: Functional training gear, cropped dark hair; engaged in climbing.',
      model: 'spice-diffusion-xl-v2',
      seed: '51102',
      cost_cents: 20,
      status: 'published',
      created_at: new Date(Date.now() - 86400000).toISOString(),
      reviewer: 'lead_operator',
      review_note: 'Sharp athletic action shot.',
      published_url: 'https://tiktok.com/@tesswilder_climb'
    });
    this.recordEvent('candidate_proposed', { candidate_id: c4Id, persona_id: 'tess_wilder' });
    this.recordEvent('asset_reviewed', { candidate_id: c4Id, decision: 'approved', reviewer: 'lead_operator' });
    this.recordEvent('content_published', { candidate_id: c4Id, url: 'https://tiktok.com/@tesswilder_climb' });
    for (let i = 0; i < 30; i++) {
      this.recordEvent('impression', { candidate_id: c4Id, persona_id: 'tess_wilder', amount_cents: 0 });
    }
    for (let i = 0; i < 6; i++) {
      this.recordEvent('click', { candidate_id: c4Id, persona_id: 'tess_wilder', amount_cents: 0 });
    }
    this.recordEvent('purchase', { candidate_id: c4Id, persona_id: 'tess_wilder', amount_cents: 1800 });
  }

  // --- API METHODS ---

  getPersonas(): Persona[] {
    return this.personas;
  }

  getPersona(id: string): Persona | undefined {
    return this.personas.find(p => p.id === id);
  }

  getCandidates(statusFilter?: string): Candidate[] {
    const list = Array.from(this.candidates.values());
    list.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
    if (statusFilter) {
      return list.filter(c => c.status === statusFilter);
    }
    return list;
  }

  getCandidate(id: string): Candidate {
    const candidate = this.candidates.get(id);
    if (!candidate) {
      throw new Error(`Unknown candidate: ${id}`);
    }
    return candidate;
  }

  proposeCandidate(params: {
    persona_id: string;
    theme: string;
    format: string;
    channel: string;
    offer: string;
    asset_uri?: string;
    prompt?: string;
    model?: string;
    seed?: string;
    cost_cents?: number;
  }): Candidate {
    const persona = this.getPersona(params.persona_id);
    if (!persona) throw new Error(`Unknown persona: ${params.persona_id}`);
    if (!params.theme || !params.format || !params.channel || !params.offer) {
      throw new Error('Theme, format, channel, and offer are required');
    }

    const cid = crypto.randomUUID();
    const candidate: Candidate = {
      id: cid,
      persona_id: persona.id,
      persona_name: persona.name,
      persona_version: persona.version,
      theme: params.theme.trim(),
      format: params.format.trim(),
      channel: params.channel.trim(),
      offer: params.offer.trim(),
      asset_uri: params.asset_uri || null,
      prompt: params.prompt || null,
      model: params.model || 'spice-diffusion-xl-v2',
      seed: params.seed || Math.floor(Math.random() * 100000).toString(),
      cost_cents: params.cost_cents ?? 15,
      status: 'proposed',
      created_at: new Date().toISOString()
    };

    this.candidates.set(cid, candidate);
    this.recordEvent('candidate_proposed', {
      candidate_id: cid,
      persona_id: persona.id,
      persona_version: persona.version,
      theme: candidate.theme,
      format: candidate.format,
      channel: candidate.channel,
      offer: candidate.offer,
      cost_cents: candidate.cost_cents
    });

    return candidate;
  }

  reviewCandidate(cid: string, decision: 'approved' | 'rejected' | 'revise', reviewer: string, note = ''): Candidate {
    if (!reviewer || !reviewer.trim()) {
      throw new Error('Reviewer name is required');
    }
    const current = this.getCandidate(cid);
    if (current.status !== 'proposed') {
      throw new Error('Candidate has already been reviewed; create a new revision');
    }

    current.status = decision;
    current.reviewer = reviewer.trim();
    current.review_note = note.trim();
    this.candidates.set(cid, current);

    this.recordEvent('asset_reviewed', {
      candidate_id: cid,
      persona_id: current.persona_id,
      decision,
      reviewer: current.reviewer,
      note: current.review_note
    });

    return current;
  }

  publishCandidate(cid: string, url: string, externalId?: string | null): Candidate {
    const current = this.getCandidate(cid);
    if (current.status !== 'approved') {
      throw new Error('Publishing requires an approved candidate');
    }
    if (!url || !url.trim()) {
      throw new Error('URL is required for publishing');
    }

    current.status = 'published';
    current.published_url = url.trim();
    this.candidates.set(cid, current);

    this.recordEvent('content_published', {
      candidate_id: cid,
      persona_id: current.persona_id,
      url: current.published_url
    }, externalId);

    return current;
  }

  recordOutcome(cid: string, kind: 'impression' | 'click' | 'purchase' | 'refund' | 'distribution_cost', amountCents = 0, externalId?: string | null): SystemEvent {
    const current = this.getCandidate(cid);
    if (current.status !== 'published') {
      throw new Error('Outcomes require published candidates');
    }
    if (['purchase', 'refund', 'distribution_cost'].includes(kind) && amountCents <= 0) {
      throw new Error('Monetary outcomes require a positive amount in cents');
    }

    return this.recordEvent(kind, {
      candidate_id: cid,
      persona_id: current.persona_id,
      amount_cents: amountCents
    }, externalId);
  }

  simulateTraffic(cid: string, options: { impressions?: number; clicks?: number; purchases?: number; purchaseCents?: number; refunds?: number; refundCents?: number }): void {
    const current = this.getCandidate(cid);
    if (current.status !== 'published') {
      throw new Error('Traffic simulation requires a published candidate');
    }

    const {
      impressions = 20,
      clicks = 3,
      purchases = 1,
      purchaseCents = 2500,
      refunds = 0,
      refundCents = 0
    } = options;

    for (let i = 0; i < impressions; i++) {
      this.recordOutcome(cid, 'impression', 0);
    }
    for (let i = 0; i < clicks; i++) {
      this.recordOutcome(cid, 'click', 0);
    }
    for (let i = 0; i < purchases; i++) {
      this.recordOutcome(cid, 'purchase', purchaseCents);
    }
    for (let i = 0; i < refunds; i++) {
      this.recordOutcome(cid, 'refund', refundCents);
    }
  }

  getStats(): PersonaStats[] {
    const result: PersonaStats[] = [];

    for (const persona of this.personas) {
      const candidatesForPersona = Array.from(this.candidates.values()).filter(c => c.persona_id === persona.id);
      const published = candidatesForPersona.filter(c => c.status === 'published').length;
      const candidateCosts = candidatesForPersona.reduce((sum, c) => sum + (c.cost_cents || 0), 0);

      const sums = {
        impression: 0,
        click: 0,
        purchase: 0,
        refund: 0,
        distribution_cost: 0
      };

      for (const ev of this.events) {
        if (ev.payload?.persona_id === persona.id && ev.kind in sums) {
          const kind = ev.kind as keyof typeof sums;
          if (['purchase', 'refund', 'distribution_cost'].includes(kind)) {
            sums[kind] += (ev.payload.amount_cents || 0);
          } else {
            sums[kind] += 1;
          }
        }
      }

      const totalCost = candidateCosts + sums.distribution_cost;
      const netCents = sums.purchase - sums.refund - totalCost;

      result.push({
        persona_id: persona.id,
        name: persona.name,
        published,
        impressions: sums.impression,
        clicks: sums.click,
        revenue_cents: sums.purchase,
        refund_cents: sums.refund,
        cost_cents: totalCost,
        net_cents: netCents
      });
    }

    return result;
  }

  recommendPolicy(seed?: number, exploration = 0.30): PolicyRecommendation {
    const stats = this.getStats();
    if (!stats.length || exploration < 0 || exploration > 1) {
      throw new Error('Need arms and an exploration fraction between 0 and 1');
    }

    // A one-observation zero-reward prior prevents a single sale from determining portfolio
    const values = stats.map(s => s.net_cents / (s.published + 1));
    const untestedIndices = stats.map((s, idx) => s.published === 0 ? idx : -1).filter(idx => idx !== -1);

    let probabilities: number[] = [];
    let method = '';

    if (untestedIndices.length > 0) {
      probabilities = stats.map((_, idx) => untestedIndices.includes(idx) ? 1.0 / untestedIndices.length : 0.0);
      method = 'untested_rotation';
    } else {
      let leaderIndex = 0;
      let maxVal = -Infinity;
      values.forEach((v, idx) => {
        if (v > maxVal) {
          maxVal = v;
          leaderIndex = idx;
        }
      });

      probabilities = stats.map(() => exploration / stats.length);
      probabilities[leaderIndex] += (1 - exploration);
      method = 'epsilon_greedy';
    }

    // Deterministic or pseudo-random selection
    let chosenIndex = 0;
    const r = (seed !== undefined) ? ((Math.sin(seed) + 1) / 2) : Math.random();
    let cumulative = 0;
    for (let i = 0; i < probabilities.length; i++) {
      cumulative += probabilities[i];
      if (r <= cumulative) {
        chosenIndex = i;
        break;
      }
    }

    const chosen = stats[chosenIndex];

    return {
      policy_version: 'epsilon-greedy-v1',
      method,
      persona_id: chosen.persona_id,
      name: chosen.name,
      selection_probability: Number(probabilities[chosenIndex].toFixed(4)),
      estimated_net_cents_per_published: Number(values[chosenIndex].toFixed(2)),
      supporting_published_count: chosen.published,
      uncertainty_note: 'Exploratory contextual bandit heuristic; auditable decision record.',
      ranking_change_condition: 'Changes when additional recorded net outcomes shift the smoothed arm ranking.',
      all_arms: stats.map((s, idx) => ({
        persona_id: s.persona_id,
        published: s.published,
        estimated_net_cents_per_published: Number(values[idx].toFixed(2)),
        selection_probability: Number(probabilities[idx].toFixed(4))
      }))
    };
  }

  buildBriefs(theme: string, channel: string, seed?: number): Brief[] {
    if (!theme || !theme.trim() || !channel || !channel.trim()) {
      throw new Error('Theme and channel are required');
    }

    return this.personas.map((persona, idx) => {
      const interests = persona.hobbies;
      const hobbyIdx = seed !== undefined ? Math.abs((seed + idx) % interests.length) : Math.floor(Math.random() * interests.length);
      const chosen = interests[hobbyIdx];

      const prompt = `Original fictional AI-generated adult character ${persona.name}, age ${persona.age}; ` +
        `distinctive original look: ${persona.visual}; engaged in ${chosen}; ` +
        `theme: ${theme.trim()}; candid detail, coherent anatomy, same identity across the series. ` +
        `Do not resemble a public figure. No youth-coded sexual styling.`;

      return {
        persona_id: persona.id,
        persona_name: persona.name,
        reference_version: persona.version,
        theme: theme.trim(),
        channel: channel.trim(),
        interest: chosen,
        format: 'still',
        evidence_level: 'hypothesis',
        prompt,
        test_question: `Does ${theme.trim()} featuring ${chosen} draw qualified engagement for ${persona.name}?`,
        disclosure: persona.disclosure
      };
    });
  }

  getEvents(limit = 100): SystemEvent[] {
    const copy = [...this.events];
    copy.reverse();
    return copy.slice(0, limit);
  }

  getKnowledge(): KnowledgeItem[] {
    return this.knowledge;
  }

  addKnowledge(source: string, title: string, body: string, tags: string[] = [], approved = true): KnowledgeItem {
    const item: KnowledgeItem = {
      id: crypto.randomUUID(),
      ts: new Date().toISOString(),
      source: source.trim(),
      title: title.trim(),
      body: body.trim(),
      tags: Array.from(new Set(tags)).sort(),
      approved
    };
    this.knowledge.push(item);
    this.recordEvent('knowledge_added', {
      knowledge_id: item.id,
      title: item.title,
      source: item.source,
      tags: item.tags
    });
    return item;
  }

  searchKnowledge(query: string): KnowledgeItem[] {
    const tokens = (query || '').toLowerCase().match(/[a-z0-9][a-z0-9_-]{1,}/g) || [];
    if (!tokens.length) return this.knowledge.slice(0, 10);

    return this.knowledge.filter(k => {
      const text = `${k.title} ${k.body} ${k.source} ${k.tags.join(' ')}`.toLowerCase();
      return tokens.some(token => text.includes(token));
    });
  }
}

export const store = new AppStore();
