import { useState, useEffect } from 'react';
import { useLocation } from 'wouter';
import { useListConversations, useListResearchOutputs, useListRagDocuments } from '@workspace/api-client-react';
import {
  MessageSquare, FlaskConical, BookOpen, ShieldCheck, ImageIcon,
  FileText, Linkedin, Search, ArrowRight, Lightbulb, Cpu, PenTool, BookMarked,
  Microscope, Target, GraduationCap, Network, Images, Wrench, Eye, Layers, Database
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Link } from 'wouter';

const API = import.meta.env.BASE_URL.replace(/\/$/, '');

const MODULE_GROUPS = [
  {
    label: 'AI INTELLIGENCE',
    color: 'text-blue-400',
    modules: [
      { icon: MessageSquare, title: 'AI Chat', desc: 'Multi-agent expert assistant with 8 specialized modes', href: '/chat', badge: 'Live', badgeColor: 'bg-blue-500/20 text-blue-400 border-blue-400/20' },
      { icon: Eye,           title: 'X-Ray Analysis', desc: 'Upload scans — threat detection with bounding boxes', href: '/upload', badge: 'Vision', badgeColor: 'bg-cyan-500/20 text-cyan-400 border-cyan-400/20' },
    ]
  },
  {
    label: 'RESEARCH & INNOVATION',
    color: 'text-violet-400',
    modules: [
      { icon: FlaskConical,  title: 'Research Studio', desc: 'Generate IEEE papers, literature reviews, proposals', href: '/research?mode=paper_ieee', badge: 'GPT-5.4', badgeColor: 'bg-violet-500/20 text-violet-400 border-violet-400/20' },
      { icon: ShieldCheck,   title: 'Patent Analyzer', desc: 'Novelty analysis, prior art search, claim drafting', href: '/patent' },
      { icon: Lightbulb,     title: 'Invention Engine', desc: 'Generate breakthrough ideas for X-ray technology', href: '/research?mode=research_ideas' },
      { icon: Target,        title: 'Research Gap Analysis', desc: 'Identify unexplored areas in X-ray science', href: '/research?mode=research_gaps' },
      { icon: Microscope,    title: 'Experiment Planning', desc: 'Design methodology and lab procedures', href: '/research?mode=experiment_plan' },
    ]
  },
  {
    label: 'KNOWLEDGE',
    color: 'text-emerald-400',
    modules: [
      { icon: BookOpen,      title: 'Knowledge Base', desc: 'Upload PDFs — automatic text & visual indexing', href: '/rag', badge: 'ColPali', badgeColor: 'bg-emerald-500/20 text-emerald-400 border-emerald-400/20' },
      { icon: Images,        title: 'Image Gallery', desc: 'Browse all visually-indexed document pages', href: '/gallery' },
      { icon: Network,       title: 'Knowledge Graph', desc: 'Visual concept network across all documents', href: '/graph' },
    ]
  },
  {
    label: 'ENGINEERING',
    color: 'text-amber-400',
    modules: [
      { icon: Wrench,        title: 'Technical Reports', desc: 'Maintenance, failure analysis, inspection reports', href: '/reports' },
      { icon: Cpu,           title: 'Scanner Design', desc: 'Technical specs and engineering documentation', href: '/research?mode=technical_report' },
    ]
  },
  {
    label: 'EDUCATION & CONTENT',
    color: 'text-teal-400',
    modules: [
      { icon: GraduationCap, title: 'Education Studio', desc: 'Courses, quizzes, lesson plans, certificates', href: '/education', badge: 'New', badgeColor: 'bg-teal-500/20 text-teal-400 border-teal-400/20' },
      { icon: PenTool,       title: 'IEEE Paper Writing', desc: 'Standard academic paper format and style', href: '/research?mode=paper_ieee' },
      { icon: BookMarked,    title: 'Literature Review', desc: 'Synthesize and cite academic sources', href: '/research?mode=literature_review' },
      { icon: Linkedin,      title: 'LinkedIn Content', desc: 'Professional posts, articles, and summaries', href: '/linkedin' },
    ]
  },
];

const AGENTS = [
  { id: 'general',     label: 'General',     color: 'bg-blue-500/10 text-blue-400 border-blue-400/20' },
  { id: 'research',    label: 'Research',    color: 'bg-violet-500/10 text-violet-400 border-violet-400/20' },
  { id: 'physics',     label: 'Physics',     color: 'bg-amber-500/10 text-amber-400 border-amber-400/20' },
  { id: 'patent',      label: 'Patent',      color: 'bg-emerald-500/10 text-emerald-400 border-emerald-400/20' },
  { id: 'vision',      label: 'Vision',      color: 'bg-cyan-500/10 text-cyan-400 border-cyan-400/20' },
  { id: 'maintenance', label: 'Maintenance', color: 'bg-rose-500/10 text-rose-400 border-rose-400/20' },
  { id: 'training',    label: 'Training',    color: 'bg-teal-500/10 text-teal-400 border-teal-400/20' },
  { id: 'innovation',  label: 'Innovation',  color: 'bg-yellow-500/10 text-yellow-400 border-yellow-400/20' },
];

