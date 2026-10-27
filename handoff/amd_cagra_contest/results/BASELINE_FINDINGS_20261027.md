# 冻结基线 GPU 路径诊断（2026-10-27）

冻结源码 `ad3253a52fbeb3b9fc5b0a097d69f41696d28466` 编译成功，原版官方 GPU smoke 的 12 项检查全部 PASS。
但严格按“导入未建索引的表 → CREATE VECTOR INDEX → 首条固定 ANN 查询”运行时，原版 D1 三次冷启动全部缺少 CAGRA build/serve，GPU fd 为空。因此这些时间不能作为 GPU 基线成绩。默认表布局的三次对照同样失败。

## 阶段探针结果

以下为单独加探针的诊断版本，各数据集三个新 observer/数据目录，取中位数。VSAG/缓冲是累计调用时长，可能在线程间重叠，不能相加当作墙钟时间；全部结果因未执行 CAGRA 而失效，不能用于构建加速比。

| 数据集 | VSAG 调用累计秒 | 缓冲调用累计秒 | CREATE 秒 | 首查询毫秒（CPU） | CAGRA |
|---|---:|---:|---:|---:|---|
| D1 | 1.963622 | 0.009661 | 2.441118 | 12.629 | 未执行，记 null |
| D2 | 14.681447 | 0.048507 | 16.194068 | 37.636 | 未执行，记 null |
| D3 | 21.797843 | 0.091773 | 23.639054 | 49.804 | 未执行，记 null |

每轮向量缓冲和 VSAG Add 调用数均等于行数；首查询 `phase_marked a=0`。trace 显示临时建图 handle 删除后，快照反序列化到新 handle。`fdeserialize()` 只恢复 VSAG，未恢复 GPU 标记及原始向量缓冲；显式标记仅在插入/追加时设置。
定位文件：`src/oblib/lib/vector/ob_vsag_adaptor.cpp` 的 `fserialize/fdeserialize`、`ob_cuvs_erase`，以及 `src/observer/vector_index/ob_plugin_vector_index_adaptor.cpp` 的快照恢复路径。

## GPU 与质量证据

原版 smoke 和诊断版 smoke 都实际执行 CAGRA，打开 `/dev/kfd` 与 `/dev/dri/renderD128`，Top-10/100 batch recall 均为 1.0000；过滤、删除、更新、无 GPU 回退及清理均 PASS。这是 smoke 自身的 10k×128 近邻数据，不能代替 D2/D3 的召回/吞吐对比。
诊断 smoke 中 10k CAGRA build 的两个单次样本约 5.490 秒、7.513 秒，属于 batch API 的一次性建图，既不是三次冷启动中位数，也不是离线 CREATE INDEX 的构建成绩。
当前没有有效冻结 GPU 基线的 Recall@10/100、QPS/P50/P95 或候选加速比，这些字段保留 null。

## 可复核材料

- `cloud_20261027/collected_summary.json`：全部三次原始计时、ID、PID/fd、trace 计数、阶段累计计时和诊断中位数。
- `cloud_20261027/{baseline-repro-v2,baseline-default-layout,baseline-profile-v1}`：逐轮原始 JSON、命令和失败项。
- `baseline_profile.patch`：仅用于诊断的计时探针；未应用到本地生产源码。完整云端应用差异另存为 `cloud_20261027/diagnostic_applied.patch`。
- 完整原始日志/trace/输入与工具备份：`E:\OceanBase2026\amd-cagra-cloud-evidence-20261027.zip`，48,307,831 字节。
- SHA256：`9f595459df98e6ecc6d606b13f1ed17acd28d57a96e88f1002e8c2a0a0623d7d`；云端与本地匹配，ZIP CRC 验证通过，不含 ELF/预编译执行文件。
- ROCm 7.2.4 / 驱动 6.16.13 / gfx1100，设备报告 AMD Radeon Graphics；55 GiB 内存上限、16 核配额。hipVS 源码 commit 未能核验，已记录实际库的 SHA256。

## 后续边界

用户在 2026-10-28 要求继续候选实现与交付，实例保留。先在候选侧恢复离线快照的 GPU 状态，保留原 CPU 回退与 lib=vsag 语义，再做 CAGRA 参数实验。冻结 commit/tag 不改。
若用共同修复后的控制版本做开发比较，必须单独记录其完整 SHA，与冻结正式基线区分。未经正式评测口径确认，不把该控制版本的加速比宣称为正式赛成绩。
