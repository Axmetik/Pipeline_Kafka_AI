import type { CombinedDecision } from "./types";
const names: Record<string, string> = {
  isolation_forest: "Isolation Forest",
  autoencoder: "Autoencoder",
  residual: "Residual Detector",
};
export const methodNames = (methods: string[]) =>
  methods.map((m) => names[m] || m).join(", ");
export function combinedText(decision: CombinedDecision | undefined): string {
  if (!decision)
    return "Для поточного вимірювання збережене комбіноване рішення недоступне. Для історичних запусків воно могло не обчислюватися.";
  if (
    decision.status !== "ready" ||
    decision.trigger_count === null ||
    decision.flag === null ||
    decision.coverage_count !== 3
  )
    return `Неповне покриття: готові ${decision.coverage_count} із 3 методів (${decision.status}); серед доступних є ${decision.available_trigger_count} перевищень. Повне рішення недоступне, це не 0 із 3.`;
  const count = decision.trigger_count;
  const level = [
    "Перевищень не зафіксовано",
    "Низький рівень узгодження: інформаційний сигнал одного методу",
    "Узгоджений сигнал двох методів",
    "Узгоджений сигнал трьох методів",
  ][count];
  return `${count} із 3 · ${level}. ${count ? "Методи: " + methodNames(decision.triggered_methods) + ". " : ""}${decision.flag ? "Правило комбінування спрацювало." : "Правило комбінування не спрацювало."} Це узгодження експериментальних методів, не ймовірність або фізична тяжкість несправності.`;
}
