package faceswap

import (
	"bytes"
	"context"
	"encoding/binary"
	"fmt"
	"image"
	"image/color"
	"image/png"
	"math"
	"os"
	"strings"

	ident "github.com/jcltd303-hub/spice-hoes/internal/identity"
	"github.com/jcltd303-hub/spice-hoes/internal/nativecore"
	ort "github.com/shota3506/onnxruntime-purego/onnxruntime"
)

const swapSize = 128

type Config struct {
	RuntimeLibrary string
	ModelPath      string
	Threads        int
}

type Meta struct {
	Model       string  `json:"model"`
	Alignment   string  `json:"alignment"`
	TargetScore float64 `json:"target_face_score"`
}

type Swapper struct {
	rt      *ort.Runtime
	env     *ort.Env
	session *ort.Session
	emap    []float32
	manager *nativecore.Manager
	model   string
}

func ConfigFromEnv() Config {
	return Config{
		RuntimeLibrary: strings.TrimSpace(os.Getenv("SPICE_ONNXRUNTIME_LIB")),
		ModelPath: strings.TrimSpace(os.Getenv("SPICE_INSWAPPER_MODEL")),
		Threads: 1,
	}
}

func Available(cfg Config) bool {
	if cfg.RuntimeLibrary == "" || cfg.ModelPath == "" {
		return false
	}
	if _, err := os.Stat(cfg.RuntimeLibrary); err != nil {
		return false
	}
	if _, err := os.Stat(cfg.ModelPath); err != nil {
		return false
	}
	return true
}

func New(ctx context.Context, cfg Config, manager *nativecore.Manager) (*Swapper, error) {
	_ = ctx
	if manager == nil {
		manager = nativecore.FromEnv()
	}
	if !Available(cfg) {
		return nil, fmt.Errorf("face swap assets unavailable; set SPICE_ONNXRUNTIME_LIB and SPICE_INSWAPPER_MODEL")
	}
	emap, dims, err := extractLastFloatInitializer(cfg.ModelPath)
	if err != nil {
		return nil, fmt.Errorf("read inswapper embedding map: %w", err)
	}
	if len(dims) != 2 || dims[0] != 512 || dims[1] != 512 || len(emap) != 512*512 {
		return nil, fmt.Errorf("unexpected inswapper embedding map shape %v (%d values)", dims, len(emap))
	}
	rt, err := ort.NewRuntime(cfg.RuntimeLibrary, 23)
	if err != nil {
		return nil, fmt.Errorf("load ONNX Runtime: %w", err)
	}
	env, err := rt.NewEnv("spicy-inswapper", ort.LoggingLevelWarning)
	if err != nil {
		_ = rt.Close()
		return nil, fmt.Errorf("create ONNX environment: %w", err)
	}
	opts := &ort.SessionOptions{IntraOpNumThreads: cfg.Threads}
	session, err := rt.NewSession(env, cfg.ModelPath, opts)
	if err != nil {
		env.Close()
		_ = rt.Close()
		return nil, fmt.Errorf("load InSwapper model: %w", err)
	}
	if len(session.InputNames()) != 2 || len(session.OutputNames()) != 1 {
		session.Close(); env.Close(); _ = rt.Close()
		return nil, fmt.Errorf("unexpected InSwapper IO: inputs=%v outputs=%v", session.InputNames(), session.OutputNames())
	}
	return &Swapper{rt:rt, env:env, session:session, emap:emap, manager:manager, model:cfg.ModelPath}, nil
}

func (s *Swapper) Close() {
	if s == nil { return }
	if s.session != nil { s.session.Close() }
	if s.env != nil { s.env.Close() }
	if s.rt != nil { _ = s.rt.Close() }
}

func detectPrimary(ctx context.Context, m *nativecore.Manager, raw []byte) (ident.FaceDetection, error) {
	prep, err := ident.SCRFDInput(raw)
	if err != nil { return ident.FaceDetection{}, err }
	outputs, _, err := m.Detect(ctx, prep.Tensor)
	if err != nil { return ident.FaceDetection{}, err }
	faces, err := ident.DecodeSCRFD(outputs, prep, 0.5, 0.4)
	if err != nil { return ident.FaceDetection{}, err }
	if len(faces) == 0 { return ident.FaceDetection{}, fmt.Errorf("no face detected") }
	return faces[0], nil
}

