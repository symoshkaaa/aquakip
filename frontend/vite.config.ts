import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const { VITE_API_URL = "http://127.0.0.1:8000/api/v1" } = loadEnv(
    mode,
    process.cwd(),
    "VITE_",
  );
  const apiUrl = new URL(VITE_API_URL, "http://127.0.0.1:8000");
  const apiPrefix = apiUrl.pathname.replace(/\/$/, "");

  return {
    plugins: [react()],
    server: {
      proxy: {
        [apiPrefix]: {
          target: apiUrl.origin,
          changeOrigin: true,
        },
      },
    },
  };
});
