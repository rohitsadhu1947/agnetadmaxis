'use client';

/**
 * Broadcasts — list page.
 *
 * Shows the admin/agency_dev team's composed broadcasts grouped by status.
 * Filter by type/status, click into one for the live status board.
 * Top-right "+ New broadcast" button takes them into the composer.
 */

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useAuth } from '@/lib/AuthContext';
import { api } from '@/lib/api';
import {
  Megaphone, Plus, RefreshCw, ShieldAlert, FileText, Send,
  Clock, CheckCircle2, XCircle, AlertTriangle, GraduationCap,
  Package, Trophy,
} from 'lucide-react';

const TYPE_ICON: Record<string, any> = {
  training: GraduationCap,
  product: Package,
  incentive: Trophy,
  announcement: Megaphone,
};

const STATUS_META: Record<string, { label: string; color: string; bg: string }> = {
  draft:       { label: 'Draft',       color: '#9CA3AF', bg: 'rgba(156,163,175,0.12)' },
  scheduled:   { label: 'Scheduled',   color: '#60A5FA', bg: 'rgba(96,165,250,0.12)' },
  dispatching: { label: 'Dispatching', color: '#A78BFA', bg: 'rgba(167,139,250,0.12)' },
  completed:   { label: 'Completed',   color: '#34D399', bg: 'rgba(52,211,153,0.12)' },
  cancelled:   { label: 'Cancelled',   color: '#6B7280', bg: 'rgba(107,114,128,0.12)' },
  failed:      { label: 'Failed',      color: '#F87171', bg: 'rgba(248,113,113,0.12)' },
};

