import type { DashboardView } from "./view";
import { label } from "../data";
import { detectors } from "./presentation";
export default function EpisodeTable({ view }: { view: DashboardView }) {
  const { data } = view;
  return (
    <section id="events" className="card table-card">
      <div className="card-heading">
        <div>
          <h2>Історія експериментальних подій</h2>
          <p className="muted small">
            Останні 50 епізодів за весь вибраний запуск, будівлю та джерело · не
            лише видиме вікно. Це не підтверджені несправності.
          </p>
        </div>
        <span className="badge experimental" title="Експериментальний метод">
          experimental
        </span>
      </div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Початок / кінець зафіксованого перевищення</th>
              <th>Детектор</th>
              <th>Джерело</th>
              <th>Точок</th>
              <th>Стан епізоду</th>
            </tr>
          </thead>
          <tbody>
            {data?.events.map((e) => (
              <tr key={e.episode_id}>
                <td>
                  {label(e.start_timestamp)}
                  <small>{label(e.end_timestamp)}</small>
                </td>
                <td>
                  {detectors.find((d) => d.id === e.detector)?.name}
                  <details className="row-details">
                    <summary>Деталі</summary>
                    <span>Тип: experimental threshold exceedance</span>
                    <small>Модель: {e.model_version}</small>
                    <small>Поріг: {e.threshold_version}</small>
                    <small>
                      Це статистичний сигнал, а не підтверджена несправність.
                    </small>
                  </details>
                </td>
                <td>{data?.selection.source}</td>
                <td>{e.flagged_points}</td>
                <td>
                  <span
                    className={`status ${e.status === "open" ? "open" : ""}`}
                  >
                    {e.status === "open" ? "Відкритий" : "Завершений"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!data?.events.length && (
          <p className="table-empty">
            У завантаженій історії немає епізодів перевищення. Відсутність
            оцінок не означає відсутність відхилень.
          </p>
        )}
      </div>
      {data?.moreEvents && (
        <p className="muted small">
          Показано останні 50 подій. Повна історія доступна через cursor API.
        </p>
      )}
    </section>
  );
}
