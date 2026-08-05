# Sherlock 状态与返回指南

更新时间：2026-08-03。本文只保存可迁移的状态和命令，不保存密码、rclone
token、`rclone.conf` 或其他 credential。

## 1. 项目与环境

```bash
PROJECT=/scratch/users/zhangzh/oligolivefish_nd2_to_trajectory
PYTHON=$PROJECT/env/py312_torch251_cu124_ml217/bin/python
V422_REPO=$PROJECT/code/OligoLiveFish-ML-ZZH-v4.2.2-833515e
V5_REPO=$PROJECT/code/OligoLiveFish-ML-ZZH-v5-dev1
```

- Sherlock user：`zhangzh`
- Slurm account：`slqi`
- 常用 partition：`normal`
- production Python：3.12.1
- production MATLAB：R2022b
- v4.2.2/v5 baseline commit：
  `833515ee7a3da2ced4b34925c85107d54c006918`
- v5 branch：`experiment/v5-dev1-trackmem-global-gap`
- v5 version：`5.0.0-dev1-trackmem-global-gap`

环境恢复：

```bash
module purge
module load system
module load git/2.45.1
module load python/3.12.1
module load matlab/R2022b
hash -r

PROJECT=/scratch/users/zhangzh/oligolivefish_nd2_to_trajectory
PYTHON=$PROJECT/env/py312_torch251_cu124_ml217/bin/python

test -x "$PYTHON"
"$PYTHON" -c 'import sys; print(sys.executable); print(sys.version)'
matlab -batch "disp(version)"
```

必须先加载 `python/3.12.1`，否则环境中的 Python 可能报
`libpython3.12.so.1.0` 不存在。若 login node 的 MATLAB 因 open-files 或 Java
环境失败，用 Slurm batch job 运行，不要修改 MATLAB 安装。

某些旧 login 环境中的 `git` 不接受 `git -C`。最稳妥的写法是：

```bash
cd "$V5_REPO"
git rev-parse HEAD
git status --short
```

## 2. 已部署代码

v5 是从 clean v4.2.2 worktree 建立的独立 worktree，再应用 23-file overlay。
原 v4.2.2 worktree保持 clean；v5 worktree 保留 overlay changes，不应当把其 HEAD
单独解释成完整 v5 provenance。

部署包：

```text
$PROJECT/staging/v5_dev1_20260729/v5_dev1_overlay_20260729.tar.gz
SHA256=5702b636d96a9776eff3d702e4c5a96a973b3acc00551a8512d7e539ef8e9ea5
```

v5 已上传过一个代码快照到：

```text
zhangzh:2-25-26-dsb_E/more/zhehao/code_snapshots/
  OligoLiveFish-ML-ZZH-v5-dev1_20260803T165041Z
```

该快照的 `_UPLOAD_METADATA.txt` 中 Git HEAD 是 `UNKNOWN`，所以它必须与本指南、
baseline commit 和 overlay SHA 一起解释。文档修订后的新快照另建目录，不覆盖它。

## 3. 数据与结果位置

原始 DSB 输入与 manifests：

```bash
DSB_SOURCE=$PROJECT/data/raw_nd2/dsb_20260225_more_a
DSB_CANDIDATES=$PROJECT/work/dsb_v421_smoke_20260725T002049Z/all_usam_candidates
DSB_SCOPE=$PROJECT/manifests/dsb_final_scope_20260726
DSB_SCOPE_LIST=$PROJECT/manifests/dsb_v421_raw_all_spt19_20260726T063845Z.txt
```

已完成并必须保留的 DSB v5 smoke：

```bash
DSB_SMOKE=$PROJECT/work/v5_dev1_real_smoke_20260729T183313Z
```

published exact-pixel 219-input comparison：

```bash
PUBLISHED_MAP=$PROJECT/incoming_20260720/manuscript_reference/published_to_original_bundle_mapping.csv
PUBLISHED_RUN=$PROJECT/work/published_exact219_v422_v5_20260729T205411Z
```

