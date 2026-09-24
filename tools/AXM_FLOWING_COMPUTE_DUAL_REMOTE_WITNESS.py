#!/usr/bin/env python3
"""AXM Flowing Compute Wave 98: content-addressed authority boundary + dual remote-witness protocol model.

Additive experiment. The two remote witnesses are separate modeled state/credential domains in one
process, not physically independent services, distributed consensus, production cryptography, or a
compute/energy claim.
"""
from __future__ import annotations
import argparse, hashlib, hmac, json, secrets, statistics, time
from copy import deepcopy

ROOTS=("truth","agency_non_domination","continuity","wisdom_before_speed")
LOCAL_WITNESSES=("witness-a","witness-b","witness-c")
REMOTE_IDS=("remote-a","remote-b")
SRC={
 "wave97_head":"20e82977205040168c5fa79b967ee6868aa3f7db",
 "wave97_tool_blob":"f5ca09a21e64ec390c15e5825751d0d6977d023d",
 "wave97_report_blob":"9e5fcdba8c6dbac9916c2fefd2c05f78e34ed31b",
 "verifier_pr":22,
 "verifier_head":"84cbc21db30540e9cdd2e8973a68573aebd317b3",
 "verifier_evidence_blob":"2cb814b195a8c53833b169871db1dab606b66c02",
}

def E(x): return json.dumps(x,sort_keys=True,separators=(",",":")).encode()
def D(x): return hashlib.sha256(E(x)).hexdigest()
def H(x): return hashlib.sha256(x).hexdigest()
def seal(x,field):
 y=deepcopy(x); y.pop(field,None); y[field]=D(y); return y
def chk(x,field):
 y=deepcopy(x); got=y.pop(field,None)
 if got!=D(y): raise ValueError(field+" mismatch")
def put(store,x,field):
 chk(x,field); key=x[field]
 if key in store and store[key]!=x: raise ValueError("collision")
 store[key]=deepcopy(x); return key
def get(store,key,field):
 if key not in store: raise ValueError(field+" body missing")
 x=deepcopy(store[key]); chk(x,field)
 if x.get(field)!=key: raise ValueError(field+" key/body mismatch")
 return x
def fail(fn,text=""):
 try: fn()
 except Exception as e: return (not text) or text in str(e)
 return False

def bits(x): return [(q>>b)&1 for q in hashlib.sha256(E(x)).digest() for b in range(7,-1,-1)]
def pre(seed,root,generation,i,b):
 return hmac.new(seed,f"axm-w98|{root}|{generation}|{i}|{b}".encode(),hashlib.sha256).digest()
def pair(root,generation,predecessor=None):
 seed=secrets.token_bytes(32)
 hashes=[[H(pre(seed,root,generation,i,b)) for b in (0,1)] for i in range(256)]
 pub=seal({"schema":"lamport-pub/w98-v1","root":root,"generation":generation,
           "predecessor_pub_sha":predecessor,"hashes":hashes,
           "algorithm":"Lamport-OTS-SHA256-secret-seed-test-model","pub_sha":""},"pub_sha")
 return pub,{"seed":seed,"reserved":None}
def vpub(p,root=None,generation=None,pred="ANY"):
 chk(p,"pub_sha")
 if p.get("schema")!="lamport-pub/w98-v1" or p.get("algorithm")!="Lamport-OTS-SHA256-secret-seed-test-model": raise ValueError("pub schema/algorithm mismatch")
 if len(p.get("hashes",[]))!=256 or any(len(x)!=2 for x in p["hashes"]): raise ValueError("pub shape mismatch")
 if root is not None and p["root"]!=root: raise ValueError("pub root mismatch")
 if generation is not None and p["generation"]!=generation: raise ValueError("pub generation mismatch")
 if pred!="ANY" and p["predecessor_pub_sha"]!=pred: raise ValueError("pub predecessor mismatch")
 if "seed" in p: raise ValueError("private seed leaked")
