import type { DashboardView } from "./view";
import { label, valueLabel } from "../data";
export default function MeasurementTable({ view }: { view: DashboardView }) {
  const { data, chart, actualUnit, detailRow, setDetail } = view;
  return (
    <section className="card table-card">
      <div className="card-heading">
        <div>
          <h2>Останні вимірювання</h2>
          <p className="muted small">
            HGB20 для часу вимірювання у рядку. Верхня картка показує наступний
            інтервал; тому значення можуть відрізнятися.
          </p>
        </div>
        <span className="subtle-tag">{actualUnit}</span>
      </div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Час вимірювання</th>
              <th>Факт, Wh</th>
              <th>HGB20, Wh</th>
              <th>Деталі</th>
            </tr>
          </thead>
          <tbody>
            {chart
              .filter((p) => p.measurement)
              .slice(-5)
              .reverse()
              .map((p) => (
                <tr key={p.timestamp}>
                  <td>{label(p.timestamp)}</td>
                  <td>{valueLabel(p.actual)}</td>
                  <td>{valueLabel(p.forecast)}</td>
                  <td>
                    <button
                      className="text-button"
                      onClick={() => setDetail(p.measurement!.measurement_id)}
                    >
                      Переглянути ↗
                    </button>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
      {detailRow && (
        <div className="details" data-testid="measurement-detail">
          <b>Часові мітки запису</b>
          <dl>
            <dt>Час вимірювання (джерело)</dt>
            <dd>{label(detailRow.timestamp)}</dd>
            <dt>Надходження повідомлення (UTC)</dt>
            <dd>{label(detailRow.measurement?.received_at)}</dd>
            <dt>Час вимірювання для прогнозу (origin)</dt>
            <dd>{label(detailRow.prediction?.forecast_origin)}</dd>
            <dt>Цільовий час прогнозу (target)</dt>
            <dd>{label(detailRow.prediction?.forecast_target_timestamp)}</dd>
            <dt>Формування прогнозу (UTC)</dt>
            <dd>{label(detailRow.prediction?.generated_at)}</dd>
            <dt>Версія прогнозної моделі</dt>
            <dd>{detailRow.prediction?.model_version ?? "—"}</dd>
          </dl>
        </div>
      )}
    </section>
  );
}
