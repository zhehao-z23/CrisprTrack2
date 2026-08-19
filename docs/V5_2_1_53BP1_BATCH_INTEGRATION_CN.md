# v5.2.1：53BP1 逐帧旁路测量接入正式 batch

## 范围

v5.2.1 只在 DSB profile 的 longest-baseline 产生后新增
`53bp1_metrics/`。该阶段只读 corrected Green、0 px aligned nucleus mask、
最终 P/Site2 baseline 和可选 R/Site1 baseline。它不参与也不改变：

- crop 候选 QC 或 selection policy；
- P/R reference 检测、配对或 ROI；
- ThunderSTORM localization、SPT linking、`max_disp`；
- longest-baseline 选择。

允许 P 存在而 R 缺失。没有 P baseline 的 crop 仍保存全帧 53BP1 分割与
component 表，但 allele-frame 表为空。

## 固定计算合同

### Component 候选与 lineage

- 每帧在完整 aligned nucleus mask 内对 Green 图像做 `sigma=1 px` 的高斯平滑，
  仅用于分割；强度计算始终读取未平滑图像。
- 阈值为核内 `median + 2.5 × 1.4826 × MAD`；MAD 退化时回退标准差。
- 仅去除小于 3 px 的 component；不做 opening、closing、fill holes 或 watershed。
- lineage 仅允许相邻帧、互为唯一最大 mask-overlap 的主分支延续；最多 1 px
  dilation 只用于 overlap 容差。没有 centroid fallback、gap closing、插值或
  DNA 轨迹引导。split/merge 的父子边全部保留在审计字段中。

### 连续强度

- 中心：最终 P/Site2 baseline localization。
- aperture 半径：1700 nm。
- background：2000–3000 nm 核内环带，并排除所有已分割 53BP1 component 像素。
- 主分数：`max(0, (aperture_mean - background_median) / background_median)`。
- 不设 53BP1 阳性阈值；未截断的差值、积分与 ratio 同时保留。

### 距离

- 保存 P/Site2 到 component 边界的最短有符号 2D 距离：component 内为负，外为正。
- 先在 3000 nm 工程 harvest 域内列出候选；只有边界距离不超过 1000 nm 且
  第一、第二候选相差至少 250 nm 才唯一分配。
- 距离分数为 `max(0, 1 - unsigned_distance_nm / 1000)`；无 component、超界或
  身份歧义时 fail closed 为 0，同时保留最近候选与拒绝原因。

## 每个 crop 的输出

| 文件 | 内容 |
| --- | --- |
| `bp1_focus_labels.tif` | 压缩 TYX、逐帧 object ID 标签；不是裁剪的新影像 |
| `bp1_frame_segmentation.csv` | 每帧阈值、背景、component 数与前景面积 |
| `bp1_focus_objects.csv` | 每个 component 的几何、强度、边缘标记及 lineage |
| `bp1_allele_frame_metrics.csv` | 每个 P allele × 每个 movie frame 的稠密表 |
| `bp1_allele_summary.csv` | 每个 allele 的 localization、有效强度和唯一 component 汇总 |
| `bp1_analysis_manifest.json` | 参数、坐标/时间合同、源路径/bytes/SHA-256 和解释边界 |

FOV batch summary 另含 `bp1_metrics_status` 与 `bp1_metrics_manifest`，因此可以在
不扫描所有文件的情况下区分完成、未到达和不适用的 crop。

## Candidate selection policy 的定位

四个 policy 都只是从不可变 candidate archive 生成的纳入视图，不改变任何像素或
下游算法。人工 `include/exclude` 永远优先。

| policy | 忽略的自动排除原因 | 用途 |
| --- | --- | --- |
| `strict` | 无 | 所有直接 QC 均生效 |
| `no_badqc` | `bad_qc` | 只放宽低对比/低边界梯度 |
| `publicationlike` | `bad_qc`, `mask_border` | 较宽松的 sensitivity analysis |
| `all` | 所有自动原因 | 全候选一次运行，轨迹层以后再筛选 |

旧 DSB 全量采用 `all`/raw-candidate archive：1507 个 candidate 均进入 SPT，最后
1181 个形成 usable crop。该设计为后续 policy 反事实比较保留了信息，并非新的
默认生物学 QC 结论。policy 代码因此不是计算冗余；它们是低成本、可复现的视图。
旧版 `run_crop_trajectory_batch.py` 是历史 smoke/兼容入口，不是当前正式 full-FOV
runner；正式入口为 `run_full_pipeline_v4.py` 和 `run_batch_pipeline_v4.py`。
