# Changelog

## 5.2.1 — 2026-08-18

- Integrate the frozen per-frame 53BP1 component, continuous-intensity and
  bounded-distance measurements into the formal DSB single-cell and batch
  runners as a sidecar stage after baseline selection.
- Save a compressed TYX label stack, frame segmentation table, component and
  conservative adjacent-frame lineage table, dense allele-by-frame metrics,
  allele summaries, source hashes, timing provenance and interpretation limits.
- Preserve the v5.2 candidate QC, P/R reference, ROI, SPT, linker and longest-
  baseline contracts exactly; P/Site2-only alleles remain valid inputs.
- Add synthetic end-to-end/no-R tests and real-crop equivalence validation
  against the frozen 53BP1 pilot.

### 5.2.0 53BP1 locus metrics addendum

- Add independent Site2/P-centred 53BP1 readouts: a continuous local-excess
  intensity metric with a 1.7-um aperture and no positivity cutoff, plus a
  segmented-component boundary-distance metric that fails closed at 1.0 um.
- Preserve signed intensity audits, signed component-boundary distance,
  rejected-nearest-component evidence and ambiguity margins; missing, distant
  or ambiguous components receive distance score zero without suppressing the
  independent intensity measurement.
- Add synthetic contract tests and a Chinese parameter/data-contract document.
  Full-cohort workflow integration remains gated on pilot review.

## 5.2.0 — 2026-08-18

- Add a DSB-only P-gated, Red-autonomous reference path. Purple defines a
  2.5-um per-frame harvest domain and canonical allele identities; Red
  detections link only to Red detections within the fixed 750-nm reference
  limit. Adjacent frames have priority and at most one missing frame is
  tolerated; there is no Purple-position fallback or interpolation.
- Pair Red candidates to Purple identities by median P-R distance on at least
  five common frames and at least 25% of all movie frames. Accept only
  reciprocal one-to-one matches with at least a 1-px bilateral alternative
  margin; ambiguous loci fail closed without a Red SPT run.
- Use channel-specific DSB ROIs: Green/Purple use the Purple reference, while
  Red uses its uniquely paired autonomous Red reference.
- Add `validated_segment_convex_hull`: split a reference at a non-adjacent
  frame or excessive channel-fixed step, fill a convex hull independently for
  each legal segment, union the segment hulls, dilate by 5 px, and intersect
  with the aligned 0-px micro-SAM support. Disconnected segment unions are
  retained and audited rather than bridged.
- Make the new reference/ROI policy the `auto` default only for the DSB
  profile; retain the legacy target-reference and tube defaults for Chr3.
- Add full detection, common-frame pairing, ROI-transition and coordinate
  audits, a reusable 16-case reference/ROI validation utility, synthetic
  no-fallback/no-bridge tests, and robust long-path MATLAB QC export.

## 5.1.0 — 2026-08-05

- Set drift-aligned micro-SAM mask expansion to 0 px by default; keep the
  independent 5 px anchor-ROI dilation required by Gaussian fit support.
- Lock `D*=0.0041`, `alpha=0.38` and solve one movie-level radius whose product
  of adjacent-step inclusion probabilities is 0.975; prefer exact crop-sidecar
  ND2 intervals, audit a uniform TIFF fallback, and round upward to 0.05 px.
- Retain the same scalar radius after every v5-permitted gap; do not fit D per
  cell/ND2 and do not add a gap-scaled linker.
- Select reference seeds from global time-average connected components using
  minimum area, 100% consensus-mask containment, a 3 px inner edge band with
  at most 10% occupancy, original mean-intensity ranking and a Top-5 cap.
- Split DSB Purple reference thresholds into `k_seed=1.645` and
  `k_tracking=0.5`; record every component decision and accepted trajectory
  length in `reference_detection_audit.json`.
- Add one versioned coordinate module for automatic 1-based pixel centres,
  ThunderSTORM 0.5-based ROI-local centres, FIJI ROI edges and 1-based frames;
  update QC overlays and cellular feature extraction to use it.
- Add synthetic regression tests for reference policy, trajectory-level
  max-disp probability, exact sidecar timing, coordinate transforms and runner
  defaults, plus a complete Chinese analysis/provenance contract.

## 5.0.0-dev1-trackmem-global-gap — 2026-07-29

- Fork the clean v4.2.2 worktree into a separate v5 development snapshot;
  retain the complete v4.2.2 source unchanged.
