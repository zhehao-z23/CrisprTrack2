# DSB ND2 metadata 与当前运行范围审计

记录日期：2026-08-03

## 一句话结论

DSB 数据不是“完全没有跑完”，而是存在三层不同范围：30 个 ND2 均已完成分割和候选 crop 导出；其中 19 个时间轴合格 FOV 的 1,031 个候选做过旧版 v4.2.1 大规模轨迹运行；当前 v5-dev1 只在 10 个 FOV 中选择了 16 个 crop 做配对 smoke 比较。Drive 目前正式上传的只有 FOV7 的 3 个 crop、共 6 个 v4.2.2/v5 任务目录。

## 总体范围

- 原始 ND2：30 个，235,994,497,024 bytes（219.787 GiB）。
- ND2 header：30/30 可读取。
- 分割和 uSAM 候选导出：30/30 FOV，1,614 个候选 crop。
- 当前固定步长 SPT 合格：19 个 FOV，1,031 个候选 crop。
- 没有进入旧版固定步长 SPT：11 个 FOV，其中 9 个时间轴非均匀、2 个只有单时间点；这不是遗漏或计算失败。
- v5-dev1 smoke：10 个 FOV、16 个选定 crop；每个 crop 各有一个 v4.2.2 和一个 v5 任务，共 32 个任务。
- smoke manifest 状态：v4.2.2 完成 12/16，v5 完成 14/16。
- Drive 正式结果：FOV7 的 3 个 crop，v4.2.2/v5 共 6 个任务。

## 共同成像 metadata

30 个 ND2 全部为：

- 3 个通道：`CF GFP SINGLE1_YZ`、`CF RFP SINGLE1_yz`、`CF Cy5 SINGLE_YZ`；
- 2720 × 2720 pixels；
- uint16；
- XY pixel size 0.108333 µm；
- `Plan Apo λ 60x Oil`；
- Kinetix camera `A23J723026`。

曝光组合有两组：12 个文件为 50/200/200 ms，18 个文件为 30/200/150 ms。T、Z 和真实时间间隔在不同 FOV 之间不同，不能在后续动力学分析中统一假定一个 frame interval。

## 30 个 ND2 的范围汇总

`旧版处理数`指进入 19-FOV 固定步长 SPT 范围的候选 crop 数；`v5 smoke`指当前 v4.2.2/v5 配对测试所选 crop。

