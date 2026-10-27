#!/usr/bin/env bash
set -Eeuo pipefail
root=/workspace/amd-cagra-run
src=$root/source/baseline
trap 'echo "rc=$?" > "$root/stage2-profile-status.txt"' EXIT
[[ $(cat "$root/control-fad7-status.txt") == exit_code=0 ]]
! pgrep -f '^python3 -u handoff/amd_cagra_contest/run_cold.py' >/dev/null
cd "$src"
[[ $(git rev-parse HEAD) == fad7f97ca8520471e420e600d0e5437115e6c397 ]]
[[ -z $(git status --porcelain --untracked-files=no) ]]
mkdir -p "$root/variants/control100"
cp build_release/src/observer/seekdb "$root/variants/control100/seekdb"
cp "$root/bridge/libseekdb_cuvs_bridge.so" "$root/variants/control100/libseekdb_cuvs_bridge.so"
sha256sum "$root/variants/control100/seekdb" "$root/variants/control100/libseekdb_cuvs_bridge.so" > "$root/variants/control100/sha256.txt"
git fetch "$root/stage2-harness.bundle" HEAD
git checkout --detach a25e80f5c13a9077508dc0e7f3959f59ca42c65c
git apply --check handoff/amd_cagra_contest/control_profile.patch
git apply handoff/amd_cagra_contest/control_profile.patch
bash tools/hipvs_bridge/build.sh "$root/profile-control/libseekdb_cuvs_bridge.so"
bash "$root/build-baseline-ready.sh"
python3 -u handoff/amd_cagra_contest/run_cold.py --observer "$src/build_release/src/observer/seekdb" --bridge "$root/profile-control/libseekdb_cuvs_bridge.so" --out "$root/profile-control-a25e" --phase-only > "$root/profile-control-a25e.log" 2>&1
git diff -- src/oblib/lib/vector/ob_vsag_adaptor.cpp tools/hipvs_bridge/seekdb_cuvs_bridge.c > "$root/control_profile_applied.patch"
git apply -R handoff/amd_cagra_contest/control_profile.patch
[[ -z $(git status --porcelain --untracked-files=no) ]]
python3 -m py_compile handoff/amd_cagra_contest/bench_build.py handoff/amd_cagra_contest/run_cold.py
python3 -m unittest discover -s handoff/amd_cagra_contest -p test_bench_build.py
