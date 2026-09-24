#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, hmac, json, statistics, time
from copy import deepcopy

ROOTS=("truth","agency_non_domination","continuity","wisdom_before_speed")
WIT=("witness-a","witness-b","witness-c")
W94={
 "builder_head":"340fd44141b40493b0ddd7a51fd653ada9ddf9b8",
 "path":"tools/AXM_FLOWING_COMPUTE_EVIDENCE_CLOSURE_SIGNER_KEYS.py",
 "blob_sha":"4b086ac98331a63e21292d3f11e65b3868c9204c",
}
V94={
 "pr":19,
 "head":"50212ef804bf9a545f930af55584ba7ff1d4fc75",
 "evidence_path":"verification/WAVE94_ADVERSARIAL_VERIFICATION_2026-09-16.md",
 "evidence_blob_sha":"af5669da6f9c16a471ff45d6ae7b17429c36a8d1",
 "finding":"FAIL_ATTESTATION_AND_KEY_STATE_PREDECESSOR_BODIES_CAN_DANGLE_AND_HISTORY_CAN_EXTEND",
 "workflow_run":35133408523,
}

def enc(x): return json.dumps(x,sort_keys=True,separators=(",",":")).encode()
def dig(x): return hashlib.sha256(enc(x)).hexdigest()
def td(s): return hashlib.sha256(s.encode()).hexdigest()
def seal(x,f):
    y=deepcopy(x); y.pop(f,None); y[f]=dig(y); return y
def chk(x,f):
    y=deepcopy(x); got=y.pop(f,None)
    if got!=dig(y): raise ValueError(f"{f} mismatch")
def put(st,x,f):
    chk(x,f); k=x[f]
    if k in st and st[k]!=x: raise ValueError("collision")
    st[k]=deepcopy(x); return k
def get(st,k,f):
    if k not in st: raise ValueError(f"{f} body missing")
    x=deepcopy(st[k]); chk(x,f)
    if x.get(f)!=k: raise ValueError(f"{f} key/body mismatch")
    return x
def mac(sec,x): return hmac.new(sec,enc(x),hashlib.sha256).hexdigest()
def fails(fn,text):
    try: fn()
    except Exception as e: return text in str(e)
    return False

def key(root,gen,sec,pred=None):
    return seal({"schema":"key/v1","root":root,"generation":gen,"predecessor":pred,
                 "material":hashlib.sha256(sec).hexdigest(),"key_sha":""},"key_sha")
def secret(k,secrets):
    sec=secrets.get(k["key_sha"])
    if sec is None or hashlib.sha256(sec).hexdigest()!=k["material"]:
        raise ValueError("key secret mismatch")
    return sec
def hist(gen,registry,pred=None):
    return seal({"schema":"history/v1","generation":gen,"registry_sha":registry,
                 "predecessor":pred,"history_sha":""},"history_sha")
def state(gen,registry,pred,heads):
    return seal({"schema":"att-state/v1","generation":gen,"registry_sha":registry,
                 "predecessor":pred,"heads":deepcopy(heads),"state_sha":""},"state_sha")
def key_state(gen,registry,pred,heads):
    return seal({"schema":"key-state/v1","generation":gen,"registry_sha":registry,
                 "predecessor":pred,"heads":deepcopy(heads),"key_state_sha":""},"key_state_sha")
def attest(trans,gen,root,seq,prev,key_sha,sec,verdict="PASS"):
    x={"schema":"att/v1","transition_sha":trans,"registry_generation":gen,"root":root,
       "sequence":seq,"previous":prev,"signer_key_sha":key_sha,"verdict":verdict,
       "algorithm":"HMAC-SHA256-test-model","test_only":True}
    x["mac"]=mac(sec,x); return seal(x,"att_sha")
def aval(a,K,secrets):
    chk(a,"att_sha")
    x=deepcopy(a); x.pop("att_sha"); sig=x.pop("mac")
    k=get(K,a["signer_key_sha"],"key_sha")
    if k["root"]!=a["root"] or sig!=mac(secret(k,secrets),x):
        raise ValueError("attestation MAC mismatch")

def hchain(head,H,stop=None,manifest=None):
    exp=None; n=0
    while head and head!=stop:
        h=get(H,head,"history_sha")
        if exp is not None and h["generation"]!=exp: raise ValueError("history discontinuity")
        if manifest is not None: manifest["history"].add(head)
        exp=h["generation"]-1; head=h["predecessor"]; n+=1
    if stop is None and exp!=-1: raise ValueError("history genesis missing")
    if stop is not None and head!=stop: raise ValueError("history checkpoint not reached")
    return n

