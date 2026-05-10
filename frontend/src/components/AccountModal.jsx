import React, { useEffect, useRef, useState } from 'react';
import {
  X, RefreshCw, Trash2,
  Users, UserPlus, Loader2, FileText,
} from 'lucide-react';
import useAppStore from '../stores/appStore';
import useDataStore from '../stores/dataStore';
import * as api from '../api';
import { showToast } from './Toast';

const cardStyle = {
  border: '1px solid #e2e8f0',
  borderRadius: 10,
  background: '#ffffff',
  boxShadow: '0 1px 2px rgba(15,23,42,0.04)',
};

const inputStyle = {
  width: '100%',
  background: '#ffffff',
  border: '1px solid #d1d5db',
  borderRadius: 8,
  fontSize: 12,
  lineHeight: 1.4,
  color: '#0f172a',
  padding: '8px 10px',
  outline: 'none',
};

const fieldLabelStyle = {
  fontFamily: 'JetBrains Mono, monospace',
  fontSize: 10,
  color: '#64748b',
  marginBottom: 4,
  letterSpacing: '0.06em',
  textTransform: 'uppercase',
};

function StatusBadge({ status }) {
  const map = {
    available: { fg: '#059669', bg: '#ecfdf5', bd: '#a7f3d0' },
    exhausted: { fg: '#b45309', bg: '#fffbeb', bd: '#fcd34d' },
    disabled: { fg: '#64748b', bg: '#f8fafc', bd: '#cbd5e1' },
    error: { fg: '#dc2626', bg: '#fef2f2', bd: '#fecaca' },
  };
  const c = map[status] || map.disabled;
  return (
    <span
      style={{
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: 10,
        padding: '2px 7px',
        border: `1px solid ${c.bd}`,
        borderRadius: 999,
        color: c.fg,
        background: c.bg,
      }}
    >
      {status || 'unknown'}
    </span>
  );
}

function IconButton({ icon, title, danger, disabled, onClick }) {
  const [hover, setHover] = useState(false);
  const color = danger
    ? (hover ? '#dc2626' : '#64748b')
    : (hover ? '#0f172a' : '#64748b');
  return (
    <button
      title={title}
      disabled={disabled}
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        width: 28,
        height: 28,
        borderRadius: 8,
        border: '1px solid #e2e8f0',
        background: hover ? '#f8fafc' : '#fff',
        color,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.45 : 1,
      }}
    >
      {icon}
    </button>
  );
}