- Change the `spt_track.m` global-gap boundary from “split at every missing
  frame” to “split only when globally missing frames exceed `trackMem`”.
- Preserve v4 behavior exactly when `trackMem=0`.
- Keep the existing fixed `max_disp`; this release does not implement
  timestamp-aware or gap-scaled search radii.
- Add MATLAB runtime regressions for one- and two-frame global gaps, exact
  memory boundaries, and two-particle identity preservation.
- Add dependency-free Python source-contract tests and a one-command local
  test runner.
- Stamp all three trajectory runtime manifests with the v5 dev1 version while
  retaining the existing runner filenames and output layout for compatibility.
- Add a temporary-TIFF integration test that exercises first-frame threshold
  calculation, particle detection, a globally empty frame and final linking.
- Add a local same-TIFF v4.2/v5 control: v4.2 remains fragmented while v5
  recovers the expected trajectory under the unchanged production parameters.
- Add a non-destructive Sherlock deployment overlay, checksum workflow and
  synthetic preflight runner before any real-data smoke test.

## 4.2.2-convex-hull-roi — 2026-07-25

- Add an explicit `tube` versus `convex_hull` static anchor-ROI option.
- Fill anchor-path concavities before dilation for the convex-hull policy, then
  retain the existing intersection with aligned micro-SAM support.
- Store convex-hull runs in a separate result directory so existing tube
  results are never overwritten.
- Record ROI geometry in run manifests, summaries and geometry audits.
- Resolve candidate-selection symlinks before batch resume checks.

## 4.2.1-nd2-frame-timestamps — 2026-07-24

- Read exact per-timepoint acquisition timestamps from ND2 frame metadata,
  including acquisitions represented by `NETimeLoop`.
- Store the complete relative-time axis and observed frame intervals in every
  crop metadata sidecar.
- Use the median observed interval as the representative ImageJ TIFF interval,
  while retaining the exact nonuniform timestamps for downstream analysis.
- Treat `periodMs` and `periodDiff.avg` consistently as milliseconds when exact
  frame metadata is unavailable.
- Add a metadata-only ND2 audit command that checks channel contracts, exact
  timestamp coverage and nonuniform-time review flags without loading pixels.

## 4.2.0-candidate-preserving-qc — 2026-07-22

- Preserve every unmodified micro-SAM instance by default in a separate output tree,
  including its cropped mask, exportable crop JSON and stable candidate ID.
- Add `candidate_selection_manifest.csv` with direct QC annotations,
  exclusion reasons and a blank manual-decision field; no candidate is deleted.
- Materialize `spt_included` and `spt_excluded` TIFF views from default or
  manual decisions without moving or duplicating archived candidate data.
- Make the ordinary crop export command automatically export the default
  sibling candidate archive, ensuring every candidate receives a full TIFF.
- Add reproducible `strict`, `no_badqc`, `publicationlike`, and `all` policy
  views so one all-candidate SPT run can support later gate comparisons.
- Add a checked-in policy comparison command that joins final per-cell SPT
  status to those views and reports success and baseline-length statistics.
- Keep the locked v4.1.6 filtered analysis output unchanged unless the new
  candidate archive option is explicitly requested.

## 4.1.6-experiment-profiles — 2026-07-20

- Fixed the segmented-frame MATLAB SPT path when `track.m` returns no
  retained trajectories for an individual segment.
- Return an explicit empty trajectory result before accessing trajectory
  column 4 when every eligible segment produces no retained trajectory.
- Preserve completed v4.1.5 results; affected technical failures can be
  retried through the existing resume workflow.

## 4.1.5-experiment-profiles — 2026-07-19

- Fix the legacy MATLAB single-track boundary so every row of the only
  retained trajectory is renumbered consistently as track ID 1.
- Extend the Sherlock MATLAB regression to cover zero retained trajectories
  and exactly one retained trajectory without changing scientific parameters.

## 4.1.4-experiment-profiles — 2026-07-18

- Assign the correctly shaped empty matrix to the declared MATLAB `tracks`
  output before the legacy `track.m` empty-result branch returns.
- Extend the regression contract to prevent an unassigned-output failure while
  preserving all v4.1.3 tracking parameters and locked experiment profiles.

## 4.1.3-experiment-profiles — 2026-07-18

- Return an empty matrix from legacy MATLAB `track.m` before its post-processing
  indexes the first row when no tracks survive linking or length filtering.
