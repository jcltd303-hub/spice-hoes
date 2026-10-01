"""Command-line MVP for running the entire reviewed experiment loop."""

import argparse
import json
import secrets
from http.server import HTTPServer
from pathlib import Path

from .core import Store, load_personas
from .autonomy import plan_next_batch
from .assetflow import produce_job
from .identityflow import run_identity_batch
from .identityref import select_identity
from .sceneflow import generate_scene,identity_inpaint,transfer_identity,SCENES
from .policy import recommend
from .moa import deliberate
from .localdream import generate as localdream_generate, probe as localdream_probe
from .rag import LocalRAG
from .orchestration import write_n8n
from .production import free_production_plan, write_job
from .web import make_handler
from .workflow import build_briefs


def main(argv=None):
    parser = argparse.ArgumentParser(prog='spicecore')
    parser.add_argument('--db', default='data/experiments.sqlite')
    parser.add_argument('--personas', default='personas')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('init')
    sub.add_parser('personas')
    sub.add_parser('stats')
    sub.add_parser('events')
    scene = sub.add_parser('identity-scene')
    scene.add_argument('scene', choices=tuple(SCENES))
    scene.add_argument('--persona', default='celeste_vale')
    scene.add_argument('--output')
    scene.add_argument('--seed', type=int, default=100)
    scene.add_argument('--denoise', type=float, default=0.45)
    scene.add_argument('--server-url')
    scene.add_argument('--reference-dir', default='identity/references')
    scene.add_argument('--composition-only', action='store_true')
    xfer = sub.add_parser('identity-transfer')
    xfer.add_argument('scene_asset')
    xfer.add_argument('--persona', default='celeste_vale')
    xfer.add_argument('--output')
    xfer.add_argument('--endpoint')
    xfer.add_argument('--strength', type=float, default=0.85)
    xfer.add_argument('--reference-dir', default='identity/references')
    inp = sub.add_parser('identity-inpaint')
    inp.add_argument('scene_asset')
    inp.add_argument('--persona', default='celeste_vale')
    inp.add_argument('--output')
    inp.add_argument('--seed', type=int, default=200)
    inp.add_argument('--denoise', type=float, default=0.55)
    inp.add_argument('--server-url')
    inp.add_argument('--reference-dir', default='identity/references')
    inp.add_argument('--invert-mask', action='store_true')
    sel = sub.add_parser('select-identity')
    sel.add_argument('candidate_id')
    sel.add_argument('--persona', default='celeste_vale')
    sel.add_argument('--reference-dir', default='identity/references')
    ident = sub.add_parser('identity-batch')
    ident.add_argument('--persona', default='celeste_vale')
    ident.add_argument('--seed', type=int, default=42)
    ident.add_argument('--candidates', type=int, default=6)
    ident.add_argument('--output-dir', default='jobs/identity')
    ident.add_argument('--assets-dir', default='assets/generated')
    ident.add_argument('--server-url')
    auto = sub.add_parser('auto-assets')
    auto.add_argument('--theme', required=True)
    auto.add_argument('--channel', required=True)
    auto.add_argument('--seed', type=int)
    auto.add_argument('--output-dir', default='jobs')
    auto.add_argument('--assets-dir', default='assets/generated')
    auto.add_argument('--server-url')
    auto.add_argument('--size', type=int)
    auto.add_argument('--steps', type=int)
    auto.add_argument('--cfg', type=float)
    auto.add_argument('--candidates', type=int, default=6)
    auto.add_argument('--profile', choices=('cyberrealistic-v10','sdxl-dmd2-fast','sdxl-quality','sd15-quality'), default='cyberrealistic-v10')
    auto.add_argument('--negative-prompt', default='')
    resume = sub.add_parser('produce-job')
    resume.add_argument('job')
    resume.add_argument('--assets-dir', default='assets/generated')
    resume.add_argument('--server-url')
    resume.add_argument('--size', type=int)
    resume.add_argument('--steps', type=int)
    resume.add_argument('--cfg', type=float)
    resume.add_argument('--candidates', type=int, default=6)
    resume.add_argument('--profile', choices=('cyberrealistic-v10','sdxl-dmd2-fast','sdxl-quality','sd15-quality'), default='cyberrealistic-v10')
    resume.add_argument('--negative-prompt', default='')
    diag = sub.add_parser('probe-local')
    diag.add_argument('--prompt', default='test photograph')
    diag.add_argument('--server-url')
    gen = sub.add_parser('generate-local')
    gen.add_argument('--prompt', required=True)
    gen.add_argument('--output', required=True)
    gen.add_argument('--negative-prompt', default='')
    gen.add_argument('--size', type=int)
    gen.add_argument('--steps', type=int)
    gen.add_argument('--cfg', type=float)
    gen.add_argument('--profile', choices=('cyberrealistic-v10','sdxl-dmd2-fast','sdxl-quality','sd15-quality'), default='cyberrealistic-v10')
    gen.add_argument('--seed', type=int)
    gen.add_argument('--server-url')
    nxt = sub.add_parser('next-batch')
    nxt.add_argument('--theme', required=True)
    nxt.add_argument('--channel', required=True)
    nxt.add_argument('--seed', type=int)
    nxt.add_argument('--avatar', action='store_true')
    nxt.add_argument('--output-dir', default='jobs')
    moa = sub.add_parser('moa-plan')
    moa.add_argument('--theme', required=True)
    moa.add_argument('--channel', required=True)
    moa.add_argument('--persona', required=True)
    moa.add_argument('--seed', type=int)
    export = sub.add_parser('export-n8n')
    export.add_argument('--output', default='n8n/spicecore-free.json')
    briefs = sub.add_parser('briefs')
    briefs.add_argument('--theme', required=True)
    briefs.add_argument('--channel', required=True)
    briefs.add_argument('--seed', type=int)
    plan = sub.add_parser('free-plan')
    plan.add_argument('--theme', required=True)
    plan.add_argument('--channel', required=True)
    plan.add_argument('--persona')
    plan.add_argument('--seed', type=int)
    plan.add_argument('--avatar', action='store_true')
    plan.add_argument('--output-dir', default='jobs')
    serve = sub.add_parser('serve')
    serve.add_argument('--port', type=int, default=8765)
    rec = sub.add_parser('recommend')
    rec.add_argument('--seed', type=int)
    prop = sub.add_parser('propose')
    for field in ('persona', 'theme', 'format', 'channel', 'offer'):
        prop.add_argument('--' + field, required=True)
    for field in ('asset-uri', 'prompt', 'model', 'seed'):
        prop.add_argument('--' + field)
    prop.add_argument('--cost-cents', type=int, default=0)
    review = sub.add_parser('review')
    review.add_argument('candidate_id')
    review.add_argument('decision', choices=('approved', 'rejected', 'revise'))
    review.add_argument('--reviewer', required=True)
    review.add_argument('--note', default='')
    pub = sub.add_parser('publish')
    pub.add_argument('candidate_id')
    pub.add_argument('--url', required=True)
    outcome = sub.add_parser('outcome')
    outcome.add_argument('candidate_id')
    outcome.add_argument('kind', choices=('impression', 'click', 'purchase', 'refund', 'distribution_cost'))
    outcome.add_argument('--amount-cents', type=int, default=0)
    outcome.add_argument('--external-id')
    args = parser.parse_args(argv)
    personas = load_personas(args.personas)
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    store = Store(args.db)
    try:
        if args.command == 'init':
            output = {'database': args.db, 'personas': len(personas)}
        elif args.command == 'personas':
            output = personas
        elif args.command == 'stats':
            output = store.stats(personas)
        elif args.command == 'events':
            output = store.events()
        elif args.command == 'identity-scene':
            out=args.output or f'assets/generated/{args.persona}/scenes/{args.scene}-{args.seed}.png'
            persona = next((p for p in personas if p['id'] == args.persona), None)
            if persona is None: parser.error('Unknown persona')
            output = generate_scene(store,args.persona,args.scene,out,args.seed,args.denoise,args.server_url,args.reference_dir,persona,args.composition_only)
        elif args.command == 'identity-transfer':
            persona = next((p for p in personas if p['id'] == args.persona), None)
            if persona is None: parser.error('Unknown persona')
            source=Path(args.scene_asset)
            out=args.output or str(source.with_name(source.stem+'-identity.png'))
            output=transfer_identity(store,args.persona,args.scene_asset,out,args.endpoint,args.strength,args.reference_dir,persona)
        elif args.command == 'identity-inpaint':
            persona = next((p for p in personas if p['id'] == args.persona), None)
            if persona is None: parser.error('Unknown persona')
            source=Path(args.scene_asset)
            out=args.output or str(source.with_name(source.stem+'-celeste.png'))
            output=identity_inpaint(store,args.persona,args.scene_asset,out,args.seed,args.denoise,args.server_url,args.reference_dir,persona,args.invert_mask)
        elif args.command == 'select-identity':
            output = select_identity(store,args.persona,args.candidate_id,args.reference_dir)
        elif args.command == 'identity-batch':
            output = run_identity_batch(store,personas,args.persona,args.output_dir,args.assets_dir,args.server_url,args.seed,args.candidates)
        elif args.command == 'auto-assets':
            planned = plan_next_batch(store, personas, args.theme, args.channel, args.output_dir, args.seed, False)
            output = produce_job(store, personas, planned['job'], args.assets_dir, args.server_url, args.size, args.steps, args.cfg, args.negative_prompt, args.candidates, args.profile)
        elif args.command == 'produce-job':
            output = produce_job(store, personas, args.job, args.assets_dir, args.server_url, args.size, args.steps, args.cfg, args.negative_prompt, args.candidates, args.profile)
        elif args.command == 'probe-local':
            output = localdream_probe(args.prompt,args.server_url)
        elif args.command == 'generate-local':
            output = localdream_generate(args.prompt,args.output,args.negative_prompt,args.size,args.steps,args.cfg,args.seed,args.server_url,profile=args.profile)
            store.record_event('asset_generated', output)
        elif args.command == 'next-batch':
            output = plan_next_batch(store, personas, args.theme, args.channel, args.output_dir, args.seed, args.avatar)
        elif args.command == 'moa-plan':
            persona = next((p for p in personas if p['id'] == args.persona), None)
            if persona is None: parser.error('Unknown persona')
            brief = next(b for b in build_briefs(personas, args.theme, args.channel, args.seed) if b['persona_id'] == args.persona)
            rag = LocalRAG.from_paths(['project.md', 'identity', 'personas'])
            context = rag.search(f"{persona['name']} {args.theme} {args.channel} monetization identity")
            output = deliberate(persona, brief, store.stats(personas), context, args.seed)
            store.record_event('moa_decision', output)
        elif args.command == 'export-n8n':
            output = {'workflow': str(write_n8n(args.output))}
        elif args.command == 'briefs':
            output = build_briefs(personas, args.theme, args.channel, args.seed)
        elif args.command == 'free-plan':
            briefs = build_briefs(personas, args.theme, args.channel, args.seed)
            if args.persona:
                briefs = [b for b in briefs if b['persona_id'] == args.persona]
                if not briefs:
                    parser.error('Unknown persona')
            jobs = []
            for brief in briefs:
                path = Path(args.output_dir) / f"{brief['persona_id']}-{args.theme}.json"
                write_job(brief, path, args.avatar)
                jobs.append({'persona_id': brief['persona_id'], 'job': str(path),
                             'production': free_production_plan(brief, args.avatar)})
            output = jobs
        elif args.command == 'serve':
            token = secrets.token_urlsafe(24)
            server = HTTPServer(('127.0.0.1', args.port), make_handler(store, personas, token))
            print(f'Local review: http://127.0.0.1:{server.server_port}/?token={token}', flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
            return
        elif args.command == 'recommend':
            output = recommend(store.stats(personas), seed=args.seed)
            store.record_event('policy_decision', output)
        elif args.command == 'propose':
            persona = next((p for p in personas if p['id'] == args.persona), None)
            if persona is None:
                parser.error('Unknown persona')
            output = {'candidate_id': store.propose(persona, args.theme, args.format,
                args.channel, args.offer, args.asset_uri, args.prompt, args.model,
                args.seed, args.cost_cents)}
        elif args.command == 'review':
            output = store.review(args.candidate_id, args.decision, args.reviewer, args.note)
        elif args.command == 'publish':
            output = store.publish(args.candidate_id, args.url)
        elif args.command == 'outcome':
            output = store.record_outcome(args.candidate_id, args.kind, args.amount_cents, args.external_id)
        print(json.dumps(output, indent=2, ensure_ascii=False))
    finally:
        store.close()


if __name__ == '__main__':
    main()
