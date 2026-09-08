# 参数、单位与调整方法

本手册针对 v5.2.1 冻结算法。配置文件字段使用下划线，CLI 使用连字符；两者一一对应。
每次改参数使用新运行目录并保存配置。数值是当前实现默认值，不是跨仪器通用的推荐值。
所有可调用 Python 脚本的参数、默认值和源码位置列于 [CLI_REFERENCE.md](CLI_REFERENCE.md)。

## Nucleus segmentation

| 配置/CLI | 默认 | 单位/含义 | 调整的影响 |
|---|---:|---|---|
| nucleus_channel | 0 | ND2中零起始通道号；用于分割核的通道 | 必须与采集协议一致，先看 channel metadata |
| margin | 30 | crop bbox 四周额外像素 | 增大保留更多背景、增加 TIFF 体积；不改变原mask |
| min_area | 1000 | mask 最小面积，px² | 降低可保留小核，也可能保留碎片 |
| max_area | 200000 | mask 最大面积，px² | 提高放宽大核/粘连限制 |
| border_margin | 5 | 质心距图像边缘的最小距离，px | 增大更严格去除边缘候选 |
| mask_border_margin | -1 | mask 像素与边缘距离，px；-1禁用 | >=0启用，比仅看质心更严格 |
| segmentation_mode | apg | micro-SAM automatic instance 模式；apg/amg | 改变分割生成器，需重新检查 mask |
| model_type | vit_b_lm | micro-SAM模型类型 | 改变网络/权重和显存需求 |
| device | auto | auto/cuda/mps/cpu | 执行设备；不替代模型版本记录 |
| preserve_all_candidates | true | 是否保存所有原始micro-SAM实例 | 保留筛选决策与可重选性；false将失去完整候选档案 |
| output_root | ND2父目录 | 原脚本输出位置 | 统一入口固定为run-root/segmented，避免写原始数据目录 |
| candidate_output_root | output-root的同级目录 | 所有候选的独立档案位置 | 统一入口固定为run-root/all_usam_candidates；不得嵌套进selected树 |
| include_sibling_candidates | true | save_crops是否同时导出默认同级候选目录 | 统一入口export显式关闭，候选档案可单独export |
| policy | strict | selection的strict/no_badqc/publicationlike/all | 仅创建独立选择视图；manual_decision优先。见materialize_candidate_selection.py中的POLICY_IGNORED_REASONS |

以下是 `crop_nuclei_sam.py` 的固定科学常量，不是 CLI 参数。修改它们需要编辑源码、形成新版本和重新验证：

| 常量 | 默认 | 含义/影响 |
|---|---:|---|
| MIN_SOLIDITY | 0.70 | 低于该solidity尝试watershed split；提高会使更多碎片状mask进入split |
| SPLIT_SIGMA | 5 px | distance-transform平滑sigma；更大抑制小峰 |
| SPLIT_MIN_DIST | 20 px | 分割种子峰最小距离；更大减少拆分 |
| MERGE_PROXIMITY | 2 px | 合并候选接近阈值 |
| MERGE_MIN_SOLID | 0.60 | 合并流程的solidity门槛 |
| MIN_CIRC | 0.3 | circularity=4πA/P²门槛 |
| IOU_THRESH | 0.3 | 重叠去重判据 |
| CONTAIN_THRESH | 0.5 | 包含/合并判据 |
| BAD_QC_CH0_CONTRAST_MAX | 0.085 | 与boundary_grad共同构成bad_qc |
| BAD_QC_CH0_BOUNDARY_GRAD_MAX | 1.70 | 仅当contrast<0.085且boundary_grad<1.70时bad_qc为真 |

## Tracking：输入、profile和执行

