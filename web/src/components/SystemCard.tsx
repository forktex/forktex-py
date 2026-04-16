import type { SystemInfo } from '../api/archApi'

interface Props {
  system: SystemInfo
  onClick: () => void
}

export function SystemCard({ system, onClick }: Props) {
  return (
    <div onClick={onClick} style={styles.card}>
      <div style={styles.header}>
        <span style={styles.name}>{system.name}</span>
        <span style={styles.level}>{system.fsq_level}</span>
      </div>

      {system.git && (
        <div style={styles.git}>
          <span style={styles.branch}>{system.git.branch}</span>
          <code style={styles.hash}>{system.git.last_commit}</code>
          {system.git.dirty && <span style={styles.dirty}>*</span>}
        </div>
      )}

      {system.packages && system.packages.length > 0 && (
        <div style={styles.pkgs}>
          {system.packages.map(p => (
            <span key={p.name} style={styles.pkg}>{p.name} <small>v{p.version}</small></span>
          ))}
        </div>
      )}

      <div style={styles.meta}>
        {system.provider && <span>{system.provider}/{system.region}</span>}
        {system.domains?.[0] && <span> — {system.domains[0]}</span>}
      </div>

      <div style={styles.services}>
        {system.containers?.map(c => (
          <div key={c.id} style={styles.svc}>
            <span style={{ ...styles.dot, background: c.service_type === 'compute' ? '#2a7fc1' : '#1a6d3a' }} />
            <span style={styles.svcName}>{c.id}</span>
            <span style={styles.svcTech}>{c.technology?.map(t => t.name).join(', ')}</span>
            {c.ports?.[0] && <code style={styles.port}>:{c.ports[0].host}</code>}
          </div>
        ))}
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  card: { background: '#161b22', border: '1px solid #30363d', borderRadius: 8, padding: '1.25rem', cursor: 'pointer', transition: 'border-color .15s' },
  header: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '.5rem' },
  name: { fontWeight: 700, fontSize: '1.05rem' },
  level: { color: '#3fb950', border: '1px solid #3fb950', borderRadius: 999, padding: '.1rem .5rem', fontSize: '.75rem', fontWeight: 600 },
  git: { display: 'flex', alignItems: 'center', gap: '.35rem', marginBottom: '.4rem', fontSize: '.8rem' },
  branch: { color: '#3fb950', fontWeight: 600 },
  hash: { color: '#8b949e', fontFamily: 'monospace', fontSize: '.75rem', background: '#1c2333', padding: '.1rem .3rem', borderRadius: 3 },
  dirty: { color: '#d29922' },
  pkgs: { display: 'flex', flexWrap: 'wrap', gap: '.3rem', marginBottom: '.4rem' },
  pkg: { fontSize: '.75rem', background: '#1c2333', border: '1px solid #30363d', borderRadius: 3, padding: '.1rem .4rem', color: '#58a6ff' },
  meta: { fontSize: '.85rem', color: '#8b949e', marginBottom: '.5rem' },
  services: { display: 'flex', flexDirection: 'column', gap: '.25rem' },
  svc: { display: 'flex', alignItems: 'center', gap: '.5rem', padding: '.25rem .5rem', borderRadius: 4, fontSize: '.85rem', background: '#1c2333' },
  dot: { width: 8, height: 8, borderRadius: '50%', flexShrink: 0 },
  svcName: { fontWeight: 600, minWidth: 60 },
  svcTech: { color: '#8b949e', flex: 1 },
  port: { color: '#58a6ff', fontFamily: 'monospace', fontSize: '.8rem' },
}
