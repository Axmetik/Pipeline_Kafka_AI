import type { EmailNotification } from "./types";
import { label } from "./data";

const names: Record<EmailNotification["status"], string> = {
  pending: "У черзі", sending: "Відправляється", sent: "Прийнято SMTP",
  retrying: "Повторна спроба", failed: "Помилка", suppressed: "Придушено",
};
export default function NotificationsPanel({ rows }: { rows?: EmailNotification[] }) {
  return <section className="card table-card" data-testid="email-notifications">
    <div className="card-heading"><h3>Email-сповіщення</h3><span className="badge experimental">experimental</span></div>
    <p className="muted">Останні 20 повідомлень вибраного джерела. Прийняття SMTP не гарантує прочитання листа чи фізичну несправність.</p>
    {!rows?.length ? <p>Сповіщень немає. Доставка вимкнена за замовчуванням; відсутність листів не означає відсутності аномалій.</p> :
      <div className="table-scroll"><table><thead><tr><th>Створено (UTC)</th><th>Тип / метод</th><th>Доставка</th><th>Епізод</th><th>Причина</th></tr></thead><tbody>
        {rows.map(r => <tr key={r.notification_id}><td>{label(r.created_at)}</td><td>{r.kind} / {r.method}</td><td>{names[r.status]} · {r.attempt_count} спроб</td><td title={r.episode_id}>{r.episode_id.slice(0, 12)}</td><td>{r.suppression_reason ?? r.error_category ?? "—"}</td></tr>)}
      </tbody></table></div>}
  </section>;
}