Slurm arrays：

- v4.2.2：job `36529586`；219 tasks，189 completed，30 failed；每个 task 均生成
  可审计 manifest/artifact。
- v5：job `36529588`；219 tasks，190 completed，29 failed；每个 task 均生成
  可审计 manifest/artifact。

“Slurm FAILED” 不应直接等同“无结果”。这批任务中的失败多为 pipeline 后段
状态，最终比较必须以 corrected manifest/artifact audit 为准。

关键报告：

```text
$PUBLISHED_RUN/reports/completion_audit/
$PUBLISHED_RUN/reports/artifact_integrity/
$PUBLISHED_RUN/reports/v422_v5_length_comparison/
  per_sample_length_comparison.tsv
  per_baseline_length_comparison.tsv
```

已核查的长度摘要：

```text
TOTAL_SAMPLES=219
V422_NONEMPTY=189
V5_NONEMPTY=190
V422_BASELINES=833
V5_BASELINES=883
V422_TOTAL_POINTS=9317
V5_TOTAL_POINTS=9897
V422_COMPLETE_GPR_ALLELES=77
V5_COMPLETE_GPR_ALLELES=98
```

## 4. rclone

Sherlock 已配置 remote `zhangzh:`，其 root 对应 shared Drive 的
`LivevFISH data`。已验证：

```bash
rclone lsd zhangzh:
```

目标工作区：

```bash
DRIVE_ROOT='zhangzh:2-25-26-dsb_E/more/zhehao'
```

不要把 `~/.config/rclone/rclone.conf` 上传或写入日志。上传后至少运行
`rclone check`，并保存 copy log、check report、文件数和字节数。

小文件逐个上传很慢：1113 个、约 1.8 MiB 的代码文件曾耗时约 28 分钟。
结果迁移时应将“需要本地直接打开的 final TIFF/CSV/QC”保持可浏览，将大量内部
小文件按 run/FOV 另外打包并保留 SHA-256；不能只保留 archive 而丢失最终产物。

## 5. 本次返回 Sherlock 的第一步

先运行 `sherlock_handoff/scripts/01_inventory_v5_results.sh`。它只读扫描已知结果，
把 inventory 写入新的 manifest 目录，不复制或删除任何数据。把脚本最后打印的
summary 和 TSV 头部返回给 Codex，确认 source-to-FOV mapping 后再运行上传脚本。

在映射确认之前：

- published validation 可以按 run 名归档到 `published_validation/`；
- DSB 结果不得直接猜测写入 `dsb_v5_results/a/<FOV>`；
- 不确定项目只能进入 `dsb_v5_results/unmapped_review/`。

## 6. 资源与调度经验

- synthetic tests：2 CPUs、8 GiB、20 min 足够。
- 单 crop smoke 的实测运行通常约 1–6 min；24 GiB/4 CPUs 不是普遍必要条件。
- published arrays 的 2 CPUs/8 GiB 配置可运行；pending 主要来自 scheduler，而非
  MATLAB license（当时 license 仍有大量 free slots）。
- `squeue` 的 `(None)` 和预测 start time 不等于代码问题。
- array 中已完成的 tasks 应保留；retry 只提交明确未完成的 indices。
- 解析 compressed Slurm array record 时不能只按一行 aggregate state 统计 individual
  tasks；最终以 `sacct -X -j ...` 与 artifact manifest 双重核查。

## 7. 禁止事项

- 不删除、不移动、不改写 `$PROJECT/data`、原始 ND2 或原始 metadata。
- 不覆盖 v4.2.2 worktree、旧 v5 snapshot 或旧 run root。
- 不把 published/manual 与自动结果混写。
- 不根据 FOV 数字猜 source mapping。
- 不在命令输出中显示 rclone token 或配置文件内容。

