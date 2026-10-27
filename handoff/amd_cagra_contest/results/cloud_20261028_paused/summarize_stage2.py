from pathlib import Path
import json
import re
import statistics
import sys
from collections import Counter

root = Path("/workspace/amd-cagra-run")

def metrics(result):
    values = dict(result["timing"])
    values.update(result.get("recall", {}))
    for k in ("10", "100"):
        if "query_qps" in result:
            values[f"query_qps_{k}"] = result["query_qps"][k]
            for name in ("p50", "p95"):
                values[f"query_{k}_{name}_ms"] = result["query_latency_by_k_ms"][k][name]
            batch = result["batch_query"][k]
            values[f"batch_qps_{k}"] = batch["qps"]
            values[f"batch_{k}_p50_ms"] = batch["call_p50_ms"]
            values[f"batch_{k}_p95_ms"] = batch["call_p95_ms"]
            values[f"batch_recall_{k}"] = min(batch["recall"])
    return values

def collect(directory):
    output = {}
    for dataset in ("D1", "D2", "D3"):
        runs = []
        for path in sorted(directory.glob(dataset + "_r*")):
            entry = {"run": path.name, "path": str(path.relative_to(root))}
            if (path / "result.json").exists():
                result = json.loads((path / "result.json").read_text())
                entry.update(status=result["status"], metrics=metrics(result))
            if (path / "failure.json").exists():
                entry.update(status="FAIL", failure=json.loads((path / "failure.json").read_text()))
            if (path / "trace.log").exists():
                trace = (path / "trace.log").read_text()
                entry["trace_counts"] = dict(Counter(line.split()[0] for line in trace.splitlines() if line.strip()))
                phases = {}
                for name in ("vsag", "buffer", "save", "restore", "marked"):
                    matches = re.findall(r"phase_" + name + r"\s+handle=\S+ a=(\d+) b=(-?\d+)", trace)
                    if matches:
                        phases[name] = {"a": int(matches[-1][0]), "b": int(matches[-1][1])}
                        if name != "marked":
                            entry.setdefault("metrics", {})[f"phase_{name}_sec"] = int(matches[-1][0]) / 1e9
                entry["phases"] = phases
            logs = list((path / "log").glob("seekdb.log*"))
            profile = []
            for log in logs:
                profile += re.findall(r"phase_cagra_build total_ns=(\d+)", log.read_text(errors="replace"))
            if profile:
                entry.setdefault("metrics", {})["phase_cagra_build_sec"] = int(profile[0]) / 1e9
            for name in ("gpu_fds", "bridge_loaded"):
                if (path / (name + ".json")).exists():
                    entry[name] = json.loads((path / (name + ".json")).read_text())
            runs.append(entry)
        if runs:
            good = [r for r in runs if r.get("status") in ("PASS", "PROFILE_ONLY")]
            median = {key: statistics.median([r["metrics"][key] for r in good])
                      for key in good[0].get("metrics", {}) if all(key in r.get("metrics", {}) for r in good)} if good else {}
            output[dataset] = {"runs": runs, "median": median, "three_pass": len(good) == 3 and len(runs) == 3}
    return output

experiments = {name: collect(root / name) for name in sys.argv[1:]}
report = {"frozen_baseline_commit": "ad3253a52fbeb3b9fc5b0a097d69f41696d28466",
          "formal_gpu_comparison": None,
          "formal_blocker": "Frozen offline CREATE INDEX path fails GPU gate; repaired-control comparisons are development only.",
          "repaired_control_commit": "fad7f97ca8520471e420e600d0e5437115e6c397",
          "experiments": experiments,
          "phase_note": "VSAG and buffer counters are cumulative call durations and may overlap; instrumented totals are diagnostic only."}
(root / "stage2_summary.json").write_text(json.dumps(report, indent=2) + "\n")
for name, datasets in experiments.items():
    for dataset, data in datasets.items():
        print(name, dataset, data["three_pass"], {k: round(v,6) for k,v in data["median"].items()
              if k.startswith(("phase_", "recall", "batch_qps")) or k in ("build_total_sec", "create_index_sec", "first_query_sec")})
