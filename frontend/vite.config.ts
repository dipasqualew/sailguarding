import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The build lands *inside* the Python package (`sailguarding/web/static`) so `sg serve` — and an
// installed wheel — can serve the bundle straight off disk with no extra copy step. In dev,
// `npm run dev` runs Vite with HMR and proxies the JSON API to a locally running Python server
// (`sg serve` / `python -m sailguarding.web`), so the same-origin `/api` calls just work.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../src/sailguarding/web/static",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