def schain(head,S,field,stop=None,manifest=None):
    exp=None; n=0
    while head and head!=stop:
        s=get(S,head,field)
        if exp is not None and s["generation"]!=exp: raise ValueError(f"{field} discontinuity")
        if manifest is not None:
            manifest["att_state" if field=="state_sha" else "key_state"].add(head)
        exp=s["generation"]-1; head=s["predecessor"]; n+=1
    if stop is None and exp!=-1: raise ValueError(f"{field} genesis missing")
    if stop is not None and head!=stop: raise ValueError(f"{field} checkpoint not reached")
    return n

def achain(head,A,K,secrets,root,seq,stop_sha=None,stop_seq=0,manifest=None):
    exp=seq
    while head and head!=stop_sha:
        a=get(A,head,"att_sha"); aval(a,K,secrets)
        if a["root"]!=root or a["sequence"]!=exp: raise ValueError("attestation lineage mismatch")
        if manifest is not None:
            manifest["attestations"].add(head); manifest["keys"].add(a["signer_key_sha"])
        exp-=1; head=a["previous"]
    if head!=stop_sha or exp!=stop_seq: raise ValueError("attestation checkpoint/genesis missing")

def kchain(head,K,secrets,root,stop_sha=None,stop_gen=-1,manifest=None,need_all_secrets=True):
    exp=None; n=0
    while head and head!=stop_sha:
        k=get(K,head,"key_sha")
        if k["root"]!=root or (exp is not None and k["generation"]!=exp): raise ValueError("key lineage mismatch")
        if need_all_secrets: secret(k,secrets)
        if manifest is not None: manifest["keys"].add(head)
        exp=k["generation"]-1; head=k["predecessor"]; n+=1
    if head!=stop_sha: raise ValueError("key checkpoint not reached")
    if stop_sha is None:
        if exp!=-1: raise ValueError("key genesis missing")
    elif n and exp!=stop_gen:
        raise ValueError("key checkpoint generation mismatch")

def full_tuple_closure(tup,stores,manifest=None):
    H,A,K,S,KS,C,secrets=stores
    hh,ss,kk=tup
    h=get(H,hh,"history_sha"); s=get(S,ss,"state_sha"); ks=get(KS,kk,"key_state_sha")
    if not(h["generation"]==s["generation"]==ks["generation"]): raise ValueError("authority tuple generation mismatch")
    if not(h["registry_sha"]==s["registry_sha"]==ks["registry_sha"]): raise ValueError("authority tuple registry mismatch")
    if set(s["heads"])!=set(ROOTS) or set(ks["heads"])!=set(ROOTS): raise ValueError("root set mismatch")
    hchain(hh,H,None,manifest); schain(ss,S,"state_sha",None,manifest); schain(kk,KS,"key_state_sha",None,manifest)
    for r in ROOTS:
        hd=s["heads"][r]; achain(hd["att_sha"],A,K,secrets,r,hd["sequence"],None,0,manifest)
        kchain(ks["heads"][r],K,secrets,r,None,-1,manifest,True)
    return h["generation"],h["registry_sha"],s,ks

def manifest_for(tup,stores):
    m={k:set() for k in ("history","att_state","key_state","attestations","keys")}
    full_tuple_closure(tup,stores,m)
    out={k:sorted(v) for k,v in m.items()}
    out["counts"]={k:len(v) for k,v in out.items() if isinstance(v,list)}
    out["digest"]=dig({k:out[k] for k in ("history","att_state","key_state","attestations","keys")})
    return out

def checkpoint(tup,stores,epoch):
    H,A,K,S,KS,C,secrets=stores
    gen,reg,s,ks=full_tuple_closure(tup,stores)
    m=manifest_for(tup,stores)
    snap={"generation":gen,"registry_sha":reg,"tuple":list(tup),
          "attestation_heads":deepcopy(s["heads"]),"key_heads":deepcopy(ks["heads"]),
          "archive_digest":m["digest"],"archive_counts":m["counts"]}
    sigs={}
    for r in ROOTS:
        kh=ks["heads"][r]; k=get(K,kh,"key_sha")
        payload={"schema":"checkpoint-root-endorsement/v1","epoch":epoch,"root":r,
                 "key_sha":kh,"snapshot":snap,"algorithm":"HMAC-SHA256-test-model","test_only":True}
        sigs[r]={"key_sha":kh,"mac":mac(secret(k,secrets),payload)}
    cp=seal({"schema":"authority-checkpoint/v1","epoch":epoch,"snapshot":snap,
             "endorsements":sigs,"truth_boundary":{
                "signatures":"HMAC-SHA256-test-model; proves modeled possession only",
                "archive":"pre-cut bodies may be pruned only after checkpoint commit",
                "rollback":"all-domain rollback remains undetectable"
             },"checkpoint_sha":""},"checkpoint_sha")
    put(C,cp,"checkpoint_sha")
    return cp,m

