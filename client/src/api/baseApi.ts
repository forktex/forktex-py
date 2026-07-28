// Copyright (C) 2026 FORKTEX S.R.L.
// SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-ForkTex-Commercial
//
// RTK Query base API. `make sync` generates the typed `gridApi` slice + hooks
// into ./grid.ts on top of this base (see codegen/rtk.config.cjs).
import { createApi, fetchBaseQuery } from "@reduxjs/toolkit/query/react";

const env = (import.meta as unknown as { env?: Record<string, string> }).env ?? {};

export const baseApi = createApi({
  reducerPath: "gridApi",
  baseQuery: fetchBaseQuery({
    baseUrl: env.VITE_GRID_URL ?? "http://127.0.0.1:4445",
    prepareHeaders: (headers) => {
      const ns = env.VITE_GRID_NAMESPACE;
      if (ns) headers.set("X-Grid-Namespace", ns);
      return headers;
    },
  }),
  endpoints: () => ({}),
});
