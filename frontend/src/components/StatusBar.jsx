import React, { useEffect, useState } from 'react';
import { Wifi, WifiOff, Activity, Users } from 'lucide-react';
import useDataStore from '../stores/dataStore';

export default function StatusBar() {
  const { overview, accounts, tasks, fetchOverview } = useDataStore();
  const [connected, setConnected] = useState(true);

  // Refresh overview every 10 s
  useEffect(() => {
    fetchOverview();
    const interval = setInterval(() => {
      fetchOverview()
        .then(() => setConnected(true))
        .catch(() => setConnected(false));
    }, 10_000);
    return () => clearInterval(interval);
  }, [fetchOverview]);

  // Derive counts from store (fallback to computed values)
  const totalAccounts     = overview.total_accounts     ?? accounts.length;
  const availableAccounts = overview.available_accounts ?? accounts.filter((a) => a.status === 'available').length;
  const runningTasks      = overview.running_tasks      ?? Object.values(tasks).flat().filter((t) =>
    [
      'running', 'monitoring', 'pending', 'switching', 'syncing', 'pushing',
      'acquiring_account', 'auto_registering_account',
      'bootstrapping_runtime', 'creating_session', 'sending_message', 'submitting_commit',
    ].includes(t.status)
  ).length;
  const totalTasks        = overview.total_tasks        ?? Object.values(tasks).flat().length;

  const sep = (
    <span style={{ color: '#e2e8f0' }}>│</span>
  );

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 16,
        padding: '0 16px',
        height: 28,
        background: '#f1f5f9',
        borderTop: '1px solid #e8f4f1',
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: 11,
        color: '#6b7280',
        flexShrink: 0,
        userSelect: 'none',
      }}
    >
      {/* Accounts */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
        <Users size={9} style={{ color: '#94a3b8' }} />
        <span>
          <span style={{ color: '#64748b' }}>accounts: </span>
          <span style={{ color: '#00a888' }}>{availableAccounts}</span>
          <span style={{ color: '#94a3b8' }}>/</span>
          <span style={{ color: '#888899' }}>{totalAccounts}</span>
          <span style={{ color: '#64748b' }}> avail</span>
        </span>
      </div>

      {sep}

      {/* Tasks */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
        <Activity size={9} style={{ color: '#94a3b8' }} />
        <span>
          <span style={{ color: '#64748b' }}>tasks: </span>
          <span style={{ color: runningTasks > 0 ? '#00a888' : '#888899' }}>
            {runningTasks}
          </span>
          <span style={{ color: '#64748b' }}> running</span>
          {totalTasks > 0 && (
            <span style={{ color: '#94a3b8' }}> / {totalTasks} total</span>
          )}
        </span>
      </div>

      {sep}

      {/* Connection */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
        {connected ? (
          <>
            <span
              style={{
                display: 'inline-block',
                width: 5,
                height: 5,
                borderRadius: '50%',
                background: '#00a888',
                boxShadow: '0 0 4px rgba(0,168,136,0.6)',
              }}
            />
            <Wifi size={9} style={{ color: '#00a888' }} />
            <span style={{ color: '#00a888' }}>connected</span>
          </>
        ) : (
          <>
            <span
              style={{
                display: 'inline-block',
                width: 5,
                height: 5,
                borderRadius: '50%',
                background: '#ff6b4a',
              }}
            />
            <WifiOff size={9} style={{ color: '#ff6b4a' }} />
            <span style={{ color: '#ff6b4a' }}>disconnected</span>
          </>
        )}
      </div>

      {/* Spacer + version */}
      <div style={{ marginLeft: 'auto', color: '#e2e8f0' }}>
        nodeops-manager v0.1
      </div>
    </div>
  );
}
