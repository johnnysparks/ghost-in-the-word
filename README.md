# Ghost in the Word

An interactive Bible translation comparison project exploring wording differences,
embedding-based semantic distance, and the limits of automated faithfulness assessment.

The project is currently in planning. See [the project plan](PLAN.md) for the proposed
experience, corpus sources, evaluation approach, architecture, and delivery milestones.

The first implementation milestone is a small, dependency-free corpus pipeline. Use the
source tree directly, download the pinned USFM sources, and build an alignment report for
two editions:

```sh
python3 scripts/download_sources.py --edition webp --edition bsb
PYTHONPATH=src python3 scripts/build_alignment.py \
  data/raw/webp data/raw/bsb \
  --left-id webp --right-id bsb
```

Raw downloads and generated reports are ignored by Git. The manifest in `sources.json`
records the edition URLs and licenses; verify snapshots and checksums before publishing
derived data.
