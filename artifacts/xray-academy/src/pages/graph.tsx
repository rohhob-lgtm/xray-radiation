import { useState, useEffect, useRef, useCallback } from 'react';
import { Network, RefreshCw, ZoomIn, ZoomOut, Maximize2, Search, Info } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';

const API = import.meta.env.BASE_URL.replace(/\/$/, '');

interface GraphNode {
  id: string;
  type: 'document' | 'concept';
  label: string;
  size: number;
  category?: string;
  doc_count?: number;
  filename?: string;
  // Physics state
  x: number;
  y: number;
  vx: number;
  vy: number;
}

interface GraphEdge {
  id: string;
  source: string;
  target: string;
  weight: number;
  type?: string;
}

interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  stats: { documents: number; concepts: number; connections: number };
}

const CATEGORY_COLORS: Record<string, string> = {
  scanner:    '#06b6d4',  // cyan
  physics:    '#8b5cf6',  // violet
  detection:  '#f59e0b',  // amber
  engineering:'#10b981',  // emerald
  safety:     '#ef4444',  // red
  software:   '#3b82f6',  // blue
  general:    '#6b7280',  // gray
  document:   '#0ea5e9',  // sky
};

function runForceSimulation(nodes: GraphNode[], edges: GraphEdge[], width: number, height: number, iterations = 200): GraphNode[] {
  const mutable = nodes.map(n => ({ ...n,
    x: n.x || width / 2 + (Math.random() - 0.5) * 400,
    y: n.y || height / 2 + (Math.random() - 0.5) * 400,
    vx: 0, vy: 0,
  }));

  const nodeMap: Record<string, GraphNode> = {};
  for (const n of mutable) nodeMap[n.id] = n;

  for (let iter = 0; iter < iterations; iter++) {
    const alpha = Math.max(0.01, 1 - iter / iterations);

    // Reset forces
    for (const n of mutable) { n.vx = 0; n.vy = 0; }

    // Repulsion between all nodes
    for (let i = 0; i < mutable.length; i++) {
      for (let j = i + 1; j < mutable.length; j++) {
        const a = mutable[i], b = mutable[j];
        const dx = b.x - a.x || 0.01;
        const dy = b.y - a.y || 0.01;
        const dist2 = dx * dx + dy * dy;
        const repulsion = 18000 / Math.max(dist2, 1);
        const fx = dx / Math.sqrt(dist2) * repulsion;
        const fy = dy / Math.sqrt(dist2) * repulsion;
        a.vx -= fx; a.vy -= fy;
        b.vx += fx; b.vy += fy;
      }
    }

    // Attraction along edges (spring)
    for (const edge of edges) {
      const a = nodeMap[edge.source];
      const b = nodeMap[edge.target];
      if (!a || !b) continue;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;
      const targetDist = 120;
      const spring = (dist - targetDist) * 0.08 * alpha;
      const fx = dx / dist * spring;
      const fy = dy / dist * spring;
      a.vx += fx; a.vy += fy;
      b.vx -= fx; b.vy -= fy;
    }

    // Gravity to center
    for (const n of mutable) {
      n.vx += (width / 2 - n.x) * 0.003;
      n.vy += (height / 2 - n.y) * 0.003;
    }

    // Apply velocities with damping
    for (const n of mutable) {
      n.x += n.vx * 0.5;
      n.y += n.vy * 0.5;
      n.x = Math.max(40, Math.min(width - 40, n.x));
      n.y = Math.max(40, Math.min(height - 40, n.y));
    }
  }
  return mutable;
}