- Keep the v4.1.2 common `spt_track.m` empty-result handling and validate both
  layers with the Sherlock MATLAB regression smoke test.

## 4.1.2-experiment-profiles — 2026-07-18

- Treat an empty MATLAB `track.m` result as a valid zero-trajectory outcome
  for both consecutive- and non-consecutive-frame inputs.
- Preserve empty channel/allele results without changing thresholds, minimum
  trajectory length or other scientific tracking parameters.
- Add a MATLAB regression smoke test for multi-frame detections that produce
  no retained trajectories.

## 4.1.1-experiment-profiles — 2026-07-18

- Preserved the two locked v4.1 biological experiment profiles while adding
  three runtime fixes recovered from the audited Sherlock smoke-test clone.
- Return an explicit empty trajectory result when legacy MATLAB SPT receives
  detections from fewer than two frames.
- Normalize literal `\\u00b5`/`\\u03bc` TIFF spatial-unit metadata before the
  physical max-step validation.
- Read baseline CSV manifests with an explicit text/CSV contract and export
  SVG through the MATLAB R2022b-compatible `print -dsvg` path.

## 4.1.0-experiment-profiles — 2026-07-18

- Added two and only two locked biological acquisition profiles:
  `chr3_sites_2_3_4` and `dsb_53bp1_site1_site2`.
- Locked raw C2 as the anchor in both profiles while preserving its distinct
  biological identity: Chr3 Site 2/A488 for the four-channel manuscript data,
  and Site 2/Purple for the three-channel DSB data.
- Added hard profile validation for channel count and filename evidence before
  Fiji or MATLAB starts.
- Required the Step-3 acquisition sidecar and validated the original ND2
  channel-name order (`405/640/488/561` or `GFP/RFP/Cy5`) before execution.
- Removed the free-form production anchor override and moved marker names,
  slugs, fluorophores, genomic loci and raw indices into the profile contract.
- Namespaced outputs by profile so results from the two experiments cannot
  overwrite or be resumed as each other.
- Removed hard-coded 53BP1/Site1/Site2 labels from CSV, Python QC and MATLAB
  figure generation.

## 4.0.0-anchor-roi — 2026-07-14

This release promotes the validated FOV15 static anchor-ROI experiment to the
production ND2-to-trajectory workflow.

### Changed

- Fixed the nucleus-mask handoff: every exported crop records its exact
  micro-SAM instance mask, which is aligned to Fiji-corrected frames and passed
  explicitly to anchor tracking. The production path no longer silently
  replaces this boundary with intensity/Otsu segmentation.
- Made Purple the default anchor channel. Accepted complete anchor paths define
  one connected, 5 px-dilated static irregular ROI, intersected with the aligned
  micro-SAM support and reused for every movie frame.
- Restricted SPT peak admission to the anchor ROI while retaining the unmasked
  image pixels required by the 2-D Gaussian fitting window.
- Replaced v3 reference-distance matching, the 2,000 nm filter, and greedy
  assignment in the production path with a deterministic per-allele/channel
  longest-candidate baseline. All candidates remain available for audit.
- Exposed the linking step radius as a metadata-to-physics model with declared
  `D*`, anomalous exponent, coverage probability, localization error, lag, and
  rounding parameters; an explicit CLI override remains available and audited.
- Added automatic Python spatial QC and MATLAB time-coloured PNG/SVG plots of
  selected baselines. SVG trajectories use explicit RGB line segments.
- Added new single-cell and multi-cell production entry points:
  `run_full_pipeline_v4.py` and `run_batch_pipeline_v4.py`.

### Validated regression

- FOV15 metadata produces a theoretical `2.726893 px` radius and the approved
  upward-rounded operational value `2.75 px`.
- micro-SAM alignment is pixel-identical to the approved experimental aligned
  mask.
- Purple anchor outputs for loci 2, 3, and 5 are byte-identical to Run 03.
- All 27 ROI-SPT candidate CSVs are byte-identical to Run 03.
- The deterministic baseline selects 6 available allele/channel tracks and
  records the 3 no-candidate combinations.
- MATLAB export produces 6 PNG and 6 coloured SVG figures for those baselines.

### Migration

The former v3 top-level runners are removed from the production interface.
Low-level v3 matching modules remain in `trajectory_extraction/pipeline/` only
for historical reproducibility; the v4 runners never call them. Existing v3
result folders are not upgraded in place—archive them and rerun from the
Step-3 crop TIFF and associated micro-SAM mask.
