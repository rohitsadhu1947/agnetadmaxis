'use client';

import { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, PieChart, Pie, Cell,
} from 'recharts';
import {
  Ticket, Filter, Clock, AlertTriangle, CheckCircle2, Send,
  MessageSquareText, ChevronDown, ChevronUp, Search, Loader2,
  ArrowRight, Shield, Zap, TrendingUp, AlertCircle, XCircle,
  Building2, ThumbsUp, ThumbsDown, RotateCcw, Eye, FileText,
  Timer, CircleDot, Star, ChevronRight, Mic, Tags, Plus, HelpCircle,
  User, Bot, Settings,
} from 'lucide-react';
import { api } from '@/lib/api';
import { useAPI } from '@/lib/useAPI';
import { useAuth } from '@/lib/AuthContext';
import ChartCard from '@/components/ChartCard';
import StatCard from '@/components/StatCard';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

// ─── Bucket config ───────────────────────────────────────────────
const BUCKETS: Record<string, { label: string; color: string; bg: string; border: string; icon: React.ElementType }> = {
  underwriting: { label: 'Underwriting', color: 'text-blue-400', bg: 'bg-blue-500/10', border: 'border-blue-500/20', icon: Shield },
  finance:      { label: 'Finance', color: 'text-emerald-400', bg: 'bg-emerald-500/10', border: 'border-emerald-500/20', icon: TrendingUp },
  contest:      { label: 'Contest & Engagement', color: 'text-purple-400', bg: 'bg-purple-500/10', border: 'border-purple-500/20', icon: Star },
  operations:   { label: 'Operations', color: 'text-amber-400', bg: 'bg-amber-500/10', border: 'border-amber-500/20', icon: Zap },
  product:      { label: 'Product', color: 'text-pink-400', bg: 'bg-pink-500/10', border: 'border-pink-500/20', icon: FileText },
};

const PRIORITY_CONFIG: Record<string, { label: string; color: string; bg: string; border: string }> = {
  critical: { label: 'Critical', color: 'text-red-400', bg: 'bg-red-500/10', border: 'border-red-500/20' },
  high:     { label: 'High', color: 'text-orange-400', bg: 'bg-orange-500/10', border: 'border-orange-500/20' },
  medium:   { label: 'Medium', color: 'text-amber-400', bg: 'bg-amber-500/10', border: 'border-amber-500/20' },
  low:      { label: 'Low', color: 'text-gray-400', bg: 'bg-gray-500/10', border: 'border-gray-500/20' },
};

const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string; icon: React.ElementType }> = {
  received:         { label: 'Received', color: 'text-blue-400', bg: 'bg-blue-500/10', icon: CircleDot },
  classified:       { label: 'Classified', color: 'text-indigo-400', bg: 'bg-indigo-500/10', icon: Filter },
  routed:           { label: 'Routed', color: 'text-cyan-400', bg: 'bg-cyan-500/10', icon: ArrowRight },
  pending_dept:     { label: 'Pending Dept', color: 'text-amber-400', bg: 'bg-amber-500/10', icon: Clock },
  pending_adm:      { label: 'Awaiting ADM', color: 'text-blue-400', bg: 'bg-blue-500/10', icon: Clock },
  responded:        { label: 'Responded', color: 'text-purple-400', bg: 'bg-purple-500/10', icon: MessageSquareText },
  script_generated: { label: 'Script Ready', color: 'text-emerald-400', bg: 'bg-emerald-500/10', icon: FileText },
  script_sent:      { label: 'Script Sent', color: 'text-green-400', bg: 'bg-green-500/10', icon: Send },
  closed:           { label: 'Closed', color: 'text-gray-400', bg: 'bg-gray-500/10', icon: CheckCircle2 },
};

const PIE_COLORS = ['#3B82F6', '#10B981', '#8B5CF6', '#F59E0B', '#EC4899', '#6B7280'];

// ─── Tooltip ─────────────────────────────────────────────────────
const CustomTooltip = ({ active, payload, label }: any) => {
  if (active && payload?.length) {
    return (
      <div className="bg-surface-card border border-surface-border rounded-lg p-3 shadow-xl">
        <p className="text-gray-200 font-medium text-sm mb-1">{label}</p>
        {payload.map((entry: any, i: number) => (
          <p key={i} className="text-xs" style={{ color: entry.color }}>
            {entry.name}: {entry.value}
          </p>
        ))}
      </div>
    );
  }
  return null;
};

// ─── SLA helpers ─────────────────────────────────────────────────
function getSLAInfo(ticket: any) {
  if (!ticket.sla_deadline) return { text: 'No SLA', color: 'text-gray-500', urgent: false };
  const deadline = new Date(ticket.sla_deadline);
  const now = new Date();
  const hoursLeft = (deadline.getTime() - now.getTime()) / (1000 * 60 * 60);

  if (ticket.status === 'closed' || ticket.status === 'script_sent') {
    return { text: 'Completed', color: 'text-emerald-400', urgent: false };
  }
  if (hoursLeft <= 0) {
    return { text: 'SLA Breached', color: 'text-red-400', urgent: true };
  }
  if (hoursLeft <= 4) {
    return { text: `${Math.ceil(hoursLeft)}h left`, color: 'text-red-400', urgent: true };
  }
  if (hoursLeft <= 12) {
    return { text: `${Math.ceil(hoursLeft)}h left`, color: 'text-amber-400', urgent: false };
  }
  if (hoursLeft <= 24) {
    return { text: `${Math.ceil(hoursLeft)}h left`, color: 'text-yellow-400', urgent: false };
  }
  const days = Math.floor(hoursLeft / 24);
  const hrs = Math.ceil(hoursLeft % 24);
  return { text: `${days}d ${hrs}h left`, color: 'text-gray-400', urgent: false };
}

