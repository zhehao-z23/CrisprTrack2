# v5.2 53BP1 locus 连续强度与有界距离指标

## 设计目标

这两个 readout 必须彼此独立：

1. **强度**描述 Site2/P locus 周围的连续 53BP1 burden。它没有阳性比例阈值，最低值仅由物理下限截为 0。
2. **距离**描述 Site2/P locus 与一个可唯一归属的分割 53BP1 component 的几何关系。过远、缺失或含糊的 component 必须拒绝，并令距离分数为 0。

因此，“局部强度大于 0”不等同于“存在可接受 component”；反之，弱 component 也不应因强度阈值被事后删除。

## 冻结参数

| 参数 | v5.2 值 | 用途 |
|---|---:|---|
| Site2 到预期切点的 2D `r95` | 703–810 nm | 来自 Phase 2 自动/人工 mean-square scaling；只作为空间先验 |
| 已发表完整 53BP1 focus 等效半径 | 691–874 nm | 由本实验 PDF 报告的 1.5–2.4 µm² 面积换算 |
| 强度孔径半径 | **1700 nm** | 810 + 874 = 1684 nm，向上取整；覆盖 locus-to-cut 偏移和完整 aggregate，而非 53BP1 core 半径 |
| 局部背景环 | **2000–3000 nm** | 位于强度孔径之外；只使用核内、非分割前景像素 |
| component 边界 cutoff | **1000 nm** | 810 nm 上界加约 2 个 corrected-image pixel 的分割/配准容差，取整 |
| candidate harvest 半径 | 3000 nm | 仅为计算候选池，不是生物学判定线 |
| 最近/次近边界 margin | 250 nm | 唯一性保护；小于此值按 ambiguous 拒绝 |

不能从 233,770 bp 直接确定一个唯一的 nm 半径；这里使用同一实验数据的物理 scaling 得到概率上界，再与实测 focus 尺度组合。已发表的约 0.29 µm Gaussian core 只描述典型亮核，不用于本强度孔径。

## 连续强度

对每个有 Site2/P localization 的 frame，以 locus 为中心建立 1700-nm 圆形孔径。背景为同心 2000–3000-nm 环，并限制于当帧 nucleus mask 内，同时排除已分割的 53BP1 前景像素。

设孔径均值为 `I_aperture`，局部背景中位数为 `I_bg`：

```text
signed_excess_mean = I_aperture - I_bg
local_excess_ratio = (I_aperture - I_bg) / I_bg
continuous_intensity = max(0, local_excess_ratio)
```

`continuous_intensity` 不再接受任意 positivity cutoff。为保证信息不丢失，CSV 同时保存孔径 mean/sum、背景 median、未截断的 background-subtracted mean/sum 和未截断 ratio。圆周被图像或核 mask 截断时，只有在孔径有效支持低于 80% 或背景有效支持低于 50% 时才记为缺失；这两个值是可计算性 QC，不是 53BP1 阳性阈值。

## component 距离

每帧对冻结 segmentation 中候选 component 的真实轮廓计算 Site2/P 到边界的最短距离：

- locus 在 component 内：保存负的 signed distance；用于评分的 unsigned distance 为 0；
- locus 在 component 外：保存正的 signed distance；
- 最近 component 的边界距离大于 1000 nm：`NO_ASSOCIATED_FOCUS`；
- 3000 nm 内没有 component：`NO_BP1_COMPONENT_IN_HARVEST_DOMAIN`；
- 最近和次近候选距离差小于 250 nm：`AMBIGUOUS_ASSIGNMENT`；
- 以上三种拒绝状态的距离分数均为 0。

唯一接受后：

```text
u = 0                                  if locus is inside component
u = signed_boundary_distance_nm        if locus is outside component
distance_score = max(0, 1 - u / 1000)
```

因此 boundary cutoff 处以及更远处均为 0，component 内部为 1。原始 signed distance、最近被拒候选距离、候选数量和 second-candidate margin 全部保留用于 QC。

## 输出接口

实现位于 `trajectory_extraction/pipeline/bp1_locus_metrics.py`。主函数为：

- `measure_continuous_intensity(...)`
- `associate_component(...)`
- `signed_boundary_distance_nm(...)`
- `clipped_distance_score(...)`

建议每个 allele 保存一个逐帧 CSV，并和最终 Site1/Site2 baseline 使用同一 `frame`、`time_s` 与 whole-corrected-image 坐标。强度缺失必须为 NA；component 被拒绝时距离分数必须显式为 0，不能用 NA 隐去。

## 当前证据边界

参数已在隔离的 8-case pilot 上冻结并验证，但尚未自动接入全 cohort workflow。pilot 的时间图只用于人工审阅时序关系；单轨迹 Spearman 相关是描述性结果，不能代替 cell/acquisition 层级模型，也不能据此再次调整 cutoff。
