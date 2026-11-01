import { useState } from "react";
import { Layers, Mail, Activity } from "lucide-react";
import type { DashboardView } from "../components/view";
import EpisodeTable from "../components/EpisodeTable";
import CombinedPanel from "../CombinedPanel";
import NotificationsPanel from "../NotificationsPanel";
export default function EventsPage({ view }: { view: DashboardView }) {
  const [kind, setKind] = useState("all");
  const data = view.data;
  return (
    <div data-testid="page-events">
      <section className="card events-intro">
        <div>
          <span className="eyebrow">ІСТОРІЯ ТА УВАГА</span>
          <h2>Події обраного джерела</h2>
          <p className="muted">
            {view.chosen.building || "—"} / {view.chosen.source || "—"}
          </p>
          <p className="small muted">
            Епізоди перевищення статистичного порогу — experimental, не
            підтверджені несправності. Пріоритет фізичної несправності не
            визначено.
          </p>
        </div>
        <label className="event-filter">
          Тип історії
          <select
            aria-label="Тип історії"
            value={kind}
            onChange={(e) => setKind(e.target.value)}
          >
            <option value="all">Уся доступна історія</option>
            <option value="individual">Індивідуальні епізоди</option>
            <option value="combined">Комбіновані епізоди</option>
            <option value="email">Доставка Email</option>
          </select>
        </label>
      </section>
      <div className="event-summary">
        <article className="card">
          <Activity size={18} />
          <strong>{data ? data.events.length : "—"}</strong>
          <span>Індивідуальні епізоди</span>
          <small>Завантажено до 50 · не загальний підсумок</small>
        </article>
        <article className="card">
          <Layers size={18} />
          <strong>{data ? (data.combinedEvents?.length ?? 0) : "—"}</strong>
          <span>Комбіновані епізоди</span>
          <small>Завантажено до 50 · Unanimous</small>
        </article>
        <article className="card">
          <Mail size={18} />
          <strong>{data ? (data.notifications?.length ?? 0) : "—"}</strong>
          <span>Записи доставки</span>
          <small>Завантажено до 20 · не фізичні події</small>
        </article>
      </div>
      {(kind === "all" || kind === "individual") && (
        <>
          <p className="clock-note">
            Час епізодів:{" "}
            {data?.basis === "offset_aware"
              ? "час джерела з явним offset"
              : "час датасету, часовий пояс не визначено"}
            . Відкритий епізод — кандидат для перегляду, не встановлена аварія.
          </p>
          <EpisodeTable view={view} />
        </>
      )}
      {(kind === "all" || kind === "combined") && <CombinedPanel data={data} />}
      {(kind === "all" || kind === "email") && (
        <>
          <p className="clock-note">
            Історія доставки — окремий годинник UTC. Прийняття SMTP не
            підтверджує несправність і не гарантує прочитання листа.
          </p>
          <NotificationsPanel rows={data?.notifications} />
        </>
      )}
    </div>
  );
}
