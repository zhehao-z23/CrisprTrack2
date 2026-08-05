# 2026-08-03 代码快照 provenance 补充说明

Drive 快照批次：`20260803T175830Z`。

## 为什么需要本说明

当前 Windows 环境没有可调用的 `git.exe`。快照构建器因此把自动探测字段写成
`GIT_HEAD=NO_GIT`；这表示“构建时未能调用 Git”，不表示这些版本没有 Git
历史。每份 `_FILE_SHA256.tsv` 仍已对 Drive 中的实际文件逐项复核，hash failure
为 0。

以下 provenance 来自迁移前的只读 worktree 审计，是解释本批快照时的权威
Git 修正：

| Drive snapshot prefix | source | Git HEAD / baseline | branch / status |
| --- | --- | --- | --- |
| `ref_3e65bff_code_` | `OligoLiveFish-ML-reference` | `3e65bff66d13fbcf61ccd4dcacd8ff3d5b008839` | `main`；README 有 1 行 trailing-space dirty，快照保留当时文件 |
| `v416_fix_5d1aa1b_` | `OligoLiveFish-ML-ZZH-v4.1.6-fix` | `5d1aa1b02d84adb73619a6be45b1ead625274e7f` | `fix/v4.1.6-empty-trajlist`；clean |
| `v416_demo_6b3e57f_` | `OligoLiveFish-ML-ZZH-v4.1.6-demo` | `6b3e57f3d27c40755e4aff603f5c5ab9e21508ec` | `demo/v4.1.6-sherlock-handoff`；clean |
| `v422_833515e_` | `OligoLiveFish-ML-ZZH-v4.2-candidate-qc` | `833515ee7a3da2ced4b34925c85107d54c006918` | `feature/v4.2.2-convex-hull-roi`；clean |
| `v5_dev1_docs_` | `OligoLiveFish-ML-ZZH-v5` | v4.2.2 baseline `833515ee7a3da2ced4b34925c85107d54c006918` + v5 overlay + 2026-08-03 docs | snapshot 无 `.git`；不能用 baseline HEAD 代替 v5 version |

v5 overlay SHA-256：
`5702b636d96a9776eff3d702e4c5a96a973b3acc00551a8512d7e539ef8e9ea5`。

`sherlock_handoff_20260727_*` 和 `phase2_current_20260728_*` 是文档/分析项目
快照，本身不声明独立 Git HEAD。

## 本批次完整性

正式索引：
`manifests/CODE_SNAPSHOT_INDEX_20260803T175830Z.tsv`。

逐快照复核结果：

| snapshot | manifest rows | actual files | SHA-256 failures | ND2 | TIFF |
| --- | ---: | ---: | ---: | ---: | ---: |
| `ref_3e65bff_code_20260803T175830Z` | 43 | 44 | 0 | 0 | 0 |
| `v416_fix_5d1aa1b_20260803T175830Z` | 65 | 66 | 0 | 0 | 0 |
| `v416_demo_6b3e57f_20260803T175830Z` | 76 | 77 | 0 | 0 | 0 |
| `v422_833515e_20260803T175830Z` | 80 | 81 | 0 | 0 | 0 |
| `v5_dev1_docs_20260803T175830Z` | 106 | 107 | 0 | 0 | 0 |
| `sherlock_handoff_20260727_20260803T175830Z` | 15 | 16 | 0 | 0 | 0 |
| `phase2_current_20260728_20260803T175830Z` | 241 | 242 | 0 | 0 | 0 |

每个 actual-files 数量比 manifest rows 多 1，是因为 `_FILE_SHA256.tsv` 不对
自身做递归 hash。

## 过滤边界

code-only 快照整体排除了 `trajectory_extraction/example_data`，避免为每个版本
重复保存相同的大型示例影像和长路径派生产物。源码、README、tests、deployment
和 provenance 保留。Phase2 current snapshot 保留 outputs、source data、reports 和
provenance，只排除了旧 `archive/packages`；Sherlock handoff 排除了单个约 221 MiB
的 `archive_core_file_list.txt`。

三个早期构建尝试因 offline-placeholder/长路径中止，目录名已明确带
`INCOMPLETE_DO_NOT_USE`，没有进入正式 index，也不得作为代码版本使用。它们被
保留而未删除，以完整记录迁移过程。

## 完整 Git 历史

由于本地没有 Git executable，完整 `git bundle --all` 尚未在本地生成。
`sherlock_handoff/scripts/03_upload_git_history_bundle.sh` 会在 Sherlock 的原 Git
worktree 中创建、verify、hash 并上传 bundle；完成前，上表 commit 与当前代码
快照共同构成现阶段的版本 provenance。

