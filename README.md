# CrisprTrack2

An auditable pipeline from **multichannel ND2 → nucleus segmentation → single-nucleus TIFF → trajectory extraction**.
The scientific implementation is frozen at **v5.2.1 / `9f4e28a7bdaa6847e876fa9e3de059de197d0441`**.
This repository adds a unified entry point, parameter documentation, and a defined project scope while retaining the original scientific algorithms, thresholds, and output names.

| Repository | Input | Responsibilities and outputs |
|---|---|---|
| **CrisprTrack2** | ND2, or exported TIFF + metadata + exact mask | Segmentation, drift correction, ROI/SPT, trajectory CSVs, extraction QC, and 53BP1 measurement sidecars |
| [ChromatinDynamics-Biophysics](https://github.com/zhehao-z23/ChromatinDynamics-Biophysics) | Trajectories, timing and identity metadata, extraction audits | Scientific QC, MSD/MSCD/VAC/VCC, model assessment, and static/dynamic visualization |
| [ChromatinDynamics-ML](https://github.com/zhehao-z23/ChromatinDynamics-ML) | Frozen trajectory/physics tables and targets | Fingerprinting, unsupervised stratification, supervised learning, and published benchmarks |

Legacy `Cellular_feature_extraction/`, `trajectory_to_nuclear_features/`, example results, and v2/v3 comparison runners have been removed from the current tree.
Git history is retained; the [archive and provenance guide](docs/ARCHIVE_AND_PROVENANCE.md) documents their sources and recovery.

## 1. Installation and starting inputs

Requirements: Python, Fiji with **Correct 3D drift**, and MATLAB with **Optimization Toolbox** (`lsqcurvefit` is used for Gaussian fitting). Segmentation also requires micro-SAM model weights and a compatible PyTorch environment.
Python dependencies and validated versions are listed in [requirements_nd2_to_traj.txt](requirements_nd2_to_traj.txt).
See the [environment guide](REQUIREMENTS_ND2_TO_TRAJ.md) for GPU/CUDA setup. Fiji, MATLAB, model weights, and virtual environments are external dependencies.

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

Two supported starting points:

- **Raw ND2:** a file or directory containing ND2 files, with original channel names, timing, and pixel calibration preserved.
- **Existing single-nucleus crops:** `cell.tif` (TCYX or TZCYX), a neighboring `cell_metadata.json`, and the exact micro-SAM mask for that crop. The selected profile checks channel counts, names, source tags, and sidecars. Arbitrary TIFFs or trajectory CSVs alone do not satisfy this input contract.

```text
raw/experiment.nd2                # Read-only source data
runs/new_run/                     # New output directory, separate from raw inputs
  segmented/<ND2 stem>/           # Nuclei, masks, and crops passing default segmentation gates
  all_usam_candidates/<ND2 stem>/ # Every raw candidate and QC decision; not automatically tracked
  workflow_config.json
  workflow_commands.json
```

## 2. Run the complete pipeline

Copy [configs/dsb_v521.json](configs/dsb_v521.json) and set `fiji_bin` / `matlab_bin` to your executable paths.
JSON keys correspond to CLI options: for example, `roi_dilation_px` maps to `--roi-dilation-px`; `null` uses the internal default.
The [parameter guide](docs/PARAMETERS.md) explains values, units, effects, and fixed constants; the [complete CLI reference](docs/CLI_REFERENCE.md) follows the source declarations.

```bash
# Print commands without starting analysis
python crisprtrack2.py --config configs/dsb_v521.json --input /data/raw --run-root /data/runs/test01 --plan
# Run segment → export → track
python crisprtrack2.py --config configs/dsb_v521.json --input /data/raw --run-root /data/runs/test01
```

`all` / `segment` require a new run root. The example uses one cell worker; maximum MATLAB concurrency is `cell_workers × matlab_workers`.
Start with `cell_workers=1` on a mechanical drive.
This configuration reproduces the code's default segmentation selection. Recover a historical study's reviewed candidate selection from its frozen manifest; default gates alone do not reconstruct that study cohort.

## 3. Staged runs and resuming

```bash
python crisprtrack2.py --config configs/dsb_v521.json --input /data/raw --run-root /data/runs/test01 --stage segment
python crisprtrack2.py --config configs/dsb_v521.json --input /data/raw --run-root /data/runs/test01 --stage export
python crisprtrack2.py --config configs/dsb_v521.json --input /data/raw --run-root /data/runs/test01 --stage track
```

`export` reads saved crop JSON and exports TIFFs from the original ND2 files, which must remain accessible.
`track` defaults to `resume=true`; the existing batch runner checks completion status. When changing scientific parameters, use a new run root or independent crop working copies. Do not mix configurations within a batch. The single-cell runner clears and rebuilds its generated result directory with the same name.

Existing crops can be processed without repeating segmentation:

```bash
python trajectory_extraction/run_full_pipeline_v4.py /data/cell.tif --experiment-profile dsb_53bp1_site1_site2 --fiji-bin /apps/Fiji/ImageJ-linux64 --matlab-bin matlab
python trajectory_extraction/run_batch_pipeline_v4.py /data/crops --crop-glob "**/*.tif" --experiment-profile dsb_53bp1_site1_site2 --dry-run
python trajectory_extraction/run_batch_pipeline_v4.py /data/crops --crop-glob "**/*.tif" --experiment-profile dsb_53bp1_site1_site2 --fiji-bin /apps/Fiji/ImageJ-linux64 --matlab-bin matlab
```

Reuse existing Fiji output:

```bash
python trajectory_extraction/run_full_pipeline_v4.py /data/cell_analysis --no-fiji --crop-tif /data/cell.tif --experiment-profile dsb_53bp1_site1_site2 --matlab-bin matlab
```

To change nucleus selection, preserve the raw candidate archive and create a separate selection view:

```bash
python nucleus_segmentation/save_crops.py /data/runs/test01/all_usam_candidates --no-include-sibling-candidates
python nucleus_segmentation/materialize_candidate_selection.py /data/runs/test01/all_usam_candidates /data/runs/selection_v2 --policy strict
python trajectory_extraction/run_batch_pipeline_v4.py /data/runs/selection_v2/spt_included --crop-glob "**/*.tif" --experiment-profile dsb_53bp1_site1_site2 --dry-run
```

Selection output is organized by FOV and can be processed recursively. Per-FOV audits are stored in `manifests/<FOV>/selection_summary.json`.
Selection views use symlinks; the runner resolves them and writes results beside the source crops. **Changing the selection label does not isolate analysis results.**
On Windows, symlink creation requires appropriate permissions and a supporting filesystem such as NTFS; exFAT does not support these views. Independent physical copies of crops are an alternative.
Before changing scientific parameters, create independent working copies of crops, sidecars, and masks. Do not rerun changed settings inside a frozen candidate archive.
Manual decisions take precedence over the policy; see the [nucleus documentation](nucleus_segmentation/crop_nucleus.md).

## 4. Outputs and downstream data contract

The default DSB analysis directory for each crop contains:

```text
anchor_roi_v4_dsb_53bp1_site1_site2_independent_r_autonomous_validated_segment_convex_hull/
  run_manifest.json                # Version, configuration, inputs, and completion status
  mask_alignment/                  # Exact masks aligned to drift-corrected images
  anchor_stage1/                    # Reference detections and association audits
  static_union_rois/                # Static ROIs built from valid segments
  roi_spt/                          # All SPT candidates and MATLAB outputs
  baseline_longest/
    baseline_manifest.csv          # Alleles, channels, coordinates, and sources
    allele_*_longest_spt_cleaned.csv
  53bp1_metrics/                    # Measurement sidecars; do not affect track selection
  audit/                            # Max-step, baseline, and other decisions
  figures/                          # Extraction-level QC
```

Final trajectory columns are **`frame,x_nm,y_nm`**, with coordinates in nm under the whole-image pixel-centre convention.
Preserve original frame numbers and missing frames: do not renumber, interpolate, or fill missing positions. Exact timing is in the crop sidecar; row numbers are not a time axis.
Downstream datasets must retain baseline manifests, profile/identity mappings, timing and pixel calibration, and QC audits. Trajectory CSVs alone are a portable subset and cannot reconstruct 53BP1 intensity measurements or raw-image QC.

## 5. Scientific conventions

- DSB: Purple defines canonical Site2 allele identities. Red/Site1 is detected autonomously across the nucleus, linked by Red continuity, and paired with Purple only at the final step.
- Red allows at most one missing frame, requires at least 5 track points and 5 shared frames, at least 25% movie coverage, and a median P–R distance of at most 2.5 µm over shared frames.
- P-only alleles remain valid. P/R ROIs are convex hulls of valid segments dilated by 5 px; the micro-SAM mask itself is not dilated.
- Gaussian SPT accepts peak centres only within the ROI while fitting unmasked image intensities. Movie-level 97.5% coverage determines one fixed maximum displacement.
- SPT `trackMem=3` and Red-reference `red_max_missing_frames=1` operate at different stages and are not interchangeable.
- The 53BP1 sidecar is measured after baseline selection; its values do not feed back into segmentation, ROI generation, SPT, or baseline selection.

`chr3_sites_2_3_4` is for the original manuscript's four-channel data; DSB data require `dsb_53bp1_site1_site2`.
Both profiles lock the anchor automatically. Filenames containing `v4` / `v2.13` are retained for compatibility, while their contents are the frozen v5.2.1 implementation.

## 6. Validation and provenance

```bash
python -m unittest discover -s tests -p "test_*.py"
# MATLAB regression on small synthetic data (requires MATLAB):
matlab -batch "addpath('tests'); test_spt_track_global_gap_memory"
```

See [VALIDATION.md](VALIDATION.md) for packaging validation and its limits. The study data were not re-extracted during repository preparation.
The algorithms originate from [chenxy19/OligoLiveFish-ML](https://github.com/chenxy19/OligoLiveFish-ML) and ZZH's v4–v5.2.1 changes.
Original author notices in MATLAB files are preserved; see the [provenance guide](docs/ARCHIVE_AND_PROVENANCE.md).
