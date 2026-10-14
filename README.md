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

For a versification exception or a reviewed verse bridge, pass a JSON mapping file.
Each mapping consumes one or more references on either side; omitted segments remain
explicitly missing. A mapping marked `unresolved` is retained for review and receives
no semantic score:

```json
[
  {
    "left": ["JHN 3:16", "JHN 3:17"],
    "right": ["JHN 3:16"],
    "method": "reviewed-verse-bridge"
  }
]
```

```sh
PYTHONPATH=src python3 scripts/build_alignment.py \
  data/raw/webp data/raw/bsb \
  --left-id webp --right-id bsb \
  --mapping mappings/webp-bsb.json
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

Recorded E5-small and BGE-M3 reports are kept in `benchmarks/reports/`; both are below
the provisional gate and therefore remain research evidence rather than product labels.

Generate a blinded review packet from a scored comparison. The selector mixes the
highest-scoring matched passages with a seeded random sample, then removes scores and
ranks from the reviewer-facing payload:

```sh
PYTHONPATH=src python3 scripts/select_review_sample.py \
  web/public/data/john-webp-bsb.json \
  --metric lexicalDistance --count 30 --seed 20261014 \
  --output benchmarks/review-packet.json
```

Reviewers should return one JSON document each with `reviewerId` and an `items` array
using the fields in `benchmarks/REVIEW_RUBRIC.md`. Aggregate those documents with:

```sh
PYTHONPATH=src python3 scripts/evaluate_reviews.py \
  benchmarks/reviews/reviewer-1.json benchmarks/reviews/reviewer-2.json \
  --output benchmarks/reports/natural-review.json
```

The report retains per-item votes, disagreement, and uncertain judgments. It does not
convert review usefulness into a translation-faithfulness grade.

Book/chapter aggregates can be generated from any comparison artifact for a future
whole-Bible overview. Missing units stay in coverage counts and are excluded from score
statistics:

```sh
PYTHONPATH=src python3 scripts/build_summary.py \
  data/derived/webp-bsb-full.json \
  --output data/derived/webp-bsb-summary.json
```

The default atlas uses the partitioned WEB↔BSB corpus. Rebuild its one-book-at-a-time
payloads from a full comparison artifact with:

```sh
PYTHONPATH=src python3 scripts/partition_comparison.py \
  data/derived/webp-bsb-full.json \
  --output-dir web/public/data/webp-bsb
```

The first interactive slice is in `web/`. It serves a committed John pilot fixture and
keeps the selected comparison pair, verse, chapter, search, and reader state in the URL.
The pair menu includes WEB↔BSB and WEB↔ASV lexical baselines, plus the recorded
`multilingual-e5-small` WEB↔BSB run:

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
