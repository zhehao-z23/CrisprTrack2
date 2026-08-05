# FOV7 修正版 Drive 试传验收记录

记录日期：2026-08-03

## 最终结论

修正版 FOV7 试传通过全部上传、校验和本地 Drive 验收门禁，可以开始人工查看，并证明修订后的 DSB 归档策略可用于全量上传。

## Sherlock 传输结果

- literal FOV：`fov7_testforZH`
- 配对样本：3 个（crop index 5、12、33）
- 软件版本：v4.2.2 与 v5-dev1
- 任务目录：6 个
- 文件：633 个
- 字节：627,469,175 bytes（0.584 GiB）
- copy failures：0
- check failures：0
- 最终门禁：`PASS`
- 成功标志：`DSB_SMOKE_FOV7_DRIVE_TEST_OK`

六个任务均满足 `COPY=0` 和 `CHECK=0`。逐任务 copy 时间为 176.7、364.7、180.1、173.0、155.8 和 118.8 秒。

## 时间与吞吐率

- 脚本内部上传和校验墙钟时间：1,307.6 秒（21 分 48 秒）
- shell 总时间：22 分 04 秒
- 有效吞吐率：0.458 MiB/s
- 按字节数外推 DSB smoke 全量：约 3 小时 10 分
- 按文件数外推 DSB smoke 全量：约 1 小时 34 分

建议为 DSB smoke 全量预留 2–4 小时。上述估算不适用于 published exact219；后者文件更多、总量更大，Google Drive API 与小文件开销可能使其明显更慢。

## 本地 Drive 独立验收

本地 Google Drive 侧确认：

- `fov7_testforZH` 顶层目录仅有 1 个；
- 版本目录仅有 `v422` 与 `v5_dev1`；
- 每个版本均有 `sample_04`、`sample_13`、`sample_16` 三个目录；
- 本地递归统计为 633 个文件、627,469,175 bytes，与 Sherlock 源完全一致。

正式审阅入口：

```text
G:\共享云端硬盘\LivevFISH data\2-25-26-dsb_E\more\zhehao\
  dsb_v5_results\a\fov7_testforZH\validation_smoke_20260729\
    v422\
    v5_dev1\
```

## 归档策略决策

保留按原始 FOV、验证批次、软件版本和任务目录分层的现有结构。跨任务改为顺序执行，单任务内部使用 16 个 transfers，从而避免多个 rclone 进程同时创建共同 Google Drive 父目录。该修正已同步到 DSB 全量脚本 `06_upload_dsb_smoke_mapped.sh`。

第一次并行试传的完整产物没有删除，保存在：

```text
dsb_v5_results\unmapped_review\
  fov7_parallel_folder_race_20260803T222741Z\
```

