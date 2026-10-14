import { useEffect, useMemo, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import type { ComparisonData, ComparisonManifest, ComparisonUnit, TranslationMatrix } from "./types";

type PairConfig = {
  id: string;
  label: string;
  dataUrl?: string;
  manifestUrl?: string;
  matrixUrl?: string;
  leftSource: string;
  rightSource: string;
};

const PAIRS: PairConfig[] = [
  {
    id: "webp-bsb",
    label: "WEB ↔ BSB",
    manifestUrl: "/data/webp-bsb/manifest.json",
    matrixUrl: "/data/john-translation-matrix.json",
    leftSource: "https://ebible.org/find/details.php?id=engwebp",
    rightSource: "https://berean.bible/downloads.htm",
  },
  {
    id: "webp-asv",
    label: "WEB ↔ ASV 1901",
    dataUrl: "/data/john-webp-asv.json",
    matrixUrl: "/data/john-translation-matrix.json",
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
  {
    id: "webp-rv1909-e5-small",
    label: "WEB ↔ RV1909 · E5 small",
    dataUrl: "/data/john-webp-rv1909-e5-small.json",
    leftSource: "https://ebible.org/find/details.php?id=engwebp",
    rightSource: "https://ebible.org/find/details.php?id=spaRV1909",
  },
  {
    id: "webp-srgrc-e5-small",
    label: "WEB ↔ SR Greek source · E5 small",
    dataUrl: "/data/john-webp-srgrc-e5-small.json",
    leftSource: "https://ebible.org/find/details.php?id=engwebp",
    rightSource: "https://github.com/Center-for-New-Testament-Restoration/SR",
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

function downloadText(filename: string, content: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

function csvCell(value: unknown) {
  const text = value === null || value === undefined ? "" : String(value);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function distanceFor(unit: ComparisonUnit, field: string) {
  const value = unit[field as keyof ComparisonUnit];
  return typeof value === "number" ? value : null;
}

function normalizedWords(text: string) {
  return text.toLocaleLowerCase().match(/[\p{L}\p{N}’'-]+/gu) ?? [];
}

function MarkedText({ text, other, sameLanguage = true }: { text: string | null; other: string | null; sameLanguage?: boolean }) {
  if (!text) return <span className="missing-copy">No aligned text</span>;
  if (!sameLanguage) return <>{text}</>;
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

function formatOverviewScore(score: number | null | undefined) {
  return score === null || score === undefined ? "—" : score.toFixed(3);
}

function AtlasOverview({
  manifest,
  selectedBook,
  onSelectBook,
  onSelectChapter,
}: {
  manifest: ComparisonManifest;
  selectedBook: string;
  onSelectBook: (book: string) => void;
  onSelectChapter: (book: string, chapter: number) => void;
}) {
  const selected = manifest.books.find((book) => book.id === selectedBook) ?? manifest.books[0];
  const metricLabel = manifest.comparison.metric.label;
  return (
    <section className="panel atlas-overview" aria-labelledby="atlas-overview-title">
      <div className="panel-heading">
        <div><p className="eyebrow">ATLAS OVERVIEW · {manifest.books.length} BOOKS</p><h2 id="atlas-overview-title">See the shape of the corpus.</h2></div>
        <span className="metric-chip">{metricLabel.toUpperCase()}</span>
      </div>
      <p className="panel-intro">Book and chapter summaries keep the full corpus navigable. Select a book or chapter to load its verse points; scores describe this translation pair and metric only.</p>
      <div className="atlas-overview-stats">
        <div><span>scored verses</span><strong>{manifest.summary.scoredUnits.toLocaleString()}</strong></div>
        <div><span>coverage</span><strong>{Math.round((manifest.summary.coverage ?? 0) * 100)}%</strong></div>
        <div><span>median distance</span><strong>{formatOverviewScore(manifest.summary.score?.median)}</strong></div>
        <div><span>highest distance</span><strong>{formatOverviewScore(manifest.summary.score?.max)}</strong></div>
      </div>
      <div className="atlas-books" role="list" aria-label="Book summaries">
        {manifest.books.map((book) => (
          <button className={book.id === selected?.id ? "atlas-book active" : "atlas-book"} key={book.id} onClick={() => onSelectBook(book.id)} role="listitem">
            <span className="atlas-book-name">{book.name}</span>
            <span className="atlas-book-meta">{book.totalUnits.toLocaleString()} verses · {Math.round(book.coverage * 100)}% · median {formatOverviewScore(book.score.median)}</span>
            <span className="atlas-book-bar"><i style={{ width: `${Math.max(0, Math.min(100, book.coverage * 100))}%` }} /></span>
          </button>
        ))}
      </div>
      {selected && <div className="atlas-chapters">
        <div className="atlas-chapters-heading"><span>{selected.name} chapters</span><small>click a chapter to drill in · {selected.matchedUnits.toLocaleString()} matched of {selected.totalUnits.toLocaleString()}</small></div>
        <div className="chapter-summary-list" role="list" aria-label={`${selected.name} chapter summaries`}>
          {selected.chapters.map((chapter) => (
            <button key={chapter.chapter} onClick={() => onSelectChapter(selected.id, chapter.chapter)} role="listitem">
              <span>ch {chapter.chapter}</span><strong>{formatOverviewScore(chapter.score.median)}</strong><small>{chapter.scoredUnits.toLocaleString()} scored · {Math.round(chapter.coverage * 100)}%</small>
            </button>
          ))}
        </div>
      </div>}
    </section>
  );
}

function ResultsTable({
  units,
  selectedId,
  onSelect,
  distanceField,
  distanceLabel,
  sameLanguage,
}: {
  units: ComparisonUnit[];
  selectedId: string | undefined;
  onSelect: (unit: ComparisonUnit) => void;
  distanceField: string;
  distanceLabel: string;
  sameLanguage: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <section className="panel results-table-panel" aria-labelledby="results-table-title">
      <div className="panel-heading"><div><p className="eyebrow">05 · ACCESSIBLE RESULTS</p><h2 id="results-table-title">Read every visible point.</h2></div><span className="table-count">{units.length.toLocaleString()} rows</span></div>
      <p className="panel-intro">This table mirrors the current book, chapter, search, and brush filters. Use the reference buttons to select a row and synchronize the chart and reader.</p>
      <div className="results-table-controls"><button className="table-toggle" aria-expanded={expanded} aria-controls="comparison-results-table" onClick={() => setExpanded((value) => !value)}>{expanded ? "Hide table" : "Show table"}</button><span>Rows are loaded when opened for faster navigation.</span></div>
      {expanded && <div className="results-table-wrap" id="comparison-results-table">
        <table>
          <caption className="sr-only">Filtered translation comparison results</caption>
          <thead><tr><th scope="col">Reference</th><th scope="col">Status</th><th scope="col">{distanceLabel}</th><th scope="col">Wording</th><th scope="col">Translation A</th><th scope="col">Translation B</th></tr></thead>
          <tbody>{units.map((unit) => (
            <tr className={unit.id === selectedId ? "selected-row" : undefined} key={unit.id}>
              <th scope="row"><button className="table-ref" onClick={() => onSelect(unit)}>{unit.reference}</button></th>
              <td><span className={`table-status ${unit.status}`}>{unit.status === "matched" ? "matched" : unit.status.replace("missing-", "missing ")}</span></td>
              <td>{formatScore(distanceFor(unit, distanceField))}</td>
              <td>{sameLanguage ? formatScore(unit.wordingDistance) : "n/a"}</td>
              <td>{unit.leftText ?? "No aligned text"}</td>
              <td>{unit.rightText ?? "No aligned text"}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>}
    </section>
  );
}

function TranslationDistanceMatrix({ matrix, selectedId }: { matrix: TranslationMatrix; selectedId: string | undefined }) {
  const passage = matrix.passages.find((candidate) => candidate.id === selectedId);
  if (!passage || passage.status !== "matched") return null;
  const distanceForPair = (left: string, right: string) => {
    if (left === right) return 0;
    const key = [left, right].sort().join("|");
    return passage.distances[key]?.lexicalDistance ?? null;
  };
  return (
    <section className="translation-matrix" aria-labelledby="translation-matrix-title">
      <div className="matrix-heading"><div><span className="matrix-kicker">PANEL VIEW</span><strong id="translation-matrix-title">Distance across three translations</strong></div><span>{passage.reference}</span></div>
      <div className="matrix-table-wrap">
        <table className="matrix-table">
          <caption className="sr-only">Pairwise lexical distance matrix for {passage.reference}</caption>
          <thead><tr><th scope="col">edition</th>{matrix.metadata.editions.map((edition) => <th scope="col" key={edition.id}>{edition.name}</th>)}</tr></thead>
          <tbody>{matrix.metadata.editions.map((row) => <tr key={row.id}><th scope="row">{row.name}</th>{matrix.metadata.editions.map((column) => <td key={column.id}>{formatScore(distanceForPair(row.id, column.id))}</td>)}</tr>)}</tbody>
        </table>
      </div>
      <p className="matrix-note">Pairwise lexical distances are shown for panel context. They describe this verse and edition set; they do not identify a faithful translation.</p>
    </section>
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
  const [matrix, setMatrix] = useState<TranslationMatrix | null>(null);
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
    setMatrix(null);
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
      if (pair.matrixUrl && book === "JHN") {
        const matrixResponse = await fetch(pair.matrixUrl, { signal: controller.signal });
        if (!matrixResponse.ok) throw new Error(`Could not load translation matrix (${matrixResponse.status})`);
        setMatrix(await matrixResponse.json() as TranslationMatrix);
      }
    };
    load().catch((reason: Error) => {
      if (reason.name !== "AbortError") setError(reason.message);
    });
    return () => controller.abort();
  }, [book, pair.dataUrl, pair.manifestUrl, pair.matrixUrl]);

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

  const selectBook = (nextBook: string) => {
    setBook(nextBook);
    setChapter("all");
    setSelectedId(undefined);
    setBrushRange(null);
  };

  const selectChapter = (nextBook: string, nextChapter: number) => {
    setBook(nextBook);
    setChapter(String(nextChapter));
    setSelectedId(undefined);
    setBrushRange(null);
  };

  if (error) return <main className="app error-state"><p className="eyebrow">Ghost in the Word</p><h1>Couldn’t load this comparison.</h1><p>{error}</p></main>;
  if (!data) return <main className="app loading-state"><div className="loading-orb" /><p>Loading the comparison atlas…</p></main>;

  const leftName = data.metadata.leftEdition.name;
  const rightName = data.metadata.rightEdition.name;
  const metric = data.metadata.metric;
  const bookName = displayBook(book);
  const sameLanguage = Boolean(data.metadata.leftEdition.language && data.metadata.leftEdition.language === data.metadata.rightEdition.language);
  const sourceMode = data.metadata.leftEdition.role === "source" || data.metadata.rightEdition.role === "source";
  const leftRole = data.metadata.leftEdition.role === "source" ? "source text A" : "translation A";
  const rightRole = data.metadata.rightEdition.role === "source" ? "source text B" : "translation B";
  const alignmentNote = data.metadata.alignment.method === "exact-book-chapter-verse"
    ? "The chart preserves missing passages as gaps and only scores exact book/chapter/verse matches."
    : "The chart preserves missing and unresolved passages as gaps and only scores reviewed mappings marked matched.";
  const exportCurrentView = (format: "json" | "csv") => {
    const filename = `${pair.id}-${book}-${brushRange ? `range-${brushRange.start}-${brushRange.end}` : "view"}.${format}`;
    if (format === "json") {
      downloadText(filename, JSON.stringify({ metadata: data.metadata, summary: data.summary, filters: { chapter, search, range: brushRange }, units: visibleUnits }, null, 2), "application/json");
      return;
    }
    const header = ["reference", "status", "leftText", "rightText", data.metadata.metric.distanceField, "wordingDistance"];
    const rows = visibleUnits.map((unit) => [unit.reference, unit.status, unit.leftText, unit.rightText, distanceFor(unit, distanceField), unit.wordingDistance].map(csvCell).join(","));
    downloadText(filename, [header.join(","), ...rows].join("\n") + "\n", "text/csv;charset=utf-8");
  };

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

      {manifest && <AtlasOverview manifest={manifest} selectedBook={book} onSelectBook={selectBook} onSelectChapter={selectChapter} />}

      <section className="controls panel">
        <div className="translation-pair">
          <label><span>{leftRole}</span><strong>{leftName}</strong></label>
          <span className="pair-arrow">→</span>
          <label><span>{rightRole}</span><strong>{rightName}</strong></label>
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
              <article className="translation-card"><div className="translation-label"><span className="edition-dot dot-a" />{leftName}{data.metadata.leftEdition.role === "source" ? " · source text" : ""}</div><p><MarkedText text={selected.leftText} other={selected.rightText} sameLanguage={sameLanguage} /></p><TranslationNotes notes={selected.leftNotes} /></article>
              <article className="translation-card"><div className="translation-label"><span className="edition-dot dot-b" />{rightName}{data.metadata.rightEdition.role === "source" ? " · source text" : ""}</div><p><MarkedText text={selected.rightText} other={selected.leftText} sameLanguage={sameLanguage} /></p><TranslationNotes notes={selected.rightNotes} /></article>
            </div>
            {matrix && <TranslationDistanceMatrix matrix={matrix} selectedId={selected.id} />}
            {(previous || next) && <div className="reader-context" aria-label="Adjacent verse context">
              {previous && <button onClick={() => selectUnit(previous)}><span>← {previous.reference}</span><small>{previous.leftText ?? "No aligned text"}</small></button>}
              {next && <button onClick={() => selectUnit(next)}><span>{next.reference} →</span><small>{next.leftText ?? "No aligned text"}</small></button>}
            </div>}
            <div className="score-row"><div><span>{distanceLabel}</span><strong>{formatScore(distanceFor(selected, distanceField))}</strong></div>{sameLanguage ? <div><span>wording distance</span><strong>{formatScore(selected.wordingDistance)}</strong></div> : <div><span>wording distance</span><strong>n/a</strong></div>}<div className="score-explainer">{sameLanguage ? "Highlighted words are a token-level reading aid. They do not explain the score." : "Wording distance is hidden for cross-language comparisons because token overlap is not comparable across scripts."}</div></div>
          </> : <p className="empty-state">No verses match this filter.</p>}
        </section>

        <section className="panel ranked-panel">
          <div className="panel-heading"><div><p className="eyebrow">03 · RANKED DIFFERENCES</p><h2>Start with a lead.</h2></div></div>
          <p className="panel-intro">The largest {distanceLabel} values in the current view. Select one to sync the chart and reader.</p>
          <div className="ranked-list">{ranked.map((unit, index) => <button className={unit.id === selected?.id ? "ranked-item active" : "ranked-item"} key={unit.id} onClick={() => selectUnit(unit)}><span className="rank-number">{String(index + 1).padStart(2, "0")}</span><span className="rank-ref">{unit.reference}<small>{unit.leftText?.slice(0, 68)}{(unit.leftText?.length ?? 0) > 68 ? "…" : ""}</small></span><strong>{formatScore(distanceFor(unit, distanceField))}</strong></button>)}{ranked.length === 0 && <p className="empty-state">No scored verses in this view.</p>}</div>
        </section>
      </div>

      {sameLanguage && <section className="panel scatter-panel">
        <div className="panel-heading"><div><p className="eyebrow">04 · WORDING / DISTANCE</p><h2>Different words don’t always mean different things.</h2></div></div>
        <p className="panel-intro">The same comparison shown two ways: horizontal movement is wording distance; vertical movement is the selected comparison metric. Use this as an investigation map, not a classification.</p>
        <ScatterPlot units={visibleUnits} selectedId={selected?.id} onSelect={selectUnit} distanceField={distanceField} distanceLabel={distanceLabel} maxScore={maxScore} />
      </section>}

      <ResultsTable units={visibleUnits} selectedId={selected?.id} onSelect={selectUnit} distanceField={distanceField} distanceLabel={distanceLabel} sameLanguage={sameLanguage} />

      <section className="method-note"><div className="method-icon">i</div><div className="method-copy"><strong>What this score means</strong><p>{metric.description} {alignmentNote} {sourceMode ? "A source edition is shown as a textual reference point; this does not produce a faithfulness grade." : ""} Each run is identified in the comparison artifact so model estimates remain distinct from lexical baselines.</p><details className="provenance-details"><summary>Show provenance</summary><dl><dt>Metric</dt><dd>{metric.id}</dd><dt>Alignment</dt><dd>{data.metadata.alignment.method}</dd><dt>Languages</dt><dd>{data.metadata.leftEdition.language ?? "unknown"} → {data.metadata.rightEdition.language ?? "unknown"}</dd><dt>Roles</dt><dd>{data.metadata.leftEdition.role ?? "translation"} → {data.metadata.rightEdition.role ?? "translation"}</dd>{data.metadata.embeddingRun && <><dt>Model</dt><dd>{data.metadata.embeddingRun.modelId} · {data.metadata.embeddingRun.dimensions} dimensions · max {data.metadata.embeddingRun.maxSeqLength} tokens</dd><dt>Input hash</dt><dd>{data.metadata.embeddingRun.inputHash}</dd>{data.metadata.embeddingRun.leftInputHash && <><dt>Left input hash</dt><dd>{data.metadata.embeddingRun.leftInputHash}</dd><dt>Right input hash</dt><dd>{data.metadata.embeddingRun.rightInputHash}</dd></>}</>}</dl></details></div><div className="method-actions"><button className="share-button" onClick={() => exportCurrentView("json")}>Download JSON</button><button className="share-button" onClick={() => exportCurrentView("csv")}>Download CSV</button><button className="share-button" onClick={() => navigator.clipboard?.writeText(window.location.href)}>Copy this view <span>↗</span></button></div></section>

      <footer><span>GHOST IN THE WORD · PILOT 01</span><span>Sources: <a href={pair.leftSource} target="_blank" rel="noreferrer">A</a> + <a href={pair.rightSource} target="_blank" rel="noreferrer">B</a></span><span>{metric.id}</span></footer>
    </main>
  );
}

export { App };
