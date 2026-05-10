import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Play, Square, Trash2, RefreshCw, FileText,
  ChevronRight, ChevronDown, Folder, File,
  AlertCircle, CheckCircle, Clock, Minus,
  BarChart2, MessageSquare, Copy, Check,
  Activity, Zap,
} from 'lucide-react';
import useAppStore from '../stores/appStore';
import useDataStore from '../stores/dataStore';
import * as api from '../api';
import { showToast } from './Toast';

// ─── Status helpers ───────────────────────────────────────────────────────────
const STATUS_CONFIG = {
  running:            { text: '#00a888', border: 'rgba(0,168,136,0.3)',  bg: 'rgba(0,168,136,0.08)',  label: 'running' },
  monitoring:         { text: '#00a888', border: 'rgba(0,168,136,0.3)',  bg: 'rgba(0,168,136,0.08)',  label: 'monitoring' },
  bootstrapping_runtime: { text: '#00a888', border: 'rgba(0,168,136,0.3)', bg: 'rgba(0,168,136,0.08)', label: 'runtime bootstrapping' },
  creating_session:   { text: '#00a888', border: 'rgba(0,168,136,0.3)',  bg: 'rgba(0,168,136,0.08)',  label: 'creating session' },
  sending_message:    { text: '#00a888', border: 'rgba(0,168,136,0.3)',  bg: 'rgba(0,168,136,0.08)',  label: 'sending message' },
  pending:            { text: '#f59e0b', border: 'rgba(245,158,11,0.3)', bg: 'rgba(245,158,11,0.08)', label: 'pending' },
  switching:          { text: '#f59e0b', border: 'rgba(245,158,11,0.3)', bg: 'rgba(245,158,11,0.08)', label: 'switching' },
  syncing:            { text: '#4a9eff', border: 'rgba(74,158,255,0.3)', bg: 'rgba(74,158,255,0.08)', label: 'syncing' },
  pushing:            { text: '#4a9eff', border: 'rgba(74,158,255,0.3)', bg: 'rgba(74,158,255,0.08)', label: 'pushing' },
  acquiring_account:  { text: '#f59e0b', border: 'rgba(245,158,11,0.3)', bg: 'rgba(245,158,11,0.08)', label: 'acquiring account' },
  auto_registering_account: { text: '#f59e0b', border: 'rgba(245,158,11,0.3)', bg: 'rgba(245,158,11,0.08)', label: 'auto registering account' },
  blocked:            { text: '#ff6b4a', border: 'rgba(255,107,74,0.3)', bg: 'rgba(255,107,74,0.08)', label: 'blocked' },
  blocked_no_account: { text: '#ff6b4a', border: 'rgba(255,107,74,0.3)', bg: 'rgba(255,107,74,0.08)', label: 'no accounts' },
  failed:             { text: '#ff6b4a', border: 'rgba(255,107,74,0.3)', bg: 'rgba(255,107,74,0.08)', label: 'failed' },
  completed:          { text: '#6b7280', border: 'rgba(107,114,128,0.3)',bg: 'rgba(107,114,128,0.08)',label: 'completed' },
  stopped:            { text: '#6b7280', border: 'rgba(107,114,128,0.3)',bg: 'rgba(107,114,128,0.08)',label: 'stopped' },
  canceled:           { text: '#64748b', border: 'rgba(68,68,96,0.3)',   bg: 'rgba(68,68,96,0.08)',   label: 'canceled' },
};

function getStatusCfg(status) {
  return STATUS_CONFIG[status] || { text: '#4b5563', border: '#cbd5e1', bg: 'transparent', label: status || 'idle' };
}

function StatusBadge({ status }) {
  const c = getStatusCfg(status);
  return (
    <span style={{
      fontFamily: 'JetBrains Mono, monospace',
      fontSize: 11,
      padding: '2px 8px',
      border: `1px solid ${c.border}`,
      background: c.bg,
      color: c.text,
    }}>
      {c.label}
    </span>
  );
}

// ─── Action button ────────────────────────────────────────────────────────────
function ActionBtn({ icon, label, variant = 'default', disabled, onClick }) {
  const [hover, setHover] = useState(false);
  const colors = {
    accent:  { base: '#00a888', borderBase: 'rgba(0,168,136,0.3)',  bgHover: 'rgba(0,168,136,0.12)'  },
    warn:    { base: '#ff6b4a', borderBase: 'rgba(255,107,74,0.3)', bgHover: 'rgba(255,107,74,0.12)' },
    default: { base: '#4b5563', borderBase: '#cbd5e1',              bgHover: '#f1f5f9'               },
  };
  const c = colors[variant] || colors.default;
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        padding: '6px 12px',
        border: `1px solid ${c.borderBase}`,
        background: hover ? c.bgHover : 'transparent',
        color: hover ? c.base : (variant !== 'default' ? c.base : '#888899'),
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: 11,
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.4 : 1,
        transition: 'all 0.15s',
      }}
    >
      {icon}
      {label}
    </button>
  );
}

