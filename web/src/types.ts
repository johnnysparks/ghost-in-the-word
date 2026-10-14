export type UnitStatus = "matched" | "missing-left" | "missing-right" | "unresolved";

export type ComparisonUnit = {
  id: string;
  order: number;
  reference: string;
  book: string;
  chapter: number;
  verse: string;
  leftText: string | null;
  rightText: string | null;
  leftEdition: string;
  rightEdition: string;
  status: UnitStatus;
  mappingType?: string;
  leftReferences?: string[];
  rightReferences?: string[];
  mappingMethod?: string;
  leftNotes?: string[];
  rightNotes?: string[];
  wordingDistance: number | null;
  lexicalDistance: number | null;
  embeddingDistance?: number | null;
};

export type ComparisonData = {
  schemaVersion: number;
  metadata: {
    leftEdition: { id: string; name: string; language?: string };
    rightEdition: { id: string; name: string; language?: string };
    scope: { books: string[]; unit: string };
    alignment: { method: string; statuses: Record<string, number> };
    metric: {
      id: string;
      label: string;
      distanceField: string;
      wordingField: keyof ComparisonUnit;
      description: string;
    };
    embeddingRun?: {
      modelId: string;
      dimensions: number;
      maxSeqLength: number;
      inputHash: string;
      prefix: string;
    };
    source: { alignment: string };
  };
  units: ComparisonUnit[];
  summary: { totalUnits: number; matchedUnits: number; scoredUnits: number };
};

export type ComparisonManifest = {
  schemaVersion: number;
  kind: "comparison-partition-manifest";
  comparison: {
    leftEdition: { id: string; name: string; language?: string };
    rightEdition: { id: string; name: string; language?: string };
    metric: ComparisonData["metadata"]["metric"];
    alignment: ComparisonData["metadata"]["alignment"];
    scope: { books: string[]; unit: string };
  };
  summary: SummaryStats;
  books: Array<{
    id: string;
    name: string;
    dataUrl: string;
    totalUnits: number;
    matchedUnits: number;
    coverage: number;
    score: ScoreStats;
    statuses: Record<string, number>;
    chapters: Array<ChapterSummary>;
  }>;
};

export type ScoreStats = {
  mean: number | null;
  median: number | null;
  max: number | null;
};

export type ChapterSummary = {
  chapter: number;
  totalUnits: number;
  matchedUnits: number;
  scoredUnits: number;
  coverage: number;
  score: ScoreStats;
  statuses: Record<string, number>;
};

export type SummaryStats = {
  totalUnits: number;
  matchedUnits: number;
  scoredUnits: number;
  coverage?: number;
  score?: ScoreStats;
  statuses?: Record<string, number>;
};
