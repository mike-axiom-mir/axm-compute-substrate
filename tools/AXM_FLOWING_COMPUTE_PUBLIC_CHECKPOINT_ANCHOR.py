#!/usr/bin/env python3
"""AXM Flowing Compute Wave 96: repeatable public checkpoints + external rollback anchor.
Experimental authority-state model only; not distributed consensus, not an energy/compute-win claim.
"""
from __future__ import annotations
import argparse,hashlib,hmac,json,statistics,time
from copy import deepcopy
R=("truth","agency_non_domination","continuity","wisdom_before_speed"); W=("witness-a","witness-b","witness-c")
SRC={"wave95_head":"42bf7230f2537fe7229983769b9130f9c58c2393","wave95_tool_blob":"5e38d8ad23dc9c659d774127beb95a745b08a151","wave95_evidence_blob":"b202f5724dc340119e656189718ea64f0a9feb71","verifier_pr":20,"verifier_head":"bbe9bbccbc5c9241c4391c609ec36deef99df1fa","verifier_workflow":35139830377}
def E(x):return json.dumps(x,sort_keys=True,separators=(",",":")).encode()
def D(x):return hashlib.sha256(E(x)).hexdigest()
def H(b):return hashlib.sha256(b).hexdigest()
def T(s):return hashlib.sha256(s.encode()).hexdigest()
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
def fail(fn,text):
 try:fn()
 except Exception as e:return text in str(e)
 return False
def mac(k,x):return hmac.new(k,E(x),hashlib.sha256).hexdigest()
def key(r,g,sec,p=None):return seal({"schema":"key/v1","root":r,"generation":g,"predecessor":p,"material":H(sec),"key_sha":""},"key_sha")
def hist(g,reg,p=None):return seal({"schema":"history/v1","generation":g,"registry_sha":reg,"predecessor":p,"history_sha":""},"history_sha")
def state(g,reg,p,heads,f="state_sha",schema="att-state/v1"):return seal({"schema":schema,"generation":g,"registry_sha":reg,"predecessor":p,"heads":deepcopy(heads),f:""},f)
def attest(tr,g,r,seq,prev,ks,sec):
 x={"schema":"att/v1","transition_sha":tr,"registry_generation":g,"root":r,"sequence":seq,"previous":prev,"signer_key_sha":ks,"verdict":"PASS","algorithm":"HMAC-SHA256-test-model","test_only":True};x["mac"]=mac(sec,x);return seal(x,"att_sha")
def aval(a,st):
 chk(a,"att_sha");x=deepcopy(a);x.pop("att_sha");sig=x.pop("mac");k=get(st["K"],a["signer_key_sha"],"key_sha");sec=st["SEC"].get(k["key_sha"])
 if sec is None or H(sec)!=k["material"] or k["root"]!=a["root"] or sig!=mac(sec,x):raise ValueError("attestation MAC mismatch")
def bits(x):return [(q>>b)&1 for q in hashlib.sha256(E(x)).digest() for b in range(7,-1,-1)]
def lpair(r,g,p=None):
 pv=[];ph=[]
 for i in range(256):
  row=[];hr=[]
  for b in (0,1):s=hashlib.sha256(f"w96|{r}|{g}|{i}|{b}".encode()).digest();row.append(s.hex());hr.append(H(s))
  pv.append(row);ph.append(hr)
 pub=seal({"schema":"lamport-pub/v1","root":r,"generation":g,"predecessor_pub_sha":p,"hashes":ph,"algorithm":"Lamport-OTS-SHA256-test-model","pub_sha":""},"pub_sha");return pub,pv
def lsign(pv,x):return [pv[i][b] for i,b in enumerate(bits(x))]
def lverify(pub,x,sig):
 chk(pub,"pub_sha")
 if len(sig)!=256:raise ValueError("lamport signature size mismatch")
 for i,b in enumerate(bits(x)):
  if H(bytes.fromhex(sig[i]))!=pub["hashes"][i][b]:raise ValueError("lamport signature mismatch")
