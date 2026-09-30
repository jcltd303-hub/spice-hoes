"""n8n Community Edition workflow exporter."""
import json
from pathlib import Path
def n8n_workflow(name="SpiceCore free production"):
    nodes=[
      {"parameters":{},"id":"manual","name":"Start batch","type":"n8n-nodes-base.manualTrigger","typeVersion":1,"position":[0,0]},
      {"parameters":{"command":"python3 -m spicecore.cli recommend --seed 42"},"id":"recommend","name":"Choose experiment","type":"n8n-nodes-base.executeCommand","typeVersion":1,"position":[220,0]},
      {"parameters":{"command":"python3 -m spicecore.cli free-plan --theme city-nights --channel TikTok --output-dir jobs"},"id":"plan","name":"Build free production jobs","type":"n8n-nodes-base.executeCommand","typeVersion":1,"position":[440,0]},
      {"parameters":{"command":"echo 'Complete browser generation tasks in jobs/, then import approved assets.'"},"id":"handoff","name":"Human generation handoff","type":"n8n-nodes-base.executeCommand","typeVersion":1,"position":[660,0]}]
    return {"name":name,"nodes":nodes,"connections":{"Start batch":{"main":[[{"node":"Choose experiment","type":"main","index":0}]]},"Choose experiment":{"main":[[{"node":"Build free production jobs","type":"main","index":0}]]},"Build free production jobs":{"main":[[{"node":"Human generation handoff","type":"main","index":0}]]}},"settings":{"executionOrder":"v1"},"active":False}
def write_n8n(output):
    path=Path(output); path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(n8n_workflow(),indent=2)+"\n"); return path