| FOV | ND2 | T×Z | 中位 Δt (s) | 时间轴分类 | 全部候选 | 旧版处理数 | v5 smoke crop |
|---|---|---:|---:|---|---:|---:|---|
| fov1_1.5h | LiveFISH DSB.nd2 | 1×11 | — | 单时间点，仅分割 | 45 | 0 | — |
| fov2_1.5h | LiveFISH DSB001.nd2 | 40×7 | 10.001 | SPT-ready | 45 | 45 | — |
| fov3_1.5h | LiveFISH DSB002.nd2 | 20×7 | 9.985 | SPT-ready | 65 | 65 | — |
| fov4 2h | LiveFISH DSB003.nd2 | 20×1 | 9.996 | SPT-ready | 40 | 40 | — |
| fov5 2h | LiveFISH DSB004.nd2 | 20×1 | 1.149 | SPT-ready | 53 | 53 | 41 |
| fov6 2h | LiveFISH DSB005.nd2 | 20×1 | 0.994 | SPT-ready | 55 | 55 | — |
| fov7_testforZH | LiveFISH DSB006.nd2 | 50×1 | 1.014 | SPT-ready | 51 | 51 | 5, 12, 33 |
| fov8_2h | LiveFISH DSB007.nd2 | 40×3 | 3.372 | SPT-ready | 51 | 51 | — |
| fov9_2h | LiveFISH DSB008.nd2 | 40×3 | 7.564 | SPT-ready | 45 | 45 | — |
| fov10_2.5h | LiveFISH DSB009.nd2 | 40×5 | 9.306 | SPT-ready | 57 | 57 | 41 |
| fov11_2.5h | LiveFISH DSB010.nd2 | 40×5 | 5.217 | SPT-ready | 57 | 57 | — |
| fov12_2.5h | LiveFISH DSB011.nd2 | 40×5 | 5.244 | SPT-ready | 61 | 61 | 61 |
| fov13_2.5h | LiveFISH DSB012.nd2 | 40×5 | 8.632 | SPT-ready | 49 | 49 | — |
| fov14_3h | LiveFISH DSB013.nd2 | 200×1 | 1.007 | 非均匀，待专门处理 | 48 | 0 | — |
| fov15 3h_1s | LiveFISH DSB014.nd2 | 200×1 | 1.008 | 非均匀，待专门处理 | 49 | 0 | — |
| fov16 3h | LiveFISH DSB015.nd2 | 200×1 | 1.008 | 非均匀，待专门处理 | 43 | 0 | — |
| fov17_3h_forZH | LiveFISH 3h_DSB016.nd2 | 200×1 | 1.008 | SPT-ready | 49 | 49 | 3, 4, 13 |
| fov18_3.5h | LiveFISH DSB017.nd2 | 500×1 | 1.007 | 非均匀，待专门处理 | 50 | 0 | — |
| fov19_3.5h | LiveFISH DSB018.nd2 | 100×3 | 7.638 | SPT-ready | 56 | 56 | 25, 49 |
| fov20_3.5h | LiveFISH DSB020.nd2 | 5×3 | 5.101 | SPT-ready | 53 | 53 | — |
| fov21_3.5h | LiveFISH DSB021.nd2 | 5×3 | 4.935 | SPT-ready | 47 | 47 | 32 |
| fov22_4h | LiveFISH DSB022.nd2 | 50×3 | 4.909 | 非均匀，待专门处理 | 61 | 0 | — |
| fov23_4h | LiveFISH DSB023.nd2 | 50×3 | 5.084 | SPT-ready | 61 | 61 | 37, 60 |
| fov24_4h | LiveFISH DSB024.nd2 | 440×1 | 1.041 | 非均匀，待专门处理 | 53 | 0 | — |
| fov25_4h | LiveFISH DSB025.nd2 | 232×1 | 1.008 | 非均匀，待专门处理 | 51 | 0 | — |
| fov26_4.5h | LiveFISH DSB026.nd2 | 1×9 | — | 单时间点，仅分割 | 62 | 0 | — |
| fov27_samefovas26_4.5h | LiveFISH DSB027.nd2 | 323×1 | 1.008 | 非均匀，待专门处理 | 59 | 0 | — |
| fov28_4.5h_5s | LiveFISH DSB028.nd2 | 50×3 | 4.974 | SPT-ready | 60 | 60 | 48 |
| fov29_4.5h | LiveFISH DSB029.nd2 | 50×3 | 4.991 | SPT-ready | 76 | 76 | 58 |
| fov30_5h | LiveFISH DSB030.nd2 | 500×1 | 1.008 | 非均匀，待专门处理 | 62 | 0 | — |

候选数合计为 1,614，旧版处理数合计为 1,031。

## 当前 16-crop v5 smoke 的运行状态

| FOV | crop | v4.2.2 | v5-dev1 | Drive 正式上传 |
|---|---|---|---|---|
| fov5 2h | 41 | failed/interrupted | complete | 否 |
| fov7_testforZH | 5, 12, 33 | 3/3 complete | 3/3 complete | 是，3/3 |
| fov10_2.5h | 41 | complete | complete | 否 |
| fov12_2.5h | 61 | failed/interrupted | complete | 否 |
| fov17_3h_forZH | 3, 4, 13 | 2/3 complete | 2/3 complete | 否 |
| fov19_3.5h | 25, 49 | 2/2 complete | 2/2 complete | 否 |
| fov21_3.5h | 32 | complete | complete | 否 |
| fov23_4h | 37, 60 | 1/2 complete | 1/2 complete | 否 |
| fov28_4.5h_5s | 48 | complete | complete | 否 |
| fov29_4.5h | 58 | complete | complete | 否 |

`failed/interrupted` 是 run manifest 状态；对应目录及已有产物仍被保留，不能等同于“完全没有输出”。

## 对后续工作的含义

1. v5 目前不能代表 DSB 全量，只能代表 16-crop smoke。
2. 旧版已有 1,031-crop 大规模结果，不应误说成只有 16 个 crop 被分析过。
3. 下一步若要公平比较 v4.2.1/v4.2.2/v5，应先确定范围：仅重跑 19 个 SPT-ready FOV 的 1,031 个 crop，还是先扩展算法以处理 9 个非均匀时间轴 FOV。
4. 两个单时间点 FOV 可以用于静态空间信息，不能用于 MSD、轨迹长度或时间相关分析。
5. 任何跨 FOV 的动力学比较都必须使用逐 ND2 的真实时间戳；本批数据的中位 frame interval 从约 0.994 s 到约 10.001 s 不等。

