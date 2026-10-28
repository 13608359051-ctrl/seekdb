#!/usr/bin/env python3
"""Compare three real cold runs against the repaired development control."""
import argparse
import json
from pathlib import Path
import statistics


def summarize(runs):
    if len(runs) != 3 or any(run["status"] != "PASS" for run in runs):
        raise ValueError("three successful cold runs are required")
    return {
        "build_sec": statistics.median(r["timing"]["build_total_sec"] for r in runs),
        "recall": {k: statistics.median(r["recall"][f"recall@{k}"] for r in runs)
                   for k in ("10", "100")},
        "worst_recall": {k: min(r["recall"][f"recall@{k}"] for r in runs)
                         for k in ("10", "100")},
        "batch_recall": {k: statistics.median(min(r["batch_query"][k]["recall"]) for r in runs)
                         for k in ("10", "100")},
        "worst_batch_recall": {k: min(min(r["batch_query"][k]["recall"]) for r in runs)
                               for k in ("10", "100")},
        "batch_qps": {k: statistics.median(r["batch_query"][k]["qps"] for r in runs)
                      for k in ("10", "100")},
        "single_qps": {k: statistics.median(r["query_qps"][k] for r in runs)
                       for k in ("10", "100")},
        "single_p50_ms": {k: statistics.median(r["query_latency_by_k_ms"][k]["p50"] for r in runs)
                          for k in ("10", "100")},
        "single_p95_ms": {k: statistics.median(r["query_latency_by_k_ms"][k]["p95"] for r in runs)
                          for k in ("10", "100")},
        "batch_call_p50_ms": {k: statistics.median(r["batch_query"][k]["call_p50_ms"] for r in runs)
                              for k in ("10", "100")},
        "batch_call_p95_ms": {k: statistics.median(r["batch_query"][k]["call_p95_ms"] for r in runs)
                              for k in ("10", "100")},
    }


def compare(control, candidate):
    base, trial = summarize(control), summarize(candidate)
    ratios = {k: trial["batch_qps"][k] / base["batch_qps"][k] for k in ("10", "100")}
    gates = {
        "recall": all(trial["worst_recall"][k] + 0.005 + 1e-12 >= base["recall"][k]
                      and trial["worst_batch_recall"][k] + 0.005 + 1e-12 >= base["batch_recall"][k]
                      for k in ("10", "100")),
        "batch_query": all(ratio >= 0.90 for ratio in ratios.values()),
        "build_improves": trial["build_sec"] < base["build_sec"],
    }
    return {"control_median": base, "candidate_median": trial, "gates": gates,
            "build_speedup": base["build_sec"] / trial["build_sec"],
            "batch_qps_ratio": ratios, "development_pass": all(gates.values())}


def load_runs(root, dataset):
    runs = []
    rows, dim = {"D2": (50000, 128), "D3": (50000, 256)}[dataset]
    for repeat in (1, 2, 3):
        path = root / f"{dataset}_r{repeat}"
        if (path / "failure.json").exists():
            raise ValueError(f"failed cold run: {path}")
        result = json.loads((path / "result.json").read_text())
        expected = {"rows": rows, "dim": dim, "queries": 100, "seed": 42,
                    "generator": "numpy standard_normal float32"}
        if result.get("data") != expected or result["index_ddl"] != (
                f"CREATE VECTOR INDEX idx_v ON vecs(v) WITH (DISTANCE=L2, TYPE=hnsw, "
                "LIB=cuvs, M=16, EF_CONSTRUCTION=200, EF_SEARCH=200)"):
            raise ValueError(f"different data or SQL parameters: {path}")
        devices = json.loads((path / "gpu_fds.json").read_text())["devices"]
        if "/dev/kfd" not in devices or not any(d.startswith("/dev/dri/renderD") for d in devices):
            raise ValueError(f"no GPU fd proof: {path}")
        bridge = json.loads((path / "bridge_loaded.json").read_text())
        if len(bridge["loaded"]) != 1 or bridge["loaded"][0]["sha256"] != bridge["expected_sha256"]:
            raise ValueError(f"wrong bridge: {path}")
        markers = [line.split()[0] for line in (path / "trace.log").read_text().splitlines() if line.strip()]
        if markers.count("cuvs_build") < 1 or markers.count("cuvs_serve") < 201 or markers.count("cuvs_raw_batch") < 6:
            raise ValueError(f"incomplete CAGRA trace: {path}")
        runs.append(result)
    return runs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--control", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    report = {"frozen_baseline_commit": "ad3253a52fbeb3b9fc5b0a097d69f41696d28466",
              "repaired_control_commit": "fad7f97ca8520471e420e600d0e5437115e6c397",
              "formal_score": None,
              "comparison_scope": "repaired development control; frozen offline GPU gate remains unresolved",
              "control_root": str(args.control), "candidate_root": str(args.candidate), "datasets": {}}
    for dataset in ("D2", "D3"):
        report["datasets"][dataset] = compare(load_runs(args.control, dataset), load_runs(args.candidate, dataset))
    report["development_pass"] = all(d["development_pass"] for d in report["datasets"].values())
    report["provisional_full_mark_targets"] = all(
        d["build_speedup"] >= 2.0 and min(d["batch_qps_ratio"].values()) >= 1.5
        for d in report["datasets"].values())
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"development_pass": report["development_pass"], "datasets": {
        k: {field: value[field] for field in ("gates", "build_speedup", "batch_qps_ratio")}
        for k, value in report["datasets"].items()}}), flush=True)


if __name__ == "__main__":
    main()
