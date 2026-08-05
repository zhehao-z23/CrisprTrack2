# Phase2 current snapshot 说明

Drive 正式快照：
`code_snapshots/phase2_current_20260728_20260803T175830Z`。

迁移前只读审计发现，Phase2 项目中旧的 `ACTIVE_PROJECT_MANIFEST.csv` 已落后于
7 月 28 日后的科学审阅修订：相对旧 manifest，约 60 个已列项目的 size/hash
发生变化，并新增 7 个文件（包括 `SCIENTIFIC_REVIEW_REVISION_CN.md`、
`FIGURE_INTERPRETATION_CN.md` 等）。这是项目继续修订后的正常状态，不是本次
Drive 复制导致的变化。

因此：

- 旧 handoff tar、旧 active manifest 和旧 `archive/packages` 仅是历史快照；
- 2026-08-03 Drive snapshot 及其 `_FILE_SHA256.tsv` 是当前迁移时刻的权威文件
  清单；
- `2026-07-27_OligoLiveFISH_reproduce` 已由 Phase2 迁移/封存，不再重复复制为
  第二个裸目录；
- 以后继续修改 Phase2 时，应新建带时间戳的 snapshot/manifest，不覆盖本批次。

