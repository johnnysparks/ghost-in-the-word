# Ghost in the Word

An interactive Bible translation comparison project exploring wording differences,
embedding-based semantic distance, and the limits of automated faithfulness assessment.

The project plan is now being exercised by a dependency-free corpus pipeline and a
React/Vite atlas. See [the project plan](PLAN.md) for the research limits, evaluation
approach, architecture, and remaining milestones.

The first implementation milestone is a small, dependency-free corpus pipeline. Use the
source tree directly, download the pinned USFM sources, and build an alignment report for
two editions:

```sh
python3 scripts/download_sources.py --edition webp --edition bsb
PYTHONPATH=src python3 scripts/build_alignment.py \
  data/raw/webp data/raw/bsb \
  --left-id webp --right-id bsb
```

The checked-in `mappings/webp-bsb-reviewed.json` applies the known WEB/BSB verse
bridges and edition omissions to the pinned snapshots. It contains only exceptions;
unmentioned shared references still use exact alignment:

```sh
PYTHONPATH=src python3 scripts/build_alignment.py \
  data/raw/webp data/raw/bsb \
  --left-id webp --right-id bsb \
  --mapping mappings/webp-bsb-reviewed.json \
  --output data/derived/webp-bsb-reviewed-alignment.json \
  --mapping-report data/derived/webp-bsb-mapping-review.json
```

For a versification exception or a reviewed verse bridge, pass a JSON mapping file.
Each mapping consumes one or more references on either side; unmentioned shared
references still align by exact key, while one-sided segments remain explicitly
missing. A mapping marked `unresolved` is retained for review and receives no semantic
score:

```json
[
  {
    "left": ["JHN 3:16", "JHN 3:17"],
    "right": ["JHN 3:16"],
    "method": "reviewed-verse-bridge",
    "review": {
      "reviewer": "source-reviewer-1",
      "reviewType": "snapshot-comparison",
      "evidence": "Reference checked against the edition notes."
    }
  }
]
```

When `--mapping` is supplied, `build_alignment.py` validates the mapping before applying
it and requires each source directory to carry a matching `snapshot.json`. The validator
requires reviewer, review-type, and evidence fields by default; `--allow-unreviewed` is
available only for exploratory mappings. Use `--mapping-report` to retain the content
hashes and review summary. The report does not prove reviewer independence, so that
remains an external review responsibility:

```sh
PYTHONPATH=src python3 scripts/validate_mapping.py \
  data/raw/webp data/raw/bsb mappings/webp-bsb-reviewed.json \
  --left-id webp --right-id bsb \
  --output data/derived/webp-bsb-mapping-review.json
```

Raw downloads and generated reports are ignored by Git. The manifest in `sources.json`
records the edition URLs and licenses; verify snapshots and checksums before publishing
derived data.

Record and verify content hashes for downloaded source directories. The recording command
also writes the tracked aggregate manifest at `source_snapshots.json`:

```sh
PYTHONPATH=src python3 scripts/validate_sources.py
PYTHONPATH=src python3 scripts/record_snapshots.py
PYTHONPATH=src python3 scripts/verify_snapshots.py
```

Future downloads write the same `snapshot.json` inventory automatically, including the
archive hash when the source was obtained by `download_sources.py`.

The manifest also includes the public-domain Spanish Reina Valera 1909 edition. Download
it with `--edition rv1909` and build a John pilot alignment with the same parser. The
checked-in `WEB ↔ RV1909 · E5 small` browser fixture is a real cross-language embedding
run, not a lexical comparison. Cross-language embedding artifacts carry both edition
language codes. The embedding builder suppresses same-language lexical fields when
those codes differ, and the web client hides token-diff highlighting and the wording
scatterplot for that comparison:

```sh
python3 scripts/download_sources.py --edition rv1909
PYTHONPATH=src python3 scripts/build_alignment.py \
  data/raw/webp data/raw/rv1909 \
  --left-id webp --right-id rv1909 \
  --output data/derived/webp-rv1909-alignment.json
PYTHONPATH=src python3 scripts/build_embedding_comparison.py \
  data/derived/webp-rv1909-alignment.json --book JHN \
  --left-id webp --right-id rv1909 --left-language en --right-language es \
  --manifest sources.json \
  --model intfloat/multilingual-e5-small \
  --output data/derived/john-webp-rv1909-e5-small.json
```

