# Scope, history and attribution

The extraction implementation is copied from the working tree at commit
`9f4e28a7bdaa6847e876fa9e3de059de197d0441`, branch
`agent/v5.1-finalized-analysis-strategy`, in `zhehao-z23/OligoLiveFish-ML-ZZH`.
The repository was renamed to CrisprTrack2 during closeout. The upstream repository is
https://github.com/chenxy19/OligoLiveFish-ML . Its available repository metadata did not declare a license;
this closeout does not assign a new license to inherited code. Existing file-level attribution is retained.

`provenance/SOURCE_MANIFEST.csv` records every retained source file and SHA256.
`provenance/REMOVED_FROM_CURRENT_TREE.txt` lists removed historical assets and unrelated code.
They remain recoverable from Git history, for example:

```bash
git show 9f4e28a:trajectory_to_nuclear_features/README.md
git archive 9f4e28a Cellular_feature_extraction trajectory_to_nuclear_features -o historical_modules.tar
```

The default checkout contains the current extraction path only. Historical comparison runners,
large example microscopy/MATLAB output, deployment payloads, old cloud-transfer logs and inherited
feature/ML code are excluded. Historical v5.1/v5.2 derivation documents remain as background for
the current algorithm; root README and PARAMETERS define the current entry points.

The new `crisprtrack2.py` only constructs subprocess commands and writes workflow records.
No scientific implementation parameter is changed by the repository split. A packaging-time resume
correctness fix adds Red movie coverage and maximum missing frames to the batch completion comparison;
changing either parameter can no longer silently reuse an incompatible previous result. Numerical defaults
and scientific computation remain unchanged. The new regression tests exercise both parameter changes.
Extraction QC belongs here; scientific trajectory QC/modeling and ML belong in the two downstream repositories.