def fixture():
 st={k:{} for k in ("H","S","KS","A","K","SEC","CP","PUB")};kh={};ah={r:{"sequence":0,"att_sha":None} for r in R}
 for r in R:
  sec=hashlib.sha256(f"state|{r}|0".encode()).digest();k=key(r,0,sec);put(st["K"],k,"key_sha");st["SEC"][k["key_sha"]]=sec;kh[r]=k["key_sha"]
 reg=T("registry-0");h=hist(0,reg);s=state(0,reg,None,ah);ks=state(0,reg,None,kh,"key_state_sha","key-state/v1")
 put(st["H"],h,"history_sha");put(st["S"],s,"state_sha");put(st["KS"],ks,"key_state_sha");cur=[h["history_sha"],s["state_sha"],ks["key_state_sha"]]
 return st,{"cur":cur,"w":{w:list(cur) for w in W},"cp":None,"cpe":0,"cw":{w:None for w in W}}
def view(t,st):
 h=get(st["H"],t[0],"history_sha");s=get(st["S"],t[1],"state_sha");ks=get(st["KS"],t[2],"key_state_sha")
 if not(h["generation"]==s["generation"]==ks["generation"]):raise ValueError("tuple generation mismatch")
 if not(h["registry_sha"]==s["registry_sha"]==ks["registry_sha"]):raise ValueError("tuple registry mismatch")
 if set(s["heads"])!=set(R) or set(ks["heads"])!=set(R):raise ValueError("root set mismatch")
 return h,s,ks
def closure(cur,st,cp=None,counter=None):
 if counter is not None:counter[0]+=1
 h,s,ks=view(cur,st);m={k:set() for k in ("history","att_state","key_state","attestations","keys")}
 if cp is None:base=(None,None,None);ast={r:(None,0) for r in R};kst={r:None for r in R}
 else:base=tuple(cp["snapshot"]["tuple"]);view(base,st);ast={r:(cp["snapshot"]["attestation_heads"][r]["att_sha"],cp["snapshot"]["attestation_heads"][r]["sequence"]) for r in R};kst=cp["snapshot"]["key_heads"]
 for head,store,f,n,stop in ((cur[0],st["H"],"history_sha","history",base[0]),(cur[1],st["S"],"state_sha","att_state",base[1]),(cur[2],st["KS"],"key_state_sha","key_state",base[2])):
  exp=None
  while head!=stop:
   o=get(store,head,f)
   if exp is not None and o["generation"]!=exp:raise ValueError(f+" discontinuity")
   m[n].add(head);exp=o["generation"]-1;head=o["predecessor"]
   if head is None and stop is not None:raise ValueError(f+" checkpoint not reached")
  if cp is None and exp!=-1:raise ValueError(f+" genesis missing")
 for r in R:
  head=s["heads"][r]["att_sha"];exp=s["heads"][r]["sequence"];stop,stopseq=ast[r]
  while head!=stop:
   a=get(st["A"],head,"att_sha");aval(a,st)
   if a["root"]!=r or a["sequence"]!=exp:raise ValueError("attestation lineage mismatch")
   m["attestations"].add(head);m["keys"].add(a["signer_key_sha"]);exp-=1;head=a["previous"]
  if exp!=stopseq:raise ValueError("attestation sequence mismatch")
  head=ks["heads"][r];stop=kst[r];exp=None
  while head!=stop:
   k=get(st["K"],head,"key_sha")
   if k["root"]!=r or (exp is not None and k["generation"]!=exp):raise ValueError("key lineage mismatch")
   if cp is None:
    sec=st["SEC"].get(head)
    if sec is None or H(sec)!=k["material"]:raise ValueError("key secret mismatch")
   m["keys"].add(head);exp=k["generation"]-1;head=k["predecessor"]
  if cp is None and exp!=-1:raise ValueError("key genesis missing")
 out={k:sorted(v) for k,v in m.items()};out["counts"]={k:len(v) for k,v in out.items()};out["digest"]=D({k:out[k] for k in m});return out
