# legacy/ — Preserved, Not Deleted

This directory is the destination for files classified as **LEGACY** or
**DUPLICATE** during the framework restructuring. Per the project's safety
rules, nothing is ever deleted — superseded files are moved here (with their
original sub-path preserved) and recorded in `../MIGRATION_LOG.md`.

**Status at the facade stage:** no files have been physically moved here yet.
Physical relocation of duplicates is scheduled for the post-API/Docker cleanup
phase, where it can be verified. Until then, every candidate is *classified in
place* in `MIGRATION_LOG.md`.

Restoring a file: copy it back from here (or from `../migration_backup/`) to
its original path listed in `MIGRATION_LOG.md`. No git history is rewritten.
