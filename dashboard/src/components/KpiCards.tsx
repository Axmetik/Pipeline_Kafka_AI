import type { DashboardView } from "./view";
import { label, valueLabel } from "../data";
import { finite } from "../insights";
import { statusName } from "./presentation";
import { Activity, ArrowUpRight, Database, Zap } from "lucide-react";
export default function KpiCards({ view }: { view: DashboardView }) {
  const { data, latest, next, actualUnit } = view;
  return (
    <section className="kpis">
      <article className="card kpi">
        <div className="kpi-top">
          Останнє споживання
          <Zap size={17} />
        </div>
        <strong>
          {valueLabel(latest?.energy_wh)}
          <small>{actualUnit}</small>
        </strong>
        <p>
          {latest
            ? label(latest.measurement_timestamp)
            : "Очікуємо вимірювання"}
        </p>
      </article>
      <article className="card kpi" data-testid="next-forecast">
        <div className="kpi-top">
          Прогноз наступного інтервалу
          <ArrowUpRight size={17} />
        </div>
        <strong>
          {valueLabel(
            next?.status === "ready" &&
              finite(next.predicted_energy_wh) &&
              next.predicted_energy_wh >= 0
              ? next.predicted_energy_wh
              : null,
          )}
          <small>Wh / 10 хв</small>
        </strong>
        <p>
          {next
            ? `HGB20 · ${statusName(next.status)}`
            : "HGB20 · Очікуємо прогноз"}
        </p>
        <p>Цільовий час: {label(next?.forecast_target_timestamp)}</p>
        <p>Від вимірювання: {label(next?.forecast_origin)}</p>
      </article>
      <article className="card kpi">
        <div className="kpi-top">
          Вимірювань у запуску
          <Database size={17} />
        </div>
        <strong data-testid="measurement-count">
          {data?.status.unique_measurements ?? "—"}
        </strong>
        <p>Усі джерела вибраного запуску · не лише ця будівля</p>
      </article>
      <article className="card kpi">
        <div className="kpi-top">
          Відкриті епізоди <Activity size={17} />
        </div>
        <strong>
          {data ? data.events.filter((e) => e.status === "open").length : "—"}
        </strong>
        <p>
          Індивідуальні · серед останніх 50 завантажених. Не підтверджені
          несправності.
        </p>
      </article>
    </section>
  );
}
