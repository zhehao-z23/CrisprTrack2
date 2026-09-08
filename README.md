# CrisprTrack2

从 **多通道 ND2 → nucleus segmentation → 单核 TIFF → trajectory extraction** 的可审计管线。
科学实现冻结于 **v5.2.1 / `9f4e28a7bdaa6847e876fa9e3de059de197d0441`**。
本次整理添加统一入口、参数索引和项目边界，保留原始科学算法、阈值和输出命名。

| 仓库 | 输入 | 责任与输出 |
|---|---|---|
| **CrisprTrack2** | ND2，或已导出的 TIFF + metadata + exact mask | 分割、漂移校正、ROI/SPT、轨迹 CSV、提取 QC 和 53BP1 测量 sidecar |
| [ChromatinDynamics-Biophysics](https://github.com/zhehao-z23/ChromatinDynamics-Biophysics) | 轨迹、时间和身份元数据、提取审计 | 科学 QC、MSD/MSCD/VAC/VCC、模型检验、静态与动态可视化 |
| [ChromatinDynamics-ML](https://github.com/zhehao-z23/ChromatinDynamics-ML) | 冻结轨迹/物理表及 target | Fingerprinting、无监督分层、监督学习和 published benchmark |

旧 `Cellular_feature_extraction/`、`trajectory_to_nuclear_features/`、旧示例结果及 v2/v3 比较运行器已从当前代码树移出。
原有 Git 历史保留；[归档说明](docs/ARCHIVE_AND_PROVENANCE.md)记录来源和恢复方法。

## 1. 安装和起始文件

需要 Python、Fiji（安装 **Correct 3D drift**）、MATLAB（**Optimization Toolbox**，Gaussian拟合调用`lsqcurvefit`）。分割还需要 micro-SAM 模型及其 PyTorch 环境。
Python 依赖和经验证的版本保留在 [requirements_nd2_to_traj.txt](requirements_nd2_to_traj.txt)；
GPU/CUDA 安装见 [环境说明](REQUIREMENTS_ND2_TO_TRAJ.md)。不把 Fiji、MATLAB、模型权重或整个虚拟环境加入 Git。

```bash
git clone https://github.com/zhehao-z23/CrisprTrack2.git
cd CrisprTrack2
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements_nd2_to_traj.txt
python -m pip check
matlab -batch "assert(exist('lsqcurvefit','file')==2, 'Optimization Toolbox lsqcurvefit is required'); disp(version)"
```

两种起点：

- **原始 ND2**：单文件或含 ND2 的目录，必须保留真实通道名、时序和像素校准。
- **现有单核 crop**：`cell.tif`（TCYX 或 TZCYX）、同目录 `cell_metadata.json`、该 crop 对应的精确 micro-SAM mask。
  profile 会检查通道数量、名称、来源标记与 sidecar；任意 TIFF 或仅 CSV 不能代替此输入。

```text
raw/experiment.nd2                # 只读原始数据
runs/new_run/                     # 新输出目录；与 raw 分开
  segmented/<ND2 stem>/           # 通过默认分割筛选的 nuclei / masks / crops
  all_usam_candidates/<ND2 stem>/ # 每个原始候选及 QC 决策；不自动进入本次 tracking
  workflow_config.json
  workflow_commands.json
```

## 2. 完整运行

复制 [configs/dsb_v521.json](configs/dsb_v521.json)，修改 `fiji_bin` / `matlab_bin` 为本机可执行路径。
JSON 的键对应 CLI 名称：如 `roi_dilation_px` 就是 `--roi-dilation-px`；`null` 使用内部默认值。
[参数手册](docs/PARAMETERS.md)逐项解释数值、单位、影响和固定常量；[完整 CLI 清单](docs/CLI_REFERENCE.md)对应源码。

```bash
# 只打印命令，不启动任何分析
python crisprtrack2.py --config configs/dsb_v521.json --input /data/raw --run-root /data/runs/test01 --plan
# 完整执行：segment → export → track
python crisprtrack2.py --config configs/dsb_v521.json --input /data/raw --run-root /data/runs/test01
```

`all` / `segment` 要求新的 run-root。示例使用单个 cell worker，最大 MATLAB 并发数是
`cell_workers × matlab_workers`。F 盘机械盘建议先保持 `cell_workers=1`。
此配置重现代码默认分割选择；历史研究的已审核 candidate selection 应从其冻结 manifest 恢复，不能仅凭默认规则重建研究 cohort。

## 3. 分阶段运行与重启

```bash
python crisprtrack2.py --config configs/dsb_v521.json --input /data/raw --run-root /data/runs/test01 --stage segment
python crisprtrack2.py --config configs/dsb_v521.json --input /data/raw --run-root /data/runs/test01 --stage export
python crisprtrack2.py --config configs/dsb_v521.json --input /data/raw --run-root /data/runs/test01 --stage track
```

`export` 读取已保存的 crops JSON，再从原始 ND2 导出 TIFF，所以原始 ND2 必须仍可访问。
`track` 默认 `resume=true`，由原 batch runner 检查完成状态。要改变科学参数，使用新的 run-root / crop 工作副本，
不要把不同配置混进同一批次；原 single-cell runner 会清理并重建其同名生成结果目录。

已有 crop 可直接运行，不需要再次分割：

```bash
python trajectory_extraction/run_full_pipeline_v4.py /data/cell.tif --experiment-profile dsb_53bp1_site1_site2 --fiji-bin /apps/Fiji/ImageJ-linux64 --matlab-bin matlab
python trajectory_extraction/run_batch_pipeline_v4.py /data/crops --crop-glob "**/*.tif" --experiment-profile dsb_53bp1_site1_site2 --dry-run
python trajectory_extraction/run_batch_pipeline_v4.py /data/crops --crop-glob "**/*.tif" --experiment-profile dsb_53bp1_site1_site2 --fiji-bin /apps/Fiji/ImageJ-linux64 --matlab-bin matlab
```

重复使用 Fiji 输出：

```bash
python trajectory_extraction/run_full_pipeline_v4.py /data/cell_analysis --no-fiji --crop-tif /data/cell.tif --experiment-profile dsb_53bp1_site1_site2 --matlab-bin matlab
```

需要改变 nucleus 选择时，原始候选档案保持不变，另外生成 selection view：

```bash
python nucleus_segmentation/save_crops.py /data/runs/test01/all_usam_candidates --no-include-sibling-candidates
python nucleus_segmentation/materialize_candidate_selection.py /data/runs/test01/all_usam_candidates /data/runs/selection_v2 --policy strict
python trajectory_extraction/run_batch_pipeline_v4.py /data/runs/selection_v2/spt_included --crop-glob "**/*.tif" --experiment-profile dsb_53bp1_site1_site2 --dry-run
```

selection 输出按 FOV 分层，递归batch命令可统一处理；各FOV审计在 `manifests/<FOV>/selection_summary.json`。
选择视图使用symlink，runner解析后的结果写在源crop旁；**更换selection标签不会隔离分析结果**。
在Windows需有创建symlink的权限，并把选择视图放在NTFS；当前F盘exFAT不能创建这种视图。也可使用独立实体crop副本。
改变科学参数时先为crop、sidecar、mask创建独立实体工作副本，再运行，不能在原冻结candidate档案上改参数重跑。
手动决定优先于policy；详见 [nucleus 文档](nucleus_segmentation/crop_nucleus.md)。

## 4. 输出与下游合同

DSB 默认每个 crop 的分析目录下包含：

```text
anchor_roi_v4_dsb_53bp1_site1_site2_independent_r_autonomous_validated_segment_convex_hull/
  run_manifest.json                # 版本、配置、输入和完成状态
  mask_alignment/                  # 与漂移校正图像对应的精确 mask
  anchor_stage1/                   # reference 检出及关联审计
  static_union_rois/               # 按有效片段生成的静态 ROI
  roi_spt/                         # 所有 SPT candidates、MATLAB 输出
  baseline_longest/
    baseline_manifest.csv          # allele、通道、坐标、来源
    allele_*_longest_spt_cleaned.csv
  53bp1_metrics/                   # 测量 sidecar；不影响轨迹选取
  audit/                          # max-step、baseline 等决策
  figures/                        # 提取层 QC
```

正式轨迹列为 **`frame,x_nm,y_nm`**，坐标单位 nm，使用 whole-image pixel-centre 坐标合同。
保留原始 frame 和缺帧；禁止重新编号、插值或填补缺失位置。精确时间在 crop sidecar，不能仅用行号当时间。
下游必须连同 baseline manifest、profile/身份映射、时间/像素校准和 QC 审计保存；仅轨迹 CSV 是便携子集，
不能重建 53BP1 intensity 或原始图像 QC。

## 5. 当前算法约定

- DSB：Purple 给出 Site2 的 canonical allele 身份；Red/Site1 在全核自主检出、按 Red 连续性连接，最终才与 Purple 配对。
- Red 最多缺一帧，轨迹至少 5 点，共有帧至少 5，movie coverage 至少 25%，共同帧 median P–R distance 至多 2.5 µm。
- P-only allele 仍有效。P/R ROI 为各有效片段 convex hull 并膨胀 5 px；micro-SAM mask 本身不膨胀。
- Gaussian SPT 只在 ROI 内接纳峰中心，拟合读取未掩膜图像；movie-level 97.5% coverage 决定一个固定 max-displacement。
- SPT `trackMem=3` 与 Red reference `red_max_missing_frames=1` 是不同层的参数，不能混用。
- 53BP1 sidecar 在 baseline 后测量；其值不会反馈到分割、ROI、SPT 或 baseline 选择。

`chr3_sites_2_3_4` 用于原 manuscript 四通道数据；DSB 必须选 `dsb_53bp1_site1_site2`。
两个 profile 自动锁定 anchor。为兼容历史结果，`v4` / `v2.13` 的文件名仍保留，但其内容就是冻结的 v5.2.1 实现。

## 6. 验证与来源

```bash
python -m unittest discover -s tests -p "test_*.py"
# MATLAB 小型合成数据回归（需 MATLAB）：
matlab -batch "addpath('tests'); test_spt_track_global_gap_memory"
```

本次收尾验证结果见 [VALIDATION.md](VALIDATION.md)。没有重新提取研究数据。
算法来源为 [chenxy19/OligoLiveFish-ML](https://github.com/chenxy19/OligoLiveFish-ML) 及 ZZH 的 v4–v5.2.1 修改；
保留 MATLAB 文件内原作者声明，详细来源见 [provenance](docs/ARCHIVE_AND_PROVENANCE.md)。