def boot(st):
 keys={};priv={}
 for r in R:p,v=lpair(r,0);put(st["PUB"],p,"pub_sha");keys[r]=p["pub_sha"];priv[p["pub_sha"]]=v
 return keys,priv
def payload(ep,pred,snap,signers,nextk):return {"schema":"public-checkpoint-payload/v1","epoch":ep,"predecessor_checkpoint_sha":pred,"snapshot":snap,"signer_keys":signers,"next_signer_keys":nextk,"algorithm":"Lamport-OTS-SHA256-test-model"}
def verifycp(cp,st,bootstrap,pred=None):
 chk(cp,"checkpoint_sha")
 if pred is None:
  if cp["epoch"]!=1 or cp["predecessor_checkpoint_sha"] is not None or cp["signer_keys"]!=bootstrap:raise ValueError("checkpoint bootstrap mismatch")
 else:
  if cp["epoch"]!=pred["epoch"]+1:raise ValueError("checkpoint epoch not monotonic")
  if cp["predecessor_checkpoint_sha"]!=pred["checkpoint_sha"]:raise ValueError("checkpoint predecessor mismatch")
  if cp["signer_keys"]!=pred["next_signer_keys"]:raise ValueError("checkpoint signer rotation mismatch")
 p=payload(cp["epoch"],cp["predecessor_checkpoint_sha"],cp["snapshot"],cp["signer_keys"],cp["next_signer_keys"])
 for r in R:lverify(get(st["PUB"],cp["signer_keys"][r],"pub_sha"),{**p,"root":r},cp["signatures"][r])
def auth(rt,st,ext,bootstrap):
 try:
  cur=tuple(rt["cur"])
  if set(rt["w"])!=set(W) or any(tuple(rt["w"][w])!=cur for w in W):return "HOLD_LOCAL_TUPLE"
  if rt["cp"] is None:
   if any(v is not None for v in rt["cw"].values()):return "HOLD_LOCAL_CHECKPOINT"
   if ext:return "HOLD_EXTERNAL_AHEAD"
   closure(cur,st);return "AUTHORITATIVE_FULL"
  if any(rt["cw"][w]!=rt["cp"] for w in W):return "HOLD_LOCAL_CHECKPOINT"
  cp=get(st["CP"],rt["cp"],"checkpoint_sha");pred=None if cp["predecessor_checkpoint_sha"] is None else get(st["CP"],cp["predecessor_checkpoint_sha"],"checkpoint_sha");verifycp(cp,st,bootstrap,pred)
  if not ext:return "HOLD_EXTERNAL_MISSING"
  if ext[-1]["checkpoint_sha"]!=rt["cp"]:return "HOLD_EXTERNAL_AHEAD"
  closure(cur,st,cp);return "AUTHORITATIVE_PUBLIC_CHECKPOINTED"
 except Exception:return "HOLD"
def prep(rt,st,ext,bootstrap,priv,used,count):
 if not auth(rt,st,ext,bootstrap).startswith("AUTHORITATIVE"):raise ValueError("predecessor authority HOLD")
 pred=None if rt["cp"] is None else get(st["CP"],rt["cp"],"checkpoint_sha");ep=1 if pred is None else pred["epoch"]+1;signers=deepcopy(bootstrap if pred is None else pred["next_signer_keys"]);m=closure(tuple(rt["cur"]),st,pred,count);h,s,ks=view(tuple(rt["cur"]),st)
 snap={"generation":h["generation"],"registry_sha":h["registry_sha"],"tuple":list(rt["cur"]),"attestation_heads":deepcopy(s["heads"]),"key_heads":deepcopy(ks["heads"]),"segment_digest":m["digest"],"segment_counts":m["counts"]};nextk={}
 for r in R:
  p=get(st["PUB"],signers[r],"pub_sha");n,v=lpair(r,p["generation"]+1,p["pub_sha"]);put(st["PUB"],n,"pub_sha");priv[n["pub_sha"]]=v;nextk[r]=n["pub_sha"]
 pay=payload(ep,None if pred is None else pred["checkpoint_sha"],snap,signers,nextk);sigs={}
 for r in R:
  k=signers[r]
  if k in used:raise ValueError("lamport signer reuse forbidden")
  if k not in priv:raise ValueError("checkpoint private signer missing")
  sigs[r]=lsign(priv[k],{**pay,"root":r});used.add(k)
 cp=seal({"schema":"public-authority-checkpoint/v1","epoch":ep,"predecessor_checkpoint_sha":None if pred is None else pred["checkpoint_sha"],"snapshot":snap,"signer_keys":signers,"next_signer_keys":nextk,"signatures":sigs,"checkpoint_sha":""},"checkpoint_sha");put(st["CP"],cp,"checkpoint_sha");return cp,m
