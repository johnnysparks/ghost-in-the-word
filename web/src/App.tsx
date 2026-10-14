import { useEffect, useMemo, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import type { ComparisonData, ComparisonManifest, ComparisonUnit } from "./types";

type PairConfig = {
  id: string;
  label: string;
  dataUrl?: string;
  manifestUrl?: string;
  leftSource: string;
  rightSource: string;
};

const PAIRS: PairConfig[] = [
  {
    id: "webp-bsb",
    label: "WEB ↔ BSB",
    manifestUrl: "/data/webp-bsb/manifest.json",
    leftSource: "https://ebible.org/find/details.php?id=engwebp",
    rightSource: "https://berean.bible/downloads.htm",
  },
  {
    id: "webp-asv",
    label: "WEB ↔ ASV 1901",
    dataUrl: "/data/john-webp-asv.json",
    leftSource: "https://ebible.org/find/details.php?id=engwebp",
    rightSource: "https://ebible.org/find/details.php?id=eng-asv",
  },
  {
    id: "webp-bsb-e5-small",
    label: "WEB ↔ BSB · E5 small",
    dataUrl: "/data/john-e5-small-webp-bsb.json",
    leftSource: "https://ebible.org/find/details.php?id=engwebp",
    rightSource: "https://berean.bible/downloads.htm",
  },
];

const bookNames: Record<string, string> = {
  GEN: "Genesis", EXO: "Exodus", LEV: "Leviticus", NUM: "Numbers", DEU: "Deuteronomy", JOS: "Joshua", JDG: "Judges", RUT: "Ruth", "1SA": "1 Samuel", "2SA": "2 Samuel", "1KI": "1 Kings", "2KI": "2 Kings", "1CH": "1 Chronicles", "2CH": "2 Chronicles", EZR: "Ezra", NEH: "Nehemiah", EST: "Esther", JOB: "Job", PSA: "Psalms", PRO: "Proverbs", ECC: "Ecclesiastes", SNG: "Song of Solomon", ISA: "Isaiah", JER: "Jeremiah", LAM: "Lamentations", EZK: "Ezekiel", DAN: "Daniel", HOS: "Hosea", JOL: "Joel", AMO: "Amos", OBA: "Obadiah", JON: "Jonah", MIC: "Micah", NAM: "Nahum", HAB: "Habakkuk", ZEP: "Zephaniah", HAG: "Haggai", ZEC: "Zechariah", MAL: "Malachi", MAT: "Matthew", MRK: "Mark", LUK: "Luke", JHN: "John", ACT: "Acts", ROM: "Romans", "1CO": "1 Corinthians", "2CO": "2 Corinthians", GAL: "Galatians", EPH: "Ephesians", PHP: "Philippians", COL: "Colossians", "1TH": "1 Thessalonians", "2TH": "2 Thessalonians", "1TI": "1 Timothy", "2TI": "2 Timothy", TIT: "Titus", PHM: "Philemon", HEB: "Hebrews", JAS: "James", "1PE": "1 Peter", "2PE": "2 Peter", "1JN": "1 John", "2JN": "2 John", "3JN": "3 John", JUD: "Jude", REV: "Revelation",
};

function displayBook(book: string) {
  return bookNames[book] ?? book;
}

function parseInitialRef() {
  return new URLSearchParams(window.location.search).get("ref");
}

function parseInitialPair() {
  return new URLSearchParams(window.location.search).get("pair") ?? PAIRS[0].id;
}

function parseInitialBook() {
  return new URLSearchParams(window.location.search).get("book") ?? "JHN";
}

function formatScore(score: number | null) {
  return score === null ? "—" : score.toFixed(3);
}

function distanceFor(unit: ComparisonUnit, field: string) {
  const value = unit[field as keyof ComparisonUnit];
  return typeof value === "number" ? value : null;
}

function normalizedWords(text: string) {
  return text.toLocaleLowerCase().match(/[\p{L}\p{N}’'-]+/gu) ?? [];
}

function MarkedText({ text, other }: { text: string | null; other: string | null }) {
  if (!text) return <span className="missing-copy">No aligned text</span>;
  const otherWords = new Set(normalizedWords(other ?? ""));
  return (
    <>
      {text.split(/(\s+)/).map((part, index) => {
        const word = part.match(/[\p{L}\p{N}’'-]+/u)?.[0]?.toLocaleLowerCase();
        return word && !otherWords.has(word) ? (
          <mark className="word-change" key={`${part}-${index}`}>{part}</mark>
        ) : (
          <span key={`${part}-${index}`}>{part}</span>
        );
      })}
    </>
  );
}

function TranslationNotes({ notes }: { notes?: string[] }) {
  if (!notes?.length) return null;
  return (
    <details className="translation-notes">
      <summary>Notes ({notes.length})</summary>
      <ul>{notes.map((note, index) => <li key={`${index}-${note}`}>{note}</li>)}</ul>
    </details>
  );
}

type UnitRange = { start: number; end: number };

function parseInitialRange(): UnitRange | null {
  const value = new URLSearchParams(window.location.search).get("range");
  if (!value) return null;
  const [start, end] = value.split("-").map(Number);
  if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end < start) return null;
  return { start, end };
}

function updateUrl(pairId: string, book: string, unit: ComparisonUnit | undefined, chapter: string, search: string, range: UnitRange | null = null) {
  const params = new URLSearchParams(window.location.search);
  params.set("pair", pairId);
  params.set("book", book);
  if (unit) params.set("ref", unit.id);
  if (chapter === "all") params.delete("chapter");
  else params.set("chapter", chapter);
  if (search) params.set("q", search);
  else params.delete("q");
  if (range) params.set("range", `${range.start}-${range.end}`);
  else params.delete("range");
  window.history.replaceState({}, "", `${window.location.pathname}?${params.toString()}`);
}

function DivergenceChart({
  units,
  selectedId,
  onSelect,
  maxScore,
  distanceField,
  distanceLabel,
  bookName,
  onBrush,
  onClearBrush,
  rangeActive,
}: {
  units: ComparisonUnit[];
  selectedId: string | undefined;
  onSelect: (unit: ComparisonUnit) => void;
  maxScore: number;
  distanceField: string;
  distanceLabel: string;
  bookName: string;
  onBrush: (start: number, end: number) => void;
  onClearBrush: () => void;
  rangeActive: boolean;
}) {
  const [brushStart, setBrushStart] = useState<number | null>(null);
  const [brushEnd, setBrushEnd] = useState<number | null>(null);
  const width = 1000;
  const height = 292;
  const padding = { left: 56, right: 22, top: 22, bottom: 42 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const valid = units.filter((unit) => distanceFor(unit, distanceField) !== null);
  const visibleIndex = new Map(units.map((unit, index) => [unit.id, index]));
  const xFor = (unit: ComparisonUnit) => padding.left + ((visibleIndex.get(unit.id) ?? 0) / Math.max(1, units.length - 1)) * plotWidth;
  const yFor = (unit: ComparisonUnit) => padding.top + (1 - (distanceFor(unit, distanceField) ?? 0) / maxScore) * plotHeight;
  const gridValues = [0, maxScore / 2, maxScore];
  const indexForPoint = (event: ReactPointerEvent<SVGSVGElement>) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    const svgX = ((event.clientX - bounds.left) / bounds.width) * width;
    const fraction = (svgX - padding.left) / plotWidth;
    return Math.max(0, Math.min(units.length - 1, Math.round(fraction * Math.max(1, units.length - 1))));
  };
  const brushLow = brushStart !== null && brushEnd !== null ? Math.min(brushStart, brushEnd) : null;
  const brushHigh = brushStart !== null && brushEnd !== null ? Math.max(brushStart, brushEnd) : null;
  const brushX = brushLow === null ? 0 : padding.left + (brushLow / Math.max(1, units.length - 1)) * plotWidth;
  const brushWidth = brushHigh === null || brushLow === null ? 0 : ((brushHigh - brushLow) / Math.max(1, units.length - 1)) * plotWidth;
  const finishBrush = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (brushStart === null || brushEnd === null) return;
    event.currentTarget.releasePointerCapture?.(event.pointerId);
    const start = Math.min(brushStart, brushEnd);
    const end = Math.max(brushStart, brushEnd);
    setBrushStart(null);
    setBrushEnd(null);
    if (end > start) onBrush(start, end);
  };

  return (
    <div className="chart-shell">
      <svg
        className="chart"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-labelledby="divergence-title divergence-description"
        onPointerDown={(event) => {
          if ((event.target as Element).tagName.toLowerCase() === "circle" || units.length < 2) return;
          event.currentTarget.setPointerCapture(event.pointerId);
          const index = indexForPoint(event);
          setBrushStart(index);
          setBrushEnd(index);
        }}
        onPointerMove={(event) => {
          if (brushStart !== null) setBrushEnd(indexForPoint(event));
        }}
        onPointerUp={finishBrush}
        onPointerCancel={() => { setBrushStart(null); setBrushEnd(null); }}
      >
        <title id="divergence-title">Distance across the selected book</title>
        <desc id="divergence-description">Each point is a matched verse. Higher points have more divergence according to the selected comparison metric.</desc>
        {gridValues.map((value) => {
          const y = padding.top + (1 - value / maxScore) * plotHeight;
          return (
            <g key={value}>
              <line className="grid-line" x1={padding.left} x2={width - padding.right} y1={y} y2={y} />
              <text className="axis-label" x={padding.left - 10} y={y + 4} textAnchor="end">{value.toFixed(2)}</text>
            </g>
          );
        })}
        <line className="axis-line" x1={padding.left} x2={padding.left} y1={padding.top} y2={height - padding.bottom} />
        <line className="axis-line" x1={padding.left} x2={width - padding.right} y1={height - padding.bottom} y2={height - padding.bottom} />
        <rect className="brush-surface" x={padding.left} y={padding.top} width={plotWidth} height={plotHeight} />
        {brushLow !== null && brushHigh !== null && <rect className="brush-selection" x={brushX} y={padding.top} width={Math.max(2, brushWidth)} height={plotHeight} />}
        <text className="axis-title" x={padding.left} y={height - 10}>{bookName} · verse order</text>
        <text className="axis-title" x={16} y={height / 2} transform={`rotate(-90 16 ${height / 2})`}>{distanceLabel}</text>
        {valid.map((unit) => {
          const selected = unit.id === selectedId;
          return (
            <circle
              className={selected ? "point selected-point" : "point"}
              cx={xFor(unit)}
              cy={yFor(unit)}
              key={unit.id}
              r={selected ? 6 : 3.8}
              tabIndex={0}
              role="button"
              aria-label={`${unit.reference}, ${distanceLabel} ${formatScore(distanceFor(unit, distanceField))}. A: ${unit.leftText ?? "No aligned text"}. B: ${unit.rightText ?? "No aligned text"}`}
              onClick={() => onSelect(unit)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onSelect(unit);
                }
              }}
            >
              <title>{`${unit.reference}\n${distanceLabel}: ${formatScore(distanceFor(unit, distanceField))}\nA: ${unit.leftText ?? "No aligned text"}\nB: ${unit.rightText ?? "No aligned text"}`}</title>
            </circle>
          );
        })}
      </svg>
      <div className="chart-note"><span className="legend-dot" /> matched verse <span className="legend-ring" /> selected verse <span className="brush-hint">Drag to focus a range</span>{rangeActive && <button className="clear-range" onClick={onClearBrush}>Reset range</button>}<span className="chart-count">{valid.length} scored units</span></div>
    </div>
  );
}

function ScatterPlot({ units, selectedId, onSelect, distanceField, distanceLabel, maxScore }: { units: ComparisonUnit[]; selectedId: string | undefined; onSelect: (unit: ComparisonUnit) => void; distanceField: string; distanceLabel: string; maxScore: number }) {
  const width = 1000;
  const height = 266;
  const padding = { left: 58, right: 24, top: 20, bottom: 42 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const valid = units.filter((unit) => distanceFor(unit, distanceField) !== null && unit.wordingDistance !== null);
  const xFor = (unit: ComparisonUnit) => padding.left + (unit.wordingDistance ?? 0) * plotWidth;
  const yFor = (unit: ComparisonUnit) => padding.top + (1 - (distanceFor(unit, distanceField) ?? 0) / maxScore) * plotHeight;
  return (
    <div className="chart-shell compact-chart">
      <svg className="chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-labelledby="scatter-title scatter-description">
        <title id="scatter-title">Wording change compared with comparison distance</title>
        <desc id="scatter-description">Each point is a verse. Points farther right use less shared vocabulary; points higher have more divergence according to the selected comparison metric.</desc>
        {[0, 0.5, 1].map((value) => <line className="grid-line" key={`h-${value}`} x1={padding.left} x2={width - padding.right} y1={padding.top + (1 - value) * plotHeight} y2={padding.top + (1 - value) * plotHeight} />)}
        {[0, 0.5, 1].map((value) => <line className="grid-line" key={`v-${value}`} x1={padding.left + value * plotWidth} x2={padding.left + value * plotWidth} y1={padding.top} y2={height - padding.bottom} />)}
        <line className="axis-line" x1={padding.left} x2={padding.left} y1={padding.top} y2={height - padding.bottom} />
        <line className="axis-line" x1={padding.left} x2={width - padding.right} y1={height - padding.bottom} y2={height - padding.bottom} />
        <text className="axis-title" x={width / 2} y={height - 10} textAnchor="middle">wording distance</text>
        <text className="axis-title" x={17} y={height / 2} transform={`rotate(-90 17 ${height / 2})`}>{distanceLabel}</text>
        {valid.map((unit) => (
          <circle
            className={unit.id === selectedId ? "point selected-point" : "point scatter-point"}
            key={unit.id}
            cx={xFor(unit)}
            cy={yFor(unit)}
            r={unit.id === selectedId ? 6 : 3.6}
            tabIndex={0}
            role="button"
            aria-label={`${unit.reference}, wording distance ${formatScore(unit.wordingDistance)}, ${distanceLabel} ${formatScore(distanceFor(unit, distanceField))}. A: ${unit.leftText ?? "No aligned text"}. B: ${unit.rightText ?? "No aligned text"}`}
            onClick={() => onSelect(unit)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onSelect(unit);
              }
            }}
          >
            <title>{`${unit.reference}\nwording distance: ${formatScore(unit.wordingDistance)}\n${distanceLabel}: ${formatScore(distanceFor(unit, distanceField))}\nA: ${unit.leftText ?? "No aligned text"}\nB: ${unit.rightText ?? "No aligned text"}`}</title>
          </circle>
        ))}
      </svg>
    </div>
  );
}

