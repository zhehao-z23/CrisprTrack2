# OligoLiveFish-ML 自动轨迹提取开发历史

## 1. 文档目的

本文记录从参考实现到 v5 dev1 的每一步改进、改动边界、验收依据和
已知限制。它同时充当提交历史和科学 provenance；不能用它替代源码、
运行 manifest 或原始数据。

当前版本为 `5.0.0-dev1-trackmem-global-gap`。v5 从干净的 v4.2.2
基线 commit
`833515ee7a3da2ced4b34925c85107d54c006918` 建立独立 worktree，随后以
未提交 overlay 的形式部署和验证。因此，归档时必须同时记录基线 commit、
`VERSION`、changed-files 清单和文件 SHA-256，不能只写一个 Git HEAD。

## 2. 不可修改原则

- 原始 ND2、原始 TIFF、原有 sidecar、micro-SAM mask 和人工轨迹均只读。
- 新版本写入独立目录；不原地升级或覆盖 v3/v4 结果。
- 人工轨迹只用于事后比较，不参与自动检测、ROI、候选过滤或 baseline 选择。
- 每次比较必须区分四个 provenance 层：published/manual、historical v3、
  audited v4.2.2、v5 dev1。
- 轨迹更长只是 baseline 选择指标，不等于轨迹在生物学上必然正确。

## 3. 版本总表

| 版本 | 日期 | provenance | 主要目标 | 科学参数变化 | 验收状态 |
| --- | --- | --- | --- | --- | --- |
| reference / v3 | 项目原始版本 | `OligoLiveFish-ML-reference` snapshot | 复原 CrisprTrack 与论文风格工作流 | 历史规则 | 只作为参考层 |
| v4.0.0-anchor-roi | 2026-07-14 | changelog snapshot | 用真实 micro-SAM mask 和 anchor-defined static ROI 取代生产路径中的旧 reference matching | ROI 和 baseline 规则改变 | FOV15 逐项回归通过 |
| v4.1.0–v4.1.6 | 2026-07-18 至 2026-07-20 | versioned local snapshots | 锁定两类实验 profile，并修复空结果、单轨迹、编码和 MATLAB R2022b 兼容问题 | profile contract 改变；SPT 数值参数不变 | 本地与 Sherlock regression 通过 |
| v4.2.0-candidate-preserving-qc | 2026-07-22 | changelog + manifests | 保存全部 micro-SAM 候选，并把自动 gate 与人工决策分离 | 不改变已锁定 v4.1.6 结果，除非显式使用新 candidate view | policy/audit tests 通过 |
| v4.2.1-nd2-frame-timestamps | 2026-07-24 | changelog + sidecar schema | 保存逐帧 ND2 时间戳，标记 nonuniform sampling | metadata 更完整；当前 linker 仍使用代表性 interval | timestamp tests 通过 |
| v4.2.2-convex-hull-roi | 2026-07-25 | commit `833515e…` | 增加 `tube`/`convex_hull` 静态 ROI 选项并隔离输出 | 新的可选 ROI geometry；默认 tube 不变 | clean baseline + ROI tests 通过 |
| v5.0.0-dev1-trackmem-global-gap | 2026-07-29 | v4.2.2 commit + overlay manifests | 让 `trackMem` 对全局空检测帧真正生效 | 仅改变全局 gap 预切段边界 | synthetic、DSB smoke、219-input benchmark 已运行 |

详细文件级改动另见 `CHANGELOG.md`、`V5_BASELINE_MANIFEST.csv` 和
`V5_DEV1_CHANGED_FILES.csv`。

### Git 提交主线

以下是本地 Git 历史中可核查的关键提交；短 hash 仅用于阅读，归档 manifest
应记录完整 hash。