export default function GraphPage() {
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [simulatedNodes, setSimulatedNodes] = useState<GraphNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [search, setSearch] = useState('');
  const svgRef = useRef<SVGSVGElement>(null);
  const W = 1000, H = 700;

  const load = useCallback(() => {
    setLoading(true);
    fetch(`${API}/api/graph/data`, { credentials: 'include' })
      .then(r => r.json())
      .then((data: GraphData) => {
        setGraphData(data);
        const simulated = runForceSimulation(data.nodes, data.edges, W, H, 300);
        setSimulatedNodes(simulated);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const nodeMap: Record<string, GraphNode> = {};
  for (const n of simulatedNodes) nodeMap[n.id] = n;

  const filteredNodeIds = new Set(
    search
      ? simulatedNodes.filter(n => n.label.toLowerCase().includes(search.toLowerCase())).map(n => n.id)
      : simulatedNodes.map(n => n.id)
  );

  const getNodeColor = (node: GraphNode) => {
    if (node.type === 'document') return CATEGORY_COLORS.document;
    return CATEGORY_COLORS[node.category || 'general'] || CATEGORY_COLORS.general;
  };

  const connectedNodeIds = selectedNode
    ? new Set(graphData?.edges.flatMap(e =>
        e.source === selectedNode.id ? [e.target] :
        e.target === selectedNode.id ? [e.source] : []
      ) || [])
    : null;

  return (
    <div className="flex flex-col h-full bg-background overflow-hidden">
      {/* Header */}
      <div className="bg-card border-b border-border p-5 shrink-0">
        <div className="max-w-7xl mx-auto flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-4">
            <div className="h-10 w-10 rounded-lg bg-violet-500/10 flex items-center justify-center ring-1 ring-violet-500/30">
              <Network className="h-5 w-5 text-violet-400" />
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight">Knowledge Graph</h1>
              <p className="text-sm text-muted-foreground font-mono uppercase tracking-wider">Document Concept Network</p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {graphData?.stats && (
              <>
                <Badge variant="outline" className="text-sky-400 border-sky-400/20 bg-sky-400/5">{graphData.stats.documents} docs</Badge>
                <Badge variant="outline" className="text-violet-400 border-violet-400/20 bg-violet-400/5">{graphData.stats.concepts} concepts</Badge>
                <Badge variant="outline" className="text-emerald-400 border-emerald-400/20 bg-emerald-400/5">{graphData.stats.connections} links</Badge>
              </>
            )}
            <Button variant="outline" size="sm" onClick={load} disabled={loading}>
              <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${loading ? 'animate-spin' : ''}`} />Refresh
            </Button>
          </div>
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Graph Canvas */}
        <div className="flex-1 relative overflow-hidden">
          {loading ? (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="flex items-center gap-3 text-muted-foreground">
                <RefreshCw className="h-5 w-5 animate-spin" />
                Building knowledge graph...
              </div>
            </div>
          ) : simulatedNodes.length === 0 ? (
            <div className="absolute inset-0 flex items-center justify-center text-center">
              <div className="space-y-3">
                <div className="h-16 w-16 rounded-2xl bg-card border border-border mx-auto flex items-center justify-center">
                  <Network className="h-8 w-8 text-muted-foreground opacity-30" />
                </div>
                <p className="text-muted-foreground">No documents in the knowledge base yet.</p>
                <p className="text-sm text-muted-foreground/60">Upload PDFs to build your concept network.</p>
              </div>
            </div>
          ) : (
            <svg
              ref={svgRef}
              viewBox={`${-pan.x / zoom} ${-pan.y / zoom} ${W / zoom} ${H / zoom}`}
              className="w-full h-full"
              style={{ cursor: 'grab' }}
            >
              <defs>
                <radialGradient id="nodeglow" cx="30%" cy="30%">
                  <stop offset="0%" stopColor="white" stopOpacity="0.3" />
                  <stop offset="100%" stopColor="white" stopOpacity="0" />
                </radialGradient>
                {Object.entries(CATEGORY_COLORS).map(([cat, color]) => (
                  <filter key={cat} id={`glow-${cat}`}>
                    <feGaussianBlur stdDeviation="3" result="blur" />
                    <feFlood floodColor={color} floodOpacity="0.4" result="color" />
                    <feComposite in="color" in2="blur" operator="in" result="shadow" />
                    <feMerge><feMergeNode in="shadow" /><feMergeNode in="SourceGraphic" /></feMerge>
                  </filter>
                ))}
              </defs>

              {/* Edges */}
              {graphData?.edges.map(edge => {
                const a = nodeMap[edge.source];
                const b = nodeMap[edge.target];
                if (!a || !b) return null;
                const isHighlighted = selectedNode &&
                  (edge.source === selectedNode.id || edge.target === selectedNode.id);
                const isVisible = filteredNodeIds.has(edge.source) && filteredNodeIds.has(edge.target);
                if (!isVisible) return null;

                return (
                  <line
                    key={edge.id}
                    x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                    stroke={isHighlighted ? '#60a5fa' : (edge.type === 'similarity' ? '#475569' : '#1e293b')}
                    strokeWidth={isHighlighted ? 2 : (edge.type === 'similarity' ? 1.5 : 0.8)}
                    strokeDasharray={edge.type === 'similarity' ? '4 3' : undefined}
                    opacity={selectedNode && !isHighlighted ? 0.15 : 0.7}
                  />
                );
              })}

              {/* Nodes */}
              {simulatedNodes.filter(n => filteredNodeIds.has(n.id)).map(node => {
                const color = getNodeColor(node);
                const isSelected = selectedNode?.id === node.id;
                const isConnected = connectedNodeIds?.has(node.id);
                const isFaded = selectedNode && !isSelected && !isConnected;
                const r = node.size / 2;

                return (
                  <g
                    key={node.id}
                    transform={`translate(${node.x},${node.y})`}
                    style={{ cursor: 'pointer' }}
                    onClick={() => setSelectedNode(selectedNode?.id === node.id ? null : node)}
                    onMouseEnter={() => setHoveredNode(node)}
                    onMouseLeave={() => setHoveredNode(null)}
                    opacity={isFaded ? 0.2 : 1}
                  >
                    {/* Glow ring for selected */}
                    {isSelected && (
                      <circle r={r + 6} fill="none" stroke={color} strokeWidth="2" opacity="0.5" />
                    )}
                    {/* Node circle */}
                    <circle
                      r={r}
                      fill={color}
                      fillOpacity={node.type === 'document' ? 0.9 : 0.7}
                      stroke={isSelected ? 'white' : color}
                      strokeWidth={isSelected ? 2 : 1}
                    />
                    <circle r={r} fill="url(#nodeglow)" />
                    {/* Label */}
                    <text
                      y={r + 12}
                      textAnchor="middle"
                      fill="white"
                      fontSize={node.type === 'document' ? 10 : 8}
                      fontWeight={node.type === 'document' ? 600 : 400}
                      fontFamily="monospace"
                      opacity={0.85}
                      className="select-none pointer-events-none"
                    >
                      {node.label.length > 18 ? node.label.slice(0, 16) + '…' : node.label}
                    </text>
                  </g>
                );
              })}
            </svg>
          )}

          {/* Zoom controls */}
          <div className="absolute bottom-4 right-4 flex flex-col gap-1">
            <Button variant="outline" size="icon" className="h-8 w-8" onClick={() => setZoom(z => Math.min(2, z + 0.2))}>
              <ZoomIn className="h-3.5 w-3.5" />
            </Button>
            <Button variant="outline" size="icon" className="h-8 w-8" onClick={() => setZoom(z => Math.max(0.3, z - 0.2))}>
              <ZoomOut className="h-3.5 w-3.5" />
            </Button>
            <Button variant="outline" size="icon" className="h-8 w-8" onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }}>
              <Maximize2 className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>

        {/* Sidebar: Legend + Node Detail */}
        <div className="w-64 border-l border-border bg-card flex flex-col">
          {/* Search */}
          <div className="p-3 border-b border-border">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
              <Input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Filter nodes..."
                className="pl-8 h-8 text-xs bg-background"
              />
            </div>
          </div>

          {/* Legend */}
          <div className="p-3 border-b border-border">
            <p className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground mb-2">Legend</p>
            <div className="space-y-1.5">
              <div className="flex items-center gap-2">
                <div className="w-4 h-4 rounded-full" style={{ background: CATEGORY_COLORS.document }} />
                <span className="text-xs text-muted-foreground">Document</span>
              </div>
              {Object.entries(CATEGORY_COLORS).filter(([k]) => k !== 'document').map(([cat, color]) => (
                <div key={cat} className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full" style={{ background: color }} />
                  <span className="text-xs text-muted-foreground capitalize">{cat}</span>
                </div>
              ))}
              <div className="flex items-center gap-2 mt-2 pt-2 border-t border-border/50">
                <div className="w-8 h-0 border-t-2 border-dashed border-muted-foreground/50" />
                <span className="text-xs text-muted-foreground">Doc similarity</span>
              </div>
            </div>
          </div>

          {/* Selected Node Detail */}
          <div className="flex-1 p-3 overflow-y-auto">
            {selectedNode ? (
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full shrink-0" style={{ background: getNodeColor(selectedNode) }} />
                  <p className="text-sm font-semibold leading-tight">{selectedNode.label}</p>
                </div>
                <div className="space-y-1.5 text-xs text-muted-foreground">
                  <div className="flex justify-between">
                    <span>Type</span>
                    <span className="text-foreground capitalize">{selectedNode.type}</span>
                  </div>
                  {selectedNode.category && (
                    <div className="flex justify-between">
                      <span>Category</span>
                      <span className="text-foreground capitalize">{selectedNode.category}</span>
                    </div>
                  )}
                  {selectedNode.doc_count !== undefined && (
                    <div className="flex justify-between">
                      <span>In documents</span>
                      <span className="text-foreground">{selectedNode.doc_count}</span>
                    </div>
                  )}
                  <div className="flex justify-between">
                    <span>Connections</span>
                    <span className="text-foreground">
                      {graphData?.edges.filter(e => e.source === selectedNode.id || e.target === selectedNode.id).length || 0}
                    </span>
                  </div>
                </div>
                {selectedNode.filename && (
                  <p className="text-[10px] text-muted-foreground/60 break-all">{selectedNode.filename}</p>
                )}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-center py-8 space-y-2">
                <Info className="h-6 w-6 text-muted-foreground/30" />
                <p className="text-xs text-muted-foreground/50">Click a node to see details</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
