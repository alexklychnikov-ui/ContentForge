import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { cf } from "../api/cf";
import { pollJob } from "../api/client";

function PlanPollProbe() {
  const [status, setStatus] = useState("");
  const [planId, setPlanId] = useState("");
  return (
    <div>
      <button
        type="button"
        onClick={async () => {
          const accepted = await cf.generatePlan("brand-1", {
            year: 2026,
            month: 1,
            channels: ["telegram"],
            targets: { social_post: 4 },
          });
          const job = await pollJob(accepted.job_id, (id) => cf.job(id), {
            intervalMs: 1,
            maxTicks: 10,
          });
          setStatus(job.status);
          setPlanId(String(job.result?.plan_id ?? ""));
        }}
      >
        generate
      </button>
      <div data-testid="job-status">{status}</div>
      <div data-testid="plan-id">{planId}</div>
    </div>
  );
}

describe("plan generate polling", () => {
  it("polls 202 job until succeeded", async () => {
    const user = userEvent.setup();
    let ticks = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/plans/generate")) {
          return {
            ok: true,
            status: 202,
            text: async () => JSON.stringify({ job_id: "job-1" }),
          };
        }
        if (url.includes("/jobs/job-1")) {
          ticks += 1;
          const status = ticks < 3 ? (ticks === 1 ? "queued" : "running") : "succeeded";
          return {
            ok: true,
            status: 200,
            text: async () =>
              JSON.stringify({
                id: "job-1",
                type: "generate_plan",
                status,
                result: status === "succeeded" ? { plan_id: "plan-9" } : null,
                error: null,
                created_at: "2026-01-01T00:00:00Z",
              }),
          };
        }
        return { ok: false, status: 404, text: async () => "" };
      }),
    );
    render(<PlanPollProbe />);
    await user.click(screen.getByRole("button", { name: "generate" }));
    expect(await screen.findByTestId("job-status")).toHaveTextContent("succeeded");
    expect(screen.getByTestId("plan-id")).toHaveTextContent("plan-9");
    expect(ticks).toBeGreaterThanOrEqual(3);
  });
});
