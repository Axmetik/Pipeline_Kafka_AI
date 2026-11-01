import type { DashboardView } from "./view";
import { detectors } from "./presentation";
import { Box } from "lucide-react";
export default function ModelRegistry({ view }: { view: DashboardView }) {
  const { data } = view;
  return (
    <section id="models" className="card table-card">
      <div className="card-heading">
        <div>
          <h2>Реєстр моделей</h2>
          <p className="muted small">
            HGB20 — основний прогноз · RF21 — окремий reference для residual
            detector
          </p>
        </div>
        <Box size={19} />
      </div>
      <div className="model-grid">
        {data?.models.map((m) => (
          <article className="model" key={m.model_id}>
            <span className="model-role">
              {m.role === "primary_forecast"
                ? "HGB20 · основний прогноз"
                : m.role === "residual_reference"
                  ? "RF21 · residual reference"
                  : (detectors.find((d) => d.id === m.role)?.name ?? m.role)}
            </span>
            <span
              className={`badge ${m.maturity === "experimental" ? "experimental" : "existing"}`}
            >
              {m.maturity}
            </span>
            <code>{m.model_version}</code>
            <small>
              {m.feature_version} · {m.feature_names.length} ознак
            </small>
            {m.threshold_version && <small>Поріг: {m.threshold_version}</small>}
          </article>
        ))}
      </div>
      {!data?.models.length && (
        <p className="table-empty">
          Моделі з’являться після перших записаних прогнозів та оцінок.
        </p>
      )}
    </section>
  );
}
