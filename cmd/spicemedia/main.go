package main

import (
    "context"
    "encoding/base64"
    "encoding/json"
    "fmt"
    "io"
    "os"
    "time"

    ident "github.com/jcltd303-hub/spice-hoes/internal/identity"
    "github.com/jcltd303-hub/spice-hoes/internal/imagemetrics"
    "github.com/jcltd303-hub/spice-hoes/internal/identitygen"
    "github.com/jcltd303-hub/spice-hoes/internal/nativecore"
    "github.com/jcltd303-hub/spice-hoes/internal/termui"
)

var progress *termui.Spinner

func fail(err error) {
    if progress != nil { progress.Stop(false) }
    fmt.Fprintln(os.Stderr, err)
    os.Exit(1)
}

func readObject() map[string]any {
    b,err:=io.ReadAll(os.Stdin); if err!=nil { fail(err) }
    var v map[string]any; if err:=json.Unmarshal(b,&v); err!=nil { fail(err) }; return v
}

func write(v any) { enc:=json.NewEncoder(os.Stdout); enc.SetEscapeHTML(false); if err:=enc.Encode(v); err!=nil { fail(err) } }

func decodeB64(v any) ([]byte,error) {
    s,ok:=v.(string); if !ok || s=="" { return nil,fmt.Errorf("missing base64 image") }
    if i:=indexComma(s); i>=0 { s=s[i+1:] }
    return base64.StdEncoding.DecodeString(s)
}

func indexComma(s string) int { for i:=0;i<len(s);i++ { if s[i]==',' { return i } }; return -1 }

func progressEvent(ev identitygen.ProgressEvent) {
    if progress==nil { return }
    progress.SetProgress(ev.Percent,ev.Stage)
    progress.SetMetrics(ev.Metrics)
}

func finish(title string, metrics map[string]any) {
    if progress==nil { return }
    progress.SetMetrics(metrics)
    progress.SetProgress(100,"complete")
    progress.Stop(true)
    progress.Summary(title)
    progress=nil
}

func commandGenerate() {
    payload:=readObject()
    manager:=nativecore.FromEnv()
    if manager.ModelDir=="" { fail(fmt.Errorf("generation requires SPICE_QNN_MODEL_DIR")) }
    ctx,cancel:=context.WithTimeout(context.Background(),12*time.Minute); defer cancel()
    progress.SetProgress(15,"QNN generation")
    out,err:=manager.Generate(ctx,payload); if err!=nil { fail(err) }
    progress.SetProgress(90,"packing response")
    img,_:=out["image"].(string); format,_:=out["format"].(string); if format=="" { format="png" }
    mime:="image/png"; if format=="jpeg" || format=="jpg" { mime="image/jpeg" }
    response:=map[string]any{"image_base64":img,"mime_type":mime,"model":"spicemedia:qnn","backend":"go-managed-qnn"}
    for _,k:=range []string{"seed","width","height","channels","generation_time_ms","first_step_time_ms"} { if v,ok:=out[k]; ok { response[k]=v } }
    finish("generation metrics",map[string]any{
        "backend":"go-managed-qnn","model":"spicemedia:qnn","format":format,
        "seed":out["seed"],"size":fmt.Sprintf("%vx%v",out["width"],out["height"]),
        "channels":out["channels"],"generation_time_ms":out["generation_time_ms"],
        "first_step_time_ms":out["first_step_time_ms"],
    })
    write(response)
}

func commandQuality() {
    payload:=readObject(); raw,err:=decodeB64(payload["image_base64"]); if err!=nil { fail(err) }
    progress.SetProgress(25,"analyzing pixels")
    m,err:=imagemetrics.Analyze(raw); if err!=nil { fail(err) }
    result:=map[string]any{
        "semantic_scored":false,
        "overall":m.LocalScore,
        "local":m,
        "model":"go-stdlib-quality-v1",
    }
    finish("quality metrics",map[string]any{
        "quality_score":m.LocalScore,"size":fmt.Sprintf("%dx%d",m.Width,m.Height),
        "sharpness":m.Sharpness,"contrast":m.Contrast,"brightness":m.Brightness,
        "exposure":m.ExposureScore,"resolution":m.ResolutionScore,"backend":m.Backend,
    })
    write(result)
}

