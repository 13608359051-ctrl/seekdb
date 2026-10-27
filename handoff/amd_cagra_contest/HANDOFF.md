# 正式赛交接：hipVS 加速 seekdb HNSW 构建

## 1. 规则结论（来自赛题原文）

### 1.1 正式评分对象

正式分数比较：

```text
参赛版本 vs 同一轮、同一 GPU、同一数据、同一参数下的冻结 CAGRA 基线
```

不是 CPU VSAG vs GPU，也不是“修改前版本” vs 参赛版本。冻结基线由主办方在同一轮运行。

### 1.2 分数结构

| 项 | 分值 | 说明 |
|---|---:|---|
| 正确性与硬门槛 | 4 | 二值：任一失败总分 0 |
| CAGRA 构建性能 | 14 | 主战场，参赛版本相对冻结基线的构建加速 |
| 批量查询性能 | 2 | 不得低于基线吞吐 90% |

正式成绩全部由主办方在 AMD GPU 云端产生；本地脚本、预编译二进制、自报耗时都不算正式成绩。

### 1.3 硬门槛

1. 源码可编译，能在云端资源/时间内跑完。
2. ID 合法、结果完整、语义正确。
3. Recall@10 / Recall@100 达绝对下限，且相比同轮冻结基线下降 ≤ **0.005**。
4. 构建过程中**真实执行 hipVS/cuVS CAGRA**，不能静默回退 VSAG/CPU。
5. 原 `lib=vsag` CPU 路径仍可用；查询吞吐不低于同轮基线 **90%**。

### 1.4 计时边界

- 起点：原始向量表已导入，目标索引不存在，无可用 CAGRA 图/索引/进程内缓存。
- 终点：索引创建完成 + 扫描/传输完成 + CAGRA 构建和 GPU 同步完成 + 索引可查询 + **第一条固定查询返回合法结果**。
- 第一条查询必须计入构建时间，禁止把惰性建图移出计时。
- 每版本每个数据集 3 次，交替、清缓存/清索引，取中位数；多数据集加权。

## 2. 正式基线

```text
仓库:   https://github.com/zihaomu/seekdb
分支:   amd-oceanbase-official-contest-base-v4
Tag:    amd-cagra-contest-baseline-v4
Commit: ad3253a52fbeb3b9fc5b0a097d69f41696d28466
hipVS:  f96a663d0a4441d6f5344bd3ef552b71ae7b370b
```

证据：

- tag 说明写明 `Raises NN-Descent graph degree and validated search breadth so SIFT and hidden 256d datasets pass Top-10 and Top-100 quality gates.`
- v4 相对 v3 只改 `tools/hipvs_bridge/seekdb_cuvs_bridge.c`，5 行，目的是提高 256d 图质量。
- v4 是 v1/v2/v3 的后代，基于 v4 创建的 commit 一定满足“冻结基线后代”的检查。
- 赛题页面的分支/tag/commit 字段当前为空，**必须以主办方最终公布为准**；未确认前不要把 v4 写死到提交说明里。

## 3. 基线实际做了什么

### 3.1 SQL 与后端选择

```sql
CREATE TABLE items(
  id BIGINT PRIMARY KEY,
  embedding VECTOR(128),
  VECTOR INDEX idx_embedding(embedding)
    WITH (distance=l2, type=hnsw, lib=cuvs)
);
```

- `lib=cuvs`：dense float32、L2、HNSW/HGRAPH 才启用 GPU。
- `lib=vsag`：保持原 CPU 路径。
- 过滤、删除、GPU 不可用、索引过期时回退 VSAG。
- 目前 cosine / inner-product 在 DDL 层被拒绝；正式题目输入是 FP32，基线只保证 L2 dense。

### 3.2 关键代码

| 位置 | 作用 |
|---|---|
| `src/oblib/lib/vector/ob_vsag_adaptor.cpp` `ObCuvsEntry` | 每个索引保存 bridge handle、dim、`ids_`、`buf_vecs_`、`buf_ids_`、`built_n_` |
| 同文件 `ob_cuvs_add()` | **每一行 add_index** 都追加到 `std::vector`，并持全局 mutex |
| 同文件 `ob_cuvs_try_search()` | 第一次 ANN 查询时懒构建 CAGRA；`n >= 256` 且 `bridge_ == nullptr` 或 `n >= built_n_*2` 才 build |
| 同文件 `ob_cuvs_job()` | 32MB 栈 pthread 上 build+search |
| 同文件 `add_index()` | `lib=cuvs` 时先 `ob_cuvs_add`，**随后仍然执行 VSAG `add_index`** |
| `tools/hipvs_bridge/seekdb_cuvs_bridge.c` `seekdb_cuvs_build()` | 硬编码 CAGRA 参数：`NN_DESCENT`、`graph_degree=128`、`intermediate_graph_degree=256`、`nn_descent_niter=100` |
| 同文件 `seekdb_cuvs_search()` | `itopk_size=max(4*topk,512)`、`search_width=4` |
| `docs/gpu-vector-index-hipvs-cuvs/validation/run_gpu_smoke.sh` | 官方 GPU 冒烟与 fallback/recall 验证，产出 `summary.json` |

