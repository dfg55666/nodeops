import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  RefreshCw, MessageSquare, User, Bot,
  ChevronDown, ChevronUp, Copy, Check, Send, ImagePlus, X,
  ChevronRight, Folder, File, AlertCircle, Download, Repeat,
} from 'lucide-react';
import useAppStore from '../stores/appStore';
import useDataStore from '../stores/dataStore';
import * as api from '../api';
import { showToast } from './Toast';
import { MODEL_OPTIONS, DEFAULT_MODEL_ID, buildModelRef } from '../constants/models';

function extractHeaderValue(raw, key) {
  if (!raw || typeof raw !== 'string') return '';
  const prefix = `- ${key}:`;
  const line = raw.split('\n').find((l) => l.startsWith(prefix));
  if (!line) return '';
  return line.slice(prefix.length).trim();
}

function normalizeRole(role) {
  const v = String(role || '').trim().toLowerCase();
  if (v === 'user' || v === 'assistant' || v === 'system') return v;
  if (v === 'unknown') return 'assistant';
  return '';
}

function normalizeMessageRows(rows) {
  if (!Array.isArray(rows)) return [];
  const out = [];
  for (const row of rows) {
    if (!row || typeof row !== 'object') continue;
    const role = normalizeRole(row.role || row.sender || row.type || '');
    const text = String(row.content || row.text || row.message || '').trim();
    if (!role || !text) continue;
    if (role !== 'user' && role !== 'assistant') continue;
    const cur = { role, text };
    const prev = out[out.length - 1];
    if (prev && prev.role === cur.role && prev.text === cur.text) continue;
    if (prev && prev.role === 'user' && cur.role === 'assistant' && prev.text === cur.text) continue;
    out.push(cur);
  }
  return out;
}

