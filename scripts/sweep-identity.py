#!/usr/bin/env python3
import argparse, csv, itertools, json, os, pathlib, subprocess, sys, time
from datetime import datetime, timezone

def parse_nums(s, cast=float):
    return [cast(x.strip()) for x in s.split(",") if x.strip()]

def score_row(r):
    # A run without a valid ArcFace result is never rankable.
    if not r.get("identity_scored"):
        return float("-inf")
    ident=float(r.get("identity_score") or 0)
    mean=float(r.get("identity_mean") or 0)
    qual=float(r.get("quality_score") or 0)
    return 0.70*ident + 0.20*mean + 0.10*qual

def rank_key(r):
    return (
        1 if r.get("identity_scored") else 0,
        1 if r.get("accepted") else 0,
        1 if r.get("identity_pass") else 0,
        float(r.get("identity_score") or 0),
        float(r.get("identity_mean") or 0),
        1 if r.get("quality_pass") else 0,
        float(r.get("quality_score") or 0),
        -float(r.get("runtime_sec") or 0),
    )

def run_one(bin_path, req, timeout):
    started=time.time()
    p=subprocess.run(
        [bin_path,"identity-generate"],
        input=json.dumps(req).encode(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    elapsed=time.time()-started
    if p.returncode!=0:
        return {"ok":False,"runtime_sec":elapsed,"error":p.stderr.decode(errors="replace")[-4000:]}
    try:
        out=json.loads(p.stdout.decode())
    except Exception as e:
        return {"ok":False,"runtime_sec":elapsed,"error":f"invalid JSON: {e}","stdout":p.stdout.decode(errors="replace")[-4000:]}
    row={
        "ok":True,
        "runtime_sec":elapsed,
        "status":out.get("status"),
        "asset_path":out.get("asset_path"),
        "metadata_path":out.get("metadata_path"),
        "identity_scored":bool((out.get("identity") or {}).get("scored")),
        "identity_reason":((out.get("identity") or {}).get("reason") or ""),
        "identity_score":((out.get("identity") or {}).get("score") or 0),
        "identity_mean":((out.get("identity") or {}).get("mean_score") or 0),
        "identity_pass":bool((out.get("identity") or {}).get("passed")),
        "quality_score":((out.get("quality") or {}).get("local_score") or 0),
        "quality_pass":bool(out.get("quality_passed")),
        "selected_attempt":((out.get("generation") or {}).get("selected_attempt")),
        "selected_seed":((out.get("generation") or {}).get("selected_seed")),
        "swap_source":((out.get("generation") or {}).get("faceswap_source_mode")),
        "swap_trials":((out.get("generation") or {}).get("faceswap_trials")),
        "selection_score":((out.get("generation") or {}).get("selection_score") or 0),
    }
    row["accepted"]=bool(row["identity_pass"] and row["quality_pass"])
    return row

def main():
    ap=argparse.ArgumentParser(description="Tournament sweep for Local Dream identity generation")
    ap.add_argument("--bin",default="./bin/spicemedia")
    ap.add_argument("--persona",default="celeste_vale")
    ap.add_argument("--theme",default="identity reference portrait")
    ap.add_argument("--scene",default="")
    ap.add_argument("--style",default="photorealistic")
    ap.add_argument("--seed",type=int,default=424242)
    ap.add_argument("--guidance",default="6.0,6.5,7.0")
    ap.add_argument("--steps",default="20,22,24")
    ap.add_argument("--embedding-weight",default="1.05,1.10,1.15")
    ap.add_argument("--swap-top-k",default="2,4,8")
    ap.add_argument("--stage1-best-of-n",type=int,default=4)
    ap.add_argument("--stage2-best-of-n",type=int,default=8)
    ap.add_argument("--stage1-keep",type=int,default=6)
    ap.add_argument("--stage2-keep",type=int,default=3)
    ap.add_argument("--timeout",type=int,default=1800)
    ap.add_argument("--require-embedding",action="store_true")
    ap.add_argument("--output-root",default="data/sweeps")
    args=ap.parse_args()

    guidance=parse_nums(args.guidance,float)
    steps=parse_nums(args.steps,int)
    weights=parse_nums(args.embedding_weight,float)
    swapks=parse_nums(args.swap_top_k,int)

    run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root=pathlib.Path(args.output_root)/f"{args.persona}-{run_id}"
    root.mkdir(parents=True,exist_ok=True)

    base={
        "persona_id":args.persona,
        "theme":args.theme,
        "scene":args.scene,
        "style":args.style,
        "generator":"local-dream",
        "seed":args.seed,
        "stop_on_accept":False,
        "save_all_attempts":True,
        "require_identity_embedding":args.require_embedding,
    }

    rows=[]
    run_no=0

    # Stage 1: broad sweep guidance x embedding weight at fixed 20 steps.
    stage1=[]
    for g,w in itertools.product(guidance,weights):
        run_no+=1
        req=dict(base)
        req.update({"guidance":g,"steps":20,"identity_embedding_weight":w,"best_of_n":args.stage1_best_of_n,"swap_top_k":1})
        print(f"[stage1 {run_no}] cfg={g} weight={w}",file=sys.stderr,flush=True)
        result=run_one(args.bin,req,args.timeout)
        if not result.get("ok"):
            print(f"[stage1 {run_no}] ERROR: {result.get('error','unknown error')}",file=sys.stderr,flush=True)
        elif not result.get("identity_scored"):
            print(f"[stage1 {run_no}] IDENTITY ERROR: {result.get('identity_reason') or result.get('status')}",file=sys.stderr,flush=True)
        row={"stage":1,"run":run_no,"guidance":g,"steps":20,"embedding_weight":w,"swap_top_k":1,"best_of_n":args.stage1_best_of_n,**result}
        row["sweep_score"]=score_row(row)
        rows.append(row); stage1.append(row)
        (root/f"run-{run_no:03d}.json").write_text(json.dumps({"request":req,"result":result},indent=2)+"\n")

    stage1_ok=[r for r in stage1 if r.get("ok") and r.get("identity_scored")]
    stage1_ok.sort(key=rank_key,reverse=True)
    if not stage1_ok:
        reasons={}
        for r in stage1:
            reason=r.get("error") or r.get("identity_reason") or r.get("status") or "unknown"
            reasons[reason]=reasons.get(reason,0)+1
        summary={
            "schema":"spice.identity-sweep.v1",
            "run_id":run_id,
            "persona_id":args.persona,
            "seed":args.seed,
            "total_runs":len(rows),
            "successful_runs":sum(1 for r in rows if r.get("ok")),
            "identity_scored_runs":0,
            "failure_reasons":reasons,
            "winner":None,
            "all":rows,
        }
        (root/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
        print(json.dumps({
            "ok":False,
            "root":str(root),
            "error":"no stage-1 run produced a valid identity score",
            "failure_reasons":reasons
        },indent=2))
        raise SystemExit(2)
    finalists=stage1_ok[:args.stage1_keep]

    # Stage 2: refine the best guidance/embedding pairs across steps and swap budget.
    stage2=[]
    seen=set()
    for f in finalists:
        for st,sk in itertools.product(steps,swapks):
            key=(f["guidance"],f["embedding_weight"],st,sk)
            if key in seen: continue
            seen.add(key); run_no+=1
            req=dict(base)
            req.update({
                "guidance":f["guidance"],"steps":st,
                "identity_embedding_weight":f["embedding_weight"],
                "best_of_n":args.stage2_best_of_n,"swap_top_k":sk,
            })
            print(f"[stage2 {run_no}] cfg={f['guidance']} steps={st} weight={f['embedding_weight']} swapK={sk}",file=sys.stderr,flush=True)
            result=run_one(args.bin,req,args.timeout)
            if not result.get("ok"):
                print(f"[stage2 {run_no}] ERROR: {result.get('error','unknown error')}",file=sys.stderr,flush=True)
            elif not result.get("identity_scored"):
                print(f"[stage2 {run_no}] IDENTITY ERROR: {result.get('identity_reason') or result.get('status')}",file=sys.stderr,flush=True)
            row={"stage":2,"run":run_no,"guidance":f["guidance"],"steps":st,"embedding_weight":f["embedding_weight"],"swap_top_k":sk,"best_of_n":args.stage2_best_of_n,**result}
            row["sweep_score"]=score_row(row)
            rows.append(row); stage2.append(row)
            (root/f"run-{run_no:03d}.json").write_text(json.dumps({"request":req,"result":result},indent=2)+"\n")

    ranked=[r for r in rows if r.get("ok") and r.get("identity_scored")]
    ranked.sort(key=rank_key,reverse=True)

    fields=["rank","stage","run","guidance","steps","embedding_weight","swap_top_k","best_of_n","identity_scored","identity_reason","identity_score","identity_mean","quality_score","accepted","runtime_sec","sweep_score","status","selected_seed","swap_source","swap_trials","asset_path","metadata_path","error"]
    with (root/"leaderboard.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore"); w.writeheader()
        for i,row in enumerate(ranked,1):
            rr=dict(row); rr["rank"]=i; w.writerow(rr)

    summary={
        "schema":"spice.identity-sweep.v1",
        "run_id":run_id,
        "persona_id":args.persona,
        "seed":args.seed,
        "total_runs":len(rows),
        "successful_runs":sum(1 for r in rows if r.get("ok")),
        "identity_scored_runs":len(ranked),
        "stage1_keep":args.stage1_keep,
        "winner":ranked[0] if ranked else None,
        "top":ranked[:args.stage2_keep],
        "all":rows,
    }
    (root/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")

    if ranked:
        winner=ranked[0]
        winning_req=dict(base)
        winning_req.update({
            "guidance":winner["guidance"],
            "steps":winner["steps"],
            "identity_embedding_weight":winner["embedding_weight"],
            "best_of_n":winner["best_of_n"],
            "swap_top_k":winner["swap_top_k"],
        })
        (root/"winning-request.json").write_text(json.dumps(winning_req,indent=2)+"\n")
        print(json.dumps({"ok":True,"root":str(root),"winner":winner},indent=2))
    else:
        print(json.dumps({"ok":False,"root":str(root),"error":"no successful runs"},indent=2))
        raise SystemExit(1)

if __name__=="__main__":
    main()
