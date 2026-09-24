#!/usr/bin/env python3
"""AXM Flowing Compute Wave 97: secret-seeded checkpoint signer lineage.
Additive experiment; not distributed consensus, remote attestation, or a compute/energy claim.
"""
from __future__ import annotations
import argparse,hashlib,hmac,json,secrets,statistics,time
from copy import deepcopy
R=("truth","agency_non_domination","continuity","wisdom_before_speed"); W=("witness-a","witness-b","witness-c")
SRC={"wave96_head":"f9599f45f8fc3d4f028157eab28b89e3b7962395","wave96_tool_blob":"ab7a57af1f5259e893aaa14c6f17f40a064cc801","wave96_report_blob":"f55152574d076a56a710a9f4f3bcae0295ddeb0c","verifier_pr":21,"verifier_head":"2933d68ab47577aa4afd52392ba10d832c1d7e11","verifier_evidence_blob":"ea58ded87d0d91471898054e8772438ee100d1fc"}
def E(x):return json.dumps(x,sort_keys=True,separators=(",",":")).encode()
def D(x):return hashlib.sha256(E(x)).hexdigest()
def H(x):return hashlib.sha256(x).hexdigest()
def seal(x,f):y=deepcopy(x);y.pop(f,None);y[f]=D(y);return y
def chk(x,f):
 y=deepcopy(x);g=y.pop(f,None)
 if g!=D(y):raise ValueError(f+" mismatch")
def put(s,x,f):
 chk(x,f);k=x[f]
 if k in s and s[k]!=x:raise ValueError("collision")
 s[k]=deepcopy(x);return k
def get(s,k,f):
 if k not in s:raise ValueError(f+" body missing")
 x=deepcopy(s[k]);chk(x,f)
 if x.get(f)!=k:raise ValueError(f+" key/body mismatch")
 return x
def fail(fn,text=""):
 try:fn()
 except Exception as e:return not text or text in str(e)
 return False
def bits(x):return [(q>>b)&1 for q in hashlib.sha256(E(x)).digest() for b in range(7,-1,-1)]
def pre(seed,r,g,i,b):return hmac.new(seed,f"axm-w97|{r}|{g}|{i}|{b}".encode(),hashlib.sha256).digest()
def pair(r,g,p=None):
 seed=secrets.token_bytes(32); hs=[[H(pre(seed,r,g,i,b)) for b in (0,1)] for i in range(256)]
 pub=seal({"schema":"lamport-pub/v2","root":r,"generation":g,"predecessor_pub_sha":p,"hashes":hs,"algorithm":"Lamport-OTS-SHA256-secret-seed-test-model","pub_sha":""},"pub_sha")
 return pub,{"seed":seed,"reserved":None}
def vpub(p,r=None,g=None,pred="ANY"):
 chk(p,"pub_sha")
 if p.get("schema")!="lamport-pub/v2" or p.get("algorithm")!="Lamport-OTS-SHA256-secret-seed-test-model":raise ValueError("pub schema/algorithm mismatch")
 if len(p.get("hashes",[]))!=256 or any(len(x)!=2 for x in p["hashes"]):raise ValueError("pub shape mismatch")
 if r is not None and p["root"]!=r:raise ValueError("pub root mismatch")
 if g is not None and p["generation"]!=g:raise ValueError("pub generation mismatch")
 if pred!="ANY" and p["predecessor_pub_sha"]!=pred:raise ValueError("pub predecessor mismatch")
 if "seed" in p:raise ValueError("private seed leaked")
def sign(priv,p,x):
 vpub(p); seed=priv.get("seed")
 if not isinstance(seed,(bytes,bytearray)) or len(seed)!=32:raise ValueError("private seed missing")
 out=[]
 for i,b in enumerate(bits(x)):
  q=pre(seed,p["root"],p["generation"],i,b)
  if H(q)!=p["hashes"][i][b]:raise ValueError("private/public mismatch")
  out.append(q.hex())
 return out
def vsig(p,x,sig):
 vpub(p)
 if len(sig)!=256:raise ValueError("signature size mismatch")
 for i,b in enumerate(bits(x)):
  if H(bytes.fromhex(sig[i]))!=p["hashes"][i][b]:raise ValueError("signature mismatch")
def legacy_sig(p,x):
 return [hashlib.sha256(f"w96|{p['root']}|{p['generation']}|{i}|{b}".encode()).digest().hex() for i,b in enumerate(bits(x))]
