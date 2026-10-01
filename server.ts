import express from 'express';
import cors from 'cors';
import path from 'path';
import { fileURLToPath } from 'url';
import { store } from './server/store.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = process.env.PORT || 3000;
const isProd = process.env.NODE_ENV === 'production';

app.use(cors());
app.use(express.json());

// In-memory media jobs & scheduled posts for web UI synchronization
interface WebMediaJob {
  id: string;
  persona_id: string;
  candidate_id: string;
  source_asset_uri: string;
  script: string;
  aspect_ratio: string;
  status: 'planned' | 'rendering' | 'rendered' | 'qa_passed' | 'review_ready' | 'approved' | 'rejected' | 'revise' | 'scheduled' | 'published';
  duration_seconds: number;
  output_uri: string | null;
  video_provider: string;
  voice_provider: string;
  generation_cost_cents: number;
  render_cost_cents: number;
  reviewer?: string;
  review_note?: string;
  qa_report?: {
    passed: boolean;
    score: number;
    checks: Record<string, boolean>;
  };
  created_at: string;
}

interface WebScheduledPost {
  schedule_id: string;
  candidate_id: string;
  media_job_id: string;
  platform: string;
  account_id: string;
  scheduled_at: string;
  status: 'scheduled' | 'publishing' | 'published' | 'failed' | 'cancelled';
  canonical_url?: string;
  external_post_id?: string;
  created_at: string;
}

const mediaJobs: Map<string, WebMediaJob> = new Map();
const scheduledPosts: Map<string, WebScheduledPost> = new Map();

// Seed initial video job for Celeste Vale
const seedJobId = 'job_celeste_video_01';
mediaJobs.set(seedJobId, {
  id: seedJobId,
  persona_id: 'celeste_vale',
  candidate_id: store.getCandidates().find(c => c.persona_id === 'celeste_vale')?.id || 'cand_celeste',
  source_asset_uri: 'https://images.unsplash.com/photo-1600585154340-be6161a56a0c?w=800&auto=format&fit=crop&q=80',
  script: 'Architectural clarity requires deliberate composition. Every angle has intention. Tap link for the autumn portfolio.',
  aspect_ratio: '9:16',
  status: 'review_ready',
  duration_seconds: 16.0,
  output_uri: 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4',
  video_provider: 'luma-dream-machine',
  voice_provider: 'elevenlabs-celeste-v1',
  generation_cost_cents: 35,
  render_cost_cents: 12,
  qa_report: {
    passed: true,
    score: 0.94,
    checks: {
      file_integrity: true,
      resolution: true,
      aspect_ratio: true,
      duration: true,
      audio_present: true,
      fps: true
    }
  },
  created_at: new Date(Date.now() - 3600000).toISOString()
});

// --- API ROUTES ---

app.get('/api/health', (req, res) => {
  res.json({ status: 'ok', service: 'spice-hoes-core', uptime: process.uptime() });
});

app.get('/api/personas', (req, res) => {
  res.json(store.getPersonas());
});

app.get('/api/candidates', (req, res) => {
  const status = req.query.status as string | undefined;
  res.json(store.getCandidates(status));
});

app.post('/api/candidates/propose', (req, res) => {
  try {
    const candidate = store.proposeCandidate(req.body);
    res.status(201).json(candidate);
  } catch (err: any) {
    res.status(400).json({ error: err.message });
  }
});

app.post('/api/candidates/:id/review', (req, res) => {
  try {
    const { decision, reviewer, note } = req.body;
    const candidate = store.reviewCandidate(req.params.id, decision, reviewer, note);
    res.json(candidate);
  } catch (err: any) {
    res.status(400).json({ error: err.message });
  }
});

app.post('/api/candidates/:id/publish', (req, res) => {
  try {
    const { url, external_id } = req.body;
    const candidate = store.publishCandidate(req.params.id, url, external_id);
    res.json(candidate);
  } catch (err: any) {
    res.status(400).json({ error: err.message });
  }
});

app.post('/api/candidates/:id/outcome', (req, res) => {
  try {
    const { kind, amount_cents, external_id } = req.body;
    const event = store.recordOutcome(req.params.id, kind, amount_cents, external_id);
    res.json(event);
  } catch (err: any) {
    res.status(400).json({ error: err.message });
  }
});

app.post('/api/candidates/:id/simulate', (req, res) => {
  try {
    store.simulateTraffic(req.params.id, req.body || {});
    res.json({ success: true, stats: store.getStats() });
  } catch (err: any) {
    res.status(400).json({ error: err.message });
  }
});

// Media Pipeline Routes
app.get('/api/media-jobs', (req, res) => {
  res.json(Array.from(mediaJobs.values()).sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()));
});

