# v5.1 最终轨迹分析策略与复核合同

版本：`5.1.0`  
状态：已固定代码、参数、审计输出与坐标合同。  
适用范围：从单细胞 crop TIFF、相邻 `*_metadata.json` 与 micro-SAM mask 到自动 reference、ROI-restricted SPT、最长 baseline 和 QC。人工轨迹不作为算法输入。

## 1. 相对 v5 dev1 的最终变化

v5 dev1 保留 `trackMem=3`，允许连接不超过 3 个全局空检测帧；这一逻辑继续保留。v5.1 另外固定四项：

1. micro-SAM 核支持在漂移对齐后默认不外扩，`mask_dilation_px=0`；
2. `max_disp` 不再使用单 step `p=0.995`，而使用锁定全局运动先验和整段采集 `Q=0.975`；
3. reference 初筛改成全图连通域、100% 核内、边缘带过滤、亮度排序 Top 5，并把 time-average seed 与逐帧 tracking 的阈值分开；
4. 自动轨迹、ThunderSTORM、FIJI ROI、NumPy/Matplotlib 和 frame index 使用一个版本化坐标合同。

旧版快照保留在 Git 提交 `b6615cf`，因此 v5 dev1 与 v5.1 可以分别 checkout 和复核。

## 2. 输入与两种 dilation

生产输入包括：单细胞多通道 crop TIFF；相邻 `<crop_stem>_metadata.json`；sidecar 指向的原始 crop-space micro-SAM mask。

- `mask_dilation_px=0`：micro-SAM mask 经逐帧漂移变换后不再向外扩 5 px；它是核支持与 reference 过滤域。
- `roi_dilation_px=5`：把 reference 轨迹中心线或 convex hull 扩成静态 SPT ROI，以完整支持 9 px Gaussian fitting box；它仍保留，且不是核 mask 外扩。

`mask_alignment/alignment_manifest.json` 记录原始 mask、逐帧漂移、dilation 和输出。文件名可能含 `dilated_0px`，含义是应用了 0 px 操作，像素集合未外扩。

## 3. reference 选择的完整顺序

### 3.1 profile 与核支持

生产入口必须选择实验 profile。DSB profile `dsb_53bp1_site1_site2` 锁定 Purple/Cy5/Site 2 为 anchor，不能为得到想要的结果手动换 reference channel。

原始 micro-SAM mask 重复到所有时间点，按 profile 指定 corrected channel 的漂移逐帧变换，默认不外扩。reference 初筛使用“至少 50% 可用帧为核内”的 consensus mask；逐帧 reference 位置仍回到对应帧 mask 检查。

### 3.2 time-average seed：Purple 的 `k=1.645`

1. 对 reference stack 沿时间取平均；
2. 用 border-connected fill 检测排除漂移校正填充值；
3. 在其余有效像素计算 `mean` 和 `std`；
4. Purple 阈值为 `mean + 1.645 × std`。`1.645` 是预先固定的单侧标准正态 95% 分位数，只作为 seed 图像阈值系数，不解释成轨迹显著性检验；
5. 在整张有效 time-average 图上做 connected-component labeling，不能先用核 mask 裁图，也不能只检查 centroid；
6. 保留面积至少 10 px 的连通域；
7. 连通域每一个像素都必须在 consensus nucleus mask 内，即 containment=100%；跨越边界的区域即使 centroid 在核内也拒绝；
8. 定义核内 3 px 边缘带，连通域落在边缘带的像素比例不得超过 10%；
9. 不加入“弥散度”“背景扣除积分”“面积≥30 px 的帧比例”等未跨数据验证的额外规则，避免误删真实 allele；
10. 按原始 time-average component mean intensity 降序，最多取 Top 5。

Green/Red 若作为 profile anchor，seed 默认分别为 `k=2.0/0.5`；本轮 `1.645` 是 DSB Purple 规则。阈值、每个连通域的接受/拒绝原因、Top-N 排名和强度写入 `anchor_stage1/reference_detection_audit.json`。

### 3.3 逐帧 reference tracking：Purple 的 `k=0.5`