function StatusBadge({ status }: { status: string }) {
  const meta = STATUS_META[status] || STATUS_META.draft;
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
  const m = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.round(h / 24)}d ago`;
}

export default function BroadcastsListPage() {
  const { isAdmin, user } = useAuth();
  const allowed = isAdmin || (user?.role as string) === 'agency_dev';

  const [broadcasts, setBroadcasts] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [typeFilter, setTypeFilter] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = async () => {
    if (!allowed) return;
    setLoading(true);
    setError(null);
    try {
      const [list, st] = await Promise.all([
        api.listBroadcasts({
          status: statusFilter || undefined,
          type: typeFilter || undefined,
          limit: 100,
        }),
        api.getBroadcastStats(),
      ]);
      setBroadcasts(list?.broadcasts || []);
      setStats(st);
    } catch (e: any) {
      setError(e?.message || 'Could not load broadcasts');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { reload(); /* eslint-disable-next-line */ }, [statusFilter, typeFilter]);

  if (!allowed) {
    return (
      <div className="max-w-xl mx-auto mt-16 text-center">
        <ShieldAlert className="w-12 h-12 mx-auto text-red-400 mb-4" />
        <h2 className="text-xl font-semibold text-gray-200">Access restricted</h2>
        <p className="mt-2 text-sm text-gray-400">
          Broadcasts are visible only to admin / Agency Development users.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold text-gray-100 flex items-center gap-2">
            <Megaphone className="w-6 h-6 text-blue-300" />
            Broadcasts
          </h1>
          <p className="text-sm text-gray-400 mt-1">
            Send training, product, incentive, and announcement updates to filtered groups of agents on Telegram.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={reload}
            className="px-3 py-2 rounded-lg text-sm text-gray-200 bg-white/5 hover:bg-white/10 border border-white/10 flex items-center gap-2"
          >
            <RefreshCw className="w-4 h-4" /> Refresh
          </button>
          <Link
            href="/broadcasts/new"
            className="px-4 py-2 rounded-lg text-sm font-medium bg-blue-500/20 hover:bg-blue-500/30 text-blue-100 border border-blue-500/30 flex items-center gap-2"
          >
            <Plus className="w-4 h-4" /> New broadcast
          </Link>
        </div>
      </div>

      {/* Stats tiles */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
          <Tile label="Total" value={stats.total} color="#E5E7EB" />
          <Tile label="Draft" value={stats.by_status?.draft ?? 0} color={STATUS_META.draft.color} />
          <Tile label="Scheduled" value={stats.by_status?.scheduled ?? 0} color={STATUS_META.scheduled.color} />
          <Tile label="Dispatching" value={stats.by_status?.dispatching ?? 0} color={STATUS_META.dispatching.color} />
          <Tile label="Completed" value={stats.by_status?.completed ?? 0} color={STATUS_META.completed.color} />
          <Tile label="Failed" value={stats.by_status?.failed ?? 0} color={STATUS_META.failed.color} />
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="py-2 px-3 rounded-lg bg-white/5 border border-white/10 text-sm text-gray-200"
        >
          <option value="">All statuses</option>
          {Object.keys(STATUS_META).map((s) => (
            <option key={s} value={s}>{STATUS_META[s].label}</option>
          ))}
        </select>
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="py-2 px-3 rounded-lg bg-white/5 border border-white/10 text-sm text-gray-200"
        >
          <option value="">All types</option>
          <option value="training">Training</option>
          <option value="product">Product</option>
          <option value="incentive">Incentive</option>
          <option value="announcement">Announcement</option>
        </select>
      </div>

      {error && (
        <div className="px-4 py-3 rounded-lg bg-red-500/10 border border-red-500/30 text-sm text-red-300">
          {error}
        </div>
      )}

      {/* List */}
      <div className="rounded-xl bg-white/[0.03] border border-white/5 overflow-hidden">
        {loading ? (
          <div className="p-6 text-center text-sm text-gray-500">Loading…</div>
        ) : broadcasts.length === 0 ? (
          <div className="p-10 text-center">
            <Megaphone className="w-10 h-10 mx-auto text-gray-600 mb-2" />
            <div className="text-sm text-gray-400">No broadcasts yet.</div>
            <Link href="/broadcasts/new" className="inline-block mt-3 text-sm text-blue-300 hover:text-blue-200">
              Compose your first one →
            </Link>
          </div>
        ) : (
          broadcasts.map((b) => {
            const TypeIcon = TYPE_ICON[b.type] || Megaphone;
            return (
              <Link
                key={b.id}
                href={`/broadcasts/${b.id}`}
                className="block px-4 py-3 border-b border-white/5 hover:bg-white/[0.03] transition"
              >
                <div className="flex items-center gap-3">
                  <div
                    className="w-9 h-9 rounded-lg flex items-center justify-center"
                    style={{ background: `${b.type_color}1f`, color: b.type_color }}
                  >
                    <TypeIcon className="w-5 h-5" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className="text-xs font-mono text-gray-500">{b.broadcast_ref}</span>
                      <StatusBadge status={b.status} />
                      <span className="text-[11px] text-gray-500">{b.type_label}</span>
                    </div>
                    <div className="text-sm font-medium text-gray-100 truncate">{b.title}</div>
                    <div className="text-xs text-gray-400 truncate">{b.body}</div>
                  </div>
                  <div className="text-right text-xs text-gray-400 shrink-0">
                    <div>{b.recipient_count} recipients</div>
                    {b.status === 'completed' && (
                      <div className="text-emerald-300">
                        {b.sent_count} sent
                        {b.failed_count > 0 && <span className="text-red-300"> · {b.failed_count} failed</span>}
                      </div>
                    )}
                    {b.scheduled_at && (
                      <div className="text-blue-300">
                        {new Date(b.scheduled_at).toLocaleString()}
                      </div>
                    )}
                    <div className="text-gray-500 mt-0.5">{timeAgo(b.created_at)}</div>
                  </div>
                </div>
              </Link>
            );
          })
        )}
      </div>
    </div>
  );
}

function Tile({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div
      className="rounded-xl px-3 py-2 border"
      style={{ background: 'rgba(255,255,255,0.03)', borderColor: 'rgba(255,255,255,0.06)' }}
    >
      <div className="text-xs text-gray-400">{label}</div>
      <div className="text-2xl font-semibold" style={{ color }}>{value}</div>
    </div>
  );
}
