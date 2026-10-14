export type UnitStatus = "matched" | "missing-left" | "missing-right";

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
  wordingDistance: number | null;
  lexicalDistance: number | null;
};

export type ComparisonData = {
  schemaVersion: number;
  metadata: {
    leftEdition: { id: string; name: string };
    rightEdition: { id: string; name: string };
    scope: { books: string[]; unit: string };
    alignment: { method: string; statuses: Record<string, number> };
    metric: {
      id: string;
      label: string;
      distanceField: keyof ComparisonUnit;
      wordingField: keyof ComparisonUnit;
      description: string;
    };
    source: { alignment: string };
  };
  units: ComparisonUnit[];
  summary: { totalUnits: number; matchedUnits: number; scoredUnits: number };
};
