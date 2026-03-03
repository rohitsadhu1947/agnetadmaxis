'use client';

import { useState, useMemo, useCallback, useEffect } from 'react';
import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer,
} from 'recharts';
import {
  Users,
  Target,
  BarChart3,
  UserSearch,
  Loader2,
  RefreshCw,
  Upload,
  Phone,
  MessageCircle,
  Send,
  XCircle,
  AlertTriangle,
  CheckCircle,
  Search,
  ShieldAlert,
  TrendingUp,
  Clock,
  MapPin,
  Layers,
  Briefcase,
  GraduationCap,
  Smartphone,
  Calendar,
  Lightbulb,
  CheckSquare,
  TrendingDown,
  Shield,
  Activity,
  Hash,
  RotateCcw,
  ChevronDown,
  ChevronUp,
  Workflow,
} from 'lucide-react';
import { api } from '@/lib/api';
import { useAPI } from '@/lib/useAPI';
import { useAuth } from '@/lib/AuthContext';
import CohortSegmentCard, { SEGMENT_DISPLAY, SEGMENT_COLORS } from '@/components/CohortSegmentCard';
import ReactivationScoreGauge from '@/components/ReactivationScoreGauge';
import BulkAgentImportModal from '@/components/BulkAgentImportModal';
import WorkflowStepBuilder from '@/components/WorkflowStepBuilder';

// ─── Tab config ───────────────────────────────────────────────
type TabKey = 'overview' | 'segments' | 'agent-detail';

const TABS: { key: TabKey; label: string; icon: any }[] = [
  { key: 'overview', label: 'Overview', icon: BarChart3 },
  { key: 'segments', label: 'Segments', icon: Layers },
  { key: 'agent-detail', label: 'Agent Detail', icon: UserSearch },
];

// ─── Colors for Recharts PieChart ───────────────────────────────
const PIE_COLORS = [
  '#10b981', '#f59e0b', '#3b82f6', '#f97316', '#a855f7',
  '#ef4444', '#f43f5e', '#eab308', '#6b7280', '#06b6d4',
  '#6366f1', '#14b8a6', '#84cc16', '#ec4899', '#0ea5e9',
  '#71717a',
];

// ─── Strategy & risk config ─────────────────────────────────────
const STRATEGY_CONFIG: Record<string, { icon: any; label: string; color: string; bg: string }> = {
  direct_call:    { icon: Phone, label: 'Direct Call', color: 'text-blue-400', bg: 'bg-blue-500/10' },
  whatsapp_first: { icon: MessageCircle, label: 'WhatsApp First', color: 'text-emerald-400', bg: 'bg-emerald-500/10' },
  telegram_only:  { icon: Send, label: 'Telegram Only', color: 'text-cyan-400', bg: 'bg-cyan-500/10' },
  no_contact:     { icon: XCircle, label: 'No Contact', color: 'text-gray-400', bg: 'bg-gray-500/10' },
};

const RISK_CONFIG: Record<string, { label: string; color: string; bg: string; border: string }> = {
  high:   { label: 'High Risk', color: 'text-red-400', bg: 'bg-red-500/10', border: 'border-red-500/20' },
  medium: { label: 'Medium Risk', color: 'text-amber-400', bg: 'bg-amber-500/10', border: 'border-amber-500/20' },
  low:    { label: 'Low Risk', color: 'text-emerald-400', bg: 'bg-emerald-500/10', border: 'border-emerald-500/20' },
  lost:   { label: 'Lost', color: 'text-gray-400', bg: 'bg-gray-500/10', border: 'border-gray-500/20' },
};

// ─── Custom tooltip for Recharts PieChart ──────────────────────
function CustomPieTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="bg-surface-card border border-surface-border rounded-lg px-3 py-2 shadow-xl">
      <p className="text-sm font-medium text-white">{d.displayName}</p>
      <p className="text-xs text-gray-400">{d.value} agents ({d.pct}%)</p>
    </div>
  );
}

