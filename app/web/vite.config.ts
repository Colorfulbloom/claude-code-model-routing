import { fileURLToPath } from "node:url";
import babel from "@rolldown/plugin-babel";
import react, { reactCompilerPreset } from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

/**
 * `vite build --mode sheet` builds the component sheet alone into dist-sheet/. It is a dev and test
 * entry and never ships. The normal build uses index.html only.
 */
export default defineConfig(({ mode }) => ({
  plugins: [react(), babel({ presets: [reactCompilerPreset()] })],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  build:
    mode === "sheet"
      ? {
          outDir: "dist-sheet",
          emptyOutDir: true,
          rollupOptions: {
            input: fileURLToPath(new URL("./sheet.html", import.meta.url)),
          },
        }
      : {
          outDir: "dist",
          emptyOutDir: true,
          rollupOptions: {
            input: fileURLToPath(new URL("./index.html", import.meta.url)),
          },
        },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
}));