def payload(ep,pred,state,cur,nxt):return {"schema":"checkpoint-payload/v2","epoch":ep,"predecessor_checkpoint_sha":pred,"state_sha":state,"signer_keys":cur,"next_signer_keys":nxt,"algorithm":"Lamport-OTS-SHA256-secret-seed-test-model"}
def fixture():
 st={k:{} for k in ("P","C","U","L")}; priv={}; boot={}
 for r in R:
  p,v=pair(r,0);put(st["P"],p,"pub_sha");priv[p["pub_sha"]]=v;boot[r]=p["pub_sha"]
 rt={"state_sha":hashlib.sha256(b"state-0").hexdigest(),"a":None,"w":{q:None for q in W}};return st,priv,boot,rt,[]
def pred_parts(st,rt):
 if rt["a"] is None:return None,None,None
 l=get(st["L"],rt["a"],"authority_sha");return l,get(st["C"],l["checkpoint_sha"],"checkpoint_sha"),get(st["U"],l["use_sha"],"use_sha")
def successors(st,priv,cur):
 out={}
 for r in R:
  p=get(st["P"],cur[r],"pub_sha");n,v=pair(r,p["generation"]+1,p["pub_sha"]);put(st["P"],n,"pub_sha");priv[n["pub_sha"]]=v;out[r]=n["pub_sha"]
 return out
def resolve_next(cp,st):
 if set(cp["next_signer_keys"])!=set(R) or len(set(cp["next_signer_keys"].values()))!=4:raise ValueError("successor set mismatch")
 for r in R:
  p=get(st["P"],cp["signer_keys"][r],"pub_sha");n=get(st["P"],cp["next_signer_keys"][r],"pub_sha");vpub(n,r,p["generation"]+1,p["pub_sha"])
def vcp(cp,st,boot,pred=None):
 chk(cp,"checkpoint_sha")
 if cp.get("schema")!="checkpoint/v2" or set(cp["signer_keys"])!=set(R) or set(cp["signatures"])!=set(R):raise ValueError("checkpoint shape mismatch")
 if pred is None:
  if cp["epoch"]!=1 or cp["predecessor_checkpoint_sha"] is not None or cp["signer_keys"]!=boot:raise ValueError("bootstrap mismatch")
 else:
  if cp["epoch"]!=pred["epoch"]+1 or cp["predecessor_checkpoint_sha"]!=pred["checkpoint_sha"]:raise ValueError("checkpoint predecessor mismatch")
  if cp["signer_keys"]!=pred["next_signer_keys"]:raise ValueError("signer rotation mismatch")
 for r in R:
  p=get(st["P"],cp["signer_keys"][r],"pub_sha");vpub(p,r,cp["epoch"]-1,None if pred is None else pred["signer_keys"][r])
 resolve_next(cp,st);pay=payload(cp["epoch"],cp["predecessor_checkpoint_sha"],cp["state_sha"],cp["signer_keys"],cp["next_signer_keys"])
 for r in R:vsig(get(st["P"],cp["signer_keys"][r],"pub_sha"),{**pay,"root":r},cp["signatures"][r])
def use(cp,pred):return seal({"schema":"signer-use/v1","epoch":cp["epoch"],"checkpoint_sha":cp["checkpoint_sha"],"signer_keys":cp["signer_keys"],"predecessor_use_sha":pred,"use_sha":""},"use_sha")
def vuse(u,cp,st,pred=None):
 chk(u,"use_sha"); exp=None if pred is None else pred["use_sha"]
 if u["epoch"]!=cp["epoch"] or u["checkpoint_sha"]!=cp["checkpoint_sha"] or u["signer_keys"]!=cp["signer_keys"] or u["predecessor_use_sha"]!=exp:raise ValueError("use binding mismatch")
 seen=set();cur=exp;ee=cp["epoch"]-1
 while cur:
  q=get(st["U"],cur,"use_sha")
  if q["epoch"]!=ee:raise ValueError("use chain discontinuity")
  seen.update(q["signer_keys"].values());cur=q["predecessor_use_sha"];ee-=1
 if seen.intersection(u["signer_keys"].values()):raise ValueError("signer already consumed")
