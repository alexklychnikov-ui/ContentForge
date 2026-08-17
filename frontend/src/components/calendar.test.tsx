import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MonthGrid } from "../components/MonthGrid";
import type { PlanItemPublic } from "../api/types";

const item: PlanItemPublic = {
  id: "slot-1",
  plan_id: "plan-1",
  date: "2026-01-15",
  channel_type: "telegram",
  content_type: "social_post",
  theme: "Тема",
  goal: "awareness",
  hook: "хук",
  content_piece_id: null,
  sort_order: 0,
};

describe("SCR-CAL month grid", () => {
  it("selects a day by click, not drag", async () => {
    const user = userEvent.setup();
    const onSelectDate = vi.fn();
    render(
      <MonthGrid
        year={2026}
        month={1}
        items={[item]}
        selectedDate={null}
        onSelectDate={onSelectDate}
      />,
    );
    expect(screen.getByTestId("month-grid")).toBeInTheDocument();
    const day = screen.getByRole("button", { name: /15/ });
    expect(day).toHaveAttribute("draggable", "false");
    expect(day.querySelector("[draggable='true']")).toBeNull();
    await user.click(day);
    expect(onSelectDate).toHaveBeenCalledWith("2026-01-15");
    expect(screen.getByText("Telegram")).toBeInTheDocument();
  });
});