def sign(priv,p,x):
 vpub(p); seed=priv.get("seed")
 if not isinstance(seed,(bytes,bytearray)) or len(seed)!=32: raise ValueError("private seed missing")
 out=[]
 for i,b in enumerate(bits(x)):
  q=pre(seed,p["root"],p["generation"],i,b)
  if H(q)!=p["hashes"][i][b]: raise ValueError("private/public mismatch")
  out.append(q.hex())
 return out
def vsig(p,x,sig):
 vpub(p)
 if len(sig)!=256: raise ValueError("signature size mismatch")
 for i,b in enumerate(bits(x)):
  if H(bytes.fromhex(sig[i]))!=p["hashes"][i][b]: raise ValueError("signature mismatch")

def payload(epoch,pred,state,current,next_keys):
 return {"schema":"checkpoint-payload/w98-v1","epoch":epoch,"predecessor_checkpoint_sha":pred,
         "state_sha":state,"signer_keys":current,"next_signer_keys":next_keys,
         "algorithm":"Lamport-OTS-SHA256-secret-seed-test-model"}
def fixture():
 st={k:{} for k in ("P","C","U","L")}; priv={}; boot={}
 for root in ROOTS:
  p,v=pair(root,0); put(st["P"],p,"pub_sha"); priv[p["pub_sha"]]=v; boot[root]=p["pub_sha"]
 rt={"state_sha":hashlib.sha256(b"state-0").hexdigest(),"a":None,"w":{q:None for q in LOCAL_WITNESSES}}
 remotes={}; tokens={}
 for rid in REMOTE_IDS:
  token=secrets.token_bytes(32); tokens[rid]=token
  remotes[rid]={"schema":"modeled-remote-service/w98-v1","service_id":rid,"credential_hash":H(token),
                "online":True,"head":None,"records":{}}
 return st,priv,boot,rt,remotes,tokens

def pred_parts(st,rt):
 if rt["a"] is None: return None,None,None
 l=get(st["L"],rt["a"],"authority_sha")
 return l,get(st["C"],l["checkpoint_sha"],"checkpoint_sha"),get(st["U"],l["use_sha"],"use_sha")
def successors(st,priv,current):
 out={}
 for root in ROOTS:
  p=get(st["P"],current[root],"pub_sha")
  n,v=pair(root,p["generation"]+1,p["pub_sha"]); put(st["P"],n,"pub_sha"); priv[n["pub_sha"]]=v; out[root]=n["pub_sha"]
 return out
def resolve_next(cp,st):
 if set(cp["next_signer_keys"])!=set(ROOTS) or len(set(cp["next_signer_keys"].values()))!=len(ROOTS): raise ValueError("successor set mismatch")
 for root in ROOTS:
  p=get(st["P"],cp["signer_keys"][root],"pub_sha")
  n=get(st["P"],cp["next_signer_keys"][root],"pub_sha")
  vpub(n,root,p["generation"]+1,p["pub_sha"])
def vcp(cp,st,boot,pred=None):
 chk(cp,"checkpoint_sha")
 if cp.get("schema")!="checkpoint/w98-v1" or set(cp["signer_keys"])!=set(ROOTS) or set(cp["signatures"])!=set(ROOTS): raise ValueError("checkpoint shape mismatch")
 if pred is None:
  if cp["epoch"]!=1 or cp["predecessor_checkpoint_sha"] is not None or cp["signer_keys"]!=boot: raise ValueError("bootstrap mismatch")
 else:
  if cp["epoch"]!=pred["epoch"]+1 or cp["predecessor_checkpoint_sha"]!=pred["checkpoint_sha"]: raise ValueError("checkpoint predecessor mismatch")
  if cp["signer_keys"]!=pred["next_signer_keys"]: raise ValueError("signer rotation mismatch")
 for root in ROOTS:
  p=get(st["P"],cp["signer_keys"][root],"pub_sha")
  vpub(p,root,cp["epoch"]-1,None if pred is None else pred["signer_keys"][root])
 resolve_next(cp,st)
 pay=payload(cp["epoch"],cp["predecessor_checkpoint_sha"],cp["state_sha"],cp["signer_keys"],cp["next_signer_keys"])
 for root in ROOTS: vsig(get(st["P"],cp["signer_keys"][root],"pub_sha"),{**pay,"root":root},cp["signatures"][root])
