import { afterEach, beforeEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { clearSession } from "../auth/session";

beforeEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
  clearSession();
});

afterEach(() => {
  cleanup();
});