func sourceEmbedding(ctx context.Context, m *nativecore.Manager, raw []byte) ([]float64, error) {
	face, err := detectPrimary(ctx, m, raw)
	if err != nil { return nil, err }
	input, err := ident.ArcFaceInputAligned(raw, face.Landmarks)
	if err != nil { return nil, err }
	vec, _, err := m.Embed(ctx, input)
	if err != nil { return nil, err }
	vec = ident.Normalize(vec)
	if len(vec) != 512 {
		return nil, fmt.Errorf("InSwapper requires 512D ArcFace embedding, got %d", len(vec))
	}
	return vec, nil
}

func bilinear(img image.Image, x, y float64) color.RGBA {
	b := img.Bounds()
	if x < float64(b.Min.X) || y < float64(b.Min.Y) || x > float64(b.Max.X-1) || y > float64(b.Max.Y-1) {
		return color.RGBA{0,0,0,255}
	}
	x0,y0 := int(math.Floor(x)),int(math.Floor(y))
	x1,y1 := x0+1,y0+1
	if x1>=b.Max.X { x1=b.Max.X-1 }
	if y1>=b.Max.Y { y1=b.Max.Y-1 }
	fx,fy := x-float64(x0),y-float64(y0)
	sample:=func(xx,yy int)(float64,float64,float64){
		r,g,bv,_:=img.At(xx,yy).RGBA()
		return float64(r>>8),float64(g>>8),float64(bv>>8)
	}
	r00,g00,b00:=sample(x0,y0); r10,g10,b10:=sample(x1,y0)
	r01,g01,b01:=sample(x0,y1); r11,g11,b11:=sample(x1,y1)
	mix:=func(a,b,c,d float64) uint8 {
		top:=a*(1-fx)+b*fx; bot:=c*(1-fx)+d*fx
		v:=top*(1-fy)+bot*fy
		if v<0 {v=0}; if v>255 {v=255}
		return uint8(math.Round(v))
	}
	return color.RGBA{mix(r00,r10,r01,r11),mix(g00,g10,g01,g11),mix(b00,b10,b01,b11),255}
}

func alignedCrop(img image.Image, landmarks [5]ident.Point) (*image.RGBA, ident.SimilarityTransform, error) {
	dst := ident.ArcFaceTemplate
	scale := float64(swapSize)/float64(ident.ArcFaceSize)
	for i := range dst {
		dst[i].X *= scale
		dst[i].Y *= scale
	}
	t, err := ident.EstimateSimilarity(landmarks, dst)
	if err != nil { return nil, t, err }
	det := t.A*t.A+t.B*t.B
	if det < 1e-12 { return nil, t, fmt.Errorf("non-invertible face transform") }
	out := image.NewRGBA(image.Rect(0,0,swapSize,swapSize))
	for y:=0;y<swapSize;y++ {
		for x:=0;x<swapSize;x++ {
			dx:=float64(x)-t.TX; dy:=float64(y)-t.TY
			sx:=(t.A*dx+t.B*dy)/det
			sy:=(-t.B*dx+t.A*dy)/det
			out.SetRGBA(x,y,bilinear(img,sx,sy))
		}
	}
	return out,t,nil
}

func imageTensor(img image.Image) []float32 {
	plane:=swapSize*swapSize
	out:=make([]float32,3*plane)
	for y:=0;y<swapSize;y++ {
		for x:=0;x<swapSize;x++ {
			r,g,b,_:=img.At(x,y).RGBA()
			i:=y*swapSize+x
			out[i]=float32(r>>8)/255
			out[plane+i]=float32(g>>8)/255
			out[2*plane+i]=float32(b>>8)/255
		}
	}
	return out
}

func transformedLatent(src []float64, emap []float32) []float32 {
	out:=make([]float32,512)
	for i:=0;i<512;i++ {
		s:=float32(src[i])
		base:=i*512
		for j:=0;j<512;j++ { out[j]+=s*emap[base+j] }
	}
	var norm float64
	for _,v:=range out { norm+=float64(v*v) }
	norm=math.Sqrt(norm)
	if norm>1e-12 { for i:=range out { out[i]/=float32(norm) } }
	return out
}