def applycp(rt,cp,n=None):
 old=rt["cp"]
 if cp["predecessor_checkpoint_sha"]!=old:return "PREDECESSOR_HOLD"
 if cp["epoch"]!=rt["cpe"]+1:return "EPOCH_HOLD"
 if any(rt["cw"][w] not in (old,cp["checkpoint_sha"]) for w in W):return "COMPETING_HOLD"
 lag=[w for w in W if rt["cw"][w]==old];n=len(lag) if n is None else min(max(n,0),len(lag))
 for w in lag[:n]:rt["cw"][w]=cp["checkpoint_sha"]
 if any(rt["cw"][w]!=cp["checkpoint_sha"] for w in W):return "PARTIAL"
 rt["cp"]=cp["checkpoint_sha"];rt["cpe"]=cp["epoch"];return "COMMITTED"
def extpub(ext,cp):
 prev=ext[-1] if ext else None;ep=1 if prev is None else prev["epoch"]+1;pred=None if prev is None else prev["checkpoint_sha"]
 if cp["epoch"]!=ep:return "EPOCH_HOLD"
 if cp["predecessor_checkpoint_sha"]!=pred:return "PREDECESSOR_HOLD"
 rec=seal({"schema":"external-anchor/v1","epoch":ep,"checkpoint_sha":cp["checkpoint_sha"],"previous_record_sha":None if prev is None else prev["record_sha"],"record_sha":""},"record_sha");ext.append(rec);return "APPENDED"
def trans(rt,st,ext,bootstrap,reg,rotate=None):
 if not auth(rt,st,ext,bootstrap).startswith("AUTHORITATIVE"):raise ValueError("predecessor authority HOLD")
 old=tuple(rt["cur"]);h,s,ks=view(old,st);g=h["generation"];tr=seal({"schema":"transition/v1","generation":g+1,"predecessor_tuple":list(old),"target_registry_sha":reg,"rotate_root":rotate,"transition_sha":""},"transition_sha");kh=deepcopy(ks["heads"])
 if rotate:
  ok=get(st["K"],kh[rotate],"key_sha");sec=hashlib.sha256(f"state|{rotate}|{ok['generation']+1}".encode()).digest();nk=key(rotate,ok["generation"]+1,sec,ok["key_sha"]);put(st["K"],nk,"key_sha");st["SEC"][nk["key_sha"]]=sec;kh[rotate]=nk["key_sha"]
 ah=deepcopy(s["heads"])
 for r in R:
  k=get(st["K"],ks["heads"][r],"key_sha");sec=st["SEC"].get(k["key_sha"])
  if sec is None:raise ValueError("key secret mismatch")
  a=attest(tr["transition_sha"],g,r,ah[r]["sequence"]+1,ah[r]["att_sha"],k["key_sha"],sec);put(st["A"],a,"att_sha");ah[r]={"sequence":a["sequence"],"att_sha":a["att_sha"]}
 nh=hist(g+1,reg,old[0]);ns=state(g+1,reg,old[1],ah);nks=state(g+1,reg,old[2],kh,"key_state_sha","key-state/v1");put(st["H"],nh,"history_sha");put(st["S"],ns,"state_sha");put(st["KS"],nks,"key_state_sha");return [nh["history_sha"],ns["state_sha"],nks["key_state_sha"]]
