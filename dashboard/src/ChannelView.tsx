import { useState } from "react";
import {
  ArrowLeft,
  Lightbulb,
  Thermometer,
  Info,
  RefreshCw,
} from "lucide-react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { fetchJSON, label, valueLabel } from "./data";
import { chartTime } from "./insights";
import { sourceHref, navigate } from "./sourceData";
import { useResource } from "./useResource";
import type { ChannelSeries, Selection } from "./types";

export function channelSeriesURL(
  selection: Selection,
  channel: string,
  windowSize: number,
) {
  return (
    "/api/channel-series?" +
    new URLSearchParams({
      run_id: selection.run,
      building_id: selection.building,
      source_id: selection.source,
      channel_id: channel,
      limit: String(windowSize),
    })
  );
}
export default function ChannelView({
  selection,
  channel,
}: {
  selection: Selection;
  channel: string;
}) {
  const [windowSize, setWindowSize] = useState(144);
  const resource = useResource(
    JSON.stringify([selection, channel, windowSize]),
    (signal) =>
      fetchJSON<ChannelSeries>(
        channelSeriesURL(selection, channel, windowSize),
        signal,
      ),
    5000,
  );
  const data = resource.data,
    def = data?.definition,
    latest = data?.items[0];
  const zone = def?.category === "zones";
  const Icon = zone ? Thermometer : Lightbulb;
  const points = [...(data?.items ?? [])].reverse();
  return (
    <div className="channel-detail" data-testid="channel-detail">
      <a
        className="source-back"
        href={sourceHref("sources", selection)}
        onClick={(e) => {
          e.preventDefault();
          navigate(sourceHref("sources", selection));
        }}
      >
        <ArrowLeft size={16} />
        До каталогу
      </a>
      <div className="page-heading source-heading">
        <div>
          <div className="eyebrow">
            {zone
              ? "СЕНСОРИ ЗОН · ВИМІРЮВАЛЬНІ КАНАЛИ"
              : "ОСВІТЛЕННЯ · ІНТЕРВАЛЬНА ЕНЕРГІЯ"}
          </div>
          <h1>
            {def?.name ?? "Аналітика каналу"}
            <span>.</span>
          </h1>
          <p className="channel-identity">
            {selection.building} / {selection.source} / {channel}
          </p>
        </div>
        <span className="source-heading-icon">
          <Icon size={30} />
        </span>
      </div>
      <section className="card source-intro">
        <Info size={22} />
        <div>
          <strong>Графіки та описова статистика</strong>
          <p>
            Для цього каналу прогнозування, детектори, події та сповіщення не
            підключені. Моделі Appliances тут не застосовуються.
          </p>
        </div>
      </section>
      {resource.status === "offline" && (
        <div className="source-notice error" role="alert">
          <Info size={20} />
          <div>
            <strong>Не вдалося отримати дані API</strong>
            <p>
              {data ? "Показано останні отримані дані. " : ""}Підключення
              відновлюється автоматично.
            </p>
          </div>
          <button className="source-button secondary" onClick={resource.retry}>
            <RefreshCw size={16} />
            Повторити
          </button>
        </div>
      )}
      {resource.status === "loading" && (
        <div className="card source-empty" role="status">
          Завантаження вимірювань…
        </div>
      )}
      {data && !data.items.length && (
        <div className="card source-empty">
          <h2>Немає збережених вимірювань каналу</h2>
          <p>
            Перевірте запуск, будівлю та джерело. Відсутні значення не
            замінюються нулями.
          </p>
        </div>
      )}
      {latest && (
        <>
          <div className="channel-toolbar">
            <div>
              <span className="source-type">
                Історичні дані · активність джерела невідома
              </span>
              <p className="muted small">
                {latest.time_basis === "dataset_naive"
                  ? "Час датасету, часовий пояс не визначено"
                  : "Час джерела з явним часовим зміщенням"}
              </p>
            </div>
            <label>
              Вікно спостережень
              <select
                aria-label="Вікно каналу"
                value={windowSize}
                onChange={(e) => setWindowSize(Number(e.target.value))}
              >
                <option value={72}>Останні 72 інтервали</option>
                <option value={144}>Останні 144 інтервали</option>
                <option value={288}>Останні 288 інтервалів</option>
              </select>
            </label>
          </div>
          {def!.columns.map((column, i) => {
            const field = i === 0 ? "value" : "secondary_value",
              unit = def!.units[i],
              stats = data.statistics[i];
            const title = zone
              ? i === 0
                ? "Температура"
                : "Відносна вологість"
              : "Енергоспоживання освітлення";
            return (
              <section
                className="card channel-chart"
                key={column}
                data-testid={`metric-${column}`}
              >
                <div className="panel-heading">
                  <div>
                    <div className="eyebrow">
                      {column} · {unit}
                      {zone ? "" : " за 10 хвилин"}
                    </div>
                    <h2>{title}</h2>
                  </div>
                  <div className="channel-last">
                    <span>Останнє значення</span>
                    <strong>
                      {valueLabel(latest[field])}
                      <small> {unit}</small>
                    </strong>
                  </div>
                </div>
                <p className="muted small">
                  {label(points[0].measurement_timestamp)} —{" "}
                  {label(latest.measurement_timestamp)}
                </p>
                <div className="channel-plot">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart
                      data={points}
                      margin={{ top: 16, right: 20, left: 0, bottom: 8 }}
                    >
                      <CartesianGrid stroke="#ffffff09" vertical={false} />
                      <XAxis
                        dataKey="measurement_timestamp"
                        tickFormatter={chartTime}
                        minTickGap={52}
                        tick={{ fill: "#86878f", fontSize: 11 }}
                      />
                      <YAxis
                        width={55}
                        tick={{ fill: "#86878f", fontSize: 11 }}
                        domain={["auto", "auto"]}
                      />
                      <Tooltip
                        labelFormatter={(v) => label(String(v))}
                        formatter={(v) => [
                          `${valueLabel(typeof v === "number" ? v : null)} ${unit}`,
                          title,
                        ]}
                        contentStyle={{
                          background: "#222328",
                          border: "1px solid #3b3c42",
                          borderRadius: 12,
                        }}
                      />
                      <Line
                        dataKey={field}
                        name={title}
                        stroke={i === 0 ? "#c8ed87" : "#83b9ed"}
                        strokeWidth={2}
                        dot={false}
                        connectNulls={false}
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
                <div className="channel-stats">
                  {[
                    ["Мінімум", valueLabel(stats.minimum) + " " + unit],
                    ["Максимум", valueLabel(stats.maximum) + " " + unit],
                    ["Середнє", valueLabel(stats.mean) + " " + unit],
                    ["Спостережень", String(stats.count)],
                  ].map(([name, value]) => (
                    <div key={name}>
                      <span>{name}</span>
                      <strong>{value}</strong>
                    </div>
                  ))}
                </div>
                {stats.count < data.items.length && (
                  <p className="source-time-note">
                    Є відсутні вимірювання: {data.items.length - stats.count}.
                    Прогалини не заповнюються.
                  </p>
                )}
              </section>
            );
          })}
          <section className="card channel-provenance">
            <h2>Походження та контекст</h2>
            <p>
              Appliances Energy Prediction · UCI · колонки{" "}
              {def!.columns.join(" / ")}. Значення прочитані з архівних
              повідомлень цього джерела за часовими мітками, без генерації нових
              вимірювань.
            </p>
            <p>
              Статистика лише для показаного вікна.{" "}
              {zone
                ? "Температура та вологість мають окремі шкали. Картка зони не є паспортом фізичного пристрою."
                : "Wh — енергія за 600 секунд, а не миттєва потужність W."}
            </p>
            <p>
              Час вимірювання: {label(latest.measurement_timestamp)} ·
              Надходження: {latest.received_at} (операційний час).
            </p>
            <p className="channel-identity">
              Запуск: {selection.run} · Будівля: {selection.building} · Джерело:{" "}
              {selection.source}
            </p>
          </section>
        </>
      )}
    </div>
  );
}
