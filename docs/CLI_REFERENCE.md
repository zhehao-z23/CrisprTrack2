# Complete CLI reference

Generated from every production Python argparse declaration. Defaults shown as expressions refer to constants in that file.
See [PARAMETERS.md](PARAMETERS.md) for units and scientific interpretation. Run each script with `--help` for runtime usage.

## `crisprtrack2.py`

| Argument | Default / required | Type / choices | Help / source |
|---|---|---|---|
| --config | required | Path | JSON containing segmentation and tracking options |
| --input | required | Path | ND2 file or directory; only read by the segment stage |
| --run-root | required | Path | Dedicated output root; segment/all require a new directory |
| --stage | all | str; ('all', *STAGES) | [definition](../crisprtrack2.py#L57) |
| --plan | false | str | Print commands without running applications or writing output |

## `nucleus_segmentation/audit_nd2_time_metadata.py`

| Argument | Default / required | Type / choices | Help / source |
|---|---|---|---|
| input_root | required | Path | [definition](../nucleus_segmentation/audit_nd2_time_metadata.py#L142) |
| --output | required | Path | [definition](../nucleus_segmentation/audit_nd2_time_metadata.py#L143) |
| --expected-channel-token | [] | str | Required token for the corresponding zero-based raw channel. |
| --review-cv | 0.1 | float | [definition](../nucleus_segmentation/audit_nd2_time_metadata.py#L150) |
| --review-max-ratio | 1.25 | float | [definition](../nucleus_segmentation/audit_nd2_time_metadata.py#L151) |

## `nucleus_segmentation/cell_crop_qc.py`

| Argument | Default / required | Type / choices | Help / source |
|---|---|---|---|
| --fov17-metrics | required | str | CSV with fov17 ch0_contrast/ch0_boundary_grad metrics |
| --fov7-metrics |  | str | Optional CSV with fov7 validation metrics |
| --out-dir | required | str | Output directory for CSV and PNG artifacts |

## `nucleus_segmentation/crop_nuclei_sam.py`

| Argument | Default / required | Type / choices | Help / source |
|---|---|---|---|
| input | required | str | .nd2 file or directory of .nd2 files |
| --nucleus-channel | 0 | int | [definition](../nucleus_segmentation/crop_nuclei_sam.py#L1235) |
| --margin | 30 | int | [definition](../nucleus_segmentation/crop_nuclei_sam.py#L1236) |
| --min-area | 1000 | int | [definition](../nucleus_segmentation/crop_nuclei_sam.py#L1237) |
| --max-area | 200000 | int | [definition](../nucleus_segmentation/crop_nuclei_sam.py#L1238) |
| --border-margin | DEFAULT_BORDER_MARGIN_PX | int | Min distance (px) from image border to nucleus centroid |
| --mask-border-margin | -1 | int | Drop masks whose pixels are <= this many px from image border; -1 disables |
| --segmentation-mode | apg | str; ['apg', 'amg'] | [definition](../nucleus_segmentation/crop_nuclei_sam.py#L1241) |
| --model-type | vit_b_lm | str | [definition](../nucleus_segmentation/crop_nuclei_sam.py#L1242) |
| --device | auto | str; ['auto', 'cuda', 'mps', 'cpu'] | [definition](../nucleus_segmentation/crop_nuclei_sam.py#L1243) |
| --output-root |  | str | Optional output parent; defaults to the ND2 parent |
| --preserve-all-candidates | True | str | Preserve every raw micro-SAM instance in a separate archive (default: enabled; use --no-preserve-all-candidates to disable). |
| --candidate-output-root |  | str | Optional separate output parent for all raw micro-SAM candidates. By default, <output-root>_all_usam_candidates is used. Keep this outside --output-root so analysis cannot discover candidates twice. |

## `nucleus_segmentation/materialize_candidate_selection.py`

| Argument | Default / required | Type / choices | Help / source |
|---|---|---|---|
| candidate_root | required | Path | [definition](../nucleus_segmentation/materialize_candidate_selection.py#L136) |
| output_root | required | Path | [definition](../nucleus_segmentation/materialize_candidate_selection.py#L137) |
| --policy | strict | str; sorted(POLICY_IGNORED_REASONS) | QC policy used when manual_decision is blank: strict, no_badqc, publicationlike, or all (default: strict). |

## `nucleus_segmentation/save_crops.py`

| Argument | Default / required | Type / choices | Help / source |
|---|---|---|---|
| input | required | str | directory containing *_crops.json files (searched recursively) |
| --include-sibling-candidates | True | str | Also export <input>_all_usam_candidates when present (default: enabled; use --no-include-sibling-candidates to disable). |

## `trajectory_extraction/pipeline/align_microsam_mask.py`

| Argument | Default / required | Type / choices | Help / source |
|---|---|---|---|
| crop_tiff | required | Path | [definition](../trajectory_extraction/pipeline/align_microsam_mask.py#L291) |
| analysis_dir | required | Path | [definition](../trajectory_extraction/pipeline/align_microsam_mask.py#L292) |
| --microsam-mask | None | Path | [definition](../trajectory_extraction/pipeline/align_microsam_mask.py#L293) |
| --alignment-channel | auto | str; ('auto', 'nucleus', 'green') | [definition](../trajectory_extraction/pipeline/align_microsam_mask.py#L294) |
| --raw-channel-index | None | int | [definition](../trajectory_extraction/pipeline/align_microsam_mask.py#L295) |
| --dilation-px | 0 | int | [definition](../trajectory_extraction/pipeline/align_microsam_mask.py#L296) |
| --output-dir | None | Path | [definition](../trajectory_extraction/pipeline/align_microsam_mask.py#L297) |

## `trajectory_extraction/pipeline/auto_roi_for_published_v2.13.py`

| Argument | Default / required | Type / choices | Help / source |
|---|---|---|---|
| nucleus_path | required | Path | Path to the *_Nucleus.tif file. |
| --reference-channel | purple | str; CHANNELS | Legacy standalone Stage-1 anchor (default: purple). Production v4.1 always supplies the locked anchor from its experiment profile. |
| --nucleus-mask | None | Path | Optional drift-aligned binary micro-SAM TYX mask. When supplied, it is used directly for anchor filtering instead of rebuilding a nucleus boundary with per-frame intensity Otsu. |
| --output-dir | None | Path | Directory for Stage-1 CSV/ROI/mask outputs (default: TIFF directory). |
| --reference-seed-k | None | float | Override the time-average reference candidate threshold coefficient. |
| --reference-tracking-k | None | float | Override the independent per-frame reference tracking coefficient. |
| --reference-edge-width-px | REFERENCE_EDGE_WIDTH_PX | float | Inner nucleus boundary-band width used for reference candidate filtering. |
| --reference-max-edge-fraction | REFERENCE_MAX_EDGE_FRACTION | float | Maximum fraction of an intact reference component inside the boundary band. |
| --target-reference-mode | legacy | str; ('legacy', 'p_gated_r_autonomous', 'independent_r_autonomous') | legacy keeps historical target tracking; p_gated_r_autonomous uses P for every-frame Red harvest; independent_r_autonomous builds Red tracks over the whole nucleus and consults P only at final pairing. |
| --red-harvest-radius-um | DSB_RED_HARVEST_RADIUS_UM | float | [definition](../trajectory_extraction/pipeline/auto_roi_for_published_v2.13.py#L1361) |
| --red-min-track-points | DSB_RED_MIN_TRACK_POINTS | int | [definition](../trajectory_extraction/pipeline/auto_roi_for_published_v2.13.py#L1364) |
| --red-min-shared-frames | DSB_RED_MIN_SHARED_FRAMES | int | [definition](../trajectory_extraction/pipeline/auto_roi_for_published_v2.13.py#L1367) |
| --red-min-movie-coverage-fraction | DSB_RED_MIN_MOVIE_COVERAGE_FRACTION | float | [definition](../trajectory_extraction/pipeline/auto_roi_for_published_v2.13.py#L1370) |
| --red-max-missing-frames | DSB_RED_MAX_MISSING_FRAMES | int | [definition](../trajectory_extraction/pipeline/auto_roi_for_published_v2.13.py#L1375) |
| --red-uniqueness-margin-px | DSB_RED_UNIQUENESS_MARGIN_PX | float | [definition](../trajectory_extraction/pipeline/auto_roi_for_published_v2.13.py#L1378) |

## `trajectory_extraction/pipeline/export_bp1_locus_metrics.py`

| Argument | Default / required | Type / choices | Help / source |
|---|---|---|---|
| analysis_dir | required | Path | [definition](../trajectory_extraction/pipeline/export_bp1_locus_metrics.py#L141) |
| --aligned-nucleus-mask | required | Path | [definition](../trajectory_extraction/pipeline/export_bp1_locus_metrics.py#L142) |
| --baseline-manifest | required | Path | [definition](../trajectory_extraction/pipeline/export_bp1_locus_metrics.py#L143) |
| --crop-metadata-sidecar | None | Path | [definition](../trajectory_extraction/pipeline/export_bp1_locus_metrics.py#L144) |
| --output-dir | required | Path | [definition](../trajectory_extraction/pipeline/export_bp1_locus_metrics.py#L145) |

## `trajectory_extraction/pipeline/max_step_model.py`

| Argument | Default / required | Type / choices | Help / source |
|---|---|---|---|
| tiff | required | Path | [definition](../trajectory_extraction/pipeline/max_step_model.py#L424) |
| --crop-metadata-sidecar | None | Path | [definition](../trajectory_extraction/pipeline/max_step_model.py#L425) |
| --d-star | DEFAULT_D_STAR | float | [definition](../trajectory_extraction/pipeline/max_step_model.py#L426) |
| --alpha | DEFAULT_ANOMALOUS_EXPONENT | float | [definition](../trajectory_extraction/pipeline/max_step_model.py#L427) |
| --trajectory-coverage | DEFAULT_TRAJECTORY_COVERAGE | float | [definition](../trajectory_extraction/pipeline/max_step_model.py#L428) |
| --localization-error-nm | 0.0 | float | [definition](../trajectory_extraction/pipeline/max_step_model.py#L433) |
| --rounding-increment-px | 0.05 | float | [definition](../trajectory_extraction/pipeline/max_step_model.py#L434) |
| --track-mem | 3 | int | [definition](../trajectory_extraction/pipeline/max_step_model.py#L435) |
| --max-step-px | None | float | [definition](../trajectory_extraction/pipeline/max_step_model.py#L436) |
| --output | None | Path | [definition](../trajectory_extraction/pipeline/max_step_model.py#L437) |

## `trajectory_extraction/pipeline/run_anchor_roi_spt.py`

| Argument | Default / required | Type / choices | Help / source |
|---|---|---|---|
| analysis_dir | required | Path | [definition](../trajectory_extraction/pipeline/run_anchor_roi_spt.py#L488) |
| --anchor-dir | required | Path | [definition](../trajectory_extraction/pipeline/run_anchor_roi_spt.py#L489) |
| --aligned-microsam-mask | required | Path | [definition](../trajectory_extraction/pipeline/run_anchor_roi_spt.py#L490) |
| --output-dir | None | Path | [definition](../trajectory_extraction/pipeline/run_anchor_roi_spt.py#L491) |
| --experiment-profile | required | str; experiment_profiles.profile_choices() | [definition](../trajectory_extraction/pipeline/run_anchor_roi_spt.py#L492) |
| --roi-geometry | tube | str; ('tube', 'convex_hull', 'validated_segment_convex_hull') | Static ROI seed: the temporally ordered anchor-path tube (backward-compatible default), or the filled convex hull of that path. Both are dilated and intersected with micro-SAM support. |
| --channel-specific-reference-mode | legacy | str; ('legacy', 'p_r_specific') | p_r_specific uses P reference/ROI for Green+Purple and the uniquely paired autonomous R reference/ROI for Red. |
| --roi-dilation-px | 5 | int | [definition](../trajectory_extraction/pipeline/run_anchor_roi_spt.py#L516) |
| --matlab-bin | matlab | str | [definition](../trajectory_extraction/pipeline/run_anchor_roi_spt.py#L517) |
| --matlab-workers | 1 | int; (1, 2, 3) | [definition](../trajectory_extraction/pipeline/run_anchor_roi_spt.py#L518) |
| --matlab-save-filter-images | false | str | [definition](../trajectory_extraction/pipeline/run_anchor_roi_spt.py#L519) |
| --crop-metadata-sidecar | None | Path | Crop _metadata.json containing exact ND2 frame intervals; uniform TIFF timing is the audited fallback. |
| --d-star | 0.0041 | float | [definition](../trajectory_extraction/pipeline/run_anchor_roi_spt.py#L525) |
| --alpha | 0.38 | float | [definition](../trajectory_extraction/pipeline/run_anchor_roi_spt.py#L526) |
| --trajectory-coverage-probability | 0.975 | float | [definition](../trajectory_extraction/pipeline/run_anchor_roi_spt.py#L527) |
| --localization-error-nm | 0.0 | float | [definition](../trajectory_extraction/pipeline/run_anchor_roi_spt.py#L528) |
| --max-step-rounding-px | 0.05 | float | [definition](../trajectory_extraction/pipeline/run_anchor_roi_spt.py#L529) |
| --max-step-px | None | float | Explicit override; otherwise use the metadata/physical model. |

## `trajectory_extraction/pipeline/validate_v52_reference_strategy.py`

| Argument | Default / required | Type / choices | Help / source |
|---|---|---|---|
| case_manifest | required | Path | [definition](../trajectory_extraction/pipeline/validate_v52_reference_strategy.py#L102) |
| output_dir | required | Path | [definition](../trajectory_extraction/pipeline/validate_v52_reference_strategy.py#L103) |
| --harvest-radius-um | 2.5 | float | [definition](../trajectory_extraction/pipeline/validate_v52_reference_strategy.py#L104) |
| --roi-dilation-px | 5 | int | [definition](../trajectory_extraction/pipeline/validate_v52_reference_strategy.py#L105) |
| --red-max-missing-frames | 1 | int | [definition](../trajectory_extraction/pipeline/validate_v52_reference_strategy.py#L106) |
| --red-min-movie-coverage-fraction | 0.25 | float | [definition](../trajectory_extraction/pipeline/validate_v52_reference_strategy.py#L107) |

## `trajectory_extraction/pipeline/visualize_anchor_roi_results.py`

| Argument | Default / required | Type / choices | Help / source |
|---|---|---|---|
| analysis_dir | required | Path | [definition](../trajectory_extraction/pipeline/visualize_anchor_roi_results.py#L232) |
| --results-dir | None | Path | [definition](../trajectory_extraction/pipeline/visualize_anchor_roi_results.py#L233) |
| --output-dir | None | Path | [definition](../trajectory_extraction/pipeline/visualize_anchor_roi_results.py#L234) |
| --aligned-microsam-mask | None | Path | [definition](../trajectory_extraction/pipeline/visualize_anchor_roi_results.py#L235) |

## `trajectory_extraction/run_batch_pipeline_v4.py`

| Argument | Default / required | Type / choices | Help / source |
|---|---|---|---|
| crop_dir | required | Path | [definition](../trajectory_extraction/run_batch_pipeline_v4.py#L217) |
| --crop-glob | *.tif | str | [definition](../trajectory_extraction/run_batch_pipeline_v4.py#L218) |
| --fiji-bin | fiji | str | [definition](../trajectory_extraction/run_batch_pipeline_v4.py#L219) |
| --matlab-bin | matlab | str | [definition](../trajectory_extraction/run_batch_pipeline_v4.py#L220) |
| --experiment-profile | required | str; experiment_profiles.profile_choices() | Required locked biological channel contract; it determines the anchor automatically. |
| --cell-workers | 1 | int | [definition](../trajectory_extraction/run_batch_pipeline_v4.py#L227) |
| --matlab-workers | 1 | int; (1, 2, 3) | [definition](../trajectory_extraction/run_batch_pipeline_v4.py#L228) |
| --matlab-save-filter-images | false | str | [definition](../trajectory_extraction/run_batch_pipeline_v4.py#L229) |
| --mask-dilation-px | 0 | int | [definition](../trajectory_extraction/run_batch_pipeline_v4.py#L230) |
| --reference-seed-k | None | float | [definition](../trajectory_extraction/run_batch_pipeline_v4.py#L231) |
| --reference-tracking-k | None | float | [definition](../trajectory_extraction/run_batch_pipeline_v4.py#L232) |
| --reference-edge-width-px | 3.0 | float | [definition](../trajectory_extraction/run_batch_pipeline_v4.py#L233) |
| --reference-max-edge-fraction | 0.1 | float | [definition](../trajectory_extraction/run_batch_pipeline_v4.py#L234) |
| --roi-geometry | auto | str; ('auto', 'tube', 'convex_hull', 'validated_segment_convex_hull') | [definition](../trajectory_extraction/run_batch_pipeline_v4.py#L235) |
| --target-reference-mode | auto | str; ('auto', 'legacy', 'p_gated_r_autonomous', 'independent_r_autonomous') | [definition](../trajectory_extraction/run_batch_pipeline_v4.py#L240) |
| --red-harvest-radius-um | 2.5 | float | [definition](../trajectory_extraction/run_batch_pipeline_v4.py#L250) |
| --red-min-track-points | 5 | int | [definition](../trajectory_extraction/run_batch_pipeline_v4.py#L251) |
| --red-min-shared-frames | 5 | int | [definition](../trajectory_extraction/run_batch_pipeline_v4.py#L252) |
| --red-min-movie-coverage-fraction | 0.25 | float | [definition](../trajectory_extraction/run_batch_pipeline_v4.py#L253) |
| --red-max-missing-frames | 1 | int | [definition](../trajectory_extraction/run_batch_pipeline_v4.py#L254) |
| --red-uniqueness-margin-px | 1.0 | float | [definition](../trajectory_extraction/run_batch_pipeline_v4.py#L255) |
| --roi-dilation-px | 5 | int | [definition](../trajectory_extraction/run_batch_pipeline_v4.py#L256) |
| --d-star | 0.0041 | float | [definition](../trajectory_extraction/run_batch_pipeline_v4.py#L257) |
| --alpha | 0.38 | float | [definition](../trajectory_extraction/run_batch_pipeline_v4.py#L258) |
| --trajectory-coverage-probability | 0.975 | float | [definition](../trajectory_extraction/run_batch_pipeline_v4.py#L259) |
| --localization-error-nm | 0.0 | float | [definition](../trajectory_extraction/run_batch_pipeline_v4.py#L260) |
| --max-step-rounding-px | 0.05 | float | [definition](../trajectory_extraction/run_batch_pipeline_v4.py#L261) |
| --max-step-px | None | float | [definition](../trajectory_extraction/run_batch_pipeline_v4.py#L262) |
| --resume | True | str | [definition](../trajectory_extraction/run_batch_pipeline_v4.py#L263) |
| --dry-run | false | str | [definition](../trajectory_extraction/run_batch_pipeline_v4.py#L264) |

## `trajectory_extraction/run_full_pipeline_v4.py`

| Argument | Default / required | Type / choices | Help / source |
|---|---|---|---|
| input_path | required | Path | Step-3 crop TIFF, or Fiji analysis directory with --no-fiji. |
| --no-fiji | false | str | Reuse an existing Fiji analysis directory. |
| --crop-tif | None | Path | Original crop TIFF for --no-fiji if it cannot be inferred as <analysis_dir>.tif. |
| --crop-metadata-sidecar | None | Path | Override the standard <crop>_metadata.json timing sidecar. |
| --microsam-mask | None | Path | Override the crop-associated micro-SAM mask. |
| --fiji-bin | fiji | str | [definition](../trajectory_extraction/run_full_pipeline_v4.py#L87) |
| --matlab-bin | matlab | str | [definition](../trajectory_extraction/run_full_pipeline_v4.py#L88) |
| --matlab-workers | 1 | int; (1, 2, 3) | [definition](../trajectory_extraction/run_full_pipeline_v4.py#L89) |
| --matlab-save-filter-images | false | str | [definition](../trajectory_extraction/run_full_pipeline_v4.py#L90) |
| --experiment-profile | required | str; experiment_profiles.profile_choices() | Required locked biological channel contract; it determines the anchor automatically. |
| --mask-dilation-px | 0 | int | Drift-aligned micro-SAM support expansion. Final v5.1 default is 0 px. |
| --reference-seed-k | None | float | [definition](../trajectory_extraction/run_full_pipeline_v4.py#L103) |
| --reference-tracking-k | None | float | [definition](../trajectory_extraction/run_full_pipeline_v4.py#L104) |
| --reference-edge-width-px | 3.0 | float | [definition](../trajectory_extraction/run_full_pipeline_v4.py#L105) |
| --reference-max-edge-fraction | 0.1 | float | [definition](../trajectory_extraction/run_full_pipeline_v4.py#L106) |
| --roi-geometry | auto | str; ('auto', 'tube', 'convex_hull', 'validated_segment_convex_hull') | Static anchor ROI geometry. Tube preserves the v4.2.1 behavior; convex_hull writes to an isolated result directory. |
| --target-reference-mode | auto | str; ('auto', 'legacy', 'p_gated_r_autonomous', 'independent_r_autonomous') | auto selects the v5.2 whole-nucleus autonomous Red mode for DSB; P is consulted only during final identity pairing. |
| --red-harvest-radius-um | 2.5 | float | [definition](../trajectory_extraction/run_full_pipeline_v4.py#L130) |
| --red-min-track-points | 5 | int | [definition](../trajectory_extraction/run_full_pipeline_v4.py#L131) |
| --red-min-shared-frames | 5 | int | [definition](../trajectory_extraction/run_full_pipeline_v4.py#L132) |
| --red-min-movie-coverage-fraction | 0.25 | float | [definition](../trajectory_extraction/run_full_pipeline_v4.py#L133) |
| --red-max-missing-frames | 1 | int | [definition](../trajectory_extraction/run_full_pipeline_v4.py#L134) |
| --red-uniqueness-margin-px | 1.0 | float | [definition](../trajectory_extraction/run_full_pipeline_v4.py#L135) |
| --roi-dilation-px | 5 | int | [definition](../trajectory_extraction/run_full_pipeline_v4.py#L136) |
| --d-star | 0.0041 | float | [definition](../trajectory_extraction/run_full_pipeline_v4.py#L137) |
| --alpha | 0.38 | float | [definition](../trajectory_extraction/run_full_pipeline_v4.py#L138) |
| --trajectory-coverage-probability | 0.975 | float | [definition](../trajectory_extraction/run_full_pipeline_v4.py#L139) |
| --localization-error-nm | 0.0 | float | [definition](../trajectory_extraction/run_full_pipeline_v4.py#L140) |
| --max-step-rounding-px | 0.05 | float | [definition](../trajectory_extraction/run_full_pipeline_v4.py#L141) |
| --max-step-px | None | float | Explicit override; default is metadata + physical-prior model. |
