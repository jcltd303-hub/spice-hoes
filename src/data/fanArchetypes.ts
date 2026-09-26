import { FanPsychProfile } from '../types';

export const FAN_PSYCH_PROFILES: FanPsychProfile[] = [
  {
    id: 'fan-whale-alex',
    name: 'Marcus "Vanguard" Chen',
    archetype: 'Whale Collector',
    budgetLevel: 'Ultra-High ($1,000+/mo)',
    vulnerabilities: [
      'Craves exclusive recognition & status over others',
      'Desires direct 1-on-1 access and whispered secrets',
      'Competes fiercely on public tipping leaderboards',
      'Weakness to aloof, unattainable feminine figures',
    ],
    sentiment: 0.94,
    relationshipTier: 'Whale Patron',
    pastInteractions: [
      'Tipped $500 on Zara Voss live stream for a 3-second acknowledgement',
      'Subscribed to Lila Hart Golden Whale Guardian for 8 consecutive months',
      'Requested custom voice note from Tess Wilder about staying disciplined',
    ],
  },
  {
    id: 'fan-simp-kevin',
    name: 'Kevin "Daydreamer" Miller',
    archetype: 'Devoted Simp',
    budgetLevel: 'Mid ($50-$100/mo)',
    vulnerabilities: [
      'Extreme emotional attachment to gentle, sweet interactions',
      'Believes he has a genuine romantic connection',
      'Always leaves supportive comments within 30 seconds of posting',
      'Saves every audio note to a private folder',
    ],
    sentiment: 0.98,
    relationshipTier: 'Inner Circle',
    pastInteractions: [
      'Purchased 14 "Goodnight Voice Notes" from Lila Hart',
      'Sends $15 strawberry boba tips twice weekly without prompt',
      'Left 3-paragraph essay defending Ruby Wren in controversial comment section',
    ],
  },
  {
    id: 'fan-sponsor-sophia',
    name: 'Sophia Sterling (Brand VP, Lumina Tech)',
    archetype: 'High-Ticket Sponsor',
    budgetLevel: 'Ultra-High ($1,000+/mo)',
    vulnerabilities: [
      'Obsessed with high engagement-to-follower ratios',
      'Needs brand safety assurance combined with viral edge',
      'Will pay $50,000 upfront for 3-part sponsored episodic integration',
    ],
    sentiment: 0.78,
    relationshipTier: 'Admirer',
    pastInteractions: [
      'Requested metrics deck for Tess Wilder biohacking affiliate campaign',
      'Auditioning Zara Voss for exclusive luxury smart-ring launch',
    ],
  },
  {
    id: 'fan-critic-damon',
    name: 'Damon Vance',
    archetype: 'Skeptical Critic',
    budgetLevel: 'Low/Free ($0-$15/mo)',
    vulnerabilities: [
      'Prides himself on seeing through "influencer tricks"',
      'Secretly addicted to the banter and hates when he is outsmarted',
      'Can be converted to high-payer if challenged intellectually or put in his place',
    ],
    sentiment: -0.25,
    relationshipTier: 'Casual Fan',
    pastInteractions: [
      'Commented: "This whole stream is calculated psychological bait"',
      'Got roasted by Ruby Wren in front of 40,000 viewers and secretly replayed the clip 20 times',
    ],
  },
];
