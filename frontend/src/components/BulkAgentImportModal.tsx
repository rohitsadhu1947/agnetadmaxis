'use client';

import { useState } from 'react';
import {
  X,
  Upload,
  FileSpreadsheet,
  Eye,
  Download,
  Loader2,
  CheckCircle,
  AlertTriangle,
} from 'lucide-react';
import { api } from '@/lib/api';

interface BulkAgentImportModalProps {
  mode: 'admin' | 'adm' | 'cohort';
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

const ADMIN_TEMPLATE = `name,phone,location,email,state,language,lifecycle_state,license_number,specialization,assigned_adm_id`;
const ADMIN_SAMPLE = `name,phone,location,email,state,language,lifecycle_state,license_number,specialization,assigned_adm_id
Rajesh Kumar,9876543210,Mumbai,rajesh@email.com,Maharashtra,Hindi,dormant,LIC001,Life Insurance,
Anita Sharma,9876543211,Delhi,,Delhi,English,at_risk,,,`;

const ADM_TEMPLATE = `name,phone,location,email,state,language,license_number,specialization`;
const ADM_SAMPLE = `name,phone,location,email,state,language,license_number,specialization
Rajesh Kumar,9876543210,Mumbai,rajesh@email.com,Maharashtra,Hindi,LIC001,Life Insurance
Anita Sharma,9876543211,Delhi,,Delhi,English,,`;

const COHORT_TEMPLATE = `name,phone,location,email,state,language,total_policies_sold,policies_last_12_months,premium_last_12_months,avg_ticket_size,persistency_ratio,days_since_last_activity,contact_attempts,contact_responses,years_in_insurance,work_type,age,education_level,has_app_installed,dormancy_reason`;
const COHORT_SAMPLE = `name,phone,location,email,state,language,total_policies_sold,policies_last_12_months,premium_last_12_months,avg_ticket_size,persistency_ratio,days_since_last_activity,contact_attempts,contact_responses,years_in_insurance,work_type,age,education_level,has_app_installed,dormancy_reason
Rajesh Kumar,9876543210,Mumbai,rajesh@email.com,Maharashtra,Hindi,15,3,250000,50000,0.7,45,5,3,2.5,full_time,35,Graduate,true,commission issues
Anita Sharma,9876543211,Delhi,,Delhi,English,0,0,0,0,0,180,2,0,0.5,part_time,28,Post Graduate,false,no training`;

const REQUIRED_FIELDS = ['name', 'phone', 'location'];

export default function BulkAgentImportModal({
  mode,
  isOpen,
  onClose,
  onSuccess,
}: BulkAgentImportModalProps) {
  const [csvText, setCsvText] = useState('');
  const [parsed, setParsed] = useState<any[]>([]);
  const [parseError, setParseError] = useState('');
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<any>(null);

  const template = mode === 'cohort' ? COHORT_TEMPLATE : mode === 'admin' ? ADMIN_TEMPLATE : ADM_TEMPLATE;
  const sample = mode === 'cohort' ? COHORT_SAMPLE : mode === 'admin' ? ADMIN_SAMPLE : ADM_SAMPLE;

  const resetState = () => {
    setCsvText('');
    setParsed([]);
    setParseError('');
    setUploading(false);
    setResult(null);
  };

  const handleClose = () => {
    resetState();
    onClose();
  };

  const handleParseCSV = () => {
    setParseError('');
    setParsed([]);
    setResult(null);

    if (!csvText.trim()) {
      setParseError('Please paste CSV or tab-separated data');
      return;
    }

    const lines = csvText.trim().split('\n');
    if (lines.length < 2) {
      setParseError('Data must have a header row and at least one data row');
      return;
    }

    // Auto-detect delimiter
    const delimiter = lines[0].includes('\t') ? '\t' : ',';
    const headers = lines[0]
      .split(delimiter)
      .map((h) => h.trim().toLowerCase().replace(/\s+/g, '_'));

    // Validate required columns
    const missing = REQUIRED_FIELDS.filter((f) => !headers.includes(f));
    if (missing.length) {
      setParseError(`Missing required columns: ${missing.join(', ')}`);
      return;
    }

    const rows: any[] = [];
    for (let i = 1; i < lines.length; i++) {
      if (!lines[i].trim()) continue;
      const vals = lines[i].split(delimiter).map((v) => v.trim());
      const row: any = {};
      headers.forEach((h, idx) => {
        row[h] = vals[idx] || '';
      });

      // Validate required values
      const missingVals = REQUIRED_FIELDS.filter((f) => !row[f]);
      if (missingVals.length) {
        setParseError(
          `Row ${i + 1}: missing required value(s): ${missingVals.join(', ')}`
        );
        return;
      }

      // Set defaults
      row.language = row.language || 'Hindi';
      row.lifecycle_state = row.lifecycle_state || 'dormant';

      // Parse assigned_adm_id as number if present
      if (row.assigned_adm_id) {
        row.assigned_adm_id = parseInt(row.assigned_adm_id) || undefined;
      } else {
        delete row.assigned_adm_id;
      }

      // Clean empty optional fields
      ['email', 'state', 'license_number', 'specialization', 'dormancy_reason'].forEach((f) => {
        if (row[f] === '') delete row[f];
      });

      rows.push(row);
    }

    if (rows.length === 0) {
      setParseError('No valid data rows found');
      return;
    }

    setParsed(rows);
  };

  const handleUpload = async () => {
    if (!parsed.length) return;
    setUploading(true);
    setResult(null);

    try {
      let res: any;
      if (mode === 'cohort') {
        // Convert parsed data back to CSV and upload as file
        const headers = Object.keys(parsed[0]);
        const csvContent = [
          headers.join(','),
          ...parsed.map(row => headers.map(h => row[h] ?? '').join(',')),
        ].join('\n');
        const blob = new Blob([csvContent], { type: 'text/csv' });
        const file = new File([blob], 'cohort_upload.csv', { type: 'text/csv' });
        res = await api.bulkUploadCohort(file);
        // Normalize response for cohort
        res.created = res.total_uploaded || res.created || 0;
        res.total_submitted = parsed.length;
      } else {
        res = await api.bulkImportAgents(parsed);
      }
      setResult(res);
      if (res.created > 0 || res.total_uploaded > 0) {
        onSuccess();
      }
    } catch (e: any) {
      setResult({ error: true, message: e.message || 'Upload failed' });
    } finally {
      setUploading(false);
    }
  };

  if (!isOpen) return null;

  // Determine preview columns from parsed data
  const previewCols = parsed.length > 0
    ? mode === 'cohort'
      ? ['name', 'phone', 'location', 'total_policies_sold', 'premium_last_12_months', 'years_in_insurance', 'work_type']
      : ['name', 'phone', 'location', 'state', 'language', 'lifecycle_state', ...(mode === 'admin' ? ['assigned_adm_id'] : [])]
    : [];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-surface-card border border-surface-border rounded-xl w-full max-w-4xl mx-4 max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-surface-border sticky top-0 bg-surface-card z-10">
          <h2 className="text-lg font-semibold text-white flex items-center gap-2">
            <Upload className="w-5 h-5 text-brand-red" />
            Bulk Import Agents
          </h2>
          <button
            onClick={handleClose}
            className="p-1 rounded-lg hover:bg-white/5 text-gray-400 hover:text-white transition-all"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-5 space-y-5">
          {/* Instructions */}
          <div>
            <p className="text-sm text-gray-400">
              Paste CSV or tab-separated data below. Required columns:{' '}
              <span className="text-white font-medium">name, phone, location</span>.
              {mode === 'cohort' && (
                <> Cohort fields: <span className="text-gray-300">total_policies_sold, premium_last_12_months, persistency_ratio, years_in_insurance, work_type, contact_attempts, etc.</span>
                <span className="block mt-1 text-xs text-emerald-400/80">Agents will be auto-classified into cohort segments with reactivation scores.</span></>
              )}
              {mode === 'admin' && (
                <> Optional: <span className="text-gray-300">email, state, language, lifecycle_state, license_number, specialization, assigned_adm_id</span></>
              )}
              {mode === 'adm' && (
                <> Optional: <span className="text-gray-300">email, state, language, license_number, specialization</span></>
              )}
            </p>
            {mode === 'adm' && (
              <p className="text-xs text-amber-400/80 mt-2">
                Agents will be onboarded as unassigned. Admin will handle ADM assignment via the Assignment tab.
              </p>
            )}
          </div>

          {/* Template */}
          <div className="bg-[#0B1120] rounded-lg p-4 border border-surface-border/20">
            <p className="text-[11px] text-gray-500 uppercase tracking-wider mb-2">
              Sample Template
            </p>
            <code className="text-xs text-emerald-400 block whitespace-pre leading-relaxed overflow-x-auto">
              {sample}
            </code>
            <button
              onClick={() => {
                setCsvText(template + '\n');
                setParsed([]);
                setParseError('');
                setResult(null);
              }}
              className="mt-2 text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1"
            >
              <Download className="w-3 h-3" />
              Use Template
            </button>
          </div>

          {/* Text Area */}
          <textarea
            value={csvText}
            onChange={(e) => {
              setCsvText(e.target.value);
              setParsed([]);
              setParseError('');
              setResult(null);
            }}
            rows={8}
            placeholder="Paste your CSV or tab-separated data here..."
            className="w-full p-4 rounded-lg bg-[#0B1120] border border-surface-border/30 text-sm text-white placeholder-gray-600 font-mono focus:outline-none focus:border-brand-red/30 resize-y"
          />

          {/* Parse Error */}
          {parseError && (
            <div className="flex items-center gap-2 text-sm text-red-400">
              <AlertTriangle className="w-4 h-4 flex-shrink-0" />
              {parseError}
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex items-center gap-3">
            <button
              onClick={handleParseCSV}
              disabled={!csvText.trim()}
              className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-surface-card border border-surface-border text-gray-300 hover:text-white text-sm font-medium disabled:opacity-40 transition-all"
            >
              <Eye className="w-4 h-4" />
              Preview & Validate
            </button>
            {parsed.length > 0 && !result && (
              <button
                onClick={handleUpload}
                disabled={uploading}
                className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-brand-red hover:bg-brand-red/90 text-white text-sm font-medium disabled:opacity-40 transition-all"
              >
                {uploading ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Upload className="w-4 h-4" />
                )}
                Import {parsed.length} Agents
              </button>
            )}
          </div>

          {/* Preview Table */}
          {parsed.length > 0 && !result && (
            <div className="rounded-lg border border-surface-border/30 overflow-hidden">
              <div className="px-4 py-3 border-b border-surface-border/20 bg-surface-card/50">
                <h4 className="text-sm font-semibold text-white flex items-center gap-2">
                  <CheckCircle className="w-4 h-4 text-emerald-400" />
                  Preview: {parsed.length} agents ready to import
                  {parsed.length > 20 && (
                    <span className="text-xs text-gray-500 font-normal">
                      (showing first 20)
                    </span>
                  )}
                </h4>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-surface-border/20">
                      <th className="text-left text-[11px] font-medium text-gray-500 uppercase px-4 py-2">
                        #
                      </th>
                      {previewCols.map((col) => (
                        <th
                          key={col}
                          className="text-left text-[11px] font-medium text-gray-500 uppercase px-4 py-2"
                        >
                          {col.replace(/_/g, ' ')}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {parsed.slice(0, 20).map((row, idx) => (
                      <tr
                        key={idx}
                        className="border-b border-surface-border/10"
                      >
                        <td className="px-4 py-2 text-xs text-gray-500">
                          {idx + 1}
                        </td>
                        {previewCols.map((col) => (
                          <td
                            key={col}
                            className={`px-4 py-2 text-sm ${
                              REQUIRED_FIELDS.includes(col)
                                ? 'text-white'
                                : 'text-gray-300'
                            }`}
                          >
                            {row[col] ?? '-'}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Result */}
          {result && (
            <div
              className={`rounded-lg p-5 border ${
                result.error
                  ? 'border-red-500/20 bg-red-500/5'
                  : result.errors_count > 0
                  ? 'border-amber-500/20 bg-amber-500/5'
                  : 'border-emerald-500/20 bg-emerald-500/5'
              }`}
            >
              <div className="flex items-start gap-3">
                {result.error ? (
                  <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
                ) : result.errors_count > 0 ? (
                  <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
                ) : (
                  <CheckCircle className="w-5 h-5 text-emerald-400 flex-shrink-0 mt-0.5" />
                )}
                <div className="flex-1 min-w-0">
                  {result.error ? (
                    <>
                      <h3 className="text-sm font-semibold text-white">
                        Import Failed
                      </h3>
                      <p className="text-sm text-red-400 mt-1">
                        {result.message}
                      </p>
                    </>
                  ) : (
                    <>
                      <h3 className="text-sm font-semibold text-white">
                        Import Complete: {result.created || result.total_uploaded || 0} of{' '}
                        {result.total_submitted || parsed.length} agents {mode === 'cohort' ? 'classified' : 'created'}
                      </h3>
                      {mode === 'cohort' && result.segment_summary && Object.keys(result.segment_summary).length > 0 && (
                        <div className="mt-3 p-3 rounded-lg bg-blue-500/5 border border-blue-500/10">
                          <p className="text-xs text-blue-400 font-medium mb-2">Cohort Classification:</p>
                          <div className="grid grid-cols-2 gap-1">
                            {Object.entries(result.segment_summary).map(([seg, count]: [string, any]) => (
                              <div key={seg} className="flex justify-between text-xs">
                                <span className="text-gray-400">{seg.replace(/_/g, ' ')}</span>
                                <span className="text-white font-medium">{count}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                      {result.errors_count > 0 && result.errors?.length > 0 && (
                        <div className="mt-3 p-3 rounded-lg bg-red-500/5 border border-red-500/10">
                          <p className="text-xs text-red-400 font-medium mb-1">
                            Errors ({result.errors_count}):
                          </p>
                          {result.errors
                            .slice(0, 10)
                            .map((err: any, i: number) => (
                              <p
                                key={i}
                                className="text-xs text-red-400/80"
                              >
                                {typeof err === 'string'
                                  ? err
                                  : `${err.phone || `Row ${err.index + 1}`}: ${err.error}`}
                              </p>
                            ))}
                          {result.errors.length > 10 && (
                            <p className="text-xs text-gray-500 mt-1">
                              ...and {result.errors.length - 10} more
                            </p>
                          )}
                        </div>
                      )}
                    </>
                  )}

                  {/* Reset / Close buttons */}
                  <div className="flex items-center gap-3 mt-4">
                    {!result.error && result.created > 0 && (
                      <button
                        onClick={handleClose}
                        className="px-4 py-2 rounded-lg bg-brand-red hover:bg-brand-red/90 text-white text-sm font-medium transition-all"
                      >
                        Done
                      </button>
                    )}
                    <button
                      onClick={resetState}
                      className="px-4 py-2 rounded-lg bg-surface-card border border-surface-border text-gray-300 hover:text-white text-sm transition-all"
                    >
                      Import More
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
