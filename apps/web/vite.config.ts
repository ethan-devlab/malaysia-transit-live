import { fileURLToPath, URL } from "node:url"

import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"
import reactScan from "vite-plugin-react-scan"

export default defineConfig(({ command }) => {
  const reactDevtoolsEnabled =
    command === "serve" && process.env.VITE_DISABLE_REACT_DEVTOOLS !== "1"

  return {
    plugins: [react(), tailwindcss(), ...(reactDevtoolsEnabled ? [reactScan()] : [])],
    resolve: {
      alias: {
        "@": fileURLToPath(new URL("./src", import.meta.url)),
      },
    },
    test: {
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
    },
  }
})