func outputImage(data []float32, shape []int64) (*image.RGBA,error) {
	if len(shape)!=4 || shape[0]!=1 || shape[1]!=3 || shape[2]!=swapSize || shape[3]!=swapSize {
		return nil,fmt.Errorf("unexpected InSwapper output shape %v",shape)
	}
	if len(data)!=3*swapSize*swapSize { return nil,fmt.Errorf("unexpected output length %d",len(data)) }
	out:=image.NewRGBA(image.Rect(0,0,swapSize,swapSize))
	plane:=swapSize*swapSize
	clamp:=func(v float32) uint8 {
		if v<0 {v=0}; if v>1 {v=1}; return uint8(math.Round(float64(v*255)))
	}
	for y:=0;y<swapSize;y++ { for x:=0;x<swapSize;x++ {
		i:=y*swapSize+x
		out.SetRGBA(x,y,color.RGBA{clamp(data[i]),clamp(data[plane+i]),clamp(data[2*plane+i]),255})
	}}
	return out,nil
}

func featherMask(x,y float64) float64 {
	cx,cy:=float64(swapSize-1)/2,float64(swapSize-1)/2
	nx:=(x-cx)/(float64(swapSize)*0.46)
	ny:=(y-cy)/(float64(swapSize)*0.52)
	r:=math.Sqrt(nx*nx+ny*ny)
	if r>=1 { return 0 }
	if r<=0.72 { return 1 }
	v:=(1-r)/(1-0.72)
	return v*v*(3-2*v)
}

func pasteBack(target image.Image, fake *image.RGBA, t ident.SimilarityTransform, face ident.FaceDetection) *image.RGBA {
	b:=target.Bounds()
	out:=image.NewRGBA(b)
	for y:=b.Min.Y;y<b.Max.Y;y++ { for x:=b.Min.X;x<b.Max.X;x++ { out.Set(x,y,target.At(x,y)) } }
	padX:=(face.X2-face.X1)*0.35; padY:=(face.Y2-face.Y1)*0.45
	x0:=int(math.Max(float64(b.Min.X),face.X1-padX)); x1:=int(math.Min(float64(b.Max.X-1),face.X2+padX))
	y0:=int(math.Max(float64(b.Min.Y),face.Y1-padY)); y1:=int(math.Min(float64(b.Max.Y-1),face.Y2+padY))
	for y:=y0;y<=y1;y++ { for x:=x0;x<=x1;x++ {
		cx:=t.A*float64(x)-t.B*float64(y)+t.TX
		cy:=t.B*float64(x)+t.A*float64(y)+t.TY
		if cx<0 || cy<0 || cx>swapSize-1 || cy>swapSize-1 { continue }
		alpha:=featherMask(cx,cy)
		if alpha<=0 { continue }
		fc:=bilinear(fake,cx,cy)
		tr,tg,tb,_:=target.At(x,y).RGBA()
		mix:=func(a uint8,b uint32) uint8 { return uint8(math.Round(alpha*float64(a)+(1-alpha)*float64(b>>8))) }
		out.SetRGBA(x,y,color.RGBA{mix(fc.R,tr),mix(fc.G,tg),mix(fc.B,tb),255})
	}}
	return out
}

func (s *Swapper) Swap(ctx context.Context, sourceRaw, targetRaw []byte) ([]byte, Meta, error) {
	if s == nil || s.session == nil { return nil,Meta{},fmt.Errorf("swapper not initialized") }
	sourceVec,err:=sourceEmbedding(ctx,s.manager,sourceRaw)
	if err!=nil { return nil,Meta{},fmt.Errorf("source identity: %w",err) }
	targetFace,err:=detectPrimary(ctx,s.manager,targetRaw)
	if err!=nil { return nil,Meta{},fmt.Errorf("target face: %w",err) }
	targetImg,_,err:=image.Decode(bytes.NewReader(targetRaw))
	if err!=nil { return nil,Meta{},fmt.Errorf("decode target: %w",err) }
	crop,t,err:=alignedCrop(targetImg,targetFace.Landmarks)
	if err!=nil { return nil,Meta{},err }
	imageInput:=imageTensor(crop)
	latent:=transformedLatent(sourceVec,s.emap)
	inNames:=s.session.InputNames()
	outNames:=s.session.OutputNames()
	imgTensor,err:=ort.NewTensorValue(s.rt,imageInput,[]int64{1,3,swapSize,swapSize})
	if err!=nil { return nil,Meta{},err }
	defer imgTensor.Close()
	latentTensor,err:=ort.NewTensorValue(s.rt,latent,[]int64{1,512})
	if err!=nil { return nil,Meta{},err }
	defer latentTensor.Close()
	outputs,err:=s.session.Run(ctx,map[string]*ort.Value{inNames[0]:imgTensor,inNames[1]:latentTensor})
	if err!=nil { return nil,Meta{},fmt.Errorf("InSwapper inference: %w",err) }
	outVal:=outputs[outNames[0]]
	if outVal==nil { return nil,Meta{},fmt.Errorf("InSwapper returned no output") }
	defer outVal.Close()
	data,shape,err:=ort.GetTensorData[float32](outVal)
	if err!=nil { return nil,Meta{},err }
	fake,err:=outputImage(data,shape)
	if err!=nil { return nil,Meta{},err }
	merged:=pasteBack(targetImg,fake,t,targetFace)
	var buf bytes.Buffer
	if err:=png.Encode(&buf,merged); err!=nil { return nil,Meta{},err }
	return buf.Bytes(),Meta{Model:s.model,Alignment:"scrfd-5pt-128",TargetScore:targetFace.Score},nil
}

