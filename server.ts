import express from 'express';
import cors from 'cors';
import path from 'path';
import { fileURLToPath } from 'url';
import { CoreBridgeError, runCore } from './server/coreBridge.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = process.env.PORT || 3000;
const isProd = process.env.NODE_ENV === 'production';

app.use(cors());
app.use(express.json({ limit: '2mb' }));

function sendCoreError(res: express.Response, err: unknown) {
  const error = err instanceof CoreBridgeError ? err : new CoreBridgeError((err as Error)?.message || 'Unknown error', 500);
  res.status(error.status).json({ error: error.message, details: error.details });
}

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

const mediaJobs = new Map<string, WebMediaJob>();
const scheduledPosts = new Map<string, WebScheduledPost>();

// Canonical experiment / commerce / review data comes from spicecore.
app.get('/api/health', async (_req, res) => {
  try {
    const core = await runCore<Record<string, unknown>>('health');
    res.json({ ...core, node_uptime: process.uptime() });
  } catch (err) {
    sendCoreError(res, err);
  }
});

app.get('/api/personas', async (_req, res) => {
  try {
    res.json(await runCore('personas'));
  } catch (err) {
    sendCoreError(res, err);
  }
});

app.get('/api/candidates', async (req, res) => {
  try {
    res.json(await runCore('candidates', { status: req.query.status || null }));
  } catch (err) {
    sendCoreError(res, err);
  }
});

app.post('/api/candidates/propose', async (req, res) => {
  try {
    res.status(201).json(await runCore('propose', req.body || {}));
  } catch (err) {
    sendCoreError(res, err);
  }
});

app.post('/api/candidates/:id/review', async (req, res) => {
  try {
    res.json(await runCore('review', {
      candidate_id: String(req.params.id),
      decision: req.body?.decision,
      reviewer: req.body?.reviewer,
      note: req.body?.note || '',
    }));
  } catch (err) {
    sendCoreError(res, err);
  }
});

app.post('/api/candidates/:id/publish', async (req, res) => {
  try {
    const result: any = await runCore('publish', {
      candidate_id: String(req.params.id),
      url: req.body?.url,
      external_id: req.body?.external_id || null,
    });
    res.json(result.candidate || result);
  } catch (err) {
    sendCoreError(res, err);
  }
});

app.post('/api/candidates/:id/outcome', async (req, res) => {
  try {
    res.json(await runCore('outcome', {
      candidate_id: String(req.params.id),
      kind: req.body?.kind,
      amount_cents: req.body?.amount_cents || 0,
      external_id: req.body?.external_id || null,
    }));
  } catch (err) {
    sendCoreError(res, err);
  }
});

app.post('/api/candidates/:id/simulate', async (req, res) => {
  try {
    res.json(await runCore('simulate', {
      candidate_id: String(req.params.id),
      ...(req.body || {}),
    }));
  } catch (err) {
    sendCoreError(res, err);
  }
});

app.get('/api/stats', async (_req, res) => {
  try {
    res.json(await runCore('stats'));
  } catch (err) {
    sendCoreError(res, err);
  }
});

app.get('/api/events', async (req, res) => {
  try {
    const limit = req.query.limit ? Number(req.query.limit) : 100;
    res.json(await runCore('events', { limit }));
  } catch (err) {
    sendCoreError(res, err);
  }
});

app.get('/api/recommend', async (req, res) => {
  try {
    res.json(await runCore('recommend', {
      seed: req.query.seed !== undefined ? Number(req.query.seed) : null,
      exploration: req.query.exploration !== undefined ? Number(req.query.exploration) : 0.30,
    }));
  } catch (err) {
    sendCoreError(res, err);
  }
});

app.post('/api/briefs', async (req, res) => {
  try {
    res.json(await runCore('briefs', {
      theme: req.body?.theme,
      channel: req.body?.channel,
      seed: req.body?.seed ?? null,
    }));
  } catch (err) {
    sendCoreError(res, err);
  }
});

app.get('/api/knowledge', async (req, res) => {
  try {
    res.json(await runCore('knowledge', {
      query: typeof req.query.q === 'string' ? req.query.q : '',
      limit: req.query.limit ? Number(req.query.limit) : 20,
    }));
  } catch (err) {
    sendCoreError(res, err);
  }
});

app.get('/api/runtime-policy', async (_req, res) => {
  try {
    res.json(await runCore('policy'));
  } catch (err) {
    sendCoreError(res, err);
  }
});

app.post('/api/runtime-policy', async (req, res) => {
  try {
    res.json(await runCore('policy_update', {
      changes: req.body?.changes || {},
      actor: req.body?.actor,
      note: req.body?.note || '',
    }));
  } catch (err) {
    sendCoreError(res, err);
  }
});

app.get('/api/rl/status', async (_req, res) => {
  try {
    res.json(await runCore('rl_status'));
  } catch (err) {
    sendCoreError(res, err);
  }
});

app.get('/api/autopilot/status', async (_req, res) => {
  try {
    res.json(await runCore('autopilot_status'));
  } catch (err) {
    sendCoreError(res, err);
  }
});

