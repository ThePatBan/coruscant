/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Absolute origin of the customer console (console.coruscant.com). CTAs point here;
   *  defaults to the production origin when unset. */
  readonly VITE_CONSOLE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