| 日期 | commit | 内容 |
| --- | --- | --- |
| 2026-07-14 | `79c0916` | v4.0 anchor-ROI |
| 2026-07-18 | `ed0d063` | v4.1 locked experiment profiles |
| 2026-07-18 | `f597b78` | v4.1.1 Sherlock runtime fixes |
| 2026-07-18 | `cfce4d3` | v4.1.2 empty linked-trajectory handling |
| 2026-07-18 | `4b4e8f4` | v4.1.3 empty legacy `track.m` handling |
| 2026-07-18 | `e7a3da2` | v4.1.4 assigned empty output |
| 2026-07-19 | `ad1a29e` | v4.1.5 single-track renumbering |
| 2026-07-20 | `5d1aa1b` | v4.1.6 empty segmented-list handling |
| 2026-07-20–21 | `d40de8d` → `ca49b13` → `f751d6e` → `6b3e57f` | Sherlock demo、license、module 与 login-shell handoff |
| 2026-07-22 | `5da74a9` → `75b9ffd` → `93b7366` | candidate-preserving QC 与 policy views |
| 2026-07-23 | `0637d86` → `50d8667` → `3645c6c` → `d9f7fef` → `9412f1f` → `7d84881` | QC、pairing、recovery 和 report packaging |
| 2026-07-24 | `6418406` → `e470514` | exact ND2 timestamps 与 metadata audit |
| 2026-07-25 | `833515e` | v4.2.2 convex-hull ROI；v5 唯一 clean baseline |
| 2026-07-29 | non-Git overlay | v5 dev1 global-gap change；overlay SHA-256 `5702b636d96a9776eff3d702e4c5a96a973b3acc00551a8512d7e539ef8e9ea5` |

## 4. 参考实现与 v3

参考项目提供了 ND2 到轨迹、细胞特征和轨迹到特征建模的四阶段结构。
历史轨迹路径包含基于参考距离的匹配、2,000 nm filter 和 greedy
assignment。它对论文复现仍有价值，但 v4/v5 生产 runner 不调用这些规则。

这一层保留的原因是：人工发布轨迹、历史代码输出和新的自动输出并非同一
数据产品。任何“复现”都要先确认比较的是像素、候选、最终轨迹还是论文统计量。

## 5. v4.0：anchor ROI 生产路径

### 要解决的问题

旧生产路径可能用强度/Otsu 边界替代已有的 micro-SAM instance mask，且最终
匹配依赖 reference distance。这样既弱化了 segmentation provenance，也不利于
在未知 DSB 数据上工作。

### 主要修改

- 将 crop 与其 exact micro-SAM instance mask 明确关联。
- 按 Fiji drift 对 mask 逐帧对齐，再膨胀 5 px。
- 锁定 anchor channel；完整 anchor 路径形成一次性的 static irregular ROI。
- ROI 只限制 peak admission；2-D Gaussian fitting 仍使用完整邻域像素。
- 保留全部 MATLAB candidates；按 allele/channel 选择确定性的最长 baseline。
- 去除生产路径中的旧 reference-distance matcher、2,000 nm filter 和 greedy
  assignment。
- 从 TIFF metadata 和物理先验推导并审计 `max_disp`。

### 验收

FOV15 的 calibration、mask alignment、anchor 轨迹、27 个候选 CSV 和 6 个
baseline 均与获批实验逐项比对；MATLAB 可输出 time-coloured PNG/SVG。

## 6. v4.1：实验 profile 与运行时修复

### profile contract

生产路径只接受两个 profile：

- `chr3_sites_2_3_4`：四通道，raw C2 / Site 2 / A488 为 anchor；
- `dsb_53bp1_site1_site2`：三通道，raw C2 / Site 2 / Purple 为 anchor。

运行前硬校验 channel count、ND2 channel order、文件名证据、sidecar 和 anchor
身份。输出按 profile 隔离。

### v4.1.1–v4.1.6 修复

连续修复了以下技术失败：MATLAB 无 retained trajectory、单 retained trajectory、
分段后为空、literal Unicode spatial unit、CSV text contract、R2022b SVG 输出。
这些修复处理异常分支，不改变 threshold、`trackMem`、`max_disp`、minimum
trajectory length 或 baseline selection。

## 7. v4.2：候选保存、时间戳和 ROI geometry

### v4.2.0 candidate-preserving QC

所有原始 micro-SAM instances 被保存在独立 archive，并获得稳定 candidate ID。
`candidate_selection_manifest.csv` 记录 QC、排除原因和空白的人工决策列。
`strict`、`no_badqc`、`publicationlike` 和 `all` 仅是可重建 view，不删除候选。

### v4.2.1 exact ND2 timestamps

从每个 timepoint 的 ND2 metadata 提取相对时间轴；sidecar 同时保存完整时间轴、
observed interval 和代表性 median interval。nonuniform timestamps 会被标记，
但 v5 dev1 的 MATLAB linker 尚未使用逐步可变时间间隔。

### v4.2.2 convex-hull ROI

增加 `--roi-geometry tube|convex_hull`。`convex_hull` 先填补 anchor path 的
concavity，再膨胀并与 aligned micro-SAM support 相交。结果写入独立的
`anchor_roi_v4_<profile>_convex_hull`，不会覆盖默认 tube 结果。

