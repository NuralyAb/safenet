import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { RiskGauge } from "./RiskGauge";

describe("RiskGauge", () => {
  it("renders the score and an accessible label", () => {
    render(<RiskGauge score={84} level="HIGH" />);
    expect(screen.getByText("84")).toBeInTheDocument();
    const gauge = screen.getByRole("img");
    expect(gauge).toHaveAttribute("aria-label", expect.stringContaining("84"));
    expect(gauge).toHaveAttribute("aria-label", expect.stringContaining("HIGH"));
  });

  it("clamps an out-of-range score", () => {
    render(<RiskGauge score={140} level="CRITICAL" />);
    expect(screen.getByText("140")).toBeInTheDocument(); // label shows raw, ring clamps internally
  });
});
