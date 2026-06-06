'use client';

/**
 * Broadcast detail + live status board.
 *
 * If status is "scheduled" or "dispatching" we poll /status every 3s so the
 * dashboard reflects what the dispatcher is doing in near-real-time.
 */

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAuth } from '@/lib/AuthContext';
import { api } from '@/lib/api';
import {
  ArrowLeft, Send, RefreshCw, X, ShieldAlert, AlertTriangle, Loader2,
  Megaphone, GraduationCap, Package, Trophy, Paperclip, Trash2,
} from 'lucide-react';

const TYPE_ICON: Record<string, any> = {
  training: GraduationCap, product: Package, incentive: Trophy, announcement: Megaphone,
};

const STATUS_META: Record<string, { label: string; color: string; bg: string }> = {
  draft:       { label: 'Draft',       color: '#9CA3AF', bg: 'rgba(156,163,175,0.12)' },
  scheduled:   { label: 'Scheduled',   color: '#60A5FA', bg: 'rgba(96,165,250,0.12)' },
  dispatching: { label: 'Dispatching', color: '#A78BFA', bg: 'rgba(167,139,250,0.12)' },
  completed:   { label: 'Completed',   color: '#34D399', bg: 'rgba(52,211,153,0.12)' },
  cancelled:   { label: 'Cancelled',   color: '#6B7280', bg: 'rgba(107,114,128,0.12)' },
  failed:      { label: 'Failed',      color: '#F87171', bg: 'rgba(248,113,113,0.12)' },
};

