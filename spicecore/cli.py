"""Command-line MVP for running the entire reviewed experiment loop."""

import argparse
import json
import secrets
from http.server import HTTPServer
from pathlib import Path

from .core import Store, load_personas
from .autonomy import plan_next_batch
from .policy import recommend
from .moa import deliberate
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
