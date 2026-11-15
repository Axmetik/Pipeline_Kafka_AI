import type { DashboardView } from "./view";
import { label } from "../data";
export default function DemoStatus({ view }: { view: DashboardView }) {
  const { data, connection, newMeasurements, latest } = view;
  return (
    <section className="card demo-status" data-testid="demo-status">
      <div>
        <h3>Демонстраційний запуск</h3>
        <p>
          <b>Стан відтворення невідомий</b> · Оброблено у запуску:{" "}
          {data?.status.unique_measurements ?? "—"} вимірювань.
        </p>
      </div>
      <p>
        Остання транзакція (реальний час, UTC):{" "}
        {label(data?.status.last_processed_at)}
        <br />
        Надходження останнього видимого вимірювання (UTC):{" "}
        {label(latest?.received_at)}
        <br />
        {connection !== "online"
          ? "Нові надходження зараз не перевірено."
          : newMeasurements === null
            ? "Очікуємо два оновлення для порівняння надходжень."
            : `Між останніми двома успішними оновленнями API: +${newMeasurements} вимірювань у запуску.`}
        <br />
        API не повідомляє стан producer або очікувану кількість. Незмінні
        лічильники не підтверджують завершення replay.
      </p>
    </section>
  );
}