export default function DashboardPage() {
  const [, setLocation] = useLocation();
  const [quickQuery, setQuickQuery] = useState('');
  const [ragStatus, setRagStatus] = useState<any>(null);

  const { data: conversations } = useListConversations();
  const { data: researchOutputs } = useListResearchOutputs();
  const { data: ragDocs } = useListRagDocuments();

  useEffect(() => {
    fetch(`${API}/api/rag/status`, { credentials: 'include' })
      .then(r => r.json()).then(setRagStatus).catch(() => {});
  }, []);

  const handleAskAI = (e: React.FormEvent) => {
    e.preventDefault();
    if (!quickQuery.trim()) return;
    sessionStorage.setItem('prefilled_chat_query', quickQuery);
    setLocation('/chat');
  };

  return (
    <div className="flex flex-col h-full bg-background overflow-y-auto">
      {/* Hero Header */}
      <div className="bg-card border-b border-border p-6 md:p-8 shrink-0 relative overflow-hidden">
        <div className="absolute inset-0 bg-[linear-gradient(135deg,rgba(37,99,235,0.04)_0%,transparent_50%,rgba(139,92,246,0.04)_100%)] pointer-events-none" />
        <div className="absolute top-0 right-0 w-96 h-96 bg-primary/5 rounded-full blur-3xl pointer-events-none transform translate-x-1/2 -translate-y-1/2" />

        <div className="max-w-7xl mx-auto flex flex-col md:flex-row gap-6 items-start md:items-center justify-between relative z-10">
          <div>
            <div className="flex items-center gap-3 mb-3">
              <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">Platform Online</span>
            </div>
            <h1 className="text-3xl md:text-4xl font-bold tracking-tight mb-2">X-Ray AI Platform</h1>
            <p className="text-muted-foreground font-mono text-xs uppercase tracking-widest">
              Research · Analysis · Education · Innovation
            </p>
          </div>

          <form onSubmit={handleAskAI} className="w-full md:w-auto relative group">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground group-focus-within:text-primary transition-colors" />
            <Input
              placeholder="Ask the X-Ray AI..."
              className="w-full md:w-[340px] pl-10 pr-24 h-12 bg-background border-border focus-visible:ring-primary shadow-inner"
              value={quickQuery}
              onChange={e => setQuickQuery(e.target.value)}
            />
            <Button size="sm" type="submit" className="absolute right-1 top-1 h-10 bg-primary hover:bg-primary/90 text-primary-foreground">
              Ask <ArrowRight className="h-3 w-3 ml-1" />
            </Button>
          </form>
        </div>
      </div>

      <div className="flex-1 p-6 md:p-8 max-w-7xl mx-auto w-full space-y-8">
        {/* Stats Bar */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          {[
            { label: 'Conversations', value: conversations?.length ?? '–', icon: MessageSquare, color: 'text-blue-400' },
            { label: 'Research Outputs', value: researchOutputs?.length ?? '–', icon: FlaskConical, color: 'text-violet-400' },
            { label: 'KB Documents', value: ragDocs?.length ?? '–', icon: BookOpen, color: 'text-emerald-400' },
            { label: 'Pages Indexed', value: ragStatus?.pages_indexed ?? '–', icon: Layers, color: 'text-cyan-400' },
            { label: 'Images Captioned', value: ragStatus?.images_captioned ?? '–', icon: ImageIcon, color: 'text-amber-400' },
            { label: 'Visual Backend', value: ragStatus?.colpali_backend ?? '–', icon: Database, color: 'text-rose-400' },
          ].map((stat, i) => (
            <Card key={i} className="bg-card/50 border-border/50 shadow-sm">
              <CardContent className="p-4 flex items-center gap-3">
                <div className={`p-2 rounded-lg bg-background border border-border ${stat.color} shrink-0`}>
                  <stat.icon className="h-4 w-4" />
                </div>
                <div className="min-w-0">
                  <div className="text-lg font-bold font-mono truncate">{stat.value}</div>
                  <div className="text-[10px] text-muted-foreground uppercase tracking-wider truncate">{stat.label}</div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* AI Agents */}
        <div>
          <h2 className="text-xs font-bold uppercase tracking-widest text-muted-foreground mb-3 font-mono flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-blue-400 animate-pulse" />Specialized AI Agents
          </h2>
          <div className="flex flex-wrap gap-2">
            {AGENTS.map(agent => (
              <Link
                key={agent.id}
                href={`/chat`}
                onClick={() => {
                  sessionStorage.setItem('prefilled_agent', agent.id);
                  // store for chat page to pick up
                }}
              >
                <Badge
                  variant="outline"
                  className={`cursor-pointer hover:opacity-80 transition-opacity px-3 py-1.5 text-xs font-mono uppercase tracking-wider ${agent.color}`}
                >
                  {agent.label}
                </Badge>
              </Link>
            ))}
          </div>
        </div>

        {/* Module Groups */}
        {MODULE_GROUPS.map((group) => (
          <div key={group.label}>
            <h2 className={`text-xs font-bold uppercase tracking-widest mb-3 font-mono flex items-center gap-2 ${group.color}`}>
              <span className="w-2 h-2 rounded-full bg-current" />{group.label}
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
              {group.modules.map((mod, i) => (
                <Link key={i} href={mod.href}>
                  <Card className="group hover:border-border hover:bg-card/80 transition-all cursor-pointer h-full bg-card/30 border-border/40">
                    <CardContent className="p-4 flex items-start gap-3 h-full">
                      <div className="p-2 rounded-lg bg-background border border-border/60 group-hover:border-border text-muted-foreground group-hover:text-foreground transition-colors shrink-0 mt-0.5">
                        <mod.icon className="h-4 w-4" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <h3 className="font-semibold text-sm text-foreground leading-tight">{mod.title}</h3>
                          {mod.badge && (
                            <Badge variant="outline" className={`text-[9px] px-1.5 py-0 h-4 font-mono uppercase tracking-wider shrink-0 ${mod.badgeColor}`}>
                              {mod.badge}
                            </Badge>
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground leading-snug">{mod.desc}</p>
                        <div className="mt-2 text-[10px] font-mono text-primary flex items-center gap-1 uppercase tracking-wider opacity-0 group-hover:opacity-100 transition-opacity">
                          Open <ArrowRight className="h-2.5 w-2.5" />
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </Link>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
