# Radeon Cloud 运行手册

> 目标：在官方 Radeon Cloud 上从**源码**重建基线/候选，拿到构建、召回、查询和 GPU 证据。
> 不使用模板里的预编译 seekdb 冒充正式结果。

## 1. 领取算力

1. 注册 AMD 开发者计划（ADP）：
   `https://developer.amd.com.cn/login?source=0u9Eqno7R`
2. 在权益页领取/兑换算力券。
3. 登录 Radeon Cloud，Profile → Redeem Credits，粘贴算力券。
4. Gallery 搜索 `seekdb`，选择 **seekdb-hipvs** 模板 → Launch。
5. 等待 `Your workspace is ready` → Open Notebook / Terminal。

规则提醒：

- 热门时段需要排队；非热门时段先到先得。
- 单实例最长运行 4 小时，超时回收。
- 先保存代码、结果、截图和 UUID，再 Destroy 实例。
- 不要把密码、API Key、SSH 私钥写入交接包或截图。

## 2. 获取代码

在云端终端：

```bash
git clone https://github.com/zihaomu/seekdb.git baseline
cd baseline

# 先确认正式基线
git fetch origin 'refs/heads/amd-oceanbase-official-contest-base*:refs/remotes/origin/amd-oceanbase-official-contest-base*'
git checkout amd-oceanbase-official-contest-base-v4
git rev-parse HEAD
# 期望：ad3253a52fbeb3b9fc5b0a097d69f41696d28466
```

自己的候选分支必须从该 commit 创建，并推到自己的团队仓库。不要在云端直接改主分支。

## 3. 检查环境

```bash
rocm-smi
rocminfo | grep -E 'Name:|gfx'
hipcc --version
ls /opt/hipvs/include/cuvs/neighbors/cagra.h
ls /opt/hipvs/lib/libcuvs_c.so
ls /dev/kfd /dev/dri/renderD*
```

如果 `hipcc`、hipVS 头/库或 `/dev/kfd` 不存在，先停，不要开始调参。
记录 GPU 型号、gfx target、ROCm 版本、hipVS commit（若有）。

## 4. 编译 bridge

```bash
mkdir -p /workspace/bridge
HIPVS_ROOT=/opt/hipvs \
ROCM_ROOT=/opt/rocm \
tools/hipvs_bridge/build.sh /workspace/bridge/libseekdb_cuvs_bridge.so
```

检查：

```bash
ldd /workspace/bridge/libseekdb_cuvs_bridge.so | grep -E 'cuvs|rocm|amdhip'
```

## 5. 从源码编译 seekdb

```bash
./build.sh release \
  -DOB_BUILD_CUVS=ON \
  -DOB_BUILD_CUVS_TRACE=ON \
  -DCUVS_BRIDGE_LIB=/workspace/bridge/libseekdb_cuvs_bridge.so \
  --make -j"$(nproc)"
```

说明：

- 正式评测会自己从源码编译，因此本地也必须走源码构建。
- `OB_BUILD_CUVS_TRACE=ON` 只用于开发取证；正式提交不应依赖 trace 才能正确运行。
- 记录编译命令、编译器版本、commit，编译失败先保存日志。

## 6. 先跑官方 smoke

```bash
RENDER=$(ls /dev/dri/renderD* | head -n1)

LD_LIBRARY_PATH=/workspace/bridge:/opt/hipvs/lib:/opt/rocm/lib \
docs/gpu-vector-index-hipvs-cuvs/validation/run_gpu_smoke.sh \
  --observer "$(pwd)/build_release/src/observer/seekdb" \
  --bridge /workspace/bridge/libseekdb_cuvs_bridge.so \
  --base-dir /tmp/seekdb-cuvs-smoke \
  --port 2981 \
  --render "$RENDER" \
  --evidence /tmp/seekdb-cuvs-evidence
```

验收：

```bash
python3 -m json.tool /tmp/seekdb-cuvs-evidence/summary.json
```

必须是 `"status": "PASS"`，并且包含：

- `cuvs_l2_route`：真实走了 cuVS build/serve；
- `vsag_cpu_route`：VSAG 路径未误走 GPU；
- `filter_fallback` / `delete_fallback` / `freshness_fallback`；
- `batch_knn` / `batch_knn_top100` 的 recall；
- `gpu_fd`：observer 打开了 `/dev/kfd` 和 render node；
- `cleanup`：进程和端口都清理。

smoke 失败时先解决，不要开始性能调参。

## 7. 构建性能测量

基线/候选使用同一套脚本、同一数据、同一参数。每轮：

1. 销毁 base-dir，启动新 observer；
2. 导入原始向量表；此时目标索引不存在；
3. 开始计时；
4. `CREATE VECTOR INDEX ... WITH (lib=cuvs, ...)`；
5. 发第一条固定 ANN 查询并取回合法结果；
6. 停止计时；
7. 记录构建耗时、第一条查询耗时、Recall@10/100、QPS、P50/P95、GPU trace。

每版本 3 次，交替 baseline/candidate。不要把编译、导入、服务启动计入构建。
不要复用上一轮索引/图/缓存。

开发用测速入口：

```bash
python3 handoff/amd_cagra_contest/bench_build.py \
  --rows 50000 --dim 128 --queries 100 --first-k 10 --lib cuvs \
  --out /workspace/results/candidate_d2_r1.json
```

每次调用必须配一个**新 observer 进程**（一次调用只测一个冷启动）。脚本只用于开发，
组织方固定程序才是正式成绩。

本机已在 **lib=vsag** 上验证脚本 SQL/计时链可用（2000×32，first-k=10）：
`build_total_sec=1.048`、recall@10=0.995、recall@100=0.988；
该结果**不是 CAGRA，也不是 GPU 数据**，只证明脚本能跑。

## 8. 保存与释放

必须保存：

```text
experiment.json
summary.json
obvsag-trace.log
observer log
编译命令与版本
GPU 自检输出
```

再 Destroy 实例。不要把实例留到超时自动回收。

## 9. 常见失败

| 现象 | 先查 |
|---|---|
| 没有 GPU | 模板未挂载 `/dev/kfd` / render node，或选错实例 |
| GPU 路径未触发 | 索引不是 `lib=cuvs`，不是 L2/HNSW，数据量低于 256 |
| 召回掉点 | 参数太激进，回到 v4 并逐项加回 |
| 静默回退 | trace 无 `cuvs_build`，或 observer fd 没有 `/dev/kfd` |
| 编译找不到 bridge | `CUVS_BRIDGE_LIB` 路径错误或 `.so` 依赖缺失 |
| 实例被回收 | 单次 4 小时上限；提前保存结果 |
