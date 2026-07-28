// Copyright (C) 2026 FORKTEX S.R.L.
// SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-ForkTex-Commercial
//
// @rtk-query/codegen-openapi config — generates a typed RTK Query slice
// (gridApi) + React hooks from the grid OpenAPI schema. Run via `make sync`.
const config = {
  schemaFile: "../openapi.json",
  apiFile: "../client/src/api/baseApi.ts",
  apiImport: "baseApi",
  outputFile: "../client/src/api/grid.ts",
  exportName: "gridApi",
  hooks: { queries: true, mutations: true, lazyQueries: true },
  tag: true,
};
module.exports = config;
