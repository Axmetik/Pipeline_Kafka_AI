import type { Snapshot } from "./types";
import { label } from "./data";
import { combinedText, methodNames } from "./combined";
export default function CombinedPanel({ data }: { data: Snapshot | null }) {
  const current = data?.combined?.find(
    (d) => d.measurement_id === data.measurements[0]?.measurement_id,
  );
  return (
    <section className="card table-card" data-testid="combined-panel">
      <div className="card-heading">
        <h2>Комбінована оцінка аномальності</h2>
        <span className="badge experimental">experimental</span>
      </div>
      <p data-testid="combined-current">{combinedText(current)}</p>
      <p className="muted small">
        Поточний інтервал: {label(data?.measurements[0]?.measurement_timestamp)}{" "}
        · Правило: {current?.rule_version ?? "—"} · Покриття:{" "}
        {current?.coverage_count ?? "—"}/3
      </p>
      <p className="muted small">
        Unanimous потребує 3 із 3 готових спрацювань. Вибір за validation не
        доводить операційну якість. Історія нижче — останні 50 комбінованих
        епізодів за весь вибраний запуск, будівлю та джерело.
      </p>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Початок / останнє перевищення</th>
              <th>Максимальне одночасне узгодження</th>
              <th>Методи за весь епізод</th>
              <th>Вимірювань</th>
              <th>Стан / версія</th>
            </tr>
          </thead>
          <tbody>
            {data?.combinedEvents?.map((e) => (
              <tr key={e.episode_id}>
                <td>
                  {label(e.start_timestamp)}
                  <small>{label(e.end_timestamp)}</small>
                </td>
                <td>
                  {e.max_trigger_count}/3
                  <small>Останнє: {e.last_trigger_count}/3</small>
                </td>
                <td>{methodNames(e.triggered_methods)}</td>
                <td>{e.flagged_points}</td>
                <td>
                  {e.status}
                  <small>
                    {e.rule_version} · {e.closed_reason ?? "—"}
                  </small>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!data?.combinedEvents?.length && (
        <p className="table-empty">
          Збережених комбінованих епізодів немає. Це не підтвердження
          відсутності відхилень.
        </p>
      )}
      {data?.moreCombinedEvents && (
        <p className="small muted">Повна історія доступна через cursor API.</p>
      )}
    </section>
  );
}
