import { describe, it, expect } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";

describe("Debug MSW", () => {
  it("fetches from /api/v1/uploads", async () => {
    const res = await fetch("/api/v1/uploads");
    const body = await res.json();
    console.log("RAW /api/v1/uploads:", JSON.stringify(body).slice(0, 200));
    expect(body.data).toBeDefined();
    expect(Array.isArray(body.data)).toBe(true);
    expect(body.data.length).toBe(3);
  });

  it("fetches from /uploads", async () => {
    const res = await fetch("/uploads");
    const body = await res.json();
    console.log("RAW /uploads:", JSON.stringify(body).slice(0, 200));
    expect(body.data).toBeDefined();
    expect(Array.isArray(body.data)).toBe(true);
    expect(body.data.length).toBe(3);
  });

  it("fetches from /experiments", async () => {
    const res = await fetch("/experiments");
    const body = await res.json();
    console.log("RAW /experiments:", JSON.stringify(body).slice(0, 200));
    expect(body.data).toBeDefined();
    expect(Array.isArray(body.data)).toBe(true);
    expect(body.data.length).toBe(3);
  });

  it("fetches from /agents", async () => {
    const res = await fetch("/agents");
    const body = await res.json();
    console.log("RAW /agents:", JSON.stringify(body).slice(0, 200));
    expect(body.data).toBeDefined();
    expect(Array.isArray(body.data)).toBe(true);
    expect(body.data.length).toBe(3);
  });
});