// ─── Simple Markdown renderer (bold, inline code, code blocks) ────────────────
function renderMarkdown(text) {
  if (!text) return null;

  // Split on fenced code blocks
  const parts = text.split(/(```[\s\S]*?```)/g);

  return parts.map((part, idx) => {
    if (part.startsWith('```')) {
      const firstNewline = part.indexOf('\n');
      const lang = firstNewline > 3 ? part.slice(3, firstNewline).trim() : '';
      const code = firstNewline >= 0 ? part.slice(firstNewline + 1, -3) : part.slice(3, -3);
      return (
        <pre key={idx} style={{
          background: '#1e293b',
          color: '#e2e8f0',
          padding: '10px 12px',
          margin: '6px 0',
          borderRadius: 4,
          fontSize: 11,
          fontFamily: 'JetBrains Mono, monospace',
          overflowX: 'auto',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
        }}>
          {lang && <span style={{ color: '#64748b', display: 'block', marginBottom: 4, fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.1em' }}>{lang}</span>}
          {code}
        </pre>
      );
    }

    // Inline formatting: split on lines first
    return part.split('\n').map((line, li) => {
      const inlineParts = line.split(/(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)/g);
      const rendered = inlineParts.map((chunk, ci) => {
        if (chunk.startsWith('**') && chunk.endsWith('**')) {
          return <strong key={ci}>{chunk.slice(2, -2)}</strong>;
        }
        if (chunk.startsWith('*') && chunk.endsWith('*') && chunk.length > 2) {
          return <em key={ci}>{chunk.slice(1, -1)}</em>;
        }
        if (chunk.startsWith('`') && chunk.endsWith('`') && chunk.length > 1) {
          return (
            <code key={ci} style={{
              background: 'rgba(0,0,0,0.08)',
              padding: '1px 4px',
              borderRadius: 3,
              fontFamily: 'JetBrains Mono, monospace',
              fontSize: '0.92em',
            }}>{chunk.slice(1, -1)}</code>
          );
        }
        return chunk;
      });
      return (
        <React.Fragment key={li}>
          {rendered}
          {li < part.split('\n').length - 1 && <br />}
        </React.Fragment>
      );
    });
  });
}

function MessageBubble({ segment }) {
  const { role, text } = segment;
  const [copied, setCopied] = useState(false);
  const [expanded, setExpanded] = useState(true);

  if (role === 'divider') {
    return <div style={{ height: 1, background: '#e2e8f0', margin: '12px 16px' }} />;
  }

  if (role === 'meta') {
    return (
      <div style={{ padding: '4px 16px' }}>
        <span style={{
          fontFamily: 'JetBrains Mono, monospace',
          fontSize: 10,
          color: '#64748b',
          textTransform: 'uppercase',
          letterSpacing: '0.1em',
        }}>
          {text}
        </span>
      </div>
    );
  }

  if (role === 'system') {
    if (!text || !text.trim()) return null;
    return (
      <div style={{ padding: '2px 16px' }}>
        <p style={{
          fontFamily: 'JetBrains Mono, monospace',
          fontSize: 10,
          color: '#64748b',
          fontStyle: 'italic',
          margin: 0,
          lineHeight: 1.5,
        }}>
          {text}
        </p>
      </div>
    );
  }

  const isUser = role === 'user';
  const isLong = text.length > 800;

  const handleCopy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div style={{
      display: 'flex',
      justifyContent: isUser ? 'flex-end' : 'flex-start',
      padding: '4px 16px',
    }}>
      <div style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: 8,
        maxWidth: isUser ? '75%' : '82%',
        flexDirection: isUser ? 'row-reverse' : 'row',
      }}>
        {/* Avatar */}
        <div style={{
          flexShrink: 0,
          width: 26,
          height: 26,
          background: isUser ? '#00a888' : '#e2e8f0',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          borderRadius: '50%',
          marginTop: 2,
        }}>
          {isUser
            ? <User size={12} style={{ color: '#ffffff' }} />
            : <Bot size={12} style={{ color: '#4a9eff' }} />}
        </div>

        {/* Bubble */}
        <div style={{
          background: isUser ? '#00a888' : '#f1f5f9',
          border: `1px solid ${isUser ? '#00a888' : '#e2e8f0'}`,
          borderRadius: isUser ? '16px 4px 16px 16px' : '4px 16px 16px 16px',
          padding: '8px 12px',
          position: 'relative',
          minWidth: 60,
          maxWidth: '100%',
        }}>
          {/* Copy + collapse buttons */}
          <div style={{
            position: 'absolute',
            top: 4,
            right: 6,
            display: 'flex',
            gap: 2,
          }}>
            {isLong && (
              <button
                onClick={() => setExpanded((v) => !v)}
                title={expanded ? 'Collapse' : 'Expand'}
                style={{
                  background: 'none',
                  border: 'none',
                  color: isUser ? 'rgba(255,255,255,0.6)' : '#6b7280',
                  cursor: 'pointer',
                  padding: '1px 3px',
                  display: 'flex',
                  alignItems: 'center',
                }}
              >
                {expanded ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
              </button>
            )}
            <button
              onClick={handleCopy}
              title="Copy"
              style={{
                background: 'none',
                border: 'none',
                color: copied
                  ? (isUser ? '#fff' : '#00a888')
                  : (isUser ? 'rgba(255,255,255,0.6)' : '#6b7280'),
                cursor: 'pointer',
                padding: '1px 3px',
                display: 'flex',
                alignItems: 'center',
              }}
            >
              {copied ? <Check size={10} /> : <Copy size={10} />}
            </button>
          </div>

          {/* Message body */}
          <div style={{
            fontFamily: isUser ? 'Inter, sans-serif' : 'JetBrains Mono, monospace',
            fontSize: 13,
            color: isUser ? '#ffffff' : '#334155',
            lineHeight: 1.65,
            paddingRight: 28,
            maxHeight: (!isLong || expanded) ? 'none' : 120,
            overflow: (!isLong || expanded) ? 'visible' : 'hidden',
            wordBreak: 'break-word',
            whiteSpace: isUser ? 'pre-wrap' : 'normal',
          }}>
            {isUser ? text : renderMarkdown(text)}
          </div>
        </div>
      </div>
    </div>
  );
}

function FileNode({ node, projectName, taskId, accountId, depth = 0 }) {
  const [open, setOpen] = useState(false);
  const [children, setChildren] = useState(Array.isArray(node.children) ? node.children : null);
  const [content, setContent] = useState(null);
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [copied, setCopied] = useState(false);

  const isDir = node.type === 'directory' || node.is_dir === true || Array.isArray(node.children);
  const nodePath = node.path || node.name || '';
  const indent = depth * 16 + 8;

  const handleClick = async () => {
    if (isDir) {
      const willOpen = !open;
      setOpen(willOpen);
      if (willOpen && children === null) {
        try {
          setLoading(true);
          let res;
          if (projectName && taskId) {
            res = await api.getTaskFileTreeWithAccount(projectName, taskId, accountId || '', nodePath);
          } else if (accountId) {
            res = await api.getFileTree(accountId, nodePath);
          } else {
            setChildren([]);
            return;
          }
          const nodes = res?.data ?? res ?? [];
          setChildren(Array.isArray(nodes) ? nodes : []);
        } catch (e) {
          showToast(`Failed to load directory: ${e.message}`, 'error');
          setChildren([]);
        } finally {
          setLoading(false);
        }
      }
      return;
    }
    if (content !== null) {
      setContent(null);
      return;
    }
    try {
      setLoading(true);
      const res = (projectName && taskId)
        ? await api.getTaskFileContent(projectName, taskId, nodePath, accountId || '')
        : await api.getFileContent(accountId, nodePath);
      if (res?.is_binary) {
        setContent('[binary file]');
      } else {
        setContent(res?.data ?? res ?? '');
      }
    } catch (e) {
      showToast(`Failed to load file: ${e.message}`, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = async (e) => {
    e.stopPropagation();
    if (!projectName && !taskId && !accountId) {
      showToast('No account for workspace', 'error');
      return;
    }
    if (!nodePath) {
      showToast('Invalid file path', 'error');
      return;
    }
    try {
      setDownloading(true);
      const res = (projectName && taskId)
        ? await api.downloadTaskWorkspacePath(projectName, taskId, nodePath, isDir, accountId || '')
        : await api.downloadWorkspacePath(accountId, nodePath, isDir);
      const savedTo = res?.data?.saved_to || '';
      const savedCount = Number(res?.data?.saved_count || 0);
      if (isDir) {
        showToast(`Saved ${savedCount} files to ${savedTo}`, 'success');
      } else {
        showToast(`Saved to ${savedTo}`, 'success');
      }
    } catch (err) {
      showToast(`Save failed: ${err.message}`, 'error');
    } finally {
      setDownloading(false);
    }
  };

  const copyContent = (e) => {
    e.stopPropagation();
    if (content == null) return;
    navigator.clipboard.writeText(typeof content === 'string' ? content : JSON.stringify(content, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
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
        }}
        onMouseEnter={(e) => (e.currentTarget.style.background = '#f1f5f9')}
        onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
      >
        {isDir
          ? (open ? <ChevronDown size={10} style={{ color: '#6b7280' }} /> : <ChevronRight size={10} style={{ color: '#6b7280' }} />)
          : <span style={{ width: 10, flexShrink: 0 }} />}
        {isDir
          ? <Folder size={11} style={{ color: 'rgba(0,168,136,0.5)', flexShrink: 0 }} />
          : <File size={11} style={{ color: '#6b7280', flexShrink: 0 }} />}
        <span style={{
          flex: 1,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          color: isDir ? '#475569' : '#4b5563',
        }}>
          {node.name}
        </span>
        <span
          onClick={handleDownload}
          title={isDir ? 'Save folder to local download/' : 'Save file to local download/'}
          style={{
            background: 'none',
            border: 'none',
            color: downloading ? '#00a888' : '#64748b',
            cursor: downloading ? 'wait' : 'pointer',
            display: 'flex',
            alignItems: 'center',
            padding: 2,
            flexShrink: 0,
            pointerEvents: downloading ? 'none' : 'auto',
          }}
        >
          <Download size={10} />
        </span>
        {loading && <RefreshCw size={9} style={{ color: '#00a888', animation: 'spin 1s linear infinite', flexShrink: 0 }} />}
      </button>

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
            onClick={copyContent}
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

      {isDir && open && (
        <>
          {loading && children === null && (
            <div style={{
              paddingLeft: indent + 16,
              fontFamily: 'JetBrains Mono, monospace',
              fontSize: 11,
              color: '#94a3b8',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}>
              <RefreshCw size={9} style={{ animation: 'spin 1s linear infinite' }} />
              Loading...
            </div>
          )}
          {(children || []).map((child, i) => (
            <FileNode
              key={child.path || child.name || i}
              node={child}
              projectName={projectName}
              taskId={taskId}
              accountId={accountId}
              depth={depth + 1}
            />
          ))}
          {children && children.length === 0 && !loading && (
            <div style={{
              paddingLeft: indent + 16,
              fontFamily: 'JetBrains Mono, monospace',
              fontSize: 10,
              color: '#94a3b8',
              fontStyle: 'italic',
            }}>
              (empty)
            </div>
          )}
        </>
      )}
    </div>
  );
}

function SessionFilesTab({ projectName, taskId, accountId, accountEmail }) {
  const [tree, setTree] = useState(null);
  const [loading, setLoading] = useState(false);

  const loadTree = useCallback(async () => {
    try {
      setLoading(true);
      let res;
      if (projectName && taskId) {
        res = await api.getTaskFileTreeWithAccount(projectName, taskId, accountId || '', '');
      } else if (accountId) {
        res = await api.getFileTree(accountId, '');
      } else {
        setTree([]);
        return;
      }
      const nodes = res.data ?? res ?? [];
      setTree(Array.isArray(nodes) ? nodes : []);
    } catch (e) {
      showToast(`Failed to load workspace: ${e.message}`, 'error');
      setTree([]);
    } finally {
      setLoading(false);
    }
  }, [projectName, taskId, accountId]);

  useEffect(() => {
    setTree(null);
    loadTree();
  }, [loadTree]);

  if (!projectName && !taskId && !accountId) {
    return (
      <div style={{ padding: '32px 16px', textAlign: 'center', fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: '#94a3b8', fontStyle: 'italic' }}>
        Account not found for this session.
      </div>
    );
  }

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
        No files found in workspace.
      </div>
    );
  }

  return (
    <div style={{ padding: '8px 0' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '0 16px 8px' }}>
        <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 10, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
          workspace
        </span>
        <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 10, color: '#94a3b8' }}>
          {accountEmail || accountId}
        </span>
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
        <FileNode
          key={i}
          node={node}
          projectName={projectName}
          taskId={taskId}
          accountId={accountId}
        />
      ))}
    </div>
  );
}

