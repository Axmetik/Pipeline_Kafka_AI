import { useEffect, useState } from "react";
import { Activity, SlidersHorizontal } from "lucide-react";
import type { DashboardView } from "../components/view";
import KpiCards from "../components/KpiCards";
import ForecastChart from "../components/ForecastChart";
import MeasurementTable from "../components/MeasurementTable";
import PipelineStatus from "../components/PipelineStatus";
import DemoStatus from "../components/DemoStatus";
import ModelRegistry from "../components/ModelRegistry";
import ScoreChart from "../components/ScoreChart";
import { detectors } from "../components/presentation";
import Insights from "../InsightsPanel";
import CombinedPanel from "../CombinedPanel";
export default function AnalyticsPage({
  view,
  legacyAdvanced,
}: {
  view: DashboardView;
  legacyAdvanced: boolean;
}) {
  const [expanded, setExpanded] = useState(legacyAdvanced);
  useEffect(() => {
    if (legacyAdvanced) setExpanded(true);
  }, [legacyAdvanced]);
  useEffect(() => {
    if (expanded && legacyAdvanced)
      document
        .getElementById(location.hash.slice(1))
        ?.scrollIntoView({ block: "start" });
  }, [expanded, legacyAdvanced]);
  return (
    <div data-testid="page-analytics">
      <KpiCards view={view} />
      <ForecastChart view={view} />
      <Insights data={view.data} offline={view.connection === "offline"} />
      <MeasurementTable view={view} />
      <details
        className="card advanced"
        data-testid="advanced-analytics"
        open={expanded}
        onToggle={(e) => setExpanded(e.currentTarget.open)}
      >
        <summary>
          <SlidersHorizontal size={18} />
          <span>
            <b>Розширена аналітика та діагностика</b>
            <small>Experimental scores, моделі, пороги та стан конвеєра</small>
          </span>
        </summary>
        {expanded && (
          <div className="advanced-body">
            <DemoStatus view={view} />
            <section id="detectors" className="section-heading">
              <div>
                <h2>Експериментальні детектори</h2>
                <p>
                  Score не є ймовірністю. Перевищення порогу не підтверджує
                  несправність.
                </p>
              </div>
              <span className="subtle-tag">3 незалежні шкали</span>
            </section>
            <div className="detector-grid">
              {detectors.map((d) => (
                <ScoreChart
                  key={d.id}
                  detector={d}
                  rows={
                    view.data?.scores.filter((s) => s.detector === d.id) ?? []
                  }
                />
              ))}
            </div>
            <CombinedPanel data={view.data} />
            <PipelineStatus view={view} />
            <ModelRegistry view={view} />
          </div>
        )}
      </details>
    </div>
  );
}