// ─── Main Page ─────────────────────────────────────────────────
export default function CohortPage() {
  const { isAdmin } = useAuth();
  const [activeTab, setActiveTab] = useState<TabKey>('overview');

  // ── Data fetching ──
  const { data: summary, loading: summaryLoading, refetch: refetchSummary } = useAPI(() => api.getCohortSummary());
  const { data: allAgents, loading: agentsLoading } = useAPI(() => api.listAgents({ limit: '200' }));

  // ── Segments tab state ──
  const [selectedSegment, setSelectedSegment] = useState<string | null>(null);
  const [segmentAgents, setSegmentAgents] = useState<any[]>([]);
  const [segmentLoading, setSegmentLoading] = useState(false);

  // ── Agent detail tab state ──
  const [agentSearch, setAgentSearch] = useState('');
  const [selectedAgentId, setSelectedAgentId] = useState<number | null>(null);
  const [agentAnalysis, setAgentAnalysis] = useState<any>(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [outreachSending, setOutreachSending] = useState(false);
  const [outreachResult, setOutreachResult] = useState<any>(null);

  // ── Editable first message state ──
  const [editedFirstMessage, setEditedFirstMessage] = useState('');
  const [originalFirstMessage, setOriginalFirstMessage] = useState('');

  // ── Workflow section state ──
  const [showWorkflow, setShowWorkflow] = useState(false);

  // ── Reclassify state ──
  const [reclassifying, setReclassifying] = useState(false);
  const [reclassifyResult, setReclassifyResult] = useState<any>(null);

  // ── Bulk import state ──
  const [showBulkImport, setShowBulkImport] = useState(false);

  // ── Derived data ──
  const segments = summary?.segments || [];
  const totalAgents = summary?.total_agents || 0;
  const classifiedCount = summary?.classified_count || 0;
  const avgScore = summary?.avg_reactivation_score || 0;
  const strategyDist = summary?.strategy_distribution || {};
  const riskDist = summary?.risk_distribution || {};

  const topSegment = useMemo(() => {
    if (!segments.length) return '-';
    const sorted = [...segments].sort((a: any, b: any) => b.count - a.count);
    return SEGMENT_DISPLAY[sorted[0].segment] || sorted[0].segment;
  }, [segments]);

  // PieChart data
  const pieData = useMemo(() => {
    if (!segments.length) return [];
    const total = segments.reduce((sum: number, s: any) => sum + s.count, 0);
    return segments.map((s: any, i: number) => ({
      name: s.segment,
      displayName: SEGMENT_DISPLAY[s.segment] || s.segment.replace(/_/g, ' '),
      value: s.count,
      pct: total > 0 ? ((s.count / total) * 100).toFixed(1) : '0',
      fill: PIE_COLORS[i % PIE_COLORS.length],
    }));
  }, [segments]);

  // Agents list for search (flattened)
  const agentsList = useMemo(() => {
    const raw = allAgents?.items || allAgents || [];
    return Array.isArray(raw) ? raw : [];
  }, [allAgents]);

  // Filtered agents for search
  const filteredSearchAgents = useMemo(() => {
    if (!agentSearch.trim()) return [];
    const q = agentSearch.toLowerCase();
    return agentsList
      .filter((a: any) =>
        (a.name || '').toLowerCase().includes(q) ||
        (a.phone || '').includes(q)
      )
      .slice(0, 20);
  }, [agentsList, agentSearch]);

  // ── Segment click handler ──
  const handleSegmentClick = useCallback(async (segment: string) => {
    if (selectedSegment === segment) {
      setSelectedSegment(null);
      setSegmentAgents([]);
      return;
    }
    setSelectedSegment(segment);
    setSegmentLoading(true);
    try {
      const res = await api.getCohortSegment(segment);
      setSegmentAgents(res.agents || []);
    } catch {
      setSegmentAgents([]);
    } finally {
      setSegmentLoading(false);
    }
  }, [selectedSegment]);

  // ── Agent analysis handler ──
  const handleAgentSelect = useCallback(async (agentId: number) => {
    setSelectedAgentId(agentId);
    setAgentAnalysis(null);
    setAnalysisLoading(true);
    setOutreachResult(null);
    setShowWorkflow(false);
    try {
      const res = await api.getCohortAgentAnalysis(agentId);
      setAgentAnalysis(res);
      const msg = res.first_message || '';
      setEditedFirstMessage(msg);
      setOriginalFirstMessage(msg);
    } catch (e: any) {
      setAgentAnalysis({ error: true, message: e.message });
    } finally {
      setAnalysisLoading(false);
    }
  }, []);

  // ── Reclassify handler ──
  const handleReclassify = useCallback(async () => {
    setReclassifying(true);
    setReclassifyResult(null);
    try {
      const res = await api.reclassifyCohort();
      setReclassifyResult({ type: 'success', data: res });
      refetchSummary();
    } catch (e: any) {
      setReclassifyResult({ type: 'error', message: e.message });
    } finally {
      setReclassifying(false);
    }
  }, [refetchSummary]);

  // ── Send outreach handler ──
  const handleSendOutreach = useCallback(async (agentId: number) => {
    setOutreachSending(true);
    setOutreachResult(null);
    try {
      // Pass custom message if the admin edited it
      const customMsgs = editedFirstMessage && editedFirstMessage !== originalFirstMessage
        ? { [agentId]: editedFirstMessage }
        : undefined;
      const res = await api.sendTelegramOutreach([agentId], customMsgs);
      setOutreachResult({ type: 'success', data: res });
    } catch (e: any) {
      setOutreachResult({ type: 'error', message: e.message });
    } finally {
      setOutreachSending(false);
    }
  }, [editedFirstMessage, originalFirstMessage]);

  const handleSendWhatsApp = useCallback((phone: string) => {
    const message = editedFirstMessage || originalFirstMessage || '';
    // Format phone: strip non-digits, add 91 country code if needed
    let cleanPhone = phone.replace(/[^0-9]/g, '');
    if (cleanPhone.startsWith('0')) cleanPhone = cleanPhone.substring(1);
    if (!cleanPhone.startsWith('91') && cleanPhone.length === 10) cleanPhone = '91' + cleanPhone;
    const url = `https://wa.me/${cleanPhone}?text=${encodeURIComponent(message)}`;
    window.open(url, '_blank');
    setOutreachResult({ type: 'success', data: { message: 'WhatsApp opened — send from your app' } });
  }, [editedFirstMessage, originalFirstMessage]);

  // ── Admin gate ──
  if (!isAdmin) {
    return (
      <div className="flex flex-col items-center justify-center py-20 space-y-4">
        <ShieldAlert className="w-12 h-12 text-gray-500" />
        <h2 className="text-xl font-semibold text-white">Admin Only</h2>
        <p className="text-sm text-gray-400">
          Cohort Analysis is restricted to admin users. Please contact your administrator.
        </p>
      </div>
    );
  }

  // ── Loading state ──
  if (summaryLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* ─── Page Header ─── */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-brand-red/10">
            <Target className="w-6 h-6 text-brand-red" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-white">Cohort Analysis</h1>
            <p className="text-sm text-gray-400 mt-0.5">
              16-segment classification with reactivation scoring
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowBulkImport(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-surface-card border border-surface-border text-gray-300 hover:text-white hover:border-brand-red/30 text-sm font-medium transition-all"
          >
            <Upload className="w-4 h-4" />
            Upload Agents
          </button>
          <button
            onClick={handleReclassify}
            disabled={reclassifying}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-brand-red hover:bg-brand-red/90 text-white text-sm font-medium disabled:opacity-50 transition-all"
          >
            {reclassifying ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <RefreshCw className="w-4 h-4" />
            )}
            Reclassify All
          </button>
        </div>
      </div>

      {/* Reclassify result banner */}
      {reclassifyResult && (
        <div
          className={`rounded-lg p-4 border flex items-start gap-3 ${
            reclassifyResult.type === 'success'
              ? 'border-emerald-500/20 bg-emerald-500/5'
              : 'border-red-500/20 bg-red-500/5'
          }`}
        >
          {reclassifyResult.type === 'success' ? (
            <CheckCircle className="w-5 h-5 text-emerald-400 flex-shrink-0 mt-0.5" />
          ) : (
            <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
          )}
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-white">
              {reclassifyResult.type === 'success' ? 'Reclassification Complete' : 'Reclassification Failed'}
            </p>
            <p className="text-xs text-gray-400 mt-0.5">
              {reclassifyResult.type === 'success'
                ? `${reclassifyResult.data?.classified || 0} agents reclassified successfully.`
                : reclassifyResult.message}
            </p>
          </div>
          <button
            onClick={() => setReclassifyResult(null)}
            className="text-gray-500 hover:text-white transition-colors"
          >
            <XCircle className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* ─── Tabs ─── */}
      <div className="flex gap-1 bg-surface-card/50 p-1 rounded-xl border border-surface-border/30 overflow-x-auto">
        {TABS.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium whitespace-nowrap transition-all ${
                activeTab === tab.key
                  ? 'bg-brand-red/10 text-white border border-brand-red/20'
                  : 'text-gray-400 hover:text-white hover:bg-white/5'
              }`}
            >
              <Icon className="w-4 h-4" />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* ==================== TAB: OVERVIEW ==================== */}
      {activeTab === 'overview' && (
        <div className="space-y-6">
          {/* KPI Stat Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="bg-surface-card/60 rounded-xl p-4 border border-surface-border/30">
              <div className="flex items-center gap-2 mb-2">
                <Users className="w-4 h-4 text-blue-400" />
                <p className="text-[11px] text-gray-500 uppercase tracking-wider">Total Agents</p>
              </div>
              <p className="text-2xl font-bold text-white">{totalAgents}</p>
            </div>
            <div className="bg-surface-card/60 rounded-xl p-4 border border-surface-border/30">
              <div className="flex items-center gap-2 mb-2">
                <CheckCircle className="w-4 h-4 text-emerald-400" />
                <p className="text-[11px] text-gray-500 uppercase tracking-wider">Classified</p>
              </div>
              <p className="text-2xl font-bold text-emerald-400">{classifiedCount}</p>
            </div>
            <div className="bg-surface-card/60 rounded-xl p-4 border border-surface-border/30">
              <div className="flex items-center gap-2 mb-2">
                <TrendingUp className="w-4 h-4 text-amber-400" />
                <p className="text-[11px] text-gray-500 uppercase tracking-wider">Avg Score</p>
              </div>
              <p className="text-2xl font-bold text-amber-400">{avgScore.toFixed(1)}</p>
            </div>
            <div className="bg-surface-card/60 rounded-xl p-4 border border-surface-border/30">
              <div className="flex items-center gap-2 mb-2">
                <Target className="w-4 h-4 text-purple-400" />
                <p className="text-[11px] text-gray-500 uppercase tracking-wider">Top Segment</p>
              </div>
              <p className="text-lg font-bold text-purple-400 truncate">{topSegment}</p>
            </div>
          </div>

          {/* Segment Distribution Pie + Strategy Cards */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Pie Chart */}
            <div className="glass-card p-6">
              <h3 className="text-base font-semibold text-white mb-4 flex items-center gap-2">
                <Layers className="w-5 h-5 text-blue-400" />
                Segment Distribution
              </h3>
              {pieData.length > 0 ? (
                <div className="flex flex-col items-center">
                  <ResponsiveContainer width="100%" height={280}>
                    <PieChart>
                      <Pie
                        data={pieData}
                        cx="50%"
                        cy="50%"
                        innerRadius={60}
                        outerRadius={110}
                        paddingAngle={2}
                        dataKey="value"
                      >
                        {pieData.map((entry: any, idx: number) => (
                          <Cell key={entry.name} fill={entry.fill} stroke="transparent" />
                        ))}
                      </Pie>
                      <Tooltip content={<CustomPieTooltip />} />
                    </PieChart>
                  </ResponsiveContainer>
                  {/* Legend */}
                  <div className="grid grid-cols-2 gap-x-6 gap-y-1 mt-4 w-full max-w-md">
                    {pieData.map((entry: any) => (
                      <div key={entry.name} className="flex items-center gap-2">
                        <div
                          className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                          style={{ backgroundColor: entry.fill }}
                        />
                        <span className="text-[11px] text-gray-400 truncate">{entry.displayName}</span>
                        <span className="text-[11px] text-gray-500 ml-auto">{entry.value}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="flex items-center justify-center py-12">
                  <p className="text-sm text-gray-500">No segment data available</p>
                </div>
              )}
            </div>

            {/* Strategy + Risk Cards */}
            <div className="space-y-6">
              {/* Strategy Distribution */}
              <div className="glass-card p-6">
                <h3 className="text-base font-semibold text-white mb-4 flex items-center gap-2">
                  <Phone className="w-5 h-5 text-emerald-400" />
                  Strategy Distribution
                </h3>
                <div className="grid grid-cols-2 gap-3">
                  {Object.entries(STRATEGY_CONFIG).map(([key, config]) => {
                    const Icon = config.icon;
                    const count = strategyDist[key] || 0;
                    return (
                      <div
                        key={key}
                        className={`${config.bg} rounded-xl p-4 border border-surface-border/20`}
                      >
                        <div className="flex items-center gap-2 mb-2">
                          <Icon className={`w-4 h-4 ${config.color}`} />
                          <span className="text-xs text-gray-400">{config.label}</span>
                        </div>
                        <p className={`text-xl font-bold ${config.color}`}>{count}</p>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Risk Distribution */}
              <div className="glass-card p-6">
                <h3 className="text-base font-semibold text-white mb-4 flex items-center gap-2">
                  <AlertTriangle className="w-5 h-5 text-red-400" />
                  Risk Levels
                </h3>
                <div className="grid grid-cols-2 gap-3">
                  {Object.entries(RISK_CONFIG).map(([key, config]) => {
                    const count = riskDist[key] || 0;
                    return (
                      <div
                        key={key}
                        className={`${config.bg} rounded-xl p-3 border ${config.border}`}
                      >
                        <p className="text-xs text-gray-400 mb-1">{config.label}</p>
                        <p className={`text-xl font-bold ${config.color}`}>{count}</p>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ==================== TAB: SEGMENTS ==================== */}
      {activeTab === 'segments' && (
        <div className="space-y-6">
          {/* Segment Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            {segments.map((seg: any) => (
              <CohortSegmentCard
                key={seg.segment}
                segment={seg.segment}
                count={seg.count}
                avgScore={seg.avg_score}
                strategy={seg.strategy}
                onClick={() => handleSegmentClick(seg.segment)}
                selected={selectedSegment === seg.segment}
              />
            ))}
          </div>

          {segments.length === 0 && (
            <div className="flex flex-col items-center justify-center py-12">
              <Layers className="w-10 h-10 text-gray-600 mb-3" />
              <p className="text-sm text-gray-500">No segments found. Upload agents and run classification.</p>
            </div>
          )}

          {/* Segment Agent List */}
          {selectedSegment && (
            <div className="glass-card overflow-hidden">
              <div className="px-5 py-4 border-b border-surface-border/30 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                  <Users className="w-4 h-4 text-brand-red" />
                  {SEGMENT_DISPLAY[selectedSegment] || selectedSegment.replace(/_/g, ' ')} Agents
                  <span className="text-xs text-gray-500 font-normal">
                    ({segmentAgents.length})
                  </span>
                </h3>
                <button
                  onClick={() => { setSelectedSegment(null); setSegmentAgents([]); }}
                  className="text-gray-500 hover:text-white transition-colors"
                >
                  <XCircle className="w-4 h-4" />
                </button>
              </div>

              {segmentLoading ? (
                <div className="flex items-center justify-center py-10">
                  <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
                </div>
              ) : segmentAgents.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-surface-border bg-surface-card/30">
                        {['Name', 'Phone', 'Location', 'Score', 'Strategy', 'Risk'].map((header) => (
                          <th
                            key={header}
                            className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider"
                          >
                            {header}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {segmentAgents.map((agent: any) => {
                        const stratConfig = STRATEGY_CONFIG[agent.engagement_strategy] || STRATEGY_CONFIG.no_contact;
                        const riskConfig = RISK_CONFIG[agent.churn_risk_level] || RISK_CONFIG.medium;
                        const StratIcon = stratConfig.icon;
                        return (
                          <tr
                            key={agent.id}
                            className="border-b border-surface-border/30 hover:bg-surface-card-hover/50 transition-colors cursor-pointer"
                            onClick={() => {
                              setActiveTab('agent-detail');
                              setAgentSearch(agent.name || '');
                              handleAgentSelect(agent.id);
                            }}
                          >
                            <td className="px-4 py-3">
                              <div className="flex items-center gap-3">
                                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-brand-red/80 to-brand-navy flex items-center justify-center flex-shrink-0">
                                  <span className="text-white font-medium text-[10px]">
                                    {agent.name ? agent.name.split(' ').map((n: string) => n[0]).join('').slice(0, 2) : '??'}
                                  </span>
                                </div>
                                <p className="text-sm font-medium text-white">{agent.name}</p>
                              </div>
                            </td>
                            <td className="px-4 py-3 text-sm text-gray-400">{agent.phone}</td>
                            <td className="px-4 py-3 text-sm text-gray-400">{agent.location || '-'}</td>
                            <td className="px-4 py-3">
                              <span
                                className={`text-sm font-semibold ${
                                  agent.reactivation_score >= 70
                                    ? 'text-emerald-400'
                                    : agent.reactivation_score >= 40
                                    ? 'text-amber-400'
                                    : agent.reactivation_score >= 20
                                    ? 'text-orange-400'
                                    : 'text-red-400'
                                }`}
                              >
                                {agent.reactivation_score?.toFixed(0) ?? '-'}
                              </span>
                            </td>
                            <td className="px-4 py-3">
                              <div className="flex items-center gap-1.5">
                                <StratIcon className={`w-3.5 h-3.5 ${stratConfig.color}`} />
                                <span className="text-xs text-gray-400">{stratConfig.label}</span>
                              </div>
                            </td>
                            <td className="px-4 py-3">
                              <span
                                className={`text-xs px-2 py-1 rounded-full border ${riskConfig.bg} ${riskConfig.color} ${riskConfig.border}`}
                              >
                                {riskConfig.label}
                              </span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="flex items-center justify-center py-10">
                  <p className="text-sm text-gray-500">No agents in this segment</p>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ==================== TAB: AGENT DETAIL ==================== */}
      {activeTab === 'agent-detail' && (
        <div className="space-y-6">
          {/* Search */}
          <div className="glass-card p-4">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
              <input
                type="text"
                placeholder="Search agent by name or phone..."
                value={agentSearch}
                onChange={(e) => {
                  setAgentSearch(e.target.value);
                  setSelectedAgentId(null);
                  setAgentAnalysis(null);
                  setOutreachResult(null);
                }}
                className="w-full pl-10 pr-4 py-2.5 input-dark text-sm"
              />
            </div>

            {/* Search Results Dropdown */}
            {agentSearch.trim() && filteredSearchAgents.length > 0 && !selectedAgentId && (
              <div className="mt-2 rounded-lg border border-surface-border/30 bg-surface-card/80 max-h-60 overflow-y-auto">
                {filteredSearchAgents.map((agent: any) => (
                  <button
                    key={agent.id}
                    onClick={() => {
                      setAgentSearch(agent.name);
                      handleAgentSelect(agent.id);
                    }}
                    className="w-full text-left px-4 py-2.5 hover:bg-surface-card-hover/50 transition-colors flex items-center gap-3 border-b border-surface-border/10 last:border-0"
                  >
                    <div className="w-7 h-7 rounded-full bg-gradient-to-br from-brand-red/80 to-brand-navy flex items-center justify-center flex-shrink-0">
                      <span className="text-white font-medium text-[9px]">
                        {agent.name ? agent.name.split(' ').map((n: string) => n[0]).join('').slice(0, 2) : '??'}
                      </span>
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-white truncate">{agent.name}</p>
                      <p className="text-[11px] text-gray-500">{agent.phone} &middot; {agent.location || 'N/A'}</p>
                    </div>
                  </button>
                ))}
              </div>
            )}

            {agentSearch.trim() && filteredSearchAgents.length === 0 && !selectedAgentId && !agentsLoading && (
              <p className="mt-2 text-xs text-gray-500">No agents found matching &quot;{agentSearch}&quot;</p>
            )}
          </div>

          {/* Analysis Loading */}
          {analysisLoading && (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
            </div>
          )}

          {/* Analysis Error */}
          {agentAnalysis?.error && (
            <div className="glass-card p-6">
              <div className="flex items-start gap-3">
                <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-white">Analysis Failed</p>
                  <p className="text-xs text-red-400 mt-1">{agentAnalysis.message}</p>
                  <p className="text-xs text-gray-500 mt-2">
                    This agent may not have been classified yet. Try running &quot;Reclassify All&quot; first.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Agent Analysis Profile */}
          {agentAnalysis && !agentAnalysis.error && !analysisLoading && (
            <div className="space-y-5">

              {/* ── Row 1: Score Gauge + Agent Profile Card ── */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
                {/* Reactivation Score Gauge */}
                <div className="glass-card p-6 flex flex-col items-center justify-center">
                  <h4 className="text-xs text-gray-500 uppercase tracking-wider mb-4">Reactivation Score</h4>
                  <ReactivationScoreGauge
                    score={agentAnalysis.reactivation_score || 0}
                    breakdown={agentAnalysis.score_breakdown}
                    size="lg"
                    showBreakdown={true}
                  />
                </div>

                {/* Agent Profile Card */}
                <div className="lg:col-span-2 glass-card p-6 space-y-4">
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-4">
                      <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-brand-red/80 to-brand-navy flex items-center justify-center flex-shrink-0">
                        <span className="text-white font-bold text-lg">
                          {agentAnalysis.agent?.name ? agentAnalysis.agent.name.split(' ').map((n: string) => n[0]).join('').slice(0, 2) : '??'}
                        </span>
                      </div>
                      <div>
                        <h3 className="text-xl font-bold text-white">
                          {agentAnalysis.agent?.name || `Agent #${agentAnalysis.agent_id}`}
                        </h3>
                        <div className="flex items-center gap-3 mt-1 flex-wrap">
                          {agentAnalysis.agent?.phone && (
                            <span className="text-xs text-gray-400 flex items-center gap-1">
                              <Phone className="w-3 h-3" />
                              {agentAnalysis.agent.phone}
                            </span>
                          )}
                          {(agentAnalysis.agent?.location || agentAnalysis.agent?.state) && (
                            <span className="text-xs text-gray-400 flex items-center gap-1">
                              <MapPin className="w-3 h-3" />
                              {[agentAnalysis.agent.location, agentAnalysis.agent.state].filter(Boolean).join(', ')}
                            </span>
                          )}
                          {agentAnalysis.agent?.language && (
                            <span className="text-xs text-gray-400 flex items-center gap-1">
                              <MessageCircle className="w-3 h-3" />
                              {agentAnalysis.agent.language}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Send Outreach Buttons */}
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleSendOutreach(agentAnalysis.agent_id)}
                        disabled={outreachSending}
                        className="flex items-center gap-2 px-4 py-2 rounded-lg bg-brand-red hover:bg-brand-red/90 text-white text-sm font-medium disabled:opacity-50 transition-all"
                      >
                        {outreachSending ? (
                          <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                          <Send className="w-4 h-4" />
                        )}
                        Send via Telegram
                      </button>
                      <button
                        onClick={() => handleSendWhatsApp(agentAnalysis.agent?.phone || '')}
                        className="flex items-center gap-2 px-4 py-2 rounded-lg bg-green-600 hover:bg-green-700 text-white text-sm font-medium transition-all"
                      >
                        <MessageCircle className="w-4 h-4" />
                        Send via WhatsApp
                      </button>
                    </div>
                  </div>

                  {/* Outreach result */}
                  {outreachResult && (
                    <div
                      className={`rounded-lg p-3 border text-sm ${
                        outreachResult.type === 'success'
                          ? 'border-emerald-500/20 bg-emerald-500/5 text-emerald-400'
                          : 'border-red-500/20 bg-red-500/5 text-red-400'
                      }`}
                    >
                      {outreachResult.type === 'success'
                        ? 'Outreach message sent successfully.'
                        : `Failed: ${outreachResult.message}`}
                    </div>
                  )}

                  {/* Segment + Strategy + Risk Badges */}
                  <div className="flex flex-wrap items-center gap-2">
                    {/* Segment Badge */}
                    {agentAnalysis.segment && (() => {
                      const segColors = SEGMENT_COLORS[agentAnalysis.segment] || SEGMENT_COLORS.lost_causes;
                      return (
                        <span className={`text-xs px-3 py-1.5 rounded-full border ${segColors.bg} ${segColors.border} ${segColors.text} font-medium`}>
                          {agentAnalysis.segment_display_name || SEGMENT_DISPLAY[agentAnalysis.segment] || agentAnalysis.segment.replace(/_/g, ' ')}
                        </span>
                      );
                    })()}

                    {/* Strategy Badge */}
                    {agentAnalysis.engagement_strategy && (() => {
                      const sConfig = STRATEGY_CONFIG[agentAnalysis.engagement_strategy] || STRATEGY_CONFIG.no_contact;
                      const SIcon = sConfig.icon;
                      return (
                        <span className={`text-xs px-3 py-1.5 rounded-full border border-surface-border/30 ${sConfig.bg} ${sConfig.color} font-medium flex items-center gap-1.5`}>
                          <SIcon className="w-3 h-3" />
                          {sConfig.label}
                        </span>
                      );
                    })()}

                    {/* Risk Badge */}
                    {agentAnalysis.churn_risk && (() => {
                      const rConfig = RISK_CONFIG[agentAnalysis.churn_risk] || RISK_CONFIG.medium;
                      return (
                        <span className={`text-xs px-3 py-1.5 rounded-full border ${rConfig.border} ${rConfig.bg} ${rConfig.color} font-medium`}>
                          {rConfig.label}
                        </span>
                      );
                    })()}
                  </div>

                  {/* Segment Description */}
                  {agentAnalysis.segment_description && (
                    <p className="text-sm text-gray-400 leading-relaxed">
                      {agentAnalysis.segment_description}
                    </p>
                  )}
                </div>
              </div>

              {/* ── Row 2: Performance Stats (6 cards) ── */}
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                {[
                  {
                    label: 'Days Inactive',
                    value: agentAnalysis.agent?.days_since_last_activity ?? agentAnalysis.agent?.dormancy_duration_days ?? '-',
                    icon: Clock,
                    color: 'text-amber-400',
                    bgColor: 'bg-amber-500/5',
                  },
                  {
                    label: 'Policies Sold',
                    value: agentAnalysis.agent?.total_policies_sold ?? '-',
                    icon: BarChart3,
                    color: 'text-blue-400',
                    bgColor: 'bg-blue-500/5',
                  },
                  {
                    label: 'Recent Policies',
                    value: agentAnalysis.agent?.policies_last_12_months ?? '-',
                    icon: TrendingUp,
                    color: 'text-emerald-400',
                    bgColor: 'bg-emerald-500/5',
                  },
                  {
                    label: 'Avg Ticket Size',
                    value: agentAnalysis.agent?.avg_ticket_size != null
                      ? `₹${Number(agentAnalysis.agent.avg_ticket_size).toLocaleString('en-IN')}`
                      : '-',
                    icon: Hash,
                    color: 'text-cyan-400',
                    bgColor: 'bg-cyan-500/5',
                  },
                  {
                    label: 'Response Rate',
                    value: agentAnalysis.agent?.response_rate != null
                      ? `${(agentAnalysis.agent.response_rate * 100).toFixed(0)}%`
                      : '-',
                    icon: Activity,
                    color: 'text-purple-400',
                    bgColor: 'bg-purple-500/5',
                  },
                  {
                    label: 'Persistency',
                    value: agentAnalysis.agent?.persistency_ratio != null
                      ? `${(agentAnalysis.agent.persistency_ratio * 100).toFixed(0)}%`
                      : '-',
                    icon: Shield,
                    color: 'text-rose-400',
                    bgColor: 'bg-rose-500/5',
                  },
                ].map((stat) => {
                  const StatIcon = stat.icon;
                  return (
                    <div
                      key={stat.label}
                      className={`${stat.bgColor} bg-surface-card/60 rounded-xl p-4 border border-surface-border/30`}
                    >
                      <div className="flex items-center gap-1.5 mb-2">
                        <StatIcon className={`w-3.5 h-3.5 ${stat.color}`} />
                        <span className="text-[10px] text-gray-500 uppercase tracking-wider">{stat.label}</span>
                      </div>
                      <p className={`text-xl font-bold ${stat.color}`}>{stat.value}</p>
                    </div>
                  );
                })}
              </div>

              {/* ── Row 3: Score Breakdown (horizontal bar chart) ── */}
              {agentAnalysis.score_breakdown && (
                <div className="glass-card p-6">
                  <h4 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                    <BarChart3 className="w-4 h-4 text-blue-400" />
                    Score Breakdown
                  </h4>
                  <div className="space-y-3">
                    {[
                      { key: 'historical_performance', label: 'Historical Performance', max: 25 },
                      { key: 'responsiveness', label: 'Responsiveness', max: 20 },
                      { key: 'market_potential', label: 'Market Potential', max: 15 },
                      { key: 'time_decay', label: 'Time Decay', max: 20 },
                      { key: 'reason_recoverability', label: 'Reason Recoverability', max: 10 },
                      { key: 'demographics', label: 'Demographics', max: 10 },
                    ].map((comp) => {
                      const val = agentAnalysis.score_breakdown[comp.key] ?? 0;
                      const pct = comp.max > 0 ? Math.min((val / comp.max) * 100, 100) : 0;
                      const barColor = pct >= 65 ? 'bg-emerald-500' : pct >= 35 ? 'bg-amber-500' : 'bg-red-500';
                      const textColor = pct >= 65 ? 'text-emerald-400' : pct >= 35 ? 'text-amber-400' : 'text-red-400';
                      return (
                        <div key={comp.key} className="flex items-center gap-3">
                          <div className="w-44 flex-shrink-0 text-xs text-gray-400 text-right">
                            {comp.label}
                          </div>
                          <div className="flex-1 h-6 bg-surface-card/80 rounded-full overflow-hidden border border-surface-border/20 relative">
                            <div
                              className={`h-full ${barColor} rounded-full transition-all duration-700 ease-out`}
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                          <div className={`w-20 text-right text-xs font-semibold ${textColor} flex-shrink-0`}>
                            {typeof val === 'number' ? val.toFixed(1) : val} / {comp.max}
                          </div>
                        </div>
                      );
                    })}
                    {/* Total row */}
                    <div className="flex items-center gap-3 pt-2 mt-1 border-t border-surface-border/20">
                      <div className="w-44 flex-shrink-0 text-xs text-white font-semibold text-right">
                        Total Score
                      </div>
                      <div className="flex-1 h-6 bg-surface-card/80 rounded-full overflow-hidden border border-surface-border/20 relative">
                        <div
                          className="h-full bg-gradient-to-r from-brand-red to-brand-red/60 rounded-full transition-all duration-700 ease-out"
                          style={{ width: `${Math.min((agentAnalysis.score_breakdown.total ?? 0), 100)}%` }}
                        />
                      </div>
                      <div className="w-20 text-right text-xs font-bold text-white flex-shrink-0">
                        {typeof agentAnalysis.score_breakdown.total === 'number' ? agentAnalysis.score_breakdown.total.toFixed(1) : agentAnalysis.score_breakdown.total} / 100
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* ── Row 4: Agent Profile Details (2 columns) ── */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                {/* Work Profile */}
                <div className="glass-card p-6">
                  <h4 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                    <Briefcase className="w-4 h-4 text-blue-400" />
                    Work Profile
                  </h4>
                  <div className="space-y-3">
                    {[
                      { label: 'Age', value: agentAnalysis.agent?.age ? `${agentAnalysis.agent.age} years` : '-', icon: Users },
                      { label: 'Education', value: agentAnalysis.agent?.education_level || '-', icon: GraduationCap },
                      { label: 'Experience', value: agentAnalysis.agent?.years_in_insurance != null ? `${agentAnalysis.agent.years_in_insurance} years` : '-', icon: Calendar },
                      { label: 'Work Type', value: agentAnalysis.agent?.work_type || '-', icon: Briefcase },
                      { label: 'Dormancy Reason', value: agentAnalysis.agent?.dormancy_reason?.replace(/_/g, ' ') || '-', icon: TrendingDown },
                      { label: 'Lifecycle State', value: agentAnalysis.agent?.lifecycle_state?.replace(/_/g, ' ') || '-', icon: Activity },
                    ].map((item) => {
                      const ItemIcon = item.icon;
                      return (
                        <div key={item.label} className="flex items-center justify-between py-2 border-b border-surface-border/10 last:border-0">
                          <div className="flex items-center gap-2 text-gray-400">
                            <ItemIcon className="w-3.5 h-3.5 text-gray-500" />
                            <span className="text-xs">{item.label}</span>
                          </div>
                          <span className="text-sm text-white font-medium capitalize">{item.value}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Digital Readiness */}
                <div className="glass-card p-6">
                  <h4 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                    <Smartphone className="w-4 h-4 text-emerald-400" />
                    Digital Readiness
                  </h4>
                  <div className="space-y-4">
                    {/* Digital Savviness Score */}
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs text-gray-400">Digital Savviness</span>
                        <span className="text-sm font-bold text-white">
                          {agentAnalysis.agent?.digital_savviness_score != null ? `${agentAnalysis.agent.digital_savviness_score} / 10` : '-'}
                        </span>
                      </div>
                      {agentAnalysis.agent?.digital_savviness_score != null && (
                        <div className="h-3 bg-surface-card/80 rounded-full overflow-hidden border border-surface-border/20">
                          <div
                            className={`h-full rounded-full transition-all duration-700 ease-out ${
                              agentAnalysis.agent.digital_savviness_score >= 7 ? 'bg-emerald-500' :
                              agentAnalysis.agent.digital_savviness_score >= 4 ? 'bg-amber-500' : 'bg-red-500'
                            }`}
                            style={{ width: `${(agentAnalysis.agent.digital_savviness_score / 10) * 100}%` }}
                          />
                        </div>
                      )}
                    </div>

                    {/* App Installed Badge */}
                    <div className="flex items-center justify-between py-2 border-b border-surface-border/10">
                      <span className="text-xs text-gray-400 flex items-center gap-2">
                        <Smartphone className="w-3.5 h-3.5 text-gray-500" />
                        App Installed
                      </span>
                      {agentAnalysis.agent?.has_app_installed != null ? (
                        <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${
                          agentAnalysis.agent.has_app_installed
                            ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                            : 'bg-red-500/10 text-red-400 border border-red-500/20'
                        }`}>
                          {agentAnalysis.agent.has_app_installed ? 'Yes' : 'No'}
                        </span>
                      ) : (
                        <span className="text-sm text-gray-500">-</span>
                      )}
                    </div>

                    {/* Contact Stats */}
                    <div className="flex items-center justify-between py-2 border-b border-surface-border/10">
                      <span className="text-xs text-gray-400 flex items-center gap-2">
                        <Phone className="w-3.5 h-3.5 text-gray-500" />
                        Contact Attempts / Responses
                      </span>
                      <span className="text-sm text-white font-medium">
                        {agentAnalysis.agent?.contact_attempts ?? '-'} / {agentAnalysis.agent?.contact_responses ?? '-'}
                      </span>
                    </div>

                    {/* Last Contact Date */}
                    <div className="flex items-center justify-between py-2 border-b border-surface-border/10">
                      <span className="text-xs text-gray-400 flex items-center gap-2">
                        <Calendar className="w-3.5 h-3.5 text-gray-500" />
                        Last Contact Date
                      </span>
                      <span className="text-sm text-white font-medium">
                        {agentAnalysis.agent?.last_contact_date || '-'}
                      </span>
                    </div>

                    {/* Last Policy Sold Date */}
                    <div className="flex items-center justify-between py-2 border-b border-surface-border/10">
                      <span className="text-xs text-gray-400 flex items-center gap-2">
                        <Calendar className="w-3.5 h-3.5 text-gray-500" />
                        Last Policy Sold
                      </span>
                      <span className="text-sm text-white font-medium">
                        {agentAnalysis.agent?.last_policy_sold_date || '-'}
                      </span>
                    </div>

                    {/* Premium (12m) */}
                    <div className="flex items-center justify-between py-2">
                      <span className="text-xs text-gray-400 flex items-center gap-2">
                        <TrendingUp className="w-3.5 h-3.5 text-gray-500" />
                        Premium (12m)
                      </span>
                      <span className="text-sm text-white font-medium">
                        {agentAnalysis.agent?.premium_last_12_months != null
                          ? `₹${Number(agentAnalysis.agent.premium_last_12_months).toLocaleString('en-IN')}`
                          : '-'}
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              {/* ── Row 5: Classification Reasoning ── */}
              {agentAnalysis.reasoning && (
                <div className="glass-card p-6">
                  <h4 className="text-sm font-semibold text-white mb-5 flex items-center gap-2">
                    <Lightbulb className="w-4 h-4 text-amber-400" />
                    Why This Classification
                  </h4>

                  <div className="space-y-5">
                    {/* Classification Reasons */}
                    {agentAnalysis.reasoning.classification_reasons?.length > 0 && (
                      <div>
                        <h5 className="text-xs text-gray-500 uppercase tracking-wider mb-2">Classification Reasons</h5>
                        <ol className="space-y-1.5 list-decimal list-inside">
                          {agentAnalysis.reasoning.classification_reasons.map((reason: string, i: number) => (
                            <li key={i} className="text-sm text-gray-300 leading-relaxed">
                              {reason}
                            </li>
                          ))}
                        </ol>
                      </div>
                    )}

                    {/* Key Factors */}
                    {agentAnalysis.reasoning.key_factors?.length > 0 && (
                      <div>
                        <h5 className="text-xs text-gray-500 uppercase tracking-wider mb-2">Key Factors</h5>
                        <div className="flex flex-wrap gap-2">
                          {agentAnalysis.reasoning.key_factors.map((kf: any, i: number) => {
                            const impactColor =
                              kf.impact === 'positive' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' :
                              kf.impact === 'negative' ? 'bg-red-500/10 text-red-400 border-red-500/20' :
                              'bg-gray-500/10 text-gray-400 border-gray-500/20';
                            return (
                              <span key={i} className={`text-xs px-3 py-1.5 rounded-full border ${impactColor} font-medium`}>
                                {kf.factor}: {kf.value}
                              </span>
                            );
                          })}
                        </div>
                      </div>
                    )}

                    {/* Risk Signals + Opportunities side by side */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                      {/* Risk Signals */}
                      {agentAnalysis.reasoning.risk_signals?.length > 0 && (
                        <div>
                          <h5 className="text-xs text-gray-500 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                            <AlertTriangle className="w-3 h-3 text-red-400" />
                            Risk Signals
                          </h5>
                          <div className="space-y-1.5">
                            {agentAnalysis.reasoning.risk_signals.map((rs: string, i: number) => (
                              <div key={i} className="flex items-start gap-2 bg-red-500/5 rounded-lg px-3 py-2 border border-red-500/10">
                                <AlertTriangle className="w-3.5 h-3.5 text-red-400 flex-shrink-0 mt-0.5" />
                                <span className="text-xs text-red-300 leading-relaxed">{rs}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Opportunities */}
                      {agentAnalysis.reasoning.opportunities?.length > 0 && (
                        <div>
                          <h5 className="text-xs text-gray-500 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                            <Lightbulb className="w-3 h-3 text-emerald-400" />
                            Opportunities
                          </h5>
                          <div className="space-y-1.5">
                            {agentAnalysis.reasoning.opportunities.map((opp: string, i: number) => (
                              <div key={i} className="flex items-start gap-2 bg-emerald-500/5 rounded-lg px-3 py-2 border border-emerald-500/10">
                                <CheckCircle className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0 mt-0.5" />
                                <span className="text-xs text-emerald-300 leading-relaxed">{opp}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* ── Row 6: Recommended Actions + First Message ── */}
              {(agentAnalysis.reasoning?.recommended_actions?.length > 0 || agentAnalysis.first_message) && (
                <div className="glass-card p-6">
                  <h4 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                    <CheckSquare className="w-4 h-4 text-emerald-400" />
                    Recommended Actions
                  </h4>

                  {/* Recommended Actions List */}
                  {agentAnalysis.reasoning?.recommended_actions?.length > 0 && (
                    <div className="space-y-2 mb-5">
                      {agentAnalysis.reasoning.recommended_actions.map((action: string, i: number) => (
                        <div key={i} className="flex items-start gap-3 py-2">
                          <div className="w-6 h-6 rounded-md bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center flex-shrink-0 mt-0.5">
                            <span className="text-[10px] font-bold text-emerald-400">{i + 1}</span>
                          </div>
                          <span className="text-sm text-gray-300 leading-relaxed">{action}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Editable First Message */}
                  {(agentAnalysis.first_message || editedFirstMessage) && (
                    <div className="bg-[#0B1120] rounded-lg p-4 border border-surface-border/20">
                      <div className="flex items-center justify-between mb-2">
                        <p className="text-[11px] text-gray-500 uppercase tracking-wider flex items-center gap-1.5">
                          <MessageCircle className="w-3 h-3" />
                          First Message (editable)
                        </p>
                        {editedFirstMessage !== originalFirstMessage && (
                          <button
                            onClick={() => setEditedFirstMessage(originalFirstMessage)}
                            className="flex items-center gap-1 text-[10px] text-gray-500 hover:text-gray-300 transition-colors"
                          >
                            <RotateCcw className="w-2.5 h-2.5" />
                            Reset to original
                          </button>
                        )}
                      </div>
                      <textarea
                        value={editedFirstMessage}
                        onChange={(e) => setEditedFirstMessage(e.target.value)}
                        rows={4}
                        className="w-full bg-surface-card border border-surface-border/30 rounded px-3 py-2 text-sm text-gray-300 resize-none focus:outline-none focus:ring-1 focus:ring-brand-red/50 placeholder:text-gray-600 leading-relaxed"
                        placeholder="Enter outreach message..."
                      />
                    </div>
                  )}
                </div>
              )}

              {/* ── Row 7: Outreach Workflow ── */}
              {agentAnalysis && !agentAnalysis.error && agentAnalysis.engagement_strategy && (
                <div className="glass-card p-6">
                  <button
                    onClick={() => setShowWorkflow(!showWorkflow)}
                    className="w-full flex items-center justify-between"
                  >
                    <h4 className="text-sm font-semibold text-white flex items-center gap-2">
                      <Workflow className="w-4 h-4 text-cyan-400" />
                      Outreach Workflow
                    </h4>
                    {showWorkflow ? (
                      <ChevronUp className="w-4 h-4 text-gray-400" />
                    ) : (
                      <ChevronDown className="w-4 h-4 text-gray-400" />
                    )}
                  </button>
                  {showWorkflow && (
                    <div className="mt-4">
                      <WorkflowStepBuilder
                        strategy={agentAnalysis.engagement_strategy}
                        agentName={agentAnalysis.agent?.name}
                        compact
                      />
                    </div>
                  )}
                </div>
              )}

            </div>
          )}

          {/* Empty state */}
          {!selectedAgentId && !analysisLoading && (
            <div className="flex flex-col items-center justify-center py-16">
              <UserSearch className="w-10 h-10 text-gray-600 mb-3" />
              <p className="text-sm text-gray-500">Search for an agent to view their cohort analysis</p>
            </div>
          )}
        </div>
      )}

      {/* ─── Bulk Import Modal ─── */}
      <BulkAgentImportModal
        mode="cohort"
        isOpen={showBulkImport}
        onClose={() => setShowBulkImport(false)}
        onSuccess={() => {
          refetchSummary();
          setShowBulkImport(false);
        }}
      />
    </div>
  );
}
