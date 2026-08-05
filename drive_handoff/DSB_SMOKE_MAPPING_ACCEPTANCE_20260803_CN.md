# DSB smoke 结果到 Google Drive 的映射验收记录

记录日期：2026-08-03

## 结论

DSB smoke 结果的归档映射已经通过最终门禁，可以进入实际上传阶段。

- 16 个样本均同时具有 v4.2.2 与 v5-dev1 结果，共 32 个独立任务目录。
- 32 个任务全部解析到唯一的 Drive 目标目录；未解析和需人工复核的条目均为 0。
- 32 个 crop TIFF 与 32 个 sidecar 均存在。
- 映射任务目录合计 2,719 个文件、5,476,080,872 bytes。
- 运行根目录还包含任务目录之外的 76 个文件、79,747 bytes；上传脚本将其单独归档为 run provenance，不会遗漏，也不会混入样本结果目录。
- 上传保留成功、失败或中断任务的现有产物，以保证审计链完整；不会把失败任务误标成成功结果。

## 映射结构

每个配对样本按以下结构归档：

```text
dsb_v5_results/a/<原始 FOV>/validation_smoke_20260729/v422/<任务目录>/
dsb_v5_results/a/<原始 FOV>/validation_smoke_20260729/v5_dev1/<任务目录>/
```

运行级、非任务目录文件单独归档到：

```text
dsb_v5_results/run_provenance/v5_dev1_real_smoke_20260729T183313Z/
```

该设计保留 `more/a` 的 FOV 命名，同时明确区分原始数据、验证批次、软件版本与运行级 provenance。

## 覆盖的原始 FOV

共覆盖 10 个原始 FOV：

1. `fov5 2h`
2. `fov7_testforZH`
3. `fov10_2.5h`
4. `fov12_2.5h`
5. `fov17_3h_forZH`
6. `fov19_3.5h`
7. `fov21_3.5h`
8. `fov23_4h`
9. `fov28_4.5h_5s`
10. `fov29_4.5h`

## 审计证据

Sherlock 本地映射目录：

```text
/scratch/users/zhangzh/oligolivefish_nd2_to_trajectory/manifests/dsb_smoke_drive_mapping_20260803T215636Z
```

Drive 映射目录：

```text
2-25-26-dsb_E/more/zhehao/sherlock_handoff/mappings/dsb_smoke_drive_mapping_20260803T215636Z
```

门禁结果：

```text
MAPPED_ROWS=32
UNRESOLVED_ROWS=0
UNIQUE_PAIRS=16
COMPLETE_V422_V5_PAIRS=16
REVIEW_PAIRS=0
UNIQUE_TARGET_DIRS=32
FINAL_GATE=PASS
```

## 上传安全约束

实际上传脚本只执行 `rclone copy` 与随后逐目录 `rclone check`：

- 不执行 `sync`、`move`、`purge` 或删除操作；
- 不修改 Sherlock 运行结果与 metadata；
- 不复制 ND2；
- 可以安全重跑，已完整上传的文件会被复用；
- 只有 32 个任务目录全部复制并校验通过，且 run provenance 数量和字节数一致时，最终门禁才会为 `PASS`。

