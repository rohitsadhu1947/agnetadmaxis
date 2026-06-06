'use client';

/**
 * People Feedback — Agency Development team dashboard.
 *
 * Visible to: admin + agency_dev roles. ADM users get 403 from the backend
 * AND don't see this in the sidebar. The whole point of this view is so
 * the Agency Development team can act on concerns agents raise about their
 * assigned ADM — without the ADM ever seeing it.
 *
 * Layout: master-detail.
 *   Left:  filters + ticket list
 *   Right: selected ticket detail + threaded conversation + reply composer
 *          + internal-notes pane + status changer
 */

import { useEffect, useMemo, useState } from 'react';
import { useAuth } from '@/lib/AuthContext';
import { api } from '@/lib/api';
import {
  ShieldAlert,
  AlertTriangle,
  Send,
  StickyNote,
  Clock,
  CheckCircle2,
  Eye,
  Cog,
  Flag,
  RefreshCw,
  Search,
} from 'lucide-react';

type Status =
  | 'new'
  | 'reviewed'
  | 'in_progress'
  | 'action_taken'
  | 'closed'
  | 'escalated';

interface Ticket {
  id: number;
  ticket_ref: string;
  agent_id: number;
  agent_name: string;
  agent_phone: string;
  target_adm_id: number | null;
  target_adm_name: string | null;
  category: string;
  category_label: string;
  subcategory: string | null;
  subcategory_label: string | null;
  other_text: string | null;
  initial_text: string | null;
  has_voice: boolean;
  has_attachment: boolean;
  status: Status;
  sla_due_at: string | null;
  is_sla_breached: boolean;
  internal_notes?: string | null;
  assigned_to_name?: string | null;
  created_at: string;
  updated_at: string;
  messages?: TicketMessage[];
}

interface TicketMessage {
  id: number;
  sender_role: 'agent' | 'agency_dev' | 'system';
  sender_name: string | null;
  text: string | null;
  has_voice: boolean;
  has_attachment: boolean;
  message_type: string;
  is_status_change: boolean;
  created_at: string;
}

const STATUS_META: Record<Status, { label: string; color: string; bg: string }> = {
  new: { label: 'New', color: '#FACC15', bg: 'rgba(250, 204, 21, 0.12)' },
  reviewed: { label: 'Reviewed', color: '#60A5FA', bg: 'rgba(96, 165, 250, 0.12)' },
  in_progress: { label: 'In Progress', color: '#A78BFA', bg: 'rgba(167, 139, 250, 0.12)' },
  action_taken: { label: 'Action Taken', color: '#34D399', bg: 'rgba(52, 211, 153, 0.12)' },
  closed: { label: 'Closed', color: '#9CA3AF', bg: 'rgba(156, 163, 175, 0.12)' },
  escalated: { label: 'Escalated', color: '#F87171', bg: 'rgba(248, 113, 113, 0.18)' },
};

const STATUS_ORDER: Status[] = ['new', 'reviewed', 'in_progress', 'action_taken', 'closed', 'escalated'];

function StatusBadge({ status }: { status: Status }) {
  const meta = STATUS_META[status];
  return (
    <span
      className="px-2 py-0.5 rounded-md text-xs font-medium"
      style={{ color: meta.color, background: meta.bg, border: `1px solid ${meta.color}33` }}
    >
      {meta.label}
    </span>
  );
}

