import { useState } from 'react'
import { useListSystemsApiSystemsGetQuery as useGetSystemsQuery, useListEdgesApiEdgesGetQuery as useGetEdgesQuery } from './api/archApi'
import { Graph } from './components/Graph'
import { SystemCard } from './components/SystemCard'
import { SystemDetail } from './components/SystemDetail'

export function App() {
  const [selectedSystem, setSelectedSystem] = useState<string | null>(null)
  const { data: systems, isLoading } = useGetSystemsQuery()
  const { data: edges } = useGetEdgesQuery()

  if (isLoading) return <div style={styles.loading}>Discovering architecture...</div>

  return (
    <div style={styles.root}>
      <nav style={styles.nav}>
        <span style={styles.logo}>FORKTEX</span>
        <span style={styles.navTitle}>Architecture</span>
        {selectedSystem && (
          <>
            <span style={styles.sep}>/</span>
            <button style={styles.backBtn} onClick={() => setSelectedSystem(null)}>Systems</button>
            <span style={styles.sep}>/</span>
            <span style={styles.current}>{selectedSystem}</span>
          </>
        )}
        <span style={styles.badge}>{systems?.length ?? 0} systems</span>
      </nav>

      {selectedSystem ? (
        <SystemDetail systemId={selectedSystem} onBack={() => setSelectedSystem(null)} />
      ) : (
        <main style={styles.main}>
          {edges && edges.length > 0 && (
            <section style={styles.section}>
              <h2 style={styles.h2}>Dependency Graph</h2>
              <Graph edges={edges} systems={systems ?? []} onNodeClick={setSelectedSystem} />
            </section>
          )}

          <section style={styles.section}>
            <h2 style={styles.h2}>Systems</h2>
            <div style={styles.grid}>
              {systems?.map(s => (
                <SystemCard key={s.id} system={s} onClick={() => setSelectedSystem(s.id)} />
              ))}
            </div>
          </section>
        </main>
      )}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  root: { minHeight: '100vh' },
  loading: { padding: '4rem', textAlign: 'center', color: '#8b949e', fontSize: '1.2rem' },
  nav: { background: '#161b22', borderBottom: '1px solid #30363d', padding: '.75rem 2rem', display: 'flex', alignItems: 'center', gap: '.75rem', position: 'sticky', top: 0, zIndex: 10 },
  logo: { fontWeight: 800, color: '#58a6ff', fontSize: '1rem' },
  navTitle: { color: '#e6edf3', fontWeight: 600 },
  sep: { color: '#30363d' },
  backBtn: { background: 'none', border: 'none', color: '#58a6ff', cursor: 'pointer', fontSize: '.9rem' },
  current: { color: '#e6edf3', fontWeight: 600 },
  badge: { marginLeft: 'auto', background: '#1c2333', color: '#8b949e', padding: '.2rem .6rem', borderRadius: '12px', fontSize: '.75rem' },
  main: { maxWidth: 1200, margin: '0 auto', padding: '2rem' },
  section: { marginBottom: '2rem' },
  h2: { fontSize: '1.2rem', color: '#58a6ff', marginBottom: '1rem', paddingBottom: '.25rem', borderBottom: '1px solid #30363d' },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: '1rem' },
}
