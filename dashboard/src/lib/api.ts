import type {
  FreshnessRow,
  IngestionRow,
  PipelineHealthRow,
  RuntimeRow,
  TestsRow,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    // Next.js 14 App Router: revalidate every 5 minutes.
    next: { revalidate: 300 },
  });
  if (!res.ok) throw new Error(`API ${path} returned ${res.status}`);
  return res.json() as Promise<T>;
}

export const api = {
  health: (days = 30) =>
    get<PipelineHealthRow[]>(`/api/pipeline/health?days=${days}`),
  freshness: () => get<FreshnessRow[]>("/api/pipeline/freshness"),
  tests: (days = 30) => get<TestsRow[]>(`/api/pipeline/tests?days=${days}`),
  runtime: (days = 30) =>
    get<RuntimeRow[]>(`/api/pipeline/runtime?days=${days}`),
  ingestion: (days = 30) =>
    get<IngestionRow[]>(`/api/pipeline/ingestion?days=${days}`),
};
