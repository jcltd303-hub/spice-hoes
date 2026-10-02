package identitygen

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/jcltd303-hub/spice-hoes/internal/faceswap"
	"github.com/jcltd303-hub/spice-hoes/internal/imagemetrics"
	"github.com/jcltd303-hub/spice-hoes/internal/nativecore"
)

type AutonomousRequest struct {
	PersonaID         string  `json:"persona_id"`
	PersonaDir        string  `json:"persona_dir,omitempty"`
	ReferenceRoot     string  `json:"reference_root,omitempty"`
	OutputRoot        string  `json:"output_root,omitempty"`
	PoseOutputRoot    string  `json:"pose_output_root,omitempty"`
	Generator         string  `json:"generator,omitempty"`
	SwapMode          string  `json:"swap_mode,omitempty"`
	Seed              int64   `json:"seed,omitempty"`
	MaxAttempts       int     `json:"max_attempts,omitempty"`
	PoseAttempts      int     `json:"pose_attempts,omitempty"`
	IdentityThreshold float64 `json:"identity_threshold,omitempty"`
	QualityThreshold  float64 `json:"quality_threshold,omitempty"`
	Progress          func(ProgressEvent) `json:"-"`
}

type PortfolioPose struct {
	PoseID          string               `json:"pose_id"`
	BasePath        string               `json:"base_path"`
	FinalPath       string               `json:"final_path"`
	IdentityApplied bool                 `json:"identity_applied"`
	Identity        IdentityResult       `json:"identity"`
	Quality         imagemetrics.Metrics `json:"quality"`
	Passed          bool                 `json:"passed"`
	Reason          string               `json:"reason,omitempty"`
}

type AutonomousResult struct {
	OK                bool               `json:"ok"`
	PersonaID         string             `json:"persona_id"`
	ReferenceComplete bool               `json:"reference_complete"`
	PortfolioComplete bool               `json:"portfolio_complete"`
	Reference          BootstrapAllResult `json:"reference"`
	Poses              PoseMasterResult   `json:"poses"`
	Portfolio          []PortfolioPose    `json:"portfolio"`
	PortfolioSheet     string             `json:"portfolio_sheet,omitempty"`
	ManifestPath       string             `json:"manifest_path,omitempty"`
	SwapAvailable      bool               `json:"swap_available"`
	SwapMode           string             `json:"swap_mode"`
}

func emitAuto(req AutonomousRequest, pct float64, stage string, metrics map[string]any) {
	if req.Progress != nil { req.Progress(ProgressEvent{Percent:pct,Stage:stage,Metrics:metrics}) }
}