def applyt(rt,t):
 old=tuple(rt["cur"])
 if any(tuple(rt["w"][w])!=old for w in W):return "HOLD"
 rt["cur"]=list(t);rt["w"]={w:list(t) for w in W};return "COMMITTED"
def prune(cp,st,prior):
 m=closure(tuple(cp["snapshot"]["tuple"]),st,prior);keep=set(cp["snapshot"]["tuple"]);keepk=set(cp["snapshot"]["key_heads"].values());rm={k:0 for k in ("history","att_state","key_state","attestations","keys","secrets")}
 for n,s in (("history",st["H"]),("att_state",st["S"]),("key_state",st["KS"])):
  for q in m[n]:
   if q not in keep and q in s:del s[q];rm[n]+=1
 for q in m["attestations"]:
  if q in st["A"]:del st["A"][q];rm["attestations"]+=1
 for q in m["keys"]:
  if q not in keepk:
   if q in st["K"]:del st["K"][q];rm["keys"]+=1
   if q in st["SEC"]:del st["SEC"][q];rm["secrets"]+=1
 return rm
def bench(n):
 c=[];v=[]
 for _ in range(n):
  st,rt=fixture();ext=[];b,p=boot(st);u=set();z=[0];t=time.process_time_ns();cp,_=prep(rt,st,ext,b,p,u,z);c.append(time.process_time_ns()-t);t=time.process_time_ns();verifycp(cp,st,b);v.append(time.process_time_ns()-t)
 return {"rounds":n,"checkpoint_create_median_cpu_us":statistics.median(c)/1000,"public_verify_median_cpu_us":statistics.median(v)/1000}