The cross-language run is still a model-estimated representational distance; it is not
evidence that either edition is more faithful to a source text.
The lexical builder refuses cross-language input rather than producing a misleading
English token baseline.

The browser also includes a source-text pilot pairing WEB with the CNTR Statistical
Restoration Greek New Testament. The source manifest records its CC BY 4.0 license and
required attribution. Source-role metadata is shown in the reader and provenance panel;
the source comparison remains an exploratory reference point, not an automatic
faithfulness grade.

Build that source pilot with the same manifest-resolved provenance:

```sh
PYTHONPATH=src python3 scripts/build_alignment.py \
  data/raw/webp data/raw/srgrc \
  --left-id webp --right-id srgrc \
  --output data/derived/webp-srgrc-alignment.json
PYTHONPATH=src python3 scripts/build_embedding_comparison.py \
  data/derived/webp-srgrc-alignment.json --book JHN \
  --left-id webp --right-id srgrc --left-language en --right-language grc \
  --left-role translation --right-role source --manifest sources.json \
  --model intfloat/multilingual-e5-small \
  --output data/derived/john-webp-srgrc-e5-small.json
```

Embedding experiments are an optional offline step. Install the extra in an isolated
environment, then run the model-specific builder. The output records the model ID,
immutable revision, dimensions, input hash, prefix, context strategy, input count,
tokenizer truncation count when available, and maximum sequence length alongside each
score:

```sh
python3 -m pip install -e '.[embeddings]'
PYTHONPATH=src python3 scripts/build_embedding_comparison.py \
  data/derived/webp-bsb.json --book JHN \
  --left-id webp --right-id bsb \
  --manifest sources.json \
  --model intfloat/multilingual-e5-small \
  --cache-dir .embedding-cache \
  --context-strategy verse-only \
  --output data/derived/john-e5-small.json
```

The optional cache stores vectors outside Git. Its key includes the exact ordered
input-text hash, model ID and immutable model revision, prefix, context strategy, and
preprocessing version. A changed input, model revision, or recipe creates a new entry; interrupted
writes cannot replace a valid entry. Pass `--model-revision` with a pinned model commit
when using a mutable local path, and increment `--preprocessing-version` whenever the
text preparation recipe changes.

Before scaling a model run, profile tokenizer lengths, truncation risk, throughput,
peak RSS, and raw-vector capacity. The checked-in E5-small John profile uses 878 matched
verses and projects the measured rate to the full 31,103-unit atlas:

```sh
PYTHONPATH=src python3 scripts/profile_embeddings.py \
  web/public/data/john-webp-bsb.json --book JHN \
  --model intfloat/multilingual-e5-small --batch-size 32 \
  --target-units 31103 --edition-count 3 \
  --output benchmarks/reports/e5-small-john-profile.json
```

This report is a capacity measurement, not a quality result; it records zero pilot
inputs beyond the model sequence limit and keeps provider cost assumptions out of the
measurement.

For a named panel experiment, provide one vector per edition and passage in a
`passages[].vectors` object, then build an offline latent-reference artifact. Exclude
the two editions under comparison; the estimator reports the normalized weighted
centroid, the closest actual panel rendering (medoid), panel dispersion, and each
included edition's distance to the reference. Related editions can share a family cap
so revisions do not dominate the panel; pairwise panel distances are retained to make
distinct interpretive clusters inspectable. These distances are panel-relative research
measurements, not faithfulness grades:

```sh
PYTHONPATH=src python3 scripts/build_reference_panel.py \
  data/derived/reference-vectors.json \
  --exclude webp --exclude bsb \
  --family asv=older --family nwt=modern \
  --output data/derived/reference-estimates.json
```

The synthetic challenge set and reviewer instructions live in `benchmarks/`. It is an
evaluation scaffold, not a substitute for independent human judgments on Scripture. The
lexical baseline is expected to perform poorly on the challenge because a meaning change
can preserve most of the same words; that failure is part of the evidence for evaluating
an embedding model separately:

```sh
PYTHONPATH=src python3 scripts/evaluate_challenge.py benchmarks/challenge.json
```