function timeAgo(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  const diffMs = Date.now() - d.getTime();
  const m = Math.round(diffMs / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  const days = Math.round(h / 24);
  return `${days}d ago`;
}

function timeRemaining(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  const diffMs = d.getTime() - Date.now();
  if (diffMs <= 0) return 'overdue';
  const h = Math.round(diffMs / 3600000);
  if (h < 24) return `${h}h left`;
  return `${Math.round(h / 24)}d left`;
}

export default function PeopleFeedbackPage() {
  const { isAdmin, user } = useAuth();
  // agency_dev is a future role; today admin is the entitled role.
  // We compare via `as string` so TypeScript doesn't reject the future role.
  const allowed =
    isAdmin || (user?.role as string) === 'agency_dev' || (user?.role as string) === 'admin';

  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState<Status | ''>('');
  const [categoryFilter, setCategoryFilter] = useState<string>('');
  const [slaOnly, setSlaOnly] = useState(false);
  const [search, setSearch] = useState('');
  const [categories, setCategories] = useState<any[]>([]);

  // Selection + detail
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<Ticket | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // Reply / note composers
  const [replyText, setReplyText] = useState('');
  const [noteText, setNoteText] = useState('');
  const [sending, setSending] = useState(false);

  // ------------------------------ Load list ------------------------------
  const reload = async () => {
    if (!allowed) return;
    setLoading(true);
    setError(null);
    try {
      const [list, st] = await Promise.all([
        api.listPeopleFeedback({
          status: statusFilter || undefined,
          category: categoryFilter || undefined,
          sla_breached_only: slaOnly || undefined,
          search: search || undefined,
          limit: 100,
        }),
        api.getPeopleFeedbackStats(),
      ]);
      setTickets(list?.tickets || []);
      setStats(st);
      if (!selectedId && (list?.tickets || []).length > 0) {
        setSelectedId(list.tickets[0].id);
      }
    } catch (e: any) {
      setError(e?.message || 'Could not load tickets');
    } finally {
      setLoading(false);
    }
  };

  const loadDetail = async (id: number) => {
    setDetailLoading(true);
    try {
      const d = await api.getPeopleFeedbackDetail(id);
      setDetail(d);
    } catch (e: any) {
      setError(e?.message || 'Could not load ticket detail');
    } finally {
      setDetailLoading(false);
    }
  };

  useEffect(() => {
    if (!allowed) return;
    (async () => {
      try {
        const c = await api.getPeopleFeedbackCategories();
        setCategories(c?.categories || []);
      } catch {}
    })();
  }, [allowed]);

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter, categoryFilter, slaOnly]);

  useEffect(() => {
    if (selectedId != null) loadDetail(selectedId);
  }, [selectedId]);

  // ------------------------------ Actions --------------------------------
  const sendReply = async () => {
    if (!selectedId || !replyText.trim()) return;
    setSending(true);
    try {
      await api.replyToPeopleFeedback(selectedId, replyText.trim());
      setReplyText('');
      await loadDetail(selectedId);
      await reload();
    } catch (e: any) {
      setError(e?.message || 'Reply failed');
    } finally {
      setSending(false);
    }
  };

  const addNote = async () => {
    if (!selectedId || !noteText.trim()) return;
    setSending(true);
    try {
      await api.addPeopleFeedbackNote(selectedId, noteText.trim());
      setNoteText('');
      await loadDetail(selectedId);
    } catch (e: any) {
      setError(e?.message || 'Failed to save note');
    } finally {
      setSending(false);
    }
  };

  const changeStatus = async (next: Status) => {
    if (!selectedId) return;
    setSending(true);
    try {
      await api.changePeopleFeedbackStatus(selectedId, next);
      await loadDetail(selectedId);
      await reload();
    } catch (e: any) {
      setError(e?.message || 'Status change failed');
    } finally {
      setSending(false);
    }
  };

  // ------------------------------ Access guard ---------------------------
  if (!allowed) {
    return (
      <div className="max-w-xl mx-auto mt-16 text-center">
        <ShieldAlert className="w-12 h-12 mx-auto text-red-400 mb-4" />
        <h2 className="text-xl font-semibold text-gray-200">Access restricted</h2>
        <p className="mt-2 text-sm text-gray-400">
          People Feedback is visible only to the Agency Development team and platform admins.
        </p>
      </div>
    );
  }

  const visibleMessages = useMemo(
    () => (detail?.messages || []).filter((m) => m), // backend already nulls hidden notes for agent view; here we keep all
    [detail?.messages]
  );

  // ============================ RENDER ===================================
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold text-gray-100 flex items-center gap-2">
            <ShieldAlert className="w-6 h-6 text-red-400" />
            People Feedback
          </h1>
          <p className="text-sm text-gray-400 mt-1">
            Confidential agent feedback about assigned ADMs / mentors. SLA: 3 days.
          </p>
        </div>
        <button
          onClick={reload}
          className="px-3 py-2 rounded-lg text-sm text-gray-200 bg-white/5 hover:bg-white/10 border border-white/10 flex items-center gap-2"
        >
          <RefreshCw className="w-4 h-4" /> Refresh
        </button>
      </div>

      {/* Stats row */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
          <StatTile label="Total" value={stats.total ?? 0} color="#E5E7EB" />
          <StatTile label="New" value={stats.by_status?.new ?? 0} color={STATUS_META.new.color} />
          <StatTile label="Reviewed" value={stats.by_status?.reviewed ?? 0} color={STATUS_META.reviewed.color} />
          <StatTile label="In Progress" value={stats.by_status?.in_progress ?? 0} color={STATUS_META.in_progress.color} />
          <StatTile label="Action Taken" value={stats.by_status?.action_taken ?? 0} color={STATUS_META.action_taken.color} />
          <StatTile
            label="SLA Breached"
            value={stats.sla_breached ?? 0}
            color={(stats.sla_breached ?? 0) > 0 ? '#F87171' : '#9CA3AF'}
            highlight={(stats.sla_breached ?? 0) > 0}
          />
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="absolute left-2 top-2.5 w-4 h-4 text-gray-500" />
          <input
            type="text"
            placeholder="Search ref, name, text..."
            className="pl-8 pr-3 py-2 rounded-lg bg-white/5 border border-white/10 text-sm text-gray-200 placeholder:text-gray-500 w-64"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && reload()}
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as Status | '')}
          className="py-2 px-3 rounded-lg bg-white/5 border border-white/10 text-sm text-gray-200"
        >
          <option value="">All statuses</option>
          {STATUS_ORDER.map((s) => (
            <option key={s} value={s}>{STATUS_META[s].label}</option>
          ))}
        </select>
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="py-2 px-3 rounded-lg bg-white/5 border border-white/10 text-sm text-gray-200"
        >
          <option value="">All categories</option>
          {categories.map((c) => (
            <option key={c.key} value={c.key}>{c.label}</option>
          ))}
        </select>
        <label className="flex items-center gap-2 text-sm text-gray-300 cursor-pointer">
          <input
            type="checkbox"
            checked={slaOnly}
            onChange={(e) => setSlaOnly(e.target.checked)}
            className="accent-red-500"
          />
          SLA breached only
        </label>
      </div>

      {error && (
        <div className="px-4 py-3 rounded-lg bg-red-500/10 border border-red-500/30 text-sm text-red-300">
          {error}
        </div>
      )}

      {/* Master-detail */}
      <div className="grid grid-cols-1 lg:grid-cols-[420px_1fr] gap-4">
        {/* List */}
        <div className="rounded-xl bg-white/[0.03] border border-white/5 overflow-hidden">
          <div className="px-3 py-2 border-b border-white/5 text-xs uppercase tracking-wider text-gray-400">
            {loading ? 'Loading…' : `${tickets.length} ticket${tickets.length === 1 ? '' : 's'}`}
          </div>
          <div className="max-h-[calc(100vh-280px)] overflow-y-auto">
            {tickets.length === 0 && !loading ? (
              <div className="p-6 text-center text-sm text-gray-500">No tickets match these filters.</div>
            ) : (
              tickets.map((t) => (
                <button
                  key={t.id}
                  onClick={() => setSelectedId(t.id)}
                  className={`w-full text-left px-3 py-3 border-b border-white/5 hover:bg-white/[0.03] transition ${
                    selectedId === t.id ? 'bg-white/[0.06]' : ''
                  }`}
                >
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <span className="text-xs font-mono text-gray-400">{t.ticket_ref}</span>
                    <StatusBadge status={t.status} />
                  </div>
                  <div className="text-sm font-medium text-gray-100 truncate">{t.agent_name}</div>
                  <div className="text-xs text-gray-400 truncate">
                    {t.category_label}
                    {t.subcategory_label ? ` · ${t.subcategory_label}` : ''}
                  </div>
                  <div className="mt-1 flex items-center justify-between text-[11px]">
                    <span className="text-gray-500">{timeAgo(t.created_at)}</span>
                    {t.is_sla_breached ? (
                      <span className="text-red-300 flex items-center gap-1">
                        <AlertTriangle className="w-3 h-3" /> SLA breached
                      </span>
                    ) : (
                      <span className="text-gray-500 flex items-center gap-1">
                        <Clock className="w-3 h-3" /> {timeRemaining(t.sla_due_at)}
                      </span>
                    )}
                  </div>
                </button>
              ))
            )}
          </div>
        </div>

        {/* Detail */}
        <div className="rounded-xl bg-white/[0.03] border border-white/5">
          {!detail ? (
            <div className="p-8 text-center text-sm text-gray-500">
              {detailLoading ? 'Loading…' : 'Select a ticket to view details.'}
            </div>
          ) : (
            <div className="flex flex-col h-full">
              {/* Detail header */}
              <div className="px-5 py-4 border-b border-white/5">
                <div className="flex items-center justify-between gap-3 flex-wrap">
                  <div>
                    <div className="flex items-center gap-3">
                      <span className="font-mono text-sm text-gray-400">{detail.ticket_ref}</span>
                      <StatusBadge status={detail.status} />
                      {detail.is_sla_breached && (
                        <span className="px-2 py-0.5 rounded-md text-[11px] font-medium text-red-300 bg-red-500/10 border border-red-500/30 flex items-center gap-1">
                          <AlertTriangle className="w-3 h-3" /> SLA breached
                        </span>
                      )}
                    </div>
                    <h2 className="mt-1 text-lg font-semibold text-gray-100">
                      {detail.category_label}
                      {detail.subcategory_label && (
                        <span className="text-gray-400"> · {detail.subcategory_label}</span>
                      )}
                    </h2>
                  </div>
                  <div className="text-right text-xs text-gray-400">
                    <div>Submitted {timeAgo(detail.created_at)}</div>
                    <div>SLA: {timeRemaining(detail.sla_due_at)}</div>
                  </div>
                </div>
                {/* Agent + target ADM */}
                <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
                  <div className="px-3 py-2 rounded-lg bg-white/[0.03] border border-white/5">
                    <div className="text-[11px] uppercase tracking-wider text-gray-500">Agent</div>
                    <div className="text-gray-100">{detail.agent_name}</div>
                    <div className="text-xs text-gray-400">{detail.agent_phone}</div>
                  </div>
                  <div className="px-3 py-2 rounded-lg bg-red-500/[0.05] border border-red-500/15">
                    <div className="text-[11px] uppercase tracking-wider text-red-300/80">About (assigned ADM)</div>
                    <div className="text-gray-100">
                      {detail.target_adm_name || <span className="text-gray-500">No ADM assigned</span>}
                    </div>
                    <div className="text-[10px] text-red-300/60 italic mt-1">
                      🔒 ADM cannot see this ticket
                    </div>
                  </div>
                </div>
              </div>

              {/* Status changer */}
              <div className="px-5 py-3 border-b border-white/5 flex items-center gap-2 flex-wrap">
                <span className="text-xs uppercase tracking-wider text-gray-500 mr-1">Status:</span>
                {STATUS_ORDER.map((s) => (
                  <button
                    key={s}
                    onClick={() => changeStatus(s)}
                    disabled={sending || detail.status === s}
                    className={`px-2 py-1 rounded-md text-xs font-medium transition ${
                      detail.status === s
                        ? 'opacity-40 cursor-not-allowed'
                        : 'hover:bg-white/10 border border-white/10'
                    }`}
                    style={
                      detail.status === s
                        ? { color: STATUS_META[s].color, background: STATUS_META[s].bg }
                        : undefined
                    }
                  >
                    {STATUS_META[s].label}
                  </button>
                ))}
              </div>

              {/* Body & thread (scrollable) */}
              <div className="px-5 py-4 overflow-y-auto max-h-[calc(100vh-470px)] space-y-4">
                {/* Initial submission */}
                <div>
                  <div className="text-[11px] uppercase tracking-wider text-gray-500 mb-1">
                    Initial submission
                  </div>
                  {detail.other_text && (
                    <div className="text-sm text-gray-300 italic">{detail.other_text}</div>
                  )}
                  {detail.initial_text && (
                    <div className="text-sm text-gray-200 whitespace-pre-wrap mt-1">
                      {detail.initial_text}
                    </div>
                  )}
                  {(detail.has_voice || detail.has_attachment) && (
                    <div className="mt-2 text-xs text-gray-400 flex gap-3">
                      {detail.has_voice && <span>🎙 Voice note attached</span>}
                      {detail.has_attachment && <span>📎 Document attached</span>}
                    </div>
                  )}
                </div>

                {/* Thread */}
                {visibleMessages.length > 0 && (
                  <div>
                    <div className="text-[11px] uppercase tracking-wider text-gray-500 mb-2">
                      Conversation
                    </div>
                    <div className="space-y-2">
                      {visibleMessages.map((m) => (
                        <ThreadMessage key={m.id} m={m} />
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Composer row */}
              <div className="px-5 py-4 border-t border-white/5 grid grid-cols-1 md:grid-cols-2 gap-3">
                {/* Reply (visible to agent) */}
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <Send className="w-3.5 h-3.5 text-blue-300" />
                    <span className="text-xs uppercase tracking-wider text-blue-300">
                      Reply to agent (visible)
                    </span>
                  </div>
                  <textarea
                    value={replyText}
                    onChange={(e) => setReplyText(e.target.value)}
                    placeholder="Type your reply…"
                    rows={3}
                    className="w-full px-3 py-2 rounded-lg bg-white/[0.03] border border-white/10 text-sm text-gray-100 resize-none"
                  />
                  <button
                    onClick={sendReply}
                    disabled={sending || !replyText.trim()}
                    className="mt-2 px-3 py-2 rounded-lg text-sm font-medium bg-blue-500/20 hover:bg-blue-500/30 text-blue-200 border border-blue-500/30 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Send reply
                  </button>
                </div>

                {/* Internal note */}
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <StickyNote className="w-3.5 h-3.5 text-amber-300" />
                    <span className="text-xs uppercase tracking-wider text-amber-300">
                      Internal note (hidden from agent)
                    </span>
                  </div>
                  <textarea
                    value={noteText}
                    onChange={(e) => setNoteText(e.target.value)}
                    placeholder="Add an internal note — visible only to your team…"
                    rows={3}
                    className="w-full px-3 py-2 rounded-lg bg-amber-500/[0.04] border border-amber-500/20 text-sm text-gray-100 resize-none"
                  />
                  <button
                    onClick={addNote}
                    disabled={sending || !noteText.trim()}
                    className="mt-2 px-3 py-2 rounded-lg text-sm font-medium bg-amber-500/20 hover:bg-amber-500/30 text-amber-200 border border-amber-500/30 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Save note
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ------------------------------ Sub-components ------------------------------

function StatTile({
  label, value, color, highlight,
}: {
  label: string; value: number; color: string; highlight?: boolean;
}) {
  return (
    <div
      className="rounded-xl px-3 py-2 border"
      style={{
        background: highlight ? `${color}10` : 'rgba(255,255,255,0.03)',
        borderColor: highlight ? `${color}55` : 'rgba(255,255,255,0.06)',
      }}
    >
      <div className="text-xs text-gray-400">{label}</div>
      <div className="text-2xl font-semibold" style={{ color }}>{value}</div>
    </div>
  );
}

function ThreadMessage({ m }: { m: TicketMessage }) {
  if (m.message_type === 'note') {
    return (
      <div className="rounded-lg bg-amber-500/[0.05] border border-amber-500/20 px-3 py-2">
        <div className="text-[11px] uppercase tracking-wider text-amber-300/90 flex items-center gap-1.5">
          <StickyNote className="w-3 h-3" />
          Internal note · {m.sender_name || 'Team'}
          <span className="ml-auto text-amber-300/60 font-normal normal-case tracking-normal">
            {timeAgo(m.created_at)}
          </span>
        </div>
        {m.text && <div className="text-sm text-amber-100 mt-1 whitespace-pre-wrap">{m.text}</div>}
      </div>
    );
  }
  if (m.is_status_change) {
    return (
      <div className="rounded-lg bg-white/[0.03] border border-white/10 px-3 py-1.5 text-xs text-gray-400 flex items-center gap-2">
        <Cog className="w-3 h-3" />
        <span className="font-mono">{m.text}</span>
        <span className="ml-auto">{timeAgo(m.created_at)}</span>
      </div>
    );
  }
  const isAgent = m.sender_role === 'agent';
  return (
    <div className={`flex ${isAgent ? 'justify-start' : 'justify-end'}`}>
      <div
        className={`max-w-[80%] rounded-lg px-3 py-2 ${
          isAgent
            ? 'bg-white/[0.04] border border-white/10'
            : 'bg-blue-500/15 border border-blue-500/30'
        }`}
      >
        <div className="text-[11px] uppercase tracking-wider text-gray-400 flex items-center gap-1.5">
          {isAgent ? <Eye className="w-3 h-3" /> : <Send className="w-3 h-3" />}
          {isAgent ? 'Agent' : (m.sender_name || 'Agency Dev')}
          <span className="ml-2 text-gray-500 normal-case tracking-normal">{timeAgo(m.created_at)}</span>
        </div>
        {m.text && <div className="text-sm text-gray-100 mt-1 whitespace-pre-wrap">{m.text}</div>}
        {(m.has_voice || m.has_attachment) && (
          <div className="mt-1 text-xs text-gray-400 flex gap-3">
            {m.has_voice && <span>🎙</span>}
            {m.has_attachment && <span>📎</span>}
          </div>
        )}
      </div>
    </div>
  );
}