def run(n):
 C=[];C.append(("exact_wave95_sources",SRC["wave95_head"].startswith("42bf7230") and SRC["verifier_head"].startswith("bbe9bbcc") and SRC["verifier_workflow"]==35139830377));st,rt=fixture();ext=[];b,p=boot(st);u=set();C.append(("genesis_authority",auth(rt,st,ext,b)=="AUTHORITATIVE_FULL"));z=[0];c1,m1=prep(rt,st,ext,b,p,u,z);C.extend([("cp1_single_closure",z[0]==1),("cp1_verify",verifycp(c1,st,b) is None),("cp1_partial",applycp(rt,c1,1)=="PARTIAL"),("partial_holds",auth(rt,st,ext,b).startswith("HOLD")),("cp1_local",applycp(rt,c1)=="COMMITTED"),("external_required",auth(rt,st,ext,b)=="HOLD_EXTERNAL_MISSING"),("cp1_external",extpub(ext,c1)=="APPENDED"),("cp1_authority",auth(rt,st,ext,b).startswith("AUTHORITATIVE"))]);oldsign=list(c1["signer_keys"].values());[p.pop(k,None) for k in oldsign];C.append(("destroyed_checkpoint_private_material_still_verifies",verifycp(c1,st,b) is None and all(k not in p for k in oldsign)));oldtruth=get(st["KS"],rt["cur"][2],"key_state_sha")["heads"]["truth"];C.append(("transition1",applyt(rt,trans(rt,st,ext,b,T("registry-1"),"truth"))=="COMMITTED"));z=[0];c2,m2=prep(rt,st,ext,b,p,u,z);C.extend([("cp2_recheckpoint_single_closure",z[0]==1),("cp2_pred_epoch_bound",c2["predecessor_checkpoint_sha"]==c1["checkpoint_sha"] and c2["epoch"]==2),("cp2_rotated_signers",c2["signer_keys"]==c1["next_signer_keys"]),("cp2_local",applycp(rt,c2)=="COMMITTED"),("cp2_external",extpub(ext,c2)=="APPENDED"),("cp2_authority",auth(rt,st,ext,b).startswith("AUTHORITATIVE")),("old_replay_local_blocked",applycp(rt,c1)=="PREDECESSOR_HOLD"),("old_replay_external_blocked",extpub(ext,c1) in ("EPOCH_HOLD","PREDECESSOR_HOLD"))]);rm=prune(c2,st,c1);st["SEC"].pop(oldtruth,None);C.extend([("compaction_survives",auth(rt,st,ext,b).startswith("AUTHORITATIVE")),("retired_state_secret_erased",oldtruth not in st["SEC"]),("segment_pruned",sum(rm.values())>0)]);C.append(("transition2_after_recheckpoint",applyt(rt,trans(rt,st,ext,b,T("registry-2")))=="COMMITTED"));z=[0];c3,m3=prep(rt,st,ext,b,p,u,z);C.extend([("third_checkpoint_after_prune",c3["epoch"]==3 and z[0]==1),("cp3_local",applycp(rt,c3)=="COMMITTED"),("cp3_external",extpub(ext,c3)=="APPENDED"),("cp3_authority",auth(rt,st,ext,b).startswith("AUTHORITATIVE"))]);bad=deepcopy(c3);bad["signatures"]["truth"][0]="00"*32;bad=seal(bad,"checkpoint_sha");C.append(("tamper_rejected",fail(lambda:verifycp(bad,st,b,c2),"lamport signature mismatch")));wrong=deepcopy(c3);wrong["signer_keys"]["truth"]=c1["signer_keys"]["truth"];wrong=seal(wrong,"checkpoint_sha");C.append(("wrong_rotation_rejected",fail(lambda:verifycp(wrong,st,b,c2),"checkpoint signer rotation mismatch")));rb=deepcopy(rt);rb["cp"]=c2["checkpoint_sha"];rb["cpe"]=2;rb["cw"]={w:c2["checkpoint_sha"] for w in W};rb["cur"]=list(c2["snapshot"]["tuple"]);rb["w"]={w:list(rb["cur"]) for w in W};C.append(("external_detects_local_rollback",auth(rb,st,ext,b)=="HOLD_EXTERNAL_AHEAD"));C.append(("whole_domain_rollback_counterexample",auth(rb,st,deepcopy(ext[:2]),b).startswith("AUTHORITATIVE")));passed=sum(ok for _,ok in C)
 return {"schema":"axm.flowing_compute.wave96.report/v1","wave":96,"source":SRC,"controls":{"passed":passed,"total":len(C),"rows":[{"name":x,"pass":bool(y)} for x,y in C]},"segments":{"cp1":m1["counts"],"cp2":m2["counts"],"cp3":m3["counts"],"pruned_cp1_to_cp2":rm},"synthetic_benchmark":{"label":"SYNTHETIC single-host process-CPU checkpoint construction/public verification; not monolith compute-efficiency or energy evidence",**bench(n)},"truth_boundary":["No fresh monolith workload is read; this is authority/checkpoint infrastructure research only.","Lamport OTS is a public-verification test model; it proves one-time private-material possession, not identity, legitimacy, or judgment correctness.","Checkpoint signing private material can be erased after signing; the older state-attestation HMAC layer remains separate and is not claimed solved.","The external anchor is a separately supplied append-only state domain in this model, not a physically independent device/service or distributed consensus.","Whole-domain rollback including the external anchor remains an explicit counterexample.","No retained/incremental/dormant compute win is inferred from these tests or timings."],"next_gate":"Put the external anchor on a physically independent monotonic service/device (or two independent remote witnesses), then attack credentialed remote rewrite, witness partition, conflicting remote histories, and recovery with one witness unavailable. Separately migrate the remaining HMAC state-attestation layer to public verification only if transition and rollback semantics survive."}
def main():
 a=argparse.ArgumentParser();a.add_argument("--bench-rounds",type=int,default=5);a.add_argument("--out");q=a.parse_args();r=run(q.bench_rounds);s=json.dumps(r,indent=2,sort_keys=True);print(s);q.out and open(q.out,"w",encoding="utf-8").write(s+"\n");raise SystemExit(0 if r["controls"]["passed"]==r["controls"]["total"] else 1)
if __name__=="__main__":main()
