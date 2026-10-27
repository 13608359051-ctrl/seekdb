# 实验计划

## 0. 先测基线，别先改代码

每个数据集先只跑冻结基线 v4，拿到：

- 构建总耗时（3 次冷启动中位数）
- VSAG 建图 / 缓冲 / CAGRA build / 第一条查询的拆分
- Recall@10、Recall@100
- 批量查询 QPS、P50/P95
- GPU 证据：`cuvs_build`/`cuvs_serve` trace、`/dev/kfd` 与 render fd

没有拆分数据，不允许直接调 NN-Descent 参数。

## 1. 数据集

| 编号 | 规模 | 维度 | 用途 |
|---|---:|---:|---|
| D1 | 10k | 128 | 官方 smoke 对齐、快速回归 |
| D2 | 50k | 128 | 主要构建性能 |
| D3 | 50k | 256 | 对应 v4 的 hidden 256d 质量门槛 |
| D4 | 100k | 128/256 | 只在 D2/D3 稳定后跑，观察扩展性 |

数据必须由固定 seed 生成或使用公开数据集，记录来源、行数、维度、生成命令。
正式隐藏数据不可推测、不可硬编码。

## 2. 参数矩阵

按顺序做，不要一次扫完：

### 阶段 A：拆分基线

只跑 v4，加计时探针；不改参数。目标是知道 CAGRA 占比。

### 阶段 B：NN-Descent 迭代数

固定 `graph_degree=128`、`intermediate=256`，只改 `nn_descent_niter`：

```text
100 (baseline) → 80 → 60 → 40 → 20
```

每个点跑 D2 + D3，3 次中位数。候选必须在 D3 上 Recall@10/100 相对 v4 下降 ≤0.005。

### 阶段 C：图度数

在阶段 B 的最优 niter 上：

```text
graph_degree:       128 → 96 → 64
intermediate_degree: 256 → 192 → 128
```

约束：`intermediate > graph_degree`，且 256d 不掉召回门槛。

### 阶段 D：低风险代码优化

- vector reserve / batch append / 去全局锁；
- 如果拆分显示 host→device 占比高，再做显式上传。

阶段 D 不改图参数，因此不应影响召回。

### 阶段 E：CPU VSAG 同步构建移除（H1）

只有在阶段 A 证明 VSAG 建图占比大时才做。必须验证：

- GPU 正常路径仍真实使用 CAGRA；
- 过滤/删除/GPU 不可用 fallback 仍正确；
- `lib=vsag` 索引行为不变；
- 第一条查询仍在计时内。

## 3. 判定规则

候选版本必须同时满足：

1. 源码可从冻结基线后代 commit 编译；
2. 所有硬门槛通过；
3. Recall@10/100 相对同轮 v4 下降 ≤ 0.005；
4. 批量查询吞吐 ≥ 同轮 v4 的 90%；
5. 构建加速可重复，3 次冷启动中位数优于 v4；
6. GPU 真实执行 CAGRA，有 trace/GPU fd 证据。

任一失败：淘汰，不进入提交。

## 4. 记录格式

每次实验一个 JSON，至少包含：

```json
{
  "baseline_commit": "ad3253a52fbeb3b9fc5b0a097d69f41696d28466",
  "candidate_commit": "<sha>",
  "dataset": {"name": "D2", "rows": 50000, "dim": 128, "seed": 42},
  "gpu": {"model": "", "gfx": "", "rocm": "", "hipvs": ""},
  "params": {"build_algo": "nn_descent", "graph_degree": 128,
             "intermediate_graph_degree": 256, "nn_descent_niter": 100},
  "runs": [
    {"build_sec": 0, "first_query_ms": 0, "recall10": 0, "recall100": 0,
     "qps": 0, "p50_ms": 0, "p95_ms": 0}
  ],
  "median": {},
  "gates": {"compile": true, "gpu_cagra": true, "recall": true, "query": true},
  "evidence": {"trace": "", "summary_json": "", "gpu_fds": ""}
}
```

不要只保存最好一次；三次都保存，并给中位数。

## 5. 预期与风险

- 仅靠 H2 参数下调，可能拿到明显加速，但隐藏 256d 召回是主要风险。
- H1 可能带来最大加速，但生命周期/fallback 复杂度最高，必须最后做。
- H3 是安全的低风险修饰，不要期待单独达成 2×。
- 任何“只算 CAGRA、不算第一条查询”的测量都无效。
