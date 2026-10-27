from pathlib import Path
import hashlib
import json
import subprocess
import sys

bundle, commit, name = sys.argv[1:]
root = Path("/workspace/amd-cagra-run")
src = root / "source/baseline"
assert (root / "stage2-profile-status.txt").read_text().strip() == "rc=0"
assert not subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=src)
subprocess.run(["git", "fetch", str(root / bundle), "HEAD"], cwd=src, check=True)
subprocess.run(["git", "checkout", "--detach", commit], cwd=src, check=True)
assert subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=src).decode().strip() == commit
assert not subprocess.check_output(["git", "diff", "fad7f97ca8520471e420e600d0e5437115e6c397", commit, "--", "src"], cwd=src)
variant = root / "variants" / name
variant.mkdir(exist_ok=False)
bridge = variant / "libseekdb_cuvs_bridge.so"
subprocess.run(["bash", "tools/hipvs_bridge/build.sh", str(bridge)], cwd=src, check=True)
observer = root / "variants/control100/seekdb"
source = (src / "tools/hipvs_bridge/seekdb_cuvs_bridge.c").read_text()
import re
params = {key: int(re.search(key + r" = (\d+)", source)[1]) for key in ("graph_degree", "intermediate_graph_degree", "nn_descent_niter")}
metadata = {"candidate_commit": commit, "params": params, "observer_compiled_commit": "fad7f97ca8520471e420e600d0e5437115e6c397", "observer_src_identical": True,
            "bridge_sha256": hashlib.sha256(bridge.read_bytes()).hexdigest(), "observer_sha256": hashlib.sha256(observer.read_bytes()).hexdigest(),
            "comparison": "repaired control only; not frozen official score"}
(variant / "metadata.json").write_text(json.dumps(metadata, indent=2))
with (root / ("experiment-" + name + ".log")).open("w") as log:
    result = subprocess.run([sys.executable, "-u", "handoff/amd_cagra_contest/run_cold.py", "--observer", str(observer), "--bridge", str(bridge), "--out", str(root / ("experiment-" + name)), "--datasets", "D2", "D3"], cwd=src, stdout=log, stderr=subprocess.STDOUT)
(root / ("experiment-" + name + "-status.txt")).write_text("rc=" + str(result.returncode))
raise SystemExit(result.returncode)
