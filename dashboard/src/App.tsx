import { useEffect, useMemo, useState } from "react";
import { align } from "./data";
import { nextPrimary } from "./insights";
import { useMonitor } from "./useMonitor";
import type { Selection } from "./types";
import type { DashboardView } from "./components/view";
import { pageFromHash, selectionQuery, type ProductPage } from "./navigation";
import ProductShell from "./components/ProductShell";
import OverviewPage from "./pages/OverviewPage";
import BuildingsPage from "./pages/BuildingsPage";
import AnalyticsPage from "./pages/AnalyticsPage";
import EventsPage from "./pages/EventsPage";
function selectionFromURL(): Selection {
  const p = new URLSearchParams(location.search);
  return {
    run: p.get("run") || "",
    building: p.get("building") || "",
    source: p.get("source") || "",
  };
}
export default function App() {
  const [selection, setSelection] = useState(selectionFromURL);
  const [hash, setHash] = useState(location.hash);
  const [windowSize, setWindowSize] = useState(144);
  const [detail, setDetail] = useState<string | null>(null);
  const monitor = useMonitor(selection, windowSize);
  const { data } = monitor;
  useEffect(() => {
    const changed = () => setHash(location.hash);
    const popped = () => {
      setSelection(selectionFromURL());
      setDetail(null);
      changed();
    };
    window.addEventListener("hashchange", changed);
    window.addEventListener("popstate", popped);
    return () => {
      window.removeEventListener("hashchange", changed);
      window.removeEventListener("popstate", popped);
    };
  }, []);
  const page = pageFromHash(hash);
  useEffect(() => {
    if (hash !== "#models" && hash !== "#detectors") {
      document.getElementById("page-title")?.focus({ preventScroll: true });
      window.scrollTo(0, 0);
    }
  }, [hash]);
  const chart = useMemo(
    () => (data ? align(data.measurements, data.forecasts, data.basis) : []),
    [data],
  );
  const latest = data?.measurements[0];
  const intervalSeconds =
    latest?.interval_seconds ??
    data?.sources.find(
      (s) =>
        s.source_id === data.selection.source &&
        s.building_id === data.selection.building,
    )?.interval_seconds ??
    600;
  const chosen = data?.selection ?? selection;
  const choose = (next: Selection) => {
    setSelection(next);
    setDetail(null);
    history.pushState(null, "", selectionQuery(next, location.hash));
  };
  const navigate = (next: ProductPage) => {
    location.hash = next;
    window.scrollTo(0, 0);
  };
  const view: DashboardView = {
    ...monitor,
    chosen,
    choose,
    buildings: [...new Set(data?.sources.map((s) => s.building_id) ?? [])],
    chart,
    latest,
    next: data ? nextPrimary(latest, data.forecasts, data.basis) : undefined,
    actualUnit:
      intervalSeconds === 600 ? "Wh / 10 хв" : `Wh / ${intervalSeconds} с`,
    intervalSeconds,
    windowSize,
    setWindowSize,
    detailRow: chart.find((p) => p.measurement?.measurement_id === detail),
    setDetail,
  };
  return (
    <ProductShell page={page} view={view}>
      {page === "overview" ? (
        <OverviewPage view={view} navigate={navigate} />
      ) : page === "buildings" ? (
        <BuildingsPage view={view} navigate={navigate} />
      ) : page === "analytics" ? (
        <AnalyticsPage
          view={view}
          legacyAdvanced={hash === "#models" || hash === "#detectors"}
        />
      ) : (
        <EventsPage view={view} />
      )}
    </ProductShell>
  );
}
