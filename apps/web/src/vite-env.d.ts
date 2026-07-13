/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_DISABLE_REACT_DEVTOOLS?: "0" | "1"
  readonly VITE_MAPTILER_KEY?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