func readUvarint(data []byte, pos *int) (uint64,error) {
	if *pos>=len(data) { return 0,fmt.Errorf("unexpected EOF") }
	v,n:=binary.Uvarint(data[*pos:])
	if n<=0 { return 0,fmt.Errorf("invalid protobuf varint") }
	*pos+=n
	return v,nil
}

func readField(data []byte,pos *int)(field int,wire int,payload []byte,varint uint64,err error){
	key,e:=readUvarint(data,pos); if e!=nil {err=e;return}
	field=int(key>>3); wire=int(key&7)
	switch wire {
	case 0:
		varint,err=readUvarint(data,pos)
	case 1:
		if *pos+8>len(data){err=fmt.Errorf("truncated fixed64");return}; payload=data[*pos:*pos+8]; *pos+=8
	case 2:
		var n uint64; n,err=readUvarint(data,pos); if err!=nil{return}
		if n>uint64(len(data)-*pos){err=fmt.Errorf("truncated bytes field");return}
		payload=data[*pos:*pos+int(n)]; *pos+=int(n)
	case 5:
		if *pos+4>len(data){err=fmt.Errorf("truncated fixed32");return}; payload=data[*pos:*pos+4]; *pos+=4
	default:
		err=fmt.Errorf("unsupported protobuf wire type %d",wire)
	}
	return
}

func extractLastFloatInitializer(path string)([]float32,[]int64,error){
	model,err:=os.ReadFile(path); if err!=nil{return nil,nil,err}
	var graph []byte
	for p:=0;p<len(model);{
		field,wire,payload,_,e:=readField(model,&p); if e!=nil{return nil,nil,e}
		if field==7 && wire==2 { graph=payload }
	}
	if len(graph)==0{return nil,nil,fmt.Errorf("ONNX graph field not found")}
	var tensor []byte
	for p:=0;p<len(graph);{
		field,wire,payload,_,e:=readField(graph,&p); if e!=nil{return nil,nil,e}
		if field==5 && wire==2 { tensor=payload }
	}
	if len(tensor)==0{return nil,nil,fmt.Errorf("ONNX initializer not found")}
	var dims []int64
	dataType:=0
	var raw []byte
	var floats []float32
	for p:=0;p<len(tensor);{
		field,wire,payload,v,e:=readField(tensor,&p); if e!=nil{return nil,nil,e}
		switch field {
		case 1:
			if wire==0 { dims=append(dims,int64(v)) }
			if wire==2 {
				for q:=0;q<len(payload);{ d,e:=readUvarint(payload,&q); if e!=nil{return nil,nil,e}; dims=append(dims,int64(d)) }
			}
		case 2:
			if wire==0 { dataType=int(v) }
		case 4:
			if wire==2 {
				if len(payload)%4!=0{return nil,nil,fmt.Errorf("invalid packed float_data")}
				for i:=0;i<len(payload);i+=4{ floats=append(floats,math.Float32frombits(binary.LittleEndian.Uint32(payload[i:i+4]))) }
			}
		case 9:
			if wire==2 { raw=append([]byte(nil),payload...) }
		}
	}
	if dataType!=1{return nil,nil,fmt.Errorf("embedding map is not FLOAT tensor (type=%d)",dataType)}
	if len(raw)>0 {
		if len(raw)%4!=0{return nil,nil,fmt.Errorf("invalid raw float tensor")}
		floats=make([]float32,len(raw)/4)
		for i:=range floats{ floats[i]=math.Float32frombits(binary.LittleEndian.Uint32(raw[i*4:i*4+4])) }
	}
	return floats,dims,nil
}
