# OligoLiveFish-ML

OligoLiveFish-ML is an analysis and modeling repository for live-cell
Oligo-LiveFISH chromatin-dynamics data. It provides a workflow for turning
multi-channel microscopy movies into audited single-particle DNA trajectories,
then using those trajectories to model nuclear and local chromatin features.

This snapshot is **v5.0.0-dev1-trackmem-global-gap**. It was derived from the
clean v4.2.2 baseline at commit
`833515ee7a3da2ced4b34925c85107d54c006918`. The v5 dev1 experiment changes one
linking boundary: a globally empty detection interval is crossed only when its
missing-frame count is no greater than `trackMem`; larger gaps remain hard
boundaries. Detection, Gaussian localization, ROI construction, `trackMem`,
`max_disp`, minimum length, and baseline selection are unchanged.

The repository retains the four stages of the original project:

1. `nucleus_segmentation/` segments nuclei in `.nd2` field-of-view files,
   preserves every micro-SAM candidate, and exports single-nucleus TIFF crops.
2. `trajectory_extraction/` runs CrisprTrack: Fiji preprocessing, exact
   micro-SAM-mask alignment, profile-locked anchor tracking, ROI-restricted
   MATLAB 2-D Gaussian SPT, v5 gap-aware linking, and deterministic baseline
   selection.
3. `Cellular_feature_extraction/` extracts cellular and nuclear features from
   masks and DNA-locus locations.
4. `trajectory_to_nuclear_features/` contains traditional-machine-learning and
   deep-learning experiments that predict nuclear and local chromatin features
   from trajectory dynamics.

The v5 dev1 code change is confined to Stage 2. Stages 3 and 4 are retained for
continuity with the reference repository but were not modified or revalidated
as part of the gap-linking experiment.

Raw microscopy files are not stored in the code snapshot. The laboratory copy
of the DSB acquisitions is maintained in the shared Drive under
`LivevFISH data/2-25-26-dsb_E/more/a`; derived v5 results are archived
separately under `more/zhehao` with a source-ND2 mapping rather than a duplicate
of the approximately 220-GiB raw collection.

## Repository Layout

```text
nucleus_segmentation/
  crop_nuclei_sam.py             # segment nuclei and preserve candidate masks
  save_crops.py                  # export multi-channel single-cell TIFFs
  materialize_candidate_selection.py
  crop_nucleus.md

trajectory_extraction/
  run_full_pipeline_v4.py        # v5 single-cell runner; compatibility filename
  run_batch_pipeline_v4.py       # v5 batch runner; compatibility filename
  pipeline/                      # Python modules and bundled MATLAB dependencies
  README.md                      # complete CrisprTrack v5 contract and usage

Cellular_feature_extraction/
  extract_features.py
  extract_nuclear_features.py

trajectory_to_nuclear_features/
  traditional_ml/
  deep_learning/
  README.md

tests/                            # source-contract and MATLAB runtime regressions
provenance/                       # v4.2.2 baseline hashes and v5 changed-file hashes
deployment/                       # non-destructive Sherlock overlay instructions
docs/
  ND2_TO_TRAJECTORY_OPERATIONAL_GUIDE.md
CHANGELOG.md
VERSION
```

The filenames `run_full_pipeline_v4.py`, `run_batch_pipeline_v4.py`, and
`anchor_roi_v4_*` are preserved for compatibility with existing scripts and
results. Runtime manifests and `VERSION` identify the implementation as v5.

## Stage 1: Nucleus Segmentation

The workflow starts from a multi-channel ND2 field of view.
`crop_nuclei_sam.py` uses micro-SAM to segment nuclei, applies declared
geometric QC, records the source channel and acquisition metadata, and writes
one exact instance mask per candidate. Candidate-preserving mode keeps every
raw micro-SAM instance in an immutable archive and records gate decisions in
`candidate_selection_manifest.csv`; no candidate is deleted merely because it
fails a default gate.

`save_crops.py` exports one calibrated multi-channel TIFF per nucleus together
with a mandatory `*_metadata.json` sidecar and the associated micro-SAM mask.
These three objects form the Stage-2 input contract. See
[`nucleus_segmentation/crop_nucleus.md`](nucleus_segmentation/crop_nucleus.md)
and the full operational guide in
[`docs/ND2_TO_TRAJECTORY_OPERATIONAL_GUIDE.md`](docs/ND2_TO_TRAJECTORY_OPERATIONAL_GUIDE.md).

## Stage 2: Trajectory Extraction

CrisprTrack v5 converts a single-cell TIFF into audited per-locus trajectories:

```text
crop TIFF + metadata sidecar + exact micro-SAM mask
  -> Fiji drift correction and channel separation
  -> per-frame mask alignment
  -> experiment-profile validation and locked-anchor tracking
  -> one static irregular ROI per accepted anchor
  -> ROI-gated MATLAB 2-D Gaussian SPT
  -> v5 linking across global gaps no longer than trackMem
  -> deterministic longest candidate per allele and channel
  -> Python/MATLAB QC and machine-readable audit files
```

