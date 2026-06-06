'use client';

/**
 * Broadcasts composer — 5-step flow:
 *   1. Pick type
 *   2. Content (title, body, link, attachment)
 *   3. Targeting (filter dimensions + live recipient count)
 *   4. Schedule (now or future)
 *   5. Review + send
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/AuthContext';
import { api } from '@/lib/api';
import {
  GraduationCap, Package, Trophy, Megaphone, Paperclip, X, ArrowLeft, ArrowRight,
  Send, Save, Calendar, Users, ShieldAlert, Loader2, Check,
} from 'lucide-react';

const TYPE_OPTIONS = [
  { key: 'training',    label: 'Training',    icon: GraduationCap, color: '#60A5FA',
    desc: 'New module live, upcoming session, training reminder.' },
  { key: 'product',     label: 'Product',     icon: Package,        color: '#A78BFA',
    desc: 'Plan launch, USP update, commission tweak.' },
  { key: 'incentive',   label: 'Incentive',   icon: Trophy,         color: '#34D399',
    desc: 'Contest, milestone reward, performance bonus.' },
  { key: 'announcement', label: 'Announcement', icon: Megaphone,    color: '#FACC15',
    desc: 'General notice, policy update, regulatory change.' },
];

const LIFECYCLE_LABELS: Record<string, string> = {
  onboarded:   'Onboarded',
  licensed:    'Licensed',
  first_sale:  'First sale',
  active:      'Active',
  productive:  'Productive',
  at_risk:     'At risk',
  dormant:     'Dormant',
  lapsed:      'Lapsed',
};

const COHORT_LABELS: Record<string, string> = {
  promising_rookies: 'Promising Rookies',
  stalled_starters: 'Stalled Starters',
  sleeping_giants: 'Sleeping Giants',
  fading_stars: 'Fading Stars',
  weekend_warriors: 'Weekend Warriors',
  economic_defectors: 'Economic Defectors',
  system_frustrated: 'System Frustrated',
  abandoned_by_adm: 'Abandoned by ADM',
  chronic_never_activators: 'Chronic Never Activators',
  life_event_paused: 'Life Event Paused',
  regulatory_blocked: 'Regulatory Blocked',
  digital_orphans: 'Digital Orphans',
  high_potential_unpolished: 'High Potential Unpolished',
  competitor_poached: 'Competitor Poached',
  satisfied_passives: 'Satisfied Passives',
  lost_causes: 'Lost Causes',
};

export default function BroadcastsComposer() {
  const router = useRouter();
  const { isAdmin, user } = useAuth();
  const allowed = isAdmin || (user?.role as string) === 'agency_dev';

  // ---- Wizard step ----
  const [step, setStep] = useState<1 | 2 | 3 | 4 | 5>(1);

  // ---- Step 1 — Type ----
  const [type, setType] = useState<string>('');

  // ---- Step 2 — Content ----
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [linkUrl, setLinkUrl] = useState('');
  const [linkLabel, setLinkLabel] = useState('');
  const [attachmentFile, setAttachmentFile] = useState<File | null>(null);
  const [attachmentFileId, setAttachmentFileId] = useState<number | null>(null);
  const [attachmentMeta, setAttachmentMeta] = useState<any>(null);
  const [attachmentUploading, setAttachmentUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ---- Step 3 — Targeting ----
  const [filterOptions, setFilterOptions] = useState<any>(null);
  const [allAgents, setAllAgents] = useState(false);
  const [cohortSegments, setCohortSegments] = useState<string[]>([]);
  const [regions, setRegions] = useState<string[]>([]);
  const [lifecycleStates, setLifecycleStates] = useState<string[]>([]);
  const [admIds, setAdmIds] = useState<number[]>([]);
  const [scoreMin, setScoreMin] = useState<string>('');
  const [scoreMax, setScoreMax] = useState<string>('');
  const [agentIdsCsv, setAgentIdsCsv] = useState<string>('');
  const [preview, setPreview] = useState<any>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  // ---- Step 4 — Schedule ----
  const [sendNow, setSendNow] = useState(true);
  const [scheduledAtLocal, setScheduledAtLocal] = useState<string>('');  // datetime-local

  // ---- Submit ----
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ---- Load filter options on mount ----
  useEffect(() => {
    if (!allowed) return;
    (async () => {
      try {
        const opts = await api.getBroadcastFilterOptions();
        setFilterOptions(opts);
      } catch (e: any) {
        setError(e?.message || 'Could not load filter options');
      }
    })();
  }, [allowed]);

  // ---- Live preview when targeting changes ----
  const filterSpec = useMemo(() => buildFilterSpec({
    allAgents, cohortSegments, regions, lifecycleStates, admIds,
    scoreMin, scoreMax, agentIdsCsv,
  }), [allAgents, cohortSegments, regions, lifecycleStates, admIds, scoreMin, scoreMax, agentIdsCsv]);

  useEffect(() => {
    if (step !== 3) return;
    let cancelled = false;
    setPreviewLoading(true);
    api.previewBroadcastRecipients(filterSpec)
      .then((p) => { if (!cancelled) setPreview(p); })
      .catch((e: any) => { if (!cancelled) setError(e?.message); })
      .finally(() => { if (!cancelled) setPreviewLoading(false); });
    return () => { cancelled = true; };
  }, [step, filterSpec]);

  if (!allowed) return <AccessRestricted />;

  // ---- Validation ----
  const step1Valid = !!type;
  const step2Valid = title.trim().length > 0 && body.trim().length > 0;
  const step3Valid = (preview?.reachable_telegram ?? 0) > 0;
  const step4Valid = sendNow || (!!scheduledAtLocal && new Date(scheduledAtLocal) > new Date());

  // ---- Submit ----
  const onSubmit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const payload: any = {
        type,
        title,
        body,
        link_url: linkUrl || undefined,
        link_label: linkLabel || undefined,
        target_filter: filterSpec,
        status: 'scheduled',
        scheduled_at: sendNow
          ? new Date().toISOString()
          : new Date(scheduledAtLocal).toISOString(),
      };
      if (attachmentFileId) payload.attachment_file_id = attachmentFileId;

      const result = await api.createBroadcast(payload);
      router.push(`/broadcasts/${result.id}`);
    } catch (e: any) {
      setError(e?.message || 'Could not create broadcast');
      setSubmitting(false);
    }
  };

  const onSaveDraft = async () => {
    if (!type || !title.trim() || !body.trim()) {
      setError('Title, body, and type are required even to save a draft');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const payload: any = {
        type, title, body,
        link_url: linkUrl || undefined,
        link_label: linkLabel || undefined,
        target_filter: filterSpec,
        status: 'draft',
      };
      if (attachmentFileId) payload.attachment_file_id = attachmentFileId;
      const result = await api.createBroadcast(payload);
      router.push(`/broadcasts/${result.id}`);
    } catch (e: any) {
      setError(e?.message || 'Could not save draft');
      setSubmitting(false);
    }
  };

  // ---- Attachment upload ----
  const onPickFile = () => fileInputRef.current?.click();
  const onFileChosen = async (file: File) => {
    setError(null);
    setAttachmentFile(file);
    setAttachmentUploading(true);
    try {
      const result = await api.uploadBroadcastAttachment(file);
      setAttachmentFileId(result.attachment_file_id);
      setAttachmentMeta(result);
    } catch (e: any) {
      setError(e?.message || 'Upload failed');
      setAttachmentFile(null);
    } finally {
      setAttachmentUploading(false);
    }
  };

  const clearAttachment = () => {
    setAttachmentFile(null);
    setAttachmentFileId(null);
    setAttachmentMeta(null);
  };

  // ============================== RENDER ==============================
  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <Link href="/broadcasts" className="text-sm text-gray-400 hover:text-gray-200 flex items-center gap-1">
            <ArrowLeft className="w-3 h-3" /> Back to broadcasts
          </Link>
          <h1 className="text-2xl font-semibold text-gray-100 mt-1 flex items-center gap-2">
            <Megaphone className="w-6 h-6 text-blue-300" /> New broadcast
          </h1>
        </div>
        <Stepper step={step} />
      </div>

      {error && (
        <div className="px-4 py-3 rounded-lg bg-red-500/10 border border-red-500/30 text-sm text-red-300">
          {error}
        </div>
      )}

      <div className="rounded-xl bg-white/[0.03] border border-white/5 p-6">
        {step === 1 && <Step1 type={type} setType={setType} />}
        {step === 2 && <Step2
          title={title} setTitle={setTitle}
          body={body} setBody={setBody}
          linkUrl={linkUrl} setLinkUrl={setLinkUrl}
          linkLabel={linkLabel} setLinkLabel={setLinkLabel}
          attachmentFile={attachmentFile}
          attachmentMeta={attachmentMeta}
          attachmentUploading={attachmentUploading}
          onPickFile={onPickFile}
          clearAttachment={clearAttachment}
          fileInputRef={fileInputRef}
          onFileChosen={onFileChosen}
        />}
        {step === 3 && <Step3
          filterOptions={filterOptions}
          allAgents={allAgents} setAllAgents={setAllAgents}
          cohortSegments={cohortSegments} setCohortSegments={setCohortSegments}
          regions={regions} setRegions={setRegions}
          lifecycleStates={lifecycleStates} setLifecycleStates={setLifecycleStates}
          admIds={admIds} setAdmIds={setAdmIds}
          scoreMin={scoreMin} setScoreMin={setScoreMin}
          scoreMax={scoreMax} setScoreMax={setScoreMax}
          agentIdsCsv={agentIdsCsv} setAgentIdsCsv={setAgentIdsCsv}
          preview={preview} previewLoading={previewLoading}
        />}
        {step === 4 && <Step4
          sendNow={sendNow} setSendNow={setSendNow}
          scheduledAtLocal={scheduledAtLocal}
          setScheduledAtLocal={setScheduledAtLocal}
        />}
        {step === 5 && <Step5
          type={type} title={title} body={body}
          linkUrl={linkUrl} linkLabel={linkLabel}
          attachmentMeta={attachmentMeta}
          preview={preview}
          sendNow={sendNow}
          scheduledAtLocal={scheduledAtLocal}
        />}
      </div>

      {/* Footer nav */}
      <div className="flex items-center justify-between">
        <div>
          {step > 1 && (
            <button
              onClick={() => setStep((s) => (s - 1) as any)}
              className="px-4 py-2 rounded-lg text-sm text-gray-200 bg-white/5 hover:bg-white/10 border border-white/10 flex items-center gap-2"
              disabled={submitting}
            >
              <ArrowLeft className="w-4 h-4" /> Back
            </button>
          )}
        </div>
        <div className="flex items-center gap-2">
          {(step === 2 || step === 3 || step === 4 || step === 5) && (
            <button
              onClick={onSaveDraft}
              disabled={submitting || !type || !title.trim() || !body.trim()}
              className="px-4 py-2 rounded-lg text-sm text-gray-200 bg-white/5 hover:bg-white/10 border border-white/10 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              <Save className="w-4 h-4" /> Save draft
            </button>
          )}
          {step < 5 ? (
            <button
              onClick={() => setStep((s) => (s + 1) as any)}
              disabled={
                (step === 1 && !step1Valid) ||
                (step === 2 && !step2Valid) ||
                (step === 3 && !step3Valid) ||
                (step === 4 && !step4Valid)
              }
              className="px-4 py-2 rounded-lg text-sm font-medium bg-blue-500/20 hover:bg-blue-500/30 text-blue-100 border border-blue-500/30 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              Next <ArrowRight className="w-4 h-4" />
            </button>
          ) : (
            <button
              onClick={onSubmit}
              disabled={submitting}
              className="px-4 py-2 rounded-lg text-sm font-medium bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-100 border border-emerald-500/30 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
              {sendNow ? 'Send now' : 'Schedule'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ============================== Sub-components ==============================

function Stepper({ step }: { step: number }) {
  const labels = ['Type', 'Content', 'Targeting', 'Schedule', 'Review'];
  return (
    <div className="flex items-center gap-1.5 text-[11px] text-gray-400">
      {labels.map((l, i) => (
        <span key={l} className="flex items-center gap-1.5">
          <span className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-medium ${
            step > i + 1 ? 'bg-emerald-500/40 text-emerald-100'
              : step === i + 1 ? 'bg-blue-500/40 text-blue-100'
              : 'bg-white/5 text-gray-500'
          }`}>{step > i + 1 ? <Check className="w-3 h-3" /> : i + 1}</span>
          <span className={step === i + 1 ? 'text-gray-200' : ''}>{l}</span>
          {i < labels.length - 1 && <span className="text-gray-700 ml-1">›</span>}
        </span>
      ))}
    </div>
  );
}

function Step1({ type, setType }: { type: string; setType: (t: string) => void }) {
  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold text-gray-100">What kind of broadcast?</h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {TYPE_OPTIONS.map((t) => {
          const Icon = t.icon;
          const active = type === t.key;
          return (
            <button
              key={t.key}
              onClick={() => setType(t.key)}
              className={`text-left p-4 rounded-lg border transition ${
                active ? 'bg-white/[0.06] border-blue-500/40' : 'bg-white/[0.02] border-white/10 hover:bg-white/[0.05]'
              }`}
            >
              <div className="flex items-center gap-3 mb-1">
                <div
                  className="w-9 h-9 rounded-lg flex items-center justify-center"
                  style={{ background: `${t.color}1f`, color: t.color }}
                >
                  <Icon className="w-5 h-5" />
                </div>
                <div className="text-base font-medium text-gray-100">{t.label}</div>
              </div>
              <div className="text-xs text-gray-400 mt-2">{t.desc}</div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function Step2(props: any) {
  const { title, setTitle, body, setBody, linkUrl, setLinkUrl, linkLabel, setLinkLabel,
    attachmentFile, attachmentMeta, attachmentUploading,
    onPickFile, clearAttachment, fileInputRef, onFileChosen } = props;
  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold text-gray-100">Message content</h2>

      <div>
        <label className="text-xs uppercase tracking-wider text-gray-500">Title</label>
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="e.g. New Term Plan launched"
          maxLength={300}
          className="mt-1 w-full px-3 py-2 rounded-lg bg-white/[0.03] border border-white/10 text-sm text-gray-100"
        />
      </div>

      <div>
        <label className="text-xs uppercase tracking-wider text-gray-500">Body</label>
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          rows={6}
          placeholder="The full message text. Supports plain text and basic line breaks."
          className="mt-1 w-full px-3 py-2 rounded-lg bg-white/[0.03] border border-white/10 text-sm text-gray-100 resize-y"
        />
        <div className="text-[10px] text-gray-500 mt-1">{body.length} characters</div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label className="text-xs uppercase tracking-wider text-gray-500">Link URL (optional)</label>
          <input
            type="url"
            value={linkUrl}
            onChange={(e) => setLinkUrl(e.target.value)}
            placeholder="https://…"
            className="mt-1 w-full px-3 py-2 rounded-lg bg-white/[0.03] border border-white/10 text-sm text-gray-100"
          />
        </div>
        <div>
          <label className="text-xs uppercase tracking-wider text-gray-500">Link label</label>
          <input
            type="text"
            value={linkLabel}
            onChange={(e) => setLinkLabel(e.target.value)}
            placeholder="Open module"
            className="mt-1 w-full px-3 py-2 rounded-lg bg-white/[0.03] border border-white/10 text-sm text-gray-100"
          />
        </div>
      </div>

      <div>
        <label className="text-xs uppercase tracking-wider text-gray-500">Attachment (optional)</label>
        <div className="mt-1">
          {attachmentMeta ? (
            <div className="px-3 py-2 rounded-lg bg-white/[0.03] border border-white/10 flex items-center gap-3">
              <Paperclip className="w-4 h-4 text-gray-400" />
              <div className="flex-1 min-w-0">
                <div className="text-sm text-gray-100 truncate">{attachmentMeta.file_name}</div>
                <div className="text-[11px] text-gray-500">
                  {attachmentMeta.kind} · {(attachmentMeta.size / 1024).toFixed(1)} KB
                </div>
              </div>
              <button onClick={clearAttachment} className="text-gray-400 hover:text-gray-200">
                <X className="w-4 h-4" />
              </button>
            </div>
          ) : (
            <button
              onClick={onPickFile}
              disabled={attachmentUploading}
              className="w-full px-3 py-3 rounded-lg bg-white/[0.02] border border-dashed border-white/15 text-sm text-gray-400 hover:bg-white/[0.04] hover:border-white/25 flex items-center justify-center gap-2"
            >
              {attachmentUploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Paperclip className="w-4 h-4" />}
              {attachmentUploading ? 'Uploading…' : 'Attach image, PDF, voice note, or document'}
            </button>
          )}
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*,.pdf,.ogg,.opus,.mp3,.wav,.m4a,.doc,.docx,.xls,.xlsx,.csv,.txt"
            className="hidden"
            onChange={(e) => e.target.files?.[0] && onFileChosen(e.target.files[0])}
          />
        </div>
        <div className="text-[10px] text-gray-500 mt-1">
          Image renders inline · .ogg/.opus plays as voice message · PDFs and others go as documents · 20MB max
        </div>
      </div>
    </div>
  );
}

function Step3(props: any) {
  const {
    filterOptions, allAgents, setAllAgents, cohortSegments, setCohortSegments,
    regions, setRegions, lifecycleStates, setLifecycleStates,
    admIds, setAdmIds, scoreMin, setScoreMin, scoreMax, setScoreMax,
    agentIdsCsv, setAgentIdsCsv, preview, previewLoading,
  } = props;
  const opts = filterOptions || { cohort_segments: [], regions: [], lifecycle_states: [], adms: [] };

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold text-gray-100">Who should receive this?</h2>

      <label className="flex items-center gap-2 cursor-pointer">
        <input
          type="checkbox"
          checked={allAgents}
          onChange={(e) => setAllAgents(e.target.checked)}
          className="accent-blue-500"
        />
        <span className="text-sm text-gray-200">All Telegram-registered agents</span>
      </label>

      {!allAgents && (
        <div className="space-y-3">
          <MultiSelect
            label="Cohort segments"
            options={opts.cohort_segments.map((k: string) => ({ value: k, label: COHORT_LABELS[k] || k }))}
            selected={cohortSegments}
            setSelected={setCohortSegments}
          />
          <MultiSelect
            label="Regions"
            options={opts.regions.map((r: string) => ({ value: r, label: r }))}
            selected={regions}
            setSelected={setRegions}
          />
          <MultiSelect
            label="Lifecycle states"
            options={opts.lifecycle_states.map((s: string) => ({ value: s, label: LIFECYCLE_LABELS[s] || s }))}
            selected={lifecycleStates}
            setSelected={setLifecycleStates}
          />
          <MultiSelect
            label="Assigned ADMs"
            options={opts.adms.map((a: any) => ({ value: String(a.id), label: a.name + (a.region ? ` · ${a.region}` : '') }))}
            selected={admIds.map(String)}
            setSelected={(arr: string[]) => setAdmIds(arr.map(Number))}
          />
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs uppercase tracking-wider text-gray-500">Reactivation score ≥</label>
              <input type="number" value={scoreMin} onChange={(e) => setScoreMin(e.target.value)}
                placeholder="(any)" min={0} max={100}
                className="mt-1 w-full px-3 py-2 rounded-lg bg-white/[0.03] border border-white/10 text-sm text-gray-100" />
            </div>
            <div>
              <label className="text-xs uppercase tracking-wider text-gray-500">Reactivation score ≤</label>
              <input type="number" value={scoreMax} onChange={(e) => setScoreMax(e.target.value)}
                placeholder="(any)" min={0} max={100}
                className="mt-1 w-full px-3 py-2 rounded-lg bg-white/[0.03] border border-white/10 text-sm text-gray-100" />
            </div>
          </div>
          <div>
            <label className="text-xs uppercase tracking-wider text-gray-500">Custom agent IDs (comma-separated)</label>
            <input type="text" value={agentIdsCsv} onChange={(e) => setAgentIdsCsv(e.target.value)}
              placeholder="e.g. 12, 47, 89"
              className="mt-1 w-full px-3 py-2 rounded-lg bg-white/[0.03] border border-white/10 text-sm text-gray-100 font-mono" />
          </div>
        </div>
      )}

      <div className="rounded-lg bg-blue-500/[0.05] border border-blue-500/20 p-4">
        <div className="flex items-center justify-between mb-2">
          <div className="text-xs uppercase tracking-wider text-blue-300 flex items-center gap-1.5">
            <Users className="w-3.5 h-3.5" /> Resolved recipients
          </div>
          {previewLoading && <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-300" />}
        </div>
        {preview ? (
          <div>
            <div className="text-2xl font-semibold text-blue-100">
              {preview.reachable_telegram} <span className="text-sm text-blue-300 font-normal">agents reachable on Telegram</span>
            </div>
            <div className="text-xs text-blue-200/70 mt-1">
              {preview.total_matched} matched the filter · {preview.skipped_no_chat} will be skipped (no Telegram link)
            </div>
            {preview.sample_recipients?.length > 0 && (
              <div className="mt-3">
                <div className="text-[10px] uppercase tracking-wider text-blue-300/70 mb-1">Sample</div>
                <div className="flex flex-wrap gap-1.5">
                  {preview.sample_recipients.map((a: any) => (
                    <span key={a.id} className="px-2 py-0.5 rounded-md bg-blue-500/15 text-[11px] text-blue-100">
                      {a.name} · {a.location}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="text-xs text-gray-400">Adjust filters to see who'll receive this.</div>
        )}
      </div>
    </div>
  );
}

function Step4({ sendNow, setSendNow, scheduledAtLocal, setScheduledAtLocal }: any) {
  // Default to "5 min from now" when switching to schedule mode
  useEffect(() => {
    if (!sendNow && !scheduledAtLocal) {
      const t = new Date(Date.now() + 5 * 60 * 1000);
      const iso = t.toISOString().slice(0, 16);
      setScheduledAtLocal(iso);
    }
  }, [sendNow]); // eslint-disable-line

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold text-gray-100">When?</h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <button
          onClick={() => setSendNow(true)}
          className={`p-4 rounded-lg border text-left transition ${
            sendNow ? 'bg-white/[0.06] border-blue-500/40' : 'bg-white/[0.02] border-white/10 hover:bg-white/[0.05]'
          }`}
        >
          <div className="flex items-center gap-2 mb-1">
            <Send className="w-4 h-4 text-emerald-300" />
            <div className="text-sm font-medium text-gray-100">Send now</div>
          </div>
          <div className="text-xs text-gray-400">Dispatcher picks it up within ~10 seconds.</div>
        </button>
        <button
          onClick={() => setSendNow(false)}
          className={`p-4 rounded-lg border text-left transition ${
            !sendNow ? 'bg-white/[0.06] border-blue-500/40' : 'bg-white/[0.02] border-white/10 hover:bg-white/[0.05]'
          }`}
        >
          <div className="flex items-center gap-2 mb-1">
            <Calendar className="w-4 h-4 text-blue-300" />
            <div className="text-sm font-medium text-gray-100">Schedule for later</div>
          </div>
          <div className="text-xs text-gray-400">Pick a date and time.</div>
        </button>
      </div>

      {!sendNow && (
        <div>
          <label className="text-xs uppercase tracking-wider text-gray-500">Date and time</label>
          <input
            type="datetime-local"
            value={scheduledAtLocal}
            min={new Date().toISOString().slice(0, 16)}
            onChange={(e) => setScheduledAtLocal(e.target.value)}
            className="mt-1 px-3 py-2 rounded-lg bg-white/[0.03] border border-white/10 text-sm text-gray-100"
          />
        </div>
      )}
    </div>
  );
}

function Step5(props: any) {
  const { type, title, body, linkUrl, linkLabel, attachmentMeta, preview, sendNow, scheduledAtLocal } = props;
  const typeOpt = TYPE_OPTIONS.find((t) => t.key === type);
  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold text-gray-100">Review and send</h2>

      {/* Telegram-style preview */}
      <div className="max-w-md">
        <div className="text-xs uppercase tracking-wider text-gray-500 mb-2">Preview (as it appears on Telegram)</div>
        <div className="rounded-2xl bg-[#212121] border border-white/10 p-3 text-sm text-gray-100">
          {attachmentMeta && (
            <div className="mb-2 px-2 py-1.5 rounded-md bg-white/[0.05] text-[11px] text-gray-300 flex items-center gap-2">
              <Paperclip className="w-3 h-3" />
              {attachmentMeta.file_name} <span className="text-gray-500">({attachmentMeta.kind})</span>
            </div>
          )}
          <div className="font-semibold mb-1">{title || '(no title)'}</div>
          <div className="whitespace-pre-wrap">{body || '(no body)'}</div>
          {linkUrl && (
            <div className="mt-2 text-blue-300 underline">{linkLabel || linkUrl}</div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="rounded-lg bg-white/[0.03] border border-white/5 p-3">
          <div className="text-[11px] uppercase tracking-wider text-gray-500">Type</div>
          <div className="text-sm text-gray-100 mt-1">{typeOpt?.label || '—'}</div>
        </div>
        <div className="rounded-lg bg-white/[0.03] border border-white/5 p-3">
          <div className="text-[11px] uppercase tracking-wider text-gray-500">Recipients</div>
          <div className="text-sm text-gray-100 mt-1">
            {preview?.reachable_telegram ?? 0} on Telegram
          </div>
        </div>
        <div className="rounded-lg bg-white/[0.03] border border-white/5 p-3">
          <div className="text-[11px] uppercase tracking-wider text-gray-500">When</div>
          <div className="text-sm text-gray-100 mt-1">
            {sendNow ? 'Send now' : new Date(scheduledAtLocal).toLocaleString()}
          </div>
        </div>
      </div>
    </div>
  );
}

function MultiSelect({
  label, options, selected, setSelected,
}: {
  label: string;
  options: { value: string; label: string }[];
  selected: string[];
  setSelected: (v: string[]) => void;
}) {
  const toggle = (v: string) => {
    if (selected.includes(v)) setSelected(selected.filter((x) => x !== v));
    else setSelected([...selected, v]);
  };
  return (
    <div>
      <label className="text-xs uppercase tracking-wider text-gray-500">{label}</label>
      <div className="mt-1 flex flex-wrap gap-1.5">
        {options.length === 0 && <span className="text-xs text-gray-500">No options available.</span>}
        {options.map((o) => {
          const active = selected.includes(o.value);
          return (
            <button
              key={o.value}
              onClick={() => toggle(o.value)}
              className={`px-2.5 py-1 rounded-md text-xs border transition ${
                active
                  ? 'bg-blue-500/20 border-blue-500/40 text-blue-100'
                  : 'bg-white/[0.03] border-white/10 text-gray-300 hover:bg-white/[0.06]'
              }`}
            >
              {o.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function AccessRestricted() {
  return (
    <div className="max-w-xl mx-auto mt-16 text-center">
      <ShieldAlert className="w-12 h-12 mx-auto text-red-400 mb-4" />
      <h2 className="text-xl font-semibold text-gray-200">Access restricted</h2>
      <p className="mt-2 text-sm text-gray-400">
        Broadcasts can only be composed by admin / Agency Development users.
      </p>
    </div>
  );
}

// ---- helpers ----
function buildFilterSpec(args: {
  allAgents: boolean;
  cohortSegments: string[];
  regions: string[];
  lifecycleStates: string[];
  admIds: number[];
  scoreMin: string;
  scoreMax: string;
  agentIdsCsv: string;
}): Record<string, any> {
  const out: Record<string, any> = {};
  if (args.allAgents) {
    out.all_agents = true;
    return out;
  }
  if (args.cohortSegments.length) out.cohort_segments = args.cohortSegments;
  if (args.regions.length) out.regions = args.regions;
  if (args.lifecycleStates.length) out.lifecycle_states = args.lifecycleStates;
  if (args.admIds.length) out.adm_ids = args.admIds;
  if (args.scoreMin !== '') out.score_min = parseFloat(args.scoreMin);
  if (args.scoreMax !== '') out.score_max = parseFloat(args.scoreMax);
  const ids = args.agentIdsCsv.split(',').map((s) => s.trim()).filter(Boolean).map(Number).filter((n) => !isNaN(n));
  if (ids.length) out.agent_ids = ids;
  return out;
}
