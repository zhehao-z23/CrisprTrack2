# CrisprTrack (CRISPR-mediated Chromatin Dynamics Tracking)

Automated, profile-locked trajectory extraction and single-particle tracking
(SPT) for live-cell Oligo-LiveFISH imaging. The production workflow converts a
single-cell, multi-channel TIFF plus its acquisition sidecar and exact
micro-SAM mask into audited 2-D Gaussian trajectories for the G/R/P channels.

The current code version is **`v5.0.0-dev1-trackmem-global-gap`**. The production
entry points are still named `run_full_pipeline_v4.py` and
`run_batch_pipeline_v4.py`, and result directories still begin with
`anchor_roi_v4_`. Those names and the output layout are intentionally retained
for compatibility; runtime manifests identify the run as v5.

v5 dev1 changes one tracking boundary relative to the audited v4.2.2 baseline:
a frame in which no particle is detected anywhere in an ROI no longer forces a
split when the number of globally missing frames is less than or equal to
`trackMem`. All other detection, localization, ROI, linking-radius, and
baseline-selection rules remain unchanged.

## Quick Start

Start from a verified v5 snapshot or worktree and run commands from the
repository root.

```bash
# 1. Enter the verified v5 repository
cd /path/to/OligoLiveFish-ML-ZZH-v5

# 2. Create an isolated environment and install the pinned ND2-to-trajectory stack
python -m venv .venv_nd2_to_traj
source .venv_nd2_to_traj/bin/activate          # Linux/macOS
# .\.venv_nd2_to_traj\Scripts\Activate.ps1   # Windows PowerShell
python -m pip install --upgrade pip
python -m pip install -r requirements_nd2_to_traj.txt

# 3. Confirm the external applications are available
fiji --help
matlab -batch "disp(version)"

# 4. Run one Step-3 single-cell crop with the correct locked profile
python trajectory_extraction/run_full_pipeline_v4.py \
  /path/to/single_cell.tif \
  --fiji-bin /path/to/Fiji.app/ImageJ-linux64 \
  --matlab-bin matlab \
  --experiment-profile chr3_sites_2_3_4
```

Fiji must include **Correct 3D drift**. The input TIFF must have its adjacent
`<cell>_metadata.json` sidecar and the exact micro-SAM mask referenced by that
sidecar. No manually cleaned trajectory is required or read.

---

## Table of Contents

