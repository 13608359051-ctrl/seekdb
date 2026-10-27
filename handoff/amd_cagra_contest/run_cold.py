#!/usr/bin/env python3
"""Run three isolated observer lifecycles per dataset, retaining logs and failures."""
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time

import pymysql


def gpu_devices(pid):
    devices = []
    for fd in Path(f"/proc/{pid}/fd").glob("*"):
        try:
            target = os.readlink(fd)
        except FileNotFoundError:
            continue
        if target == "/dev/kfd" or target.startswith("/dev/dri/renderD"):
            devices.append(target)
    return devices


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--observer", required=True, type=Path)
    parser.add_argument("--bridge", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--datasets", nargs="+", choices=("D1", "D2", "D3"), default=["D1", "D2", "D3"])
    parser.add_argument("--port", type=int, default=2981)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    observer, bridge = args.observer.resolve(strict=True), args.bridge.resolve(strict=True)
    assert observer.is_file() and bridge.is_file()
    configs = {"D1": (10000, 128), "D2": (50000, 128), "D3": (50000, 256)}
    failures = 0
    for dataset in args.datasets:
        rows, dim = configs[dataset]
        for repeat in range(1, 4):
            run = args.out / f"{dataset}_r{repeat}"
            run.mkdir()
            trace = run / "trace.log"
            env = dict(os.environ, OB_VSAG_TRACE="1", OB_VSAG_TRACE_FILE=str(trace),
                       LD_LIBRARY_PATH=f"{bridge.parent}:/opt/hipvs/lib:/opt/rocm/lib",
                       SEEKDB_PORT=str(args.port), OPENBLAS_NUM_THREADS="1")
            env.pop("OB_VSAG_USE_CUVS", None)
            command = [str(observer), "--nodaemon", "--port", str(args.port),
                       "--data-dir", str(run / "store"), "--base-dir", str(run),
                       "--parameter", "__min_full_resource_pool_memory=2147483648",
                       "--parameter", "memory_budget=2G", "--parameter", "datafile_size=20G",
                       "--parameter", "cpu_count=24", "--parameter", "local_ip=127.0.0.1"]
            (run / "command.json").write_text(json.dumps(command))
            with socket.socket() as probe:
                probe.settimeout(1)
                if probe.connect_ex(("127.0.0.1", args.port)) == 0:
                    raise RuntimeError("port already in use; refusing to reuse an existing observer")
            with (run / "observer.log").open("w") as log:
                process = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT)
                try:
                    for _ in range(120):
                        if process.poll() is not None:
                            raise RuntimeError(f"observer exited {process.returncode}")
                        try:
                            connection = pymysql.connect(host="127.0.0.1", port=args.port,
                                                         user="root", connect_timeout=1)
                            with connection.cursor() as cursor:
                                cursor.execute("SELECT 1")
                            connection.close()
                            break
                        except pymysql.MySQLError:
                            time.sleep(1)
                    else:
                        raise RuntimeError("observer readiness timeout")
                    with (run / "bench.log").open("w") as bench_log:
                        subprocess.run([sys.executable, str(Path(__file__).with_name("bench_build.py")),
                                        "--rows", str(rows), "--dim", str(dim), "--queries", "100",
                                        "--trace-file", str(trace), "--out", str(run / "result.json")],
                                       env=env, stdout=bench_log, stderr=subprocess.STDOUT,
                                       check=True, timeout=1800)
                    fds = gpu_devices(process.pid)
                    assert "/dev/kfd" in fds and any(f.startswith("/dev/dri/renderD") for f in fds), fds
                    print(f"PASS {dataset} cold run {repeat}", flush=True)
                except Exception as exc:
                    (run / "failure.json").write_text(json.dumps({"error": str(exc)}))
                    failures += 1
                    print(f"FAIL {dataset} cold run {repeat}: {exc}", flush=True)
                finally:
                    (run / "gpu_fds.json").write_text(json.dumps(
                        {"pid": process.pid, "devices": gpu_devices(process.pid)}))
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    # Only this invocation's disposable graph/data directory is removed.
                    store = run / "store"
                    assert store.resolve().parent == run.resolve()
                    if store.exists():
                        shutil.rmtree(store)
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
