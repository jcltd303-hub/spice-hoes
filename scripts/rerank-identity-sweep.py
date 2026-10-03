#!/usr/bin/env python3
import argparse, csv, json, pathlib, math

def score_row(r):
    if not r.get("identity_scored"):
        return float("-inf")
    ident=float(r.get("identity_score") or 0)
    mean=float(r.get("identity_mean") or 0)
    qual=float(r.get("quality_score") or 0)
    runtime=float(r.get("runtime_sec") or 0)
    pass_bonus=1.0 if r.get("accepted") else 0.0
    return pass_bonus + 0.55*ident + 0.25*mean + 0.20*qual - min(runtime/3600.0,1.0)*0.01

def flatten(path):
    obj=json.loads(path.read_text())
    req=obj.get("request") or {}
    res=obj.get("result") or {}
    ident=res.get("identity") or {}
    qual=res.get("quality") or {}
    gen=res.get("generation") or {}
    # Older sweep files store an already-flattened result.
    if "identity_score" in res or "quality_score" in res:
        row=dict(res)
        row.setdefault("identity_scored", bool(row.get("identity_score") or row.get("identity_mean")))
        row.setdefault("identity_reason", "")
    else:
        row={
            "ok":True,
            "status":res.get("status"),
            "asset_path":res.get("asset_path"),
            "metadata_path":res.get("metadata_path"),
            "identity_scored":bool(ident.get("scored")),
            "identity_reason":ident.get("reason") or "",
            "identity_score":ident.get("score") or 0,
            "identity_mean":ident.get("mean_score") or 0,
            "identity_pass":bool(ident.get("passed")),
            "quality_score":qual.get("local_score") or 0,
            "quality_pass":bool(res.get("quality_passed")),
            "selected_attempt":gen.get("selected_attempt"),
            "selected_seed":gen.get("selected_seed"),
            "swap_source":gen.get("faceswap_source_mode"),
            "swap_trials":gen.get("faceswap_trials"),
            "selection_score":gen.get("selection_score") or 0,
        }
    row["guidance"]=req.get("guidance")
    row["steps"]=req.get("steps")
    row["embedding_weight"]=req.get("identity_embedding_weight")
    row["swap_top_k"]=req.get("swap_top_k")
    row["best_of_n"]=req.get("best_of_n")
    row["accepted"]=bool(row.get("identity_pass") and row.get("quality_pass"))
    row["sweep_score"]=score_row(row)
    row["file"]=path.name
    return row

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("root")
    args=ap.parse_args()
    root=pathlib.Path(args.root)
    files=sorted(root.glob("run-*.json"))
    if not files: raise SystemExit(f"no run-*.json files in {root}")
    rows=[flatten(p) for p in files]
    valid=[r for r in rows if r.get("ok") and r.get("identity_scored")]
    valid.sort(key=lambda r:r["sweep_score"],reverse=True)
    fields=["rank","file","guidance","steps","embedding_weight","swap_top_k","best_of_n","identity_scored","identity_reason","identity_score","identity_mean","quality_score","accepted","runtime_sec","sweep_score","status","selected_seed","swap_source","swap_trials","asset_path","metadata_path"]
    with (root/"leaderboard-reranked.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore"); w.writeheader()
        for i,row in enumerate(valid,1):
            rr=dict(row); rr["rank"]=i; w.writerow(rr)
    summary={
        "schema":"spice.identity-sweep.rerank.v1",
        "total_runs":len(rows),
        "identity_scored_runs":len(valid),
        "runtime_failures":sum(1 for r in rows if not r.get("identity_scored")),
        "winner":valid[0] if valid else None,
        "top":valid[:10],
    }
    (root/"summary-reranked.json").write_text(json.dumps(summary,indent=2)+"\n")
    if valid:
        winner=valid[0]
        req=json.loads((root/winner["file"]).read_text()).get("request") or {}
        (root/"winning-request-reranked.json").write_text(json.dumps(req,indent=2)+"\n")
    print(json.dumps(summary,indent=2))
    if not valid: raise SystemExit(2)

if __name__=="__main__":
    main()
