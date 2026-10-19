# Bangladesh historical research benchmark

See the [training-02 selection audit](../docs/TRAINING_02_SELECTION_AUDIT.md)
and [prepared training-03 foundation benchmark](../docs/TRAINING_03.md).

For the separate calibration/recall improvement experiment, see
[Training-02 stages and interpretation](../docs/TRAINING_02.md).

Start with the [runbook and API contract](../docs/RESEARCH_BANGLADESH.md) and
[measured technical report](artifacts/technical_report.md).

Run from the repository root: `python -m ml.download`, `python -m ml.train`,
`python -m ml.report`. Use the pinned dependencies in `ml/requirements.txt`.
The finalized output directory refuses training overwrite; choose a separate
`--out ml/runs/reproduction` for exact reproduction.

This predicts source-qualified Bangladesh proxy labels for historical research.
It is not validated for Fiji or public warnings. Unknown labels are excluded,
and the source does not establish independently verified non-flood truth or a
redistribution license.
