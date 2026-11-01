import type { ReactNode } from "react";
import {
  Activity,
  ArrowUpRight,
  Building2,
  Database,
  Gauge,
  Layers,
  Leaf,
  Radio,
  ShieldCheck,
  WifiOff,
  Zap,
} from "lucide-react";
import SourceFilters from "./SourceFilters";
import type { DashboardView } from "./view";
import type { ProductPage } from "../navigation";
const pages = [
  {
    id: "overview",
    title: "Огляд",
    subtitle: "Споживання, прогнози та події вибраного об’єкта.",
    icon: Gauge,
  },
  {
    id: "buildings",
    title: "Будівлі",
    subtitle: "Портфель зареєстрованих будівель і джерел даних.",
    icon: Building2,
  },
  {
    id: "analytics",
    title: "Аналітика",
    subtitle: "Часові ряди, прогнози та експериментальне оцінювання.",
    icon: Activity,
  },
  {
    id: "events",
    title: "Події",
    subtitle: "Статистичні епізоди та історія доставки повідомлень.",
    icon: Layers,
  },
] as const;
export default function ProductShell({
  page,
  view,
  children,
}: {
  page: ProductPage;
  view: DashboardView;
  children: ReactNode;
}) {
  const current = pages.find((p) => p.id === page)!;
  const source = view.data?.sources.find(
    (s) =>
      s.building_id === view.chosen.building &&
      s.source_id === view.chosen.source,
  );
  return (
    <div className="app-shell product-shell">
      <aside className="sidebar">
        <a className="brand" href="#overview">
          <span className="brand-symbol">
            <Zap size={23} />
          </span>
          <span>
            Energy<span className="brand-sub">INTELLIGENCE</span>
          </span>
        </a>
        <div className="workspace-label">РОБОЧИЙ ПРОСТІР</div>
        <nav aria-label="Головна навігація">
          {pages.map(({ id, title, icon: Icon }) => (
            <a
              key={id}
              href={"#" + id}
              onClick={(event) => {
                if (location.hash === "#" + id) {
                  event.preventDefault();
                  document.getElementById("page-title")?.focus({ preventScroll: true });
                  window.scrollTo(0, 0);
                }
              }}
              className={id === page ? "active" : undefined}
              aria-current={id === page ? "page" : undefined}
            >
              <Icon size={18} />
              {title}
              {id === page && <span className="nav-dot" />}
            </a>
          ))}
        </nav>
        <div className="sidebar-note">
          <Leaf size={22} />
          <strong>Від даних до розуміння</strong>
          <p>
            Споживання, прогнозування та сигнали для обґрунтованого перегляду.
          </p>
          <span>ENERGY INTELLIGENCE · MVP</span>
        </div>
        <div className="local-label">
          <ShieldCheck size={15} />
          Локальне середовище
        </div>
      </aside>
      <main>
        <header className="topbar">
          <span>
            Робочий простір <span className="slash">/</span>
            <b>{current.title}</b>
          </span>
          <div className="header-context">
            <span className="run-context">
              <small>
                {source?.source_type === "dataset"
                  ? "Історичний replay"
                  : "Вибраний запуск"}
              </small>
              <code title={view.chosen.run}>
                {view.chosen.run || "Очікуємо запуск"}
              </code>
            </span>
            <span className="dataset-tag">
              <Database size={13} />
              {source?.source_type === "dataset"
                ? "Датасет / replay"
                : source?.source_type || "Тип джерела не вказано"}
            </span>
          </div>
        </header>
        <div className="page-heading">
          <div>
            <div className="eyebrow">
              ENERGY INTELLIGENCE / {page.toUpperCase()}
            </div>
            <h1 id="page-title" tabIndex={-1}>
              {current.title}
              <span>.</span>
            </h1>
            <p>{current.subtitle}</p>
          </div>
          <div
            className={"connection " + view.connection}
            role="status"
            data-testid="connection-status"
          >
            {view.connection === "offline" ? (
              <WifiOff size={15} />
            ) : (
              <Radio size={15} />
            )}
            <span>
              {view.connection === "online"
                ? "API на зв’язку"
                : view.connection === "offline"
                  ? "API недоступний"
                  : "Завантаження…"}
            </span>
          </div>
        </div>
        {view.connection === "offline" && (
          <div className="notice error" role="alert">
            Зв’язок із API втрачено.{" "}
            {view.data ? "Показуємо останні отримані дані. " : ""}Повторюємо
            підключення автоматично (до 30 с).
          </div>
        )}
        <SourceFilters view={view} />
        {children}
        <footer>
          ENERGY INTELLIGENCE
          <span>
            Дослідницький MVP · experimental оцінки не підтверджують фізичну
            несправність
          </span>
        </footer>
      </main>
    </div>
  );
}
