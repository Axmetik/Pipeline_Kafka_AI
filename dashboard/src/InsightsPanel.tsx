import { useMemo } from "react";
import { buildInsights } from "./insights";
import type { Snapshot } from "./types";

export default function Insights({
  data,
  offline,
}: {
  data: Snapshot | null;
  offline: boolean;
}) {
  const insights = useMemo(() => (data ? buildInsights(data) : null), [data]);
  return (
    <section
      className="card insights"
      data-testid="energy-insights"
      aria-labelledby="insights-heading"
    >
      <div className="card-heading">
        <h2 id="insights-heading">Інтелектуальний аналіз енергоспоживання</h2>
        <span className="subtle-tag">Прозорі правила</span>
      </div>
      {!insights ? (
        <p>Очікуємо дані для аналізу.</p>
      ) : (
        <>
          <p className="insights-context">
            Історичний replay · {data?.selection.building} /{" "}
            {data?.selection.source} · {data?.measurements.length} точок
            <br />
            Видиме вікно: {insights.window}
          </p>
          {offline && (
            <p className="notice">
              Висновки за останніми отриманими даними; зв’язок із API втрачено.
            </p>
          )}
          <ul className="insights-summary">
            {insights.summary.map((text) => (
              <li key={text}>{text}</li>
            ))}
          </ul>
          <details>
            <summary>Як сформовано висновки</summary>
            <div className="insights-details">
              <p data-testid="consumption-insight">
                {insights.consumption} {insights.trend}
              </p>
              <p data-testid="forecast-insight">{insights.forecast}</p>
              {insights.detectors.map((d) => (
                <p key={d.id} data-testid={`insight-${d.id}`}>
                  {d.text}
                </p>
              ))}
              <p>
                Усі детектори — experimental (експериментальні методи). Score не
                є ймовірністю; перевищення порога не підтверджує несправність.
                Історія епізодів нижче охоплює весь вибраний запуск і джерело, а
                не лише це вікно.
              </p>
            </div>
          </details>
        </>
      )}
    </section>
  );
}