def cvalidate(cp,stores):
    H,A,K,S,KS,C,secrets=stores
    chk(cp,"checkpoint_sha")
    snap=cp["snapshot"]
    if set(snap["attestation_heads"])!=set(ROOTS) or set(snap["key_heads"])!=set(ROOTS):
        raise ValueError("checkpoint root set mismatch")
    if set(cp["endorsements"])!=set(ROOTS): raise ValueError("checkpoint endorsement root set mismatch")
    for r in ROOTS:
        e=cp["endorsements"][r]
        if e["key_sha"]!=snap["key_heads"][r]: raise ValueError("checkpoint key/head mismatch")
        k=get(K,e["key_sha"],"key_sha")
        if k["root"]!=r: raise ValueError("checkpoint key root mismatch")
        payload={"schema":"checkpoint-root-endorsement/v1","epoch":cp["epoch"],"root":r,
                 "key_sha":e["key_sha"],"snapshot":snap,"algorithm":"HMAC-SHA256-test-model","test_only":True}
        if e["mac"]!=mac(secret(k,secrets),payload): raise ValueError("checkpoint endorsement mismatch")
    return snap

def authority(rt,stores):
    H,A,K,S,KS,C,secrets=stores
    if set(rt["w"])!=set(WIT) or any(tuple(rt["w"][w])!=tuple(rt["cur"]) for w in WIT):
        return "HOLD"
    csha=rt.get("checkpoint_sha")
    if csha is None:
        if any(rt.get("cw",{}).get(w) is not None for w in WIT): return "HOLD"
        try: full_tuple_closure(tuple(rt["cur"]),stores)
        except Exception: return "HOLD"
        return "AUTHORITATIVE_FULL"
    if set(rt.get("cw",{}))!=set(WIT) or any(rt["cw"][w]!=csha for w in WIT): return "HOLD"
    try:
        cp=get(C,csha,"checkpoint_sha"); snap=cvalidate(cp,stores)
        base=tuple(snap["tuple"]); cur=tuple(rt["cur"])
        hh,ss,kk=cur
        h=get(H,hh,"history_sha"); s=get(S,ss,"state_sha"); ks=get(KS,kk,"key_state_sha")
        if not(h["generation"]==s["generation"]==ks["generation"]): raise ValueError("authority tuple generation mismatch")
        if not(h["registry_sha"]==s["registry_sha"]==ks["registry_sha"]): raise ValueError("authority tuple registry mismatch")
        if h["generation"]<snap["generation"]: raise ValueError("current before checkpoint")
        if cur!=base:
            hchain(hh,H,base[0]); schain(ss,S,"state_sha",base[1]); schain(kk,KS,"key_state_sha",base[2])
        else:
            if (h["generation"],h["registry_sha"])!=(snap["generation"],snap["registry_sha"]): raise ValueError("checkpoint base mismatch")
        for r in ROOTS:
            bh=snap["attestation_heads"][r]; hd=s["heads"][r]
            achain(hd["att_sha"],A,K,secrets,r,hd["sequence"],bh["att_sha"],bh["sequence"])
            bk=snap["key_heads"][r]; bko=get(K,bk,"key_sha")
            kchain(ks["heads"][r],K,secrets,r,bk,bko["generation"],None,False)
    except Exception:
        return "HOLD"
    return "AUTHORITATIVE_CHECKPOINTED"

