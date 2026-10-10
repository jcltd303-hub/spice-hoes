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
const API_HOST = process.env.SPICE_API_HOST || '127.0.0.1';

const UI_ORIGINS = new Set([
  `http://127.0.0.1:${PORT}`, `http://localhost:${PORT}`,
  ...(process.env.SPICE_UI_ORIGINS || '').split(',').map(value => value.trim()).filter(Boolean),
]);
app.use('/api', (req, res, next) => {
  const origin = req.headers.origin;
  if (origin && !UI_ORIGINS.has(origin)) {
    res.status(403).json({ error: 'UI origin is not configured for this local controller' });
    return;
  }
  next();
});
app.use(cors({ origin: (origin, callback) => callback(null, !origin || UI_ORIGINS.has(origin)) }));
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

app.get('/api/compute/status', async (_req, res) => {
  try {
    res.json(await runCore('compute_status'));
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

app.post('/api/autopilot/run', async (req, res) => {
  try {
    res.status(201).json(await runCore('autopilot_run', {
      objective: req.body?.objective,
      channel: req.body?.channel,
      offer: req.body?.offer,
      variants: req.body?.variants ?? 3,
      seed: req.body?.seed ?? null,
      cost_cents_per_asset: req.body?.cost_cents_per_asset ?? 0,
    }));
  } catch (err) {
    sendCoreError(res, err);
  }
});

app.get('/api/doctor', async (_req, res) => {
  try {
    res.json(await runCore('doctor'));
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

// Media jobs are canonical in spicecore SQLite. Rendering and scheduling remain fail-closed
// until production adapters are configured and persistent scheduling is wired.
app.get('/api/media-jobs', async (_req, res) => {
  try {
    res.json(await runCore('media_jobs'));
  } catch (err) {
    sendCoreError(res, err);
  }
});

app.post('/api/media-jobs/create', async (req, res) => {
  try {
    res.status(201).json(await runCore('media_create', {
      persona_id: req.body?.persona_id,
      candidate_id: req.body?.candidate_id,
      source_asset_uri: req.body?.source_asset_uri,
      script: req.body?.script,
      aspect_ratio: req.body?.aspect_ratio || '9:16',
      soundtrack: req.body?.soundtrack,
      cta: req.body?.cta,
      offer: req.body?.offer,
      product_id: req.body?.product_id,
    }));
  } catch (err) {
    sendCoreError(res, err);
  }
});

app.post('/api/media-jobs/:id/render', async (req, res) => {
  try {
    res.json(await runCore('media_render', {
      media_job_id: String(req.params.id),
    }));
  } catch (err) {
    sendCoreError(res, err);
  }
});

app.post('/api/media-jobs/:id/review', async (req, res) => {
  try {
    res.json(await runCore('media_review', {
      media_job_id: String(req.params.id),
      decision: req.body?.decision,
      reviewer: req.body?.reviewer,
      note: req.body?.note || '',
    }));
  } catch (err) {
    sendCoreError(res, err);
  }
});

app.get('/api/schedules', (_req, res) => {
  res.json([]);
});

app.post('/api/schedules/schedule', (_req, res) => {
  res.status(501).json({
    error: 'Persistent scheduling is not wired yet; no schedule was created.',
  });
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

  app.listen(Number(PORT), API_HOST, () => {
    console.log(`Spice Hoes control plane running on http://${API_HOST}:${PORT}`);
  });
}

startServer().catch((err) => {
  console.error('Failed to start Spice Hoes control plane:', err);
  process.exit(1);
});