The separate held-out synthetic set is never mixed into the original challenge report.
It adds genre slices and a changed-versus-preserved distance margin for reproducible
model comparison:

```sh
PYTHONPATH=src python3 scripts/evaluate_challenge.py \
  benchmarks/heldout_synthetic.json --metric embedding \
  --model intfloat/multilingual-e5-small \
  --cache-dir .embedding-cache \
  --output benchmarks/reports/e5-small-heldout.json
```

The recorded held-out runs are `e5-small-heldout.json` (4/8) and
`bge-m3-heldout.json` (7/8). BGE-M3 clears the provisional synthetic ranking gate in
this small slice; these are still zero-shot synthetic checks and do not replace
held-out natural translation judgments by independent reviewers.

Reports include seeded case-level bootstrap intervals for the pass rate and mean
margin. Embedding reports also include a paired comparison against the character
n-gram lexical baseline: pass-rate delta, mean-margin delta, and seeded uncertainty
intervals over the same cases. To add the same uncertainty summary to an older saved report:

```sh
PYTHONPATH=src python3 scripts/add_report_bootstrap.py \
  benchmarks/reports/bge-m3-heldout.json
```

The original challenge reports for E5-small and BGE-M3 are kept in
`benchmarks/reports/`; both are below the provisional gate and therefore remain
research evidence rather than product labels.

Possible Bible exposure in pretrained models is tracked in
`benchmarks/model_exposure.json`. The current status is explicitly `unknown`: the
holdout packet protects against reusing this repository's development labels, but it
cannot establish that a pretrained model never saw Bible text. Record an immutable model
revision and the model maintainer's dated training-data disclosure before making a
scientific claim from a future run.

Generate a blinded review packet from a scored comparison. The selector mixes the
highest-scoring matched passages with a seeded random sample, then removes scores and
ranks from the reviewer-facing payload:

```sh
PYTHONPATH=src python3 scripts/select_review_sample.py \
  web/public/data/john-webp-bsb.json \
  --metric lexicalDistance --count 60 --seed 20261014 \
  --output benchmarks/review-packet.json \
  --key-output benchmarks/review-key.json
```

Reviewers should return one JSON document each with `reviewerId` and an `items` array
using the fields in `benchmarks/REVIEW_RUBRIC.md`. Aggregate those documents with:

```sh
PYTHONPATH=src python3 scripts/evaluate_reviews.py \
  benchmarks/reviews/reviewer-1.json benchmarks/reviews/reviewer-2.json \
  --packet benchmarks/review-packet.json \
  --key benchmarks/review-key.json \
  --output benchmarks/reports/natural-review.json
```

With a packet, the report also includes deterministic 95% bootstrap intervals for
majority-useful rates. Resampling is clustered by book so several verses from one book
do not masquerade as independent evidence; use `--bootstrap-samples 0` to omit the
intervals or `--bootstrap-seed` to declare a different seed.

The selection report also includes `rankingAgreement`: an AUC and rank-biserial effect
for the reviewed items, asking whether passages reviewers marked useful tended to appear
earlier in the model ranking than passages marked not useful. It is explicitly scoped to
the reviewed selection, includes the same book-clustered interval, and is not a
faithfulness score or a claim about unreviewed passages.

Keep the key private: it lets the evaluator separate the highest-ranked 30 items from
the seeded random sample without exposing that selection to reviewers. The report
retains per-item votes, disagreement, and uncertain judgments, and reports usefulness
and agreement by selection bucket. Supplying `--packet` checks every response against
the exact blinded item IDs, rejects score/rank leakage, reports review coverage, and
marks the natural-evaluation gate ineligible until at least two reviewers have judged
every one of the 30 top-ranked items. It does not convert review usefulness into a translation-faithfulness
grade. Validate a packet independently with:

```sh
PYTHONPATH=src python3 scripts/validate_review_packet.py \
  benchmarks/natural-review-packet.example.json
```

`benchmarks/natural-review-packet.example.json` is a checked-in, score-blinded 200-item
candidate generated from the full WEB/BSB corpus. It contains 30 globally highest-ranked
leads plus 170 seeded background passages balanced across narrative, poetry, law, and
argument, with short and long renderings mixed within each genre. Recreate it (and keep
the private key outside the repository) with:

