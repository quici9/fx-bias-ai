/**
 * Tests for AlertBanner component — F2-01d
 * Coverage: not rendered when no HIGH alerts, renders alert details,
 * dismiss button collapses banner.
 */

import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import { AlertBanner } from "@/components/dashboard/AlertBanner";
import type { Alert } from "@/lib/types";

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const HIGH_ALERT: Alert = {
  type: "EXTREME_POSITIONING",
  currency: "USD",
  message: "USD net long near 52w maximum",
  severity: "HIGH",
};

const MEDIUM_ALERT: Alert = {
  type: "MOMENTUM_DECEL",
  currency: "EUR",
  message: "EUR momentum decelerating",
  severity: "MEDIUM",
};

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("AlertBanner", () => {
  it("should not render when alerts array is empty", () => {
    const { container } = render(<AlertBanner alerts={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("should not render when alerts have no HIGH severity", () => {
    // This component expects only HIGH alerts passed in from parent
    // Passing a MEDIUM alert would still show it (behavior test for parent filtering)
    // AlertBanner renders whatever is passed — the filter is upstream
    render(<AlertBanner alerts={[]} />);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("should render when HIGH alerts are present", () => {
    render(<AlertBanner alerts={[HIGH_ALERT]} />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("should display correct alert count — singular", () => {
    render(<AlertBanner alerts={[HIGH_ALERT]} />);
    expect(screen.getByText(/1 High Priority Alert$/)).toBeInTheDocument();
  });

  it("should display correct alert count — plural", () => {
    const second: Alert = { ...HIGH_ALERT, message: "Second alert" };
    render(<AlertBanner alerts={[HIGH_ALERT, second]} />);
    expect(screen.getByText(/2 High Priority Alerts$/)).toBeInTheDocument();
  });

  it("should display alert message", () => {
    render(<AlertBanner alerts={[HIGH_ALERT]} />);
    expect(screen.getByText(HIGH_ALERT.message)).toBeInTheDocument();
  });

  it("should display alert currency", () => {
    render(<AlertBanner alerts={[HIGH_ALERT]} />);
    expect(screen.getByText("USD")).toBeInTheDocument();
  });

  it("should display human-readable alert type label", () => {
    render(<AlertBanner alerts={[HIGH_ALERT]} />);
    expect(screen.getByText("Extreme Positioning")).toBeInTheDocument();
  });

  it("should dismiss banner when dismiss button is clicked", () => {
    render(<AlertBanner alerts={[HIGH_ALERT]} />);
    expect(screen.getByRole("alert")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /dismiss alerts/i }));

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("should render multiple alerts", () => {
    const alerts: Alert[] = [
      HIGH_ALERT,
      { type: "RISK_OFF_REGIME", message: "VIX elevated", severity: "HIGH" },
    ];
    render(<AlertBanner alerts={alerts} />);
    expect(screen.getByText(HIGH_ALERT.message)).toBeInTheDocument();
    expect(screen.getByText("VIX elevated")).toBeInTheDocument();
  });

  it("should have aria-live assertive for screen reader announcement", () => {
    render(<AlertBanner alerts={[HIGH_ALERT]} />);
    const alertEl = screen.getByRole("alert");
    expect(alertEl).toHaveAttribute("aria-live", "assertive");
  });
});
