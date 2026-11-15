import type { DashboardView } from "./view";
import { label } from "../data";
export default function PipelineStatus({ view }: { view: DashboardView }) {
  const { data, next } = view;
  return (
    <section className="card pipeline">
      <div>
        <h3>Конвеєр обробки</h3>
        <p>
          Стан обробника: <b className="unknown">Невідомий</b> — checkpoint не
          доводить активність.
        </p>
        <p className="muted small">
          Лічильники всього запуску · стан зафіксованих транзакцій
        </p>
      </div>
      <div className="pipeline-metrics">
        <span>
          Записи прогнозів (HGB20 + RF21)
          <b data-testid="forecast-count">{data?.status.forecasts ?? "—"}</b>
        </span>
        <span>
          Записи оцінок (3 методи)
          <b data-testid="score-count">{data?.status.anomaly_scores ?? "—"}</b>
        </span>
        <span>
          Дублі
          <b data-testid="duplicate-count">
            {data?.status.duplicate_deliveries ?? "—"}
          </b>
        </span>
        <span>
          Відхилено
          <b data-testid="rejected-count">
            {data?.status.rejected_messages ?? "—"}
          </b>
        </span>
        <span>
          Наступна позиція обробки
          <b data-testid="checkpoint-next">
            {data?.status.checkpoints[0]?.next_offset ?? "—"}
          </b>
        </span>
      </div>
      <div className="last-processed">
        Остання транзакція (реальний час, UTC):{" "}
        {label(data?.status.last_processed_at)}
      </div>
      {!!data?.status.recent_errors.length && (
        <div className="notice">
          Останні помилки:{" "}
          {data.status.recent_errors.map((e) => e.kind).join(", ")}
        </div>
      )}
    </section>
  );
}
