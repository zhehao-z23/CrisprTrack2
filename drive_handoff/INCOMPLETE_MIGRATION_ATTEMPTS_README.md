# 迁移尝试归档：请勿作为正式版本使用

这里保存 2026-08-03 第一次建立 Drive 工作区时中止或被后续脚本取代的产物。
保留它们是为了不删除已有文件并记录迁移过程；它们没有进入正式
`CODE_SNAPSHOT_INDEX_20260803T175830Z.tsv`。

- `175519Z`：参考仓库中存在不可读取的 cloud-placeholder/失效文件，复制中止。
- `175614Z`：增加 reparse 检查后仍遇到不可读取 placeholder，复制中止。
- `175705Z`：已跳过 placeholder，但命中 Windows/Drive 长路径限制，复制中止。
- `01_inventory_*_initial_without_symlink_audit.sh`：可运行，但缺少结果树 symlink
  盘点；标准脚本已加入该检查。

正式可用快照均带时间戳 `20260803T175830Z`，并在每个目录中包含
`_SNAPSHOT_METADATA.txt` 与 `_FILE_SHA256.tsv`。完整解释见上一级
`PROVENANCE_CN.md`。

