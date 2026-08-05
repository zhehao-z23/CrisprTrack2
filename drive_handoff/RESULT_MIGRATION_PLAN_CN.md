# Sherlock v5 结果迁移计划

## 目标

将 Sherlock 已产生的 v5 结果复制到 shared Drive，使最终 TIFF、轨迹、QC 和报告
可以直接在本地打开，同时保留全部内部结果的可追溯归档。原始 ND2 不在本轮
重复复制。

## 两层归档

### A. 可直接审阅层

保留普通文件/目录，不打包：

- crop TIFF、Fiji corrected/channel TIFF 和与结果解释直接相关的 ROI TIFF；
- `baseline_longest` CSV 与 manifest；
- all-candidate trajectory CSV；
- Python/MATLAB QC PNG、SVG；
- `run_manifest.json`、metadata sidecar、mask-alignment audit、max-step audit、
  baseline-selection audit、batch summary；
- published v4.2.2/v5 comparison reports 和 source-data TSV。

### B. 全部结果归档层

对每个 run 或 DSB FOV 另建只读 archive，包含 A 层以及 MATLAB `.mat`、logs、
中间 candidates、Slurm logs 和其他内部产物。archive 同时保存 SHA-256、文件数、
字节数和 archive member list。这样既不会因 Google Drive 大量小文件而丢失完整
内部状态，也不会妨碍日常查看 A 层。

## 目标位置

```text
published_validation/
  published_exact219_v422_v5_20260729T205411Z/
    reviewable/
    archive/
    transfer_manifest/

dsb_v5_results/
  a/
    <literal FOV name>/
      <literal source/cell name>/
        reviewable v5 results
      archive/
      transfer_manifest/
  unmapped_review/
```

DSB 的 `<literal FOV name>` 必须来自 source map/metadata 证据，不能从任务编号推断。

## 顺序

1. 运行 `01_inventory_v5_results.sh`：只读收集 sizes、extensions、run manifests
   和 symlinks。
2. 对照 `SOURCE_ND2_MAP.tsv`，建立 `SHERLOCK_TO_DRIVE_RESULT_MAP.tsv`。
3. 人工审阅所有 ambiguous mappings；未解决的行进入 `unmapped_review`。
4. 为 published validation 生成 reviewable include list 和完整 archive。
5. 为每个 DSB FOV 生成 reviewable include list 和完整 archive。
6. 用 `rclone copy` 上传到从未使用的新目录；不得使用会删除远端文件的 `sync`。
7. `rclone check --one-way`，并核对 files/bytes/checksums。
8. 写 `ARCHIVE_MANIFEST.tsv` 和 `acceptance_summary.txt`；只有全部 gate 通过才能把
   状态标成 complete。

## symlink 规则

Sherlock run root 可能通过 symlink 指向外部 crop TIFF 或 results。不能直接假设
`rclone copy` 会包含其 target。inventory 必须先列出每条 symlink。之后：

- 对已确认的 TIFF target，显式复制到 reviewable 层；
- 不对未知目录 symlink 使用全局 `--copy-links`；
- 如果使用 `--copy-links`，必须先证明它不会递归带入 ND2 或整个原始数据树；
- transfer manifest 同时记录 link path、target path 和最终 Drive path。

## 禁止项

- `rclone sync`、`move`、`purge` 或任何删除命令；
- 修改 Sherlock run manifest 里的原始路径；
- 把 v4.2.2 与 v5 输出覆盖到同一目录；
- 只保存压缩包而不提供可直接打开的最终图/表/TIFF；
- 在 inventory 尚未确认前开始 DSB 正式归档。