func arcFaceEmbedding(manager *nativecore.Manager, raw []byte) ([]float64,map[string]any,string,error) {
    const alignment = "scrfd-5pt-112"
    if manager.FaceDetector == "" {
        return nil,nil,alignment,fmt.Errorf("SPICE_FACE_DETECT_MODEL is not configured")
    }
    if manager.IdentityVision == "" {
        return nil,nil,alignment,fmt.Errorf("SPICE_FACE_EMBED_MODEL is not configured")
    }

    prep,err:=ident.SCRFDInput(raw)
    if err!=nil { return nil,nil,alignment,fmt.Errorf("prepare SCRFD input: %w",err) }

    detectCtx,detectCancel:=context.WithTimeout(context.Background(),2*time.Minute)
    outputs,detectMeta,err:=manager.Detect(detectCtx,prep.Tensor)
    detectCancel()
    if err!=nil { return nil,nil,alignment,fmt.Errorf("SCRFD detection failed: %w",err) }

    faces,err:=ident.DecodeSCRFD(outputs,prep,0.5,0.4)
    if err!=nil || len(faces)==0 {
        if err==nil { err=fmt.Errorf("no face detected") }
        return nil,nil,alignment,fmt.Errorf("SCRFD landmarks unavailable: %w",err)
    }

    input,err:=ident.ArcFaceInputAligned(raw,faces[0].Landmarks)
    if err!=nil { return nil,nil,alignment,fmt.Errorf("five-point alignment failed: %w",err) }

    embedCtx,embedCancel:=context.WithTimeout(context.Background(),2*time.Minute)
    vec,meta,err:=manager.Embed(embedCtx,input)
    embedCancel()
    if err!=nil { return nil,nil,alignment,fmt.Errorf("ArcFace embedding failed: %w",err) }

    meta["alignment"]=alignment
    meta["detector_latency_ms"]=detectMeta["latency_ms"]
    return ident.Normalize(vec),meta,alignment,nil
}
func commandDetect() {
    payload:=readObject()
    raw,err:=decodeB64(payload["image_base64"]); if err!=nil { fail(err) }
    manager:=nativecore.FromEnv()
    if manager.FaceDetector=="" { fail(fmt.Errorf("SPICE_FACE_DETECT_MODEL is not configured")) }

    prep,err:=ident.SCRFDInput(raw); if err!=nil { fail(err) }
    ctx,cancel:=context.WithTimeout(context.Background(),2*time.Minute); defer cancel()
    progress.SetProgress(35,"SCRFD detection")
    outputs,meta,err:=manager.Detect(ctx,prep.Tensor); if err!=nil { fail(err) }
    faces,err:=ident.DecodeSCRFD(outputs,prep,0.5,0.4); if err!=nil { fail(err) }

    result:=make([]map[string]any,0,len(faces))
    for _,face:=range faces {
        points:=make([][]float64,0,5)
        for _,p:=range face.Landmarks {
            points=append(points,[]float64{p.X,p.Y})
        }
        result=append(result,map[string]any{
            "score":face.Score,
            "box":[]float64{face.X1,face.Y1,face.X2,face.Y2},
            "landmarks":points,
        })
    }
    response:=map[string]any{
        "faces":result,
        "count":len(result),
        "model":"scrfd-10g-qnn",
        "npu":true,
        "latency_ms":meta["latency_ms"],
    }
    finish("face detection metrics",map[string]any{"faces":len(result),"latency_ms":meta["latency_ms"],"model":"scrfd-10g-qnn","npu":true})
    write(response)
}

func commandEmbed() {
    payload:=readObject()
    raw,err:=decodeB64(payload["image_base64"]); if err!=nil { fail(err) }
    manager:=nativecore.FromEnv()
    if manager.IdentityVision=="" { fail(fmt.Errorf("SPICE_FACE_EMBED_MODEL is not configured")) }
    progress.SetProgress(30,"SCRFD + ArcFace embedding")
    vec,meta,alignment,err:=arcFaceEmbedding(manager,raw); if err!=nil { fail(err) }
    response:=map[string]any{
        "embedding":vec,
        "dimensions":len(vec),
        "model":"arcface-w600k-r50-qnn",
        "alignment":alignment,
        "npu":true,
        "latency_ms":meta["latency_ms"],
        "detector_latency_ms":meta["detector_latency_ms"],
        "l2_norm":meta["l2_norm"],
    }
    finish("embedding metrics",map[string]any{"dimensions":len(vec),"alignment":alignment,"latency_ms":meta["latency_ms"],"detector_latency_ms":meta["detector_latency_ms"],"l2_norm":meta["l2_norm"],"model":"arcface-w600k-r50-qnn"})
    write(response)
}

