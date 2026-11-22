import { Building2, ArrowUpRight, Database, RefreshCw } from "lucide-react";
import { usePortfolio } from "../usePortfolio";
import type { DashboardView } from "../components/view";
import type { ProductPage } from "../navigation";
export default function BuildingsPage({
  view,
  navigate,
}: {
  view: DashboardView;
  navigate: (page: ProductPage) => void;
}) {
  const portfolio = usePortfolio(view.chosen.run);
  const buildings = [...new Set(portfolio.sources.map((s) => s.building_id))];
  return (
    <div data-testid="page-buildings">
      <section className="card portfolio-intro">
        <div>
          <span className="eyebrow">ПОРТФЕЛЬ ОБ’ЄКТІВ</span>
          <h2>Будівлі та джерела вимірювань</h2>
          <p className="muted">
            Зареєстровані джерела. Назви будівель показано за їхніми
            ідентифікаторами; адресу та інші характеристики не задано.
          </p>
          <p className="small muted">
            Прогнозування доступне лише для сумісної моделі й джерела. Наявність
            будівлі в портфелі не означає сумісність з поточними ML artifacts.
          </p>
        </div>
        <button
          className="action-button"
          onClick={portfolio.retry}
          disabled={portfolio.status === "loading"}
        >
          <RefreshCw size={15} />
          Оновити портфель
        </button>
      </section>
      {portfolio.status === "loading" && (
        <div className="card page-state" role="status">
          Завантажуємо портфель будівель…
        </div>
      )}
      {portfolio.status === "error" && (
        <div className="notice error" role="alert">
          Не вдалося завантажити портфель. Спробуйте оновити його. Поточні дані
          моніторингу доступні в інших розділах.
        </div>
      )}
      {portfolio.truncated && (
        <p className="notice">
          Показано перші 1000 джерел каталогу. Це не повний портфель; інші
          записи доступні через cursor API.
        </p>
      )}
      {portfolio.status === "ready" && !buildings.length && (
        <div className="card page-state" data-testid="portfolio-empty">
          <Building2 size={28} />
          <h2>Будівлі ще не зареєстровані</h2>
          <p>
            Зареєстровані джерела з’являться після надходження вимірювань.
            Демонстраційні будівлі не створюються автоматично.
          </p>
        </div>
      )}
      <div className="building-grid">
        {buildings.map((id) => (
          <section
            className={
              "card building-card" +
              (id === view.chosen.building ? " selected-building" : "")
            }
            key={id}
            data-testid="building-card"
          >
            <div className="card-heading">
              <span className="building-icon">
                <Building2 size={25} />
              </span>
              <span className="subtle-tag">
                {id === view.chosen.building ? "Обрано" : "Зареєстровано"}
              </span>
            </div>
            <h2>{id}</h2>
            <p className="muted small">
              Ідентифікатор будівлі ·{" "}
              {portfolio.sources.filter((s) => s.building_id === id).length}{" "}
              джерел
            </p>
            <div className="building-sources">
              {portfolio.sources
                .filter((s) => s.building_id === id)
                .map((source) => {
                  const inRun = !!view.data?.sources.some(
                    (s) =>
                      s.building_id === id && s.source_id === source.source_id,
                  );
                  const selected =
                    id === view.chosen.building &&
                    source.source_id === view.chosen.source;
                  const measured = selected ? view.latest : undefined;
                  return (
                    <article className="source-row" key={source.source_id}>
                      <div className="source-name">
                        <Database size={16} />
                        <b>{source.source_id}</b>
                      </div>
                      <dl>
                        <dt>Тип</dt>
                        <dd>
                          {source.source_type === "dataset"
                            ? "Датасет / історичний replay"
                            : source.source_type === "smart_meter"
                              ? "Smart meter (тип джерела)"
                              : source.source_type || "Не вказано"}
                        </dd>
                        <dt>Обсяг обліку</dt>
                        <dd>
                          {source.energy_scope === "appliances"
                            ? "Побутові прилади"
                            : source.energy_scope || "Не вказано"}
                        </dd>
                        <dt>Інтервал</dt>
                        <dd>
                          {source.interval_seconds
                            ? `${source.interval_seconds} с`
                            : "Не вказано"}
                        </dd>
                        <dt>Часовий пояс</dt>
                        <dd>{source.timezone || "Не визначено"}</dd>
                        <dt>Модель</dt>
                        <dd>
                          {measured?.feature_status === "incompatible"
                            ? "Несумісне джерело"
                            : measured?.feature_status === "warmup"
                              ? "Прогрів часової історії"
                              : measured?.feature_status === "ready"
                                ? "Ознаки готові; окремі моделі можуть бути в прогріві"
                                : "Сумісність ще не перевірена"}
                        </dd>
                      </dl>
                      {!inRun && (
                        <p className="small muted">
                          У вибраному запуску вимірювань цього джерела немає.
                          Доступність даних в інших запусках не перевірена.
                        </p>
                      )}
                      {selected && !view.data?.measurements.length && (
                        <p className="small muted">
                          Немає доступних вимірювань для обраного джерела.
                        </p>
                      )}
                      {measured?.feature_status === "incompatible" && (
                        <p className="notice">
                          Споживання можна переглядати; поточна прогнозна модель
                          не застосовується до цього джерела.
                        </p>
                      )}
                      <button
                        className="action-button"
                        disabled={!inRun}
                        onClick={() => {
                          view.choose({
                            run: view.chosen.run,
                            building: id,
                            source: source.source_id,
                          });
                          navigate("analytics");
                        }}
                        aria-label={`Відкрити ${id} / ${source.source_id}`}
                      >
                        Відкрити аналітику <ArrowUpRight size={14} />
                      </button>
                    </article>
                  );
                })}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