// ─── Section label ────────────────────────────────────────────────────────────
function SectionLabel({ children }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <span style={{
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: 10,
        color: '#64748b',
        textTransform: 'uppercase',
        letterSpacing: '0.1em',
      }}>
        {children}
      </span>
      <div style={{ flex: 1, height: 1, background: '#e2e8f0' }} />
    </div>
  );
}

// ─── File tree node ───────────────────────────────────────────────────────────
function FileNode({ node, accountId, depth = 0 }) {
  const [open,    setOpen]    = useState(false);
  const [content, setContent] = useState(null);
  const [loading, setLoading] = useState(false);
  const [copied,  setCopied]  = useState(false);

  const isDir   = node.type === 'directory' || node.is_dir === true || Array.isArray(node.children);
  const indent  = depth * 16 + 8;
  const hasChildren = isDir && ((node.children && node.children.length > 0) || !node.children);

  const handleClick = async () => {
    if (isDir) {
      setOpen((v) => !v);
      return;
    }
    if (content !== null) { setContent(null); return; }
    if (!accountId) { showToast('No account available to read file', 'error'); return; }
    try {
      setLoading(true);
      const res = await api.getFileContent(accountId, node.path || node.name);
      setContent(res.data ?? res.content ?? res ?? '');
    } catch (e) {
      showToast(`Failed to load file: ${e.message}`, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = (e) => {
    e.stopPropagation();
    if (content) {
      navigator.clipboard.writeText(typeof content === 'string' ? content : JSON.stringify(content, null, 2));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }
  };

  return (
    <div>
      <button
        onClick={handleClick}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          gap: 5,
          paddingTop: 3,
          paddingBottom: 3,
          paddingLeft: indent,
          paddingRight: 8,
          textAlign: 'left',
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          fontFamily: 'JetBrains Mono, monospace',
          fontSize: 11,
          color: isDir ? '#475569' : '#4b5563',
          transition: 'background 0.1s',
        }}
        onMouseEnter={(e) => (e.currentTarget.style.background = '#f1f5f9')}
        onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
      >
        {isDir
          ? (open ? <ChevronDown size={10} style={{ color: '#6b7280' }} /> : <ChevronRight size={10} style={{ color: '#6b7280' }} />)
          : <span style={{ width: 10, flexShrink: 0 }} />}
        {isDir
          ? <Folder size={11} style={{ color: 'rgba(0,168,136,0.5)', flexShrink: 0 }} />
          : <File   size={11} style={{ color: '#6b7280', flexShrink: 0 }} />}
        <span style={{
          flex: 1,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          color: isDir ? '#475569' : (content !== null ? '#1e293b' : '#4b5563'),
        }}>
          {node.name}
        </span>
        {loading && <RefreshCw size={9} style={{ color: '#00a888', animation: 'spin 1s linear infinite', flexShrink: 0 }} />}
      </button>

      {/* Inline file content */}
      {content !== null && !isDir && (
        <div style={{
          margin: '2px 8px 4px 8px',
          border: '1px solid #e2e8f0',
          background: '#f8fafc',
          overflow: 'auto',
          maxHeight: 320,
          position: 'relative',
        }}>
          <button
            onClick={handleCopy}
            title="Copy"
            style={{
              position: 'absolute',
              top: 4,
              right: 4,
              background: '#f1f5f9',
              border: '1px solid #e2e8f0',
              color: copied ? '#00a888' : '#6b7280',
              padding: '2px 6px',
              cursor: 'pointer',
              fontFamily: 'JetBrains Mono, monospace',
              fontSize: 10,
              display: 'flex',
              alignItems: 'center',
              gap: 3,
            }}
          >
            {copied ? <Check size={9} /> : <Copy size={9} />}
            {copied ? 'copied' : 'copy'}
          </button>
          <pre style={{
            padding: '10px 12px',
            fontFamily: 'JetBrains Mono, monospace',
            fontSize: 10,
            color: '#334155',
            whiteSpace: 'pre-wrap',
            lineHeight: 1.6,
            margin: 0,
          }}>
            {typeof content === 'string' ? content : JSON.stringify(content, null, 2)}
          </pre>
        </div>
      )}

      {/* Directory children */}
      {isDir && open && (
        <>
          {(node.children || []).map((child, i) => (
            <FileNode key={i} node={child} accountId={accountId} depth={depth + 1} />
          ))}
        </>
      )}
    </div>
  );
}

// ─── Files tab ────────────────────────────────────────────────────────────────
function FilesTab({ project, taskId, task }) {
  const [tree,    setTree]    = useState(null);
  const [loading, setLoading] = useState(false);

  // Resolve account ID from task data
  const accountId = task?.current_account_id
    || task?.accounts?.[0]?.id
    || (typeof task?.accounts?.[0] === 'string' ? task.accounts[0] : null)
    || task?.assigned_accounts?.[0]?.id
    || (typeof task?.assigned_accounts?.[0] === 'string' ? task.assigned_accounts[0] : null)
    || null;

  const loadTree = useCallback(async () => {
    try {
      setLoading(true);
      const res = await api.getTaskFileTree(project, taskId);
      const nodes = res.data ?? res.tree ?? res ?? [];
      setTree(Array.isArray(nodes) ? nodes : []);
    } catch (e) {
      showToast(`Failed to load file tree: ${e.message}`, 'error');
      setTree([]);
    } finally {
      setLoading(false);
    }
  }, [project, taskId]);

  useEffect(() => { loadTree(); }, [loadTree]);

  if (loading && !tree) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '32px 16px', fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: 'rgba(0,168,136,0.6)' }}>
        <RefreshCw size={12} style={{ animation: 'spin 1s linear infinite' }} />
        loading workspace…
      </div>
    );
  }

  if (!tree || tree.length === 0) {
    return (
      <div style={{ padding: '32px 16px', textAlign: 'center', fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: '#94a3b8', fontStyle: 'italic' }}>
        {!accountId ? 'No account assigned to this task yet.' : 'No files found in workspace.'}
      </div>
    );
  }

  return (
    <div style={{ padding: '8px 0' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '0 16px 8px' }}>
        <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 10, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
          workspace
        </span>
        {accountId && (
          <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 10, color: '#94a3b8' }}>
            {accountId}
          </span>
        )}
        <button
          onClick={loadTree}
          disabled={loading}
          style={{ marginLeft: 'auto', background: 'none', border: 'none', color: '#64748b', cursor: 'pointer', display: 'flex', alignItems: 'center', padding: 2 }}
          onMouseEnter={(e) => (e.currentTarget.style.color = '#00a888')}
          onMouseLeave={(e) => (e.currentTarget.style.color = '#64748b')}
        >
          <RefreshCw size={11} style={loading ? { animation: 'spin 1s linear infinite' } : {}} />
        </button>
      </div>
      {tree.map((node, i) => (
        <FileNode key={i} node={node} accountId={accountId} />
      ))}
    </div>
  );
}

