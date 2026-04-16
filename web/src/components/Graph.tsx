import { useRef, useEffect, useMemo } from 'react'

interface Edge { source: string; target: string; description: string }
interface System { id: string; name: string; fsq_level?: string }

interface Props {
  edges: Edge[]
  systems: System[]
  onNodeClick: (id: string) => void
}

export function Graph({ edges, systems, onNodeClick }: Props) {
  const svgRef = useRef<SVGSVGElement>(null)

  const { nodes, nodeMap, W, H } = useMemo(() => {
    const nodeSet = new Set<string>()
    edges.forEach(e => { nodeSet.add(e.source); nodeSet.add(e.target) })
    const nodes = Array.from(nodeSet).map((id, i) => {
      const sys = systems.find(s => s.id === id || s.name === id)
      return { id, label: sys?.name ?? id, level: sys?.fsq_level ?? '', x: 0, y: 0, idx: i }
    })
    const nodeMap = Object.fromEntries(nodes.map(n => [n.id, n]))
    const cols = Math.ceil(Math.sqrt(nodes.length))
    const W = Math.max(cols * 180, 600)
    const cellH = 56
    nodes.forEach((n, i) => {
      n.x = (i % cols) * 170 + 30
      n.y = Math.floor(i / cols) * cellH + 20
    })
    const H = Math.ceil(nodes.length / cols) * cellH + 60
    return { nodes, nodeMap, W, H }
  }, [edges, systems])

  const boxW = 150, boxH = 32

  return (
    <div style={styles.wrap}>
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: H }}>
        <defs>
          <marker id="arr" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#8b949e" />
          </marker>
        </defs>

        {edges.map((e, i) => {
          const src = nodeMap[e.source], tgt = nodeMap[e.target]
          if (!src || !tgt) return null
          const x1 = src.x + boxW / 2, y1 = src.y + boxH / 2
          const x2 = tgt.x + boxW / 2, y2 = tgt.y + boxH / 2
          return (
            <g key={i}>
              <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="#8b949e" strokeWidth={1.5} opacity={0.5} markerEnd="url(#arr)" />
              <text x={(x1 + x2) / 2} y={(y1 + y2) / 2 - 4} textAnchor="middle" fill="#8b949e" fontSize={9}>{e.description}</text>
            </g>
          )
        })}

        {nodes.map(n => (
          <g key={n.id} style={{ cursor: 'pointer' }} onClick={() => onNodeClick(n.id)}>
            <rect x={n.x} y={n.y} width={boxW} height={boxH} fill="#1c2333" stroke="#30363d" strokeWidth={1.5} rx={6} />
            <text x={n.x + boxW / 2} y={n.y + boxH / 2 + 4} textAnchor="middle" fill="#e6edf3" fontSize={11}>{n.label}</text>
            {n.level && (
              <text x={n.x + boxW - 8} y={n.y + 12} textAnchor="end" fill="#3fb950" fontSize={9} fontWeight={700}>{n.level}</text>
            )}
          </g>
        ))}
      </svg>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  wrap: { background: '#161b22', border: '1px solid #30363d', borderRadius: 8, padding: '1rem', overflowX: 'auto' },
}