function App() {
  const [data, setData] = useState<ComparisonData | null>(null);
  const [manifest, setManifest] = useState<ComparisonManifest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pairId, setPairId] = useState(parseInitialPair());
  const [book, setBook] = useState(parseInitialBook());
  const [chapter, setChapter] = useState(new URLSearchParams(window.location.search).get("chapter") ?? "all");
  const [search, setSearch] = useState(new URLSearchParams(window.location.search).get("q") ?? "");
  const [selectedId, setSelectedId] = useState<string | undefined>(parseInitialRef() ?? undefined);
  const [brushRange, setBrushRange] = useState<UnitRange | null>(parseInitialRange());

  const pair = PAIRS.find((candidate) => candidate.id === pairId) ?? PAIRS[0];

  useEffect(() => {
    const controller = new AbortController();
    setData(null);
    setError(null);
    const load = async () => {
      const response = await fetch(pair.manifestUrl ?? pair.dataUrl ?? "", { signal: controller.signal });
      if (!response.ok) throw new Error(`Could not load comparison data (${response.status})`);
      if (pair.manifestUrl) {
        const nextManifest = await response.json() as ComparisonManifest;
        setManifest(nextManifest);
        const selectedBook = nextManifest.books.find((entry) => entry.id === book) ?? nextManifest.books[0];
        if (!selectedBook) throw new Error("Comparison manifest has no books");
        if (selectedBook.id !== book) {
          setBook(selectedBook.id);
          setBrushRange(null);
        }
        const bookResponse = await fetch(selectedBook.dataUrl, { signal: controller.signal });
        if (!bookResponse.ok) throw new Error(`Could not load ${selectedBook.name} (${bookResponse.status})`);
        setData(await bookResponse.json() as ComparisonData);
      } else {
        setManifest(null);
        setData(await response.json() as ComparisonData);
      }
    };
    load().catch((reason: Error) => {
      if (reason.name !== "AbortError") setError(reason.message);
    });
    return () => controller.abort();
  }, [book, pair.dataUrl, pair.manifestUrl]);

  const chapters = useMemo(() => data ? [...new Set(data.units.map((unit) => unit.chapter))].sort((a, b) => a - b) : [], [data]);
  const books = manifest?.books ?? [{ id: "JHN", name: "John", dataUrl: "", totalUnits: data?.summary.totalUnits ?? 0, matchedUnits: data?.summary.matchedUnits ?? 0, coverage: data && data.summary.totalUnits ? data.summary.matchedUnits / data.summary.totalUnits : 0 }];
  const filtered = useMemo(() => {
    if (!data) return [];
    const query = search.trim().toLocaleLowerCase();
    return data.units.filter((unit) => {
      const inChapter = chapter === "all" || unit.chapter === Number(chapter);
      const inSearch = !query || unit.reference.toLocaleLowerCase().includes(query) || (unit.leftText ?? "").toLocaleLowerCase().includes(query) || (unit.rightText ?? "").toLocaleLowerCase().includes(query);
      return inChapter && inSearch;
    });
  }, [chapter, data, search]);
  const visibleUnits = useMemo(() => {
    if (!brushRange || !filtered.length) return filtered;
    const start = Math.max(0, Math.min(brushRange.start, filtered.length - 1));
    const end = Math.max(start, Math.min(brushRange.end, filtered.length - 1));
    return filtered.slice(start, end + 1);
  }, [brushRange, filtered]);
  const selected = visibleUnits.find((unit) => unit.id === selectedId) ?? visibleUnits.find((unit) => unit.status === "matched") ?? visibleUnits[0];
  const distanceField = data?.metadata.metric.distanceField ?? "lexicalDistance";
  const distanceLabel = data?.metadata.metric.label.toLocaleLowerCase().replace("baseline", "distance") ?? "distance";
  const maxScore = Math.max(0.1, ...visibleUnits.map((unit) => distanceFor(unit, distanceField) ?? 0));
  const ranked = [...visibleUnits].filter((unit) => distanceFor(unit, distanceField) !== null).sort((a, b) => (distanceFor(b, distanceField) ?? 0) - (distanceFor(a, distanceField) ?? 0)).slice(0, 8);
  const selectedIndex = selected ? visibleUnits.findIndex((unit) => unit.id === selected.id) : -1;
  const previous = selectedIndex > 0 ? visibleUnits[selectedIndex - 1] : undefined;
  const next = selectedIndex >= 0 ? visibleUnits[selectedIndex + 1] : undefined;

  useEffect(() => {
    if (selected) {
      setSelectedId((current) => current ?? selected.id);
      updateUrl(pair.id, book, selected, chapter, search, brushRange);
    }
  }, [book, brushRange, chapter, pair.id, search, selected]);

  const selectUnit = (unit: ComparisonUnit) => {
    setSelectedId(unit.id);
    updateUrl(pair.id, book, unit, chapter, search, brushRange);
  };

  const focusRange = (start: number, end: number) => {
    const nextRange = { start: Math.min(start, end), end: Math.max(start, end) };
    setBrushRange(nextRange);
    const firstScored = visibleUnits.slice(nextRange.start, nextRange.end + 1).find((unit) => distanceFor(unit, distanceField) !== null);
    if (firstScored) setSelectedId(firstScored.id);
  };

  if (error) return <main className="app error-state"><p className="eyebrow">Ghost in the Word</p><h1>Couldn’t load this comparison.</h1><p>{error}</p></main>;
  if (!data) return <main className="app loading-state"><div className="loading-orb" /><p>Loading the comparison atlas…</p></main>;

  const leftName = data.metadata.leftEdition.name;
  const rightName = data.metadata.rightEdition.name;
  const metric = data.metadata.metric;
  const bookName = displayBook(book);
  const alignmentNote = data.metadata.alignment.method === "exact-book-chapter-verse"
    ? "The chart preserves missing passages as gaps and only scores exact book/chapter/verse matches."
    : "The chart preserves missing and unresolved passages as gaps and only scores reviewed mappings marked matched.";

  return (
    <main className="app">
      <header className="topbar">
        <div className="brand"><span className="brand-mark">✦</span><span>Ghost in the Word</span></div>
        <div className="topbar-meta"><span className="status-pip" /> live comparison atlas <span className="slash">/</span> {(manifest?.summary.scoredUnits ?? data.summary.scoredUnits).toLocaleString()} scored verses in corpus</div>
      </header>

      <section className="hero">
        <div className="hero-copy">
          <p className="eyebrow">TRANSLATION ATLAS · PILOT</p>
          <h1>Where the words<br /><em>move apart.</em></h1>
          <p className="lede">A verse-by-verse view of how {leftName} and {rightName} render {bookName}. Find an unusual point, then read the text that made it move.</p>
        </div>
        <div className="hero-stamp"><span>01</span><span>{bookName.toUpperCase()}</span><span>·</span><span>VERSE</span><span>MAP</span></div>
      </section>

      <section className="controls panel">
        <div className="translation-pair">
          <label><span>translation A</span><strong>{leftName}</strong></label>
          <span className="pair-arrow">→</span>
          <label><span>translation B</span><strong>{rightName}</strong></label>
        </div>
        <div className="filter-grid">
          <label className="field"><span>comparison</span><select value={pair.id} onChange={(event) => { setPairId(event.target.value); setBook("JHN"); setSelectedId(undefined); setBrushRange(null); }} aria-label="Comparison pair">{PAIRS.map((candidate) => <option value={candidate.id} key={candidate.id}>{candidate.label}</option>)}</select></label>
          <label className="field"><span>book</span><select value={book} onChange={(event) => { setBook(event.target.value); setChapter("all"); setSelectedId(undefined); setBrushRange(null); }} aria-label="Book">{books.map((entry) => <option value={entry.id} key={entry.id}>{entry.name} · {entry.totalUnits.toLocaleString()} · {Math.round(entry.coverage * 100)}%</option>)}</select></label>
          <label className="field"><span>chapter</span><select value={chapter} onChange={(event) => { setChapter(event.target.value); setSelectedId(undefined); setBrushRange(null); }}><option value="all">All chapters</option>{chapters.map((item) => <option key={item} value={item}>Chapter {item}</option>)}</select></label>
          <label className="field search-field"><span>find a passage</span><input value={search} onChange={(event) => { setSearch(event.target.value); setBrushRange(null); }} placeholder="Reference or phrase" /></label>
        </div>
      </section>

      <section className="summary-grid">
        <div className="summary-card"><span className="summary-label">scope</span><strong>{visibleUnits.length.toLocaleString()}</strong><span>{brushRange ? "focused verses" : "visible verses"}</span></div>
        <div className="summary-card"><span className="summary-label">highest distance</span><strong>{formatScore(ranked[0] ? distanceFor(ranked[0], distanceField) : null)}</strong><span>{ranked[0]?.reference ?? "No match"}</span></div>
        <div className="summary-card summary-card-wide"><span className="summary-label">alignment coverage</span><div className="coverage-bar"><i style={{ width: `${(data.summary.matchedUnits / data.summary.totalUnits) * 100}%` }} /></div><span>{data.summary.matchedUnits.toLocaleString()} matched · {data.summary.totalUnits.toLocaleString()} total</span></div>
      </section>

      <section className="panel chart-panel">
        <div className="panel-heading"><div><p className="eyebrow">01 · DIVERGENCE ACROSS {bookName.toUpperCase()}</p><h2>Find the verses that drift.</h2></div><span className="metric-chip">{metric.label.toUpperCase()}</span></div>
        <p className="panel-intro">Each point is a matched verse in canonical order. Higher points have more divergence according to the selected metric. {metric.description}</p>
        <DivergenceChart units={visibleUnits} selectedId={selected?.id} onSelect={selectUnit} maxScore={maxScore} distanceField={distanceField} distanceLabel={distanceLabel} bookName={bookName} onBrush={focusRange} onClearBrush={() => setBrushRange(null)} rangeActive={Boolean(brushRange)} />
      </section>

      <div className="two-column">
        <section className="panel reader-panel">
          <div className="panel-heading reader-heading"><div><p className="eyebrow">02 · LINKED READER</p><h2>{selected?.reference ?? "Select a verse"}</h2></div><div className="reader-nav"><button aria-label="Previous verse" disabled={!previous} onClick={() => previous && selectUnit(previous)}>←</button><button aria-label="Next verse" disabled={!next} onClick={() => next && selectUnit(next)}>→</button></div></div>
          {selected ? <>
            <div className="reference-line"><span>{displayBook(selected.book)} · chapter {selected.chapter} · verse {selected.verse}</span><span className={`alignment-status ${selected.status}`}>{selected.status === "matched" ? "matched" : selected.status.replace("missing-", "missing ")}</span></div>
            <div className="translation-columns">
              <article className="translation-card"><div className="translation-label"><span className="edition-dot dot-a" />{leftName}</div><p><MarkedText text={selected.leftText} other={selected.rightText} /></p><TranslationNotes notes={selected.leftNotes} /></article>
              <article className="translation-card"><div className="translation-label"><span className="edition-dot dot-b" />{rightName}</div><p><MarkedText text={selected.rightText} other={selected.leftText} /></p><TranslationNotes notes={selected.rightNotes} /></article>
            </div>
            <div className="score-row"><div><span>{distanceLabel}</span><strong>{formatScore(distanceFor(selected, distanceField))}</strong></div><div><span>wording distance</span><strong>{formatScore(selected.wordingDistance)}</strong></div><div className="score-explainer">Highlighted words are a token-level reading aid. They do not explain the score.</div></div>
          </> : <p className="empty-state">No verses match this filter.</p>}
        </section>

        <section className="panel ranked-panel">
          <div className="panel-heading"><div><p className="eyebrow">03 · RANKED DIFFERENCES</p><h2>Start with a lead.</h2></div></div>
          <p className="panel-intro">The largest {distanceLabel} values in the current view. Select one to sync the chart and reader.</p>
          <div className="ranked-list">{ranked.map((unit, index) => <button className={unit.id === selected?.id ? "ranked-item active" : "ranked-item"} key={unit.id} onClick={() => selectUnit(unit)}><span className="rank-number">{String(index + 1).padStart(2, "0")}</span><span className="rank-ref">{unit.reference}<small>{unit.leftText?.slice(0, 68)}{(unit.leftText?.length ?? 0) > 68 ? "…" : ""}</small></span><strong>{formatScore(distanceFor(unit, distanceField))}</strong></button>)}{ranked.length === 0 && <p className="empty-state">No scored verses in this view.</p>}</div>
        </section>
      </div>

      <section className="panel scatter-panel">
        <div className="panel-heading"><div><p className="eyebrow">04 · WORDING / DISTANCE</p><h2>Different words don’t always mean different things.</h2></div></div>
        <p className="panel-intro">The same comparison shown two ways: horizontal movement is wording distance; vertical movement is the selected comparison metric. Use this as an investigation map, not a classification.</p>
        <ScatterPlot units={visibleUnits} selectedId={selected?.id} onSelect={selectUnit} distanceField={distanceField} distanceLabel={distanceLabel} maxScore={maxScore} />
      </section>

      <section className="method-note"><div className="method-icon">i</div><div><strong>What this score means</strong><p>{metric.description} {alignmentNote} Each run is identified in the comparison artifact so model estimates remain distinct from lexical baselines.</p></div><button className="share-button" onClick={() => navigator.clipboard?.writeText(window.location.href)}>Copy this view <span>↗</span></button></section>

      <footer><span>GHOST IN THE WORD · PILOT 01</span><span>Sources: <a href={pair.leftSource} target="_blank" rel="noreferrer">A</a> + <a href={pair.rightSource} target="_blank" rel="noreferrer">B</a></span><span>{metric.id}</span></footer>
    </main>
  );
}

export { App };