| 配置/CLI | 默认 | 含义/调整 |
|---|---|---|
| input_path | 必填 | 单核TIFF；配合no_fiji时为已有Fiji分析目录 |
| crop_dir | 必填 | batch输入根目录 |
| crop_glob | `*.tif` | batch匹配；统一入口使用`**/*.tif`，仍检查sidecar/mask过滤非crop |
| experiment_profile | 必填 | `dsb_53bp1_site1_site2`或`chr3_sites_2_3_4`；锁定生物身份/通道，不能随意交换 |
| fiji_bin | fiji | Fiji executable，需Correct 3D drift |
| matlab_bin | matlab | MATLAB executable，需支持-batch |
| cell_workers | 1 | 同时运行的cell数量；增加CPU/RAM与I/O负担 |
| matlab_workers | 1 | 每cell的MATLAB并发数，1/2/3；总并发为两worker参数之积 |
| matlab_save_filter_images | false | 保存完整band-pass movie到MAT；true大幅增加写盘，CSV无需此图像 |
| resume | true | batch跳过其完成判据已满足的cell；不会证明不同参数的结果等价 |
| dry_run | false | batch只检查并列出有效crop，不启动分析 |
| no_fiji | false | single runner复用Fiji分析目录；仍需原crop以对齐mask |
| crop_tif | 自动推断 | no_fiji的原始crop TIFF显式路径 |
| crop_metadata_sidecar | `<crop>_metadata.json` | 时间/校准sidecar；profile验证仍要求相邻标准sidecar |
| microsam_mask | 自动发现 | 显式覆盖精确crop mask路径，尺寸/坐标需匹配 |

## Tracking：mask、reference与ROI

| 参数 | 默认 | 单位、含义和调整 |
|---|---:|---|
| mask_dilation_px | 0 | 对齐micro-SAM核mask扩张，px；增加允许更多边界外区域，改变support合同 |
| reference_seed_k | null | seed阈值mean+k·SD；按reference通道：G=2.0、R=0.5、P=1.645。增大更严格 |
| reference_tracking_k | null | 每帧tracking阈值mean+k·SD；G=2.0、R=0.5、P=0.5；与seed阈值分开 |
| reference_edge_width_px | 3 | 核mask内侧边缘带宽，px |
| reference_max_edge_fraction | 0.10 | component落在边缘带的最大比例；降低更严格 |
| target_reference_mode | auto | DSB→independent_r_autonomous；chr3→legacy。另保留p_gated_r_autonomous供已有对照。正式DSB使用全核Red自主模式 |
| roi_geometry | auto | DSB→validated_segment_convex_hull；chr3→tube；还支持convex_hull。改变模式会改变结果目录后缀 |
| red_harvest_radius_um | 2.5 µm | 自主Red最终配对的共同帧median P–R距离上限；p_gated模式还用于P周围检出范围。不是全核Red检出的空间限制 |
| red_min_track_points | 5点 | Red轨迹最小观测数；提高减少短轨迹 |
| red_min_shared_frames | 5帧 | 最终P–R配对最小共有帧数 |
| red_min_movie_coverage_fraction | 0.25 | Red movie支持比例下限；提高更严格 |
| red_max_missing_frames | 1帧 | Red reference连续性允许的缺帧；不是SPT trackMem |
| red_uniqueness_margin_px | 1.0 px | 最优与竞争配对的唯一性距离margin；提高更严格 |
| roi_dilation_px | 5 px | 每个有效片段ROI膨胀；增加搜索支持与潜在干扰 |

Reference脚本 `auto_roi_for_published_v2.13.py` 的固定常量（保留原文件名兼容调用）：

| 常量 | 默认 | 意义/适用路径 |
|---|---|---|
| TARGET_TRACKING_K | G2.0/R0.5/P0.5 | target每帧阈值；自主Red使用R0.5 |
| REFERENCE_MASK_OCCUPANCY_FRACTION | 0.50 | 时间平均mask转换为reference support的占据比例 |
| REFERENCE_CONTAINMENT_FRACTION | 1.0 | reference component须完整位于support内 |
| NUCLEUS_SIGMA | 2 px | 无显式mask时旧Otsu核边界平滑；正式提供micro-SAM mask |
| NUCLEUS_OUTSIDE_FRAC | 0.10 | reference观测在核外的比例上限 |
| FILL_RATIO | 0.85 | 低于图像75百分位×此比例的边缘连通像素视为drift填充候选 |
| MIN_SPOT_PX | 10 px² | 最小连通spot component面积 |
| N_MAX | 5 | 接受reference loci最大数 |
| INTER_FRAME_MAX_NM | 500 nm | Purple reference每帧位移上限 |
| INTER_FRAME_MAX_NM_RED | 750 nm | Red reference每帧位移上限 |
| SEED_MAX_FRAME | 5 | 初始seed搜索帧范围 |
| MAX_BLOB_PX | 120 px² | 超过此面积触发自适应阈值拆分blob |
| _ADAPTIVE_K_STEPS | 1.0,1.5,2.0 | 拆分大blob尝试的升高阈值；仅尝试高于基础k的值 |
| PADDING | 20 px | reference脚本的bbox可视化/legacy ROI padding；正式SPT ROI由roi_geometry另算 |
| ADJACENCY_PX | 30 px | legacy centroid tracking邻接距离；不是正式SPT位移门限 |
| REFERENCE_PROX_MAX_UM | 3 µm | legacy target-to-reference搜索距离；不是自主Red最终配对的2.5 µm阈值 |

