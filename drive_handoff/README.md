# Zhehao OligoLiveFISH / DSB 工作区

本目录是 OligoLiveFish-ML 自动轨迹提取、published validation 和 DSB 分析的
Google Drive 协作入口。建立日期：2026-08-03。

## 目录

```text
zhehao/
  README.md
  code_snapshots/          只读、带 provenance 的重要代码快照
  project_history/        开发历史、归档契约和版本索引
  manifests/              ND2 映射、快照清单和迁移清单
  sherlock_handoff/       Sherlock 状态、返回指南和可粘贴脚本
  published_validation/   published exact-pixel v4.2.2/v5 验证结果
  dsb_v5_results/
    a/                    按 more/a 的 literal FOV 名归档的正式 DSB 结果
    unmapped_review/      来源尚未严格确认的结果；禁止用于正式生物分析
```

## 权威边界

- 原始 DSB 数据位于相邻的 `more/a`，始终只读。
- 原始 ND2 默认不在本目录重复保存。`manifests/SOURCE_ND2_MAP.tsv` 给出逐 FOV
  的原始 Drive 路径、字节数和时间戳。
- 任何新结果必须写到 `zhehao`，不得改名、移动或覆盖 `more/a` 中的文件。
- FOV、ND2、cell/crop 的字面名称全部保留；不能自动补零或按数字重新命名。
- Sherlock metadata 原件保留。若需要本地路径映射，另写带 `_drive` 或
  `.drive.json` 后缀的 derived copy，不能改原件。
- published/manual、historical v3、v4.2.2 和 v5 dev1 是四个独立 provenance
  层，不能混在同一结果目录中。

完整规则见
`project_history/DRIVE_ARCHIVE_CONTRACT_CN.md`。

## 当前版本

- v5：`5.0.0-dev1-trackmem-global-gap`
- clean baseline：v4.2.2 commit
  `833515ee7a3da2ced4b34925c85107d54c006918`
- v5 部署 overlay SHA-256：
  `5702b636d96a9776eff3d702e4c5a96a973b3acc00551a8512d7e539ef8e9ea5`

v5 唯一算法改动是：全局空检测帧数不超过 `trackMem` 时不再提前切断轨迹；
超过 `trackMem` 仍切断。检测、ROI、Gaussian localization、`trackMem=3`、
固定 `max_disp`、minimum length 和 baseline selection 均未改变。

## 已完成验证的摘要

同一批 219 个 exact-pixel published inputs 上，v4.2.2 → v5：

- non-empty samples：189 → 190；
- baselines：833 → 883（+6.00%）；
- total points：9,317 → 9,897（+6.23%）；
- mean points per baseline：11.18 → 11.21（+0.21%）；
- complete G/P/R alleles：77 → 98；
- paired per-sample longest mean：12.70 → 12.84（+1.04%）。

因此目前支持的结论是“恢复更多 baseline 和完整 G/P/R 组合”，而不是“所有
轨迹明显变长”。详细解释见
`project_history/DEVELOPMENT_HISTORY_CN.md`。

## 从哪里开始

1. 看代码：`code_snapshots/INDEX_CN.md`。
2. 看版本与科学边界：`project_history/DEVELOPMENT_HISTORY_CN.md`。
3. 看归档规则：`project_history/DRIVE_ARCHIVE_CONTRACT_CN.md`。
4. 返回 Sherlock：`sherlock_handoff/SHERLOCK_STATE_AND_RETURN_GUIDE_CN.md`。
5. 检查数据映射：`manifests/SOURCE_ND2_MAP.tsv`。

## 当前尚未完成

- Sherlock 上的 v5 结果还需要先生成只读 inventory 并确认 source-to-FOV
  映射，再复制到本目录。
- DSB 全量 v5 尚未运行；当前 DSB smoke 必须保存，但不能冒充全量结果。
- published v4.2.2/v5 output 已完成运行，仍需归档并继续与人工轨迹/论文关键
  统计量比较。
- ND2 不在本轮复制；若以后确需离线副本，应另做容量、checksum 和去重计划。