### 3.3 计时内的真实工作

按代码路径，`CREATE VECTOR INDEX` 期间会：

1. 正常构建 VSAG CPU HNSW；
2. 同时把每行向量追加到 `buf_vecs_`/`buf_ids_`（`lib=cuvs` 才做）。

随后第一条 ANN 查询触发：

3. 用完整 buffer 构建 CAGRA；
4. 用 CAGRA 完成第一条查询。

所以构建计时不是“只算 CAGRA”，而是 **VSAG HNSW + 缓冲 + CAGRA + 第一条查询**。优化前必须先拆分这几段耗时，否则可能优化了占比很小的一段。

## 4. 优化候选（按证据强度排序）

### H1：GPU 索引不再同步构建完整 CPU VSAG（潜力最大，风险最高）

证据：`add_index()` 对 `lib=cuvs` 仍调用 VSAG `add_index`，GPU 和 CPU 两份图都建。
候选：`lib=cuvs` 首次构建只维护 GPU 所需 ID/向量；VSAG 延迟到真正 fallback（过滤/删除/过期/GPU 不可用）时再建。
收益：可能直接去掉一半以上的建图工作。
风险：fallback 功能、内存峰值、生命周期、硬门槛 5。只有在 GPU 正常路径不触发 VSAG 构建时才有加速；不能改变查询结果。
必须先量：VSAG 建图占构建时间的比例。

### H2：CAGRA NN-Descent 参数收敛（最直接）

证据：bridge 硬编码 `nn_descent_niter=100`，而 cuVS 默认是 20；基线为过 256d recall 门槛把它拉高。
候选：

- `nn_descent_niter`: 100 → 80 / 60 / 40 / 20；
- `graph_degree`: 128（可试 96/64）；
- `intermediate_graph_degree`: 256（可试 192/128）。

必须按维度/数据集分别验证，不能全局降到 20。召回下降超过 0.005 即淘汰。
这是最可能快速拿到 1.2–2× 的方向，但也是最容易踩召回门槛的方向。

### H3：去掉逐行缓冲的分配与锁开销（零召回风险）

证据：`ob_cuvs_add()` 每行持 `g_ob_cuvs_mu`，并 `std::vector::insert` 扩容；DDL 逐行喂数据时会产生大量 realloc/拷贝/锁。
候选：

- 按 index 预估行数或几何增长预留 `buf_vecs_`/`buf_ids_`；
- 把全局 mutex 改为按 handle 的锁/单写者假设；
- 按 batch 追加，而非每行 `insert`。

收益取决于 DDL 行数与分配器，可能 5–20%；召回零影响。适合先做低风险收益。

### H4：显式设备上传 / 复用 GPU 资源（中等）

证据：`seekdb_cuvs_build()` 用 `kDLCPU` 的 DLManagedTensor，让 cuVS 内部搬运；每次 build 重新创建 resources/params/index。
候选：一次性 `cuvsRMMAlloc` + 异步拷贝到 `kDLCUDA`，复用 resources，减少 host staging 和重复初始化。
收益可能有限，需先量传输占比；风险是实现复杂、显存峰值上升。

### H5：换 build_algo 或压缩（不优先）

CAGRA 支持 `ivf_pq` / `nn_descent` / `iterative_cagra_search`。基线已选 NN_DESCENT 以过召回门槛，换回 IVF_PQ 很可能掉召回。
只有在 H1/H2 做完仍有余量时再试。

### H6：批量查询（只有 2 分）

基线已有 `dbms_vector.batch_knn`，且官方说明 Notebook 的 12.65× 是**批量查询加速，不是构建加速**。
构建优化不应以查询回归为代价；批量查询只守住 90% 吞吐底线，不是 14 分主项。

## 5. 必须先测什么

1. 基线在 Radeon Cloud 上的正式构建耗时（3 次冷启动中位数）。
2. 同一轮里拆分：
   - VSAG HNSW 建图；
   - `buf_vecs_` 追加；
   - CAGRA build；
   - 第一条查询；
   - GPU 同步。
3. 基线 Recall@10/100、QPS、P50/P95。
4. 128d 与 256d 两个维度都测；v4 明确是为 hidden 256d 质量门槛修的。
5. 只有基线数据齐全后，才选 H1 或 H2 开工。

## 6. 当前阻塞

- 本机无可用 AMD GPU / ROCm / hipVS；所有 GPU 数字必须在 Radeon Cloud 产生。
- 正式数据集与 Recall 绝对下限未公布；本地只能用 128d/256d 代理数据做相对判断。
- 赛题页面的冻结分支/tag/commit 字段为空，需向主办方确认 v4。
- 官方固定评测程序和隐藏数据不可得；本地脚本只用于开发，不冒充正式成绩。

## 7. 边界

- 不修改 SQL 语义、FP32 输入/输出语义、M/ef_construction/默认 ef_search。
- 不修改 `competition/` 或评测数据。
- 不用 VSAG/CPU 回退冒充 GPU CAGRA。
- 不把上一轮 CAGRA 图/索引/缓存复用到下一轮。
- 不把首次查询的惰性建图移出计时。
- 不提交预编译二进制。