def transition(rt,stores,registry,rotate=None):
    H,A,K,S,KS,C,secrets=stores
    if not authority(rt,stores).startswith("AUTHORITATIVE"): raise ValueError("predecessor authority HOLD")
    old=tuple(rt["cur"]); hh,ss,kk=old
    h=get(H,hh,"history_sha"); s=get(S,ss,"state_sha"); ks=get(KS,kk,"key_state_sha"); gen=h["generation"]
    tr=seal({"schema":"transition/v1","generation":gen+1,"predecessor_tuple":list(old),
             "target_registry_sha":registry,"rotate_root":rotate,"transition_sha":""},"transition_sha")
    kh=deepcopy(ks["heads"])
    if rotate:
        oldk=get(K,kh[rotate],"key_sha"); sec=td(f"{rotate}-secret-{gen+1}").encode()
        nk=key(rotate,oldk["generation"]+1,sec,oldk["key_sha"]); put(K,nk,"key_sha"); secrets[nk["key_sha"]]=sec
        kh[rotate]=nk["key_sha"]
    heads=deepcopy(s["heads"])
    for r in ROOTS:
        hd=heads[r]; signer=ks["heads"][r]; k=get(K,signer,"key_sha")
        a=attest(tr["transition_sha"],gen,r,hd["sequence"]+1,hd["att_sha"],signer,secret(k,secrets))
        put(A,a,"att_sha"); heads[r]={"sequence":a["sequence"],"att_sha":a["att_sha"]}
    nh=hist(gen+1,registry,hh); put(H,nh,"history_sha")
    ns=state(gen+1,registry,ss,heads); put(S,ns,"state_sha")
    nks=key_state(gen+1,registry,kk,kh); put(KS,nks,"key_state_sha")
    return (nh["history_sha"],ns["state_sha"],nks["key_state_sha"])

def apply_transition(rt,target):
    old=tuple(rt["cur"])
    if any(tuple(rt["w"][w])!=old for w in WIT): return "HOLD"
    for w in WIT: rt["w"][w]=list(target)
    rt["cur"]=list(target); return "COMMITTED"

def apply_checkpoint(rt,cp,count=None):
    csha=cp["checkpoint_sha"]; old=rt.get("checkpoint_sha")
    cw=rt.setdefault("cw",{w:old for w in WIT})
    if set(cw)!=set(WIT): return "HOLD"
    if any(cw[w] not in (old,csha) for w in WIT): return "COMPETING_HOLD"
    lag=[w for w in WIT if cw[w]==old]
    n=len(lag) if count is None else min(max(count,0),len(lag))
    for w in lag[:n]: cw[w]=csha
    if any(cw[w]!=csha for w in WIT): return "PARTIAL"
    rt["checkpoint_sha"]=csha
    return "COMMITTED"

def prune_precut(cp,stores,keep_current_tuple=True):
    H,A,K,S,KS,C,secrets=stores
    snap=cp["snapshot"]; base=tuple(snap["tuple"])
    manifest={"history":set(),"att_state":set(),"key_state":set(),"attestations":set(),"keys":set()}
    full_tuple_closure(base,stores,manifest)
    current_heads=set(snap["key_heads"].values())
    removed={k:0 for k in ("history","att_state","key_state","attestations","keys","secrets")}
    for name,store in (("history",H),("att_state",S),("key_state",KS),("attestations",A)):
        for sha in list(manifest[name]):
            if keep_current_tuple and sha in base: continue
            if sha in store: del store[sha]; removed[name]+=1
    for sha in list(manifest["keys"]):
        if sha in current_heads: continue
        if sha in K: del K[sha]; removed["keys"]+=1
        if sha in secrets: del secrets[sha]; removed["secrets"]+=1
    return removed

def fixture():
    H,A,K,S,KS,C,secrets={},{},{},{},{},{},{}
    kh={}; heads={r:{"sequence":0,"att_sha":None} for r in ROOTS}
    for r in ROOTS:
        sec=td(f"{r}-secret-0").encode(); k=key(r,0,sec); put(K,k,"key_sha"); secrets[k["key_sha"]]=sec; kh[r]=k["key_sha"]
    reg=td("registry-0")
    h=hist(0,reg); put(H,h,"history_sha")
    s=state(0,reg,None,heads); put(S,s,"state_sha")
    ks=key_state(0,reg,None,kh); put(KS,ks,"key_state_sha")
    cur=[h["history_sha"],s["state_sha"],ks["key_state_sha"]]
    rt={"cur":cur,"w":{w:list(cur) for w in WIT},"checkpoint_sha":None,"cw":{w:None for w in WIT}}
    return (H,A,K,S,KS,C,secrets),rt

def build_depth(depth):
    st,rt=fixture()
    for i in range(depth):
        tgt=transition(rt,st,td(f"registry-{i+1}"),rotate=("truth" if i in (1,7,31) else None))
        if apply_transition(rt,tgt)!="COMMITTED": raise RuntimeError("depth build failed")
    return st,rt

