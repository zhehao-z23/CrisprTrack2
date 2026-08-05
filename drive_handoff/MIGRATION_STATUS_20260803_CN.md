# Google Drive 工作区迁移状态（2026-08-03）

## 已完成

1. 建立协作入口：
   `G:\共享云端硬盘\LivevFISH data\2-25-26-dsb_E\more\zhehao`。
2. 建立 `code_snapshots`、`project_history`、`manifests`、
   `sherlock_handoff`、`published_validation`、`dsb_v5_results/a` 和
   `dsb_v5_results/unmapped_review`。
3. 改写 v5 根 README，使其恢复参考项目的四阶段结构。
4. 按参考 CrisprTrack README 骨架完成 675 行 trajectory extraction 文档。
5. 完成 v4.0→v5 commit/改进历史、v5 科学边界和 219-input benchmark 解释。
6. 建立 30-row `SOURCE_ND2_MAP.tsv`；已与 30 个原始 ND2 逐文件核对：
   - missing：0；
   - size mismatch：0；
   - 总字节：235,994,497,024；
   - ND2 被复制到 `zhehao`：0。
7. 建立 7 个正式代码/项目快照和逐文件 SHA-256：
   - manifest rows 总计：626；
   - actual files 总计：633（每份多出的 1 个文件是 hash manifest 自身）；
   - SHA-256 failures：0；
   - code snapshot 内 ND2：0；
   - code snapshot 内 TIFF：0。
8. 保留早期 Sherlock 上传的 v5 snapshot，没有覆盖。
9. 将三次中止的本地构建尝试隔离到 `_migration_attempts`；它们未进入正式索引。
10. 完成 Sherlock 状态/返回指南、只读 result inventory 脚本、上传 preview
    和 Git bundle 上传脚本。

正式代码索引：
`manifests/CODE_SNAPSHOT_INDEX_20260803T175830Z.tsv`。

## 尚未完成

1. Sherlock 上的 published exact219 与 DSB smoke 结果尚未复制到 Drive。
2. 需要先运行 `sherlock_handoff/scripts/01_inventory_v5_results.sh`，确认：
   - 总文件数/字节数；
   - TIFF 数量/字节数；
   - symlink 及其 target；
   - run manifest 中的 crop/source-to-FOV 映射。
3. published validation 可在 inventory 通过后按 run 名整体归档。
4. DSB smoke 必须按 literal source FOV 映射；无法确认的行只能进入
   `unmapped_review`。
5. DSB 全量 v5 尚未运行，不能在 Drive 中标记为 complete。
6. 完整 Git `bundle --all` 待在 Sherlock 执行
   `03_upload_git_history_bundle.sh`。

## 当前结论

本地/Drive 的代码、文档和原始 ND2 指针迁移已经验收通过；结果数据迁移尚处于
“remote inventory pending”，没有伪造目录或声称已经上传。下一次工作应从
Sherlock inventory 输出继续，不需要重新盘点本地代码或重建 Drive 框架。

