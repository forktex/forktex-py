import { useGetSystemApiSystemsSystemIdGetQuery as useGetSystemQuery } from '../api/archApi'

interface Props {
  systemId: string
  onBack: () => void
}

export function SystemDetail({ systemId, onBack }: Props) {
  const { data: system, isLoading, error } = useGetSystemQuery({ systemId })

  if (isLoading) return <div style={styles.loading}>Loading {systemId}...</div>
  if (error || !system) return <div style={styles.loading}>System not found</div>

  return (
    <main style={styles.main}>
      <button onClick={onBack} style={styles.back}>Back to systems</button>

      <h1 style={styles.h1}>
        {system.name} <span style={styles.level}>{system.fsq_level}</span>
      </h1>

      {system.git && (
        <div style={styles.git}>
          <span style={styles.branch}>{system.git.branch}</span>
          <code style={styles.hash}>{system.git.last_commit}</code>
          {system.git.message && <span style={styles.msg}>— {system.git.message}</span>}
        </div>
      )}

      {system.packages && system.packages.length > 0 && (
        <div style={styles.section}>
          <h2 style={styles.h2}>Packages</h2>
          <div style={styles.pkgGrid}>
            {system.packages.map(p => (
              <div key={p.name} style={styles.pkgCard}>
                <div style={styles.pkgName}>{p.name}</div>
                <div style={styles.pkgMeta}>v{p.version} · {p.language}{p.publishable ? ' · PyPI' : ''}</div>
                {p.description && <div style={styles.pkgDesc}>{p.description}</div>}
              </div>
            ))}
          </div>
        </div>
      )}

      <div style={styles.section}>
        <h2 style={styles.h2}>Containers ({system.containers?.length ?? 0})</h2>
        {system.containers?.map(c => (
          <div key={c.id} style={styles.container}>
            <div style={styles.cHeader}>
              <span style={styles.cName}>{c.id}</span>
              <span style={{ ...styles.cBadge, color: c.service_type === 'compute' ? '#2a7fc1' : '#1a6d3a', borderColor: c.service_type === 'compute' ? '#2a7fc1' : '#1a6d3a' }}>
                {c.service_type}
              </span>
            </div>
            <div style={styles.techRow}>
              {c.technology?.map((t, i) => (
                <span key={i} style={styles.tech}>{t.name}{t.version ? ` ${t.version}` : ''}</span>
              ))}
              {c.ports?.[0] && <code style={styles.portCode}>:{c.ports[0].host} → :{c.ports[0].container}</code>}
            </div>

            {c.components && c.components.length > 0 && (
              <div style={styles.compGrid}>
                {c.components.map(comp => (
                  <div key={comp.id} style={styles.comp}>
                    <div style={styles.compName}>{comp.name}</div>
                    <div style={styles.compDesc}>{comp.description}</div>
                    {(comp.line_count ?? 0) > 0 && (
                      <>
                        <div style={styles.compLoc}>{comp.line_count} LoC</div>
                        <div style={{ ...styles.locBar, width: `${Math.min((comp.line_count ?? 0) / 30, 100)}%` }} />
                      </>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </main>
  )
}

const styles: Record<string, React.CSSProperties> = {
  main: { maxWidth: 1200, margin: '0 auto', padding: '2rem' },
  loading: { padding: '4rem', textAlign: 'center', color: '#8b949e' },
  back: { background: 'none', border: '1px solid #30363d', color: '#58a6ff', padding: '.4rem .8rem', borderRadius: 6, cursor: 'pointer', marginBottom: '1rem', fontSize: '.85rem' },
  h1: { fontSize: '1.8rem', marginBottom: '.5rem' },
  level: { color: '#3fb950', fontSize: '.9rem', fontWeight: 600 },
  git: { display: 'flex', alignItems: 'center', gap: '.5rem', marginBottom: '1rem', fontSize: '.85rem' },
  branch: { color: '#3fb950', fontWeight: 600 },
  hash: { color: '#8b949e', fontFamily: 'monospace', background: '#1c2333', padding: '.1rem .3rem', borderRadius: 3 },
  msg: { color: '#8b949e' },
  section: { marginBottom: '2rem' },
  h2: { fontSize: '1.1rem', color: '#58a6ff', marginBottom: '.75rem', paddingBottom: '.25rem', borderBottom: '1px solid #30363d' },
  pkgGrid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))', gap: '.75rem' },
  pkgCard: { background: '#161b22', border: '1px solid #30363d', borderRadius: 6, padding: '.75rem' },
  pkgName: { fontWeight: 700, color: '#58a6ff', marginBottom: '.25rem' },
  pkgMeta: { fontSize: '.8rem', color: '#8b949e' },
  pkgDesc: { fontSize: '.8rem', color: '#8b949e', marginTop: '.25rem' },
  container: { background: '#161b22', border: '1px solid #30363d', borderRadius: 8, padding: '1rem', marginBottom: '.75rem' },
  cHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '.5rem' },
  cName: { fontWeight: 700, fontSize: '1rem' },
  cBadge: { border: '1px solid', borderRadius: 999, padding: '.1rem .5rem', fontSize: '.75rem', fontWeight: 600 },
  techRow: { display: 'flex', flexWrap: 'wrap', gap: '.3rem', marginBottom: '.5rem' },
  tech: { fontSize: '.75rem', background: '#1c2333', border: '1px solid #30363d', borderRadius: 3, padding: '.1rem .4rem', color: '#8b949e' },
  portCode: { fontFamily: 'monospace', fontSize: '.8rem', color: '#58a6ff' },
  compGrid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: '.5rem', marginTop: '.5rem' },
  comp: { background: '#1c2333', border: '1px solid #30363d', borderRadius: 4, padding: '.5rem .75rem' },
  compName: { fontWeight: 600, color: '#d2a8ff', fontSize: '.85rem' },
  compDesc: { color: '#8b949e', fontSize: '.8rem' },
  compLoc: { color: '#8b949e', fontSize: '.75rem', marginTop: '.2rem' },
  locBar: { height: 4, borderRadius: 2, background: '#58a6ff', opacity: 0.6, marginTop: '.15rem' },
}
