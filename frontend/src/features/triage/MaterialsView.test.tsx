import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ContentTriageItem } from "../../api/client";

const ITEMS: ContentTriageItem[] = [
  {
    id: 1, content_id: "v1", author: "@giv_shymkent", source: "instagram",
    url: "https://instagram.com/p/v1", score: 100, threat_level: "HIGH", track: "lottery", lang: "kk",
    breakdown: [
      { factor: "lottery.paid_entry", label: "Платное участие", kind: "signal", contribution: 40,
        quotes: [{ text: "Номер = 1000 тг", source: "caption", view: "base" }] },
      { factor: "lottery.random_draw", label: "Случайный выбор победителя", kind: "signal", contribution: 20, quotes: [] },
      { factor: "casino.gambling", label: "Азартные игры", kind: "signal", contribution: 0, quotes: [] },
      { factor: "gate.lottery", kind: "adjustment", contribution: -5, note: "Максимум шкалы — 100" },
    ],
    recommendation: "Высокий риск: приоритетная ручная проверка специалистом.",
    reach: { views: 1_200_000, likes: 45_000, comments: 800, shares: 1200 }, priority: 160,
    disposition: "pending", disposition_by: null,
  },
  {
    id: 2, content_id: "v2", author: "@halyk_news", source: "instagram", url: "", score: 0,
    threat_level: "LOW", track: "", breakdown: [], recommendation: "Низкий риск",
    reach: { views: 10, likes: 0, comments: 0, shares: 0 }, priority: 0, disposition: "pending", disposition_by: null,
  },
];

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return {
    ...actual,
    api: { getContentTriage: () => Promise.resolve(ITEMS), setContentDisposition: vi.fn() },
  };
});

function renderWithClient(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("MaterialsView", () => {
  it("shows track, Russian level and the signs that fired, hiding zero-contribution ones", async () => {
    const { MaterialsView } = await import("./MaterialsView");
    renderWithClient(<MaterialsView />);

    expect(await screen.findByText("@giv_shymkent")).toBeInTheDocument();
    expect(screen.getByText("100 · высокий")).toBeInTheDocument();
    expect(screen.getAllByText("Платный розыгрыш").length).toBeGreaterThan(0);
    expect(screen.getByText(/1\.2M/)).toBeInTheDocument();          // reach (охват) shown
    expect(screen.getByText("Платное участие")).toBeInTheDocument();
    expect(screen.queryByText("Азартные игры")).not.toBeInTheDocument();

    // «почему помечено» reveals the verbatim quote and the gate adjustment
    fireEvent.click(screen.getByText("почему помечено →"));
    expect(screen.getByText(/Номер = 1000 тг/)).toBeInTheDocument();
    expect(screen.getByText(/Максимум шкалы/)).toBeInTheDocument();
  });

  it("filters by track", async () => {
    const { MaterialsView } = await import("./MaterialsView");
    renderWithClient(<MaterialsView />);
    expect(await screen.findByText("@halyk_news")).toBeInTheDocument();
    fireEvent.click(screen.getAllByText("Платный розыгрыш")[0]);
    expect(screen.queryByText("@halyk_news")).not.toBeInTheDocument();
  });
});