app.post('/api/rl/train', async (req, res) => {
  try {
    res.json(await runCore('rl_train', {
      epochs: req.body?.epochs ?? 20,
      learning_rate: req.body?.learning_rate ?? 0.01,
    }));
  } catch (err) {
    sendCoreError(res, err);
  }
});

app.post('/api/knowledge', async (req, res) => {
  try {
    res.status(201).json(await runCore('knowledge_add', {
      source: req.body?.source,
      title: req.body?.title,
      body: req.body?.body,
      tags: req.body?.tags || [],
    }));
  } catch (err) {
    sendCoreError(res, err);
  }
});

// Media pipeline remains a separate transient adapter until a production renderer is configured.
app.get('/api/media-jobs', (_req, res) => {
  res.json(Array.from(mediaJobs.values()).sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)));
});

app.post('/api/media-jobs/create', async (req, res) => {
  try {
    const { persona_id, candidate_id, source_asset_uri, script, aspect_ratio = '9:16' } = req.body || {};
    const candidates: any[] = await runCore('candidates');
    const candidate = candidates.find(c => c.id === candidate_id);
    if (!candidate) return res.status(404).json({ error: 'Candidate not found in canonical spicecore ledger' });
    if (candidate.persona_id !== persona_id) return res.status(400).json({ error: 'Candidate/persona mismatch' });

    const id = `job_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;
    const job: WebMediaJob = {
      id,
      persona_id,
      candidate_id,
      source_asset_uri: source_asset_uri || candidate.asset_uri || '',
      script: script || '',
      aspect_ratio,
      status: 'planned',
      duration_seconds: 15,
      output_uri: null,
      video_provider: 'spice-video-engine',
      voice_provider: `voice-${persona_id}`,
      generation_cost_cents: 30,
      render_cost_cents: 10,
      created_at: new Date().toISOString(),
    };
    mediaJobs.set(id, job);
    res.status(201).json(job);
  } catch (err) {
    sendCoreError(res, err);
  }
});

app.post('/api/media-jobs/:id/render', (req, res) => {
  const job = mediaJobs.get(String(req.params.id));
  if (!job) return res.status(404).json({ error: 'Job not found' });
  job.status = 'rendering';
  job.output_uri = null;
  job.status = 'review_ready';
  job.qa_report = {
    passed: false,
    score: 0,
    checks: {
      renderer_configured: false,
    },
  };
  mediaJobs.set(job.id, job);
  res.json(job);
});

app.post('/api/media-jobs/:id/review', (req, res) => {
  const job = mediaJobs.get(String(req.params.id));
  if (!job) return res.status(404).json({ error: 'Job not found' });
  const { decision, reviewer, note } = req.body || {};
  if (!['approved', 'rejected', 'revise'].includes(decision)) {
    return res.status(400).json({ error: 'Invalid decision' });
  }
  if (decision === 'approved' && !job.qa_report?.passed) {
    return res.status(409).json({ error: 'Cannot approve media until a configured renderer produces a passing QA report' });
  }
  job.status = decision;
  job.reviewer = reviewer;
  job.review_note = note;
  mediaJobs.set(job.id, job);
  res.json(job);
});

app.get('/api/schedules', (_req, res) => {
  res.json(Array.from(scheduledPosts.values()).sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)));
});

app.post('/api/schedules/schedule', (req, res) => {
  const { media_job_id, platform, account_id, scheduled_at } = req.body || {};
  const job = mediaJobs.get(media_job_id);
  if (!job) return res.status(404).json({ error: 'Media job not found' });
  if (job.status !== 'approved') {
    return res.status(403).json({ error: `Cannot schedule media in state '${job.status}'. Only approved media can be scheduled.` });
  }

  const scheduleId = `sched_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;
  const post: WebScheduledPost = {
    schedule_id: scheduleId,
    candidate_id: job.candidate_id,
    media_job_id: job.id,
    platform: platform || 'instagram',
    account_id: account_id || 'official',
    scheduled_at: scheduled_at || new Date().toISOString(),
    status: 'scheduled',
    created_at: new Date().toISOString(),
  };
  scheduledPosts.set(scheduleId, post);
  job.status = 'scheduled';
  res.status(201).json(post);
});

app.post('/api/schedules/process-outbox', (_req, res) => {
  res.status(501).json({
    error: 'No production publisher adapter is configured. Scheduled records are retained but not falsely marked published.',
  });
});

async function startServer() {
  // Fail fast if the canonical Python engine is unavailable.
  await runCore('health');

  if (!isProd) {
    const { createServer: createViteServer } = await import('vite');
    const vite = await createViteServer({
      server: { middlewareMode: true, host: '0.0.0.0', port: Number(PORT) },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    app.use(express.static(path.resolve(__dirname, 'dist')));
    app.get('*', (_req, res) => {
      res.sendFile(path.resolve(__dirname, 'dist', 'index.html'));
    });
  }

  app.listen(Number(PORT), '0.0.0.0', () => {
    console.log(`Spice Hoes control plane running on http://0.0.0.0:${PORT}`);
  });
}

startServer().catch((err) => {
  console.error('Failed to start Spice Hoes control plane:', err);
  process.exit(1);
});
