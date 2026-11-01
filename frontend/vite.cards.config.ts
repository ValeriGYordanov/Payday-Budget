import { defineConfig } from "vite";

// The dashboard cards (§8) as one ES module, served by the integration (§7.1).
// Committed: HACS installs custom_components/ as-is.
export default defineConfig({
  define: { __APP_VERSION__: JSON.stringify(process.env.npm_package_version ?? "dev") },
  build: {
    outDir: "../custom_components/payday_budget/www",
    emptyOutDir: true,
    target: "es2022",
    lib: {
      entry: "src/cards/index.ts",
      formats: ["es"],
      fileName: () => "payday-budget-cards.js",
    },
  },
});
