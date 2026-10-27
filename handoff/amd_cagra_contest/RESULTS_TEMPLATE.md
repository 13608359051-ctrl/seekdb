# 结果记录模板

> 一份结果只对应一个 (baseline, candidate, dataset) 三元组。
> 三次运行全部保留，不能只填最好一次。

## 1. 标识

```text
日期/时区:
提交仓库:
参赛分支:
参赛 commit (40 位):
冻结基线仓库:
冻结基线 tag:
冻结基线 commit:
hipVS commit:
```

## 2. 环境

```text
GPU 型号:
gfx target:
显存:
ROCm 版本:
hipcc 版本:
OS / kernel:
编译命令:
bridge 构建命令:
```

## 3. 数据与参数

```text
数据集/来源:
行数:
维度:
数据类型: float32
距离: L2
M:
ef_construction:
ef_search:
CAGRA build_algo:
graph_degree:
intermediate_graph_degree:
nn_descent_niter:
```

## 4. 构建计时（3 次，交替）

| 轮次 | 版本 | 建索引 s | 第一条查询 ms | 构建合计 s | Recall@10 | Recall@100 | GPU 真实执行 |
|---:|---|---:|---:|---:|---:|---:|---|
| 1 | baseline v4 | | | | | | |
| 2 | candidate | | | | | | |
| 3 | baseline v4 | | | | | | |
| 4 | candidate | | | | | | |
| 5 | baseline v4 | | | | | | |
| 6 | candidate | | | | | | |

```text
baseline 中位构建 s:
candidate 中位构建 s:
构建加速比 = baseline / candidate:
```

## 5. 查询性能

| 版本 | QPS | P50 ms | P95 ms | Recall@10 | Recall@100 | ID 正确 |
|---|---:|---:|---:|---:|---:|---|
| baseline v4 | | | | | | |
| candidate | | | | | | |

```text
candidate QPS / baseline QPS = ____  (硬门槛 >= 0.90)
```

## 6. 硬门槛

- [ ] 源码编译成功
- [ ] 结果完整、ID 合法
- [ ] Recall 绝对下限达标（待官方公布）
- [ ] Recall 相对基线下降 ≤ 0.005
- [ ] 构建真实执行 hipVS/cuVS CAGRA（trace + GPU fd）
- [ ] 无静默 VSAG/CPU 回退
- [ ] `lib=vsag` CPU 路径正常
- [ ] 查询吞吐 ≥ 基线 90%
- [ ] 未复用上一轮图/索引/缓存
- [ ] 第一条查询计入构建时间

## 7. 证据文件

```text
experiment.json:
summary.json:
obvsag-trace.log:
observer.log:
gpu-fds.txt:
compile.log:
```

## 8. 结论

```text
是否可提交: 是 / 否
若否，失败项:
下一步:
```
