# v5.2 DSB 通道特异 reference 与 ROI 策略

> **v5.2.1 formal-runner correction (authoritative):** DSB `auto` resolves to
> `independent_r_autonomous`. Red components are harvested over the whole
> aligned nucleus and linked only by Red continuity. Purple is not used during
> Red detection or linking; it is consulted only at final one-to-one pairing.
> The frozen 2.5 um value is therefore the final common-frame median P-R
> distance ceiling. The older `p_gated_r_autonomous` path remains available
> only when explicitly requested for sensitivity comparison.

## 适用范围

本变更只默认应用于 `dsb_53bp1_site1_site2`。Chr3 profile 继续使用 v5.1
兼容路径，除非用户显式指定新参数。v5.2 不改变 micro-SAM 0 px、SPT
`max_disp` 97.5% 轨迹覆盖、坐标系或 longest-baseline 规则。

## 生物身份与候选生成

1. Purple/Site2 仍是 canonical allele identity。
2. 每个有观测 P 位置的帧，以该位置为圆心、2.5 µm 为半径收获 Red/Site1
   connected-component detection。2.5 µm 是保守搜索上限，不是 600 nm
   proximity 分类线，也不是 repair-state 定义。
3. Red detection 一旦被收获，只能依靠 Red 自身端点连续性建立候选轨迹：
   Red-to-Red 位移不超过 750 nm；相邻帧优先，最多允许 1 个缺失帧。
4. 没有 P-position fallback 或插值。跨过缺失帧时只保留两个真实端点，
   不生成缺失帧坐标。
5. 少于 5 点的 Red 候选不进入 identity pairing，但所有收获 detection 均写入
   `red_harvest_detections.csv`。

## P-R 唯一配对

对每个 P locus 与 Red candidate，仅在共同观测帧计算二维距离：

```text
d_t = sqrt((P_x(t)-R_x(t))^2 + (P_y(t)-R_y(t))^2)
pair_cost = median_t(d_t)
```

候选必须同时满足：

- 至少 5 个共同帧，且不少于电影总帧数的 25%；
- 共同帧中位距离不超过 2.5 µm；
- P 与 R 互为最低 cost；
- 相对于同一 P 的次优 R，以及同一 R 的次优 P，cost margin 均至少 1 px；
- 全局 one-to-one Hungarian assignment 不冲突。

任一条件不满足即不写 `R_loci<N>_traj_rela2wholeimg.csv`。未唯一配对的
allele 仍可运行 Green/Purple，但 Red SPT 必须 fail closed。

保存三层审计：

- `red_harvest_detections.csv`：逐帧 component、面积、坐标、最近 P 与距离；
- `red_pair_common_frames.csv`：每个 P-R 候选组合的逐共同帧坐标与距离；
- `red_pair_summary.csv`：共同帧数、中位/P95 距离、双向 margin 与决策。

## P/R 统一 ROI 几何

P 与 R reference 使用同一个几何算法，但各自使用通道固定 reference 步长：

- P：500 nm；
- R：750 nm。

首先将 reference 按时间排序。只有 `delta frame = 1` 且步长不超过该通道上限
的相邻点属于同一合法 segment。对每个 segment 单独填充 convex hull；随后
union 所有 segment hull，外扩 5 px，并与漂移对齐、未外扩的 frame-1 micro-SAM
mask 相交。这样不会用直线或一个全局 hull 跨过空帧/不合法跳跃。合法 segment
彼此分离时允许 ROI 多连通，并在 `static_anchor_roi_geometry.csv` 中记录：

- 合法相邻 transition 数；
- gap-rejected transition 数；
- excessive-step-rejected transition 数；
- ROI 面积、bbox 与 connected-component 数；
- reference CSV、通道及使用该 ROI 的 SPT 通道。

DSB 的通道使用关系为：

```text
P reference -> Green/53BP1 SPT + Purple/Site2 SPT
uniquely paired R reference -> Red/Site1 SPT
```

## 验证与边界

合成测试必须证明：最多只跨 1 个缺失帧且不插值、ROI 不跨缺口画 hull、
超限端点不连、Red 不能借 P 位置跳跃、共同帧覆盖门、中位距离与唯一性门
正确执行。真实数据验证应先看原始 Red 图上的全部
候选、旧 v5.1 baseline、新 P/R reference 和两个 ROI，再看 trajectory 数量。

本版本不声明所有 Red identity 已人工确认，也不因轨迹更长而自动认为改进。
2.5 µm、5 点、25%共同帧覆盖和 1 px margin 均为冻结工程参数；改变其中任意参数
必须创建新输出目录并记录理由。