export default function BroadcastDetailPage() {
  const params = useParams<{ id: string }>();
  const id = parseInt(params?.id as string, 10);
  const router = useRouter();
  const { isAdmin, user } = useAuth();
  const allowed = isAdmin || (user?.role as string) === 'agency_dev';

  const [bc, setBc] = useState<any>(null);
  const [status, setStatus] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = async () => {
    setLoading(true);
    try {
      const [detail, st] = await Promise.all([
        api.getBroadcast(id),
        api.getBroadcastStatus(id),
      ]);
      setBc(detail);
      setStatus(st);
    } catch (e: any) {
      setError(e?.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { if (id && allowed) reload(); /* eslint-disable-next-line */ }, [id, allowed]);

  // Auto-poll while live
  useEffect(() => {
    if (!bc) return;
    if (!['scheduled', 'dispatching'].includes(bc.status)) return;
    const handle = setInterval(reload, 3000);
    return () => clearInterval(handle);
    // eslint-disable-next-line
  }, [bc?.status]);

  if (!allowed) {
    return (
      <div className="max-w-xl mx-auto mt-16 text-center">
        <ShieldAlert className="w-12 h-12 mx-auto text-red-400 mb-4" />
        <h2 className="text-xl font-semibold text-gray-200">Access restricted</h2>
      </div>
    );
  }

  if (loading && !bc) return <div className="text-center text-gray-400 mt-16">Loading…</div>;
  if (!bc) return <div className="text-center text-gray-400 mt-16">Not found.</div>;

  const TypeIcon = TYPE_ICON[bc.type] || Megaphone;
  const meta = STATUS_META[bc.status] || STATUS_META.draft;

  const onSendNow = async () => {
    try {
      await api.sendBroadcastNow(id);
      reload();
    } catch (e: any) {
      setError(e?.message);
    }
  };

  const onRetry = async () => {
    try {
      await api.retryFailedBroadcast(id);
      reload();
    } catch (e: any) {
      setError(e?.message);
    }
  };

  const onCancelOrDelete = async () => {
    const label = bc.status === 'draft' ? 'Delete this draft?' : 'Cancel this scheduled broadcast?';
    if (!confirm(label)) return;
    try {
      await api.deleteBroadcast(id);
      router.push('/broadcasts');
    } catch (e: any) {
      setError(e?.message);
    }
  };

  const counts = status?.counts || { queued: 0, sent: 0, failed: 0, skipped: 0 };
  const total = bc.recipient_count || 0;
  const progressPct = total > 0 ? Math.round(((counts.sent + counts.failed + counts.skipped) / total) * 100) : 0;

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div>
        <Link href="/broadcasts" className="text-sm text-gray-400 hover:text-gray-200 flex items-center gap-1">
          <ArrowLeft className="w-3 h-3" /> Back to broadcasts
        </Link>
        <div className="flex items-start justify-between mt-2 gap-4 flex-wrap">
          <div className="flex items-center gap-3">
            <div
              className="w-12 h-12 rounded-xl flex items-center justify-center"
              style={{ background: `${bc.type_color}1f`, color: bc.type_color }}
            >
              <TypeIcon className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center gap-2 mb-0.5">
                <span className="text-xs font-mono text-gray-500">{bc.broadcast_ref}</span>
                <span
                  className="px-2 py-0.5 rounded-md text-xs font-medium"
                  style={{ color: meta.color, background: meta.bg, border: `1px solid ${meta.color}33` }}
                >
                  {meta.label}
                </span>
                <span className="text-[11px] text-gray-500">{bc.type_label}</span>
              </div>
              <h1 className="text-xl font-semibold text-gray-100">{bc.title}</h1>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={reload} className="px-3 py-2 rounded-lg text-sm text-gray-200 bg-white/5 hover:bg-white/10 border border-white/10 flex items-center gap-2">
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} /> Refresh
            </button>
            {bc.status === 'draft' && (
              <button onClick={onSendNow} className="px-3 py-2 rounded-lg text-sm font-medium bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-100 border border-emerald-500/30 flex items-center gap-2">
                <Send className="w-4 h-4" /> Send now
              </button>
            )}
            {bc.status === 'completed' && counts.failed > 0 && (
              <button onClick={onRetry} className="px-3 py-2 rounded-lg text-sm font-medium bg-amber-500/20 hover:bg-amber-500/30 text-amber-100 border border-amber-500/30 flex items-center gap-2">
                <RefreshCw className="w-4 h-4" /> Retry {counts.failed} failed
              </button>
            )}
            {(bc.status === 'draft' || bc.status === 'scheduled') && (
              <button onClick={onCancelOrDelete} className="px-3 py-2 rounded-lg text-sm text-gray-300 bg-white/5 hover:bg-white/10 border border-white/10 flex items-center gap-2">
                {bc.status === 'draft' ? <Trash2 className="w-4 h-4" /> : <X className="w-4 h-4" />}
                {bc.status === 'draft' ? 'Delete' : 'Cancel'}
              </button>
            )}
          </div>
        </div>
      </div>

      {error && (
        <div className="px-4 py-3 rounded-lg bg-red-500/10 border border-red-500/30 text-sm text-red-300">
          {error}
        </div>
      )}

      {/* Status board */}
      <div className="rounded-xl bg-white/[0.03] border border-white/5 p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="text-xs uppercase tracking-wider text-gray-500">Delivery</div>
          {['scheduled', 'dispatching'].includes(bc.status) && (
            <div className="text-xs text-purple-300 flex items-center gap-1.5">
              <Loader2 className="w-3 h-3 animate-spin" /> Live · refreshing every 3s
            </div>
          )}
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-4">
          <Tile label="Total" value={total} color="#E5E7EB" />
          <Tile label="Queued" value={counts.queued} color="#FACC15" />
          <Tile label="Sent" value={counts.sent} color="#34D399" />
          <Tile label="Failed" value={counts.failed} color="#F87171" />
          <Tile label="Skipped" value={counts.skipped} color="#6B7280" />
        </div>
        {total > 0 && (
          <div>
            <div className="flex items-center justify-between text-xs text-gray-400 mb-1.5">
              <span>Progress</span>
              <span>{progressPct}%</span>
            </div>
            <div className="h-2 rounded-full bg-white/[0.04] overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-emerald-500 to-blue-500 transition-all duration-500"
                style={{ width: `${progressPct}%` }}
              />
            </div>
          </div>
        )}
        {status?.failed_sample?.length > 0 && (
          <div className="mt-4">
            <div className="text-xs uppercase tracking-wider text-red-300 mb-2">Sample failures</div>
            <div className="space-y-1">
              {status.failed_sample.map((r: any) => (
                <div key={r.id} className="px-3 py-2 rounded-lg bg-red-500/[0.05] border border-red-500/20 text-xs">
                  <div className="text-gray-200">{r.agent_name} <span className="text-gray-500">({r.agent_phone})</span></div>
                  <div className="text-red-300 mt-0.5 flex items-center gap-1.5">
                    <AlertTriangle className="w-3 h-3" /> {r.error_reason || 'Unknown error'}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Content + meta */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-4">
        <div className="rounded-xl bg-white/[0.03] border border-white/5 p-5">
          <div className="text-xs uppercase tracking-wider text-gray-500 mb-2">Message body</div>
          <div className="text-sm text-gray-200 whitespace-pre-wrap">{bc.body}</div>
          {bc.link_url && (
            <div className="mt-3">
              <a href={bc.link_url} target="_blank" rel="noopener noreferrer" className="text-sm text-blue-300 hover:text-blue-200 underline">
                {bc.link_label || bc.link_url}
              </a>
            </div>
          )}
          {bc.has_attachment && (
            <div className="mt-3 px-3 py-2 rounded-lg bg-white/[0.04] border border-white/10 text-sm text-gray-300 flex items-center gap-2">
              <Paperclip className="w-4 h-4" />
              {bc.attachment_file_name}
              <span className="text-xs text-gray-500">({bc.attachment_kind} · {Math.round((bc.attachment_size || 0) / 1024)} KB)</span>
            </div>
          )}
        </div>

        <div className="rounded-xl bg-white/[0.03] border border-white/5 p-5 space-y-3">
          <Meta label="Created by" value={bc.created_by_name} />
          <Meta label="Created at" value={bc.created_at && new Date(bc.created_at).toLocaleString()} />
          {bc.scheduled_at && <Meta label="Scheduled for" value={new Date(bc.scheduled_at).toLocaleString()} />}
          {bc.dispatched_at && <Meta label="Dispatched at" value={new Date(bc.dispatched_at).toLocaleString()} />}
          {bc.completed_at && <Meta label="Completed at" value={new Date(bc.completed_at).toLocaleString()} />}
          <Meta label="Channels" value={bc.channels} />
          <div>
            <div className="text-xs uppercase tracking-wider text-gray-500 mb-1">Targeting</div>
            <pre className="text-[11px] text-gray-300 bg-white/[0.03] rounded-md p-2 overflow-auto max-h-40 font-mono">
              {JSON.stringify(bc.target_filter, null, 2)}
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
}

function Tile({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="rounded-xl px-3 py-2 border" style={{ background: 'rgba(255,255,255,0.03)', borderColor: 'rgba(255,255,255,0.06)' }}>
      <div className="text-xs text-gray-400">{label}</div>
      <div className="text-2xl font-semibold" style={{ color }}>{value}</div>
    </div>
  );
}

function Meta({ label, value }: { label: string; value: any }) {
  if (value == null || value === '') return null;
  return (
    <div>
      <div className="text-xs uppercase tracking-wider text-gray-500">{label}</div>
      <div className="text-sm text-gray-200">{value}</div>
    </div>
  );
}