def link(cp,u,pred):return seal({"schema":"authority-link/v1","epoch":cp["epoch"],"checkpoint_sha":cp["checkpoint_sha"],"use_sha":u["use_sha"],"predecessor_authority_sha":pred,"authority_sha":""},"authority_sha")
def resolve(st,a,boot):
 l=get(st["L"],a,"authority_sha");pl=pc=pu=None
 if l["predecessor_authority_sha"]:
  pl=get(st["L"],l["predecessor_authority_sha"],"authority_sha");pc=get(st["C"],pl["checkpoint_sha"],"checkpoint_sha");pu=get(st["U"],pl["use_sha"],"use_sha")
  if l["epoch"]!=pl["epoch"]+1:raise ValueError("authority epoch mismatch")
 elif l["epoch"]!=1:raise ValueError("authority genesis mismatch")
 cp=get(st["C"],l["checkpoint_sha"],"checkpoint_sha");u=get(st["U"],l["use_sha"],"use_sha");vcp(cp,st,boot,pc);vuse(u,cp,st,pu)
 if cp["epoch"]!=l["epoch"]:raise ValueError("link component mismatch")
 return l,cp,u
def auth(rt,st,boot,ext):
 try:
  if set(rt["w"])!=set(W):return "HOLD_WITNESS_SET"
  if rt["a"] is None:
   if any(rt["w"].values()):return "HOLD_PARTIAL"
   if ext:return "HOLD_EXTERNAL_AHEAD" 
   return "AUTHORITATIVE_FULL"
  if any(rt["w"][q]!=rt["a"] for q in W):return "HOLD_PARTIAL"
  l,cp,_=resolve(st,rt["a"],boot)
  if not ext:return "HOLD_EXTERNAL_MISSING"
  if ext[-1]["authority_sha"]!=l["authority_sha"] or ext[-1]["checkpoint_sha"]!=cp["checkpoint_sha"]:return "HOLD_EXTERNAL_AHEAD"
  return "AUTHORITATIVE_SECRET_SIGNER_CHECKPOINTED"
 except Exception:return "HOLD"
def prep_cp(rt,st,priv,boot,ext):
 if not auth(rt,st,boot,ext).startswith("AUTHORITATIVE"):raise ValueError("predecessor HOLD")
 pl,pc,pu=pred_parts(st,rt);ep=1 if pc is None else pc["epoch"]+1;cur=deepcopy(boot if pc is None else pc["next_signer_keys"])
 for r in R:
  if cur[r] not in priv or priv[cur[r]].get("reserved") is not None:raise ValueError("signer unavailable/reserved")
 nxt=successors(st,priv,cur);pay=payload(ep,None if pc is None else pc["checkpoint_sha"],rt["state_sha"],cur,nxt);s={}
 for r in R:s[r]=sign(priv[cur[r]],get(st["P"],cur[r],"pub_sha"),{**pay,"root":r})
 cp=seal({"schema":"checkpoint/v2","epoch":ep,"predecessor_checkpoint_sha":None if pc is None else pc["checkpoint_sha"],"state_sha":rt["state_sha"],"signer_keys":cur,"next_signer_keys":nxt,"signatures":s,"checkpoint_sha":""},"checkpoint_sha");put(st["C"],cp,"checkpoint_sha")
 for r in R:priv[cur[r]]["reserved"]=cp["checkpoint_sha"]
 u=use(cp,None if pu is None else pu["use_sha"]);put(st["U"],u,"use_sha");l=link(cp,u,None if pl is None else pl["authority_sha"]);put(st["L"],l,"authority_sha");resolve(st,l["authority_sha"],boot);return cp,u,l
def commit(rt,st,boot,l,n=None):
 if l["predecessor_authority_sha"]!=rt["a"]:return "PREDECESSOR_HOLD"
 try:resolve(st,l["authority_sha"],boot)
 except Exception:return "VALIDATION_HOLD"
 if any(rt["w"][q] not in (rt["a"],l["authority_sha"]) for q in W):return "COMPETING_HOLD"
 lag=[q for q in W if rt["w"][q]==rt["a"]];n=len(lag) if n is None else min(max(n,0),len(lag))
 for q in lag[:n]:rt["w"][q]=l["authority_sha"]
 if any(rt["w"][q]!=l["authority_sha"] for q in W):return "PARTIAL"
 rt["a"]=l["authority_sha"];return "COMMITTED"
