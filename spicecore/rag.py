"""Dependency-free local RAG for project knowledge."""
from __future__ import annotations
import math,re
from collections import Counter
from pathlib import Path
TOKEN=re.compile(r"[a-z0-9][a-z0-9_-]{1,}",re.I)
def _terms(text): return Counter(t.lower() for t in TOKEN.findall(text))
def chunk_text(text,source,size=900):
    chunks=[]; buf=""
    for p in [x.strip() for x in text.split("\n\n") if x.strip()]:
        if buf and len(buf)+len(p)+2>size: chunks.append({"source":source,"text":buf}); buf=""
        buf=(buf+"\n\n"+p).strip()
    if buf: chunks.append({"source":source,"text":buf})
    return chunks
class LocalRAG:
    def __init__(self,documents):
        self.documents=documents; self.vectors=[_terms(d["text"]) for d in documents]; df=Counter()
        for v in self.vectors: df.update(v.keys())
        n=max(1,len(documents)); self.idf={t:math.log((n+1)/(f+1))+1 for t,f in df.items()}
    @classmethod
    def from_paths(cls,paths):
        docs=[]
        for raw in paths:
            path=Path(raw); files=sorted(p for p in path.rglob("*") if p.suffix.lower() in {".md",".txt",".yaml",".yml"}) if path.is_dir() else [path]
            for f in files:
                if f.exists(): docs.extend(chunk_text(f.read_text(errors="replace"),str(f)))
        return cls(docs)
    def search(self,query,k=5):
        q=_terms(query)
        if not q or not self.documents:return []
        def w(v):return {t:c*self.idf.get(t,1.0) for t,c in v.items()}
        qv=w(q); qn=math.sqrt(sum(x*x for x in qv.values())) or 1; scored=[]
        for doc,raw in zip(self.documents,self.vectors):
            dv=w(raw); dn=math.sqrt(sum(x*x for x in dv.values())) or 1; score=sum(qv.get(t,0)*dv.get(t,0) for t in qv)/(qn*dn)
            if score: scored.append({**doc,"score":round(score,6)})
        return sorted(scored,key=lambda x:(-x["score"],x["source"]))[:k]
