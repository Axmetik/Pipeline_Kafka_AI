import type { Dispatch, SetStateAction } from "react";
import type { Snapshot, Selection, Forecast, Measurement } from "../types";
import type { align } from "../data";
export interface DashboardView {
  data: Snapshot | null;
  connection: "loading" | "online" | "offline";
  updated: string | null;
  newMeasurements: number | null;
  chosen: Selection;
  choose: (selection: Selection) => void;
  buildings: string[];
  chart: ReturnType<typeof align>;
  latest: Measurement | undefined;
  next: Forecast | undefined;
  actualUnit: string;
  intervalSeconds: number;
  windowSize: number;
  setWindowSize: Dispatch<SetStateAction<number>>;
  detailRow: ReturnType<typeof align>[number] | undefined;
  setDetail: Dispatch<SetStateAction<string | null>>;
}