function AccountRow({ account }) {
  const { removeAccount, refreshAccountCredits, unbindAccountTask } = useDataStore();
  const [busy, setBusy] = useState(false);
  const id = account.id || account.email;

  const handleRefresh = async () => {
    try {
      setBusy(true);
      await refreshAccountCredits(id);
      showToast('Credits refreshed', 'success');
    } catch (e) {
      showToast(`Refresh failed: ${e.message}`, 'error');
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async () => {
    if (!window.confirm(`Remove account "${account.email}"?`)) return;
    try {
      setBusy(true);
      await removeAccount(id);
      showToast('Account removed', 'success');
    } catch (e) {
      showToast(`Delete failed: ${e.message}`, 'error');
    } finally {
      setBusy(false);
    }
  };

  const handleUnbind = async () => {
    if (!account.locked_by_task) return;
    try {
      setBusy(true);
      await unbindAccountTask(id);
      showToast('Task unbound', 'success');
    } catch (e) {
      showToast(`Unbind failed: ${e.message}`, 'error');
    } finally {
      setBusy(false);
    }
  };

  const credits = account.credits ?? account.credits_remaining ?? 0;

  return (
    <div style={cardStyle}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px' }}>
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: account.status === 'available' ? '#059669'
              : account.status === 'exhausted' ? '#d97706'
              : '#94a3b8',
          }}
        />

        <span
          style={{
            fontFamily: 'JetBrains Mono, monospace',
            fontSize: 12,
            color: '#0f172a',
            flex: 1,
            minWidth: 0,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {account.email}
        </span>

        <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: '#64748b' }}>
          {credits} cr
        </span>
        <StatusBadge status={account.status} />

        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <IconButton
            icon={<RefreshCw size={13} className={busy ? 'animate-spin' : ''} />}
            title="Refresh credits"
            onClick={handleRefresh}
            disabled={busy}
          />
          <IconButton
            icon={<Trash2 size={13} />}
            title="Delete account"
            danger
            onClick={handleDelete}
            disabled={busy}
          />
        </div>
      </div>

      {(account.locked_by_task || account.deployment_id) && (
        <div
          style={{
            borderTop: '1px solid #e2e8f0',
            padding: 10,
            background: '#f8fafc',
            borderBottomLeftRadius: 10,
            borderBottomRightRadius: 10,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 8,
            flexWrap: 'wrap',
          }}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {account.locked_by_task && (
              <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 10, color: '#b45309' }}>
                locked task: {account.locked_by_task}
              </div>
            )}
            {account.deployment_id && (
              <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 10, color: '#64748b' }}>
                deployment: {account.deployment_id}
              </div>
            )}
          </div>

          {account.locked_by_task && (
            <button
              type="button"
              onClick={handleUnbind}
              disabled={busy}
              style={{
                border: '1px solid #f59e0b',
                background: '#fffbeb',
                color: '#b45309',
                fontFamily: 'JetBrains Mono, monospace',
                fontSize: 11,
                padding: '6px 12px',
                borderRadius: 8,
                cursor: 'pointer',
                opacity: busy ? 0.6 : 1,
              }}
            >
              解绑 task
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function RegisterBatchCard({
  onDone,
  onLogReset,
  onLogAppend,
  onRunningChange,
}) {
  const [baseEmail, setBaseEmail] = useState('feijidfg55@gmail.com');
  const [count, setCount] = useState(2);
  const [concurrency, setConcurrency] = useState(2);
  const [createRuntime, setCreateRuntime] = useState(true);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  const handleRegister = async () => {
    const safeCount = Math.max(1, Math.min(50, Number(count) || 1));
    const safeThreads = Math.max(1, Math.min(20, Number(concurrency) || 1));
    if (!baseEmail.trim()) {
      showToast('Base email is required', 'error');
      return;
    }

    try {
      setLoading(true);
      setResult(null);
      onRunningChange?.(true);
      onLogReset?.();
      onLogAppend?.({
        ts: new Date().toISOString(),
        level: 'info',
        message: 'Batch register started',
        base_email: baseEmail.trim(),
        count: safeCount,
        concurrency: safeThreads,
      });

      const data = await api.registerGmailBatchStream({
        base_email: baseEmail.trim(),
        count: safeCount,
        concurrency: safeThreads,
        create_runtime: createRuntime,
        redeem_credits: false,
        save_to_pool: true,
      }, {
        onEvent: (eventName, payload) => {
          if (eventName === 'meta') {
            onLogAppend?.({
              ts: new Date().toISOString(),
              level: 'info',
              message: 'Aliases generated',
              total: payload?.total,
            });
          }
        },
        onLog: (payload) => {
          onLogAppend?.(payload);
        },
      });

      setResult(data);
      onDone?.();
      onLogAppend?.({
        ts: new Date().toISOString(),
        level: 'success',
        message: 'Batch register finished',
        total: data?.total || 0,
        success: data?.success_count || 0,
        failed: data?.failure_count || 0,
      });
      if ((data?.failure_count || 0) > 0) {
        showToast(
          `Registered ${data.success_count}/${data.total}, ${data.failure_count} failed`,
          'info',
        );
      } else {
        showToast(`Registered ${data.success_count}/${data.total} accounts`, 'success');
      }
    } catch (e) {
      onLogAppend?.({
        ts: new Date().toISOString(),
        level: 'error',
        message: 'Batch register failed',
        error: e.message,
      });
      showToast(`Register failed: ${e.message}`, 'error');
    } finally {
      setLoading(false);
      onRunningChange?.(false);
    }
  };

  const failedItems = (result?.items || []).filter((x) => !x.ok).slice(0, 3);

  return (
    <div style={{ ...cardStyle, padding: 14 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <UserPlus size={14} color="#2563eb" />
        <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 12, color: '#1d4ed8', fontWeight: 600 }}>
          Register Accounts
        </span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 8, marginBottom: 8 }}>
        <div>
          <div style={fieldLabelStyle}>基础 Gmail（base_email）</div>
          <input
            value={baseEmail}
            onChange={(e) => setBaseEmail(e.target.value)}
            placeholder="Base Gmail (e.g. feijidfg55@gmail.com)"
            style={inputStyle}
          />
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 10 }}>
        <div>
          <div style={fieldLabelStyle}>注册几个（count）</div>
          <input
            type="number"
            min={1}
            max={50}
            value={count}
            onChange={(e) => setCount(e.target.value)}
            placeholder="register count"
            style={inputStyle}
          />
        </div>
        <div>
          <div style={fieldLabelStyle}>注册线程（concurrency）</div>
          <input
            type="number"
            min={1}
            max={20}
            value={concurrency}
            onChange={(e) => setConcurrency(e.target.value)}
            placeholder="threads"
            style={inputStyle}
          />
        </div>
      </div>

      <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10, cursor: 'pointer' }}>
        <input
          type="checkbox"
          checked={createRuntime}
          onChange={(e) => setCreateRuntime(e.target.checked)}
        />
        <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: '#475569' }}>
          注册后创建 session（create_runtime）
        </span>
      </label>

      <button
        type="button"
        onClick={handleRegister}
        disabled={loading}
        style={{
          width: '100%',
          border: '1px solid #93c5fd',
          background: '#eff6ff',
          color: '#1d4ed8',
          fontFamily: 'JetBrains Mono, monospace',
          fontSize: 12,
          padding: '8px 12px',
          borderRadius: 8,
          cursor: 'pointer',
          opacity: loading ? 0.7 : 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 8,
        }}
      >
        {loading && <Loader2 size={14} className="animate-spin" />}
        {loading ? 'Registering…' : 'Register Batch'}
      </button>

      {result && (
        <div style={{ marginTop: 10, padding: 10, borderRadius: 8, background: '#f8fafc', border: '1px solid #e2e8f0' }}>
          <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: '#334155' }}>
            total: {result.total || 0} | success: {result.success_count || 0} | failed: {result.failure_count || 0}
          </div>
          {failedItems.length > 0 && (
            <div style={{ marginTop: 6, fontFamily: 'JetBrains Mono, monospace', fontSize: 10, color: '#b45309' }}>
              failed: {failedItems.map((x) => x.email).join(', ')}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function RegisterProcessLogCard({ logs, running, onClear }) {
  const boxRef = useRef(null);

  useEffect(() => {
    if (!boxRef.current) return;
    boxRef.current.scrollTop = boxRef.current.scrollHeight;
  }, [logs]);

  const pickColor = (level) => {
    const s = String(level || '').toLowerCase();
    if (s === 'error') return '#dc2626';
    if (s === 'warning') return '#b45309';
    if (s === 'success') return '#059669';
    return '#475569';
  };

  return (
    <div style={{ ...cardStyle, padding: 14 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <FileText size={14} color="#0f766e" />
        <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 12, color: '#0f766e', fontWeight: 600 }}>
          Register Process Logs
        </span>
        <span style={{ marginLeft: 'auto', fontFamily: 'JetBrains Mono, monospace', fontSize: 10, color: running ? '#0ea5e9' : '#64748b' }}>
          {running ? 'running' : 'idle'}
        </span>
      </div>

      <div
        ref={boxRef}
        style={{
          border: '1px solid #e2e8f0',
          borderRadius: 8,
          background: '#f8fafc',
          minHeight: 220,
          maxHeight: 280,
          overflowY: 'auto',
          padding: 8,
          display: 'flex',
          flexDirection: 'column',
          gap: 6,
        }}
      >
        {logs.length === 0 ? (
          <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: '#94a3b8' }}>
            No register logs yet.
          </div>
        ) : logs.map((line, idx) => (
          <div key={`${line.ts || 't'}-${idx}`} style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: pickColor(line.level) }}>
            [{line.ts ? new Date(line.ts).toLocaleTimeString() : '--:--:--'}] {line.message || '-'}
            {line.email ? ` | ${line.email}` : ''}
            {line.error ? ` | err=${line.error}` : ''}
          </div>
        ))}
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8 }}>
        <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 10, color: '#64748b' }}>
          lines: {logs.length}
        </span>
        <button
          type="button"
          onClick={onClear}
          disabled={running || logs.length === 0}
          style={{
            border: '1px solid #cbd5e1',
            background: '#fff',
            color: '#475569',
            fontFamily: 'JetBrains Mono, monospace',
            fontSize: 10,
            padding: '4px 8px',
            borderRadius: 8,
            cursor: 'pointer',
            opacity: (running || logs.length === 0) ? 0.5 : 1,
          }}
        >
          clear
        </button>
      </div>
    </div>
  );
}

