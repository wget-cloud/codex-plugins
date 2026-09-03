#!/usr/bin/env python3
"""Run only checksum-pinned official validators, offline unless asked otherwise."""
from __future__ import annotations
import argparse, hashlib, json, os, re, subprocess, sys, tempfile, urllib.request
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set

ROOT=Path(__file__).resolve().parents[1]; DEFAULT_LOCK=ROOT/"scripts/official_validators.lock.json"; DEFAULT_CACHE=Path(os.environ.get("XDG_CACHE_HOME", str(Path(tempfile.gettempdir()))))/"wgc-official-validators"
NAMES={"quick_validate.py","validate_plugin.py","identifier_validation.py"}; HEX40=re.compile(r"^[0-9a-f]{40}$"); HEX64=re.compile(r"^[0-9a-f]{64}$")
REQUIRED_VALIDATORS = NAMES
def sha256(path: Path) -> str:
    digest=hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024*1024),b""): digest.update(chunk)
    return digest.hexdigest()
def load_lock(path: Path) -> Dict[str, Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict) or set(value)!={"source","commit","license_provenance","validators"} or value["source"]!="openai/codex" or not isinstance(value["license_provenance"],str) or len(value["license_provenance"])<20 or not isinstance(value["commit"],str) or not HEX40.fullmatch(value["commit"]): raise ValueError("lock root schema is invalid")
    validators=value["validators"]
    if not isinstance(validators,dict) or set(validators)!=NAMES: raise ValueError("lock must contain exactly approved validator names")
    prefix="https://raw.githubusercontent.com/openai/codex/"+value["commit"]+"/"
    for name,entry in validators.items():
        if not isinstance(entry,dict) or set(entry)!={"url","sha256"} or not isinstance(entry["url"],str) or not entry["url"].startswith(prefix) or not entry["url"].endswith("/"+name) or "@" in entry["url"] or not isinstance(entry["sha256"],str) or not HEX64.fullmatch(entry["sha256"]): raise ValueError("lock entry is invalid: "+name)
    return value
def discover(root: Path, *, allowlist: Set[str], checksums: Mapping[str,str]) -> Dict[str, Any]:
    errors: List[str]=[]
    if not root.is_dir(): return {"accepted":False,"offline":True,"errors":["validator cache directory is missing"],"paths":{}}
    unexpected=sorted(path.name for path in root.glob("*.py") if path.name not in allowlist)
    if unexpected: errors.append("unapproved validator files present")
    paths={}
    for name in sorted(allowlist):
        path=root/name
        if not path.is_file(): errors.append("locked validator is missing: "+name)
        elif not isinstance(checksums.get(name),str) or not HEX64.fullmatch(checksums[name]) or sha256(path)!=checksums[name]: errors.append("checksum mismatch for locked validator: "+name)
        else: paths[name]=str(path)
    return {"accepted":not errors,"offline":True,"errors":errors,"paths":paths}
def ensure_cache(lock: Mapping[str,Any], cache: Path, *, allow_download: bool) -> Dict[str,Any]:
    checksums={name:entry["sha256"] for name,entry in lock["validators"].items()}; result=discover(cache,allowlist=set(checksums),checksums=checksums)
    if result["accepted"] or not allow_download: return result
    cache.mkdir(parents=True,exist_ok=True)
    for name,entry in lock["validators"].items():
        target=cache/name
        if target.is_file() and sha256(target)==entry["sha256"]: continue
        try:
            with urllib.request.urlopen(entry["url"],timeout=20) as response: content=response.read()
        except OSError: return {"accepted":False,"offline":False,"errors":["download failed for locked validator: "+name],"paths":{}}
        if hashlib.sha256(content).hexdigest()!=entry["sha256"]: return {"accepted":False,"offline":False,"errors":["checksum mismatch for downloaded validator: "+name],"paths":{}}
        temporary=target.with_suffix(".tmp"); temporary.write_bytes(content); temporary.replace(target)
    return discover(cache,allowlist=set(checksums),checksums=checksums)
def discover_targets(repository: Path) -> Dict[str,List[Path]]:
    return {"plugins":sorted(path.parent.parent for path in repository.glob("plugins/*/.codex-plugin/plugin.json")),"skills":sorted(path.parent for path in repository.glob("plugins/*/skills/*/SKILL.md"))}
def run_validators(cache: Path, repository: Path) -> List[str]:
    failures=[]; found=discover_targets(repository)
    for label,script,items in (("skill","quick_validate.py",found["skills"]),("plugin","validate_plugin.py",found["plugins"])):
        for item in items:
            try: result=subprocess.run([sys.executable,"-B",str(cache/script),str(item)],cwd=str(repository),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=30,check=False)
            except (OSError,subprocess.TimeoutExpired): failures.append(label+" validator execution failed: "+str(item.relative_to(repository))); continue
            if result.returncode:
                diagnostic=" ".join(str(result.stdout or "").split())[:240]
                failures.append(label+" validator failed: "+str(item.relative_to(repository))+("; validator diagnostic: "+diagnostic if diagnostic else ""))
    return failures
def main(argv: Optional[Sequence[str]]=None) -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--lock",type=Path,default=DEFAULT_LOCK); parser.add_argument("--cache",type=Path,default=DEFAULT_CACHE); parser.add_argument("--repository",type=Path,default=ROOT); parser.add_argument("--allow-download",action="store_true"); parser.add_argument("--offline",action="store_true")
    args=parser.parse_args(argv)
    try: lock=load_lock(args.lock.resolve())
    except (OSError,ValueError,json.JSONDecodeError) as error: print("ERROR: invalid official-validator lock: "+str(error),file=sys.stderr); return 2
    result=ensure_cache(lock,args.cache.resolve(),allow_download=args.allow_download and not args.offline)
    if not result["accepted"]:
        for error in result["errors"]: print("ERROR: "+error,file=sys.stderr)
        return 1
    failures=run_validators(args.cache.resolve(),args.repository.resolve())
    if failures:
        for failure in failures: print("ERROR: "+failure,file=sys.stderr)
        return 1
    found=discover_targets(args.repository.resolve()); print("Validated "+str(len(found["skills"]))+" skill(s) and "+str(len(found["plugins"]))+" plugin(s) with pinned official validators."); return 0
if __name__=="__main__": raise SystemExit(main())