def use(cp,pred):
 return seal({"schema":"signer-use/w98-v1","epoch":cp["epoch"],"checkpoint_sha":cp["checkpoint_sha"],
              "signer_keys":cp["signer_keys"],"predecessor_use_sha":pred,"use_sha":""},"use_sha")
def vuse(u,cp,st,pred=None):
 chk(u,"use_sha"); expected=None if pred is None else pred["use_sha"]
 if u["epoch"]!=cp["epoch"] or u["checkpoint_sha"]!=cp["checkpoint_sha"] or u["signer_keys"]!=cp["signer_keys"] or u["predecessor_use_sha"]!=expected: raise ValueError("use binding mismatch")
 seen=set(); cur=expected; epoch=cp["epoch"]-1
 while cur:
  q=get(st["U"],cur,"use_sha")
  if q["epoch"]!=epoch: raise ValueError("use chain discontinuity")
  seen.update(q["signer_keys"].values()); cur=q["predecessor_use_sha"]; epoch-=1
 if seen.intersection(u["signer_keys"].values()): raise ValueError("signer already consumed")
def link(cp,u,pred):
 return seal({"schema":"authority-link/w98-v1","epoch":cp["epoch"],"checkpoint_sha":cp["checkpoint_sha"],
              "use_sha":u["use_sha"],"predecessor_authority_sha":pred,"authority_sha":""},"authority_sha")
def resolve(st,authority_sha,boot):
 l=get(st["L"],authority_sha,"authority_sha"); pl=pc=pu=None
 if l["predecessor_authority_sha"]:
  pl=get(st["L"],l["predecessor_authority_sha"],"authority_sha")
  pc=get(st["C"],pl["checkpoint_sha"],"checkpoint_sha"); pu=get(st["U"],pl["use_sha"],"use_sha")
  if l["epoch"]!=pl["epoch"]+1: raise ValueError("authority epoch mismatch")
 elif l["epoch"]!=1: raise ValueError("authority genesis mismatch")
 cp=get(st["C"],l["checkpoint_sha"],"checkpoint_sha"); u=get(st["U"],l["use_sha"],"use_sha")
 vcp(cp,st,boot,pc); vuse(u,cp,st,pu)
 if cp["epoch"]!=l["epoch"]: raise ValueError("link component mismatch")
 return l,cp,u

def remote_record(service_id,seq,authority_epoch,authority_sha,checkpoint_sha,previous_record_sha):
 return seal({"schema":"axm-remote-anchor/w98-v1","service_id":service_id,"seq":seq,
              "authority_epoch":authority_epoch,"authority_sha":authority_sha,"checkpoint_sha":checkpoint_sha,
              "previous_record_sha":previous_record_sha,"record_sha":""},"record_sha")
def remote_get(service,key):
 return get(service["records"],key,"record_sha")
def verify_remote_chain(service):
 if service.get("schema")!="modeled-remote-service/w98-v1" or service.get("service_id") not in REMOTE_IDS: raise ValueError("remote service identity mismatch")
 cur=service["head"]; expected_seq=None; seen=set()
 if cur is None: return None
 while cur:
  if cur in seen: raise ValueError("remote cycle")
  seen.add(cur); rec=remote_get(service,cur)
  if rec["schema"]!="axm-remote-anchor/w98-v1" or rec["service_id"]!=service["service_id"]: raise ValueError("remote record identity mismatch")
  if expected_seq is None: expected_seq=rec["seq"]
  if rec["seq"]!=expected_seq or rec["seq"]<1: raise ValueError("remote sequence discontinuity")
  cur=rec["previous_record_sha"]; expected_seq-=1
 if expected_seq!=0: raise ValueError("remote genesis discontinuity")
 return remote_get(service,service["head"])
