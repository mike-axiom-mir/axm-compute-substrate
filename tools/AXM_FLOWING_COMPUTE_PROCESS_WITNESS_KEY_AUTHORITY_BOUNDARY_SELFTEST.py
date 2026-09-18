#!/usr/bin/env python3
"""Wave 130 adversarial self-test for the durable response-key uid boundary.

Runs under root only so the harness can create two numeric Unix identities, then
executes the adversary as the ordinary worker uid and the real anchor as a
separate service uid. Root is test orchestration, not part of the claimed
attacker boundary.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS as w
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_AUTHENTICATED_ANCHOR as protocol

SCRIPT = Path(__file__).resolve()
TOOLS = SCRIPT.parent
W129 = TOOLS / "AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_LIFECYCLE.py"
W130 = TOOLS / "AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_AUTHORITY_BOUNDARY.py"
PRIVATE_KEY = "response_private.pem"
WITNESS_PUBLIC_KEY = "anchor_response_public.pem"
ENV_UID = "AXM_W130_FORBIDDEN_WORKER_UID"


def pycmd(*args: str) -> list[str]:
    out = [sys.executable]
    if sys.flags.optimize:
        out.append("-O")
    return [*out, *args]


def demote(uid: int):
    def _drop() -> None:
        os.setgroups([])
        os.setgid(uid)
        os.setuid(uid)
    return _drop


def base_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(TOOLS)
    env["HOME"] = "/tmp"
    if extra:
        env.update(extra)
    return env


def run_as(uid: int, args: list[str], *, env: dict[str, str] | None = None,
           check: bool = True, timeout: float = 30.0) -> subprocess.CompletedProcess:
    cp = subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=timeout,
        env=env or base_env(),
        preexec_fn=demote(uid),
    )
    if check and cp.returncode != 0:
        raise RuntimeError(
            f"child-failed:{uid}:{cp.returncode}:{args}:{cp.stdout}:{cp.stderr}"
        )
    return cp


def popen_as(uid: int, args: list[str], *, env: dict[str, str]) -> subprocess.Popen:
    return subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        preexec_fn=demote(uid),
    )


def wait_file(path: Path, proc: subprocess.Popen | None = None,
              timeout: float = 12.0) -> None:
    end = time.time() + timeout
    while time.time() < end:
        if path.exists() and path.stat().st_size:
            return
        if proc is not None and proc.poll() is not None:
            out, err = proc.communicate()
            raise RuntimeError(
                f"process-exited-before-ready:{proc.returncode}:{out}:{err}"
            )
        time.sleep(0.02)
    raise TimeoutError(f"marker-timeout:{path}")


def chown_tree(path: Path, uid: int, gid: int) -> None:
    for root, dirs, files in os.walk(path):
        os.chown(root, uid, gid)
        for name in dirs:
            os.chown(Path(root) / name, uid, gid)
        for name in files:
            os.chown(Path(root) / name, uid, gid)


def child_read_key(private_path: Path, public_path: Path) -> int:
    try:
        private = private_path.read_bytes()
    except BaseException as exc:
        print(json.dumps({
            "readable": False,
            "error": f"{type(exc).__name__}:{exc}",
            "uid": os.getuid(), "euid": os.geteuid(),
        }, sort_keys=True))
        return 0
    cp = subprocess.run(
        ["openssl", "pkey", "-pubout"], input=private,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    derived = cp.stdout if cp.returncode == 0 else b""
    public = public_path.read_bytes()
    print(json.dumps({
        "readable": True,
        "private_bytes": len(private),
        "derived_public_matches": derived == public,
        "uid": os.getuid(), "euid": os.geteuid(),
    }, sort_keys=True))
    return 0


def child_proc_probe(pid: int) -> int:
    out = {
        "uid": os.getuid(), "euid": os.geteuid(),
        "mem_open": False, "readable_fd_count": 0, "errors": [],
    }
    try:
        fd = os.open(f"/proc/{pid}/mem", os.O_RDONLY)
    except BaseException as exc:
        out["errors"].append(f"mem:{type(exc).__name__}:{exc}")
    else:
        out["mem_open"] = True
        os.close(fd)
    try:
        names = os.listdir(f"/proc/{pid}/fd")
    except BaseException as exc:
        out["errors"].append(f"fd-list:{type(exc).__name__}:{exc}")
    else:
        for name in names:
            try:
                fd = os.open(f"/proc/{pid}/fd/{name}", os.O_RDONLY)
            except BaseException:
                continue
            else:
                out["readable_fd_count"] += 1
                os.close(fd)
    print(json.dumps(out, sort_keys=True))
    return 0


def child_ping(socket_path: Path, anchor_fp: str, public_path: Path) -> int:
    try:
        body = protocol.anchor_request(
            socket_path, {"op": "ping"}, anchor_fp, public_path, timeout=4.0
        )
        print(json.dumps({"ok": True, "body": body}, sort_keys=True))
        return 0
    except BaseException as exc:
        print(json.dumps({
            "ok": False, "error": f"{type(exc).__name__}:{exc}"
        }, sort_keys=True))
        return 3


def child_unlink(path: Path) -> int:
    try:
        path.unlink()
        print(json.dumps({"ok": True}, sort_keys=True))
        return 0
    except BaseException as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}:{exc}"}))
        return 2


def child_fake_server(socket_path: Path, ready_path: Path) -> int:
    import socket
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        s.bind(str(socket_path))
        os.chmod(socket_path, 0o777)
        ready_path.write_text("ready\n")
        s.listen(1)
        conn, _ = s.accept()
        with conn:
            data = b""
            while not data.endswith(b"\n"):
                chunk = conn.recv(65536)
                if not chunk:
                    break
                data += chunk
            # Deliberately unsigned. The public identity string alone must not
            # be enough to impersonate the anchor.
            conn.sendall(w.canonical({
                "schema": protocol.RESPONSE_SCHEMA,
                "body": {"ok": True, "fake": True},
            }) + b"\n")
        return 0
    finally:
        s.close()
        try:
            socket_path.unlink()
        except FileNotFoundError:
            pass


def parse_json_line(cp: subprocess.CompletedProcess) -> dict:
    text = cp.stdout.strip().splitlines()
    if not text:
        raise RuntimeError(f"missing-json-output:{cp.stderr}")
    return json.loads(text[-1])


def start_anchor(uid: int, anchor_dir: Path, socket_path: Path, ready: Path,
                 error: Path, worker_uid: int) -> subprocess.Popen:
    for p in (socket_path, ready, error):
        try:
            p.unlink()
        except FileNotFoundError:
            pass
    env = base_env({ENV_UID: str(worker_uid)})
    proc = popen_as(uid, pycmd(
        str(W130), "serve-anchor", str(anchor_dir), str(socket_path),
        "--ready-file", str(ready), "--error-file", str(error),
    ), env=env)
    wait_file(ready, proc)
    os.chmod(socket_path, 0o777)
    return proc


def run_suite(worker_uid: int, anchor_uid: int, report_path: Path | None) -> int:
    if os.gete²È="25}%5=¡Á­}ÍÐ¹ÍÑ}µ½‘”¤€ôô€Á¼ØÀÀ(€€€€€€€€€€€…¹¥¹¥Ñl‰Ý…Ù”ÄÌÁ}‘ÕÉ…‰±•}­•å}‰½Õ¹‘…Éä‰ul‰™½É‰¥‘‘•¹}Ý½É­•É}Õ¥‰t€ôôÝ½É­•É}Õ¥(€€€€€€€€¤(€€€€€€€É•ÍÕ±ÑÌ¹…ÁÁ•¹¡ì‰¹…µ”ˆè€‰‘•‘¥…Ñ•‘}Õ¥‘}ÁÉ¥Ù…Ñ•}ÍÑ½É•}‰½Õ¹‘…Éäˆ°€‰½¬ˆè‰½Õ¹‘…Éå}½¬°(€€€€€€€€€€€€€€€€€€€€€€€€‰‘•Ñ…¥°ˆè¥¹¥Ñl‰Ý…Ù”ÄÌÁ}‘ÕÉ…‰±•}­•å}‰½Õ¹‘…Éä‰uô¤((€€€€€€€™¥á•‘}É•…€ôÁ…ÉÍ•}©Í½¹}±¥¹”¡ÉÕ¹}…Ì¡Ý½É­•É}Õ¥°Áåµ (€€€€€€€€€€€ÍÑÈ¡MI%AP¤°€ˆ´µ¡¥±µÉ•…µ­•äˆ°(€€€€€€€€€€€ÍÑÈ¡™¥á•€¼€‰…¹¡½Èˆ€¼AI%YQ}-d¤°(€€€€€€€€€€€ÍÑÈ¡™¥á•€¼€‰Ý¥Ñ¹•ÍÌˆ€¼]%Q9MM}AU	1%}-d¤°(€€€€€€€€¤¤¤(€€€€€€€É•ÍÕ±ÑÌ¹…ÁÁ•¹¡ì‰¹…µ”ˆè€‰Ý½É­•É}‘¥É•Ñ}ÁÉ¥Ù…Ñ•}­•å}É•…‘}‘•¹¥•ˆ°(€€€€€€€€€€€€€€€€€€€€€€€€‰½¬ˆè¹½Ð™¥á•‘}É•…¹•Ð ‰É•…‘…‰±”ˆ°QÉÕ”¤°€‰‘•Ñ…¥°ˆè™¥á•‘}É•…‘ô¤((€€€€€€€ÉÕ¹}‘¥È€ô™¥á•€¼€‰ÉÕ¸ˆ(€€€€€€€ÉÕ¹}‘¥È¹µ­‘¥È¡µ½‘”ôÁ¼ÜÜÜ¤(€€€€€€€½Ì¹¡µ½¡ÉÕ¹}‘¥È°€Á¼ÜÜÜ¤(€€€€€€€Í½­•Ñ}Á…Ñ €ôÉÕ¹}‘¥È€¼€‰…¹¡½È¹Í½¬ˆ(€€€€€€€É•…‘ä€ôÉÕ¹}‘¥È€¼€‰…¹¡½È¹É•…‘äˆ(€€€€€€€•ÉÉ½È€ôÉÕ¹}‘¥È€¼€‰…¹¡½È¹•ÉÉ½Èˆ(€€€€€€€…¹¡½É}ÁÉ½Œ€ôÍÑ…ÉÑ}…¹¡½È (€€€€€€€€€€€…¹¡½É}Õ¥°™¥á•€¼€‰…¹¡½Èˆ°Í½­•Ñ}Á…Ñ °É•…‘ä°•ÉÉ½È°Ý½É­•É}Õ¥(€€€€€€€€¤((€€€€€€€ÁÉ½}ÁÉ½‰”€ôÁ…ÉÍ•}©Í½¹}±¥¹”¡ÉÕ¹}…Ì¡Ý½É­•É}Õ¥°Áåµ (€€€€€€€€€€€ÍÑÈ¡MI%AP¤°€ˆ´µ¡¥±µÁÉ½ŒµÁÉ½‰”ˆ°ÍÑÈ¡…¹¡½É}ÁÉ½Œ¹Á¥¤(€€€€€€€€¤¤¤(€€€€€€€ÁÉ½}½¬€ô¹½ÐÁÉ½}ÁÉ½‰”¹•Ð ‰µ•µ}½Á•¸ˆ¤…¹ÁÉ½}ÁÉ½‰”¹•Ð ‰É•…‘…‰±•}™‘}½Õ¹Ðˆ¤€ôô€À(€€€€€€€É•ÍÕ±ÑÌ¹…ÁÁ•¹¡ì‰¹…µ”ˆè€‰Ý½É­•É}ÁÉ½}Í•É•Ñ}Á…Ñ¡Í}‘•¹¥•ˆ°€‰½¬ˆèÁÉ½}½¬°(€€€€€€€€€€€€€€€€€€€€€€€€‰‘•Ñ…¥°ˆèÁÉ½}ÁÉ½‰•ô¤((€€€€€€€…¹¡½É}™À€ô¥¹¥Ñl‰…¹¡½É}É•‘•¹Ñ¥…±}™¥¹•ÉÁÉ¥¹Ð‰t(€€€€€€€ÁÕ‰±¥}Á…Ñ €ô™¥á•€¼€‰Ý¥Ñ¹•ÍÌˆ€¼]%Q9MM}AU	1%}-d(€€€€€€€Á¥¹œ€ôÁ…ÉÍ•}©Í½¹}±¥¹”¡ÉÕ¹}…Ì¡Ý½É­•É}Õ¥°Áåµ (€€€€€€€€€€€ÍÑÈ¡MI%AP¤°€ˆ´µ¡¥±µÁ¥¹œˆ°ÍÑÈ¡Í½­•Ñ}Á…Ñ ¤°…¹¡½É}™À°ÍÑÈ¡ÁÕ‰±¥}Á…Ñ ¤(€€€€€€€€¤¤¤(€€€€€€€É•ÍÕ±ÑÌ¹…ÁÁ•¹¡ì‰¹…µ”ˆè€‰Ý½É­•É}…¹}ÕÍ•}…ÕÑ¡•¹Ñ¥…Ñ•‘}…¹¡½É}Ý¥Ñ¡½ÕÑ}­•äˆ°€‰½¬ˆèÁ¥¹œ¹•Ð ‰½¬ˆ¤¥ÌQÉÕ”°(€€€€€€€€€€€€€€€€€€€€€€€€‰‘•Ñ…¥°ˆèÁ¥¹ô¤((€€€€€€€€ŒQ¡”Ý½É­•È…¸É•Á±…”Ñ¡”Á…Ñ¡¹…µ”¥¸„‘•±¥‰•É…Ñ•±äÍ¡…É•Í½­•Ð(€€€€€€€€Œ‘¥É•Ñ½Éä°‰ÕÐÍÑ¥±°…¹¹½Ð™½É”Ñ¡”Í¥¹•…¹¡½ÈÉ•ÍÁ½¹Í”¸(€€€€€€€ÉÕ¹}…Ì¡Ý½É­•É}Õ¥°Áåµ¡ÍÑÈ¡MI%AP¤°€ˆ´µ¡¥±µÕ¹±¥¹¬ˆ°ÍÑÈ¡Í½­•Ñ}Á…Ñ ¤¤¤(€€€€€€€™…­•}É•…‘ä€ôÉÕ¹}‘¥È€¼€‰™…­”¹É•…‘äˆ(€€€€€€€™…­•}ÁÉ½Œ€ôÁ½Á•¹}…Ì¡Ý½É­•É}Õ¥°Áåµ (€€€€€€€€€€€ÍÑÈ¡MI%AP¤°€ˆ´µ¡¥±µ™…­”µÍ•ÉÙ•Èˆ°ÍÑÈ¡Í½­•Ñ}Á…Ñ ¤°ÍÑÈ¡™…­•}É•…‘ä¤(€€€€€€€€¤°•¹Øõ‰…Í•}•¹Ø ¤¤(€€€€€€€Ý…¥Ñ}™¥±”¡™…­•}É•…‘ä°™…­•}ÁÉ½Œ¤(€€€€€€€™…­•}Á¥¹}À€ôÉÕ¹}…Ì¡Ý½É­•É}Õ¥°Áåµ (€€€€€€€€€€€ÍÑÈ¡MI%AP¤°€ˆ´µ¡¥±µÁ¥¹œˆ°ÍÑÈ¡Í½­•Ñ}Á…Ñ ¤°…¹¡½É}™À°ÍÑÈ¡ÁÕ‰±¥}Á…Ñ ¤(€€€€€€€€¤°¡•¬õ…±Í”¤(€€€€€€€™…­•}Á¥¹œ€ôÁ…ÉÍ•}©Í½¹}±¥¹”¡™…­•}Á¥¹}À¤(€€€€€€€¥˜™…­•}ÁÉ½Œ¹Á½±° ¤¥Ì9½¹”è(€€€€€€€€€€€™…­•}ÁÉ½Œ¹Ý…¥Ð¡Ñ¥µ•½ÕÐôÌ¤(€€€€€€€™…­•}ÁÉ½Œ€ô9½¹”(€€€€€€€É•ÍÕ±ÑÌ¹…ÁÁ•¹¡ì‰¹…µ”ˆè€‰Ý½É­•É}Í½­•Ñ}ÍÕ‰ÍÑ¥ÑÕÑ¥½¹}ÍÑ¥±±}É•©•Ñ•ˆ°(€€€€€€€€€€€€€€€€€€€€€€€€‰½¬ˆè™…­•}Á¥¹}À¹É•ÑÕÉ¹½‘”€„ô€À…¹™…­•}Á¥¹œ¹•Ð ‰½¬ˆ¤¥Ì…±Í”°(€€€€€€€€€€€€€€€€€€€€€€€€‰‘•Ñ…¥°ˆè™…­•}Á¥¹ô¤((€€€€€€€½Ì¹­¥±°¡…¹¡½É}ÁÉ½Œ¹Á¥°Í¥¹…°¹M%-%10¤(€€€€€€€…¹¡½É}ÁÉ½Œ¹Ý…¥Ð¡Ñ¥µ•½ÕÐôÌ¤(€€€€€€€…¹¡½É}ÁÉ½Œ€ô9½¹”(€€€€€€€É•ÍÑ…ÉÑ}É•…‘ä€ôÉÕ¹}‘¥È€¼€‰…¹¡½È¹É•ÍÑ…ÉÐ¹É•…‘äˆ(€€€€€€€É•ÍÑ…ÉÑ}•ÉÉ½È€ôÉÕ¹}‘¥È€¼€‰…¹¡½È¹É•ÍÑ…ÉÐ¹•ÉÉ½Èˆ(€€€€€€€…¹¡½É}ÁÉ½Œ€ôÍÑ…ÉÑ}…¹¡½È (€€€€€€€€€€€…¹¡½É}Õ¥°™¥á•€¼€‰…¹¡½Èˆ°Í½­•Ñ}Á…Ñ °É•ÍÑ…ÉÑ}É•…‘ä°(€€€€€€€€€€€É•ÍÑ…ÉÑ}•ÉÉ½È°Ý½É­•É}Õ¥(€€€€€€€€¤(€€€€€€€É•ÍÑ…ÉÑ}Á¥¹œ€ôÁ…ÉÍ•}©Í½¹}±¥¹”¡ÉÕ¹}…Ì¡Ý½É­•É}Õ¥°Áåµ (€€€€€€€€€€€ÍÑÈ¡MI%AP¤°€ˆ´µ¡¥±µÁ¥¹œˆ°ÍÑÈ¡Í½­•Ñ}Á…Ñ ¤°…¹¡½É}™À°ÍÑÈ¡ÁÕ‰±¥}Á…Ñ ¤(€€€€€€€€¤¤¤(€€€€€€€Í…µ•}¥‘•¹Ñ¥Ñä€ô€ (€€€€€€€€€€€É•ÍÑ…ÉÑ}Á¥¹œ¹•Ð ‰½¬ˆ¤¥ÌQÉÕ”(€€€€€€€€€€€…¹É•ÍÑ…ÉÑ}Á¥¹œ¹•Ð ‰‰½‘äˆ°íô¤¹•Ð ‰…¹¡½É}É•‘•¹Ñ¥…±}™¥¹•ÉÁÉ¥¹Ðˆ¤€ôô…¹¡½É}™À(€€€€€€€€€€€…¹É•ÍÑ…ÉÑ}Á¥¹œ¹•Ð ‰‰½‘äˆ°íô¤¹•Ð ‰É•ÍÁ½¹Í•}ÁÕ‰±¥}™¥¹•ÉÁÉ¥¹Ðˆ¤(€€€€€€€€€€€€€€€€ôô¥¹¥Ð¹•Ð ‰É•ÍÁ½¹Í•}ÁÕ‰±¥}™¥¹•ÉÁÉ¥¹Ðˆ¤(€€€€€€€€¤(€€€€€€€É•ÍÕ±ÑÌ¹…ÁÁ•¹¡ì‰¹…µ”ˆè€‰Í¥­¥±±}É•ÍÑ…ÉÑ}ÁÉ•Í•ÉÙ•Í}•á…Ñ}…¹¡½É}¥‘•¹Ñ¥Ñäˆ°(€€€€€€€€€€€€€€€€€€€€€€€€‰½¬ˆèÍ…µ•}¥‘•¹Ñ¥Ñä°€‰‘•Ñ…¥°ˆèÉ•ÍÑ…ÉÑ}Á¥¹ô¤((€€€€€€€€Œ…¥°±½Í•‰•™½É”­•ä•¹•É…Ñ¥½¸¥˜Í½µ•½¹”ÑÉ¥•ÌÑ¼½±±…ÁÍ”Ñ¡”(€€€€€€€€Œ…ÕÑ¡½É¥Ñä…¹Ý½É­•È‰…¬½¹Ñ¼Ñ¡”Í…µ”Õ¥¸(€€€€€€€‰…€ô‰…Í”€¼€‰Í…µ”µÕ¥µÉ•™ÕÍ…°ˆ(€€€€€€€‰…¹µ­‘¥È¡µ½‘”ôÁ¼ÜÜÜ¤(€€€€€€€½Ì¹¡µ½¡‰…°€Á¼ÜÜÜ¤(€€€€€€€ÉÕ¹}…Ì¡Ý½É­•É}Õ¥°Áåµ¡ÍÑÈ¡\ÄÌÀ¤°€‰¥¹¥ÐµÝ¥Ñ¹•ÍÌˆ°ÍÑÈ¡‰…€¼€‰Ý¥Ñ¹•ÍÌˆ¤¤°(€€€€€€€€€€€€€€•¹Øõ‰…Í•}•¹Ø¡í9Y}U%èÍÑÈ¡Ý½É­•É}Õ¥¥ô¤¤(€€€€€€€‰…‘}À€ôÉÕ¹}…Ì¡Ý½É­•É}Õ¥°Áåµ (€€€€€€€€€€€ÍÑÈ¡\ÄÌÀ¤°€‰¥¹¥Ðµ…¹¡½Èˆ°ÍÑÈ¡‰…€¼€‰…¹¡½Èˆ¤°ÍÑÈ¡‰…€¼€‰Ý¥Ñ¹•ÍÌˆ¤(€€€€€€€€¤°•¹Øõ‰…Í•}•¹Ø¡í9Y}U%èÍÑÈ¡Ý½É­•É}Õ¥¥ô¤°¡•¬õ…±Í”¤(€€€€€€€¹½}ÁÉ¥Ù…Ñ”€ô¹½Ð€¡‰…€¼€‰…¹¡½Èˆ€¼AI%YQ}-d¤¹•á¥ÍÑÌ ¤(€€€€€€€É•ÍÕ±ÑÌ¹…ÁÁ•¹¡ì‰¹…µ”ˆè€‰Í…µ•}Õ¥‘}…ÕÑ¡½É¥Ñå}½¹™¥ÕÉ…Ñ¥½¹}™…¥±Í}‰•™½É•}­•å}•¹•É…Ñ¥½¸ˆ°(€€€€€€€€€€€€€€€€€€€€€€€€‰½¬ˆè‰…‘}À¹É•ÑÕÉ¹½‘”€„ô€À…¹¹½}ÁÉ¥Ù…Ñ”°(€€€€€€€€€€€€€€€€€€€€€€€€‰‘•Ñ…¥°ˆèì‰É•ÑÕÉ¹½‘”ˆè‰…‘}À¹É•ÑÕÉ¹½‘”°(€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€‰ÍÑ‘•ÉÉ}Ñ…¥°ˆè‰…‘}À¹ÍÑ‘•ÉÉl´ÔÀÀét°(€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€€‰ÁÉ¥Ù…Ñ•}•á¥ÍÑÌˆè¹½Ð¹½}ÁÉ¥Ù…Ñ•õô¤((€€€€€€€Á…ÍÍ•€ôÍÕ´ Ä™½ÈÈ¥¸É•ÍÕ±ÑÌ¥˜Él‰½¬‰t¤(€€€€€€€É•Á½ÉÐ€ôì(€€€€€€€€€€€€‰Í¡•µ„ˆè€‰…á´¹™±½Ý¥¹œµ½µÁÕÑ”¹Ý…Ù”ÄÌÀµ‘•‘¥…Ñ•µÕ¥µ‰½Õ¹‘…ÉäµÍ•±™Ñ•ÍÐ¹ØÄˆ°(€€€€€€€€€€€€‰µ½‘”ˆè€‰½ÁÑ¥µ¥é•ˆ¥˜ÍåÌ¹™±…Ì¹½ÁÑ¥µ¥é”•±Í”€‰¹½Éµ…°ˆ°(€€€€€€€€€€€€‰Ý½É­•É}Õ¥ˆèÝ½É­•É}Õ¥°(€€€€€€€€€€€€‰…¹¡½É}Õ¥ˆè…¹¡½É}Õ¥°(€€€€€€€€€€€€‰Á…ÍÍ•ˆèÁ…ÍÍ•°(€€€€€€€€€€€€‰Ñ½Ñ…°ˆè±•¸¡É•ÍÕ±ÑÌ¤°(€€€€€€€€€€€€‰É•ÍÕ±ÑÌˆèÉ•ÍÕ±ÑÌ°(€€€€€€€€€€€€‰ÑÉÕÑ¡}‰½Õ¹‘…Éäˆè€ (€€€€€€€€€€€€€€€€‰Ñ•ÍÑ•U¹¥àÕ¥½ÁÉ½•ÍÌ¥Í½±…Ñ¥½¸½¹±äìÉ½½Ð½­•É¹•°°…¹¡½ÈµÕ¥½µÁÉ½µ¥Í”°€ˆ(€€€€€€€€€€€€€€€€‰É½ÍÌµ¡½ÍÐ½Á¥•­•åÌ°¥¹Ñ•ÉÉÕÁÑ•µ¥¹¥ÐÉ•½Ù•Éä°É½Ñ…Ñ¥½¸°¡…É‘Ý…É”ÕÍÑ½‘ä°€ˆ(€€€€€€€€€€€€€€€€‰Á•É™½Éµ…¹”…¹Á¡åÍ¥…°½ÁÉ½Ù¥‘•È™¥¹…±¥ÑäÉ•µ…¥¸Õ¹ÁÉ½Ù•ˆ(€€€€€€€€€€€€¤°(€€€€€€€ô(€€€€€€€¥˜É•Á½ÉÑ}Á…Ñ è(€€€€€€€€€€€É•Á½ÉÑ}Á…Ñ ¹Á…É•¹Ð¹µ­‘¥È¡Á…É•¹ÑÌõQÉÕ”°•á¥ÍÑ}½¬õQÉÕ”¤(€€€€€€€€€€€É•Á½ÉÑ}Á…Ñ ¹ÝÉ¥Ñ•}Ñ•áÐ¡©Í½¸¹‘ÕµÁÌ¡É•Á½ÉÐ°¥¹‘•¹ÐôÈ°Í½ÉÑ}­•åÌõQÉÕ”¤€¬€‰q¸ˆ¤(€€€€€€€ÁÉ¥¹Ð¡©Í½¸¹‘ÕµÁÌ¡É•Á½ÉÐ°Í½ÉÑ}­•åÌõQÉÕ”¤¤(€€€€€€€É•ÑÕÉ¸€À¥˜Á…ÍÍ•€ôô±•¸¡É•ÍÕ±ÑÌ¤•±Í”€Ä(€€€™¥¹…±±äè(€€€€€€€™½ÈÁÉ½Œ¥¸€¡™…­•}ÁÉ½Œ°…¹¡½É}ÁÉ½Œ¤è(€€€€€€€€€€€¥˜ÁÉ½Œ¥Ì¹½Ð9½¹”…¹ÁÉ½Œ¹Á½±° ¤¥Ì9½¹”è(€€€€€€€€€€€€€€€ÑÉäè(€€€€€€€€€€€€€€€€€€€½Ì¹­¥±°¡ÁÉ½Œ¹Á¥°Í¥¹…°¹M%-%10¤(€€€€€€€€€€€€€€€•á•ÁÐAÉ½•ÍÍ1½½­ÕÁÉÉ½Èè(€€€€€€€€€€€€€€€€€€€Á…ÍÌ(€€€€€€€€€€€€€€€ÑÉäè(€€€€€€€€€€€€€€€€€€€ÁÉ½Œ¹Ý…¥Ð¡Ñ¥µ•½ÕÐôÌ¤(€€€€€€€€€€€€€€€•á•ÁÐá•ÁÑ¥½¸è(€€€€€€€€€€€€€€€€€€€Á…ÍÌ(€€€€€€€Í¡ÕÑ¥°¹ÉµÑÉ•”¡‰…Í”°¥¹½É•}•ÉÉ½ÉÌõQÉÕ”¤(()‘•˜µ…¥¸ ¤€´ø¥¹Ðè(€€€…À€ô…ÉÁ…ÉÍ”¹ÉÕµ•¹ÑA…ÉÍ•È ¤(€€€…À¹…‘‘}…ÉÕµ•¹Ð ˆ´µÝ½É­•ÈµÕ¥ˆ°ÑåÁ”õ¥¹Ð¤(€€€…À¹…‘‘}…ÉÕµ•¹Ð ˆ´µ…¹¡½ÈµÕ¥ˆ°ÑåÁ”õ¥¹Ð°‘•™…Õ±ÐôÈÌÀÀÄ¤(€€€…À¹…‘‘}…ÉÕµ•¹Ð ˆ´µÉ•Á½ÉÐˆ°ÑåÁ”õA…Ñ ¤(€€€…À¹…‘‘}…ÉÕµ•¹Ð ˆ´µ¡¥±µÉ•…µ­•äˆ°¹…ÉÌôÈ¤(€€€…À¹…‘‘}…ÉÕµ•¹Ð ˆ´µ¡¥±µÁÉ½ŒµÁÉ½‰”ˆ°ÑåÁ”õ¥¹Ð¤(€€€…À¹…‘‘}…ÉÕµ•¹Ð ˆ´µ¡¥±µÁ¥¹œˆ°¹…ÉÌôÌ¤(€€€…À¹…‘‘}…ÉÕµ•¹Ð ˆ´µ¡¥±µÕ¹±¥¹¬ˆ¤(€€€…À¹…‘‘}…ÉÕµ•¹Ð ˆ´µ¡¥±µ™…­”µÍ•ÉÙ•Èˆ°¹…ÉÌôÈ¤(€€€¹Ì€ô…À¹Á…ÉÍ•}…ÉÌ ¤(€€€¥˜¹Ì¹¡¥±‘}É•…‘}­•äè(€€€€€€€É•ÑÕÉ¸¡¥±‘}É•…‘}­•ä¡A…Ñ ¡¹Ì¹¡¥±‘}É•…‘}­•ålÁt¤°A…Ñ ¡¹Ì¹¡¥±‘}É•…‘}­•ålÅt¤¤(€€€¥˜¹Ì¹¡¥±‘}ÁÉ½}ÁÉ½‰”¥Ì¹½Ð9½¹”è(€€€€€€€É•ÑÕÉ¸¡¥±‘}ÁÉ½}ÁÉ½‰”¡¹Ì¹¡¥±‘}ÁÉ½}ÁÉ½‰”¤(€€€¥˜¹Ì¹¡¥±‘}Á¥¹œè(€€€€€€€É•ÑÕÉ¸¡¥±‘}Á¥¹œ¡A…Ñ ¡¹Ì¹¡¥±‘}Á¥¹lÁt¤°¹Ì¹¡¥±‘}Á¥¹lÅt°A…Ñ ¡¹Ì¹¡¥±‘}Á¥¹lÉt¤¤(€€€¥˜¹Ì¹¡¥±‘}Õ¹±¥¹¬è(€€€€€€€É•ÑÕÉ¸¡¥±‘}Õ¹±¥¹¬¡A…Ñ ¡¹Ì¹¡¥±‘}Õ¹±¥¹¬¤¤(€€€¥˜¹Ì¹¡¥±‘}™…­•}Í•ÉÙ•Èè(€€€€€€€É•ÑÕÉ¸¡¥±‘}™…­•}Í•ÉÙ•È¡A…Ñ ¡¹Ì¹¡¥±‘}™…­•}Í•ÉÙ•ÉlÁt¤°A…Ñ ¡¹Ì¹¡¥±‘}™…­•}Í•ÉÙ•ÉlÅt¤¤(€€€Ý½É­•É}Õ¥€ô¹Ì¹Ý½É­•É}Õ¥(€€€¥˜Ý½É­•É}Õ¥¥Ì9½¹”è(€€€€€€€É…¥Í”Y…±Õ•ÉÉ½È ˆ´µÝ½É­•ÈµÕ¥µÉ•ÅÕ¥É•ˆ¤(€€€É•ÑÕÉ¸ÉÕ¹}ÍÕ¥Ñ”¡Ý½É­•É}Õ¥°¹Ì¹…¹¡½É}Õ¥°¹Ì¹É•Á½ÉÐ¤(()¥˜}}¹…µ•}|€ôô€‰}}µ…¥¹}|ˆè(€€€É…¥Í”MåÍÑ•µá¥Ð¡µ…¥¸ ¤¤(