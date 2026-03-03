'use client';

import { useState, useMemo } from 'react';
import { Search, Filter, Users, UserCheck, AlertTriangle, Phone, Eye, Upload } from 'lucide-react';
import { api } from '@/lib/api';
import { useAPI } from '@/lib/useAPI';
import StatusBadge from '@/components/StatusBadge';
import AgentDetailPanel from '@/components/AgentDetailPanel';
import BulkAgentImportModal from '@/components/BulkAgentImportModal';

const dormancyReasonLabels: Record<string, string> = {
  no_leads: 'No Quality Leads',
  low_commission: 'Low Commission',
  personal_issues: 'Personal Issues',
  product_confusion: 'Product Confusion',
  poor_support: 'Poor Support',
  market_competition: 'Market Competition',
  tech_issues: 'Technical Issues',
  lack_of_training: 'Lack of Training',
};

export default function AgentsPage() {
  const { data: apiAgents, loading, refetch } = useAPI(() => api.listAgents({ limit: '200' }));
  const { data: apiADMs } = useAPI(() => api.listADMs());
  const agents = apiAgents || [];
  const adms = apiADMs || [];

  const [search, setSearch] = useState('');
  const [stateFilter, setStateFilter] = useState<string>('all');
  const [regionFilter, setRegionFilter] = useState<string>('all');
  const [reasonFilter, setReasonFilter] = useState<string>('all');
  const [selectedAgent, setSelectedAgent] = useState<any | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [showBulkImport, setShowBulkImport] = useState(false);
  const pageSize = 10;

  const admMap = useMemo(() => {
    const m: Record<number, string> = {};
    (adms as any[]).forEach((a: any) => (m[a.id] = a.name));
    return m;
  }, [adms]);

  const regions = useMemo(() => [...new Set(agents.map((a: any) => a.state).filter(Boolean))].sort() as string[], [agents]);

  const filteredAgents = useMemo(() => {
    return agents.filter((agent: any) => {
      const matchesSearch =
        (agent.name || '').toLowerCase().includes(search.toLowerCase()) ||
        String(agent.id).includes(search.toLowerCase()) ||
        (agent.location || '').toLowerCase().includes(search.toLowerCase());
      const matchesState = stateFilter === 'all' || agent.lifecycle_state === stateFilter;
      const matchesRegion = regionFilter === 'all' || agent.state === regionFilter;
      const matchesReason = reasonFilter === 'all' || (agent.dormancy_reason || '').includes(reasonFilter);
      return matchesSearch && matchesState && matchesRegion && matchesReason;
    });
  }, [agents, search, stateFilter, regionFilter, reasonFilter]);

  const totalPages = Math.ceil(filteredAgents.length / pageSize);
  const paginatedAgents = filteredAgents.slice(
    (currentPage - 1) * pageSize,
    currentPage * pageSize
  );

  const statCounts = useMemo(() => ({
    total: agents.length,
    active: agents.filter((a: any) => a.lifecycle_state === 'active').length,
    dormant: agents.filter((a: any) => a.lifecycle_state === 'dormant').length,
    at_risk: agents.filter((a: any) => a.lifecycle_state === 'at_risk').length,
    contacted: agents.filter((a: any) => a.lifecycle_state === 'contacted').length,
  }), [agents]);

  const getDormancyDays = (agent: any) => {
    if (agent.dormancy_duration_days) return agent.dormancy_duration_days;
    const lastDate = agent.last_contact_date || agent.updated_at;
    if (!lastDate) return 0;
    return Math.floor((new Date().getTime() - new Date(lastDate).getTime()) / (1000 * 60 * 60 * 24));
  };

  const getRiskScore = (agent: any) => {
    return Math.min(100, Math.round((agent.dormancy_duration_days || 0) / 3.65));
  };

  if (loading) {
    return <div className="flex items-center justify-center py-20"><div className="w-8 h-8 border-2 border-gray-500 border-t-white rounded-full animate-spin" /></div>;
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Agent Management</h1>
          <p className="text-sm text-gray-400 mt-1">
            Monitor and manage agent lifecycle across all regions
          </p>
        </div>
        <button
          onClick={() => setShowBulkImport(true)}
          className="flex items-center gap-2 px-4 py-2 bg-surface-card border border-surface-border text-gray-300 hover:text-white hover:border-brand-red/30 rounded-lg text-sm font-medium transition-all"
        >
          <Upload className="w-4 h-4" />
          Bulk Import
        </button>
      </div>

      {/* Stats Bar */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {[
          { label: 'Total Agents', value: statCounts.total, color: 'text-white', bg: 'bg-surface-card/60' },
          { label: 'Active', value: statCounts.active, color: 'text-emerald-400', bg: 'bg-emerald-500/5' },
          { label: 'Dormant', value: statCounts.dormant, color: 'text-red-400', bg: 'bg-red-500/5' },
          { label: 'At Risk', value: statCounts.at_risk, color: 'text-amber-400', bg: 'bg-amber-500/5' },
          { label: 'Contacted', value: statCounts.contacted, color: 'text-blue-400', bg: 'bg-blue-500/5' },
        ].map((stat) => (
          <div
            key={stat.label}
            className={`${stat.bg} border border-surface-border/40 rounded-lg p-3 text-center`}
          >
            <p className={`text-2xl font-bold ${stat.color}`}>{stat.value}</p>
            <p className="text-xs text-gray-500 mt-0.5">{stat.label}</p>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="glass-card p-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative flex-1 min-w-[220px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
            <input
              type="text"
              placeholder="Search by name, ID, or city..."
              value={search}
              onChange={(e) => { setSearch(e.target.value); setCurrentPage(1); }}
              className="w-full pl-10 pr-4 py-2 input-dark text-sm"
            />
          </div>

          <select
            value={stateFilter}
            onChange={(e) => { setStateFilter(e.target.value); setCurrentPage(1); }}
            className="input-dark text-sm py-2 min-w-[140px]"
          >
            <option value="all">All States</option>
            <option value="dormant">Dormant</option>
            <option value="at_risk">At Risk</option>
            <option value="contacted">Contacted</option>
            <option value="engaged">Engaged</option>
            <option value="trained">Trained</option>
            <option value="active">Active</option>
          </select>

          <select
            value={regionFilter}
            onChange={(e) => { setRegionFilter(e.target.value); setCurrentPage(1); }}
            className="input-dark text-sm py-2 min-w-[120px]"
          >
            <option value="all">All Regions</option>
            {regions.map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>

          <select
            value={reasonFilter}
            onChange={(e) => { setReasonFilter(e.target.value); setCurrentPage(1); }}
            className="input-dark text-sm py-2 min-w-[160px]"
          >
            <option value="all">All Reasons</option>
            {Object.entries(dormancyReasonLabels).map(([key, label]) => (
              <option key={key} value={key}>{label}</option>
            ))}
          </select>

          <div className="text-xs text-gray-500">
            {filteredAgents.length} results
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="glass-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-surface-border bg-surface-card/30">
                {['Agent', 'Phone', 'Region', 'State', 'Dormancy Days', 'Reason', 'Cohort', 'Score', 'ADM', 'Status', ''].map(
                  (header) => (
                    <th
                      key={header}
                      className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider"
                    >
                      {header}
                    </th>
                  )
                )}
              </tr>
            </thead>
            <tbody>
              {paginatedAgents.map((agent: any) => {
                const initials = agent.name ? agent.name.split(' ').map((n: string) => n[0]).join('').slice(0, 2) : '??';
                const dormancyDays = getDormancyDays(agent);
                const riskScore = getRiskScore(agent);
                return (
                <tr
                  key={agent.id}
                  className="border-b border-surface-border/30 hover:bg-surface-card-hover/50 transition-colors cursor-pointer"
                  onClick={() => setSelectedAgent(agent)}
                >
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-full bg-gradient-to-br from-brand-red/80 to-brand-navy flex items-center justify-center flex-shrink-0">
                        <span className="text-white font-medium text-[10px]">
                          {initials}
                        </span>
                      </div>
                      <div>
                        <p className="text-sm font-medium text-white">{agent.name}</p>
                        <p className="text-[11px] text-gray-500">{String(agent.id)}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-400">{agent.phone}</td>
                  <td className="px-4 py-3">
                    <div>
                      <p className="text-sm text-gray-300">{agent.location}</p>
                      <p className="text-[11px] text-gray-500">{agent.state}</p>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={agent.lifecycle_state} />
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`text-sm font-medium ${
                        dormancyDays > 120
                          ? 'text-red-400'
                          : dormancyDays > 60
                          ? 'text-amber-400'
                          : 'text-gray-300'
                      }`}
                    >
                      {dormancyDays}d
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {agent.dormancy_reason ? (
                      <span className="text-xs text-gray-400 bg-surface-card/60 px-2 py-1 rounded">
                        {dormancyReasonLabels[agent.dormancy_reason] || agent.dormancy_reason}
                      </span>
                    ) : (
                      <span className="text-xs text-gray-600">-</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {agent.cohort_segment ? (
                      <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-blue-500/10 border border-blue-500/20 text-blue-400">
                        {(agent.cohort_segment || '').replace(/_/g, ' ')}
                      </span>
                    ) : (
                      <span className="text-xs text-gray-600">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {agent.reactivation_score != null ? (
                      <span className={`text-xs font-semibold ${
                        agent.reactivation_score >= 70 ? 'text-emerald-400' :
                        agent.reactivation_score >= 40 ? 'text-amber-400' :
                        agent.reactivation_score >= 20 ? 'text-orange-400' : 'text-red-400'
                      }`}>
                        {Math.round(agent.reactivation_score)}
                      </span>
                    ) : (
                      <span className="text-xs text-gray-600">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-400">
                    {admMap[agent.assigned_adm_id] || '-'}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1">
                      <div
                        className={`w-2 h-2 rounded-full ${
                          riskScore > 70
                            ? 'bg-red-400'
                            : riskScore > 40
                            ? 'bg-amber-400'
                            : 'bg-emerald-400'
                        }`}
                      />
                      <span className="text-xs text-gray-500">{riskScore}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <button
                      className="p-1.5 rounded-lg hover:bg-white/5 text-gray-500 hover:text-white transition-all"
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedAgent(agent);
                      }}
                    >
                      <Eye className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-surface-border/40">
            <p className="text-xs text-gray-500">
              Showing {(currentPage - 1) * pageSize + 1} to{' '}
              {Math.min(currentPage * pageSize, filteredAgents.length)} of{' '}
              {filteredAgents.length}
            </p>
            <div className="flex gap-1">
              <button
                onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
                disabled={currentPage === 1}
                className="px-3 py-1 text-xs rounded-md bg-surface-card border border-surface-border text-gray-400 hover:text-white hover:bg-surface-card-hover disabled:opacity-40 disabled:cursor-not-allowed transition-all"
              >
                Prev
              </button>
              {Array.from({ length: totalPages }, (_, i) => i + 1)
                .filter(
                  (p) => p === 1 || p === totalPages || Math.abs(p - currentPage) <= 1
                )
                .map((page, i, arr) => (
                  <span key={page} className="flex items-center">
                    {i > 0 && arr[i - 1] !== page - 1 && (
                      <span className="px-1 text-xs text-gray-600">...</span>
                    )}
                    <button
                      onClick={() => setCurrentPage(page)}
                      className={`px-3 py-1 text-xs rounded-md border transition-all ${
                        currentPage === page
                          ? 'bg-brand-red/20 border-brand-red/40 text-brand-red'
                          : 'bg-surface-card border-surface-border text-gray-400 hover:text-white hover:bg-surface-card-hover'
                      }`}
                    >
                      {page}
                    </button>
                  </span>
                ))}
              <button
                onClick={() => setCurrentPage(Math.min(totalPages, currentPage + 1))}
                disabled={currentPage === totalPages}
                className="px-3 py-1 text-xs rounded-md bg-surface-card border border-surface-border text-gray-400 hover:text-white hover:bg-surface-card-hover disabled:opacity-40 disabled:cursor-not-allowed transition-all"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Agent Detail Panel */}
      {selectedAgent && (
        <AgentDetailPanel
          agent={selectedAgent}
          onClose={() => setSelectedAgent(null)}
        />
      )}

      {/* Bulk Import Modal */}
      <BulkAgentImportModal
        mode="admin"
        isOpen={showBulkImport}
        onClose={() => setShowBulkImport(false)}
        onSuccess={() => refetch()}
      />
    </div>
  );
}