def pubext(rt,st,boot,ext):
 if rt["a"] is None or any(rt["w"][q]!=rt["a"] for q in W):return "LOCAL_HOLD"
 l,cp,_=resolve(st,rt["a"],boot);prev=ext[-1] if ext else None
 if l["epoch"]!=(1 if prev is None else prev["epoch"]+1) or l["predecessor_authority_sha"]!=(None if prev is None else prev["authority_sha"]):return "PREDECESSOR_HOLD"
 rec=seal({"schema":"modeled-external-anchor/v2","epoch":l["epoch"],"authority_sha":l["authority_sha"],"checkpoint_sha":cp["checkpoint_sha"],"previous_record_sha":None if prev is None else prev["record_sha"],"record_sha":""},"record_sha");ext.append(rec);return "APPENDED"
def resign(cp,nxt,st,priv):
 pay=payload(cp["epoch"],cp["predecessor_checkpoint_sha"],cp["state_sha"],cp["signer_keys"],nxt);s={r:sign(priv[cp["signer_keys"][r]],get(st["P"],cp["signer_keys"][r],"pub_sha"),{**pay,"root":r}) for r in R}
 return seal({**cp,"next_signer_keys":nxt,"signatures":s,"checkpoint_sha":""},"checkpoint_sha")
def stolen_all_counterexample():
 st,priv,b,rt,ext=fixture(); stolen={r:bytes(priv[b[r]]["seed"]) for r in R};nxt=successors(st,priv,b);pay=payload(1,None,rt["state_sha"],b,nxt);s={r:sign({"seed":stolen[r]},get(st["P"],b[r],"pub_sha"),{**pay,"root":r}) for r in R}
 cp=seal({"schema":"checkpoint/v2","epoch":1,"predecessor_checkpoint_sha":None,"state_sha":rt["state_sha"],"signer_keys":b,"next_signer_keys":nxt,"signatures":s,"checkpoint_sha":""},"checkpoint_sha");put(st["C"],cp,"checkpoint_sha");u=use(cp,None);put(st["U"],u,"use_sha");l=link(cp,u,None);put(st["L"],l,"authority_sha")
 return commit(rt,st,b,l)=="COMMITTED" and pubext(rt,st,b,ext)=="APPENDED" and auth(rt,st,b,ext).startswith("AUTHORITATIVE")
def bench(n):
 a=[];v=[]
 for _ in range(n):
  st,p,b,rt,e=fixture();t=time.process_time_ns();cp,u,l=prep_cp(rt,st,p,b,e);a.append(time.process_time_ns()-t);t=time.process_time_ns();vcp(cp,st,b);vuse(u,cp,st);v.append(time.process_time_ns()-t)
 return {"rounds":n,"prepare_median_cpu_us":statistics.median(a)/1000,"verify_plus_use_median_cpu_us":statistics.median(v)/1000}
