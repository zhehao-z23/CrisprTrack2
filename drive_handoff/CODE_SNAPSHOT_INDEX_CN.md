# 代码与项目快照索引

当前正式批次：`20260803T175830Z`。逐路径、源路径和字节数见
`../manifests/CODE_SNAPSHOT_INDEX_20260803T175830Z.tsv`；Git 自动探测修正与
hash 验收见 `PROVENANCE_CN.md`。

| 快照 | 用途 | Git provenance | 文件数 | 字节数 |
| --- | --- | --- | ---: | ---: |
| `ref_3e65bff_code_20260803T175830Z` | 原始四阶段 README/CrisprTrack 格式和参考代码 | `3e65bff66d13fbcf61ccd4dcacd8ff3d5b008839` | 44 | 708,553 |
| `v416_fix_5d1aa1b_20260803T175830Z` | v4.1.6 空轨迹/运行时修复里程碑 | `5d1aa1b02d84adb73619a6be45b1ead625274e7f` | 66 | 894,164 |
| `v416_demo_6b3e57f_20260803T175830Z` | Sherlock demo/handoff 里程碑 | `6b3e57f3d27c40755e4aff603f5c5ab9e21508ec` | 77 | 917,903 |
| `v422_833515e_20260803T175830Z` | candidate-preserving QC、timestamps、convex-hull；v5 clean baseline | `833515ee7a3da2ced4b34925c85107d54c006918` | 81 | 1,028,221 |
| `v5_dev1_docs_20260803T175830Z` | v5 global-gap 代码、完整新 README、history、deployment/tests | baseline `833515e…` + v5 overlay + docs | 107 | 1,190,151 |
| `sherlock_handoff_20260727_20260803T175830Z` | Sherlock 操作、历史记忆和 scripts | 文档快照 | 16 | 101,683 |
| `phase2_current_20260728_20260803T175830Z` | 当前 Phase2 分析、图、source data、reports、provenance | 分析项目快照 | 242 | 21,210,847 |

每个正式目录都包含：

- `_SNAPSHOT_METADATA.txt`：源路径、模式、VERSION、文件数和字节数；
- `_FILE_SHA256.tsv`：除自身以外每个文件的 SHA-256。

本批次共 633 个实际文件；626 个 manifest rows；复核后的 hash failure 为 0。
code-only 快照不含 ND2/TIFF，也不重复 `trajectory_extraction/example_data`。

## 另外保留的对象

- `OligoLiveFish-ML-ZZH-v5-dev1_20260803T165041Z`：先前从 Sherlock 上传的
  v5 snapshot。它没有被覆盖；其 Git metadata 为 `UNKNOWN`，解释时必须同时用
  v4.2.2 baseline commit 和 overlay SHA。
- `_migration_attempts/`：三次中止的复制尝试和旧脚本，只用于迁移审计，不是
  正式版本。
- `git_history/`：预留给 Sherlock 生成的 `git bundle --all`；当前 pending。

不要把 `OligoLiveFish-ML-ZZH-v4.1.2-release` 当成 v4.1.2 权威快照：该本地目录
实际 HEAD/VERSION 已到 v4.1.5。完整提交主线见
`../project_history/DEVELOPMENT_HISTORY_CN.md`。

