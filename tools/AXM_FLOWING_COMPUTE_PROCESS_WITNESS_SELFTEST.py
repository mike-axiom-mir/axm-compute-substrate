#!/usr/bin/env python3
"""Wave 123 adversarial self-test: actual OS-process witness + SIGKILL boundaries."""
from __future__ import annotations

import argparse, hashlib, json, os, shutil, signal, subprocess, sys, tempfile, time
from pathlib import Path
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS as w

TOOL = Path(w.__file__).resolve()

def h(s): return hashlib.sha256(s.encode()).hexdigest()

def check(r, name, ok, detail=None):
    r["controls"].append({"name": name, "ok": bool(ok), "detail": detail})
    if not ok: r["failed"] += 1

def wait_file(path, proc=None, timeout=8):
    end=time.time()+timeout
    while time.time()<end:
        if Path(path).exists(): return
        if proc is not None and proc.poll() is not None: raise RuntimeError(f"process-exited-before-marker:{proc.returncode}")
        time.sleep(.02)
    raise TimeoutError(f"marker-timeout:{path}")

def launch(wdir,sock,ready,error,allow=True):
    for p in (sock,ready,error):
        if Path(p).exists(): Path(p).unlink()
    cmd=[sys.executable,str(TOOL),"serve",str(wdir),str(sock),"--ready-file",str(ready),"--error-file",str(error)]
    if allow: cmd.append("--allow-fault-injection")
    p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    wait_file(ready,p); return p,json.loads(Path(ready).read_text())

def stop(p,sock):
    if p is None: return
    if p.poll() is None:
        try: w.request(sock,{"op":"stop"},timeout=1)
        except Exception: pass
        try: p.wait(timeout=2)
        except subprocess.TimeoutExpired: p.kill(); p.wait(timeout=2)
    if Path(sock).exists(): Path(sock).unlink()

def kill(p):
    if p.poll() is None: os.kill(p.pid,signal.SIGKILL)
    p.wait(timeout=3)

def tx(sock,fp,local,a,t,decision="COMMIT",stable=True,reason="",fault=None,marker=None,after_witness=None,after_local=None):
    cmd=[sys.executable,str(TOOL),"transact",str(sock),fp,str(local),a,t,decision,"true" if stable else "false",reason]
    if fault: cmd += ["--fault",fault,"--fault-marker",str(marker)]
    if after_witness: cmd += ["--pause-after-witness",str(after_witness)]
    if after_local: cmd += ["--pause-after-local",str(after_local)]
    return subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)

