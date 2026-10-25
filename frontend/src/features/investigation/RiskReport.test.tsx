import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { RiskReport } from "./RiskReport";
import type { Report } from "../../api/client";

const REPORT: Report = {
  target: "@money_fast",
  category: "Investment Fraud",
  risk_score: 84,
  threat_level: "HIGH",
  findings: ["отсутствие лицензии", "реферальная система"],
  links: { accounts: 14, sites: 3, wallets: 2 },
};

describe("RiskReport", () => {
  it("shows target, threat level, findings and link counts", () => {
    render(<RiskReport report={REPORT} />);
    expect(screen.getByText("@money_fast")).toBeInTheDocument();
    expect(screen.getByText("HIGH")).toBeInTheDocument();
    expect(screen.getByText("отсутствие лицензии")).toBeInTheDocument();
    expect(screen.getByText("14")).toBeInTheDocument();   // accounts
    expect(screen.getByText("Key findings · 2")).toBeInTheDocument();
  });
});
