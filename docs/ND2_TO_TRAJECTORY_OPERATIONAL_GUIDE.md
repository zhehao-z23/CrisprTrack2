# ND2 to trajectory operational guide — CrisprTrack2 v5.2.1

The current workflow is documented in the [root README](../README.md):

1. Create a Python environment using [requirements.txt](../requirements.txt), with Fiji and MATLAB available.
2. Start from an ND2 file/directory, or a verified crop TIFF with acquisition metadata and its exact mask.
3. Copy [the DSB configuration](../configs/dsb_v521.json), set executable paths, and inspect `crisprtrack2.py --plan`.
4. Run `segment`, `export`, `track` individually, or `all` with a new output root.
5. Read the batch summary and each crop's `run_manifest.json`; retain failures and candidate selection provenance.
6. Hand downstream users trajectories together with identities, timing, calibration and QC; retain fullrun image assets for visual review.

Every parameter is described in [PARAMETERS](PARAMETERS.md), with a source-derived exhaustive
[CLI reference](CLI_REFERENCE.md). [Nucleus segmentation detail](../nucleus_segmentation/crop_nucleus.md)
describes the candidate archive and independent selection views.

Background algorithm derivations:

- [v5.1 mask and movie-level displacement contract](V5_1_FINAL_ANALYSIS_STRATEGY_CN.md)
- [v5.2 autonomous Red/channel-specific ROI](V5_2_DSB_CHANNEL_SPECIFIC_REFERENCE_STRATEGY_CN.md)
- [v5.2.1 53BP1 measurement integration](V5_2_1_53BP1_BATCH_INTEGRATION_CN.md)

Historical v5-dev1 operational instructions and deployment payloads are available from Git history;
they do not define the current installation or run commands.