app.post('/api/media-jobs/create', (req, res) => {
  try {
    const { persona_id, candidate_id, source_asset_uri, script, aspect_ratio = '9:16' } = req.body;
    const id = `job_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;
    const job: WebMediaJob = {
      id,
      persona_id,
      candidate_id,
      source_asset_uri,
      script,
      aspect_ratio,
      status: 'planned',
      duration_seconds: 15.0,
      output_uri: null,
      video_provider: 'spice-video-engine',
      voice_provider: `elevenlabs-${persona_id}`,
      generation_cost_cents: 30,
      render_cost_cents: 10,
      created_at: new Date().toISOString()
    };
    mediaJobs.set(id, job);
    res.status(201).json(job);
  } catch (err: any) {
    res.status(400).json({ error: err.message });
  }
});

app.post('/api/media-jobs/:id/render', (req, res) => {
  const job = mediaJobs.get(req.params.id);
  if (!job) return res.status(404).json({ error: 'Job not found' });

  job.status = 'rendering';
  // Simulate progressive rendering + technical QA passing
  job.output_uri = 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4';
  job.status = 'review_ready';
  job.qa_report = {
    passed: true,
    score: 0.95,
    checks: {
      file_integrity: true,
      resolution: true,
      aspect_ratio: true,
      duration: true,
      audio_present: true,
      fps: true
    }
  };
  mediaJobs.set(job.id, job);
  res.json(job);
});

app.post('/api/media-jobs/:id/review', (req, res) => {
  const job = mediaJobs.get(req.params.id);
  if (!job) return res.status(404).json({ error: 'Job not found' });
  const { decision, reviewer, note } = req.body;

  if (!['approved', 'rejected', 'revise'].includes(decision)) {
    return res.status(400).json({ error: 'Invalid decision' });
  }

  job.status = decision;
  job.reviewer = reviewer;
  job.review_note = note;
  mediaJobs.set(job.id, job);
  res.json(job);
});

// Scheduling & Outbox Routes
app.get('/api/schedules', (req, res) => {
  res.json(Array.from(scheduledPosts.values()).sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()));
});

app.post('/api/schedules/schedule', (req, res) => {
  const { media_job_id, platform, account_id, scheduled_at } = req.body;
  const job = mediaJobs.get(media_job_id);
  if (!job) return res.status(404).json({ error: 'Media job not found' });

  // REVIEW GATE: Only approved media can be scheduled
  if (job.status !== 'approved') {
    return res.status(403).json({ error: `Cannot schedule media in state '${job.status}'. Only human-approved media can be scheduled.` });
  }

  const scheduleId = `sched_${Date.now()}`;
  const post: WebScheduledPost = {
    schedule_id: scheduleId,
    candidate_id: job.candidate_id,
    media_job_id: job.id,
    platform: platform || 'instagram',
    account_id: account_id || 'official',
    scheduled_at: scheduled_at || new Date().toISOString(),
    status: 'scheduled',
    created_at: new Date().toISOString()
  };
  scheduledPosts.set(scheduleId, post);
  job.status = 'scheduled';
  mediaJobs.set(job.id, job);
  res.status(201).json(post);
});

app.post('/api/schedules/process-outbox', (req, res) => {
  const published: WebScheduledPost[] = [];
  scheduledPosts.forEach(post => {
    if (post.status === 'scheduled') {
      post.status = 'published';
      post.external_post_id = `post_${Math.random().toString(36).substring(2, 10)}`;
      post.canonical_url = `https://${post.platform}.com/@${post.account_id}/p/${post.external_post_id}`;
      published.push(post);

      const job = mediaJobs.get(post.media_job_id);
      if (job) {
        job.status = 'published';
        mediaJobs.set(job.id, job);
      }
    }
  });
  res.json({ processed_count: published.length, published });
});

app.get('/api/stats', (req, res) => {
  res.json(store.getStats());
});

app.get('/api/events', (req, res) => {
  const limit = req.query.limit ? parseInt(req.query.limit as string) : 100;
  res.json(store.getEvents(limit));
});

app.get('/api/recommend', (req, res) => {
  try {
    const seed = req.query.seed ? parseInt(req.query.seed as string) : undefined;
    const exploration = req.query.exploration ? parseFloat(req.query.exploration as string) : 0.30;
    res.json(store.recommendPolicy(seed, exploration));
  } catch (err: any) {
    res.status(400).json({ error: err.message });
  }
});

app.post('/api/briefs', (req, res) => {
  try {
    const { theme, channel, seed } = req.body;
    res.json(store.buildBriefs(theme, channel, seed));
  } catch (err: any) {
    res.status(400).json({ error: err.message });
  }
});

app.get('/api/knowledge', (req, res) => {
  const query = req.query.q as string | undefined;
  if (query) {
    res.json(store.searchKnowledge(query));
  } else {
    res.json(store.getKnowledge());
  }
});

// Vite middleware in dev or static serving in prod
async function startServer() {
  if (!isProd) {
    const { createServer: createViteServer } = await import('vite');
    const vite = await createViteServer({
      server: { middlewareMode: true, host: '0.0.0.0', port: 3000 },
      appType: 'spa'
    });
    app.use(vite.middlewares);
  } else {
    app.use(express.static(path.resolve(__dirname, 'dist')));
    app.get('*', (req, res) => {
      res.sendFile(path.resolve(__dirname, 'dist', 'index.html'));
    });
  }

  app.listen(Number(PORT), '0.0.0.0', () => {
    console.log(`Spice Hoes Server running on http://0.0.0.0:${PORT}`);
  });
}

startServer();
