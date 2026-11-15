import { ArrowUpRight, Database, Layers } from "lucide-react";
import type { DashboardView } from "../components/view";
import KpiCards from "../components/KpiCards";
import ForecastChart from "../components/ForecastChart";
import MeasurementTable from "../components/MeasurementTable";
import Insights from "../InsightsPanel";
import { label } from "../data";
import { detectorNames } from "../insights";
import type { ProductPage } from "../navigation";
export default function OverviewPage({
  view,
  navigate,
}: {
  view: DashboardView;
  navigate: (page: ProductPage) => void;
}) {
  const { data, chosen, connection } = view;
  const scope = data?.sources.find(
    (s) => s.building_id === chosen.building && s.source_id === chosen.source,
  )?.energy_scope;
  return (
    <div data-testid="page-overview">
      <KpiCards view={view} />
      <div className="overview-grid">
        <section className="card context-card">
          <div className="section-icon">
            <Database size={19} />
          </div>
          <div>
            <span className="eyebrow">ВИБРАНИЙ ОБ’ЄКТ</span>
            <h2>{chosen.building || "Будівлю ще не вибрано"}</h2>
            <p className="muted">Джерело: {chosen.source || "—"}</p>
            <p className="small muted">
              {data?.measurements.length ?? 0} вимірювань у видимому вікні.
              Показані графіки й висновки стосуються цього джерела.
            </p>
            <p className="small muted">
              Обсяг обліку:{" "}
              {scope === "appliances"
                ? "побутові прилади (не вся енергія будівлі)"
                : scope || "не вказано"}
              .
            </p>
            <button
              className="text-button"
              onClick={() => navigate("buildings")}
            >
              До портфеля будівель <ArrowUpRight size={14} />
            </button>
          </div>
        </section>
        <section className="card attention-card">
          <div className="card-heading">
            <h2>Події для перегляду</h2>
            <Layers size={18} />
          </div>
          <p className="small muted">
            Статистичні перевищення та історія доставки, а не підтверджені
            несправності.
          </p>
          {data?.events.length ? (
            <ul className="attention-list">
              {data.events.slice(0, 2).map((e) => (
                <li key={e.episode_id}>
                  <span>
                    {detectorNames[e.detector]} ·{" "}
                    {e.status === "open"
                      ? "Епізод відкритий"
                      : "Епізод завершено"}
                  </span>
                  <small>{label(e.start_timestamp)}</small>
                </li>
              ))}
            </ul>
          ) : (
            <p className="table-empty">
              {data
                ? "У завантаженій історії індивідуальних епізодів немає."
                : "Очікуємо історію подій."}
            </p>
          )}
          <button className="text-button" onClick={() => navigate("events")}>
            Переглянути події <ArrowUpRight size={14} />
          </button>
        </section>
      </div>
      <ForecastChart view={view} />
      <div className="section-heading">
        <div>
          <h2>Розуміння споживання</h2>
          <p>Описові висновки з доступних вимірювань і прогнозів.</p>
        </div>
        <button className="action-button" onClick={() => navigate("analytics")}>
          Детальна аналітика <ArrowUpRight size={15} />
        </button>
      </div>
      <Insights data={data} offline={connection === "offline"} />
      <MeasurementTable view={view} />
    </div>
  );
}