```sh
PYTHONPATH=src python3 scripts/build_natural_benchmark.py \
  data/derived/webp-bsb-full.json \
  --count 200 --seed 20261014 --metric lexicalDistance \
  --output benchmarks/natural-review-packet.example.json \
  --key-output /tmp/natural-review-key.json
```

Keep a final evaluation independent from development selections by scoping a new
packet to a declared set of held-out books, or by excluding books used during metric
development. The scope is recorded in both the blinded packet and its private key; use
enough books to preserve the genre strata when requesting the 200-item layout:

```sh
PYTHONPATH=src python3 scripts/build_natural_benchmark.py \
  data/derived/webp-bsb-full.json --count 200 --seed 20261015 \
  --exclude-book JHN --exclude-book GEN \
  --output benchmarks/natural-review-heldout.example.json \
  --key-output /tmp/natural-heldout-key.json
```

The checked-in `benchmarks/natural-review-heldout.example.json` is this score-blinded
candidate. It excludes Genesis and John from the selection scope so a reviewer can use
it as a separate handoff from the development packet; it remains a candidate until
independent labels are collected.

The private selection key is deliberately kept outside the repository; independent
reviewers and the evaluator must receive it through separate channels. The checked-in
packet is a review candidate, not evidence that any item is useful until independent
labels are collected.

Source-conditioned judgments use a separate validated schema so the source edition,
reviewer/model origin, evidence, uncertainty, and disagreement remain attached to each
record. The checked-in file is a fixture only; it is not a judgment about Scripture:

```sh
PYTHONPATH=src python3 scripts/validate_assessments.py \
  benchmarks/source_assessments.example.json
```

Attach validated records to a source comparison only when the source edition is one
of the comparison sides and is marked with `role: source`:

```sh
PYTHONPATH=src python3 scripts/attach_assessments.py \
  data/derived/john-webp-srgrc-e5-small.json \
  benchmarks/source_assessments_srgrc.example.json \
  --output data/derived/john-webp-srgrc-assessed.json
```

The checked-in source-specific document is a fixture attachment, not a human judgment;
replace it with independently reviewed records for research use. Attached evidence
remains separate from embedding and wording scores.

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

Verse scores remain the primary view. To inspect explicitly joined two-verse windows
as a separate artifact, use a non-overlapping default stride or opt into a sliding
stride for exploratory work:

```sh
PYTHONPATH=src python3 scripts/build_windows.py \
  web/public/data/john-webp-bsb.json \
  --window-size 2 --output data/derived/john-webp-bsb-windows.json
```

Windows containing missing or unresolved verses remain visible with null scores; the
window artifact does not replace verse-level scores.

The first interactive slice is in `web/`. It serves a committed John pilot fixture,
loads the full WEB↔BSB atlas one book at a time, and keeps the selected comparison pair,
unit granularity, passage, chapter, search, brush range, and reader state in the URL. The
WEB↔BSB pair offers a verse view and a separate non-overlapping two-verse passage view;
the latter is built from joined text and has its own metric and coverage summaries. Drag
across the main chart to focus a range; the reader, ranked list, and scatterplot follow
that focus.
The full-corpus view also shows book and chapter score summaries with coverage and status
counts before loading a book's verse points.
Footnotes are removed from analysis text but retained as expandable notes in the reader.
The current focus can be downloaded as JSON or CSV, and the provenance panel exposes
the metric, alignment, language pair, and embedding run metadata.
For the John pilot, the reader also loads a separate WEB/BSB/ASV distance matrix for
the selected verse; the matrix is a panel comparison aid and does not assign a preferred
translation.
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

## Deployment

The repository includes a GitHub Actions workflow at `.github/workflows/pages.yml`.
Pull requests run the Python checks and production web build. A successful push to
`main` builds `web/dist` and deploys it to GitHub Pages; the workflow does not download
raw corpora or run embedding models.

For the first deployment, open the repository's **Settings → Pages** and set **Source**
to **GitHub Actions**. The published project site will then be available at the
repository's GitHub Pages URL. The workflow exposes that URL in the deployment job's
environment output.