seed 与 tracking 是两个参数：time-average Purple `k_seed=1.645`，逐帧 Purple `k_track=0.5`。

每帧在有效像素重新计算 `mean + k_track × std`，标记连通域并计算强度加权 centroid。对每个 seed，选择距其固定 time-average centroid 小于 30 px 的最近逐帧 component；无候选的帧保持缺失，不插值、不平滑。若可检查位置中超过 10% 在逐帧核 mask 外，则拒绝该 reference。接受轨迹的点数、1-based 起止 frame 和核外比例也写回 audit。

### 3.4 reference 后续既有逻辑

接受轨迹的 bounding box 四周保留 20 px。reference ROI 重叠时，target channel 使用 joint seeding、one-to-one assignment 和自适应 blob threshold；不重叠时独立寻找 target。target 必须在前 5 帧内成功 seed，通常同时满足相邻位置限制和距 reference 3 µm 限制；既有 reference-proximity fallback 保留。Purple/非 Red 的相邻限制为 500 nm，Red 为 750 nm。没有硬编码“只保留一个 expert allele”，真实 2–5 个 allele 仍可保留。

## 4. 静态 anchor ROI 与 SPT

每条 reference 形成一个静态 ROI：`tube` 按绝对 frame 连接 reference 点；`convex_hull` 先填完整 path 凸包；随后独立外扩 5 px，与 frame 1 的 drift-aligned、0-px-expanded micro-SAM support 取交，要求结果只有一个 connected component，并在所有帧复用。

ROI 只限制 coarse peak center，不把 ROI 外原图像素清零，因此靠边 peak 的 9 px Gaussian fit window 仍读取原始邻域。MATLAB SPT 保留：`dia=5`、`boxr=9`、first-frame bandpass threshold `mean(nz)+0.5×std(nz)`、`mtl=3`（给 `track.m` 为 `good=4`）、`trackMem=3`、Gaussian fitmethod 0、IntTh 0。

## 5. `max_disp` 的最终统计定义

### 5.1 不在线拟合 D

固定 `D*=0.0041 µm²/s^alpha`、`alpha=0.38`、每轴 localization error 0 nm、整段采集 coverage `Q_target=0.975`，并向上取整到 0.05 px。既不按 cell 重新估计 D，也不按 ND2 的初步自动轨迹拟合 D，避免短轨迹、筛选截断和错连产生反馈。一个 ND2 的各 cell sidecar 具有相同 timestamps/pixel size，因此自然得到同一个 movie-level `max_disp`。

### 5.2 公式

对 source ND2 的每个真实相邻采集间隔 `dt_i`：

```text
v_i = D* · dt_i^alpha + sigma_loc^2
p_i(r) = 1 - exp[-r^2 / (4 v_i)]
Q(r) = product_i p_i(r)
```

求解 `Q(r)=0.975`，再转为 px：

```text
max_disp_px = ceil_0.05(r / pixel_size_um)
```

`Q=0.975` 表示：在模型与 step 独立假设下，一段完整采集至少出现一次相邻 model step 超过 gate 的单侧尾概率为 2.5%。它不是经验 step 的 97.5th percentile，也不是把每个 step coverage 设为 97.5%。若有 `N` 个间隔，等效恒定 per-step coverage 是 `0.975^(1/N)`。

### 5.3 时间来源与 gap

优先读取 sidecar 的 `time.frame_intervals_s`；缺失时由 `relative_time_s` 作差。两者都无时，重复 TIFF `finterval` `frame_count-1` 次，并在 `audit/max_step_model.json` 标记 `uniform_tiff_finterval_fallback`，不静默伪装成 exact timestamps。

gate 在同一 movie/ND2 内冻结。v5 gap recovery 仍使用同一 scalar，不按 gap 放大。`trackMem=3` 表示最多 3 个全局空帧仍在同一 tracking block，超过则硬切段。

### 5.4 FOV7 只读验证

