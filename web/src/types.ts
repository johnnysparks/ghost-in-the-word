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
  review?: Record<string, unknown>;
  assessments?: AssessmentRecord[];
  leftNotes?: string[];
  rightNotes?: string[];
  wordingDistance: number | null;
  lexicalDistance: number | null;
  embeddingDistance?: number | null;
};

export type AssessmentRecord = {
  id: string;
  sourceEdition: string;
  origin: "human" | "model" | "adjudicated" | string;
  reviewerId?: string;
  modelId?: string;
  judgmentType: string;
  judgment: string;
  evidence: string[];
  uncertainty: string;
  disagreement?: string[];
  version: string;
};

export type EditionMetadata = {
  id: string;
  name: string;
  language?: string;
  role?: string;
  source?: string;
  download?: string;
  license?: string;
  canon?: string;
  revision?: string;
  versification?: string;
  sourceTradition?: string;
  family?: string;
  attribution?: string;
};

export type ComparisonData = {
  schemaVersion: number;
  metadata: {
    leftEdition: EditionMetadata;
    rightEdition: EditionMetadata;
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
      modelRevision?: string;
      preprocessingVersion?: string;
      cacheKey?: string | null;
      cacheHit?: boolean;
      leftInputHash?: string;
      rightInputHash?: string;
      leftCacheKey?: string | null;
      rightCacheKey?: string | null;
      leftCacheHit?: boolean;
      rightCacheHit?: boolean;
      contextStrategy?: string;
      inputCount?: number;
      truncatedInputCount?: number | null;
    };
    source: { alignment: string };
    assessmentAttachment?: {
      schemaVersion: number;
      kind: string;
      sourceEdition: EditionMetadata;
      sourceDocument?: string;
      summary: Record<string, unknown>;
    };
  };
  units: ComparisonUnit[];
  summary: { totalUnits: number; matchedUnits: number; scoredUnits: number };
};

export type ComparisonManifest = {
  schemaVersion: number;
  kind: "comparison-partition-manifest";
  comparison: {
    leftEdition: EditionMetadata;
    rightEdition: EditionMetadata;
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

export type TranslationMatrix = {
  schemaVersion: number;
  kind: "translation-distance-matrix";
  metadata: {
    editions: EditionMetadata[];
    scope: { books: string[]; unit: string };
    metric: { id: string; label: string; description: string };
    sourceArtifacts?: string[];
  };
  passages: Array<{
    id: string;
    order: number;
    book: string;
    chapter: number;
    verse: string;
    reference: string;
    status: string;
    texts: Record<string, string>;
    distances: Record<string, { wordingDistance: number; lexicalDistance: number }>;
  }>;
  summary: { totalPassages: number; scoredPassages: number; editionCoverage: Record<string, number> };
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
