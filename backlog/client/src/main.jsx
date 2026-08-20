// Copyright (C) 2026 FORKTEX S.R.L.
// SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-ForkTex-Commercial
import React from "react";
import { createRoot } from "react-dom/client";
import { GridStudio } from "./GridStudio.jsx";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <GridStudio />
  </React.StrictMode>,
);
