from pathlib import Path
import hashlib
import json
import subprocess
import zipfile

root = Path("/workspace/amd-cagra-run")
src = root / "source/baseline"
summary = json.loads((root / "stage2_summary.json").read_text())
summary.update(work_status="PAUSED_BY_USER", stage2_complete=False,
               pause_reason="User stopped for today; resume only after a new user instruction and new AMD instance.",
               unfinished_candidate_commit="ccc1d57959e131c5d94947be0758a0290d346788",
               unfinished_experiment="iter80: D2 run 1 completed, D2 run 2 interrupted, D3 not started. Do not select or report a three-run median.")
for data in summary["experiments"].get("experiment-iter80", {}).values():
    for run in data["runs"]:
        if "status" not in run:
            run["status"] = "STOPPED_BY_USER"
    if not data["three_pass"]:
        data["partial_sample_statistics_only"] = data.pop("median")
summary["snapshot_unit_test"] = {"filter": "TestVsagAdaptor.cuvs_snapshot_round_trip",
    "passed": "[  PASSED  ] 1 test." in (root / "snapshot-test.log").read_text(),
    "command_log": "snapshot-test/commands.json", "output": "snapshot-test.log"}
assert summary["snapshot_unit_test"]["passed"]
assert all(value["three_pass"] for name in ("control-fad7-full", "profile-control-a25e") for value in summary["experiments"][name].values())
summary["source_head"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=src, text=True).strip()
summary["source_status_tracked"] = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=src, text=True)
assert summary["source_head"] == summary["unfinished_candidate_commit"] and not summary["source_status_tracked"]
summary["source_files"] = {}
for name in ("src/oblib/lib/vector/ob_vsag_adaptor.cpp", "src/observer/vector_index/ob_plugin_vector_index_adaptor.cpp", "tools/hipvs_bridge/seekdb_cuvs_bridge.c", "unittest/oblib/vector/test_vsag_adaptor.cpp", "handoff/amd_cagra_contest/bench_build.py", "handoff/amd_cagra_contest/run_cold.py"):
    summary["source_files"][name] = hashlib.sha256((src / name).read_bytes()).hexdigest()
summary["data_hashes"] = json.loads((root / "collected_summary.json").read_text())["datasets"]
summary["official_smoke"] = json.loads((root / "control-fad7-smoke-evidence/summary.json").read_text())
assert summary["official_smoke"]["status"] == "PASS"
(root / "stage2_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
(root / "stage2_candidate.patch").write_bytes(subprocess.check_output(["git", "diff", "ad3253a52fbeb3b9fc5b0a097d69f41696d28466", "HEAD", "--", "src", "tools/hipvs_bridge", "unittest/oblib/vector/test_vsag_adaptor.cpp"], cwd=src))
subprocess.run(["git", "bundle", "create", str(root / "stage2-source.bundle"), "ad3253a52fbeb3b9fc5b0a097d69f41696d28466..HEAD"], cwd=src, check=True)
files = set()
for pattern in ("*.log", "*.txt", "*.json", "*.patch", "*.py", "*.sh", "hipvs-version.h", "stage2-source.bundle"):
    files.update(p for p in root.glob(pattern) if p.is_file() and not p.is_symlink())
for directory in ("control-3c65-d1-check", "control-fad7-full", "control-fad7-smoke-evidence", "control-fad7-smoke", "profile-control-a25e", "experiment-iter80", "variants", "snapshot-test"):
    files.update(p for p in (root / directory).rglob("*") if p.is_file() and not p.is_symlink() and "store" not in p.parts and "__pycache__" not in p.parts)
files = {p for p in files if p.open("rb").read(4) != b"\x7fELF"}
archive = root / "amd-cagra-stage2-paused-20261028.zip"
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as output:
    for path in sorted(files):
        output.write(path, path.relative_to(root))
with zipfile.ZipFile(archive) as check:
    assert check.testzip() is None
manifest = {"archive": archive.name, "bytes": archive.stat().st_size,
            "sha256": hashlib.file_digest(archive.open("rb"), "sha256").hexdigest(), "files": len(files),
            "precompiled_binaries_included": False}
(root / "stage2_backup_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(json.dumps(manifest), flush=True)
