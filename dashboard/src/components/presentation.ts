import type { Detector } from "../types";
export const chartTooltipStyle = {
  background: "var(--surface-secondary)",
  color: "var(--text)",
  border: "1px solid var(--border-strong)",
  borderRadius: 10,
  fontSize: 12,
};

export const detectors: {
  id: Detector;
  name: string;
  description: string;
  color: string;
}[] = [
  {
    id: "isolation_forest",
    name: "Isolation Forest",
    description: "Ізоляція незвичних спостережень",
    color: "var(--detector-if)",
  },
  {
    id: "autoencoder",
    name: "Autoencoder",
    description: "Помилка відновлення енергетичних ознак",
    color: "var(--detector-ae)",
  },
  {
    id: "residual",
    name: "Residual Detector",
    description: "Відхилення від окремого RF21-прогнозу",
    color: "var(--detector-residual)",
  },
];
export const statusName = (s: string) =>
  ({
    ready: "Готово",
    warmup: "Прогрів",
    incompatible: "Несумісне джерело",
    gap: "Пропуск історії",
  })[s] ?? s;
