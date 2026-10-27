# hipVS / cuVS runtime for AMD gfx1100 (RDNA3, Radeon PRO W7900)

Self-contained image with a source-built hipVS (cuVS) for gfx1100. ROCm 7.2.4.
Built dynamic-only with the Composable Kernel backend OFF. Correctness-validated:
16,320 / 16,321 GoogleTest cases pass (the one miss is a known non-deterministic
duplicate-index event in the approximate all-neighbors test).

## Baked in
- /opt/hipvs/lib     : libcuvs.so, libcuvs_c.so, librmm.so, librapids_logger.so (ldconfig-registered)
- /opt/hipvs/include : cuvs headers (+ CUDA->HIP compat shims), hnswlib, dlpack
- /opt/hipvs/examples/c : C API example sources
- /opt/hipvs/bin/ivf_flat_c_example : prebuilt demo
- hipvs-compile : helper to compile a C-API program with correct flags
- start-sshd    : optional OpenSSH server launcher (openssh-server is installed)

## Host requirements (cannot be baked in)
- AMD gfx1100 / RDNA3 GPU (e.g. Radeon PRO W7900). Library has ONLY gfx1100 code objects.
- Compatible amdgpu / ROCm 7.2.x kernel driver on the host.
- GPU devices/groups passed at docker run time.

## Run
    docker run -it --rm \
      --device=/dev/kfd --device=/dev/dri \
      --group-add video --group-add render \
      --security-opt seccomp=unconfined \
      <image>
    # inside:
    ivf_flat_c_example                 # run the bundled demo
    hipvs-compile my_app.c -o my_app   # compile your own C-API program

## SSH access (optional)
An OpenSSH server is installed but NOT started by default. Publish the port and start it:
    docker run -d --name hipvs -p 2222:22 \
      --device=/dev/kfd --device=/dev/dri \
      --group-add video --group-add render --security-opt seccomp=unconfined \
      <image> sleep infinity
    docker exec -e SSH_PUBKEY="ssh-ed25519 AAAA..." hipvs start-sshd 22   # key auth (recommended)
    #   or password auth:  docker exec -e ROOT_PASSWORD=secret hipvs start-sshd 22
    ssh -p 2222 root@<host>
Run sshd as the container's main process (e.g. as a pod command):
    FOREGROUND=1 SSH_PUBKEY="ssh-ed25519 AAAA..." start-sshd 22

Not performance-tuned (CK off; RDNA3 lacks MFMA). C/C++ only (no Python bindings).