def remote_append_raw(service,token,authority_epoch,authority_sha,checkpoint_sha):
 if not service["online"]: return "UNAVAILABLE"
 if H(token)!=service["credential_hash"]: return "AUTH_FAIL"
 prev=verify_remote_chain(service); prev_sha=None if prev is None else prev["record_sha"]
 if prev and prev["authority_sha"]==authority_sha and prev["checkpoint_sha"]==checkpoint_sha and prev["authority_epoch"]==authority_epoch: return "ALREADY_CURRENT"
 seq=1 if prev is None else prev["seq"]+1
 rec=remote_record(service["service_id"],seq,authority_epoch,authority_sha,checkpoint_sha,prev_sha)
 put(service["records"],rec,"record_sha"); service["head"]=rec["record_sha"]; return "APPENDED"

def local_status(rt,st,boot):
 try:
  if set(rt["w"])!=set(LOCAL_WITNESSES): return ("HOLD_WITNESS_SET",None,None)
  if rt["a"] is None:
   if any(rt["w"].values()): return ("HOLD_PARTIAL",None,None)
   return ("GENESIS",None,None)
  if any(rt["w"][q]!=rt["a"] for q in LOCAL_WITNESSES): return ("HOLD_PARTIAL",None,None)
  l,cp,_=resolve(st,rt["a"],boot); return ("LOCAL_OK",l,cp)
 except Exception: return ("HOLD",None,None)
def authority(rt,st,boot,remotes):
 status,l,cp=local_status(rt,st,boot)
 if status=="GENESIS":
  try:
   if any(verify_remote_chain(remotes[r]) is not None for r in REMOTE_IDS): return "HOLD_REMOTE_AHEAD"
   return "AUTHORITATIVE_FULL"
  except Exception: return "HOLD_REMOTE_CORRUPT"
 if status!="LOCAL_OK": return status
 heads=[]
 if any(not remotes[rid]["online"] for rid in REMOTE_IDS): return "HOLD_REMOTE_UNAVAILABLE"
 for rid in REMOTE_IDS:
  svc=remotes[rid]
  try: head=verify_remote_chain(svc)
  except Exception: return "HOLD_REMOTE_CORRUPT"
  if head is None: return "HOLD_REMOTE_MISSING"
  if head["authority_epoch"]!=l["epoch"] or head["authority_sha"]!=l["authority_sha"] or head["checkpoint_sha"]!=cp["checkpoint_sha"]: return "HOLD_REMOTE_DIVERGED"
  heads.append((head["authority_epoch"],head["authority_sha"],head["checkpoint_sha"]))
 if len(set(heads))!=1: return "HOLD_REMOTE_DIVERGED"
 return "AUTHORITATIVE_DUAL_REMOTE_MODELED"

def prep_cp(rt,st,priv,boot,remotes):
 if not authority(rt,st,boot,remotes).startswith("AUTHORITATIVE"): raise ValueError("predecessor HOLD")
 pl,pc,pu=pred_parts(st,rt); epoch=1 if pc is None else pc["epoch"]+1
 current=deepcopy(boot if pc is None else pc["next_signer_keys"])
 for root in ROOTS:
  if current[root] not in priv or priv[current[root]].get("reserved") is not None: raise ValueError("signer unavailable/reserved")
 nxt=successors(st,priv,current); pay=payload(epoch,None if pc is None else pc["checkpoint_sha"],rt["state_sha"],current,nxt)
 sig={root:sign(priv[current[root]],get(st["P"],current[root],"pub_sha"),{**pay,"root":root}) for root in ROOTS}
 cp=seal({"schema":"checkpoint/w98-v1","epoch":epoch,"predecessor_checkpoint_sha":None if pc is None else pc["checkpoint_sha"],
          "state_sha":rt["state_sha"],"signer_keys":current,"next_signer_keys":nxt,"signatures":sig,"checkpoint_sha":""},"checkpoint_sha")
 put(st["C"],cp,"checkpoint_sha")
 for root in ROOTS: priv[current[root]]["reserved"]=cp["checkpoint_sha"]
 u=use(cp,None if pu is None else pu["use_sha"]); put(st["U"],u,"use_sha")
 l=link(cp,u,None if pl is None else pl["authority_sha"]); put(st["L"],l,"authority_sha")
 resolve(st,l["authority_sha"],boot); return cp,u,l

