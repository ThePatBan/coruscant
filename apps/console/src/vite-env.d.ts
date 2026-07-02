/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Absolute origin of the internal admin app (admin.coruscant.com). Admin-only
   *  cross-app link; defaults to the production origin when unset. */
  readonly VITE_ADMIN_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