直接读取 `LiveFISH DSB006.nd2` 的 50 帧/49 个真实间隔：median 1.0138425 s、mean 1.0715574 s、范围 0.9891525–1.1896200 s。新实现求得理论 `3.2980045657 px`，向上取整为 `3.30 px`；取整后整段 coverage 为 `0.9752244239`。所以 3.30 px 是固定统计规则在 FOV7 metadata 上的结果，不是在所有 ND2 上硬编码。

## 6. baseline 选择

每个 allele、每个 G/P/R channel 保留所有 MATLAB candidate，并按稳定规则选一个 baseline：points 最多；并列时 frame span 最大；再并列时 first frame 更早；再并列时 candidate number 更小。

文件名中的 `cleaned` 只表示按上述自动规则选出的最长 ROI-restricted candidate；不表示人工清洗，也不做 legacy reference-distance matching。所有 candidates、排序和选中路径写入 `all_candidate_trajectories.csv`、`baseline_selection.csv` 和 `baseline_manifest.csv`。

## 7. 坐标合同

版本：`oligolivefish-pixel-centre-v1`。

- NumPy/TIFF/`imshow(origin='upper')`：top-left pixel centre 为 `(x=0,y=0)`；x=column/水平，y=row/向下。
- 自动 MATLAB/Python CSV：whole-image nm，1-based pixel centres；`image_px = automatic_nm/pixel_size_nm - 1`。
- ThunderSTORM CSV：ROI-local nm，top-left pixel centre=0.5 px；FIJI Area ROI `left/top` 是 whole-image 0-based pixel edges；`image_px = roi_edge + TS_nm/pixel_size_nm - 0.5`。
- CSV frame 为 1-based，数组 index 为 `frame-1`。

所有生产转换集中在 `trajectory_extraction/pipeline/coordinate_system.py`。QC、anchor ROI、candidate audit 和 cellular feature extraction 都调用它。无法取得 ThunderSTORM 对应 FIJI ROI offset 时直接报错，不再把 ROI-local 坐标静默当 whole-image；原始 CSV 不重写。

## 8. 必查 provenance

- `run_manifest.json`：版本、输入、profile 与 CLI；
- `mask_alignment/alignment_manifest.json`：mask 来源、漂移与 dilation=0；
- `anchor_stage1/reference_detection_audit.json`：两个 k、完整连通域判定、边缘带、排名及 reference 长度；
- `audit/max_step_model.json`：sidecar SHA-256、全部 intervals、公式、锁定先验、理论/操作 gate、coverage 与 fallback；
- `audit/static_anchor_roi_geometry.csv`：anchor、ROI geometry、dilation 与面积；
- `audit/all_candidate_trajectories.csv`、`baseline_selection.csv`：所有候选与稳定排序；
- `anchor_roi_v4_summary.json`：结果总表与坐标合同。

## 9. 发布验证

- `python -m unittest discover -s tests -p "test_*.py" -v`：48/48 通过，覆盖 profile、mask 关联、reference 规则、整段 coverage、真实/转义微米单位、坐标转换、ROI、baseline、版本合同和打包。
- `tests/run_v5_local_tests.ps1`：上述 48 项 Python 测试及 4 组 MATLAB runtime 回归全部通过；包括无可连接轨迹、global-gap memory 边界、临时 TIFF 批处理集成，以及同一 TIFF 上 v4.2 断裂而 v5 恢复的对照。
- FOV7 cell00 只读 Stage 1 smoke：最终 reference 规则得到 4 条 reference，长度均为 50/50 帧，均通过逐帧核内检查；其中包含专家标注的 allele2。该结果说明新规则清除了先前的大片弥散候选，但不会为了逼近“肉眼只认一个位点”而硬编码只保留一条 allele。
- FOV7 `max_disp` 的 metadata 数值验证见 5.4。此次发布未重新运行 DSB 全量，也未把人工轨迹作为调参输入。

## 10. 已知边界

这套规则在 FOV7 cell00 与既有 smoke set 上形成，并用合成契约回归固定。新 ND2 仍需 blinded/holdout QC，重点检查真实多 allele 是否保留、metadata-derived gate 是否增加 identity switch、target threshold 是否产生 competing detections。后续算法变更必须新建版本，不覆盖 v5.1 输出。