def commit_sha(rt,st,boot,authority_sha,n=None):
 if not isinstance(authority_sha,str) or len(authority_sha)!=64: return "INVALID_AUTHORITY_ID"
 try: l=get(st["L"],authority_sha,"authority_sha")
 except Exception: return "VALIDATION_HOLD"
 if l["predecessor_authority_sha"]!=rt["a"]: return "PREDECESSOR_HOLD"
 try: resolve(st,authority_sha,boot)
 except Exception: return "VALIDATION_HOLD"
 if any(rt["w"][q] not in (rt["a"],authority_sha) for q in LOCAL_WITNESSES): return "COMPETING_HOLD"
 lag=[q for q in LOCAL_WITNESSES if rt["w"][q]==rt["a"]]; n=len(lag) if n is None else min(max(n,0),len(lag))
 for q in lag[:n]: rt["w"][q]=authority_sha
 if any(rt["w"][q]!=authority_sha for q in LOCAL_WITNESSES): return "PARTIAL"
 rt["a"]=authority_sha; return "COMMITTED"

def publish_remote(rt,st,boot,service,token):
 status,l,cp=local_status(rt,st,boot)
 if status!="LOCAL_OK": return "LOCAL_HOLD"
 try: prev=verify_remote_chain(service)
 except Exception: return "REMOTE_CORRUPT"
 if prev is not None:
  if prev["authority_sha"]==l["authority_sha"] and prev["checkpoint_sha"]==cp["checkpoint_sha"] and prev["authority_epoch"]==l["epoch"]: return "ALREADY_CURRENT"
  expected_pred=l["predecessor_authority_sha"]
  if prev["authority_sha"]!=expected_pred: return "REMOTE_PREDECESSOR_HOLD"
 return remote_append_raw(service,token,l["epoch"],l["authority_sha"],cp["checkpoint_sha"])

def stolen_all_dual_counterexample():
 st,priv,boot,rt,remotes,tokens=fixture(); stolen={r:bytes(priv[boot[r]]["seed"]) for r in ROOTS}
 nxt=successors(st,priv,boot); pay=payload(1,None,rt["state_sha"],boot,nxt)
 sig={r:sign({"seed":stolen[r]},get(st["P"],boot[r],"pub_sha"),{**pay,"root":r}) for r in ROOTS}
 cp=seal({"schema":"checkpoint/w98-v1","epoch":1,"predecessor_checkpoint_sha":None,"state_sha":rt["state_sha"],
          "signer_keys":boot,"next_signer_keys":nxt,"signatures":sig,"checkpoint_sha":""},"checkpoint_sha"); put(st["C"],cp,"checkpoint_sha")
 u=use(cp,None); put(st["U"],u,"use_sha"); l=link(cp,u,None); put(st["L"],l,"authority_sha")
 if commit_sha(rt,st,boot,l["authority_sha"])!="COMMITTED": return False
 for rid in REMOTE_IDS:
  if publish_remote(rt,st,boot,remotes[rid],tokens[rid])!="APPENDED": return False
 return authority(rt,st,boot,remotes).startswith("AUTHORITATIVE")

def build_depth(depth):
 st,priv,boot,rt,remotes,tokens=fixture(); snapshots=[]
 for i in range(depth):
  cp,u,l=prep_cp(rt,st,priv,boot,remotes)
  if commit_sha(rt,st,boot,l["authority_sha"])!="COMMITTED": raise RuntimeError("depth commit")
  for rid in REMOTE_IDS:
   if publish_remote(rt,st,boot,remotes[rid],tokens[rid]) not in ("APPENDED","ALREADY_CURRENT"): raise RuntimeError("depth remote publish")
  if not authority(rt,st,boot,remotes).startswith("AUTHORITATIVE"): raise RuntimeError("depth authority")
  snapshots.append((deepcopy(rt),deepcopy(remotes)))
  rt["state_sha"]=hashlib.sha256(f"state-{i+1}".encode()).hexdigest()
 return st,priv,boot,rt,remotes,tokens,snapshots