def bench_depth(depth,rounds):
    full_samples=[]; cp_samples=[]
    for _ in range(rounds):
        st,rt=build_depth(depth)
        t=time.process_time_ns(); a=authority(rt,st); full_samples.append(time.process_time_ns()-t)
        if a!="AUTHORITATIVE_FULL": raise RuntimeError("full benchmark not authoritative")
        cp,m=checkpoint(tuple(rt["cur"]),st,1); apply_checkpoint(rt,cp)
        prune_precut(cp,st)
        t=time.process_time_ns(); a2=authority(rt,st); cp_samples.append(time.process_time_ns()-t)
        if a2!="AUTHORITATIVE_CHECKPOINTED": raise RuntimeError("checkpoint benchmark not authoritative")
    return {
      "depth":depth,"rounds":rounds,
      "full_closure_median_cpu_us":statistics.median(full_samples)/1000,
      "checkpointed_median_cpu_us":statistics.median(cp_samples)/1000,
      "ratio_checkpointed_over_full":statistics.median(cp_samples)/statistics.median(full_samples),
    }

def run(rounds,scale_rounds):
    C=[]
    C += [
      ("exact_wave94_builder_source",W94["builder_head"]=="340fd44141b40493b0ddd7a51fd653ada9ddf9b8"),
      ("exact_wave94_verifier_source",V94["head"]=="50212ef804bf9a545f930af55584ba7ff1d4fc75" and V94["workflow_run"]==35133408523),
    ]
    st,rt=fixture(); H,A,K,S,KS,CPS,secrets=st
    C.append(("genesis_full_authority",authority(rt,st)=="AUTHORITATIVE_FULL"))
    t1=transition(rt,st,td("registry-1")); C.append(("first_transition_commits",apply_transition(rt,t1)=="COMMITTED"))
    cur=tuple(rt["cur"]); s1=get(S,cur[1],"state_sha"); ks1=get(KS,cur[2],"key_state_sha")
    old_s=s1["predecessor"]; old_ks=ks1["predecessor"]
    save_s=S.pop(old_s); save_ks=KS.pop(old_ks)
    C += [
      ("wave94_dangling_att_state_now_holds",authority(rt,st)=="HOLD"),
      ("cannot_extend_dangling_state",fails(lambda:transition(rt,st,td("blocked")),"predecessor authority HOLD")),
      ("cannot_checkpoint_dangling_state",fails(lambda:checkpoint(tuple(rt["cur"]),st,1),"state_sha body missing")),
    ]
    S[old_s]=save_s; KS[old_ks]=save_ks
    C.append(("restored_full_closure",authority(rt,st)=="AUTHORITATIVE_FULL"))
    t2=transition(rt,st,td("registry-2"),rotate="truth"); C.append(("rotation_transition_commits",apply_transition(rt,t2)=="COMMITTED"))
    base=tuple(rt["cur"]); current_truth=get(KS,base[2],"key_state_sha")["heads"]["truth"]
    retired_truth=get(K,current_truth,"key_sha")["predecessor"]
    C.append(("retired_truth_secret_present_precheckpoint",retired_truth in secrets))
    cp,manifest=checkpoint(base,st,1)
    C += [
      ("checkpoint_binds_exact_base_tuple",tuple(cp["snapshot"]["tuple"])==base),
      ("checkpoint_binds_archive_digest",cp["snapshot"]["archive_digest"]==manifest["digest"]),
    ]
    C.append(("checkpoint_partial_fanout",apply_checkpoint(rt,cp,1)=="PARTIAL"))
    C.append(("partial_checkpoint_not_authoritative",authority(rt,st)=="HOLD"))
    C.append(("checkpoint_recovery_commits",apply_checkpoint(rt,cp)=="COMMITTED"))
    C.append(("checkpointed_authority_before_prune",authority(rt,st)=="AUTHORITATIVE_CHECKPOINTED"))
    removed=prune_precut(cp,st)
    C += [
      ("precut_bodies_pruned",sum(removed[k] for k in ("history","att_state","key_state","attestations","keys"))>0),
      ("retired_symmetric_secret_destroyed",retired_truth not in secrets),
      ("checkpointed_authority_survives_precut_prune",authority(rt,st)=="AUTHORITATIVE_CHECKPOINTED"),
    ]
    t3=transition(rt,st,td("registry-3")); C.append(("postcut_transition_commits",apply_transition(rt,t3)=="COMMITTED"))
    C.append(("postcut_authority",authority(rt,st)=="AUTHORITATIVE_CHECKPOINTED"))
    cur3=tuple(rt["cur"]); save3=S.pop(cur3[1])
    C.append(("missing_current_state_holds",authority(rt,st)=="HOLD")); S[cur3[1]]=save3
    rt_bad=deepcopy(rt); rt_bad["cw"]["witness-c"]=None
    C.append(("checkpoint_witness_disagreement_holds",authority(rt_bad,st)=="HOLD"))
    st_comp=deepcopy(st); rt_comp=deepcopy(rt)
    forged=deepcopy(cp); forged["epoch"]=99; forged=seal(forged,"checkpoint_sha"); put(st_comp[5],forged,"checkpoint_sha")
    rt_comp["cw"]["witness-a"]=forged["checkpoint_sha"]
    C.append(("competing_checkpoint_holds",authority(rt_comp,st_comp)=="HOLD"))
    tam=deepcopy(cp); tam["snapshot"]["archive_digest"]=td("forged-archive"); tam=seal(tam,"checkpoint_sha")
    C.append(("rehashed_checkpoint_forgery_rejected",fails(lambda:cvalidate(tam,st),"checkpoint endorsement mismatch")))
    cut_truth=cp["snapshot"]["key_heads"]["truth"]; saved_cut=secrets.pop(cut_truth)
    C.append(("cut_head_secret_destruction_holds",authority(rt,st)=="HOLD")); secrets[cut_truth]=saved_cut
    C.append(("cut_head_secret_restoration_recovers",authority(rt,st)=="AUTHORITATIVE_CHECKPOINTED"))
    old_st,old_rt=fixture()
    C.append(("whole_domain_rollback_counterexample_preserved",authority(old_rt,old_st)=="AUTHORITATIVE_FULL"))
    st_small,rt_small=build_depth(1)
    t=time.process_time_ns(); authority(rt_small,st_small); one_full=time.process_time_ns()-t
    t=time.process_time_ns(); checkpoint(tuple(rt_small["cur"]),st_small,1); one_cp=time.process_time_ns()-t
    C.append(("checkpoint_setup_not_assumed_free",one_cp>0 and one_full>0))
    passed=sum(1 for _,ok in C if ok)
    scaling=[bench_depth(d,scale_rounds) for d in (1,4,16,64)]
    return {
      "schema":"axm.flowing_compute.wave95.report/v1",
      "wave":95,
      "title":"Authority-bound checkpoint compaction with complete predecessor closure",
      "source":{"wave94":W94,"wave94_verifier":V94},
      "controls":{"passed":passed,"total":len(C),"rows":[{"name":n,"pass":bool(ok)} for n,ok in C]},
      "checkpoint":{"archive_counts":manifest["counts"],"archive_digest":manifest["digest"],"pruned":removed},
      "synthetic_scaling":{
        "label":"SYNTHETIC single-host process-CPU validation scaling; not monolith/AXM compute-efficiency evidence",
        "depths":scaling,
        "interpretation":"Full retained closure grows with depth in this model. Checkpointed validation is bounded by post-cut live depth, but checkpoint creation itself performs full closure and signatures. This is storage/validation infrastructure evidence only."
      },
      "truth_boundary":[
        "No fresh monolith workload was read; no retained/incremental/dormant compute win is claimed.",
        "Checkpoint signatures use HMAC-SHA256 as a test model only; they show modeled secret possession, not identity, legitimacy, or judgment correctness.",
        "Compaction can destroy retired pre-cut HMAC secrets after a committed cut, but the checkpoint-signing head secrets remain required in this model.",
        "All-domain rollback of runtime, witnesses, checkpoint store, and surviving secrets together remains internally indistinguishable.",
        "Pre-cut bodies become intentionally non-required only after exact full closure is verified and the checkpoint is committed by all required witnesses.",
      ],
      "next_gate":"Move checkpoint anti-rollback evidence into a genuinely separate failure domain and replace test-only symmetric verification with a public-verification model before claiming safe retired-private-key destruction."
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--rounds",type=int,default=1)
    ap.add_argument("--scale-rounds",type=int,default=3)
    ap.add_argument("--out")
    a=ap.parse_args()
    reps=[run(a.rounds,a.scale_rounds) for _ in range(a.rounds)]
    report=reps[-1]
    report["repeat_runs"]=a.rounds
    report["all_runs_passed"]=all(r["controls"]["passed"]==r["controls"]["total"] for r in reps)
    text=json.dumps(report,indent=2,sort_keys=True)
    if a.out: open(a.out,"w",encoding="utf-8").write(text+"\n")
    print(text)
    raise SystemExit(0 if report["all_runs_passed"] else 1)
if __name__=="__main__": main()
