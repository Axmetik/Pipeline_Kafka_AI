import type { Snapshot, HybridDecision } from "./types";
import { label } from "./data";

export function origins(inputs: string[]) {
  return (
    inputs
      .map((x) =>
        x === "residual"
          ? "Residual (відхилення від RF21)"
          : x === "sustained_high"
            ? "Sustained high (тривале підвищення)"
            : x,
      )
      .join(" + ") || "—"
  );
}
export function hybridText(row?: HybridDecision) {
  if (!row || row.flag === null)
    return "Недоступно — немає повного рішення для цього інтервалу";
  if (!row.flag) return "Відхилення немає за обома доступними входами";
  return "Експериментальний сигнал: " + origins(row.triggered_inputs);
}
function availability(status?: string) {
  if (status === "not_connected")
    return "Канал вимкнений / не підключений: опційні таблиці відсутні";
  if (status === "no_data")
    return "Немає збережених даних: канал може бути вимкнений або очікувати вимірювання";
  if (!status) return "Очікуємо дані каналу";
  return "Збережені результати; поточний стан увімкнення Worker невідомий";
}
export default function RulePanel({
  data,
  events = false,
}: {
  data: Pick<
    Snapshot,
    "measurements" | "ruleAssessments" | "hybridDecisions" | "hybridEvents"
  > | null;
  events?: boolean;
}) {
  const latest = data?.measurements[0]?.measurement_id;
  const row = data?.hybridDecisions?.items.find(
    (x) => x.measurement_id === latest,
  );
  const rules = data?.ruleAssessments?.items ?? [];
  const currentHigh = rules.find(
    (x) => x.measurement_id === latest && x.rule === "sustained_high",
  );
  const qualityWindow = rules.filter(
    (x) =>
      x.category === "telemetry_quality" &&
      (x.flag !== false || x.measurement_id === latest),
  );
  const quality = qualityWindow.slice(0, 6);
  const ep = data?.hybridEvents;
  if (events)
    return (
      <section className="card table-card" data-testid="hybrid-events">
        <div className="card-heading">
          <h2>Епізоди Residual OR Sustained high</h2>
          <span className="badge experimental">experimental</span>
        </div>
        <p className="muted small">
          {availability(ep?.channel_status)}. Останні 50 епізодів вибраного
          запуску, будівлі та джерела. Це не підтверджені несправності.
        </p>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Початок / останній сигнал</th>
                <th>Походження за весь епізод</th>
                <th>Точок</th>
                <th>Стан / версія</th>
              </tr>
            </thead>
            <tbody>
              {ep?.items.map((e) => (
                <tr key={e.episode_id}>
                  <td>
                    {label(e.start_timestamp)}
                    <small>{label(e.end_timestamp)}</small>
                  </td>
                  <td>{origins(e.triggered_inputs)}</td>
                  <td>{e.flagged_points}</td>
                  <td>
                    {e.status}
                    <small>
                      {e.closed_reason ?? "—"} · {e.layer_version}
                    </small>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!ep?.items.length && (
          <p className="table-empty">
            Збережених hybrid-епізодів немає. Це не негативне рішення детектора.
          </p>
        )}
        {ep?.next_cursor && (
          <p className="small muted">
            Повна історія доступна через cursor API.
          </p>
        )}
      </section>
    );
  return (
    <section className="card table-card" data-testid="rule-panel">
      <div className="card-heading">
        <h2>Residual OR Sustained high</h2>
        <span className="badge experimental">experimental</span>
      </div>
      <p className="muted small">
        {availability(data?.hybridDecisions?.channel_status)}
      </p>
      <p data-testid="hybrid-current">{hybridText(row)}</p>
      <p className="muted small">
        Інтервал: {label(data?.measurements[0]?.measurement_timestamp)} ·
        Покриття: {row?.coverage_count ?? "—"}/2 ·{" "}
        {row?.status ?? "unavailable"} · {row?.layer_version ?? "—"}
      </p>
      <p className="muted small">
        Residual: перевищення чинного порогу залишку RF21. Sustained high:
        кілька послідовних перевищень історичного погодинного порогу. Сигнал не
        підтверджує несправність.
      </p>
      {currentHigh && (
        <p className="small">
          Sustained high:{" "}
          {currentHigh.flag === null
            ? "Недоступно"
            : currentHigh.flag
              ? "Сигнал"
              : "Ще немає підтвердженого перевищення"}{" "}
          · {currentHigh.status} · контекст:{" "}
          {String(currentHigh.evidence.unavailable_reason ?? "доступний")} ·
          послідовність{" "}
          {String(currentHigh.evidence.consecutive_intervals ?? "—")}/
          {String(currentHigh.evidence.required_intervals ?? "—")} · поріг{" "}
          {String(currentHigh.evidence.threshold_wh ?? "—")} Wh
        </p>
      )}
      <h3>Якість телеметрії — окремі індикатори</h3>
      <p className="muted small">
        {availability(data?.ruleAssessments?.channel_status)}. Повторювані,
        зокрема нульові, показання можуть бути нормальними. Пропуск визначається
        після наступного запису; це не watchdog мовчання джерела.
      </p>
      <p className="muted small">
        Останні 6 індикаторів або недоступних оцінок із завантаженого вікна;
        також показано поточні негативні оцінки.
      </p>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Час датасету / правило</th>
              <th>Результат</th>
              <th>Пояснення / версія</th>
            </tr>
          </thead>
          <tbody>
            {quality.map((q) => (
              <tr key={q.assessment_id}>
                <td>
                  {label(q.measurement_timestamp)}
                  <small>{q.rule}</small>
                </td>
                <td>
                  {q.flag === null
                    ? "Недоступно"
                    : q.flag
                      ? "Індикатор якості"
                      : "Ознаки немає"}
                  <small>{q.status}</small>
                </td>
                <td>
                  {q.rule === "interval_gap"
                    ? `Пропущені інтервали: ${q.evidence.missing_intervals ?? "—"}; виявлено на наступному записі`
                    : `Повторення: вікно ${q.evidence.consecutive_intervals ?? "—"}/${q.evidence.required_intervals ?? "—"}; не діагноз несправності`}
                  <small>
                    {q.rule_version} · {q.activation}
                  </small>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!quality.length && (
        <p className="table-empty">
          У завантаженому вікні немає індикаторів якості; відсутні оцінки не
          вважаємо негативними.
        </p>
      )}
      {data?.ruleAssessments?.next_cursor && (
        <p className="small muted">
          Індикатори лише з обмеженого останнього вікна; повна історія доступна
          через API.
        </p>
      )}
    </section>
  );
}
