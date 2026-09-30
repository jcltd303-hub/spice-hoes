"""Command-line MVP for running the entire reviewed experiment loop."""

import argparse
import json
import secrets
from http.server import HTTPServer
from pathlib import Path

from .core import Store, load_personas
from .knowledge import KnowledgeStore
from .policy import recommend
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
    briefs = sub.add_parser('briefs')
    briefs.add_argument('--theme', required=True)
    briefs.add_argument('--channel', required=True)
    briefs.add_argument('--seed', type=int)
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
    knowledge = sub.add_parser('knowledge')
    operations = knowledge.add_subparsers(dest='knowledge_operation', required=True)
    for operation in ('add', 'revise'):
        command = operations.add_parser(operation)
        if operation == 'revise':
            command.add_argument('document_id')
        command.add_argument('--document', required=True, help='JSON document file with metadata and text/content')
    search = operations.add_parser('search')
    search.add_argument('query')
    search.add_argument('--scope', required=True, help='JSON scope with authenticated tenant, owner, persona')
    search.add_argument('--limit', type=int, default=8)
    for operation in ('archive', 'delete'):
        operations.add_parser(operation).add_argument('document_id')
    args = parser.parse_args(argv)
    if args.command == 'knowledge':
        Path(args.db).parent.mkdir(parents=True, exist_ok=True)
        knowledge_store = KnowledgeStore(args.db)
        try:
            operation = args.knowledge_operation
            if operation in ('add', 'revise'):
                document = json.loads(Path(args.document).read_text())
                if operation == 'add':
                    output = {'document_id': knowledge_store.add(document)}
                else:
                    output = {'revision_id': knowledge_store.revise(args.document_id, document)}
            elif operation == 'search':
                output = {'mode': knowledge_store.mode, 'results': knowledge_store.search(args.query, json.loads(args.scope), args.limit)}
            else:
                getattr(knowledge_store, operation)(args.document_id)
                output = {'document_id': args.document_id, 'operation': operation}
            print(json.dumps(output, indent=2, ensure_ascii=False))
        finally:
            knowledge_store.close()
        return
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
        elif args.command == 'briefs':
            output = build_briefs(personas, args.theme, args.channel, args.seed)
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

