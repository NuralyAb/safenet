import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MoneyFlowView } from "./MoneyFlow";
import type { MoneyFlow } from "../../api/client";

const FLOW: MoneyFlow = {
  account: "@scam",
  nodes: [
    { id: "@scam", type: "account" },
    { id: "0xdead000000000000000000000000000000000001", type: "wallet" },
    { id: "0x28c6c06298d514db089934071355e5743bf21d60", type: "exchange" },
  ],
  edges: [
    { source: "@scam", target: "0xdead000000000000000000000000000000000001", label: "MENTIONS", chain: "ethereum" },
    { source: "0xdead000000000000000000000000000000000001", target: "0x28c6c06298d514db089934071355e5743bf21d60", label: "SENT_TO", exchange: "Binance" },
  ],
  boundary: { reached: "exchange", note: "Дальше — связь «кошелёк → банковский счёт» … обогащается данными АФМ." },
};

describe("MoneyFlowView", () => {
  it("renders account, wallet chain, exchange and the boundary note", () => {
    render(<MoneyFlowView flow={FLOW} />);
    expect(screen.getByText("@scam")).toBeInTheDocument();
    expect(screen.getByText(/ethereum/)).toBeInTheDocument();        // wallet chain label
    expect(screen.getByText(/банковский счёт/)).toBeInTheDocument(); // explicit boundary
    expect(screen.getByText(/обогащается данными/)).toBeInTheDocument();
  });

  it("shows a hint when no wallets are found", () => {
    render(<MoneyFlowView flow={{ ...FLOW, nodes: [{ id: "@x", type: "account" }], edges: [] }} />);
    expect(screen.getByText(/кошельки не найдены/)).toBeInTheDocument();
  });
});
