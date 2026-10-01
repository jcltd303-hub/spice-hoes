"""CLI for constructing and promoting master reference packs."""

import argparse
import json
from pathlib import Path

from .core import Store, load_personas
from .masterref import MasterReferenceBuilder
from .providers import LocalDreamProvider


def main(argv=None):
    parser = argparse.ArgumentParser(prog="spicecore.reference_cli")
    parser.add_argument("--db", default="data/experiments.sqlite")
    parser.add_argument("--personas", default="personas")
    parser.add_argument("--staging-root", default="data/reference_candidates")
    parser.add_argument("--reference-root", default="data/references")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build")
    build.add_argument("--persona", required=True)
    build.add_argument("--seed", type=int)
    build.add_argument("--identity-threshold", type=float, default=0.84)
    build.add_argument("--reference-strength", type=float, default=0.90)
    build.add_argument("--anchor-candidates", type=int, default=3)
    build.add_argument("--attempts-per-view", type=int, default=2)

    promote = sub.add_parser("promote")
    promote.add_argument("manifest")

    args = parser.parse_args(argv)
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    personas = load_personas(args.personas)
    store = Store(args.db)
    try:
        builder = MasterReferenceBuilder(
            store,
            provider=LocalDreamProvider(),
            staging_root=args.staging_root,
            reference_root=args.reference_root,
            identity_threshold=getattr(args, "identity_threshold", 0.84),
            reference_strength=getattr(args, "reference_strength", 0.90),
            anchor_candidates=getattr(args, "anchor_candidates", 3),
            attempts_per_view=getattr(args, "attempts_per_view", 2),
        )
        if args.command == "build":
            persona = next((p for p in personas if p["id"] == args.persona), None)
            if persona is None:
                parser.error("Unknown persona")
            output = builder.build(persona, seed=args.seed)
        else:
            output = builder.promote(args.manifest)
        print(json.dumps(output, indent=2, ensure_ascii=False))
    finally:
        store.close()


if __name__ == "__main__":
    main()