// ─── Session Composer ────────────────────────────────────────────────────────
function SessionComposer({
  sessionId,
  accountId,
  projectName,
  taskId,
  sessionFile,
  onSent,
}) {
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [imageDataUrl, setImageDataUrl] = useState('');
  const [imageMime, setImageMime] = useState('');
  const [imageName, setImageName] = useState('');
  const [modelId, setModelId] = useState(DEFAULT_MODEL_ID);
  const [lastError, setLastError] = useState('');
  const inputRef = useRef(null);
  const textareaRef = useRef(null);

  const hasContent = Boolean(text.trim() || imageDataUrl);
  const taskBound = Boolean(projectName && taskId);
  const hasSessionContext = Boolean(sessionId) || taskBound;
  const canSend = Boolean(hasSessionContext && accountId && !sending && hasContent);

  const disabledReason = !hasSessionContext
    ? 'Session ID 缺失 — 请从历史记录文件中选择会话'
    : !accountId
    ? '账户未匹配 — 无法在账户池中找到对应账户（需要 runtime_host 和 project_token）'
    : !hasContent
    ? '请输入消息内容'
    : '';

  const pickImage = () => inputRef.current?.click();

  const onImageChange = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (!String(f.type || '').startsWith('image/')) {
      showToast('Only image files are supported', 'error');
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      setImageDataUrl(String(reader.result || ''));
      setImageMime(f.type || 'image/png');
      setImageName(f.name || 'image');
    };
    reader.onerror = () => showToast('Failed to read image file', 'error');
    reader.readAsDataURL(f);
    e.target.value = '';
  };

  const clearImage = () => {
    setImageDataUrl('');
    setImageMime('');
    setImageName('');
  };

  const send = async () => {
    if (!canSend) {
      if (disabledReason) showToast(disabledReason, 'error');
      return;
    }
      setLastError('');
    try {
      setSending(true);
      const res = await api.sendSessionMessage(sessionId || 'local-pending', accountId, {
        text: text.trim() || null,
        image_url: imageDataUrl || null,
        image_mime: imageMime || null,
        no_reply: false,
        model: buildModelRef(modelId) || undefined,
        project_name: projectName || null,
        task_id: taskId || null,
        session_file: sessionFile || null,
      });
      const effectiveSessionId = String(res?.effective_session_id || '').trim();
      setText('');
      clearImage();
      showToast(
        effectiveSessionId
          ? `消息已发送 (${effectiveSessionId.slice(0, 8)}…)`
          : '消息已发送',
        'success',
      );
      onSent?.();
      for (let i = 1; i <= 10; i += 1) {
        setTimeout(() => onSent?.({ silent: true }), i * 2000);
      }
    } catch (e) {
      const msg = e.message || 'Send failed';
      setLastError(msg);
      showToast(`发送失败: ${msg}`, 'error');
    } finally {
      setSending(false);
    }
  };

  // Allow Ctrl+Enter to send
  const onKeyDown = (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      send();
    }
  };

  return (
    <div style={{
      borderTop: '1px solid #e2e8f0',
      padding: '10px 12px',
      background: '#ffffff',
      flexShrink: 0,
    }}>
      {/* Disabled reason banner */}
      {disabledReason && disabledReason !== '请输入消息内容' && (
        <div style={{
          display: 'flex',
          alignItems: 'flex-start',
          gap: 6,
          padding: '6px 10px',
          marginBottom: 8,
          background: '#fff7ed',
          border: '1px solid #fed7aa',
          borderRadius: 4,
          fontFamily: 'JetBrains Mono, monospace',
          fontSize: 10,
          color: '#c2410c',
          lineHeight: 1.5,
        }}>
          <AlertCircle size={12} style={{ flexShrink: 0, marginTop: 1 }} />
          {disabledReason}
        </div>
      )}

      {/* Last error */}
      {lastError && (
        <div style={{
          display: 'flex',
          alignItems: 'flex-start',
          gap: 6,
          padding: '6px 10px',
          marginBottom: 8,
          background: '#fef2f2',
          border: '1px solid #fecaca',
          borderRadius: 4,
          fontFamily: 'JetBrains Mono, monospace',
          fontSize: 10,
          color: '#dc2626',
          lineHeight: 1.5,
        }}>
          <AlertCircle size={12} style={{ flexShrink: 0, marginTop: 1 }} />
          {lastError}
        </div>
      )}

      <textarea
        ref={textareaRef}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder={
          !hasSessionContext
            ? '⚠ 无 Session ID，无法发送'
            : !accountId
            ? '⚠ 账户未匹配，无法发送'
            : '发送消息到上游会话… (Ctrl+Enter 发送)'
        }
        rows={3}
        style={{
          width: '100%',
          boxSizing: 'border-box',
          resize: 'vertical',
          border: `1px solid ${lastError ? '#fca5a5' : '#cbd5e1'}`,
          borderRadius: 6,
          outline: 'none',
          padding: '8px 10px',
          fontFamily: 'Inter, sans-serif',
          fontSize: 13,
          color: '#1e293b',
          background: (!hasSessionContext || !accountId) ? '#f8fafc' : '#ffffff',
          lineHeight: 1.6,
          transition: 'border-color 0.15s',
        }}
        onFocus={(e) => { e.target.style.borderColor = '#00a888'; }}
        onBlur={(e) => { e.target.style.borderColor = lastError ? '#fca5a5' : '#cbd5e1'; }}
      />

      {imageDataUrl && (
        <div style={{
          marginTop: 8,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          border: '1px solid #e2e8f0',
          background: '#f8fafc',
          padding: '6px 8px',
          borderRadius: 4,
          fontFamily: 'JetBrains Mono, monospace',
          fontSize: 10,
          color: '#475569',
        }}>
          <img
            src={imageDataUrl}
            alt="preview"
            style={{ width: 40, height: 40, objectFit: 'cover', border: '1px solid #cbd5e1', borderRadius: 3 }}
          />
          <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {imageName || 'image'}
          </span>
          <button
            onClick={clearImage}
            style={{ border: 'none', background: 'none', color: '#64748b', cursor: 'pointer', display: 'flex', alignItems: 'center' }}
            title="Remove image"
          >
            <X size={12} />
          </button>
        </div>
      )}

      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8 }}>
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          onChange={onImageChange}
          style={{ display: 'none' }}
        />
        <button
          onClick={pickImage}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            padding: '6px 10px',
            border: '1px solid #cbd5e1',
            borderRadius: 6,
            background: '#fff',
            color: '#475569',
            cursor: 'pointer',
            fontFamily: 'JetBrains Mono, monospace',
            fontSize: 11,
            transition: 'all 0.15s',
          }}
          onMouseEnter={(e) => { e.currentTarget.style.background = '#f1f5f9'; }}
          onMouseLeave={(e) => { e.currentTarget.style.background = '#fff'; }}
        >
          <ImagePlus size={12} />
          图片
        </button>

        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          minWidth: 220,
          maxWidth: 320,
          flex: 1,
        }}>
          <span style={{
            fontFamily: 'JetBrains Mono, monospace',
            fontSize: 10,
            color: '#94a3b8',
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
            flexShrink: 0,
          }}>
            model
          </span>
          <select
            value={modelId}
            onChange={(e) => setModelId(e.target.value)}
            style={{
              flex: 1,
              minWidth: 0,
              border: '1px solid #cbd5e1',
              borderRadius: 6,
              background: '#fff',
              color: '#334155',
              fontFamily: 'JetBrains Mono, monospace',
              fontSize: 11,
              padding: '6px 8px',
              outline: 'none',
            }}
          >
            {MODEL_OPTIONS.filter((opt) => opt.id).map((opt) => (
              <option key={opt.id} value={opt.id}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{
            fontFamily: 'JetBrains Mono, monospace',
            fontSize: 10,
            color: '#94a3b8',
          }}>
            Ctrl+Enter
          </span>
          <button
            onClick={send}
            disabled={sending}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              padding: '7px 16px',
              border: 'none',
              borderRadius: 6,
              background: canSend ? '#00a888' : '#e2e8f0',
              color: canSend ? '#ffffff' : '#94a3b8',
              cursor: sending ? 'not-allowed' : 'pointer',
              fontFamily: 'Inter, sans-serif',
              fontSize: 13,
              fontWeight: 500,
              transition: 'all 0.15s',
              opacity: sending ? 0.75 : 1,
            }}
            onMouseEnter={(e) => {
              if (canSend && !sending) e.currentTarget.style.background = '#009b7d';
            }}
            onMouseLeave={(e) => {
              if (canSend) e.currentTarget.style.background = '#00a888';
            }}
          >
            {sending
              ? <RefreshCw size={13} style={{ animation: 'spin 1s linear infinite' }} />
              : <Send size={13} />
            }
            {sending ? '发送中…' : '发送'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Main SessionView ─────────────────────────────────────────────────────────
export default function SessionView() {
  const { selectedNode, setSelectedNode } = useAppStore();
  const { tasks, accounts, fetchAccounts, fetchTasks } = useDataStore();

  const [rawContent, setRawContent] = useState(null);
  const [sessionMessages, setSessionMessages] = useState([]);
  const [credits, setCredits] = useState(null);
  const [loading, setLoading] = useState(false);
  const [switching, setSwitching] = useState(false);
  const [activeTab, setActiveTab] = useState('chat');
  const bottomRef = useRef(null);

  const { project, taskId, accountEmail, sessionFile, sessionId: selectedSessionId } = selectedNode || {};

  const taskList = tasks[project] || [];
  const task = taskList.find((t) => (t.id || t.task_id || t.taskId) === taskId);
  const isLive = task && [
    'running', 'monitoring', 'pending', 'switching', 'syncing', 'pushing',
    'acquiring_account', 'auto_registering_account',
    'bootstrapping_runtime', 'creating_session', 'sending_message', 'submitting_commit',
  ].includes(task.status);

  const loadContent = useCallback(async ({ silent = false, refreshRuntime = false, accountId = '' } = {}) => {
    if (!project || !taskId || !sessionFile) return;
    try {
      if (!silent) setLoading(true);
      const res = await api.getSessionContent(project, taskId, sessionFile, {
        refreshRuntime,
        accountId,
      });
      const payload = res?.data ?? res ?? {};
      const content = typeof payload === 'string'
        ? payload
        : (payload?.content ?? res?.content ?? '');
      const rows = normalizeMessageRows(payload?.messages ?? []);
      setRawContent(typeof content === 'string' ? content : '');
      setSessionMessages(rows);
    } catch (e) {
      if (!silent) showToast(`Failed to load session: ${e.message}`, 'error');
      setRawContent('');
      setSessionMessages([]);
    } finally {
      if (!silent) setLoading(false);
    }
  }, [project, taskId, accountEmail, sessionFile]);

  useEffect(() => {
    setRawContent(null);
    setSessionMessages([]);
    setCredits(null);
    setActiveTab('chat');
    loadContent();
  }, [loadContent]);

  useEffect(() => {
    if (!isLive || !project || !taskId || !sessionFile) return undefined;
    const timer = setInterval(() => {
      loadContent({ silent: true });
    }, 5000);
    return () => clearInterval(timer);
  }, [isLive, project, taskId, sessionFile, loadContent]);

  useEffect(() => {
    if (!accounts || accounts.length === 0) {
      fetchAccounts();
    }
  }, [accounts, fetchAccounts]);

  useEffect(() => {
    if (sessionMessages.length > 0) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [sessionMessages]);

  const userMsgs = sessionMessages.filter((s) => s.role === 'user').length;
  const asstMsgs = sessionMessages.filter((s) => s.role === 'assistant').length;

  const headerAccountEmail = extractHeaderValue(rawContent, 'Account');
  const effectiveAccountEmail = accountEmail || headerAccountEmail;
  const headerSessionId = extractHeaderValue(rawContent, 'NodeOps Session ID');
  const effectiveSessionId = headerSessionId || selectedSessionId;

  const matchedAccount = (accounts || []).find((a) => a.email === effectiveAccountEmail);
  const taskBoundAccount = (accounts || []).find((a) => a.id === task?.current_account_id);
  const effectiveAccountId = taskBoundAccount?.id || matchedAccount?.id || '';
  const effectiveAccountEmailDisplay = taskBoundAccount?.email || effectiveAccountEmail;
  const lowCreditsThreshold = 150;

  useEffect(() => {
    if (!matchedAccount) return;
    const baseline = matchedAccount?.credits_remaining ?? matchedAccount?.credits ?? null;
    if (baseline === null || baseline === undefined || baseline === '') return;
    const num = Number(baseline);
    setCredits(Number.isFinite(num) ? num : baseline);
  }, [matchedAccount]);

  useEffect(() => {
    if (!project || !taskId) return undefined;
    const es = api.createTaskEventSource(project, taskId);

    const handleCreditsEvent = (evt) => {
      try {
        const payload = JSON.parse(evt?.data || '{}');
        const eventType = String(payload?.type || '').trim().toLowerCase();
        if (eventType !== 'credits_updated') return;
        const remaining = payload?.data?.credits_remaining;
        if (remaining === null || remaining === undefined || remaining === '') {
          setCredits(null);
          return;
        }
        const num = Number(remaining);
        setCredits(Number.isFinite(num) ? num : remaining);
      } catch (_) {
        // ignore malformed task events
      }
    };

    es.addEventListener('credits_updated', handleCreditsEvent);
    es.addEventListener('message', handleCreditsEvent);

    return () => {
      es.removeEventListener('credits_updated', handleCreditsEvent);
      es.removeEventListener('message', handleCreditsEvent);
      es.close();
    };
  }, [project, taskId]);

  const refreshCreditsNow = useCallback(async () => {
    if (!effectiveAccountId) return;
    try {
      const res = await api.refreshCredits(effectiveAccountId);
      const payload = res?.data ?? res ?? {};
      const remaining = payload?.credits_remaining;
      if (remaining === null || remaining === undefined || remaining === '') {
        setCredits(null);
        return;
      }
      const num = Number(remaining);
      setCredits(Number.isFinite(num) ? num : remaining);
    } catch (e) {
      showToast(`Failed to refresh credits: ${e.message}`, 'error');
    }
  }, [effectiveAccountId]);

  const handleManualRefresh = useCallback(async () => {
    await loadContent({
      refreshRuntime: true,
      accountId: effectiveAccountId || '',
    });
    await refreshCreditsNow();
  }, [loadContent, refreshCreditsNow, effectiveAccountId]);

  const handleSwitchAccount = useCallback(async () => {
    if (!project || !taskId || switching) return;
    try {
      setSwitching(true);
      const res = await api.switchTaskAccount(project, taskId);
      const data = res?.data ?? res ?? {};
      await Promise.allSettled([
        fetchTasks(project),
        fetchAccounts(),
      ]);
      if (selectedNode?.type === 'session' && selectedNode.project === project && selectedNode.taskId === taskId) {
        setSelectedNode({
          ...selectedNode,
          accountEmail: data.account_email || selectedNode.accountEmail || '',
        });
      }
      showToast(`Switched to ${data.account_email || 'new account'}`, 'success');
      // Refresh to pick up new account info
      await loadContent({ refreshRuntime: true, accountId: data.account_id || '' });
    } catch (e) {
      showToast(`Switch account failed: ${e.message}`, 'error');
    } finally {
      setSwitching(false);
    }
  }, [
    project,
    taskId,
    switching,
    loadContent,
    fetchTasks,
    fetchAccounts,
    selectedNode,
    setSelectedNode,
  ]);

  const tabs = [
    { id: 'chat', label: 'Chat', icon: <MessageSquare size={12} /> },
    { id: 'files', label: 'Files', icon: <File size={12} /> },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', fontFamily: 'Inter, sans-serif' }}>
      {/* ── Header ── */}
      <div style={{
        padding: '20px 24px 0',
        borderBottom: '1px solid #e2e8f0',
        flexShrink: 0,
        background: '#fff',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, marginBottom: 12 }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <MessageSquare size={13} style={{ color: 'rgba(0,168,136,0.6)', flexShrink: 0 }} />
              <h1 style={{
                fontFamily: 'JetBrains Mono, monospace',
                fontWeight: 700,
                fontSize: 14,
                color: '#0f172a',
                margin: 0,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}>
                {sessionFile || 'session'}
              </h1>
              {isLive && (
                <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontFamily: 'JetBrains Mono, monospace', fontSize: 10, color: '#00a888' }}>
                  <span style={{
                    width: 6,
                    height: 6,
                    borderRadius: '50%',
                    background: '#00a888',
                    boxShadow: '0 0 4px rgba(0,168,136,0.7)',
                    animation: 'pulseDot 2s ease-in-out infinite',
                  }} />
                  live
                </span>
              )}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 4, flexWrap: 'wrap' }}>
              {effectiveAccountEmailDisplay && (
                <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: '#6b7280' }}>
                  {effectiveAccountEmailDisplay}
                </span>
              )}
              <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: '#64748b' }}>
                {project} / {taskId}
              </span>
              {effectiveSessionId && (
                <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 10, color: '#94a3b8' }}>
                  {effectiveSessionId.slice(0, 8)}…
                </span>
              )}
              {sessionMessages.length > 0 && (
                <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 10, color: '#94a3b8' }}>
                  {userMsgs}↑ {asstMsgs}↓
                </span>
              )}
            </div>
          </div>

          <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
            <button
              onClick={handleSwitchAccount}
              disabled={switching || isLive}
              title="Switch to a new account"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 5,
                padding: '6px 10px',
                border: '1px solid #cbd5e1',
                borderRadius: 6,
                background: 'transparent',
                color: '#6b7280',
                fontFamily: 'JetBrains Mono, monospace',
                fontSize: 11,
                cursor: (switching || isLive) ? 'not-allowed' : 'pointer',
                opacity: (switching || isLive) ? 0.5 : 1,
                transition: 'all 0.15s',
              }}
              onMouseEnter={(e) => { if (!switching && !isLive) { e.currentTarget.style.color = '#334155'; e.currentTarget.style.background = '#f1f5f9'; } }}
              onMouseLeave={(e) => { e.currentTarget.style.color = '#6b7280'; e.currentTarget.style.background = 'transparent'; }}
            >
              <Repeat size={11} style={switching ? { animation: 'spin 1s linear infinite' } : {}} />
              换号
            </button>
            <button
              onClick={handleManualRefresh}
              disabled={loading}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                padding: '6px 12px',
                border: '1px solid #cbd5e1',
                borderRadius: 6,
                background: 'transparent',
                color: '#6b7280',
                fontFamily: 'JetBrains Mono, monospace',
                fontSize: 11,
                cursor: loading ? 'not-allowed' : 'pointer',
                opacity: loading ? 0.5 : 1,
                transition: 'all 0.15s',
              }}
              onMouseEnter={(e) => { e.currentTarget.style.color = '#334155'; e.currentTarget.style.background = '#f1f5f9'; }}
              onMouseLeave={(e) => { e.currentTarget.style.color = '#6b7280'; e.currentTarget.style.background = 'transparent'; }}
            >
              <RefreshCw size={11} style={loading ? { animation: 'spin 1s linear infinite' } : {}} />
              刷新
            </button>
          </div>
        </div>

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

      {/* ── Chat tab ── */}
      {activeTab === 'chat' && (
        <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
          {credits !== null && (
            <div style={{
              padding: '6px 16px',
              fontSize: 11,
              fontFamily: 'JetBrains Mono, monospace',
              color: (typeof credits === 'number' && credits < lowCreditsThreshold) ? '#ef4444' : '#64748b',
              borderBottom: '1px solid #e2e8f0',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              background: (typeof credits === 'number' && credits < lowCreditsThreshold) ? '#fef2f2' : 'transparent',
              flexShrink: 0,
            }}>
              <span>Credits: {typeof credits === 'number' ? credits.toFixed(1) : String(credits)}</span>
              {(typeof credits === 'number' && credits < lowCreditsThreshold) && <AlertCircle size={12} color="#ef4444" />}
            </div>
          )}
          <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0', background: '#f8fafc' }}>
            {loading ? (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 128, gap: 8, fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: 'rgba(0,168,136,0.6)' }}>
                <RefreshCw size={12} style={{ animation: 'spin 1s linear infinite' }} />
                loading session…
              </div>
            ) : sessionMessages.length === 0 ? (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 128 }}>
                <p style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 12, color: '#94a3b8', fontStyle: 'italic' }}>
                  {sessionFile ? 'Empty session — no messages yet' : 'No session selected'}
                </p>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, paddingTop: 8, paddingBottom: 8 }}>
                {sessionMessages.map((seg, i) => (
                  <MessageBubble key={i} segment={seg} />
                ))}
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          <SessionComposer
            sessionId={effectiveSessionId}
            accountId={effectiveAccountId}
            projectName={project}
            taskId={taskId}
            sessionFile={sessionFile}
            onSent={loadContent}
          />
        </div>
      )}

      {/* ── Files tab ── */}
      {activeTab === 'files' && (
        <div style={{ flex: 1, overflowY: 'auto' }}>
          <SessionFilesTab
            projectName={project}
            taskId={taskId}
            accountId={effectiveAccountId}
            accountEmail={effectiveAccountEmailDisplay}
          />
        </div>
      )}

      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        @keyframes pulseDot { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
      `}</style>
    </div>
  );
}
