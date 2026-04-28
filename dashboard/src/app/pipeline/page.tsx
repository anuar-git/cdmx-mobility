import { api } from "@/lib/api";
import { FreshnessCard } from "@/components/FreshnessCard";
import { RowCountChart } from "@/components/RowCountChart";
import { TestPassRateChart } from "@/components/TestPassRateChart";
import { RuntimeChart } from "@/components/RuntimeChart";
import type { PipelineHealthRow } from "@/lib/types";

// This page is a React Server Component — data fetching happens server-side
// and the result is serialised to the client. Revalidates every 5 minutes
// (controlled by the fetch() call inside api.ts).

function SectionHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-4">
      <h2 className="text-lg font-semibold text-slate-800">{title}</h2>
      {subtitle && <p className="text-sm text-slate-500 mt-0.5">{subtitle}</p>}
    </div>
  );
}

function KpiCard({
  label,
  value,
  sub,
  ok,
}: {
  label: string;
  value: string | number;
  sub?: string;
  ok?: boolean;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</p>
      <p
        className={`mt-1 text-3xl font-bold ${
          ok === undefined ? "text-slate-900" : ok ? "text-green-600" : "text-red-600"
        }`}
      >
        {value}
      </p>
      {sub && <p className="mt-1 text-xs text-slate-400">{sub}</p>}
    </div>
  );
}

// Aggregate the last run_date from the health table for KPI summary.
function latestKpis(rows: PipelineHealthRow[]) {
  if (!rows.length) return null;
  const latestDate = rows[0].run_date; // ordered DESC
  const latest = rows.filter((r) => r.run_date === latestDate);

  const totalRows = latest.reduce((s, r) => s + (r.total_rows_ingested ?? 0), 0);
  const anyViolated = latest.some((r) => r.freshness_sla_violated === true);
  const passRate = latest.find((r) => r.dbt_test_pass_rate_pct != null)
    ?.dbt_test_pass_rate_pct;
  const runtime = latest.find((r) => r.dbt_total_runtime_seconds != null)
    ?.dbt_total_runtime_seconds;
  const gxOk = latest.every((r) => r.gx_all_suites_passed !== false);

  return { latestDate, totalRows, anyViolated, passRate, runtime, gxOk };
}

export default async function PipelinePage() {
  const [healthRows, freshnessRows, testsRows, runtimeRows, ingestionRows] =
    await Promise.all([
      api.health(30),
      api.freshness(),
      api.tests(30),
      api.runtime(30),
      api.ingestion(30),
    ]);

  const kpis = latestKpis(healthRows);

  return (
    <div className="max-w-7xl mx-auto px-4 py-8 space-y-10">
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Pipeline Health</h1>
          <p className="text-sm text-slate-500 mt-0.5">cdmx-mobility · daily_mobility_pipeline</p>
        </div>
        {kpis && (
          <p className="text-xs text-slate-400">Last run: {kpis.latestDate}</p>
        )}
      </div>

      {/* ── KPI summary row ─────────────────────────────────────────────── */}
      {kpis && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <KpiCard
            label="Freshness SLAs"
            value={kpis.anyViolated ? "VIOLATED" : "All OK"}
            sub="as of last check"
            ok={!kpis.anyViolated}
          />
          <KpiCard
            label="dbt Test Pass Rate"
            value={kpis.passRate != null ? `${kpis.passRate.toFixed(1)}%` : "—"}
            sub="last run"
            ok={kpis.passRate === 100}
          />
          <KpiCard
            label="GX Expectations"
            value={kpis.gxOk ? "All passed" : "Failures"}
            sub="Silver validation"
            ok={kpis.gxOk}
          />
          <KpiCard
            label="Rows Ingested"
            value={kpis.totalRows.toLocaleString()}
            sub={`dbt runtime: ${kpis.runtime != null ? `${Math.round(kpis.runtime)}s` : "—"}`}
          />
        </div>
      )}

      {/* ── Freshness SLA cards ─────────────────────────────────────────── */}
      <section>
        <SectionHeader
          title="Data Freshness SLAs"
          subtitle="Lag between the most recent Silver record and the check time. Violations fire a Slack alert."
        />
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {freshnessRows.map((row) => (
            <FreshnessCard key={row.source} row={row} />
          ))}
        </div>
      </section>

      {/* ── Row counts over time ─────────────────────────────────────────── */}
      <section>
        <SectionHeader
          title="Ingestion Volume (30 days)"
          subtitle="Total rows landed per source per day, stacked."
        />
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <RowCountChart rows={ingestionRows} />
        </div>
      </section>

      {/* ── Test pass rate ───────────────────────────────────────────────── */}
      <section>
        <SectionHeader
          title="dbt Test Pass Rate (30 days)"
          subtitle="Percentage of schema/data quality tests that passed. Any drop below 100% means a data contract was broken."
        />
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <TestPassRateChart rows={testsRows} />
        </div>
      </section>

      {/* ── dbt runtime ─────────────────────────────────────────────────── */}
      <section>
        <SectionHeader
          title="dbt Runtime per Run (30 days)"
          subtitle="Total wall-clock seconds across all models. Red = models failed, amber = > 10 min, blue = normal."
        />
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <RuntimeChart rows={runtimeRows} />
        </div>
      </section>

      {/* ── Footer ──────────────────────────────────────────────────────── */}
      <footer className="text-center text-xs text-slate-400 pb-4">
        Powered by{" "}
        <a
          href="https://github.com/anuar-git/cdmx-mobility"
          className="underline hover:text-slate-600"
          target="_blank"
          rel="noreferrer"
        >
          cdmx-mobility
        </a>{" "}
        · data from{" "}
        <a
          href="https://datos.cdmx.gob.mx"
          className="underline hover:text-slate-600"
          target="_blank"
          rel="noreferrer"
        >
          datos.cdmx.gob.mx
        </a>
      </footer>
    </div>
  );
}
