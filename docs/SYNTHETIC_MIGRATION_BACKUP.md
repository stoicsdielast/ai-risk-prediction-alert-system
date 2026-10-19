# Pre-migration backup inventory

The existing `parvish-dev` development branch is the backup branch. The first
checkpoint commit contains safe source, tests, configuration templates and
documentation, including the existing application changes and the foundation
benchmark execution code. No synthetic migration cleanup may begin until this
commit is pushed and the remote SHA verified.

The Git snapshot excludes actual `backend/.env` and `frontend/.env`, virtual
environments, dependency trees, caches, generated datasets, binary models,
training runs and local pretrained checkpoints according to `.gitignore`.
Placeholder-only `.env.example` templates remain tracked. No private-key,
AWS-key, GitHub-token or Hugging Face-token patterns were found in the initial
candidate-source scan; the staged snapshot is checked separately before commit.

Explicit additional excluded files are `archive.zip`,
`docs/OVERNIGHT_TEAM_TASKS.docx`, `docs/TEAM_TASK_TICKETS.docx`, and
`docs/TEAM_TASK_TICKETS.pdf`. Corresponding Markdown documents are included.
Generated `ml/artifacts/clustering.png` and `ml/artifacts/performance.png` are
also excluded; their measured metadata and historical report remain tracked.
Exact file-level exclusion inventories and SHA256 manifests are stored in the
timestamped local backup outside the repository, documented in the migration
completion report. Secret values are never copied into the Git snapshot or
printed in the report.

Historical `ml/runs`, `ml/data` and active `ml/artifacts`, backend AI generated
data/models/artifacts, and the four excluded document/source archives are
preserved in the verified local archive before any obsolete runs are removed.
Virtual environments and downloaded public pretrained checkpoints are retained
in place for potential synthetic-data benchmarking and are not deleted.

Training-03 installation and smoke tests completed before the migration request
superseded the foreign-data benchmark. TabFM passed its CPU smoke test after a
GPU out-of-memory failure; TabICLv2 passed GPU smoke tests at 100 and 4096 context
rows. TabPFN-2.5 lacked authenticated checkpoint access. No full foundation-model
performance metrics were produced. These logs are preserved in the historical
archive, without claiming a completed benchmark.

Verified local archive:
`/home/mohanx13/UNI/cs314/flood-risk-backups/20261019T063327Z/historical-artifacts.tar.gz`.
All 547 archived file hashes matched their originals. Archive SHA256:
`5b66a3853a8c52e0d7d9fb061327ce61dc8129759e9c030b21c404a8fe6bf444`.
The same directory contains the full archive manifest and exact excluded-file
inventory. Environments and public checkpoint caches are retained separately.