def start_fail(wdir,sock,ready,error):
    for p in (sock,ready,error):
        if Path(p).exists(): Path(p).unlink()
    p=subprocess.Popen([sys.executable,str(TOOL),"serve",str(wdir),str(sock),"--ready-file",str(ready),"--error-file",str(error)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    end=time.time()+5
    while time.time()<end and p.poll() is None and not Path(error).exists() and not Path(ready).exists(): time.sleep(.02)
    if p.poll() is None: p.kill()
    p.wait(timeout=2)
    return Path(error).read_text().strip() if Path(error).exists() else f"exit={p.returncode};ready={Path(ready).exists()}"

def parallel_status(sock,fp,current,stale,a):
    code='import json,sys; import AXM_FLOWING_COMPUTE_PROCESS_WITNESS as w; print(json.dumps(w.status(sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4])))'
    env=dict(os.environ); env["PYTHONPATH"]=str(TOOL.parent)+(os.pathsep+env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    p1=subprocess.Popen([sys.executable,"-c",code,str(sock),fp,str(current),a],stdout=subprocess.PIPE,text=True,env=env)
    p2=subprocess.Popen([sys.executable,"-c",code,str(sock),fp,str(stale),a],stdout=subprocess.PIPE,text=True,env=env)
    return json.loads(p1.communicate(timeout=5)[0])["status"],json.loads(p2.communicate(timeout=5)[0])["status"]

def run():
    r={"wave":123,"title":"separate-process durable outcome witness","controls":[],"failed":0,
       "truth_boundary":["one Linux host/filesystem; fsync is not power-loss/device-finality proof","surviving client pin detects tested witness replacement; replacement of witness plus pin remains a counterexample","no network/provider independence, Byzantine consensus, performance, energy, retained/incremental/dormant-compute, or physical-finality claim"]}
    with tempfile.TemporaryDirectory(prefix="axm-wave123-") as td:
        b=Path(td); wd=b/"witness"; sock=b/"w.sock"; ready=b/"ready"; err=b/"error"; local=b/"local.jsonl"
        root=w.initialize_witness_dir(wd,"wave123-main"); fp=root["credential_fingerprint"]; wp=None
        try:
            wp,info=launch(wd,sock,ready,err); ping=w.request(sock,{"op":"ping"},fp)
            check(r,"witness_is_separate_os_process",ping["pid"]!=os.getpid(),{"test_pid":os.getpid(),"witness_pid":ping["pid"]})
            check(r,"pinned_credential_identity_matches",info["credential_fingerprint"]==fp==ping["credential_fingerprint"],fp)

            a,t=h("clean-a"),h("clean-t"); w.decide_and_publish(sock,fp,local,a,t,"COMMIT",True,""); s=w.status(sock,fp,local,a)
            check(r,"clean_commit_authoritative",s["status"]=="AUTHORITATIVE_PROCESS_WITNESS_COMMIT",s)
            led_prefix=(wd/"ledger.jsonl").read_bytes(); loc_prefix=local.read_bytes(); w.decide_and_publish(sock,fp,local,a,t,"COMMIT",True,"")
            check(r,"exact_retry_no_duplicate_ballast",(wd/"ledger.jsonl").read_bytes()==led_prefix and local.read_bytes()==loc_prefix)

            ah,th=h("hold-a"),h("hold-t"); reason="registry-evidence-temporarily-unavailable"; ps=w.proposal_sha(ah,th,"HOLD",False,reason)
            w.request(sock,{"op":"decide","authority_sha":ah,"transition_sha":th,"proposal_sha":ps,"decision":"HOLD","stable":False,"reason":reason},fp)
            sb=w.status(sock,fp,local,ah); w.decide_and_publish(sock,fp,local,ah,th,"COMMIT",True,""); sa=w.status(sock,fp,local,ah)
            check(r,"hold_is_retriable_not_terminal",sb["status"]=="HOLD_NO_TERMINAL_OUTCOME" and sa["status"]=="AUTHORITATIVE_PROCESS_WITNESS_COMMIT",{"before":sb,"after":sa})

            ar,tr=h("reject-a"),h("reject-t"); w.decide_and_publish(sock,fp,local,ar,tr,"REJECT",True,"stable-invalid-transition"); sr=w.status(sock,fp,local,ar); before=(wd/"ledger.jsonl").read_bytes(); conflict=None
            try: w.decide_and_publish(sock,fp,local,ar,tr,"COMMIT",True,"")
            except Exception as exc: conflict=str(exc)
            check(r,"stable_reject_blocks_conflicting_commit",sr["status"]=="REJECTED_PROCESS_WITNESS" and conflict is not None and (wd/"ledger.jsonl").read_bytes()==before,{"status":sr,"conflict":conflict})

            before=(wd/"ledger.jsonl").read_bytes(); errs=[]
            for d,stable,reason in (("REJECT",False,"bad"),("HOLD",True,"bad")):
                aa,tt=h(d+"-a"),h(d+"-t"); pp=w.proposal_sha(aa,tt,d,stable,reason)
                try: w.request(sock,{"op":"decide","authority_sha":aa,"transition_sha":tt,"proposal_sha":pp,"decision":d,"stable":stable,"reason":reason},fp)
                except Exception as exc: errs.append(str(exc))
            check(r,"invalid_outcome_semantics_fail_closed",len(errs)==2 and (wd/"ledger.jsonl").read_bytes()==before,errs)

            # SIGKILL witness before durable append.
            aa,tt=h("kill-witness-before-a"),h("kill-witness-before-t"); m=b/"before.marker"; p=tx(sock,fp,local,aa,tt,fault="pause_before_append",marker=m); wait_file(m,p); killed=wp.pid; kill(wp); wp=None; p.communicate(timeout=5)
            wp,info=launch(wd,sock,ready,err); sb=w.status(sock,fp,local,aa); w.decide_and_publish(sock,fp,local,aa,tt,"COMMIT",True,""); sa=w.status(sock,fp,local,aa)
            check(r,"sigkill_witness_before_append_is_retriable",sb["status"]=="HOLD_NO_TERMINAL_OUTCOME" and sa["status"]=="AUTHORITATIVE_PROCESS_WITNESS_COMMIT",{"killed_pid":killed,"before":sb,"after":sa})

            # SIGKILL witness after fsync but before response.
            aa,tt=h("kill-witness-after-a"),h("kill-witness-after-t"); pp=w.proposal_sha(aa,tt,"COMMIT",True,""); m=b/"after.marker"; p=tx(sock,fp,local,aa,tt,fault="pause_after_fsync",marker=m); wait_file(m,p); kill(wp); wp=None; p.communicate(timeout=5)
            wp,info=launch(wd,sock,ready,err); sb=w.status(sock,fp,local,aa); old=local.read_bytes(); wrong=None
            try: w.recover_exact(sock,fp,local,aa,tt,h("wrong-proposal"))
            except Exception as exc: wrong=str(exc)
            unchanged=local.read_bytes()==old; rec=w.recover_exact(sock,fp,local,aa,tt,pp); sa=w.status(sock,fp,local,aa)
            check(r,"sigkill_witness_after_fsync_preserves_newer_truth",sb["status"]=="HOLD_WITNESS_AHEAD" and wrong is not None and unchanged and rec["recovered"] and sa["status"]=="AUTHORITATIVE_PROCESS_WITNESS_COMMIT",{"before":sb,"wrong":wrong,"after":sa})

            # SIGKILL local after witness ack, before local append.
            aa,tt=h("kill-local-after-witness-a"),h("kill-local-after-witness-t"); pp=w.proposal_sha(aa,tt,"COMMIT",True,""); m=b/"client-w.marker"; p=tx(sock,fp,local,aa,tt,after_witness=m); wait_file(m,p); kill(p); sb=w.status(sock,fp,local,aa); w.recover_exact(sock,fp,local,aa,tt,pp); sa=w.status(sock,fp,local,aa)
            check(r,"sigkill_local_after_witness_ack_fails_closed_then_recovers",sb["status"]=="HOLD_WITNESS_AHEAD" and sa["status"]=="AUTHORITATIVE_PROCESS_WITNESS_COMMIT",{"before":sb,"after":sa})

            # SIGKILL local after its fsync.
            aa,tt=h("kill-local-after-local-a"),h("kill-local-after-local-t"); m=b/"client-l.marker"; p=tx(sock,fp,local,aa,tt,after_local=m); wait_file(m,p); kill(p); ss=w.status(sock,fp,local,aa)
            check(r,"sigkill_local_after_local_fsync_keeps_commit",ss["status"]=="AUTHORITATIVE_PROCESS_WITNESS_COMMIT",ss)

            # Roll local disk back while witness stays newer.
            aa,t1,t2=h("rollback-a"),h("rollback-t1"),h("rollback-t2"); w.decide_and_publish(sock,fp,local,aa,t1,"COMMIT",True,""); stale_bytes=local.read_bytes(); w.decide_and_publish(sock,fp,local,aa,t2,"COMMIT",True,""); current_bytes=local.read_bytes(); local.write_bytes(stale_bytes); rolled=w.status(sock,fp,local,aa); local.write_bytes(current_bytes)
            check(r,"complete_local_rollback_detected_by_newer_witness",rolled["status"]=="HOLD_WITNESS_AHEAD",rolled)
            stale=b/"stale.jsonl"; stale.write_bytes(stale_bytes); now,oldview=parallel_status(sock,fp,local,stale,aa)
            check(r,"simultaneous_new_and_stale_process_views_diverge_safely",now=="AUTHORITATIVE_PROCESS_WITNESS_COMMIT" and oldview=="HOLD_WITNESS_AHEAD",{"current":now,"stale":oldview})

            # Partition then reconnect.
            led=(wd/"ledger.jsonl").read_bytes(); stop(wp,sock); wp=None; sp=w.status(sock,fp,local,a); wp,info=launch(wd,sock,ready,err); sc=w.status(sock,fp,local,a)
            check(r,"partition_fails_closed_and_reconnects",sp["status"]=="HOLD_WITNESS_UNAVAILABLE" and sc["status"]=="AUTHORITATIVE_PROCESS_WITNESS_COMMIT" and (wd/"ledger.jsonl").read_bytes()==led,{"partitioned":sp,"reconnected":sc})

            # Truncation/corruption fail startup.
            stop(wp,sock); wp=None; lp=wd/"ledger.jsonl"; good=lp.read_bytes(); lp.write_bytes(good[:-1]); te=start_fail(wd,sock,ready,err); lp.write_bytes(good); bad=bytearray(good); i=good.find(b'"decision":"COMMIT"');
            if i>=0: bad[i+len(b'"decision":"')]=ord('X')
            lp.write_bytes(bytes(bad)); ce=start_fail(wd,sock,ready,err); lp.write_bytes(good); wp,info=launch(wd,sock,ready,err)
            check(r,"witness_truncation_and_corruption_fail_startup","ledger-truncated-tail" in te and ("signature" in ce or "unknown" in ce),{"truncation":te,"corruption":ce})

            # Replace entire witness store/credential, but keep old client pin.
            stop(wp,sock); wp=None; original=b/"witness-original"; wd.rename(original); fresh=w.initialize_witness_dir(wd,"substitute"); fw,fi=launch(wd,sock,ready,err); sub=w.status(sock,fp,local,a); stop(fw,sock); shutil.rmtree(wd); original.rename(wd); wp,info=launch(wd,sock,ready,err); restored=w.status(sock,fp,local,a)
            check(r,"whole_witness_substitution_rejected_by_surviving_pin",fresh["credential_fingerprint"]!=fp and sub["status"]=="HOLD_WITNESS_CREDENTIAL_MISMATCH" and restored["status"]=="AUTHORITATIVE_PROCESS_WITNESS_COMMIT",{"substituted":sub,"restored":restored})

            # Local journal tamper.
            tamp=b/"tampered.jsonl"; tb=bytearray(local.read_bytes()); i=tb.find(b'"decision":"COMMIT"');
            if i>=0: tb[i+len(b'"decision":"')]=ord('X')
            tamp.write_bytes(bytes(tb)); ts=w.status(sock,fp,tamp,a)
            check(r,"local_journal_tamper_fails_closed",ts["status"]=="HOLD_LOCAL_CORRUPT",ts)
            check(r,"witness_ledger_kept_original_append_only_prefix",(wd/"ledger.jsonl").read_bytes().startswith(led_prefix))

            # Deliberately preserve whole-domain rollback counterexample.
            aa,t1,t2=h("whole-a"),h("whole-t1"),h("whole-t2"); w.decide_and_publish(sock,fp,local,aa,t1,"COMMIT",True,""); old_ledger=(wd/"ledger.jsonl").read_bytes(); old_local=local.read_bytes(); w.decide_and_publish(sock,fp,local,aa,t2,"COMMIT",True,""); newer=w.status(sock,fp,local,aa); stop(wp,sock); wp=None; (wd/"ledger.jsonl").write_bytes(old_ledger); local.write_bytes(old_local); wp,info=launch(wd,sock,ready,err); both=w.status(sock,fp,local,aa)
            check(r,"counterexample_whole_domain_rollback_still_accepts_older_genuine_prefix",newer["status"]=="AUTHORITATIVE_PROCESS_WITNESS_COMMIT" and both["status"]=="AUTHORITATIVE_PROCESS_WITNESS_COMMIT" and both["witness_record"]["transition_sha"]==t1,{"newer_transition":t2,"rolled_transition":both.get("witness_record",{}).get("transition_sha")})
        finally: stop(wp,sock)
    r["passed"]=len(r["controls"])-r["failed"]; return r

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--json-out"); ns=ap.parse_args(); r=run(); text=json.dumps(r,indent=2,sort_keys=True)+"\n"
    if ns.json_out: Path(ns.json_out).write_text(text)
    print(text,end=""); return 1 if r["failed"] else 0

if __name__=="__main__": raise SystemExit(main())
