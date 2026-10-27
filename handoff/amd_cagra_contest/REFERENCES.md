# 官方与基线资料

## 赛题与部署

- 赛题页（AMD）：
  https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/seebnbaoxot1b0tb
- AMD Radeon 使用和部署 seekdb：
  https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/lcuknwgl955v8ou7
- 大赛官网：
  https://open.oceanbase.com/competition

## 正式基线

- 仓库：
  https://github.com/zihaomu/seekdb
- 分支：
  `amd-oceanbase-official-contest-base-v4`
- Tag：
  `amd-cagra-contest-baseline-v4`
- Commit：
  `ad3253a52fbeb3b9fc5b0a097d69f41696d28466`
- 基线内的 GPU 接入说明：
  `docs/gpu-vector-index-hipvs-cuvs/README.md`
- GPU 冒烟：
  `docs/gpu-vector-index-hipvs-cuvs/validation/run_gpu_smoke.sh`
- bridge：
  `tools/hipvs_bridge/seekdb_cuvs_bridge.c`

## hipVS

- 文档：
  https://rocm.docs.amd.com/projects/hipVS/en/latest/
- 仓库：
  https://github.com/ROCm-DS/hipVS
- 基线 tag 说明记录的 hipVS commit：
  `f96a663d0a4441d6f5344bd3ef552b71ae7b370b`

## 官方实验 Notebook

- 仓库页面：
  https://github.com/zihaomu/notebook/blob/main/seekdb_hipvs_notebook/seekdb_hipvs_batch_demo_executed.ipynb
- Raw：
  https://raw.githubusercontent.com/zihaomu/notebook/main/seekdb_hipvs_notebook/seekdb_hipvs_batch_demo_executed.ipynb

注意：Notebook 的约 12.65× 是**批量查询**加速，不是索引构建加速，不能作为本题构建成绩。

## Radeon Cloud

- AMD 开发者计划：
  https://developer.amd.com.cn/login?source=0u9Eqno7R
- Radeon Cloud 文档：
  https://amd-aim.github.io/radeon-cloud-docs/introduction/
- 官方模板：
  Gallery → `seekdb-hipvs` → Launch
