import { existsSync, readFileSync } from "node:fs";
import { defineConfig } from "vite";

// Dev only: the local backend (`.claude/launch.json`) keeps its data and token in ../.dev-data.
const devTokenFile = new URL("../.dev-data/token", import.meta.url);
const devToken =
  process.env.PAYDAY_BUDGET_TOKEN ??
  (existsSync(devTokenFile) ? readFileSync(devTokenFile, "utf8").trim() : "");

// The add-on image is built from payday_budget/ only, so the SPA is emitted there (committed).
export default defineConfig({
  define: { __APP_VERSION__: JSON.stringify(process.env.npm_package_version ?? "dev") },
  base: "./", // relative URLs: Ingress serves the UI under /api/hassio_ingress/<session>/
  build: {
    outDir: "../payday_budget/app/static",
    emptyOutDir: true,
    target: "es2022",
  },
  server: {
    // Dev only: proxy to a local backend, authenticating with its token (§6.2).
    proxy: {
      "/api": {
        target: "http://localhost:8099",
        headers: { Authorization: `Bearer ${devToken}` },
      },
    },
  },
});
