# FOV7 Drive 试传归档事件记录

记录日期：2026-08-03

## 结论

第一次 FOV7 试传的六个源任务均由 `rclone copy` 返回成功，但其中三个任务的随后校验失败。失败不是源文件损坏或上传中途退出，而是四个并行 rclone 进程同时创建共同 Google Drive 父目录，产生了四个同名 `fov7_testforZH` 文件夹。Google Drive for desktop 将其显示为原名和 `(1)`、`(2)`、`(3)`。

## 证据

- 源范围：3 个配对样本、6 个 v4.2.2/v5 任务目录。
- 源文件：633 个文件，627,469,175 bytes。
- 六个 copy 状态均为 0。
- 三个通过校验：146、113、118 个 matching files。
- 三个失败校验分别报告 63、63、130 个文件缺失；缺失数等于对应任务的完整文件数。
- Drive 本地最终出现四棵同名 FOV 树；四棵树中的任务文件数和字节数在移动前合计仍为 633 和 627,469,175，说明文件没有丢失，只是被分散到了不同的同名目录对象。

首次运行耗时 907.4 秒（15 分 07 秒），包括上传与校验。该时间受到目录竞争及失败校验影响，只能作为保守参考。

## 已采取的保全措施

四个由试传新建的同名目录已从正式结果入口移入：

```text
dsb_v5_results/unmapped_review/
  fov7_parallel_folder_race_20260803T222741Z/
    duplicate_root_00/
    duplicate_root_01/
    duplicate_root_02/
    duplicate_root_03/
```

该操作没有删除文件；失败试传产物被完整保留用于审计。移动前已核对 633 个文件和 627,469,175 bytes；移动后确认正式 `dsb_v5_results/a` 下不再残留 `fov7_testforZH*` 目录，归档位置存在四个根目录和六个样本目录。Google Drive 桌面客户端在移动后立即进行深层递归枚举时仍处于索引刷新状态，因此最终远端完整性应由修订后的 Sherlock 试传完成后再次使用 rclone 审计。

## 代码修正

`06_upload_dsb_smoke_mapped.sh` 和 `07_upload_dsb_smoke_fov7_test.sh` 已改为：

- 跨任务顺序执行，每次只由一个 rclone 进程创建/解析目录；
- 单任务内部使用 16 个 transfers 和 32 个 checkers；
- 每个任务 copy 后立即进行完整 check；
- 保持总文件传输并发度，同时避免多个 rclone 进程竞争创建同一父目录。

修正后的 FOV7 试传必须满足六个任务 `COPY=0`、`CHECK=0` 和最终 `PASS`，才能批准 DSB 全量上传。