def run(n):
 C=[];add=lambda x,y:C.append({"name":x,"pass":bool(y)});add("exact_sources",SRC["wave96_head"].startswith("f9599f45") and SRC["verifier_head"].startswith("2933d68a"));st,p,b,rt,e=fixture();add("genesis_authority",auth(rt,st,b,e)=="AUTHORITATIVE_FULL");add("seed_not_public",all("seed" not in get(st["P"],q,"pub_sha") for q in b.values()));cp1,u1,l1=prep_cp(rt,st,p,b,e);add("candidate_valid",resolve(st,l1["authority_sha"],b)[0]==l1);add("second_prepare_refused",fail(lambda:prep_cp(rt,st,p,b,e),"reserved"));pub=get(st["P"],b["truth"],"pub_sha");pay=payload(1,None,cp1["state_sha"],cp1["signer_keys"],cp1["next_signer_keys"]);add("wave96_public_recipe_attack_blocked",fail(lambda:vsig(pub,{**pay,"root":"truth"},legacy_sig(pub,{**pay,"root":"truth"})),"signature mismatch"));bad=deepcopy(cp1["next_signer_keys"]);bad["truth"]="f"*64;badcp=resign(cp1,bad,st,p);add("missing_successor_rejected",fail(lambda:vcp(badcp,st,b),"body missing"));cur=get(st["P"],b["truth"],"pub_sha");wp,wv=pair("truth",2,cur["pub_sha"]);put(st["P"],wp,"pub_sha");p[wp["pub_sha"]]=wv;bad=deepcopy(cp1["next_signer_keys"]);bad["truth"]=wp["pub_sha"];badcp=resign(cp1,bad,st,p);add("wrong_successor_generation_rejected",fail(lambda:vcp(badcp,st,b),"generation mismatch"));[p.pop(q,None) for q in cp1["signer_keys"].values()];add("verify_after_private_erasure",vcp(cp1,st,b) is None);add("partial_fanout",commit(rt,st,b,l1,1)=="PARTIAL");add("partial_holds",auth(rt,st,b,e)=="HOLD_PARTIAL");add("cp1_commit",commit(rt,st,b,l1)=="COMMITTED");add("external_required",auth(rt,st,b,e)=="HOLD_EXTERNAL_MISSING");add("cp1_external",pubext(rt,st,b,e)=="APPENDED");add("cp1_authority",auth(rt,st,b,e).startswith("AUTHORITATIVE"));rt["state_sha"]=hashlib.sha256(b"state-1").hexdigest();cp2,u2,l2=prep_cp(rt,st,p,b,e);add("rotation_and_predecessor_bound",cp2["signer_keys"]==cp1["next_signer_keys"] and l2["predecessor_authority_sha"]==l1["authority_sha"]);saved=deepcopy(st["U"][u2["use_sha"]]);del st["U"][u2["use_sha"]];add("missing_use_blocks_commit",commit(rt,st,b,l2)=="VALIDATION_HOLD");st["U"][u2["use_sha"]]=saved;[p.pop(q,None) for q in cp2["signer_keys"].values()];add("cp2_commit_after_seed_erasure",commit(rt,st,b,l2)=="COMMITTED");add("cp2_external",pubext(rt,st,b,e)=="APPENDED");add("cp2_authority",auth(rt,st,b,e).startswith("AUTHORITATIVE"));add("old_replay_blocked",commit(rt,st,b,l1)=="PREDECESSOR_HOLD");saved=deepcopy(st["U"][u2["use_sha"]]);del st["U"][u2["use_sha"]];add("committed_use_is_authority_closure",auth(rt,st,b,e)=="HOLD");st["U"][u2["use_sha"]]=saved;rb=deepcopy(rt);rb["a"]=l1["authority_sha"];rb["w"]={q:l1["authority_sha"] for q in W};rb["state_sha"]=cp1["state_sha"];add("external_detects_local_rollback",auth(rb,st,b,e)=="HOLD_EXTERNAL_AHEAD");add("whole_domain_rollback_counterexample",auth(rb,st,b,deepcopy(e[:1])).startswith("AUTHORITATIVE"));add("all_current_seed_compromise_counterexample",stolen_all_counterexample());passed=sum(x["pass"] for x in C)
 return {"schema":"axm.flowing_compute.wave97.report/v1","wave":97,"source":SRC,"controls":{"passed":passed,"total":len(C),"rows":C},"synthetic_benchmark":{"label":"SYNTHETIC single-host signer/checkpoint bookkeeping only; not monolith compute-efficiency, energy, or remote-latency evidence",**bench(n)},"counterexamples_preserved":["Compromise of all four current private signer seeds before authoritative publication can still mint a valid competing checkpoint and win first publication in this model.","Rolling local authority state and the modeled external anchor back together remains internally self-consistent.","The modeled external anchor is not a physically independent device/service and has no separate credential boundary here.","Random signer seeds prove only modeled key possession, not evaluator legitimacy, root correctness, identity, or canonical AXM authority.","Crash-atomic persistence across real devices/filesystems is not proven."],"truth_boundary":["No fresh AXM monolith workload is read; Wave 97 addresses verifier PR #21 authority/cryptographic failures.","No retained, incremental, dormant, energy, joule, or compute-efficiency win is claimed.","Lamport OTS remains a deliberately simple test model, not production-crypto guidance.","No merge, CANON promotion, or silent rewrite is implied."],"next_gate":"Move checkpoint authority/consumption heads into a genuinely independent monotonic failure domain (prefer two independent remote/device witnesses), then attack credential compromise, partition, stale replay, conflicting remote histories, partial publication, and recovery with one external witness unavailable. Preserve the all-current-signer compromise boundary; do not call this distributed consensus."}
def main():
 p=argparse.ArgumentParser();p.add_argument("--benchmark-rounds",type=int,default=5);p.add_argument("--report");a=p.parse_args();r=run(a.benchmark_rounds);s=json.dumps(r,indent=2,sort_keys=True);print(s)
 if a.report:open(a.report,"w",encoding="utf-8").write(s+"\n")
 raise SystemExit(0 if r["controls"]["passed"]==r["controls"]["total"] else 1)
if __name__=="__main__":main()