## 8. v5 dev1：在 trackMem 范围内跨越全局空帧

### 问题

legacy `track.m` 原本支持粒子短暂消失，但 wrapper 在调用它之前会在每个
全局无检测帧处预切段，使 `trackMem=3` 对这种 gap 实际失效。

### 唯一算法改动

`trajectory_extraction/pipeline/matlab_deps/spt_track.m` 的边界从：

```matlab
% v4.2.2
jump = find(t_posnew);
```

改为：

```matlab
% v5 dev1
jump = find(t_posnew > param.mem);
```

也就是说，全局连续空检测帧数不超过 `trackMem` 时交给原 linker 处理；超过
`trackMem` 时仍然硬切段。`trackMem=0` 时保持 v4 行为。

### 明确没有修改的内容

- first-frame auto threshold 与 particle detection；
- 2-D Gaussian localization；
- micro-SAM mask、anchor 和 ROI geometry；
- `trackMem=3` 的数值；
- metadata/physics-derived fixed `max_disp`；
- `mtl=3` minimum trajectory length；
- 候选导出和 deterministic longest baseline selection。

v5 dev1 也没有实现 timestamp-aware linker、按 gap 放大的搜索半径、轨迹片段
二次 stitching 或人工轨迹驱动的选择。

### 测试

- Python source-contract 与 version-contract tests；
- MATLAB one/two-frame gap、exact memory boundary、two-particle identity tests；
- 临时 TIFF 的 threshold → detection → empty frame → linking integration test；
- 同一 TIFF 的 v4.2.2/v5 control；
- Sherlock synthetic preflight 和 DSB real-data smoke。

## 9. 219 个 exact-pixel published inputs 的实测结果

比较严格使用相同的 219 个 crop TIFF、相同 sidecar/mask 和相同参数，只切换
v4.2.2 与 v5 linking implementation。

| 指标 | v4.2.2 | v5 dev1 | 变化 |
| --- | ---: | ---: | ---: |
| non-empty samples | 189 | 190 | +1 rescue |
| baselines | 833 | 883 | +50 / +6.00% |
| total trajectory points | 9,317 | 9,897 | +580 / +6.23% |
| mean points per baseline | 11.18 | 11.21 | +0.21% |
| complete G/P/R alleles | 77 | 98 | +21 |
| samples with complete G/P/R | 61 | 75 | +14 |

在 189 个两版均非空的样本中，per-sample longest-track sum 为 2,401 和
2,426，对应均值 12.70 和 12.84 points（+1.04%）。样本级 longest verdict 为
178 unchanged、11 longer、0 shorter；另有 1 个 v5 rescue。shared baseline 层面
为 725 equal、107 longer、1 shorter，另增加 50 个 v5 baselines。

因此，当前证据支持的结论是：v5 主要恢复了更多 baseline 和完整三通道 G/P/R
组合；典型单条轨迹的平均长度只温和上升。不能写成“所有轨迹都变长”或“v5
已全面替代 v4.2.2”。

## 10. DSB smoke 的定位

DSB smoke 用于确认真实三通道数据可运行、gap 逻辑能产生预期 rescue，以及
资源配置可行。它不是人工匹配的 published benchmark，也不能单独证明轨迹
生物学真实性。已完成结果应保留，待 published comparison 验收后再进入 DSB
全量分析。

## 11. 运行环境证据

| 环境 | Python | MATLAB | 用途 |
| --- | --- | --- | --- |
| 本地开发 | 3.12.11 | R2025b Update 1 | source tests 和 MATLAB regressions |
| Sherlock production | 3.12.1 | R2022b | synthetic、DSB smoke、219-input benchmark |

Sherlock v5 worktree：
`/scratch/users/zhangzh/oligolivefish_nd2_to_trajectory/code/OligoLiveFish-ML-ZZH-v5-dev1`。
Google Drive 归档只保存可迁移信息，不保存 rclone token、密码或 credential 文件。

## 12. 已知限制与下一步

1. 完成 published/manual 轨迹的坐标、帧号、长度和论文关键统计量比较。
2. 对 v5 新增和延长的轨迹做可视化 overlay，区分 gap recovery 与 identity switch。
3. 必要时研究 timestamp-aware linking 和 gap-scaled radius；必须作为新的版本，
   不能静默修改 v5 dev1。
4. 对 DSB 全量运行建立逐 FOV source mapping、checksum、失败重试和 archive manifest。
5. 所有结果归档保持原始 FOV/ND2/cell 字面命名；映射不确定时进入人工审阅区，
   不猜测。