// ─── Overview tab ─────────────────────────────────────────────────────────────
function OverviewTab({ task, project, taskId, onRefresh }) {
  const { startTask, cancelTask, deleteTask } = useDataStore();
  const { setSelectedNode }                   = useAppStore();
  const [busy, setBusy] = useState(false);

  const status  = task.status || 'idle';
  const mode    = task.mode || '—';
  const loops   = task.current_loop ?? task.loop_count ?? 0;
  const maxL    = task.max_loops ?? '∞';
  const message = task.message || task.prompt || '';
  const loopHistory = task.loops || task.loop_results || task.completed_loops || [];
  const isActive = [
    'running', 'monitoring', 'pending', 'switching', 'syncing', 'pushing',
    'acquiring_account', 'auto_registering_account',
    'bootstrapping_runtime', 'creating_session', 'sending_message',
  ].includes(status);

  const act = async (fn, label) => {
    try {
      setBusy(true);
      await fn();
      onRefresh();
      showToast(`${label} OK`, 'success');
    } catch (e) {
      showToast(`${label} failed: ${e.message}`, 'error');
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async () => {
    if (!window.confirm(`Delete task "${taskId}"?`)) return;
    try {
      setBusy(true);
      await deleteTask(project, taskId);
      setSelectedNode({ type: 'project', project });
      showToast('Task deleted', 'success');
    } catch (e) {
      showToast(`Delete failed: ${e.message}`, 'error');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20, padding: '16px 24px' }}>

      {/* Status row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <StatusBadge status={status} />

        <MetaChip label="mode" value={mode} />
        <MetaChip label="loops" value={`${loops}/${maxL}`} />
        {task.created_at && (
          <MetaChip label="created" value={new Date(task.created_at).toLocaleString()} dim />
        )}
        {isActive && task.current_account_id && (
          <MetaChip label="account" value={task.current_account_id} accent />
        )}
      </div>

      {/* Actions */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        {(status === 'pending' || status === 'idle') && (
          <ActionBtn
            icon={<Play size={12} />}
            label="Start"
            variant="accent"
            disabled={busy}
            onClick={() => act(() => startTask(project, taskId), 'Start')}
          />
        )}
        {isActive && (
          <ActionBtn
            icon={<Square size={12} />}
            label="Cancel"
            variant="warn"
            disabled={busy}
            onClick={() => act(() => cancelTask(project, taskId), 'Cancel')}
          />
        )}
        <ActionBtn
          icon={<Trash2 size={12} />}
          label="Delete"
          variant="warn"
          disabled={busy}
          onClick={handleDelete}
        />
        <ActionBtn
          icon={<RefreshCw size={12} style={busy ? { animation: 'spin 1s linear infinite' } : {}} />}
          label="Refresh"
          disabled={busy}
          onClick={onRefresh}
        />
      </div>

      {/* Prompt */}
      {message && (
        <div>
          <SectionLabel>prompt / message</SectionLabel>
          <div style={{
            marginTop: 6,
            background: '#f8fafc',
            border: '1px solid #e2e8f0',
            padding: '10px 14px',
          }}>
            <pre style={{
              fontFamily: 'JetBrains Mono, monospace',
              fontSize: 11,
              color: '#334155',
              whiteSpace: 'pre-wrap',
              lineHeight: 1.6,
              margin: 0,
            }}>
              {message}
            </pre>
          </div>
        </div>
      )}

      {/* Assigned accounts */}
      {(() => {
        const accs = task.accounts || task.assigned_accounts || [];
        if (!accs.length) return null;
        return (
          <div>
            <SectionLabel>assigned accounts</SectionLabel>
            <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 4 }}>
              {accs.map((acc, i) => {
                const email  = acc.email || (typeof acc === 'string' ? acc : acc.id || '—');
                const st     = acc.status || '';
                const cr     = acc.credits ?? acc.credits_remaining;
                const dotClr = st === 'available' ? '#00a888' : st === 'exhausted' ? '#f59e0b' : '#64748b';
                const isCur  = task.current_account_id === (acc.id || acc);
                return (
                  <div key={i} style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    padding: '6px 12px',
                    background: isCur ? 'rgba(0,168,136,0.05)' : '#f1f5f9',
                    border: `1px solid ${isCur ? 'rgba(0,168,136,0.2)' : '#e2e8f0'}`,
                    fontFamily: 'JetBrains Mono, monospace',
                    fontSize: 11,
                  }}>
                    <span style={{ width: 8, height: 8, borderRadius: '50%', background: dotClr, flexShrink: 0 }} />
                    <span style={{ color: '#1e293b', flex: 1 }}>{email}</span>
                    {isCur && <span style={{ fontSize: 9, color: '#00a888', background: 'rgba(0,168,136,0.1)', padding: '1px 6px', border: '1px solid rgba(0,168,136,0.3)' }}>current</span>}
                    {st && <span style={{ color: '#6b7280' }}>{st}</span>}
                    {cr !== undefined && <span style={{ color: '#4b5563' }}>{cr} cr</span>}
                  </div>
                );
              })}
            </div>
          </div>
        );
      })()}

      {/* Loop history */}
      {loopHistory.length > 0 && (
        <div>
          <SectionLabel>loop history ({loopHistory.length})</SectionLabel>
          <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 3 }}>
            {loopHistory.map((loop, i) => {
              const reason = loop.end_reason || loop.status || '—';
              const reasonColor = reason === 'completed' ? '#6b7280'
                : reason === 'credit_exhausted' ? '#f59e0b'
                : reason.includes('error') ? '#ff6b4a'
                : '#6b7280';
              return (
                <div key={i} style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                  padding: '6px 12px',
                  background: '#f1f5f9',
                  border: '1px solid #e2e8f0',
                  fontFamily: 'JetBrains Mono, monospace',
                  fontSize: 11,
                }}>
                  <span style={{ color: '#64748b', width: 20, textAlign: 'right', flexShrink: 0 }}>
                    {i + 1}
                  </span>
                  <span style={{ color: '#4b5563', flex: 1 }}>
                    {loop.account || loop.account_email || loop.account_id || '—'}
                  </span>
                  {loop.session_id && (
                    <span style={{ color: '#64748b', fontSize: 10 }}>
                      {loop.session_id.slice(0, 8)}…
                    </span>
                  )}
                  {loop.git_commit && (
                    <span style={{ color: '#64748b', fontSize: 10 }}>
                      git:{loop.git_commit.slice(0, 7)}
                    </span>
                  )}
                  <span style={{ color: reasonColor, marginLeft: 'auto', flexShrink: 0 }}>
                    {reason}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function MetaChip({ label, value, accent, dim }) {
  const valueColor = accent ? '#00a888' : dim ? '#6b7280' : '#334155';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontFamily: 'JetBrains Mono, monospace', fontSize: 11 }}>
      <span style={{ color: '#64748b' }}>{label}:</span>
      <span style={{ color: valueColor }}>{value}</span>
    </div>
  );
}