function formatDate(dateStr: string | null) {
  if (!dateStr) return '—';
  return new Date(dateStr).toLocaleDateString('en-IN', {
    day: 'numeric', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

// ─── Main page ───────────────────────────────────────────────────
type TabKey = 'queue' | 'departments' | 'analytics' | 'alerts' | 'agent_submitted';

export default function FeedbackTicketsPage() {
  const { user, isAdmin } = useAuth();
  const [activeTab, setActiveTab] = useState<TabKey>('queue');

  // Data fetching — NO auto-polling for tickets (user clicks Refresh or actions call refetch)
  const { data: ticketsRaw, loading: ticketsLoading, refetch: refetchTickets } = useAPI(
    () => api.listFeedbackTickets(isAdmin ? {} : { adm_id: String(user?.adm_id || '') }),
  );
  const { data: analytics, loading: analyticsLoading } = useAPI(() => api.getTicketAnalytics(), 120000);
  const { data: alertsRaw } = useAPI(() => api.getAggregationAlerts(), 120000);

  // Backend returns { tickets: [...], total } — extract the array
  const tickets = Array.isArray(ticketsRaw) ? ticketsRaw : (ticketsRaw?.tickets || []);
  const alerts = Array.isArray(alertsRaw) ? alertsRaw : (alertsRaw?.alerts || []);

  const tabs: { key: TabKey; label: string; icon: React.ElementType; count?: number }[] = [
    { key: 'queue', label: 'Ticket Queue', icon: Ticket, count: tickets.length },
    { key: 'departments', label: 'Department View', icon: Building2 },
    { key: 'analytics', label: 'Analytics', icon: TrendingUp },
    { key: 'alerts', label: 'Alerts', icon: AlertTriangle, count: (alerts || []).length },
    { key: 'agent_submitted', label: 'Agent Submitted', icon: User },
  ];

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Feedback Intelligence</h1>
          <p className="text-sm text-gray-400 mt-1">
            AI-classified tickets, departmental routing, and communication scripts
          </p>
        </div>
        <button
          onClick={() => refetchTickets()}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-surface-card border border-surface-border text-gray-300 hover:text-white hover:border-brand-red/30 transition-all text-sm"
        >
          <RotateCcw className="w-4 h-4" />
          Refresh
        </button>
      </div>

      {/* Tab Bar */}
      <div className="flex gap-1 bg-surface-card/50 rounded-xl p-1 border border-surface-border/50">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 ${
                isActive
                  ? 'bg-brand-red/10 text-white border border-brand-red/20'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-white/5 border border-transparent'
              }`}
            >
              <Icon className={`w-4 h-4 ${isActive ? 'text-brand-red' : ''}`} />
              {tab.label}
              {tab.count !== undefined && tab.count > 0 && (
                <span className={`ml-1 px-1.5 py-0.5 rounded-full text-[10px] font-bold ${
                  isActive ? 'bg-brand-red/20 text-brand-red' : 'bg-gray-700 text-gray-400'
                }`}>
                  {tab.count}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Tab Content */}
      {activeTab === 'queue' && <TicketQueue tickets={tickets} loading={ticketsLoading} refetch={refetchTickets} />}
      {activeTab === 'departments' && <DepartmentView refetch={refetchTickets} />}
      {activeTab === 'analytics' && <AnalyticsTab analytics={analytics} loading={analyticsLoading} tickets={tickets} />}
      {activeTab === 'alerts' && <AlertsTab alerts={alerts || []} />}
      {activeTab === 'agent_submitted' && <AgentSubmittedTab />}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// TAB 1: Ticket Queue
// ═══════════════════════════════════════════════════════════════════
function TicketQueue({ tickets, loading, refetch }: { tickets: any[]; loading: boolean; refetch: () => void }) {
  const [search, setSearch] = useState('');
  const [bucketFilter, setBucketFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [priorityFilter, setPriorityFilter] = useState('all');
  const [expandedTicket, setExpandedTicket] = useState<string | null>(null);

  const filtered = useMemo(() => {
    return tickets.filter((t: any) => {
      const matchSearch = search === '' ||
        (t.ticket_id || '').toLowerCase().includes(search.toLowerCase()) ||
        (t.agent_name || '').toLowerCase().includes(search.toLowerCase()) ||
        (t.adm_name || '').toLowerCase().includes(search.toLowerCase()) ||
        (t.parsed_summary || '').toLowerCase().includes(search.toLowerCase());
      const matchBucket = bucketFilter === 'all' || t.bucket === bucketFilter;
      const matchStatus = statusFilter === 'all' || t.status === statusFilter;
      const matchPriority = priorityFilter === 'all' || t.priority === priorityFilter;
      return matchSearch && matchBucket && matchStatus && matchPriority;
    });
  }, [tickets, search, bucketFilter, statusFilter, priorityFilter]);

  if (loading) {
    return <div className="flex items-center justify-center py-20"><Loader2 className="w-8 h-8 text-gray-500 animate-spin" /></div>;
  }

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="glass-card p-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search tickets, agents, summaries..."
              className="w-full pl-10 pr-4 py-2 bg-surface-card border border-surface-border rounded-lg text-sm text-white placeholder-gray-500 focus:outline-none focus:border-brand-red/40"
            />
          </div>
          <select value={bucketFilter} onChange={(e) => setBucketFilter(e.target.value)} className="input-dark text-sm py-2">
            <option value="all">All Departments</option>
            {Object.entries(BUCKETS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
          </select>
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="input-dark text-sm py-2">
            <option value="all">All Statuses</option>
            {Object.entries(STATUS_CONFIG).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
          </select>
          <select value={priorityFilter} onChange={(e) => setPriorityFilter(e.target.value)} className="input-dark text-sm py-2">
            <option value="all">All Priorities</option>
            {Object.entries(PRIORITY_CONFIG).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
          </select>
          <span className="text-xs text-gray-500">{filtered.length} tickets</span>
        </div>
      </div>

      {/* Ticket List */}
      {filtered.length === 0 ? (
        <div className="glass-card p-12 text-center">
          <Ticket className="w-12 h-12 text-gray-600 mx-auto mb-3" />
          <p className="text-gray-400">No tickets found</p>
          <p className="text-xs text-gray-500 mt-1">Tickets submitted via Telegram bot will appear here</p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((ticket: any) => (
            <TicketCard
              key={ticket.ticket_id || ticket.id}
              ticket={ticket}
              expanded={expandedTicket === (ticket.ticket_id || ticket.id)}
              onToggle={() => setExpandedTicket(
                expandedTicket === (ticket.ticket_id || ticket.id) ? null : (ticket.ticket_id || ticket.id)
              )}
              refetch={refetch}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Single Ticket Card ──────────────────────────────────────────
function TicketCard({ ticket, expanded, onToggle, refetch }: {
  ticket: any; expanded: boolean; onToggle: () => void; refetch: () => void;
}) {
  const [responding, setResponding] = useState(false);
  const [responseText, setResponseText] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const bucket = BUCKETS[ticket.bucket] || BUCKETS.operations;
  const priority = PRIORITY_CONFIG[ticket.priority] || PRIORITY_CONFIG.medium;
  const status = STATUS_CONFIG[ticket.status] || STATUS_CONFIG.received;
  const sla = getSLAInfo(ticket);
  const StatusIcon = status.icon;
  const BucketIcon = bucket.icon;

  const [scriptGenerating, setScriptGenerating] = useState(false);

  const handleRespond = async () => {
    if (!responseText.trim()) return;
    setSubmitting(true);
    try {
      const result = await api.respondToTicket(ticket.ticket_id || ticket.id, {
        response_text: responseText,
        responded_by: 'Department Team',
      });
      setResponseText('');
      setResponding(false);
      if (result?.script_status === 'generating') {
        setScriptGenerating(true);
        setTimeout(() => setScriptGenerating(false), 30000);
      }
      refetch();
    } catch (e: any) {
      alert(`Error: ${e.message}`);
    } finally {
      setSubmitting(false);
    }
  };

  const handleMarkSent = async () => {
    try {
      await api.markScriptSent(ticket.ticket_id || ticket.id);
      refetch();
    } catch (e: any) {
      alert(`Error: ${e.message}`);
    }
  };

  const handleRate = async (rating: string) => {
    try {
      await api.rateScript(ticket.ticket_id || ticket.id, { rating });
      refetch();
    } catch (e: any) {
      alert(`Error: ${e.message}`);
    }
  };

  return (
    <div className={`glass-card overflow-hidden transition-all duration-300 ${sla.urgent ? 'border-red-500/30' : ''}`}>
      {/* Header row */}
      <div
        className="flex items-center gap-4 p-4 cursor-pointer hover:bg-white/[0.02] transition-colors"
        onClick={onToggle}
      >
        {/* Ticket ID + Bucket */}
        <div className="flex items-center gap-3 min-w-[180px]">
          <div className={`p-2 rounded-lg ${bucket.bg}`}>
            <BucketIcon className={`w-4 h-4 ${bucket.color}`} />
          </div>
          <div>
            <p className="text-sm font-mono font-bold text-white">{ticket.ticket_id || `#${ticket.id}`}</p>
            <p className={`text-[11px] ${bucket.color}`}>{bucket.label}</p>
          </div>
        </div>

        {/* Summary */}
        <div className="flex-1 min-w-0">
          <p className="text-sm text-gray-200 truncate">{ticket.parsed_summary || ticket.raw_feedback_text || 'No summary'}</p>
          <div className="flex items-center gap-2 mt-0.5">
            <span className="text-[11px] text-gray-500">{ticket.agent_name || `Agent #${ticket.agent_id}`}</span>
            {ticket.adm_name && (
              <>
                <span className="text-gray-700">|</span>
                <span className="text-[11px] text-gray-500">{ticket.adm_name}</span>
              </>
            )}
          </div>
        </div>

        {/* Priority */}
        <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${priority.bg} ${priority.color} ${priority.border} border`}>
          {priority.label}
        </span>

        {/* Status */}
        <span className={`flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium ${status.bg} ${status.color}`}>
          <StatusIcon className="w-3 h-3" />
          {status.label}
        </span>

        {/* Messages badge */}
        {ticket.message_count > 0 && (
          <span className="flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-purple-500/10 text-purple-400">
            <MessageSquareText className="w-3 h-3" />
            {ticket.message_count}
          </span>
        )}

        {/* SLA */}
        <div className="flex items-center gap-1 min-w-[90px] justify-end">
          <Timer className={`w-3 h-3 ${sla.color}`} />
          <span className={`text-[11px] font-medium ${sla.color}`}>{sla.text}</span>
        </div>

        {/* Expand */}
        {expanded ? <ChevronUp className="w-4 h-4 text-gray-500" /> : <ChevronDown className="w-4 h-4 text-gray-500" />}
      </div>

      {/* Expanded Details */}
      {expanded && (
        <div className="border-t border-surface-border/50 p-4 space-y-4 bg-surface-card/30">
          {/* Detail Grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <DetailItem label="Reason" value={ticket.reason_display || ticket.reason_code || '—'} />
            <DetailItem label="Confidence" value={ticket.ai_confidence ? `${(ticket.ai_confidence * 100).toFixed(0)}%` : '—'} />
            <DetailItem label="Churn Risk" value={ticket.churn_risk || '—'} />
            <DetailItem label="Sentiment" value={ticket.sentiment || '—'} />
            <DetailItem label="Urgency Score" value={ticket.urgency_score ? `${ticket.urgency_score}/10` : '—'} />
            <DetailItem label="SLA Hours" value={ticket.sla_hours ? `${ticket.sla_hours}h` : '—'} />
            <DetailItem label="Created" value={formatDate(ticket.created_at)} />
            <DetailItem label="Channel" value={ticket.channel || '—'} />
          </div>

          {/* ADM Selected Reasons */}
          {Array.isArray(ticket.selected_reasons) && ticket.selected_reasons.length > 0 && (
            <div>
              <p className="text-[11px] text-gray-500 mb-1 flex items-center gap-1"><Tags className="w-3 h-3" /> ADM Selected Reasons</p>
              <div className="flex flex-wrap gap-1">
                {ticket.selected_reasons.map((r: any) => (
                  <span key={r.code || r} className="px-2 py-0.5 rounded text-[10px] font-bold bg-brand-red/10 border border-brand-red/20 text-brand-red" title={r.code || r}>
                    {r.name || r}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Secondary Reason Codes (AI-derived) */}
          {Array.isArray(ticket.secondary_reason_codes) && ticket.secondary_reason_codes.length > 0 && (
            <div>
              <p className="text-[11px] text-gray-500 mb-1">Secondary Reasons</p>
              <div className="flex flex-wrap gap-1">
                {ticket.secondary_reason_codes.map((r: any) => (
                  <span key={r.code || r} className="px-2 py-0.5 rounded text-[10px] bg-surface-card border border-surface-border text-gray-300" title={r.code || r}>
                    {r.name || r}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Raw Feedback */}
          {ticket.raw_feedback_text && (
            <div>
              <p className="text-[11px] text-gray-500 mb-1">Original Feedback</p>
              <p className="text-sm text-gray-300 bg-surface-card/50 rounded-lg p-3 border border-surface-border/30">
                {ticket.raw_feedback_text}
              </p>
            </div>
          )}

          {/* Voice Note Player */}
          {ticket.voice_file_id && (
            <div>
              <p className="text-[11px] text-gray-500 mb-1 flex items-center gap-1"><Mic className="w-3 h-3" /> Voice Note from ADM</p>
              <div className="flex items-center gap-3 bg-surface-card/50 rounded-lg p-3 border border-surface-border/30">
                <Mic className="w-5 h-5 text-purple-400 shrink-0" />
                <audio
                  controls
                  className="flex-1 h-8"
                  src={`${API_BASE}/feedback-tickets/${ticket.ticket_id}/voice`}
                >
                  Your browser does not support audio playback.
                </audio>
              </div>
            </div>
          )}

          {/* Conversation Thread */}
          <ConversationThread ticketId={ticket.ticket_id || ticket.id} ticket={ticket} refetch={refetch} isAdmin={true} />

          {/* Action Buttons */}
          <div className="flex flex-wrap gap-2 pt-2">
            {/* Respond button - show for any status that needs department action */}
            {['received', 'pending_dept', 'pending_adm', 'routed', 'classified'].includes(ticket.status) && !responding && (
              <button
                onClick={() => setResponding(true)}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-brand-red/10 border border-brand-red/20 text-brand-red hover:bg-brand-red/20 transition-all text-sm font-medium"
              >
                <MessageSquareText className="w-4 h-4" />
                Respond
              </button>
            )}

            {/* Mark script sent */}
            {ticket.status === 'script_generated' && (
              <button
                onClick={handleMarkSent}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 hover:bg-emerald-500/20 transition-all text-sm font-medium"
              >
                <Send className="w-4 h-4" />
                Mark Script Sent
              </button>
            )}

            {/* Rate script */}
            {ticket.status === 'script_sent' && !ticket.adm_script_rating && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-500">Rate script:</span>
                <button
                  onClick={() => handleRate('helpful')}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 hover:bg-emerald-500/20 transition-all text-xs"
                >
                  <ThumbsUp className="w-3 h-3" />
                  Helpful
                </button>
                <button
                  onClick={() => handleRate('not_helpful')}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 hover:bg-red-500/20 transition-all text-xs"
                >
                  <ThumbsDown className="w-3 h-3" />
                  Not Helpful
                </button>
              </div>
            )}

            {ticket.adm_script_rating && (
              <span className={`flex items-center gap-1 text-xs ${
                ticket.adm_script_rating === 'helpful' ? 'text-emerald-400' : 'text-red-400'
              }`}>
                {ticket.adm_script_rating === 'helpful' ? <ThumbsUp className="w-3 h-3" /> : <ThumbsDown className="w-3 h-3" />}
                Rated: {ticket.adm_script_rating}
              </span>
            )}

            {/* Script generating indicator */}
            {(scriptGenerating || ticket.status === 'responded') && !ticket.generated_script && (
              <span className="flex items-center gap-2 text-xs text-purple-400">
                <Loader2 className="w-3 h-3 animate-spin" />
                Script generating...
              </span>
            )}

            {/* Close ticket */}
            {ticket.status !== 'closed' && (
              <button
                onClick={async () => {
                  if (confirm('Close this ticket?')) {
                    try {
                      await api.closeTicket(ticket.ticket_id || ticket.id);
                      refetch();
                    } catch (e: any) { alert(`Error: ${e.message}`); }
                  }
                }}
                className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-gray-500/10 border border-gray-500/20 text-gray-400 hover:bg-gray-500/20 transition-all text-xs"
              >
                <XCircle className="w-3 h-3" />
                Close
              </button>
            )}

            {/* Reopen ticket */}
            {ticket.status === 'closed' && (
              <button
                onClick={async () => {
                  try {
                    await api.reopenTicket(ticket.ticket_id || ticket.id);
                    refetch();
                  } catch (e: any) { alert(`Error: ${e.message}`); }
                }}
                className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400 hover:bg-amber-500/20 transition-all text-xs"
              >
                <RotateCcw className="w-3 h-3" />
                Reopen
              </button>
            )}
          </div>

          {/* Response Form */}
          {responding && (
            <div className="space-y-3 p-4 bg-surface-card/50 rounded-lg border border-brand-red/20">
              <p className="text-sm font-medium text-white">Department Response</p>
              <textarea
                value={responseText}
                onChange={(e) => setResponseText(e.target.value)}
                placeholder="Type the department's response to this feedback..."
                className="w-full h-32 bg-surface-card border border-surface-border rounded-lg p-3 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-brand-red/40 resize-none"
              />
              <div className="flex gap-2">
                <button
                  onClick={handleRespond}
                  disabled={submitting || !responseText.trim()}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-brand-red text-white text-sm font-medium hover:bg-brand-red/90 disabled:opacity-50 transition-all"
                >
                  {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                  Submit Response
                </button>
                <button
                  onClick={() => { setResponding(false); setResponseText(''); }}
                  className="px-4 py-2 rounded-lg bg-surface-card border border-surface-border text-gray-400 hover:text-white text-sm transition-all"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function DetailItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[10px] text-gray-500 uppercase tracking-wider">{label}</p>
      <p className="text-sm text-gray-200 font-medium capitalize">{value}</p>
    </div>
  );
}

// ─── Conversation Thread ─────────────────────────────────────────
function ConversationThread({ ticketId, ticket, refetch, isAdmin }: { ticketId: string; ticket: any; refetch: () => void; isAdmin?: boolean }) {
  const [messages, setMessages] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [newMessage, setNewMessage] = useState('');
  const [messageType, setMessageType] = useState<'text' | 'clarification_request'>('text');
  const [sending, setSending] = useState(false);
  const [showCompose, setShowCompose] = useState(false);
  const threadEndRef = useRef<HTMLDivElement>(null);

  // Fetch messages
  const fetchMessages = useCallback(async () => {
    try {
      const data = await api.getTicketMessages(ticketId);
      const msgs = Array.isArray(data) ? data : (data?.messages || []);
      setMessages(msgs);
    } catch {
      // Fallback: build from denormalized fields if endpoint fails
      const fallback: any[] = [];
      if (ticket.raw_feedback_text) {
        fallback.push({
          id: 'fb-1',
          sender_type: 'adm',
          sender_name: ticket.adm_name || 'ADM',
          message_text: ticket.raw_feedback_text,
          message_type: 'text',
          created_at: ticket.created_at,
        });
      }
      if (ticket.department_response_text) {
        fallback.push({
          id: 'dept-1',
          sender_type: 'department',
          sender_name: ticket.department_responded_by || 'Department',
          message_text: ticket.department_response_text,
          message_type: 'text',
          created_at: ticket.department_responded_at || ticket.updated_at,
        });
      }
      if (ticket.generated_script) {
        fallback.push({
          id: 'ai-1',
          sender_type: 'ai',
          sender_name: 'AI Script Generator',
          message_text: ticket.generated_script,
          message_type: 'script',
          created_at: ticket.updated_at,
        });
      }
      setMessages(fallback);
    } finally {
      setLoading(false);
    }
  }, [ticketId, ticket]);

  useEffect(() => {
    fetchMessages();
    // Only poll when user is NOT composing a message — don't interrupt their work
    if (!showCompose) {
      const interval = setInterval(fetchMessages, 30000);
      return () => clearInterval(interval);
    }
  }, [fetchMessages, showCompose]);

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length]);

  const handleSendMessage = async () => {
    if (!newMessage.trim()) return;
    setSending(true);
    try {
      await api.addTicketMessage(ticketId, {
        sender_type: isAdmin ? 'department' : 'department',
        sender_name: isAdmin ? 'Department Team' : 'Department Team',
        message_text: newMessage.trim(),
        message_type: messageType,
      });
      setNewMessage('');
      setShowCompose(false);
      setMessageType('text');
      await fetchMessages();
      refetch();
    } catch (e: any) {
      alert(`Error: ${e.message}`);
    } finally {
      setSending(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-6">
        <Loader2 className="w-5 h-5 text-gray-500 animate-spin" />
        <span className="ml-2 text-sm text-gray-500">Loading conversation...</span>
      </div>
    );
  }

  if (messages.length === 0) {
    return (
      <div className="text-center py-4">
        <MessageSquareText className="w-8 h-8 text-gray-600 mx-auto mb-2" />
        <p className="text-sm text-gray-500">No conversation history</p>
      </div>
    );
  }

  const getMessageStyle = (msg: any) => {
    switch (msg.sender_type) {
      case 'adm':
        return {
          align: 'justify-start',
          bubble: 'bg-blue-500/10 border-blue-500/20',
          text: 'text-blue-200',
          label: 'text-blue-400',
          icon: User,
          iconBg: 'bg-blue-500/20',
          iconColor: 'text-blue-400',
        };
      case 'department':
        return {
          align: 'justify-end',
          bubble: 'bg-emerald-500/10 border-emerald-500/20',
          text: 'text-emerald-200',
          label: 'text-emerald-400',
          icon: Building2,
          iconBg: 'bg-emerald-500/20',
          iconColor: 'text-emerald-400',
        };
      case 'ai':
        return {
          align: 'justify-center',
          bubble: 'bg-purple-500/10 border-purple-500/20',
          text: 'text-purple-200',
          label: 'text-purple-400',
          icon: Bot,
          iconBg: 'bg-purple-500/20',
          iconColor: 'text-purple-400',
        };
      case 'system':
      default:
        return {
          align: 'justify-center',
          bubble: 'bg-gray-500/10 border-gray-500/20',
          text: 'text-gray-300',
          label: 'text-gray-400',
          icon: Settings,
          iconBg: 'bg-gray-500/20',
          iconColor: 'text-gray-400',
        };
    }
  };

  const getMessageTypeLabel = (msg: any) => {
    switch (msg.message_type) {
      case 'script': return '📝 Communication Script';
      case 'status_change': return '🔄 Status Update';
      case 'clarification_request': return '❓ Clarification Requested';
      case 'escalation': return '🚨 Escalation';
      case 'voice': return '🎤 Voice Note';
      case 'photo': return '📷 Photo';
      case 'document': return '📎 Document';
      default: return null;
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <p className="text-[11px] text-gray-500 flex items-center gap-1">
          <MessageSquareText className="w-3 h-3" />
          Conversation Thread ({messages.length} messages)
        </p>
        {ticket.status !== 'closed' && (
          <div className="flex items-center gap-2">
            <button
              onClick={() => { setShowCompose(true); setMessageType('clarification_request'); }}
              className="flex items-center gap-1 px-2 py-1 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400 hover:bg-amber-500/20 transition-all text-[11px]"
            >
              <HelpCircle className="w-3 h-3" />
              Request Clarification
            </button>
            <button
              onClick={() => { setShowCompose(true); setMessageType('text'); }}
              className="flex items-center gap-1 px-2 py-1 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 hover:bg-emerald-500/20 transition-all text-[11px]"
            >
              <Plus className="w-3 h-3" />
              Add Message
            </button>
          </div>
        )}
      </div>

      <div className="space-y-3 max-h-[400px] overflow-y-auto pr-1 scrollbar-thin">
        {messages.map((msg: any) => {
          const style = getMessageStyle(msg);
          const MsgIcon = style.icon;
          const typeLabel = getMessageTypeLabel(msg);
          const isSystem = msg.sender_type === 'system';
          const isScript = msg.message_type === 'script';

          // System messages are compact centered rows
          if (isSystem) {
            return (
              <div key={msg.id} className="flex justify-center">
                <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-gray-500/5 border border-gray-500/10">
                  <Settings className="w-3 h-3 text-gray-500" />
                  <span className="text-[11px] text-gray-400">{msg.message_text}</span>
                  <span className="text-[10px] text-gray-600">{formatDate(msg.created_at)}</span>
                </div>
              </div>
            );
          }

          return (
            <div key={msg.id} className={`flex ${style.align}`}>
              <div className={`max-w-[85%] ${isScript ? 'w-full' : ''}`}>
                {/* Sender header */}
                <div className={`flex items-center gap-2 mb-1 ${msg.sender_type === 'department' ? 'flex-row-reverse' : ''}`}>
                  <div className={`w-5 h-5 rounded-full flex items-center justify-center ${style.iconBg}`}>
                    <MsgIcon className={`w-3 h-3 ${style.iconColor}`} />
                  </div>
                  <span className={`text-[10px] font-medium ${style.label}`}>
                    {msg.sender_name || msg.sender_type}
                  </span>
                  {typeLabel && (
                    <span className="text-[10px] text-gray-500">{typeLabel}</span>
                  )}
                  <span className="text-[10px] text-gray-600">{formatDate(msg.created_at)}</span>
                </div>
                {/* Message bubble */}
                <div className={`rounded-lg p-3 border ${style.bubble}`}>
                  {isScript ? (
                    <pre className={`text-sm whitespace-pre-wrap font-sans ${style.text}`}>{msg.message_text}</pre>
                  ) : (
                    <p className={`text-sm ${style.text}`}>{msg.message_text}</p>
                  )}
                  {msg.voice_file_id && msg.message_type === 'voice' && (
                    <div className="mt-2 flex items-center gap-2">
                      <Mic className="w-4 h-4 text-purple-400" />
                      <audio
                        controls
                        className="flex-1 h-7"
                        src={`${API_BASE}/feedback-tickets/${ticketId}/voice`}
                      >
                        Audio not supported.
                      </audio>
                    </div>
                  )}
                  {msg.message_type === 'photo' && msg.voice_file_id && (
                    <a
                      href={`${API_BASE}/feedback-tickets/telegram-file/${msg.voice_file_id}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-2 flex items-center gap-2 text-blue-400 hover:text-blue-300 transition-colors cursor-pointer"
                    >
                      <span className="text-sm">📷</span>
                      <span className="text-[11px] underline">View Photo</span>
                    </a>
                  )}
                  {msg.message_type === 'photo' && !msg.voice_file_id && (
                    <div className="mt-2 flex items-center gap-2 text-gray-400">
                      <span className="text-sm">📷</span>
                      <span className="text-[11px]">Photo attached</span>
                    </div>
                  )}
                  {msg.message_type === 'document' && (
                    <div className="mt-2">
                      {(() => {
                        let fileName = 'Document attached';
                        try {
                          const meta = msg.metadata_json ? JSON.parse(msg.metadata_json) : {};
                          fileName = meta.file_name || 'Document attached';
                        } catch { /* ignore */ }
                        const fileId = msg.voice_file_id;
                        if (fileId) {
                          return (
                            <a
                              href={`${API_BASE}/feedback-tickets/telegram-file/${fileId}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="flex items-center gap-2 text-blue-400 hover:text-blue-300 transition-colors cursor-pointer"
                            >
                              <span className="text-sm">📎</span>
                              <span className="text-[11px] underline">{fileName}</span>
                              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                            </a>
                          );
                        }
                        return (
                          <div className="flex items-center gap-2 text-gray-400">
                            <span className="text-sm">📎</span>
                            <span className="text-[11px]">{fileName}</span>
                          </div>
                        );
                      })()}
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
        <div ref={threadEndRef} />
      </div>

      {/* Compose area */}
      {showCompose && (
        <div className="mt-3 p-3 bg-surface-card/50 rounded-lg border border-surface-border/30 space-y-2">
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-gray-500">
              {messageType === 'clarification_request' ? '❓ Requesting Clarification from ADM' : '💬 New Message'}
            </span>
          </div>
          <textarea
            value={newMessage}
            onChange={(e) => setNewMessage(e.target.value)}
            placeholder={
              messageType === 'clarification_request'
                ? 'Ask the ADM for additional details...'
                : 'Type your message...'
            }
            className="w-full h-20 bg-surface-card border border-surface-border rounded-lg p-3 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-brand-red/40 resize-none"
          />
          <div className="flex gap-2">
            <button
              onClick={handleSendMessage}
              disabled={sending || !newMessage.trim()}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all disabled:opacity-50 ${
                messageType === 'clarification_request'
                  ? 'bg-amber-500/20 border border-amber-500/30 text-amber-300 hover:bg-amber-500/30'
                  : 'bg-emerald-500/20 border border-emerald-500/30 text-emerald-300 hover:bg-emerald-500/30'
              }`}
            >
              {sending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
              {messageType === 'clarification_request' ? 'Send Clarification Request' : 'Send Message'}
            </button>
            <button
              onClick={() => { setShowCompose(false); setNewMessage(''); setMessageType('text'); }}
              className="px-4 py-2 rounded-lg bg-surface-card border border-surface-border text-gray-400 hover:text-white text-sm transition-all"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// TAB 2: Department View
// ═══════════════════════════════════════════════════════════════════
function DepartmentView({ refetch }: { refetch: () => void }) {
  const [selectedDept, setSelectedDept] = useState<string>('underwriting');
  const { data: queueData, loading, refetch: refetchQueue } = useAPI(
    () => api.getDepartmentQueue(selectedDept),
    30000,
    [selectedDept],
  );

  // Backend returns { tickets: [...], total, department } — extract the array
  const queue = Array.isArray(queueData) ? queueData : (queueData?.tickets || []);
  const deptConfig = BUCKETS[selectedDept] || BUCKETS.operations;
  const DeptIcon = deptConfig.icon;

  return (
    <div className="space-y-4">
      {/* Department Selector */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {Object.entries(BUCKETS).map(([key, config]) => {
          const Icon = config.icon;
          const isActive = selectedDept === key;
          return (
            <button
              key={key}
              onClick={() => setSelectedDept(key)}
              className={`glass-card p-4 text-center transition-all duration-200 ${
                isActive ? `${config.border} border-2 ${config.bg}` : 'hover:bg-white/[0.02]'
              }`}
            >
              <Icon className={`w-6 h-6 mx-auto mb-2 ${isActive ? config.color : 'text-gray-500'}`} />
              <p className={`text-xs font-medium ${isActive ? 'text-white' : 'text-gray-400'}`}>{config.label}</p>
            </button>
          );
        })}
      </div>

      {/* Queue Header */}
      <div className="glass-card p-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className={`p-2 rounded-lg ${deptConfig.bg}`}>
            <DeptIcon className={`w-5 h-5 ${deptConfig.color}`} />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-white">{deptConfig.label} Queue</h3>
            <p className="text-xs text-gray-400">{queue.length} tickets in queue</p>
          </div>
        </div>
        <button
          onClick={() => refetchQueue()}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-surface-card border border-surface-border text-gray-400 hover:text-white text-xs transition-all"
        >
          <RotateCcw className="w-3 h-3" />
          Refresh
        </button>
      </div>

      {/* Queue Items */}
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-6 h-6 text-gray-500 animate-spin" />
        </div>
      ) : queue.length === 0 ? (
        <div className="glass-card p-12 text-center">
          <CheckCircle2 className="w-10 h-10 text-emerald-400/50 mx-auto mb-3" />
          <p className="text-gray-400">No pending tickets</p>
          <p className="text-xs text-gray-500 mt-1">All caught up in {deptConfig.label}</p>
        </div>
      ) : (
        <div className="space-y-3">
          {queue.map((item: any) => {
            const ticket = item.ticket || item;
            const priority = PRIORITY_CONFIG[ticket.priority] || PRIORITY_CONFIG.medium;
            const status = STATUS_CONFIG[ticket.status] || STATUS_CONFIG.received;
            const sla = getSLAInfo(ticket);
            const StatusIcon = status.icon;

            return (
              <div key={ticket.ticket_id || ticket.id} className={`glass-card p-4 ${sla.urgent ? 'border-red-500/30' : ''}`}>
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-mono font-bold text-white">{ticket.ticket_id || `#${ticket.id}`}</span>
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${priority.bg} ${priority.color} ${priority.border} border`}>
                      {priority.label}
                    </span>
                    <span className={`flex items-center gap-1 text-[11px] ${status.color}`}>
                      <StatusIcon className="w-3 h-3" />
                      {status.label}
                    </span>
                  </div>
                  <div className="flex items-center gap-1">
                    <Timer className={`w-3 h-3 ${sla.color}`} />
                    <span className={`text-[11px] font-medium ${sla.color}`}>{sla.text}</span>
                  </div>
                </div>
                <p className="text-sm text-gray-300 mb-1">{ticket.parsed_summary || ticket.raw_feedback_text || 'No summary'}</p>
                <div className="flex items-center gap-2 text-[11px] text-gray-500">
                  <span>Reason: {ticket.reason_display || ticket.reason_code}</span>
                  <span className="text-gray-700">|</span>
                  <span>{ticket.agent_name || `Agent #${ticket.agent_id}`}</span>
                  <span className="text-gray-700">|</span>
                  <span>{formatDate(ticket.created_at)}</span>
                </div>
                {item.assigned_to && (
                  <p className="text-[11px] text-gray-500 mt-1">Assigned to: {item.assigned_to}</p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// TAB 3: Analytics
// ═══════════════════════════════════════════════════════════════════
function AnalyticsTab({ analytics, loading, tickets }: { analytics: any; loading: boolean; tickets: any[] }) {
  if (loading || !analytics) {
    return <div className="flex items-center justify-center py-20"><Loader2 className="w-8 h-8 text-gray-500 animate-spin" /></div>;
  }

  // Backend by_bucket format: { key: { count: N, display: "..." } } or { key: N }
  const bucketData = analytics.by_bucket
    ? Object.entries(analytics.by_bucket).map(([key, val]: [string, any], i) => ({
        name: BUCKETS[key]?.label || (typeof val === 'object' ? val.display : key),
        value: (typeof val === 'object' ? val.count : val) as number,
        color: PIE_COLORS[i % PIE_COLORS.length],
      }))
    : [];

  const priorityData = analytics.by_priority
    ? Object.entries(analytics.by_priority).map(([key, count]) => ({
        name: PRIORITY_CONFIG[key]?.label || key,
        count: count as number,
        fill: key === 'critical' ? '#EF4444' : key === 'high' ? '#F97316' : key === 'medium' ? '#F59E0B' : '#6B7280',
      }))
    : [];

  const statusData = analytics.by_status
    ? Object.entries(analytics.by_status).map(([key, count], i) => ({
        name: STATUS_CONFIG[key]?.label || key,
        value: count as number,
        color: PIE_COLORS[i % PIE_COLORS.length],
      }))
    : [];

  // Backend returns top_reason_codes: [{ code, name, count }] — map to expected format
  const topReasons = (analytics.top_reason_codes || analytics.top_reasons || []).map((item: any) => ({
    reason_code: item.reason_code || item.code || item.reason,
    reason_name: item.name || item.reason_name || item.reason_code || item.code || item.reason,
    count: item.count || 0,
  }));
  const slaCompliance = analytics.sla_compliance_pct ?? analytics.sla_compliance ?? 0;
  const totalTickets = analytics.total_tickets ?? tickets.length;
  const openTickets = tickets.filter((t: any) => !['closed', 'script_sent'].includes(t.status)).length;
  const avgResolution = analytics.avg_resolution_hours || 0;

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <StatCard title="Total Tickets" value={totalTickets} icon={Ticket} color="red" />
        <StatCard title="Open Tickets" value={openTickets} icon={Clock} color="amber" />
        <StatCard title="SLA Compliance" value={slaCompliance} suffix="%" icon={CheckCircle2} color="green" />
        <StatCard title="Avg Resolution" value={Math.round(avgResolution)} suffix="h" icon={Timer} color="blue" />
      </div>

      {/* Charts Row 1 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* By Bucket Pie */}
        <ChartCard title="Tickets by Department" subtitle="Distribution across departments">
          <div className="h-[300px] flex items-center">
            <div className="w-1/2">
              <ResponsiveContainer width="100%" height={260}>
                <PieChart>
                  <Pie data={bucketData} cx="50%" cy="50%" innerRadius={55} outerRadius={90} paddingAngle={4} dataKey="value" stroke="none">
                    {bucketData.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                  </Pie>
                  <Tooltip content={<CustomTooltip />} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="w-1/2 space-y-3">
              {bucketData.map((item) => (
                <div key={item.name} className="flex items-center gap-3">
                  <span className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: item.color }} />
                  <div className="flex-1">
                    <p className="text-sm text-gray-300">{item.name}</p>
                    <p className="text-xs text-gray-500">{item.value} tickets</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </ChartCard>

        {/* By Priority Bar */}
        <ChartCard title="Tickets by Priority" subtitle="Priority distribution">
          <div className="h-[300px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={priorityData} margin={{ top: 5, right: 30, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1F2937" />
                <XAxis dataKey="name" tick={{ fill: '#9CA3AF', fontSize: 12 }} />
                <YAxis tick={{ fill: '#9CA3AF', fontSize: 12 }} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="count" name="Tickets" radius={[6, 6, 0, 0]} barSize={40}>
                  {priorityData.map((entry, i) => <Cell key={i} fill={entry.fill} fillOpacity={0.85} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </ChartCard>
      </div>

      {/* Charts Row 2 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* By Status Pie */}
        <ChartCard title="Tickets by Status" subtitle="Current pipeline">
          <div className="h-[280px] flex items-center">
            <div className="w-1/2">
              <ResponsiveContainer width="100%" height={240}>
                <PieChart>
                  <Pie data={statusData} cx="50%" cy="50%" innerRadius={50} outerRadius={85} paddingAngle={3} dataKey="value" stroke="none">
                    {statusData.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                  </Pie>
                  <Tooltip content={<CustomTooltip />} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="w-1/2 space-y-2">
              {statusData.map((item) => (
                <div key={item.name} className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: item.color }} />
                  <span className="text-xs text-gray-300 flex-1">{item.name}</span>
                  <span className="text-xs font-bold text-white">{item.value}</span>
                </div>
              ))}
            </div>
          </div>
        </ChartCard>

        {/* Top Reasons */}
        <ChartCard title="Top Reasons" subtitle="Most frequent feedback reasons">
          <div className="space-y-3 max-h-[280px] overflow-y-auto pr-1">
            {topReasons.length === 0 ? (
              <p className="text-sm text-gray-500 text-center py-4">No data yet</p>
            ) : (
              topReasons.map((item: any, i: number) => (
                <div key={item.reason_code || i} className="flex items-center gap-3">
                  <span className="text-xs text-gray-500 w-5 text-right">{i + 1}</span>
                  <span className="px-2 py-0.5 rounded text-[10px] bg-surface-card border border-surface-border text-gray-300 text-center truncate max-w-[180px]" title={`${item.reason_code}: ${item.reason_name}`}>
                    {item.reason_name}
                  </span>
                  <div className="flex-1">
                    <div className="h-2 bg-surface-card rounded-full overflow-hidden">
                      <div
                        className="h-full bg-brand-red/60 rounded-full"
                        style={{ width: `${Math.min(100, (item.count / (topReasons[0]?.count || 1)) * 100)}%` }}
                      />
                    </div>
                  </div>
                  <span className="text-xs font-bold text-white min-w-[30px] text-right">{item.count}</span>
                </div>
              ))
            )}
          </div>
        </ChartCard>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// TAB 4: Alerts
// ═══════════════════════════════════════════════════════════════════
function AlertsTab({ alerts }: { alerts: any[] }) {
  if (alerts.length === 0) {
    return (
      <div className="glass-card p-12 text-center">
        <CheckCircle2 className="w-12 h-12 text-emerald-400/50 mx-auto mb-3" />
        <p className="text-gray-400 text-lg font-medium">No Active Alerts</p>
        <p className="text-xs text-gray-500 mt-1">
          Alerts are generated when the system detects recurring patterns (5+ similar tickets in 30 days)
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {alerts.map((alert: any) => {
        const bucket = BUCKETS[alert.bucket] || BUCKETS.operations;
        const BucketIcon = bucket.icon;

        return (
          <div
            key={alert.id}
            className={`glass-card p-5 border-l-4 ${
              alert.auto_escalated ? 'border-l-red-500' : 'border-l-amber-500'
            }`}
          >
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center gap-3">
                <div className={`p-2 rounded-lg ${alert.auto_escalated ? 'bg-red-500/10' : 'bg-amber-500/10'}`}>
                  <AlertTriangle className={`w-5 h-5 ${alert.auto_escalated ? 'text-red-400' : 'text-amber-400'}`} />
                </div>
                <div>
                  <p className="text-sm font-semibold text-white">{alert.description}</p>
                  <div className="flex items-center gap-2 mt-0.5">
                    <BucketIcon className={`w-3 h-3 ${bucket.color}`} />
                    <span className={`text-[11px] ${bucket.color}`}>{bucket.label}</span>
                    {alert.reason_code && (
                      <>
                        <span className="text-gray-700">|</span>
                        <span className="text-[11px] text-gray-400">{alert.reason_name || alert.reason_code}</span>
                      </>
                    )}
                    {alert.region && (
                      <>
                        <span className="text-gray-700">|</span>
                        <span className="text-[11px] text-gray-400">{alert.region}</span>
                      </>
                    )}
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2">
                {alert.auto_escalated && (
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-red-500/10 text-red-400 border border-red-500/20">
                    Auto-Escalated
                  </span>
                )}
                <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${
                  alert.status === 'active' ? 'bg-amber-500/10 text-amber-400' : 'bg-gray-500/10 text-gray-400'
                }`}>
                  {alert.status}
                </span>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-4">
              <div>
                <p className="text-[10px] text-gray-500 uppercase">Pattern</p>
                <p className="text-sm text-gray-200">{alert.pattern_type}</p>
              </div>
              <div>
                <p className="text-[10px] text-gray-500 uppercase">Affected Tickets</p>
                <p className="text-sm text-gray-200">{alert.affected_ticket_count ?? alert.affected_agents_count ?? 0}</p>
              </div>
              <div>
                <p className="text-[10px] text-gray-500 uppercase">Agents Impacted</p>
                <p className="text-sm text-gray-200">{alert.affected_agent_count ?? alert.affected_adms_count ?? 0}</p>
              </div>
            </div>

            {alert.ticket_ids && alert.ticket_ids.length > 0 && (
              <div className="mt-3">
                <p className="text-[10px] text-gray-500 uppercase mb-1">Related Tickets</p>
                <div className="flex flex-wrap gap-1">
                  {(typeof alert.ticket_ids === 'string' ? JSON.parse(alert.ticket_ids) : alert.ticket_ids).map((tid: string) => (
                    <span key={tid} className="px-2 py-0.5 rounded text-[10px] font-mono bg-surface-card border border-surface-border text-gray-300">
                      {tid}
                    </span>
                  ))}
                </div>
              </div>
            )}

            <p className="text-[11px] text-gray-500 mt-2">{formatDate(alert.created_at)}</p>
          </div>
        );
      })}
    </div>
  );
}


// ─── Agent Submitted Tab ─────────────────────────────────────────
function AgentSubmittedTab() {
  const [selectedBucket, setSelectedBucket] = useState<string>('all');
  const [tickets, setTickets] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedTicket, setSelectedTicket] = useState<any>(null);
  const [ticketMessages, setTicketMessages] = useState<any[]>([]);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [responseText, setResponseText] = useState('');
  const [responding, setResponding] = useState(false);
  const [responseSuccess, setResponseSuccess] = useState('');

  const fetchTickets = useCallback(async () => {
    setLoading(true);
    try {
      const buckets = selectedBucket === 'all'
        ? ['underwriting', 'finance', 'contest', 'operations', 'product']
        : [selectedBucket];
      const allTickets: any[] = [];
      for (const b of buckets) {
        try {
          const data = await api.getAgentSubmittedByDept(b);
          const arr = Array.isArray(data) ? data : (data?.tickets || []);
          allTickets.push(...arr);
        } catch {
          // bucket might have no tickets
        }
      }
      setTickets(allTickets);
    } catch {
      setTickets([]);
    } finally {
      setLoading(false);
    }
  }, [selectedBucket]);

  useEffect(() => { fetchTickets(); }, [fetchTickets]);

  const fetchTicketDetail = useCallback(async (ticketId: string) => {
    setMessagesLoading(true);
    try {
      const data = await api.getAgentTicketDetail(ticketId);
      setTicketMessages(data?.messages || []);
    } catch {
      setTicketMessages([]);
    } finally {
      setMessagesLoading(false);
    }
  }, []);

  const handleToggleTicket = useCallback((ticket: any) => {
    if (selectedTicket?.id === ticket.id) {
      setSelectedTicket(null);
      setTicketMessages([]);
    } else {
      setSelectedTicket(ticket);
      fetchTicketDetail(ticket.ticket_id);
    }
  }, [selectedTicket, fetchTicketDetail]);

  const handleRespond = async (ticketId: string) => {
    if (!responseText.trim()) return;
    setResponding(true);
    try {
      await api.respondToAgentTicket(ticketId, responseText, 'Admin');
      setResponseSuccess('Response sent to agent');
      setResponseText('');
      fetchTicketDetail(ticketId);
      fetchTickets();
      setTimeout(() => setResponseSuccess(''), 3000);
    } catch (e: any) {
      alert(e.message || 'Failed to respond');
    } finally {
      setResponding(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {responseSuccess && (
        <div className="flex items-center gap-2 px-4 py-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          <span className="text-sm text-emerald-400">{responseSuccess}</span>
        </div>
      )}

      {/* Bucket filters */}
      <div className="flex gap-2 flex-wrap">
        <button
          onClick={() => setSelectedBucket('all')}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
            selectedBucket === 'all'
              ? 'bg-brand-red/10 text-white border border-brand-red/20'
              : 'text-gray-400 hover:text-white bg-surface-card border border-surface-border'
          }`}
        >
          All ({tickets.length})
        </button>
        {Object.entries(BUCKETS).map(([key, cfg]) => {
          const Icon = cfg.icon;
          return (
            <button
              key={key}
              onClick={() => setSelectedBucket(key)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                selectedBucket === key
                  ? `${cfg.bg} ${cfg.color} border ${cfg.border}`
                  : 'text-gray-400 hover:text-white bg-surface-card border border-surface-border'
              }`}
            >
              <Icon className="w-3 h-3" />
              {cfg.label}
            </button>
          );
        })}
      </div>

      {tickets.length === 0 ? (
        <div className="text-center py-16">
          <User className="w-10 h-10 text-gray-600 mx-auto mb-3" />
          <p className="text-gray-400 text-sm">No agent-submitted tickets yet</p>
          <p className="text-gray-500 text-xs mt-1">Tickets submitted by agents via Telegram will appear here</p>
        </div>
      ) : (
        <div className="space-y-3">
          {tickets.map((ticket: any) => {
            const bucket = BUCKETS[ticket.bucket] || BUCKETS.operations;
            const BucketIcon = bucket.icon;
            const status = STATUS_CONFIG[ticket.status] || STATUS_CONFIG.received;
            const StatusIcon = status.icon;
            const priority = PRIORITY_CONFIG[ticket.priority] || PRIORITY_CONFIG.medium;
            const isExpanded = selectedTicket?.id === ticket.id;

            return (
              <div key={ticket.id} className="glass-card p-4">
                <div
                  className="flex items-start gap-4 cursor-pointer"
                  onClick={() => handleToggleTicket(ticket)}
                >
                  <div className={`p-2 rounded-lg ${bucket.bg}`}>
                    <BucketIcon className={`w-4 h-4 ${bucket.color}`} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs font-mono text-gray-500">{ticket.ticket_id}</span>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${status.bg} ${status.color}`}>
                        {status.label}
                      </span>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${priority.bg} ${priority.color}`}>
                        {priority.label}
                      </span>
                      {(ticket.message_count || 0) > 1 && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-blue-500/10 text-blue-400">
                          {ticket.message_count} messages
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-white">
                      {ticket.agent_name || 'Agent'} — {bucket.label}
                    </p>
                    <p className="text-xs text-gray-400 mt-1 line-clamp-2">
                      {ticket.raw_feedback_text || ticket.parsed_summary || 'No details'}
                    </p>
                  </div>
                  <div className="text-right flex-shrink-0">
                    <p className="text-[11px] text-gray-500">{formatDate(ticket.created_at)}</p>
                    {isExpanded ? <ChevronUp className="w-4 h-4 text-gray-500 mt-1" /> : <ChevronDown className="w-4 h-4 text-gray-500 mt-1" />}
                  </div>
                </div>

                {isExpanded && (
                  <div className="mt-4 pt-4 border-t border-surface-border/30 space-y-3">
                    <div className="grid grid-cols-2 gap-3 text-xs">
                      <div><span className="text-gray-500">Reason:</span> <span className="text-gray-300">{ticket.reason_display || ticket.reason_code || '—'}</span></div>
                      <div><span className="text-gray-500">Channel:</span> <span className="text-gray-300">{ticket.channel || 'telegram'}</span></div>
                      <div><span className="text-gray-500">Sentiment:</span> <span className="text-gray-300">{ticket.sentiment || '—'}</span></div>
                      <div><span className="text-gray-500">Churn Risk:</span> <span className="text-gray-300">{ticket.churn_risk || '—'}</span></div>
                    </div>

                    {ticket.parsed_summary && (
                      <div className="p-3 rounded-lg bg-blue-500/5 border border-blue-500/10">
                        <p className="text-[10px] text-blue-400 font-medium mb-1">AI Summary:</p>
                        <p className="text-xs text-gray-300">{ticket.parsed_summary}</p>
                      </div>
                    )}

                    {/* Conversation Thread */}
                    <div>
                      <p className="text-[10px] text-gray-500 font-medium mb-2 uppercase tracking-wide">Conversation</p>
                      {messagesLoading ? (
                        <div className="flex items-center gap-2 py-3">
                          <Loader2 className="w-3 h-3 animate-spin text-gray-500" />
                          <span className="text-xs text-gray-500">Loading messages...</span>
                        </div>
                      ) : ticketMessages.length === 0 ? (
                        <p className="text-xs text-gray-600 py-2">No messages yet</p>
                      ) : (
                        <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
                          {ticketMessages.map((msg: any) => {
                            const isAgent = msg.sender_type === 'agent';
                            const isDept = msg.sender_type === 'department';
                            return (
                              <div
                                key={msg.id}
                                className={`flex ${isDept ? 'justify-start' : 'justify-end'}`}
                              >
                                <div className={`max-w-[80%] p-2.5 rounded-lg text-xs ${
                                  isDept
                                    ? 'bg-emerald-500/10 border border-emerald-500/20'
                                    : 'bg-blue-500/15 border border-blue-500/25'
                                }`}>
                                  <div className="flex items-center gap-1.5 mb-1">
                                    {isDept ? (
                                      <Building2 className="w-3 h-3 text-emerald-400" />
                                    ) : (
                                      <User className="w-3 h-3 text-blue-400" />
                                    )}
                                    <span className={`text-[10px] font-medium ${isDept ? 'text-emerald-400' : 'text-blue-400'}`}>
                                      {msg.sender_name}
                                    </span>
                                    <span className="text-[9px] text-gray-600 ml-auto">{formatDate(msg.created_at)}</span>
                                  </div>
                                  {msg.voice_file_id && (
                                    <div className="flex items-center gap-1.5 mb-1">
                                      <Mic className="w-3 h-3 text-purple-400" />
                                      <a
                                        href={`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'}/feedback-tickets/telegram-file/${msg.voice_file_id}`}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="text-[10px] text-purple-400 underline"
                                      >
                                        Play voice note
                                      </a>
                                    </div>
                                  )}
                                  <p className="text-gray-300">{msg.message_text}</p>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>

                    {/* Always show response form */}
                    <div className="space-y-2 pt-2 border-t border-surface-border/20">
                      <textarea
                        value={responseText}
                        onChange={(e) => setResponseText(e.target.value)}
                        placeholder="Type department response..."
                        rows={2}
                        className="w-full p-3 rounded-lg bg-[#0B1120] border border-surface-border/30 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-brand-red/30 resize-none"
                      />
                      <button
                        onClick={() => handleRespond(ticket.ticket_id)}
                        disabled={responding || !responseText.trim()}
                        className="flex items-center gap-2 px-4 py-2 rounded-lg bg-brand-red hover:bg-brand-red/90 text-white text-sm font-medium disabled:opacity-40 transition-all"
                      >
                        {responding ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                        Respond to Agent
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
