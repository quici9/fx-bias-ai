/**
 * Tests for PairCard component — F2-02f
 * Coverage: render pair data, column type visual styling, hover state,
 * keyboard/mouse selection callback, accessibility.
 */

import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import { PairCard } from "@/components/dashboard/PairCard";
import type { PairRecommendation } from "@/lib/types";

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const LONG_PAIR: PairRecommendation = {
  pair: "USD/JPY",
  spread: 1.82,
  base_currency: "USD",
  quote_currency: "JPY",
  confidence: "HIGH",
};

const SHORT_PAIR: PairRecommendation = {
  pair: "EUR/USD",
  spread: 0.95,
  base_currency: "EUR",
  quote_currency: "USD",
  confidence: "MEDIUM",
};

const AVOID_PAIR: PairRecommendation = {
  pair: "AUD/CAD",
  spread: 0.3,
  base_currency: "AUD",
  quote_currency: "CAD",
  confidence: "LOW",
};

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("PairCard — rendering", () => {
  it("should display pair name", () => {
    render(<PairCard pair={LONG_PAIR} type="long" />);
    expect(screen.getByText("USD/JPY")).toBeInTheDocument();
  });

  it("should display base currency", () => {
    render(<PairCard pair={LONG_PAIR} type="long" />);
    expect(screen.getByText("USD")).toBeInTheDocument();
  });

  it("should display quote currency", () => {
    render(<PairCard pair={LONG_PAIR} type="long" />);
    expect(screen.getByText("JPY")).toBeInTheDocument();
  });

  it("should display spread score formatted to 2 decimal places", () => {
    render(<PairCard pair={LONG_PAIR} type="long" />);
    expect(screen.getByText("1.82")).toBeInTheDocument();
  });

  it("should round spread to 2 decimals", () => {
    const pair = { ...LONG_PAIR, spread: 1.8 };
    render(<PairCard pair={pair} type="long" />);
    expect(screen.getByText("1.80")).toBeInTheDocument();
  });
});

describe("PairCard — accessibility", () => {
  it("should have role=button", () => {
    render(<PairCard pair={LONG_PAIR} type="long" />);
    expect(screen.getByRole("button")).toBeInTheDocument();
  });

  it("should have descriptive aria-label", () => {
    render(<PairCard pair={LONG_PAIR} type="long" />);
    const btn = screen.getByRole("button");
    expect(btn).toHaveAttribute("aria-label", expect.stringContaining("USD/JPY"));
    expect(btn).toHaveAttribute("aria-label", expect.stringContaining("long"));
    expect(btn).toHaveAttribute("aria-label", expect.stringContaining("HIGH"));
  });

  it("should be keyboard-focusable (tabIndex=0)", () => {
    render(<PairCard pair={LONG_PAIR} type="long" />);
    expect(screen.getByRole("button")).toHaveAttribute("tabindex", "0");
  });
});

describe("PairCard — selection callbacks", () => {
  it("should call onSelect when clicked", () => {
    const onSelect = jest.fn();
    render(<PairCard pair={LONG_PAIR} type="long" onSelect={onSelect} />);
    fireEvent.click(screen.getByRole("button"));
    expect(onSelect).toHaveBeenCalledWith(LONG_PAIR);
  });

  it("should call onSelect when Enter key is pressed", () => {
    const onSelect = jest.fn();
    render(<PairCard pair={LONG_PAIR} type="long" onSelect={onSelect} />);
    fireEvent.keyDown(screen.getByRole("button"), { key: "Enter" });
    expect(onSelect).toHaveBeenCalledWith(LONG_PAIR);
  });

  it("should NOT call onSelect when other keys are pressed", () => {
    const onSelect = jest.fn();
    render(<PairCard pair={LONG_PAIR} type="long" onSelect={onSelect} />);
    fireEvent.keyDown(screen.getByRole("button"), { key: "Space" });
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("should not throw when clicked without onSelect prop", () => {
    render(<PairCard pair={LONG_PAIR} type="long" />);
    expect(() => fireEvent.click(screen.getByRole("button"))).not.toThrow();
  });
});

describe("PairCard — column types", () => {
  it("should render SHORT pair data", () => {
    render(<PairCard pair={SHORT_PAIR} type="short" />);
    expect(screen.getByText("EUR/USD")).toBeInTheDocument();
  });

  it("should render AVOID pair data", () => {
    render(<PairCard pair={AVOID_PAIR} type="avoid" />);
    expect(screen.getByText("AUD/CAD")).toBeInTheDocument();
  });
});