export default function AccountModal() {
  const { setModal } = useAppStore();
  const { accounts, fetchAccounts } = useDataStore();
  const [registerLogs, setRegisterLogs] = useState([]);
  const [registerRunning, setRegisterRunning] = useState(false);

  useEffect(() => {
    fetchAccounts();
  }, [fetchAccounts]);

  const appendRegisterLog = (payload) => {
    const line = (payload && typeof payload === 'object')
      ? payload
      : { ts: new Date().toISOString(), level: 'info', message: String(payload || '') };
    setRegisterLogs((prev) => [...prev.slice(-499), line]);
  };

  const available = accounts.filter((a) => a.status === 'available').length;

  return (
    <div
      onClick={(e) => { if (e.target === e.currentTarget) setModal(null); }}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 50,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'rgba(15,23,42,0.35)',
        backdropFilter: 'blur(2px)',
      }}
    >
      <div
        style={{
          width: 'min(980px, 94vw)',
          maxHeight: '88vh',
          display: 'flex',
          flexDirection: 'column',
          borderRadius: 12,
          border: '1px solid #dbeafe',
          background: '#f8fafc',
          boxShadow: '0 20px 70px rgba(15,23,42,0.22)',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '12px 16px',
            borderBottom: '1px solid #dbeafe',
            background: '#ffffff',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Users size={15} color="#2563eb" />
            <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 14, color: '#0f172a', fontWeight: 600 }}>
              Account Management
            </span>
            <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: '#64748b' }}>
              {available}/{accounts.length} available
            </span>
          </div>
          <button
            onClick={() => setModal(null)}
            style={{
              border: '1px solid #e2e8f0',
              background: '#fff',
              color: '#475569',
              width: 30,
              height: 30,
              borderRadius: 8,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
            }}
          >
            <X size={15} />
          </button>
        </div>

        <div
          className="account-grid-responsive"
          style={{
            flex: 1,
            overflowY: 'auto',
            padding: 14,
            display: 'grid',
            gridTemplateColumns: 'minmax(320px, 420px) 1fr',
            gap: 12,
            alignItems: 'start',
          }}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <RegisterBatchCard
              onDone={fetchAccounts}
              onLogReset={() => setRegisterLogs([])}
              onLogAppend={appendRegisterLog}
              onRunningChange={setRegisterRunning}
            />
            <RegisterProcessLogCard
              logs={registerLogs}
              running={registerRunning}
              onClear={() => setRegisterLogs([])}
            />
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 2px' }}>
              <span
                style={{
                  fontFamily: 'JetBrains Mono, monospace',
                  fontSize: 10,
                  color: '#64748b',
                  textTransform: 'uppercase',
                  letterSpacing: '0.08em',
                }}
              >
                accounts ({accounts.length})
              </span>
              <div style={{ flex: 1, height: 1, background: '#dbeafe' }} />
            </div>

            {accounts.length === 0 ? (
              <div style={{ ...cardStyle, padding: 20, textAlign: 'center', color: '#94a3b8', fontFamily: 'JetBrains Mono, monospace', fontSize: 11 }}>
                No accounts configured
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {accounts.map((acc, i) => (
                  <AccountRow key={acc.id || acc.email || i} account={acc} />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <style>{`
        @media (max-width: 980px) {
          .account-grid-responsive {
            grid-template-columns: 1fr !important;
          }
        }
      `}</style>
    </div>
  );
}