def bench(depths=(1,4,8),rounds=5):
 out=[]
 for depth in depths:
  st,priv,boot,rt,remotes,tokens,_=build_depth(depth)
  xs=[]
  for _ in range(rounds):
   t=time.process_time_ns(); verdict=authority(rt,st,boot,remotes); xs.append(time.process_time_ns()-t)
   if not verdict.startswith("AUTHORITATIVE"): raise RuntimeError("benchmark authority")
  out.append({"depth":depth,"rounds":rounds,"authority_median_cpu_us":statistics.median(xs)/1000})
 return out

def run(rounds):
 controls=[]; add=lambda name,val: controls.append({"name":name,"pass":bool(val)})
 add("exact_sources",SRC["wave97_head"].startswith("20e82977") and SRC["wave97_tool_blob"]=="f5ca09a21e64ec390c15e5825751d0d6977d023d" and SRC["verifier_head"].startswith("84cbc21d"))
 st,priv,boot,rt,remotes,tokens=fixture()
 add("distinct_remote_credentials",remotes["remote-a"]["credential_hash"]!=remotes["remote-b"]["credential_hash"])
 add("genesis_authority",authority(rt,st,boot,remotes)=="AUTHORITATIVE_FULL")
 cp1,u1,l1=prep_cp(rt,st,priv,boot,remotes); add("candidate1_valid",resolve(st,l1["authority_sha"],boot)[0]==l1)
 spoof=deepcopy(l1); spoof["predecessor_authority_sha"]="f"*64
 add("unsealed_wrapper_rejected",commit_sha(rt,st,boot,spoof)=="INVALID_AUTHORITY_ID")
 add("partial_local_commit",commit_sha(rt,st,boot,l1["authority_sha"],1)=="PARTIAL")
 add("partial_local_holds",authority(rt,st,boot,remotes)=="HOLD_PARTIAL")
 add("cp1_commit",commit_sha(rt,st,boot,l1["authority_sha"])=="COMMITTED")
 add("remote_required",authority(rt,st,boot,remotes)=="HOLD_REMOTE_MISSING")
 add("remote_a_publish",publish_remote(rt,st,boot,remotes["remote-a"],tokens["remote-a"])=="APPENDED")
 add("partial_remote_holds",authority(rt,st,boot,remotes)=="HOLD_REMOTE_MISSING")
 add("remote_b_publish",publish_remote(rt,st,boot,remotes["remote-b"],tokens["remote-b"])=="APPENDED")
 add("cp1_authority",authority(rt,st,boot,remotes).startswith("AUTHORITATIVE"))
 tampered=deepcopy(remotes); head=tampered["remote-a"]["head"]; tampered["remote-a"]["records"][head]["seq"]=999
 add("tampered_remote_record_rejected",authority(rt,st,boot,tampered)=="HOLD_REMOTE_CORRUPT")
 rt1=deepcopy(rt); rem1=deepcopy(remotes)
 rt["state_sha"]=hashlib.sha256(b"state-1").hexdigest(); cp2,u2,l2=prep_cp(rt,st,priv,boot,remotes)
 add("cp2_commit",commit_sha(rt,st,boot,l2["authority_sha"])=="COMMITTED")
 remotes["remote-b"]["online"]=False
 add("one_remote_unavailable_holds",authority(rt,st,boot,remotes)=="HOLD_REMOTE_UNAVAILABLE")
 add("publish_a_during_b_outage",publish_remote(rt,st,boot,remotes["remote-a"],tokens["remote-a"])=="APPENDED")
 add("publish_b_offline_refused",publish_remote(rt,st,boot,remotes["remote-b"],tokens["remote-b"])=="UNAVAILABLE")
 remotes["remote-b"]["online"]=True
 add("reconnect_before_catchup_holds",authority(rt,st,boot,remotes)=="HOLD_REMOTE_DIVERGED")
 add("reconnect_catchup",publish_remote(rt,st,boot,remotes["remote-b"],tokens["remote-b"])=="APPENDED")
 add("cp2_authority",authority(rt,st,boot,remotes).startswith("AUTHORITATIVE"))
 rolled=deepcopy(rt1)
 add("dual_remote_detects_local_rollback",authority(rolled,st,boot,remotes)=="HOLD_REMOTE_DIVERGED")
 stale_remote=deepcopy(remotes); stale_remote["remote-a"]["head"]=rem1["remote-a"]["head"]
 add("valid_old_remote_head_replay_holds",authority(rt,st,boot,stale_remote)=="HOLD_REMOTE_DIVERGED")
 forked=deepcopy(remotes)
 fake="e"*64
 r=remote_append_raw(forked["remote-a"],tokens["remote-a"],3,fake,"d"*64)
 add("single_remote_credential_compromise_can_poison",r=="APPENDED")
 add("single_remote_poison_no_false_authority",authority(rt,st,boot,forked)=="HOLD_REMOTE_DIVERGED")
 wrong_token=secrets.token_bytes(32)
 add("wrong_remote_credential_rejected",remote_append_raw(remotes["remote-a"],wrong_token,3,fake,"d"*64)=="AUTH_FAIL")
 both_poison=deepcopy(remotes)
 for rid in REMOTE_IDS: remote_append_raw(both_poison[rid],tokens[rid],3,fake,"d"*64)
 add("both_remote_credentials_can_force_hold_not_false_authority",authority(rt,st,boot,both_poison)=="HOLD_REMOTE_DIVERGED")
 add("all_current_signer_and_remote_credential_compromise_counterexample",stolen_all_dual_counterexample())
 add("whole_domain_rollback_counterexample",authority(rt1,st,boot,rem1).startswith("AUTHORITATIVE"))
 passed=sum(x["pass"] for x in controls)
 return {
  "schema":"axm.flowing_compute.wave98.report/v1","wave":98,"source":SRC,
  "controls":{"passed":passed,"total":len(controls),"rows":controls},
  "synthetic_scaling":{"label":"SYNTHETIC single-process dual-remote protocol + retained authority-chain verification; not network latency, physical failure-domain, monolith compute-efficiency, energy, or distributed-consensus evidence","rows":bench((1,4,8),rounds)},
  "counterexamples_preserved":[
   "The two remote witnesses are separate modeled state/credential domains in one Python process, not physically independent services/devices.",
   "With only two required witnesses, strict resistance to one arbitrary compromised witness sacrifices availability when either witness is unavailable; this model HOLDs rather than guessing.",
   "A compromised remote append credential can poison that witness's monotonic head and cause denial of authority until an explicit recovery/credential-rotation protocol exists.",
   "Compromise of all four current checkpoint signer seeds plus both remote append credentials before first publication can still mint and publish a competing valid world.",
   "Rolling local state and both modeled remote service states back together remains internally self-consistent.",
   "Lamport OTS remains a test model and valid signatures/remote records do not prove evaluator legitimacy, consent, root correctness, or canonical AXM authority."
  ],
  "truth_boundary":[
   "Wave 98 first repairs verifier PR #22: local commit accepts only a content-addressed authority SHA and resolves all gating fields from the stored sealed object; remote authority validates each remote record seal and full previous-record chain.",
   "No fresh AXM/monolith workload is read because the newest verifier exposed authority-boundary failures that had to be repaired before stronger remote claims.",
   "Remote services here are protocol simulations with separate credentials, not real independent machines/providers or authenticated network APIs.",
   "No retained, incremental, dormant, energy, joule, network-latency, or compute-efficiency win is claimed.",
   "No merge, CANON promotion, or silent rewrite is implied."
  ],
  "next_gate":"Deploy this exact monotonic record contract against at least two genuinely independent failure domains with separate credentials, then measure real partition/reconnect behavior. Add explicit poisoned-witness recovery and credential rotation. If availability with one witness down is required while one witness may also be Byzantine, move to a third independent witness and define a bounded quorum instead of weakening HOLD semantics."
 }

def main():
 p=argparse.ArgumentParser(); p.add_argument("--benchmark-rounds",type=int,default=5); p.add_argument("--report"); a=p.parse_args()
 r=run(a.benchmark_rounds); s=json.dumps(r,indent=2,sort_keys=True); print(s)
 if a.report: open(a.report,"w",encoding="utf-8").write(s+"\n")
 raise SystemExit(0 if r["controls"]["passed"]==r["controls"]["total"] else 1)
if __name__=="__main__": main()
