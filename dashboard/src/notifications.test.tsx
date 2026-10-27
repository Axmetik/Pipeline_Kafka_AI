import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import NotificationsPanel from "./NotificationsPanel";

afterEach(cleanup);
it("keeps empty email state distinct from proof of normal operation", () => {
  render(<NotificationsPanel rows={[]} />);
  expect(screen.getByText(/відсутність листів не означає/)).toBeTruthy();
  expect(screen.getByText("experimental")).toBeTruthy();
});
it("shows delivery status and suppression reason without interpreting scores", () => {
  render(<NotificationsPanel rows={[{ notification_id: "n1", episode_id: "e1", kind: "individual", method: "residual", created_at: "2026-10-27T10:00:00Z", status: "suppressed", attempt_count: 0, error_category: null, suppression_reason: "cooldown" }]} />);
  expect(screen.getByText(/Придушено/)).toBeTruthy();
  expect(screen.getByText("cooldown")).toBeTruthy();
  expect(screen.getByText("e1")).toBeTruthy();
});
