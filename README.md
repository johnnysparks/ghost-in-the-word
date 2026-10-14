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

Embedding experiments are an optional offline step. Install the extra in an isolated
environment, then run the model-specific builder. The output records the model ID,
dimensions, input hash, prefix, and maximum sequence length alongside each score:

```sh
python3 -m pip install -e '.[embeddings]'
PYTHONPATH=src python3 scripts/build_embedding_comparison.py \
  data/derived/webp-bsb.json --book JHN \
  --left-id webp --right-id bsb \
  --model intfloat/multilingual-e5-small \
  --output data/derived/john-e5-small.json
```

The synthetic challenge set and reviewer instructions live in `benchmarks/`. It is an
evaluation scaffold, not a substitute for independent human judgments on Scripture. The
lexical baseline is expected to perform poorly on the challenge because a meaning change
can preserve most of the same words; that failure is part of the evidence for evaluating
an embedding model separately:

```sh
PYTHONPATH=src python3 scripts/evaluate_challenge.py benchmarks/challenge.json
```

The first interactive slice is in `web/`. It serves a committed John pilot fixture and
keeps the selected verse, chapter, search, and reader state in the URL:

```sh
cd web
npm install
npm run dev
```

From the repository root, rebuild the committed pilot fixture after refreshing corpus data:

```sh
PYTHONPATH=src python3 scripts/build_comparison.py \
  data/derived/webp-bsb.json --book JHN \
  --left-id webp --right-id bsb \
  --left-name "World English Bible Protestant Edition" \
  --right-name "Berean Standard Bible" \
  --output web/public/data/john-webp-bsb.json
```
