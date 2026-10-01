"""Local identity-transfer backend executed as a subprocess.

Set SPICE_LOCAL_IDENTITY_CMD to a local, commercially licensed identity tool.
Placeholders: {reference}, {target}, {output}. No shell is used.
"""
from __future__ import annotations
import os,shlex,shutil,subprocess
from pathlib import Path

def default_command():
 runner=Path(__file__).resolve().parent.parent/"scripts"/"ghostv2-run"
 return f"{runner} {{reference}} {{target}} {{output}}"

def status(command=None):
 template=(command or os.environ.get("SPICE_LOCAL_IDENTITY_CMD","") or default_command()).strip()
 if not template:
  return {"ready":False,"reason":"SPICE_LOCAL_IDENTITY_CMD is not configured"}
 try: argv=shlex.split(template)
 except ValueError as exc: return {"ready":False,"reason":f"Invalid command template: {exc}"}
 if not argv: return {"ready":False,"reason":"Identity command is empty"}
 exe=argv[0]
 found=shutil.which(exe) if "/" not in exe else (exe if Path(exe).exists() else None)
 return {"ready":bool(found),"command":template,"executable":found,"reason":None if found else f"Executable not found: {exe}"}

def transfer(reference,target,output,command=None,timeout=900):
 state=status(command)
 if not state["ready"]: raise RuntimeError(state["reason"])
 out=Path(output); out.parent.mkdir(parents=True,exist_ok=True)
 values={"reference":str(Path(reference).resolve()),"target":str(Path(target).resolve()),"output":str(out.resolve())}
 argv=[part.format(**values) for part in shlex.split(state["command"])]
 proc=subprocess.run(argv,capture_output=True,text=True,timeout=timeout)
 if proc.returncode: raise RuntimeError(f"Local identity command failed ({proc.returncode}): {proc.stderr[-1200:]}")
 if not out.is_file(): raise RuntimeError("Local identity command completed without creating output")
 return {"asset_uri":str(out),"provider":"identity-local","command_executable":argv[0],"stdout_tail":proc.stdout[-500:]}
