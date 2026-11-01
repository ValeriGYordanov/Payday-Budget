import { defineConfig } from "vitest/config";

export default defineConfig({
  // The cards smoke test loads the built bundle from ../custom_components.
  server: { fs: { allow: [".."] } },
});