func commandIdentity() {
    payload:=readObject(); generated,err:=decodeB64(payload["image_base64"]); if err!=nil { fail(err) }
    refs,ok:=payload["references"].([]any); if !ok || len(refs)==0 { fail(fmt.Errorf("identity requires references")) }

    manager:=nativecore.FromEnv()
    if manager.IdentityVision != "" {
        generatedEmbedding,meta,alignment,err:=arcFaceEmbedding(manager,generated)
        if err==nil {
            scores:=make([]float64,0,len(refs))
            for _,item:=range refs {
                obj,ok:=item.(map[string]any); if !ok { continue }
                ref,err:=decodeB64(obj["image_base64"]); if err!=nil { continue }
                refEmbedding,_,_,err:=arcFaceEmbedding(manager,ref)
                if err!=nil { continue }
                score,err:=ident.Cosine(generatedEmbedding,refEmbedding)
                if err==nil { scores=append(scores,score) }
            }
            if len(scores)>0 {
                maxScore,sum:=scores[0],0.0
                for _,s:=range scores { if s>maxScore {maxScore=s}; sum+=s }
                response:=map[string]any{
                    "score":maxScore,
                    "mean_score":sum/float64(len(scores)),
                    "reference_count":len(scores),
                    "model":"arcface-w600k-r50-qnn",
                    "metric":"cosine",
                    "embedding_dimensions":len(generatedEmbedding),
                    "alignment":alignment,
                    "npu":true,
                    "latency_ms":meta["latency_ms"],
                    "detector_latency_ms":meta["detector_latency_ms"],
                    "l2_norm":meta["l2_norm"],
                }
                finish("identity metrics",map[string]any{"score":maxScore,"mean_score":sum/float64(len(scores)),"references":len(scores),"alignment":alignment,"latency_ms":meta["latency_ms"],"model":"arcface-w600k-r50-qnn","npu":true})
                write(response)
                return
            }
        }
    }

    scores:=make([]float64,0,len(refs))
    for _,item:=range refs {
        obj,ok:=item.(map[string]any); if !ok { continue }
        ref,err:=decodeB64(obj["image_base64"]); if err!=nil { continue }
        score,err:=ident.Similarity(generated,ref); if err==nil { scores=append(scores,score) }
    }
    if len(scores)==0 { fail(fmt.Errorf("no decodable identity references")) }
    maxScore,sum:=scores[0],0.0; for _,s:=range scores { if s>maxScore {maxScore=s}; sum+=s }
    response:=map[string]any{
        "score":maxScore,
        "mean_score":sum/float64(len(scores)),
        "reference_count":len(scores),
        "model":"go-perceptual-identity-v1",
        "metric":"normalized_similarity",
        "alignment":"none",
        "npu":false,
        "fallback_reason":"SPICE_FACE_EMBED_MODEL unavailable or NPU embedding failed",
    }
    finish("identity metrics",map[string]any{"score":maxScore,"mean_score":sum/float64(len(scores)),"references":len(scores),"model":"go-perceptual-identity-v1","npu":false})
    write(response)
}

func commandIdentityGenerate() {
    payload:=readObject()
    raw,err:=json.Marshal(payload); if err!=nil { fail(err) }
    var req identitygen.Request
    if err:=json.Unmarshal(raw,&req); err!=nil { fail(err) }
    req.Progress=progressEvent
    ctx,cancel:=context.WithTimeout(context.Background(),20*time.Minute); defer cancel()
    out,err:=identitygen.Run(ctx,req); if err!=nil { fail(err) }
    finish("identity generation metrics",map[string]any{
        "persona":out.PersonaID,"status":out.Status,"asset":out.AssetPath,"documents":out.DocumentsPath,
        "identity_score":out.Identity.Score,"identity_mean":out.Identity.MeanScore,"identity_pass":out.Identity.Passed,
        "identity_threshold":out.Identity.Threshold,"references":out.Identity.ReferenceCount,"alignment":out.Identity.Alignment,
        "quality_score":out.Quality.LocalScore,"quality_pass":out.QualityPassed,"quality_threshold":out.QualityThreshold,
        "sharpness":out.Quality.Sharpness,"contrast":out.Quality.Contrast,"brightness":out.Quality.Brightness,
        "exposure":out.Quality.ExposureScore,"resolution":out.Quality.ResolutionScore,
    })
    write(out)
}

