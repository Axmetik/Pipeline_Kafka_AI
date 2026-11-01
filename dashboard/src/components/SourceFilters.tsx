import type { DashboardView } from "./view";
import { label } from "../data";
export default function SourceFilters({ view }: { view: DashboardView }) {
  const { data, updated, chosen, choose, buildings } = view;
  return (
    <section className="filters card" aria-label="Вибір джерела">
      <label>
        Запуск replay
        <select
          aria-label="Запуск replay"
          value={chosen.run}
          onChange={(e) =>
            choose({ run: e.target.value, building: "", source: "" })
          }
        >
          <option value="">
            {data?.runs.length ? "Оберіть запуск" : "Очікуємо запуск"}
          </option>
          {data?.runs.map((r) => (
            <option key={r.run_id} value={r.run_id}>
              {r.run_id}
            </option>
          ))}
        </select>
      </label>
      <label>
        Будівля
        <select
          aria-label="Будівля"
          value={chosen.building}
          onChange={(e) =>
            choose({
              run: chosen.run,
              building: e.target.value,
              source: "",
            })
          }
        >
          <option value="">Оберіть будівлю</option>
          {buildings.map((b) => (
            <option key={b}>{b}</option>
          ))}
        </select>
      </label>
      <label>
        Джерело
        <select
          aria-label="Джерело"
          value={chosen.source}
          onChange={(e) => choose({ ...chosen, source: e.target.value })}
        >
          <option value="">Оберіть джерело</option>
          {data?.sources
            .filter((s) => s.building_id === chosen.building)
            .map((s) => (
              <option key={s.source_id}>{s.source_id}</option>
            ))}
        </select>
      </label>
      <div className="filter-info">
        <span className="live-dot" />
        Оновлення ≈ 2 с
        <small>
          {updated
            ? "API оновлено " + label(updated).slice(11, 19) + " UTC"
            : "З’єднуємося з PostgreSQL"}
        </small>
      </div>
    </section>
  );
}
