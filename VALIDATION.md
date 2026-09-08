# Closeout validation (2026-09-08)

- Frozen scientific source: v5.2.1 / 9f4e28a7bdaa6847e876fa9e3de059de197d0441.
- `python -m unittest discover -s tests -p "test_*.py"`: **60 tests passed** using existing Python 3.13.14.
- Tests cover candidate preservation/selection, profile and mask contracts, gap linking source contracts,
  physical max-step derivation, coordinate conventions, 53BP1 measurement behavior, the new command wrapper,
  and rejection of previous completion when Red coverage/gap parameters change.
- Existing environment versions: numpy 2.4.6, scipy 1.18.0, pandas 3.0.3, matplotlib 3.11.0,
  tifffile 2026.6.1, torch 2.10.0, scikit-image 0.26.0.
- Existing environment has nd2 0.11.1; install documentation retains its reviewed replacement 0.11.3.
  The closeout did not reread scientific ND2 data or validate segmentation on that package difference.
- No complete microscopy/Fiji/MATLAB/GPU extraction or MATLAB runtime regression was rerun.
  Existing MATLAB synthetic regressions are retained for a machine with MATLAB available.

The first test invocation from the enclosing workspace failed to import repository modules;
the documented invocation from the repository root passed. No test skips are concealed as passes.