1. [Overview](#overview)
2. [Requirements](#requirements)
3. [Input files](#input-files)
4. [Pipeline scripts](#pipeline-scripts)
5. [Running the pipeline](#running-the-pipeline)
6. [Parameters](#parameters)
7. [Output files](#output-files)
8. [Algorithm details](#algorithm-details)
9. [Validation scripts](#validation-scripts)

---

## Overview

The v5 production pipeline has three analysis stages:

```text
Stage 1  profile validation, Fiji preprocessing, exact micro-SAM mask
         alignment, and profile-locked anchor extraction
         -> corrected channel TIFFs, aligned nucleus support, anchor paths

Stage 2  static anchor-ROI construction and ROI-restricted MATLAB SPT
         -> every G/R/P 2-D Gaussian candidate trajectory

Stage 3  deterministic longest-baseline selection and read-only QC
         -> cleaned baseline CSVs, manifests, audits, PNGs, and SVGs
```

The complete sequence is:

```text
Step-3 single-cell TIFF + acquisition sidecar + exact micro-SAM mask
  -> validate one locked biological profile
  -> Fiji drift correction and channel separation
  -> align the saved micro-SAM support to every corrected frame
  -> detect and filter the profile-locked anchor trajectories
  -> convert each accepted anchor into one static irregular ROI
  -> admit peaks only inside that ROI and fit on the unmasked image
  -> link detections with the v5 global-gap boundary
  -> export every SPT candidate
  -> select one deterministic longest baseline per allele/channel
  -> generate spatial and time-coloured QC without changing selection
```

The old v3 reference-distance matcher and its 2,000 nm rejection threshold are
not called by either production runner. Reference paths remain a spatial prior
for ROI construction and QC; they are not final SPT trajectories.

For manuscript comparisons, keep these four data layers separate:

1. externally released or manually curated published trajectories;
2. the historical v2.13/v3 published-style implementation;
3. the audited v4.2.2 production baseline;
4. v5 dev1 with the global-gap change described below.

Do not write these layers into one result directory or describe a historical
implementation as byte-identical to released data without an explicit
validation.

---

## Requirements

### Python packages

Install the complete pinned stack from the repository root:

```bash
python -m pip install -r requirements_nd2_to_traj.txt
python -m pip check
```

Important direct dependencies in the pinned file include:

| Package | Pinned version | Role |
| --- | ---: | --- |
| `numpy` | `2.4.6` | numerical arrays and trajectory calculations |
| `scipy` | `1.18.0` | image registration and morphology |
| `Pillow` | `12.2.0` | TIFF metadata support |
| `matplotlib` | `3.11.0` | Python QC figures |
| `scikit-image` | `0.26.0` | phase-correlation registration |
| `tifffile` | `2026.6.1` | calibrated TIFF I/O |
| `nd2` | `0.11.3` | upstream ND2 metadata/pixel access |
| `dask[array]` | `2026.6.0` | lazy upstream image access |
| `torch` | `2.10.0` | upstream micro-SAM backend |
| `micro-sam` | `1.8.4` | upstream nucleus segmentation |

The pinned Windows workflow was validated with Python 3.13.14. v5 source and
MATLAB regressions have also been run in Python 3.12 environments, including
Sherlock. Record the actual Python executable and package environment for each
scientific batch; do not assume two environments are byte-identical. See
[`../REQUIREMENTS_ND2_TO_TRAJ.md`](../REQUIREMENTS_ND2_TO_TRAJ.md) for the full
environment guide and CUDA-specific micro-SAM installation rules.

### External dependencies

- **Fiji/ImageJ** with **Correct 3D drift** installed. Pass its executable with
  `--fiji-bin` when `fiji` is not on `PATH`.
- **MATLAB** with non-interactive `-batch` support. The local helper functions
  are bundled under `pipeline/matlab_deps/`; no separate SPT checkout is
  required.
- A GPU is recommended for the upstream micro-SAM nucleus-segmentation step,
  but the trajectory runner itself can reuse already exported crops and masks.

Quick checks:

```bash
matlab -batch "disp(version)"
python -c "import numpy, scipy, skimage, tifffile; print('PYTHON_STACK_OK')"
```

---

## Input files

The production runner starts from one crop TIFF exported by
`nucleus_segmentation/save_crops.py`, not directly from an ND2 file.

| Required input | Contract |
| --- | --- |
| `<cell>.tif` | One single-cell multi-frame TIFF with axes `TCYX` or `TZCYX`. |
| `<cell>_metadata.json` | Mandatory Step-3 sidecar containing source ND2, crop geometry, calibration, raw channel order, and exact mask association. |
| Exact micro-SAM mask TIFF | The mask referenced by `microsam_mask.path` or `microsam_mask.relative_path` in the sidecar. It may be overridden only with a verified `--microsam-mask`. |
| `--experiment-profile` | Exactly one of the two locked profiles below. It determines channel identity and the anchor. |

The TIFF and sidecar must agree on channel count. Calibration must include a
plausible pixel size and frame interval. After Fiji preprocessing, all G/R/P
channels must have identical frame count, frame interval, pixel size, and image
shape.

### Locked experiment profiles

| Profile | Raw channel contract | Corrected G/R/P meaning | Locked anchor |
| --- | --- | --- | --- |
| `chr3_sites_2_3_4` | C0 contains `405`; C1 `640`; C2 `488`; C3 `561` | C2 -> G / Site 2 / chr3:195M / A488; C1 -> R / Site 4 / chr3:198M / A647; C3 -> P / Site 3 / chr3:195.7M / A565 | raw C2 / green / Site 2 |
| `dsb_53bp1_site1_site2` | C0 contains `GFP`; C1 `RFP`; C2 `Cy5` | C0 -> G / 53BP1; C1 -> R / Site 1; C2 -> P / Site 2 | raw C2 / purple / Site 2 |

The Chr3 profile requires four channels and filename/source evidence containing
`chr3`, `195M`, `195.7M`, `198M`, `488`, `565`, and `647`. The DSB profile
requires three channels and at least one of `DSB` or `53BP1` in the
filename/source evidence. A profile, filename, channel-count, sidecar, or raw
channel-name mismatch is a hard error.

The Chr3 profile aligns the saved mask through the raw C0 nucleus channel. The
DSB profile has no morphology-grade nucleus channel and aligns through raw C0
53BP1/green; its synthetic `_Nucleus.tif` is a pipeline scaffold and must not be
used for nuclear morphology measurements.

When `--no-fiji` is used, the input is the existing Fiji analysis directory,
but the original crop TIFF remains mandatory for profile validation and mask
alignment. Pass it with `--crop-tif` if it cannot be inferred as
`<analysis_dir>.tif`.

---

## Pipeline scripts

| Script or module | Role |
| --- | --- |
| `run_full_pipeline_v4.py` | Production v5 entry point for one Step-3 crop. The `_v4` filename is retained for compatibility. |
| `run_batch_pipeline_v4.py` | Validated multi-cell wrapper with dry-run, resume, and bounded cell/MATLAB concurrency. The `_v4` filename and summary name are retained for compatibility. |
| `pipeline/headless_Macro_first_steps_for_published.ijm` | Fiji drift correction and G/R/P channel separation. |
| `pipeline/experiment_profiles.py` | Owns the only accepted channel contracts, biological labels, filename evidence, and locked anchors. |
| `pipeline/align_microsam_mask.py` | Resolves the exact saved mask and drift-aligns it to corrected frames. |
| `pipeline/auto_roi_for_published_v2.13.py` | Extracts reference/anchor paths using the supplied aligned mask. Historical filename retained. |
| `pipeline/run_anchor_roi_spt.py` | Builds static ROIs, runs MATLAB SPT, audits all candidates, and selects baselines. |
| `pipeline/spt_batch.m` | Headless band-pass filtering, peak detection, sub-pixel fitting, and tracking for one ROI/channel TIFF. |
| `pipeline/matlab_deps/spt_track.m` | Applies the v5 global-gap boundary and calls the legacy linker. |
| `pipeline/max_step_model.py` | Converts metadata and physical priors into the operational linking radius. |
| `pipeline/visualize_anchor_roi_results.py` | Read-only Python spatial QC. |
| `pipeline/plot_longest_trajectories.m` | Time-coloured PNG/SVG plots of selected baselines. |

Historical v3 matching modules remain under `pipeline/` for controlled
reproducibility, but neither production runner invokes them.

---

## Running the pipeline

### Single dataset

From the repository root:

```bash
python trajectory_extraction/run_full_pipeline_v4.py \
  "/path/to/<cell>.tif" \
  --fiji-bin "/path/to/Fiji.app/ImageJ-linux64" \
  --matlab-bin matlab \
  --matlab-workers 1 \
  --experiment-profile chr3_sites_2_3_4
```

DSB example:

```bash
python trajectory_extraction/run_full_pipeline_v4.py \
  "/path/to/DSB_<cell>.tif" \
  --fiji-bin "/path/to/Fiji.app/ImageJ-linux64" \
  --matlab-bin matlab \
  --matlab-workers 1 \
  --experiment-profile dsb_53bp1_site1_site2
```

The runner creates the Fiji analysis directory next to the crop TIFF. Do not
pre-create that stem-specific directory. On Windows, Unicode parent paths are
bridged through a temporary ASCII directory link; the TIFF filename itself
must remain ASCII and retain `.tif` or `.tiff`.

The primary log is:

```text
<cell>/anchor_roi_v4_<experiment_profile>/log_anchor_roi_v4.txt
```

The adjacent `run_manifest.json` records the v5 version, profile contract,
validated inputs, Python executable, options, status, and elapsed time.

### Reuse existing Fiji outputs

```bash
python trajectory_extraction/run_full_pipeline_v4.py \
  "/path/to/<cell>" \
  --no-fiji \
  --crop-tif "/path/to/<cell>.tif" \
  --matlab-bin matlab \
  --experiment-profile chr3_sites_2_3_4
```

`--no-fiji` reuses corrected channel files only. It does not remove the need
for the original crop, sidecar, exact mask, profile validation, or a fresh
profile-namespaced SPT result.

### Batch datasets

List and validate candidates first:

```bash
python trajectory_extraction/run_batch_pipeline_v4.py \
  "/path/to/crop_directory" \
  --crop-glob "<stem>_*.tif" \
  --fiji-bin "/path/to/Fiji.app/ImageJ-linux64" \
  --matlab-bin matlab \
  --experiment-profile chr3_sites_2_3_4 \
  --cell-workers 1 \
  --matlab-workers 1 \
  --dry-run
```

Remove `--dry-run` only after the list is correct. Resume is enabled by
default and skips only a completed manifest whose scientific and MATLAB-worker
settings match the requested run. Use `--no-resume` only for an intentional
fresh run.

Peak MATLAB processes equal `cell-workers * matlab-workers`. Increase only one
parallel dimension at a time and obey the local scheduler and license policy.
The batch summary is written as:

```text
trajectory_batch_v4_<experiment_profile>_summary.csv
```

---

## Parameters

### Production runner parameters

| Parameter | Default | Description |
| --- | ---: | --- |
| `input_path` | required | Step-3 crop TIFF; with `--no-fiji`, an existing Fiji analysis directory. |
| `--experiment-profile` | required | `chr3_sites_2_3_4` or `dsb_53bp1_site1_site2`; locks identity and anchor. |
| `--fiji-bin` | `fiji` | Fiji executable. |
| `--matlab-bin` | `matlab` | MATLAB executable or command. |
| `--matlab-workers` | `1` | Concurrent G/R/P MATLAB groups; allowed values are 1, 2, or 3. |
| `--matlab-save-filter-images` | off | Retain the large band-pass-filtered movie in MAT output. |
| `--microsam-mask` | associated mask | Explicit exact-mask override; normally do not use. |
| `--mask-dilation-px` | `5` | Expansion after per-frame drift alignment. |
| `--roi-geometry` | `tube` | Ordered anchor-path tube, or `convex_hull`. |
| `--roi-dilation-px` | `5` | Static ROI expansion. Production requires at least 5 px. |
| `--d-star` | `0.0041` | Anomalous diffusion prior in µm²/s^alpha. |
| `--alpha` | `0.38` | Anomalous diffusion exponent. |
| `--coverage-probability` | `0.995` | Radial coverage probability `p`. |
| `--localization-error-nm` | `0` | Per-axis localization-error term. |
| `--max-step-frame-gap` | `1` | Lag used to calculate the one operational radius. |
| `--max-step-rounding-px` | `0.05` | Upward pixel-rounding increment. |
| `--max-step-px` | physical model | Explicit positive override, recorded in the audit. |
| `--no-fiji` | off | Reuse an existing corrected analysis directory. |
| `--crop-tif` | inferred | Original crop required with `--no-fiji` when inference fails. |

Batch adds `--crop-glob "*.tif"`, `--cell-workers 1`, `--resume` (on by
default), `--no-resume`, and `--dry-run`.

Changing a scientific parameter requires a fresh run and a recorded reason.
The single-cell runner cleans only its own generated profile/geometry result
subdirectories before rerunning; archive a completed result first if it must be
retained.

### Locked reference/anchor extraction constants

These constants live in `pipeline/auto_roi_for_published_v2.13.py`. They are
not free-form production CLI parameters.

| Parameter | Value | Description |
| --- | ---: | --- |
| `K_SIGNAL['green']` | `2.0` | Green threshold multiplier, `mean + k * std`. |
| `K_SIGNAL['red']` | `0.5` | Red threshold multiplier. |
| `K_SIGNAL['purple']` | `0.5` | Purple threshold multiplier. |
| `NUCLEUS_OUTSIDE_FRAC` | `0.10` | Reject an anchor when more than 10% of checkable positions are outside supplied support. |
| `MIN_SPOT_PX` | `10` | Minimum connected-component area. |
| `N_MAX` | `5` | Maximum accepted anchor loci. |
| `PADDING` | `20` px | Bounding-box context retained by the low-level reference stage. |
| `ADJACENCY_PX` | `30` px | Reference-path overlap grouping distance. |
| `INTER_FRAME_MAX_NM` | `500` nm | Purple reference-track displacement limit. |
| `INTER_FRAME_MAX_NM_RED` | `750` nm | Red reference-track displacement limit. |
| `REFERENCE_PROX_MAX_UM` | `3.0` µm | Maximum target-reference proximity. |
| `SEED_MAX_FRAME` | `5` | Early frames searched for a target-channel seed. |
| `MAX_BLOB_PX` | `120` px | Area above which an overlap-group blob is re-examined. |
| `_ADAPTIVE_K_STEPS` | `[1.0, 1.5, 2.0]` | Progressive local thresholds for splitting a merged blob. |

`NUCLEUS_SIGMA=2.0` and `FILL_RATIO=0.85` remain in the historical low-level
module. In the production v5 path, the nucleus boundary is supplied explicitly
from the aligned micro-SAM mask and is not rebuilt from intensity/Otsu.

### Static ROI parameters

For `tube`, the complete time-ordered anchor path is rasterized as one
centerline. For `convex_hull`, its concavities are filled first. Both are
dilated by `roi-dilation-px`, intersected with frame 1 of the aligned/dilated
micro-SAM support, required to remain connected, and then reused unchanged for
all movie frames.

Peak centers are admitted only inside this ROI. Pixels outside it are not
zeroed before Gaussian fitting, so a near-edge peak retains its full fitting
window. `boxr=9` is the odd fit-box width, or a 4 px half-width; therefore the
production ROI dilation may not be below 5 px.

Convex-hull runs are isolated under
`anchor_roi_v4_<experiment_profile>_convex_hull`. Tube results remain under the
backward-compatible `anchor_roi_v4_<experiment_profile>` path.

### Metadata-to-physics maximum-step model

Unless `--max-step-px` is supplied, the operational linking radius is:

```text
tau = frame_gap * frame_interval_s
r_p(tau) = sqrt[-4 ln(1-p) * (D_star * tau^alpha + sigma_loc^2)]
max_step_px = ceil[(r_p / pixel_size_um) / rounding_increment]
              * rounding_increment
```

Locked defaults are `D_star=0.0041 µm²/s^alpha`, `alpha=0.38`, `p=0.995`,
`sigma_loc=0 nm`, `frame_gap=1`, and upward rounding to `0.05 px`. For the
validated FOV15 metadata (`1.0114487 s/frame`, `0.1083333 µm/px`), the
theoretical radius is `2.726893 px` and the operational radius is `2.75 px`.

The model writes sensitivity values for other gaps, but the current linker
uses the same one operational `max_disp` after every allowed gap. v5 dev1 does
not silently apply gap-scaled radii.

### MATLAB SPT parameters

| Parameter | Value/source | Description |
| --- | --- | --- |
| `f_rate` | TIFF metadata | Frame rate, `1 / frame_interval_s`. |
| `pixl` | TIFF metadata | Pixel size in µm/px. |
| `thresh` | `mean(nz) + 0.5 * std(nz)` | `nz` is the positive part of the band-pass-filtered first frame. |
| `dia` | `5` px | Particle diameter used by filtering/detection. |
| `boxr` | `9` px | Odd 2-D Gaussian fit-box width. |
| `mtl` | `3` | Legacy minimum-length setting; passed to `track.m` as `good=mtl+1`. |
| `trackMem` | `3` frames | Maximum globally missing-frame count retained in one v5 tracking block. |
| `fitmethod` | `0` | 2-D Gaussian (`1` would be centroid). |
| `IntTh` | `0` | Integrated-intensity threshold disabled. |
| `estD` | `0.001 µm²/s` | Legacy fallback prior; production normally passes the explicit physical-model radius. |
| `saveFilterImgMode` | `0` | Filtered movie omitted unless `--matlab-save-filter-images` is set. |

### v5 global-gap rule

The audited v4.2.2 code split the detection table before `track.m` at every
globally empty detection frame:

```matlab
jump = find(t_posnew);
```

v5 dev1 uses:

```matlab
jump = find(t_posnew > param.mem);
```

`t_posnew` is the number of globally missing frames between adjacent detection
times, and `param.mem` comes directly from `sptpara.trackMem`. With the current
`trackMem=3`, gaps of one to three globally empty frames remain in one block;
four or more force a split. Remaining in one block only makes linking possible:
the unchanged spatial linker and fixed `max_disp` still decide whether two
detections are connected.

Do not remove all pre-segmentation. The legacy `track.m` iterates over unique
detection times rather than the absolute frame grid; without this explicit
boundary it could link across arbitrarily long global gaps.

### Baseline selection

All ROI-restricted candidates are retained. One baseline is selected
independently for each accepted allele and G/R/P channel by:

1. maximum number of trajectory points;
2. tie: maximum frame span;
3. tie: earliest first frame;
4. tie: lowest candidate number.

A missing candidate is recorded explicitly and produces no baseline CSV.
Neither a manually cleaned trajectory nor reference-track distance participates
in this rule.

---

## Output files

All output is written beside the input crop. The primary tree is:

```text
<cell>.tif
<cell>_metadata.json
<associated micro-SAM mask>.tif
<cell>/
  <cell>_Nucleus.tif
  <cell>_green.tif
  <cell>_red.tif
  <cell>_purple.tif
  anchor_roi_v4_<experiment_profile>/
    run_manifest.json
    log_anchor_roi_v4.txt
    mask_alignment/
      microsam_mask_aligned_raw.tif
      microsam_mask_aligned_dilated_5px.tif
      drift_alignment.csv
      mask_alignment_audit.json
      microsam_mask_alignment_qc.png
    anchor_stage1/
      Nucleus_masks.tif
      RoiSet_<profile-locked-anchor>.zip
      <anchor-prefix>_loci<N>_traj_rela2wholeimg.csv
    static_union_rois/
      allele_<N>_loci<M>_static_anchor_roi.tif
    roi_spt/
      allele_<N>_loci<M>/
        matlab_result/
          <cell>_<channel>.mat
          matlab_trajectory/
            [GPR]_m2DGaussian_traj<N>.csv
    baseline_longest/
      allele_<N>_<marker_slug>_longest_spt_cleaned.csv
      baseline_manifest.csv
    audit/
      max_step_model.json
      static_anchor_roi_geometry.csv
      all_candidate_trajectories.csv
      baseline_selection.csv
    figures/
      python_spatial_qc/
        01_anchor_mask_roi_overview.png
        02_all_candidates_fixed_coordinates.png
        03_candidate_length_and_baseline.png
      matlab_longest/
        allele_<N>_<marker>_longest_spt.png
        allele_<N>_<marker>_longest_spt.svg
    anchor_roi_v4_summary.json
```

For `--roi-geometry convex_hull`, the result directory gains the
`_convex_hull` suffix. The names retain `v4` for output compatibility, while
`run_manifest.json` and `anchor_roi_v4_summary.json` record the v5 version.

Every candidate and baseline trajectory CSV has:

```text
frame,x_nm,y_nm
```

Frames are 1-indexed, coordinates are in the corrected whole-image coordinate
system, and temporal gaps are valid. The workflow is 2-D; it does not output a
`z` coordinate.

The `*_longest_spt_cleaned.csv` files are the automated v5 deliverable. Here,
“cleaned” means ROI-restricted SPT followed by the declared deterministic
longest-track rule. It does not mean manual editing or old reference-distance
matching. `baseline_manifest.csv` can be present but contain no rows when no
channel yields a baseline.

The Python figures show corrected-channel projections, aligned support, the
static ROI, every candidate, and the selected baselines in one fixed coordinate
system. MATLAB figures center coordinates on the trajectory median, invert Y to
Cartesian orientation, and encode acquisition time by colour. SVGs use explicit
RGB segments to avoid black trajectories during vector export.

---

## Algorithm details

### Stage 1 — Profile validation, mask alignment, and anchor extraction

1. `experiment_profiles.py` validates TIFF axes/channel count, the adjacent
   sidecar, raw channel indices/names, and filename/source evidence before Fiji
   or MATLAB starts.
2. Fiji drift-corrects the crop and separates its biological channels into the
   historical `green`, `red`, and `purple` filenames.
3. The exact saved micro-SAM instance mask is resolved from the sidecar. It is
   registered independently to every corrected frame by phase correlation,
   dilated by 5 px by default, and audited. The production path does not replace
   it with an intensity/Otsu boundary.
4. The profile chooses the anchor automatically. Stage 1 detects candidate
   anchor loci from the time-averaged anchor image, follows them through time,
   and rejects an anchor when more than 10% of checkable positions lie outside
   the aligned support.
5. For each accepted anchor, its complete time-ordered path becomes either a
   tube centerline or filled convex hull. The geometry is dilated, intersected
   with frame 1 of the aligned/dilated support, required to remain connected,
   and reused unchanged for all frames.

### Stage 2 — ROI-restricted MATLAB SPT and v5 linking

For each accepted allele and G/R/P channel:

1. Candidate peak centers are admitted only inside the static ROI. The source
   image remains unmasked so a near-boundary peak keeps its full fit window.
2. Each frame is band-pass filtered with low-pass 1 px and band-pass
   `dia+2=7` px.
3. The first filtered frame sets the threshold to
   `mean(nz) + 0.5 * std(nz)`.
4. `pkfnd` detects peaks and `pkRefnd` refines them by 2-D Gaussian fitting with
   `dia=5` and `boxr=9`.
5. `spt_track.m` keeps gaps no larger than `trackMem` in one block, splits
   larger gaps, and invokes the unchanged legacy linker with the one
   metadata/physics-derived `max_disp`.
6. Every retained MATLAB trajectory is exported to an individual candidate
   CSV. No candidate is removed by reference distance.

### Stage 3 — Baseline selection and QC

1. Candidate metrics include point count, first/last frame, frame span,
   temporal coverage, maximum missing frames, step statistics, and static-ROI
   containment.
2. The deterministic rule selects at most one baseline for each
   allele/channel and records missing combinations.
3. Candidate, selection, ROI-geometry, max-step, profile, and run provenance are
   written to CSV/JSON audits.
4. Python and MATLAB QC read the completed outputs. They do not regenerate,
   filter, or reselect trajectories.

Before accepting a batch, verify that anchors lie inside biological support,
each ROI follows one anchor and is connected, candidates lie on visible signal,
selected baselines are biologically plausible, and `max_step_model.json`
contains the expected calibration and priors. Trajectory length is a selection
rule, not proof of trajectory quality.

---

## Validation scripts

### Automated v5 regression suites

| Script/test | Coverage |
| --- | --- |
| `tests/run_v5_local_tests.cmd` | One-command Windows source-contract and MATLAB runtime suite; expected marker `V5_LOCAL_TESTS_OK`. |
| `tests/run_v5_sherlock_tests.sh` | Sherlock Python/MATLAB suite; expected marker `V5_SHERLOCK_TESTS_OK`. |
| `tests/test_spt_track_global_gap_memory.m` | One- and two-frame gaps, exact memory boundary, larger hard boundary, and particle identity. |
| `tests/test_spt_batch_global_gap_integration.m` | Temporary-TIFF threshold, detection, globally empty frame, and final linking integration. |
| `tests/test_v42_v5_spt_batch_gap_control.m` | Same-TIFF control demonstrating v4.2 fragmentation and v5 recovery under otherwise unchanged settings. |
| `tests/test_spt_track_global_gap_contract.py` | Dependency-free source contract for the v5 boundary. |
| `tests/test_v5_version_contract.py` | Version stamping in the three trajectory runtime manifests. |
| `tests/verify_v5_overlay.sh` | Non-destructive overlay and checksum verification for Sherlock deployment. |

From Windows PowerShell at the repository root:

```powershell
.\tests\run_v5_local_tests.cmd
```

On Sherlock, first load the documented Python and MATLAB modules, then run:

```bash
bash tests/run_v5_sherlock_tests.sh
```

### Interactive/manual validation helpers

| Script | Role |
| --- | --- |
| `pipeline/spt.m` | Historical interactive MATLAB 2-D Gaussian workflow for controlled comparison. |
| `pipeline/export_trajectories.py` | Exports trajectories from a selected MAT file for comparison. |

Manual trajectories may be introduced only after the automated run for
validation. They must not select candidates, define ROIs, or filter automated
baselines.

### Known limits of v5 dev1

- The change is limited to global gaps no larger than `trackMem`; it does not
  implement timestamp-aware linking or a gap-scaled search radius.
- Every allowed gap still uses the same operational `max_disp`.
- The ROI is static across the movie and depends on an accepted, profile-locked
  anchor path.
- Only the two declared acquisition profiles are accepted. A new acquisition
  order requires a reviewed profile/macro change, not relabelling data to make
  validation pass.
- The DSB synthetic nucleus scaffold is not valid for morphology analysis.
- The pipeline is 2-D and outputs only `x_nm` and `y_nm`.
- Longest-track selection can prefer a long artifact; visual and quantitative
  QC remain required.
- A technical success, the presence of `baseline_manifest.csv`, and the
  presence of a non-empty biological baseline are distinct states.
- v5 does not prove equivalence to manual or released trajectories. Such claims
  require a separately documented, non-circular same-input validation.

For every scientific run, retain the crop TIFF, acquisition sidecar, exact mask
association, `run_manifest.json`, mask/max-step audits, all candidate and
selection tables, baselines, and QC figures. Record all non-default parameters
and the reason for changing them.