func commandIdentityBootstrapAll() {
    payload:=readObject()
    raw,err:=json.Marshal(payload); if err!=nil { fail(err) }
    var req identitygen.BootstrapAllRequest
    if err:=json.Unmarshal(raw,&req); err!=nil { fail(err) }
    req.Progress=progressEvent
    ctx,cancel:=context.WithTimeout(context.Background(),2*time.Hour); defer cancel()
    out,err:=identitygen.BootstrapAll(ctx,req); if err!=nil { fail(err) }
    attempts:=0
    promoted:=0
    bestIdentity:=0.0
    bestQuality:=0.0
    for _,p:=range out.Personas {
        attempts+=p.Attempts
        promoted+=len(p.Promoted)
        if p.BestIdentity>bestIdentity { bestIdentity=p.BestIdentity }
        if p.BestQuality>bestQuality { bestQuality=p.BestQuality }
    }
    finish("identity bootstrap metrics",map[string]any{
        "complete":fmt.Sprintf("%d/%d",out.Complete,out.Total),"ok":out.OK,
        "target_refs":out.TargetReferences,"attempts":attempts,"promoted":promoted,
        "best_identity":bestIdentity,"best_quality":bestQuality,
    })
    write(out)
}

func commandIdentityPoses() {
    payload:=readObject()
    raw,err:=json.Marshal(payload); if err!=nil { fail(err) }
    var req identitygen.PoseMasterRequest
    if err:=json.Unmarshal(raw,&req); err!=nil { fail(err) }
    req.Progress=progressEvent
    ctx,cancel:=context.WithTimeout(context.Background(),2*time.Hour); defer cancel()
    out,err:=identitygen.GeneratePoseMasters(ctx,req); if err!=nil { fail(err) }
    finish("identity pose metrics",map[string]any{
        "persona":out.PersonaID,"ok":out.OK,"template":out.TemplateID,
        "poses":len(out.Assets),"contact_sheet":out.ContactSheet,
    })
    write(out)
}

func commandIdentityAutonomous() {
    payload:=readObject()
    raw,err:=json.Marshal(payload); if err!=nil { fail(err) }
    var req identitygen.AutonomousRequest
    if err:=json.Unmarshal(raw,&req); err!=nil { fail(err) }
    req.Progress=progressEvent
    ctx,cancel:=context.WithTimeout(context.Background(),6*time.Hour); defer cancel()
    out,err:=identitygen.AutonomousIdentity(ctx,req); if err!=nil { fail(err) }
    finish("autonomous identity metrics",map[string]any{
        "persona":out.PersonaID,"ok":out.OK,
        "reference_complete":out.ReferenceComplete,
        "portfolio_complete":out.PortfolioComplete,
        "swap_available":out.SwapAvailable,
        "portfolio_sheet":out.PortfolioSheet,
        "manifest":out.ManifestPath,
    })
    write(out)
}

func commandHealth() {
    ctx,cancel:=context.WithTimeout(context.Background(),50*time.Second); defer cancel()
    m:=nativecore.FromEnv()
    if err:=m.Ensure(ctx); err!=nil {
        result:=map[string]any{"ok":false,"backend":"go-managed-qnn","error":err.Error()}
        finish("health metrics",result)
        write(result)
        return
    }
    result:=map[string]any{
        "ok":true,
        "backend":"go-managed-qnn",
        "mode":func() string { if m.ModelDir=="" { return "face-only" }; return "generation" }(),
    }
    finish("health metrics",result)
    write(result)
}

func main() {
    if len(os.Args)!=2 { fail(fmt.Errorf("usage: spicemedia generate|quality|detect|embed|identity|identity-generate|identity-bootstrap-all|identity-poses|identity-autonomous|health")) }
    command:=os.Args[1]
    progress=termui.Start(termui.Label("spicemedia", command))
    defer func(){ if progress!=nil { progress.Stop(true) } }()

    switch command {
    case "generate": commandGenerate()
    case "quality": commandQuality()
    case "detect": commandDetect()
    case "embed": commandEmbed()
    case "identity": commandIdentity()
    case "identity-generate": commandIdentityGenerate()
    case "identity-bootstrap-all": commandIdentityBootstrapAll()
    case "identity-poses": commandIdentityPoses()
    case "identity-autonomous": commandIdentityAutonomous()
    case "health": commandHealth()
    default: fail(fmt.Errorf("unknown command: %s",command))
    }
}
