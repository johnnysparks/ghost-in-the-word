#!/usr/bin/env python3
"""Render a score-blinded review packet as a self-contained HTML form.

The generated page contains only the reviewer-facing packet. It never reads or
embeds the private selection key, and it writes the same response shape accepted
by ``scripts/evaluate_reviews.py``.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Mapping

from ghost_in_word.review import validate_review_packet


def _text(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def _option_values(name: str, values: tuple[str, ...]) -> str:
    options = [f'<option value="">Select {name.lower()}</option>']
    options.extend(f'<option value="{_text(value)}">{_text(value.title())}</option>' for value in values)
    return "".join(options)


def render_review_form(packet: Mapping[str, object], *, reviewer_id: str = "", title: str = "Blind translation review") -> str:
    """Return a self-contained HTML reviewer form for a validated packet."""

    summary = validate_review_packet(packet)
    source = packet["source"]
    assert isinstance(source, Mapping)
    left = source["leftEdition"]
    right = source["rightEdition"]
    assert isinstance(left, Mapping) and isinstance(right, Mapping)
    metric = source.get("metric")
    metric = metric if isinstance(metric, Mapping) else {}
    # Keep JSON valid in a raw-text script element while preventing packet text
    # from terminating the element if it contains markup-like characters.
    packet_json = (
        json.dumps(packet, ensure_ascii=False, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )

    cards: list[str] = []
    items = packet["items"]
    assert isinstance(items, list)
    for index, item in enumerate(items, start=1):
        assert isinstance(item, Mapping)
        item_id = _text(item["id"])
        cards.append(
            f'''<article class="review-card" data-item-id="{item_id}">
  <div class="card-heading">
    <span class="item-number">{index} / {summary["itemCount"]}</span>
    <h2>{_text(item["reference"])}</h2>
    <code>{item_id}</code>
  </div>
  <div class="renderings">
    <section><h3>{_text(left.get("name", left.get("id")))}</h3><p>{_text(item["leftText"])}</p></section>
    <section><h3>{_text(right.get("name", right.get("id")))}</h3><p>{_text(item["rightText"])}</p></section>
  </div>
  <div class="judgment-grid">
    <label>Useful for close reading
      <select data-field="useful" required>
        {_option_values("usefulness", ("yes", "no", "uncertain"))}
      </select>
    </label>
    <label>Difference type
      <select data-field="differenceType" required>
        {_option_values("difference type", ("wording", "likely meaning", "source-text issue", "alignment issue", "unclear"))}
      </select>
    </label>
    <label>Confidence
      <select data-field="confidence" required>
        {_option_values("confidence", ("low", "medium", "high"))}
      </select>
    </label>
    <label class="evidence-field">Evidence
      <textarea data-field="evidence" rows="2" placeholder="Cite the displayed words or source reference." required></textarea>
    </label>
  </div>
</article>'''
        )

    safe_title = _text(title)
    safe_reviewer = _text(reviewer_id)
    metric_label = _text(metric.get("label", metric.get("id", "comparison")))
    metric_description = _text(metric.get("description", ""))
    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title}</title>
  <style>
    :root {{ color-scheme: light; font-family: system-ui, -apple-system, sans-serif; color: #1d2433; background: #f5f6f8; }}
    body {{ margin: 0; }}
    header {{ position: sticky; top: 0; z-index: 2; padding: 1rem clamp(1rem, 4vw, 3rem); background: #18253a; color: #fff; box-shadow: 0 2px 10px #0003; }}
    header h1 {{ margin: 0 0 .35rem; font-size: 1.35rem; }}
    header p {{ max-width: 75rem; margin: .3rem 0; color: #dbe7fa; }}
    main {{ max-width: 75rem; margin: 0 auto; padding: 1rem clamp(1rem, 4vw, 3rem) 4rem; }}
    .instructions, .review-card {{ background: #fff; border: 1px solid #d9dee8; border-radius: .7rem; box-shadow: 0 1px 3px #17233b12; }}
    .instructions {{ padding: 1rem 1.2rem; margin-bottom: 1rem; }}
    .instructions p {{ margin: .45rem 0; }}
    .toolbar {{ display: flex; flex-wrap: wrap; align-items: end; gap: .75rem 1rem; margin-top: 1rem; }}
    .attestation {{ display: flex; align-items: center; gap: .45rem; font-weight: 650; }}
    .attestation input {{ min-width: 0; width: 1.1rem; height: 1.1rem; }}
    label {{ display: grid; gap: .3rem; font-weight: 650; }}
    input, select, textarea, button {{ font: inherit; }}
    input, select, textarea {{ border: 1px solid #aeb8c8; border-radius: .4rem; padding: .5rem; color: inherit; background: #fff; }}
    input:focus, select:focus, textarea:focus, button:focus {{ outline: 3px solid #85b7ff; outline-offset: 2px; }}
    input {{ min-width: 14rem; }}
    button {{ border: 0; border-radius: .45rem; padding: .62rem .9rem; background: #2769d8; color: #fff; font-weight: 700; cursor: pointer; }}
    button.secondary {{ background: #596579; }}
    button:disabled {{ opacity: .55; cursor: wait; }}
    #progress {{ font-weight: 700; }}
    #status {{ min-height: 1.4em; margin: .65rem 0 0; }}
    .review-card {{ padding: 1rem 1.2rem; margin: 1rem 0; scroll-margin-top: 7rem; }}
    .review-card.incomplete {{ border-color: #c67b1d; }}
    .card-heading {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: .45rem .75rem; }}
    .card-heading h2 {{ margin: 0; font-size: 1.15rem; }}
    .card-heading code {{ color: #5b6474; }}
    .item-number {{ color: #596579; font-size: .9rem; }}
    .renderings {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; margin: 1rem 0; }}
    .renderings section {{ border-left: 3px solid #b8c8e6; padding-left: .75rem; }}
    .renderings h3 {{ margin: 0 0 .4rem; font-size: .95rem; }}
    .renderings p {{ margin: 0; line-height: 1.55; white-space: pre-wrap; }}
    .judgment-grid {{ display: grid; grid-template-columns: repeat(3, minmax(10rem, 1fr)); gap: .75rem; }}
    .evidence-field {{ grid-column: 1 / -1; }}
    textarea {{ resize: vertical; min-height: 3.2rem; }}
    @media (max-width: 44rem) {{ .renderings, .judgment-grid {{ grid-template-columns: 1fr; }} .evidence-field {{ grid-column: auto; }} input {{ min-width: 0; width: 100%; }} }}
  </style>
</head>
<body>
<header>
  <h1>{safe_title}</h1>
  <p>{_text(left.get("name", left.get("id")))} vs. {_text(right.get("name", right.get("id")))} · {metric_label}</p>
  <p id="progress" aria-live="polite">0 of {summary["itemCount"]} completed</p>
</header>
<main>
  <section class="instructions" aria-labelledby="instructions-heading">
    <h2 id="instructions-heading">Instructions</h2>
    <p>Review each passage independently. Decide whether the difference deserves close reading; this is not a verdict that either rendering is wrong.</p>
    <p>Preserve ambiguity and use <em>uncertain</em> when a useful/not-useful judgment is not possible. Cite the displayed words or a source reference in the evidence field.</p>
    <p><strong>Comparison method:</strong> {metric_description}</p>
    <div class="toolbar">
      <label>Reviewer ID
        <input id="reviewer-id" value="{safe_reviewer}" autocomplete="off" required>
      </label>
      <label class="attestation"><input id="independence" type="checkbox"> I reviewed independently</label>
      <button type="button" id="download">Download response JSON</button>
      <button type="button" id="reset" class="secondary">Clear form</button>
    </div>
    <p id="status" role="status" aria-live="polite"></p>
  </section>
  <form id="review-form" novalidate>
    {''.join(cards)}
  </form>
</main>
<script type="application/json" id="packet-data">{packet_json}</script>
<script>
(() => {{
  const packet = JSON.parse(document.getElementById('packet-data').textContent);
  const cards = [...document.querySelectorAll('[data-item-id]')];
  const progress = document.getElementById('progress');
  const status = document.getElementById('status');
  const reviewer = document.getElementById('reviewer-id');
  const independence = document.getElementById('independence');
  const fields = ['useful', 'differenceType', 'confidence', 'evidence'];

  function cardComplete(card) {{
    return fields.every((name) => card.querySelector(`[data-field="${{name}}"]`).value.trim());
  }}

  function updateProgress() {{
    const complete = cards.filter(cardComplete).length;
    progress.textContent = `${{complete}} of ${{cards.length}} completed`;
    cards.forEach((card) => card.classList.toggle('incomplete', !cardComplete(card)));
  }}

  function collect() {{
    return cards.map((card) => Object.fromEntries([
      ['id', card.dataset.itemId],
      ...fields.map((name) => [name, card.querySelector(`[data-field="${{name}}"]`).value.trim()]),
    ]));
  }}

  function download() {{
    status.textContent = '';
    const reviewerId = reviewer.value.trim();
    const incomplete = cards.filter((card) => !cardComplete(card));
    if (!reviewerId) {{ reviewer.focus(); status.textContent = 'Enter a reviewer ID before downloading.'; return; }}
    if (!independence.checked) {{ independence.focus(); status.textContent = 'Confirm that you reviewed the packet independently.'; return; }}
    if (incomplete.length) {{ incomplete[0].querySelector('[data-field="useful"]').focus(); status.textContent = `Complete all required judgments first (${{incomplete.length}} remaining).`; return; }}
    const response = {{ schemaVersion: 1, reviewerId, independence: 'declared', items: collect() }};
    const blob = new Blob([JSON.stringify(response, null, 2) + '\\n'], {{ type: 'application/json' }});
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${{reviewerId.replace(/[^a-z0-9_-]+/gi, '_')}}-review.json`;
    link.click();
    URL.revokeObjectURL(url);
    status.textContent = 'Response downloaded.';
  }}

  cards.flatMap((card) => [...card.querySelectorAll('select, textarea')]).forEach((field) => field.addEventListener('input', updateProgress));
  document.getElementById('download').addEventListener('click', download);
  document.getElementById('reset').addEventListener('click', () => {{
    if (!window.confirm('Clear every judgment in this form?')) return;
    document.getElementById('review-form').reset();
    status.textContent = 'Form cleared.';
    updateProgress();
  }});
  updateProgress();
}})();
</script>
</body>
</html>
'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path, help="Score-blinded packet JSON")
    parser.add_argument("--output", type=Path, required=True, help="HTML file to write")
    parser.add_argument("--reviewer-id", default="", help="Initial reviewer ID in the form")
    parser.add_argument("--title", default="Blind translation review")
    args = parser.parse_args()

    packet = json.loads(args.packet.read_text(encoding="utf-8"))
    validate_review_packet(packet)
    rendered = render_review_form(packet, reviewer_id=args.reviewer_id, title=args.title)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(json.dumps({"output": str(args.output), "itemCount": len(packet["items"]), "reviewerIdPrefilled": bool(args.reviewer_id)}, indent=2))


if __name__ == "__main__":
    main()
