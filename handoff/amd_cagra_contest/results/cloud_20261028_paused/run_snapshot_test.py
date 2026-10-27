from pathlib import Path
import json
import os
import shlex
import subprocess

root = Path("/workspace/amd-cagra-run/source/baseline")
build = root / "build_release"
out = Path("/workspace/amd-cagra-run/snapshot-test")
out.mkdir(exist_ok=False)
flags_file = build / "src/observer/CMakeFiles/ob_main.dir/flags.make"
flags = dict(line.split(" = ", 1) for line in flags_file.read_text().splitlines() if " = " in line)
args = sum((shlex.split(flags[k]) for k in ("CXX_DEFINES", "CXX_INCLUDES", "CXX_FLAGS")), [])
assert any(x == "-DOB_BUILD_CUVS" or x.startswith("-DOB_BUILD_CUVS=") for x in args)
link = shlex.split((build / "src/observer/CMakeFiles/seekdb.dir/link.txt").read_text())
commands = []
objects = []
for source in (root / "unittest/oblib/vector/test_vsag_adaptor.cpp", root / "unittest/all_tests_main.cpp"):
    obj = out / (source.stem + ".o")
    command = [link[0], *args, "-I" + str(root / "unittest"), "-c", str(source), "-o", str(obj)]
    commands.append(command)
    subprocess.run(command, cwd=build / "src/observer", check=True)
    objects.append(str(obj))
removed = [x for x in link if "CMakeFiles/ob_main.dir/" in x and x.endswith(".o")]
assert removed, "no observer main object found"
link = [x for x in link if x not in removed]
link[link.index("-o") + 1] = str(out / "snapshot_test")
dep = root / "deps/3rd/usr/local/oceanbase/deps/devel"
link[1:1] = [*objects, str(dep / "lib/libgtest.a")]
commands.append(link)
(out / "commands.json").write_text(json.dumps(commands, indent=2))
subprocess.run(link, cwd=build / "src/observer", check=True)
env = dict(os.environ, LD_LIBRARY_PATH="/workspace/amd-cagra-run/variants/control100:/opt/hipvs/lib:/opt/rocm/lib:" + str(dep / "lib") + ":" + str(dep / "lib/vsag_lib"))
subprocess.run([str(out / "snapshot_test"), "--gtest_filter=TestVsagAdaptor.cuvs_snapshot_round_trip"], cwd=out, env=env, check=True)
