// Copyright (C) 2026 FORKTEX S.R.L.
// SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-ForkTex-Commercial
//
// The grid inspection studio — stateless functional components that adapt
// entirely to the server's self-describing API (/grid/types + /grid/tables/{slug}
// describe + query). No per-entity code: columns render by their declared
// capabilities, across any namespace. (Hand-wired on fetch so the studio is
// self-contained; `make sync` adds typed RTK hooks via ./api/grid.ts.)
import React, { useCallback, useEffect, useState } from "react";

const API = (import.meta.env && import.meta.env.VITE_GRID_URL) || "http://127.0.0.1:4445";

function useApi(namespace) {
  return useCallback(
    async (path, opts = {}) => {
      const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
      if (namespace) headers["X-Grid-Namespace"] = namespace;
      const res = await fetch(API + path, { ...opts, headers });
      if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
      return res.status === 204 ? null : res.json();
    },
    [namespace],
  );
}

function Badge({ on, children }) {
  return (
    <span style={{ fontSize: 11, padding: "1px 6px", marginRight: 4, borderRadius: 4, background: on ? "#1f6feb" : "#30363d", color: "#fff", opacity: on ? 1 : 0.5 }}>
      {children}
    </span>
  );
}

function ColumnRow({ col }) {
  const c = col.capabilities;
  return (
    <tr>
      <td style={{ fontWeight: 600 }}>{col.key}</td>
      <td><code>{col.type_id}</code>{col.cardinality === "many" ? "[]" : ""}</td>
      <td>
        <Badge on={c.filterable}>filter</Badge>
        <Badge on={c.sortable}>sort</Badge>
        <Badge on={c.fuzzy}>fuzzy</Badge>
        {col.is_required ? <Badge on>required</Badge> : null}
        {col.is_unique ? <Badge on>unique</Badge> : null}
      </td>
    </tr>
  );
}

function TableView({ api, slug }) {
  const [describe, setDescribe] = useState(null);
  const [rows, setRows] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    setError(null);
    (async () => {
      try {
        const d = await api(`/grid/tables/${slug}`);
        const q = await api(`/grid/tables/${slug}/query`, { method: "POST", body: JSON.stringify({ limit: 50 }) });
        if (alive) {
          setDescribe(d);
          setRows(q.rows || []);
        }
      } catch (e) {
        if (alive) setError(String(e));
      }
    })();
    return () => {
      alive = false;
    };
  }, [api, slug]);

  if (error) return <p style={{ color: "#f85149" }}>{error}</p>;
  if (!describe) return <p>Loading {slug}…</p>;
  const cols = describe.columns;
  return (
    <div>
      <h2>{describe.table.label} <small style={{ opacity: 0.6 }}>({describe.table.ownership})</small></h2>
      <h4>Columns</h4>
      <table>
        <thead><tr><th>key</th><th>type</th><th>capabilities</th></tr></thead>
        <tbody>{cols.map((c) => <ColumnRow key={c.id} col={c} />)}</tbody>
      </table>
      <h4>Rows ({rows.length})</h4>
      <table>
        <thead><tr>{cols.map((c) => <th key={c.id}>{c.key}</th>)}</tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>{cols.map((c) => <td key={c.id}>{String(r.payload?.[c.key] ?? "")}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function GridStudio() {
  const [namespace, setNamespace] = useState("");
  const api = useApi(namespace);
  const [tables, setTables] = useState([]);
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    api("/grid/tables")
      .then((t) => alive && setTables(t))
      .catch((e) => alive && setError(String(e)));
    return () => {
      alive = false;
    };
  }, [api]);

  return (
    <div style={{ fontFamily: "system-ui", display: "flex", gap: 24, padding: 24, color: "#c9d1d9", background: "#0d1117", minHeight: "100vh" }}>
      <aside style={{ minWidth: 220 }}>
        <h1 style={{ fontSize: 18 }}>Grid Studio</h1>
        <label style={{ fontSize: 12, opacity: 0.7 }}>namespace</label>
        <input value={namespace} placeholder="(root)" onChange={(e) => setNamespace(e.target.value)} style={{ width: "100%", marginBottom: 12 }} />
        {error ? <p style={{ color: "#f85149" }}>{error}</p> : null}
        <ul style={{ listStyle: "none", padding: 0 }}>
          {tables.map((t) => (
            <li key={t.id}>
              <button onClick={() => setSelected(t.slug)} style={{ background: "none", border: "none", color: selected === t.slug ? "#58a6ff" : "#c9d1d9", cursor: "pointer", padding: "2px 0" }}>
                {t.slug}
              </button>
            </li>
          ))}
          {tables.length === 0 ? <li style={{ opacity: 0.6 }}>(no tables)</li> : null}
        </ul>
      </aside>
      <main style={{ flex: 1 }}>{selected ? <TableView api={api} slug={selected} /> : <p>Select a table.</p>}</main>
    </div>
  );
}