Minimal single-cell invocation:

```bash
python trajectory_extraction/run_full_pipeline_v4.py /path/to/cell.tif \
  --fiji-bin /path/to/ImageJ \
  --matlab-bin matlab \
  --experiment-profile dsb_53bp1_site1_site2
```

For the four-channel manuscript acquisition use
`--experiment-profile chr3_sites_2_3_4`. Both profiles lock raw channel C2 as
the anchor while retaining its distinct biological identity. Channel count,
source-name evidence, ND2 channel order, calibration, and sidecar association
are hard-validated before Fiji or MATLAB starts.

The selected baseline files are written below
`anchor_roi_v4_<experiment_profile>/baseline_longest/`. Each trajectory CSV
contains `frame`, `x_nm`, and `y_nm` in whole-image coordinates. Missing frames
are valid; rows must not be renumbered to make a trajectory appear contiguous.

Complete requirements, parameters, output trees, algorithms, validation, and
troubleshooting are documented in
[`trajectory_extraction/README.md`](trajectory_extraction/README.md).

The v5 dev1 benchmark used 219 exact-pixel inputs. Relative to v4.2.2, v5
increased non-empty samples from 189 to 190, baselines from 833 to 883, and
complete G/P/R alleles from 77 to 98. Mean baseline length changed only from
11.18 to 11.21 points, while the paired per-sample longest-track mean changed
from 12.70 to 12.84 points. Thus the demonstrated benefit is primarily higher
recovery and three-channel completeness, not a large global shift in typical
trajectory length. See `provenance/DEVELOPMENT_HISTORY_CN.md` for the full
interpretation and limitations.

## Stage 3: Cellular Feature Extraction

`Cellular_feature_extraction/` retains the reference repository's feature
extraction tools. `extract_features.py` combines mask geometry, intensity, and
DNA-locus location; `extract_nuclear_features.py` provides standalone nuclear
morphology extraction. These modules were not changed by v5 dev1.

Example:

```bash
python Cellular_feature_extraction/extract_features.py \
  /path/to/nucleus_folder --pixel-size 108.33
```

## Stage 4: Trajectory-To-Feature Modeling

The modeling workflows ask whether chromatin motion encodes nuclear morphology,
local chromatin density, and spatial context.
`trajectory_to_nuclear_features/traditional_ml/` contains grouped engineered-
feature baselines; `trajectory_to_nuclear_features/deep_learning/` contains
CNN/LSTM and engineered-feature neural models. See
[`trajectory_to_nuclear_features/README.md`](trajectory_to_nuclear_features/README.md)
for the derived-data layout and reproduction commands. These workflows were not
modified or revalidated by v5 dev1.

## External Requirements

The full workflow combines:

- Python for segmentation, metadata validation, trajectory orchestration, QC,
  and modeling;
- Fiji/ImageJ with **Correct 3D Drift** for Stage-2 preprocessing;
- MATLAB for 2-D Gaussian single-particle tracking;
- CUDA-capable PyTorch for practical micro-SAM throughput, although CPU mode is
  supported.

Install the appropriate pinned dependency set:

```bash
python -m pip install -r requirements_nd2_to_traj.txt
```

Environment evidence is intentionally recorded as a matrix rather than a
single claimed requirement:

| Environment | Python | MATLAB | Scope |
| --- | --- | --- | --- |
| Local development | 3.12.11 | R2025b Update 1 | v5 source and MATLAB regressions |
| Sherlock production | 3.12.1 | R2022b | synthetic, DSB smoke, and 219-input benchmark |
| Current pinned files | see requirements files | batch-capable MATLAB | reproducible installation contract |

All required MATLAB helper files are bundled below
`trajectory_extraction/pipeline/matlab_deps/`.

## Associated Manuscript

Chen*, X., Zhu*, Y., Washington, K., Chan, T.-K., Shamsher, N., and Qi, L. S.
**Genomic DNA Dynamics Predict Chromatin Density Features in Living Cells.**
(* equal contribution)

The trajectory-analysis interpretation also follows Zhu et al., 2025,
**High-resolution dynamic imaging of chromatin DNA communication using
Oligo-LiveFISH**. Published/manual trajectories, historical v3 outputs, the
audited v4.2.2 baseline, and v5 outputs must remain separate provenance layers.

## Contributors

- Xinyi Chen (Stanford University)
- Yanyu Zhu (Stanford University)
- Kenaj Washington (Stanford University)
- Tse-Kai (Kevin) Chan (Stanford University)
- Nikhiya Shamsher (Stanford University)
- Zhehao Zhang (v4/v5 automation, validation, and DSB workflow development)

