# AMD CAGRA 正式赛交接入口

## 状态

2026-10-28：按用户要求暂停，明天收到新指令及新 AMD 实例后再继续。
指定冻结源码已编译，但离线 CREATE INDEX 路径 GPU 门禁失败；候选侧已修复快照输入丢失，
修复对照九次冷启动、九次耗时拆分和官方 smoke 已通过。80 次迭代实验只完成一个 D2 样本，
尚未选参或形成正式加速结论。先读 `results/PROGRESS_PAUSED_20261028.md`，其中有版本、备份和恢复步骤。

- 官方规则：已确认，见 `HANDOFF.md` §1。
- 正式基线：已定位并下载，见 §2。
- 本机 GPU：**不可用**（无 ROCm/hipVS；Windows 780M 不是可用的 hipVS 环境）。
- 优化实现：离线快照修复已验证；参数实验未完成，当前 80 次迭代源码属于未验收试验。
- GPU 实测：修复对照已有完整计时、召回、查询及 GPU 证据；**冻结基线离线路径仍缺有效 GPU 构建成绩**。
- 旧交接包 `hipvs_hnsw_handoff.zip` 基于上游 seekdb，**不适用于本题**，只能作为历史材料。

## 正式基线（推定冻结）

```text
仓库:   https://github.com/zihaomu/seekdb
分支:   amd-oceanbase-official-contest-base-v4
Tag:    amd-cagra-contest-baseline-v4
Commit: ad3253a52fbeb3b9fc5b0a097d69f41696d28466
hipVS:  f96a663d0a4441d6f5344bd3ef552b71ae7b370b
```

v4 继承 v1/v2/v3 全部标签；赛题页面的冻结字段目前为空，**开工前必须向主办方确认就是 v4**。
若主办方给出其它 commit，以主办方为准并 rebase。

## 我们的工作分支

```text
kimi/amd-cagra-opt
基线 commit: ad3253a52fbeb3b9fc5b0a097d69f41696d28466
```

该分支包含候选修复及未完成的参数试验，**尚未完成提测验收**。

## 先读什么

1. `HANDOFF.md`：规则、基线、优化点、硬门槛。
2. `EXPERIMENT_PLAN.md`：Radeon Cloud 上的实验矩阵和判定标准。
3. `RUNBOOK_RADEON_CLOUD.md`：从领取算力到编译、冒烟、测速。
4. `RESULTS_TEMPLATE.md`：结果必须怎么记录。
5. `SUBMISSION_CHECKLIST.md`：提交前逐项打勾。
6. `REFERENCES.md`：赛题、基线、部署、Notebook、Radeon Cloud 的原始链接。

`bench_build.py` 是开发测速入口，已在 Radeon Cloud 的修复对照上完成 GPU 计时、召回和查询实测。
`results/bench_harness_vsag_selftest.json` 只是脚本自检，不是本题性能证据。

## 最重要的一句话

正式分数比较的是 **参赛 commit 相对冻结 CAGRA 基线的构建加速**，不是 CPU vs GPU。
必须先拿到 Radeon Cloud，实测基线和候选，再决定改什么；本机 CPU 结果不能替代。
