/// <reference types="node" />
import { defineConfig, devices } from "@playwright/test";

/*
 * End to end checks run a real Chromium against the real server serving a real build. The global
 * setup builds the app and the component sheet into a temp folder outside the repo. Spec files
 * start their own servers on port 0. Screenshots go to test-results/sheet and are review material.
 */
export default defineConfig({
  testDir: "e2e",
  outputDir: "test-results/artifacts",
  globalSetup: "./e2e/global-setup.ts",
  reporter: [["list"], ["./e2e/shard-reporter.ts"]],
  timeout: 60_000,
  expect: { timeout: 8_000 },
  fullyParallel: true,
  workers: process.env.CI ? 2 : 4,
  use: { trace: "retain-on-failure" },
  // The new headless mode (channel "chromium"). The old headless shell never fires
  // requestAnimationFrame here, so every click waits forever for the element to be stable.
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], channel: "chromium" } }],
});
