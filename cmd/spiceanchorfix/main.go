package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/jcltd303-hub/spice-hoes/internal/identitygen"
)

func main() {
	personas := flag.String("personas","lila_hart,ruby_wren,tess_wilder,zara_voss","comma-separated personas to repair")
	attempts := flag.Int("attempts",4,"candidates per persona (max 12)")
	keep := flag.Int("keep",3,"top discriminative anchors to keep")
	apply := flag.Bool("apply",false,"replace current refs with selected anchors and rebuild banks")
	out := flag.String("out","anchor-fix.json","JSON report path")
	flag.Parse()

	var ids []string
	for _, id := range strings.Split(*personas,",") {
		if id=strings.TrimSpace(id); id!="" { ids=append(ids,id) }
	}

	ctx,cancel := context.WithTimeout(context.Background(), 90*time.Minute)
	defer cancel()
	res,err := identitygen.AnchorFix(ctx,ids,*attempts,*keep,*apply)
	if err!=nil {
		fmt.Fprintln(os.Stderr,"anchorfix:",err)
		os.Exit(1)
	}
	raw,_:=json.MarshalIndent(res,"","  ")
	if *out!="" { _=os.WriteFile(*out,raw,0o644) }
	for _,p:=range res.Personas {
		fmt.Printf("%s: generated=%d selected=%d\n",p.PersonaID,p.Generated,len(p.Selected))
		for i,c:=range p.Selected {
			fmt.Printf("  #%d margin=%+.3f own=%.3f other=%.3f quality=%.3f %s\n",i+1,c.Margin,c.OwnScore,c.OtherScore,c.Quality,c.AssetPath)
		}
	}
	if *apply {
		fmt.Println("applied: selected anchors installed, prior refs moved under data/references/_anchorfix/")
	} else {
		fmt.Println("dry run only; rerun with -apply after reviewing margins")
	}
	if *out!="" { fmt.Println("report:",*out) }
}