// ─── Main TaskView ────────────────────────────────────────────────────────────
export default function TaskView() {
  const { selectedNode } = useAppStore();
  const { tasks, fetchTasks } = useDataStore();
  const [activeTab, setActiveTab] = useState('overview');
  const pollRef = useRef(null);

  const { project, taskId } = selectedNode || {};
  const taskList = tasks[project] || [];
  const task = taskList.find((t) => (t.id || t.task_id || t.taskId) === taskId);

  const refresh = useCallback(() => {
    if (project) fetchTasks(project);
  }, [project, fetchTasks]);

  useEffect(() => {
    refresh();
    return () => clearInterval(pollRef.current);
  }, [project, taskId]);

  // Poll while active
  useEffect(() => {
    clearInterval(pollRef.current);
    const activeStatuses = [
      'running', 'monitoring', 'pending', 'switching', 'syncing', 'pushing',
      'acquiring_account', 'auto_registering_account',
      'bootstrapping_runtime', 'creating_session', 'sending_message',
    ];
    if (task && activeStatuses.includes(task.status)) {
      pollRef.current = setInterval(refresh, 6000);
    }
    return () => clearInterval(pollRef.current);
  }, [task?.status, refresh]);

  if (!task) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
        <p style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 12, color: '#94a3b8', fontStyle: 'italic' }}>
          {taskId ? 'Loading task…' : 'No task selected'}
        </p>
      </div>
    );
  }

  const tabs = [
    { id: 'overview', label: 'Overview', icon: <BarChart2 size={12} /> },
  ];

  const isActive = [
    'running', 'monitoring', 'pending', 'switching', 'syncing', 'pushing',
    'acquiring_account', 'auto_registering_account',
    'bootstrapping_runtime', 'creating_session', 'sending_message',
  ].includes(task.status);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', fontFamily: 'Inter, sans-serif' }}>
      {/* Header */}
      <div style={{
        padding: '20px 24px 0',
        borderBottom: '1px solid #e2e8f0',
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
          {isActive && (
            <span style={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              background: '#00a888',
              boxShadow: '0 0 6px rgba(0,168,136,0.7)',
              animation: 'pulseDot 2s ease-in-out infinite',
              flexShrink: 0,
            }} />
          )}
          <h1 style={{
            fontFamily: 'JetBrains Mono, monospace',
            fontWeight: 700,
            fontSize: 14,
            color: '#0f172a',
            margin: 0,
          }}>
            {taskId}
          </h1>
          <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: '#64748b' }}>
            in {project}
          </span>
        </div>

        {/* Tabs */}
        <div style={{ display: 'flex', gap: 0 }}>
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                padding: '8px 16px',
                fontFamily: 'JetBrains Mono, monospace',
                fontSize: 11,
                background: 'none',
                border: 'none',
                borderBottom: `2px solid ${activeTab === tab.id ? '#00a888' : 'transparent'}`,
                color: activeTab === tab.id ? '#00a888' : '#6b7280',
                cursor: 'pointer',
                transition: 'all 0.15s',
              }}
              onMouseEnter={(e) => { if (activeTab !== tab.id) e.currentTarget.style.color = '#334155'; }}
              onMouseLeave={(e) => { if (activeTab !== tab.id) e.currentTarget.style.color = '#6b7280'; }}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {activeTab === 'overview' && (
          <OverviewTab task={task} project={project} taskId={taskId} onRefresh={refresh} />
        )}
      </div>

      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        @keyframes pulseDot { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
      `}</style>
    </div>
  );
}