func AutonomousIdentity(ctx context.Context, req AutonomousRequest) (AutonomousResult, error) {
	if strings.TrimSpace(req.PersonaID)=="" {
		return AutonomousResult{},fmt.Errorf("persona_id is required")
	}
	if req.PersonaDir=="" { req.PersonaDir="personas" }
	if req.ReferenceRoot=="" { req.ReferenceRoot=filepath.Join("data","references") }
	if req.OutputRoot=="" { req.OutputRoot=filepath.Join("data","identity-candidates") }
	if req.PoseOutputRoot=="" { req.PoseOutputRoot=filepath.Join("data","pose-templates") }
	if req.MaxAttempts<=0 { req.MaxAttempts=48 }
	if req.PoseAttempts<=0 { req.PoseAttempts=4 }
	if req.IdentityThreshold<=0 { req.IdentityThreshold=0.82 }
	if req.QualityThreshold<=0 { req.QualityThreshold=0.78 }
	if req.SwapMode=="" { req.SwapMode="auto" }
	req.SwapMode=strings.ToLower(strings.TrimSpace(req.SwapMode))

	emitAuto(req,1,"reference portfolio",map[string]any{"persona_id":req.PersonaID})
	refs,err:=BootstrapAll(ctx,BootstrapAllRequest{
		PersonaID:req.PersonaID,PersonaDir:req.PersonaDir,
		ReferenceRoot:req.ReferenceRoot,OutputRoot:req.OutputRoot,
		TargetReferences:len(canonicalViews),MaxAttempts:req.MaxAttempts,
		Theme:"canonical identity reference portfolio",
		Style:"photorealistic neutral identity reference photography",
		Width:1024,Height:1024,Steps:20,Guidance:7,
		IdentityThreshold:req.IdentityThreshold,QualityThreshold:req.QualityThreshold,
		Generator:req.Generator,Seed:req.Seed,
		Progress:func(ev ProgressEvent){
			emitAuto(req,2+ev.Percent*0.43,ev.Stage,ev.Metrics)
		},
	})
	if err!=nil { return AutonomousResult{},err }
	result:=AutonomousResult{PersonaID:req.PersonaID,Reference:refs,ReferenceComplete:refs.OK,SwapMode:req.SwapMode}
	if !refs.OK {
		result.OK=false
		return result,nil
	}

	emitAuto(req,46,"body posture portfolio",nil)
	poseResult,err:=GeneratePoseMasters(ctx,PoseMasterRequest{
		PersonaID:req.PersonaID,
		PersonaPath:filepath.Join(req.PersonaDir,req.PersonaID+".yaml"),
		OutputRoot:req.PoseOutputRoot,Generator:req.Generator,
		Seed:req.Seed+100000,Width:768,Height:1024,
		QualityThreshold:req.QualityThreshold,MaxAttempts:req.PoseAttempts,
		Progress:func(ev ProgressEvent){
			emitAuto(req,46+ev.Percent*0.30,ev.Stage,ev.Metrics)
		},
	})
	if err!=nil { return result,err }
	result.Poses=poseResult

	gallery,err:=loadReferences(req.ReferenceRoot,req.PersonaID)
	if err!=nil { return result,err }
	if len(gallery)==0 { return result,fmt.Errorf("reference gallery empty after bootstrap") }
	sourcePath:=filepath.Join(req.ReferenceRoot,req.PersonaID,"00_front.png")
	sourceRaw,err:=os.ReadFile(sourcePath)
	if err!=nil { return result,fmt.Errorf("read canonical source face: %w",err) }

	manager:=nativecore.FromEnv()
	swapCfg:=faceswap.ConfigFromEnv()
	result.SwapAvailable=faceswap.Available(swapCfg)
	var swapper *faceswap.Swapper
	if req.SwapMode!="disabled" && result.SwapAvailable {
		swapper,err=faceswap.New(ctx,swapCfg,manager)
		if err!=nil && req.SwapMode=="required" { return result,err }
	}
	if swapper!=nil { defer swapper.Close() }
	if req.SwapMode=="required" && swapper==nil {
		return result,fmt.Errorf("swap_mode=required but InSwapper runtime/model are unavailable")
	}

	finalAssets:=make([]PoseAsset,0,len(poseResult.Assets))
	passCount:=0
	for i,asset:=range poseResult.Assets {
		raw,readErr:=os.ReadFile(asset.Path)
		if readErr!=nil { return result,readErr }
		finalRaw:=raw
		finalPath:=asset.Path
		applied:=false
		reason:=""
		identity:=IdentityResult{Passed:true,Reason:"rear_pose_no_face_gate",Metric:"not_applicable_rear_view"}
		if asset.PoseID!="rear_standing" {
			identity=scoreIdentity(ctx,manager,raw,gallery,req.IdentityThreshold)
			if !(identity.Scored && identity.Passed) && swapper!=nil {
				swapped,_,swapErr:=swapper.Swap(ctx,sourceRaw,raw)
				if swapErr==nil {
					swappedIdentity:=scoreIdentity(ctx,manager,swapped,gallery,req.IdentityThreshold)
					if swappedIdentity.Scored && swappedIdentity.Passed {
						finalRaw=swapped
						identity=swappedIdentity
						applied=true
						finalPath=strings.TrimSuffix(asset.Path,filepath.Ext(asset.Path))+"_identity.png"
						if err:=os.WriteFile(finalPath,finalRaw,0o644);err!=nil{return result,err}
					} else {
						reason="swap_identity_below_threshold"
						identity=swappedIdentity
					}
				} else {
					reason=swapErr.Error()
				}
			}
		}
		quality,qErr:=imagemetrics.Analyze(finalRaw)
		if qErr!=nil { return result,qErr }
		passed:=quality.LocalScore>=req.QualityThreshold && (asset.PoseID=="rear_standing" || (identity.Scored && identity.Passed))
		if passed { passCount++ }
		if reason=="" && !passed {
			if quality.LocalScore<req.QualityThreshold { reason="quality_below_threshold" } else { reason="identity_below_threshold" }
		}
		result.Portfolio=append(result.Portfolio,PortfolioPose{
			PoseID:asset.PoseID,BasePath:asset.Path,FinalPath:finalPath,
			IdentityApplied:applied,Identity:identity,Quality:quality,Passed:passed,Reason:reason,
		})
		finalAsset:=asset
		finalAsset.Path=finalPath
		finalAsset.Quality=quality
		finalAsset.QualityPassed=quality.LocalScore>=req.QualityThreshold
		finalAssets=append(finalAssets,finalAsset)
		emitAuto(req,76+22*float64(i+1)/float64(len(poseResult.Assets)),"portfolio identity verification",map[string]any{
			"pose":asset.PoseID,"passed":passed,"identity_score":identity.Score,"swap_applied":applied,
		})
	}

	result.PortfolioComplete=passCount==len(poseResult.Assets)
	result.PortfolioSheet=filepath.Join(poseResult.OutputDir,"identity_master_9pose.png")
	if err:=writePoseContactSheet(finalAssets,result.PortfolioSheet);err!=nil{return result,err}
	result.OK=result.ReferenceComplete && result.PortfolioComplete
	result.ManifestPath=filepath.Join(poseResult.OutputDir,"identity_portfolio_manifest.json")
	manifest,_:=json.MarshalIndent(result,"","  ")
	if err:=os.WriteFile(result.ManifestPath,manifest,0o644);err!=nil{return result,err}
	emitAuto(req,100,"autonomous identity complete",map[string]any{
		"ok":result.OK,"reference_complete":result.ReferenceComplete,
		"portfolio_complete":result.PortfolioComplete,"swap_available":result.SwapAvailable,
		"manifest":result.ManifestPath,
	})
	return result,nil
}