## Tracking：位移模型与MATLAB定位

| 参数 | 默认 | 单位、含义和调整 |
|---|---:|---|
| d_star | 0.0041 | µm²/s^alpha，固定运动先验；不是每条轨迹拟合D |
| alpha | 0.38 | 无量纲anomalous exponent；与d_star共同决定位移门限 |
| trajectory_coverage_probability | 0.975 | 整个movie的目标coverage；升高会增大门限 |
| localization_error_nm | 0 | 定位误差尺度nm；增加计入的观测不确定性 |
| max_step_rounding_px | 0.05 | 门限向上取整步长px |
| max_step_px | null | 显式门限px；非null时覆盖metadata+model，需要记录理由 |

模型使用采集真实间隔、固定运动先验和movie支持长度计算单个径向门限，
完整推导及端点定义见 [v5.1策略](V5_1_FINAL_ANALYSIS_STRATEGY_CN.md) 和 `max_step_model.py`。
门限不会因缺帧而扩张，写入 `audit/max_step_model.json`。

`spt_batch.m` 固定值不提供CLI覆盖；如需修改，修改源码并记录新版本：

| 字段 | 默认 | 含义 |
|---|---:|---|
| mtl | 3 | SPT最短轨迹长度（frames） |
| dia | 5 px | detector预期spot直径；band-pass高尺度为dia+2 |
| estD | 0.001 µm²/s | 旧fallback扩散常量；正式ROI wrapper强制提供max_disp，故不决定正式门限 |
| fitmethod | 0 | 2-D Gaussian；1为centroid历史可选值 |
| boxr | 9 px | 定位拟合窗口参数 |
| trackMem | 3帧 | SPT全局缺帧连接记忆；与Red reference gap1分开 |
| IntTh | 0 | 强度过滤参数 |
| cell_num | 1 | 此SPT调用只处理一个细胞 |
| K | 0.5 | 首帧正band-pass像素mean+K·SD自动阈值 |
| centfind MaxFunEvals / MaxIter | 3000 / 1000 | Gaussian lsqcurvefit最大函数评估数/迭代数；拟合失败按已有代码fallback |
| f_rate / pixl | TIFF/sidecar | 采集Hz / µm每px；不可用手填默认值替代校准 |

## 53BP1 sidecar

正式runner自动在DSB baseline后调用 `export_bp1_locus_metrics.py`。
输入为analysis_dir、aligned_nucleus_mask、baseline_manifest和可选crop_metadata_sidecar；output_dir必填。
测量定义及固定数值见 [53BP1指标合同](V5_2_53BP1_LOCUS_METRICS_CN.md)；
这些值不用于改变轨迹或推断repair state。

`bp1_locus_metrics.py` 中以下dataclass默认值固定在正式sidecar中，修改需新版本：

| 字段 | 默认 | 含义 |
|---|---:|---|
| intensity_radius_nm | 1700 nm | Site2中心强度圆形ROI半径 |
| background_inner_radius_nm | 2000 nm | 局部background环内径的半径 |
| background_outer_radius_nm | 3000 nm | 局部background环外径的半径 |
| association_boundary_cutoff_nm | 1000 nm | locus至component边界的association距离界限 |
| ambiguity_margin_nm | 250 nm | 竞争component距离差异小于此值时标记歧义 |
| candidate_harvest_radius_nm | 3000 nm | 关联候选检索范围 |
| core_minimum_valid_fraction | 0.8 | 强度core ROI有效support比例下限 |
| background_minimum_valid_fraction | 0.5 | 背景环有效support比例下限 |
| gaussian_sigma_px | 1.0 px | component检出前平滑sigma |
| threshold_robust_z | 2.5 | median+z×1.4826×MAD；MAD无效时使用SD fallback |
| minimum_component_area_px | 3 px² | 最小53BP1 component面积 |
| lineage_dilation_px | 1 px | 相邻帧component lineage重叠前膨胀尺度 |
