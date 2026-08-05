# Sherlock v5 结果 inventory 报告（2026-08-03）

Sherlock inventory：
`/scratch/users/zhangzh/oligolivefish_nd2_to_trajectory/manifests/drive_migration_inventory_20260803T213531Z`。

## 汇总

| run | files | bytes | TIFF | TIFF bytes | CSV | JSON | PNG | SVG | MAT | run manifests |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| published exact219 v4.2.2/v5 | 31,519 | 23,750,223,546 | 6,388 | 22,820,032,322 | 9,269 | 3,066 | 3,468 | 1,716 | 3,396 | 438 |
| DSB smoke v4.2.2/v5 | 2,795 | 5,476,160,619 | 450 | 5,337,423,204 | 1,131 | 188 | 299 | 177 | 240 | 32 |
| total | 34,314 | 29,226,384,165 | 6,838 | 28,157,455,526 | 10,400 | 3,254 | 3,767 | 1,893 | 3,636 | 470 |

两棵结果树均未发现 symlink，因此不会出现 rclone 只复制 link、漏掉外部 TIFF
target 的问题。TIFF 数量远大于原始 crop 数量，因为这里包括两版输入副本、Fiji
corrected/channel TIFF、mask/ROI TIFF 和其他中间结果；不能把 6,388 解释为
6,388 个独立生物样本。

## Gate 判断

### Published exact219

- 438 manifests = 219 inputs × 2 versions；
- 所有文件都是结果树中的实体文件；
- 可以按独立 run 直接迁入 `published_validation/`；
- 迁移必须保留 failed/interrupted run 的 artifacts，不应只复制 status=complete。

结论：`READY_FOR_COPY`。

### DSB smoke

- 32 manifests = 16 cells × 2 versions；
- run manifest 中的 `source_nd2` 字段为空；
- crop sidecar 按代码合同应包含 `source_nd2`、`stem`、`crop_index` 和 bbox；
- 在完成 sidecar→`SOURCE_ND2_MAP.tsv` 的唯一匹配前，不进入正式
  `dsb_v5_results/a/<literal FOV>`。

结论：`MAPPING_AUDIT_REQUIRED`。

下一步使用 `04_audit_dsb_smoke_mapping.sh`。通过条件为 32 个 crop/sidecar、
32 个唯一映射目标、16 个完整 v4.2.2/v5 pairs、0 unresolved。脚本同时把原始
inventory 和 mapping TSV 上传到 Drive 的 `sherlock_handoff` 下。

