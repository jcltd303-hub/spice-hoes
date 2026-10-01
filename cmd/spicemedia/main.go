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
    "github.com/jcltd303-hub/spice-hoes/internal/nativecore"
)

func fail(err error) { fmt.Fprintln(os.Stderr, err); os.Exit(1) }

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

func commandGenerate() {
    payload:=readObject()
    ctx,cancel:=context.WithTimeout(context.Background(),12*time.Minute); defer cancel()
    out,err:=nativecore.FromEnv().Generate(ctx,payload); if err!=nil { fail(err) }
    img,_:=out["image"].(string); format,_:=out["format"].(string); if format=="" { format="png" }
    mime:="image/png"; if format=="jpeg" || format=="jpg" { mime="image/jpeg" }
    response:=map[string]any{"image_base64":img,"mime_type":mime,"model":"spicemedia:qnn","backend":"go-managed-qnn"}
    for _,k:=range []string{"seed","width","height","channels","generation_time_ms","first_step_time_ms"} { if v,ok:=out[k]; ok { response[k]=v } }
    write(response)
}

func commandQuality() {
    payload:=readObject(); raw,err:=decodeB64(payload["image_base64"]); if err!=nil { fail(err) }
    m,err:=imagemetrics.Analyze(raw); if err!=nil { fail(err) }
    write(map[string]any{
        "semantic_scored":false,
        "overall":m.LocalScore,
        "local":m,
        "model":"go-stdlib-quality-v1",
    })
}

func commandEmbed() {
    payload:=readObject()
    raw,err:=decodeB64(payload["image_base64"]); if err!=nil { fail(err) }
    input,err:=ident.ArcFaceInput(raw); if err!=nil { fail(err) }
    manager:=nativecore.FromEnv()
    if manager.IdentityVision=="" { fail(fmt.Errorf("SPICE_FACE_EMBED_MODEL is not configured")) }
    ctx,cancel:=context.WithTimeout(context.Background(),2*time.Minute); defer cancel()
    vec,meta,err:=manager.Embed(ctx,input); if err!=nil { fail(err) }
    vec=ident.Normalize(vec)
    write(map[string]any{
        "embedding":vec,
        "dimensions":len(vec),
        "model":"arcface-w600k-r50-qnn",
        "alignment":"center-crop-112",
        "npu":true,
        "latency_ms":meta["latency_ms"],
        "l2_norm":meta["l2_norm"],
    })
}

func commandIdentity() {
    payload:=readObject(); generated,err:=decodeB64(payload["image_base64"]); if err!=nil { fail(err) }
    refs,ok:=payload["references"].([]any); if !ok || len(refs)==0 { fail(fmt.Errorf("identity requires references")) }

    manager:=nativecore.FromEnv()
    if manager.IdentityVision != "" {
        input,err:=ident.ArcFaceInput(generated); if err!=nil { fail(err) }
        ctx,cancel:=context.WithTimeout(context.Background(),2*time.Minute)
        generatedEmbedding,meta,err:=manager.Embed(ctx,input)
        cancel()
        if err==nil {
            scores:=make([]float64,0,len(refs))
            for _,item:=range refs {
                obj,ok:=item.(map[string]any); if !ok { continue }
                ref,err:=decodeB64(obj["image_base64"]); if err!=nil { continue }
                refInput,err:=ident.ArcFaceInput(ref); if err!=nil { continue }
                refCtx,refCancel:=context.WithTimeout(context.Background(),2*time.Minute)
                refEmbedding,_,err:=manager.Embed(refCtx,refInput)
                refCancel()
                if err!=nil { continue }
                score,err:=ident.Cosine(generatedEmbedding,refEmbedding)
                if err==nil { scores=append(scores,score) }
            }
            if len(scores)>0 {
                maxScore,sum:=scores[0],0.0
                for _,s:=range scores { if s>maxScore {maxScore=s}; sum+=s }
                write(map[string]any{
                    "score":maxScore,
                    "mean_score":sum/float64(len(scores)),
                    "reference_count":len(scores),
                    "model":"arcface-w600k-r50-qnn",
                    "embedding_dimensions":len(generatedEmbedding),
                    "alignment":"center-crop-112",
                    "npu":true,
                    "latency_ms":meta["latency_ms"],
                    "l2_norm":meta["l2_norm"],
                })
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
    write(map[string]any{
        "score":maxScore,
        "mean_score":sum/float64(len(scores)),
        "reference_count":len(scores),
        "model":"go-perceptual-identity-v1",
        "alignment":"none",
        "npu":false,
        "fallback_reason":"SPICE_FACE_EMBED_MODEL unavailable or NPU embedding failed",
    })
}

func commandHealth() {
    ctx,cancel:=context.WithTimeout(context.Background(),time.Second); defer cancel()
    m:=nativecore.FromEnv(); write(map[string]any{"ok":m.Health(ctx),"backend":"go-managed-qnn"})
}

func main() {
    if len(os.Args)!=2 { fail(fmt.Errorf("usage: spicemedia generate|quality|embed|identity|health")) }
    switch os.Args[1] {
    case "generate": commandGenerate()
    case "quality": commandQuality()
    case "embed": commandEmbed()
    case "identity": commandIdentity()
    case "health": commandHealth()
    default: fail(fmt.Errorf("unknown command: %s",os.Args[1]))
    }
}