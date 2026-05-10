import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  RefreshCw, MessageSquare, User, Bot, Activity,
  ChevronDown, ChevronUp, Copy, Check, Send, ImagePlus, X,
  ChevronRight, Folder, File, AlertCircle,
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

function extractTextFromParts(parts) {
  if (!Array.isArray(parts)) return { text: '', tools: [] };
  const texts = [];
  const tools = [];
  for (const part of parts) {
    if (!part || typeof part !== 'object') continue;
    const type = String(part.type || '').trim().toLowerCase();
    if (type === 'text' && part.text) {
      texts.push(String(part.text));
      continue;
    }
    if (type.includes('tool') || type === 'function') {
      const name = part.name || part.tool || part.toolName || part.functionName || 'unknown';
      const input = part.input ?? part.arguments ?? part.args ?? part.parameters ?? null;
      const output = part.output ?? part.result ?? null;
      if (input && output) {
        tools.push(`[tool ${name}] input=${JSON.stringify(input)} output=${JSON.stringify(output)}`);
      } else if (input) {
        tools.push(`[tool ${name}] input=${JSON.stringify(input)}`);
      } else if (output) {
        tools.push(`[tool ${name}] output=${JSON.stringify(output)}`);
      } else {
        tools.push(`[tool ${name}]`);
      }
    }
  }
  return { text: texts.join('\n').trim(), tools };
}

function parseRuntimePayload(payload, eventName = '') {
  const event = String(eventName || '').trim().toLowerCase();
  if (event === 'ping') return [];

  if (!payload || typeof payload !== 'object') {
    const txt = String(payload || '').trim();
    if (!txt) return [];
    return [{ role: 'system', text: event ? `[${event}] ${txt}` : txt }];
  }

  const type = String(payload.type || payload.event || '').trim();
  const typeLower = type.toLowerCase();
  const props = payload.properties && typeof payload.properties === 'object' ? payload.properties : {};

  if (typeLower === 'server.connected') return [];
  if (typeLower === 'context.updated') {
    const usage = props.usage || {};
    const tokens = usage.tokens;
    if (typeof tokens === 'number') {
      return [{ role: 'system', text: `[context] tokens=${tokens}` }];
    }
    return [];
  }
  if (typeLower === 'session.status') {
    const statusType = String(props?.status?.type || '').trim();
    if (!statusType) return [];
    return [{ role: 'system', text: `[status] ${statusType}` }];
  }
  if (typeLower === 'session.error') {
    const err = props.error || {};
    const status = err.status ? ` ${err.status}` : '';
    const msg = String(err.message || 'session error');
    return [{ role: 'system', text: `[error${status}] ${msg}` }];
  }
  if (typeLower === 'session.idle') return [];
  // Upstream SSE: message.part.updated → properties.part contains the part object
  if (typeLower === 'message.part.updated') {
    const part = props.part;
    if (!part || typeof part !== 'object') return [];
    const partType = String(part.type || '').trim().toLowerCase();
    if (partType === 'text') {
      const txt = String(part.text ?? props.delta ?? '').trim();
      if (txt) return [{ role: 'assistant', text: txt }];
    }
    if (partType === 'step-finish') return [];
    if (partType.includes('tool') || partType === 'function') {
      const name = part.name || part.toolName || 'tool';
      return [{ role: 'system', text: `[tool ${name}]` }];
    }
    return [];
  }
  if (typeLower === 'message.completed') return [];

  const messageObj =
    (payload.message && typeof payload.message === 'object' ? payload.message : null)
    || (props.message && typeof props.message === 'object' ? props.message : null)
    || (props.delta && typeof props.delta === 'object' ? props.delta : null)
    || (props.chunk && typeof props.chunk === 'object' ? props.chunk : null);

  const role = normalizeRole(
    payload.role
    || payload?.info?.role
    || messageObj?.role
    || messageObj?.info?.role
    || props.role
  );

  const parts = Array.isArray(payload.parts)
    ? payload.parts
    : Array.isArray(messageObj?.parts)
      ? messageObj.parts
      : Array.isArray(props.parts)
        ? props.parts
        : [];
  const { text: partText, tools } = extractTextFromParts(parts);

  const directText = String(
    payload.content
    || payload.text
    || (typeof payload.message === 'string' ? payload.message : '')
    || messageObj?.content
    || messageObj?.text
    || (typeof messageObj?.message === 'string' ? messageObj.message : '')
    || ''
  ).trim();
  const text = directText || partText;

  const out = [];
  if (text) {
    out.push({ role: role || 'assistant', text });
  }
  for (const t of tools) {
    out.push({ role: 'system', text: t });
  }
  if (out.length > 0) return out;

  if (type) {
    return [{ role: 'system', text: `[${type}]` }];
  }
  return [{ role: 'system', text: JSON.stringify(payload) }];
}

// ─── Parse upstream GET /session/{id}/message JSON array ─────────────────────
// Each element: { info: { role, id, ... }, parts: [{ type:"text", text:"..." }, ...] }
function parseRuntimeMessages(messages) {
  if (!Array.isArray(messages)) return [];
  const out = [];
  for (const msg of messages) {
    if (!msg || typeof msg !== 'object') continue;
    const role = normalizeRole(msg?.info?.role) || 'assistant';
    const { text, tools } = extractTextFromParts(msg.parts);
    if (text) out.push({ role, text });
    for (const t of tools) out.push({ role: 'system', text: t });
  }
  return out;
}

// ─── Parse raw session .md content into segments ──────────────────────────────
// Format from actual session files:
//   **[User]** 2026-05-09 08:40:39
//   hello
//
//   **[unknown]** 2026-05-09 08:40:39
//   hello (echo)
function parseSessionContent(raw) {
  if (!raw || typeof raw !== 'string') return [];
  const lines = raw.split('\n');
  const segments = [];
  let current = null;   // { role, lines[] }
  let pendingSseEvent = '';

  const flush = () => {
    if (current) {
      // Strip leading/trailing empty lines
      while (current.lines.length && current.lines[0].trim() === '') current.lines.shift();
      while (current.lines.length && current.lines[current.lines.length - 1].trim() === '') current.lines.pop();
      current.text = current.lines.join('\n').trim();
      if (current.text) segments.push(current);
    }
    current = null;
  };

  for (const line of lines) {
    const trimmed = line.trim();

    // ── Raw JSON line ──────────────────────────────────────────────────────────
    if (trimmed.startsWith('{') && trimmed.endsWith('}')) {
      try {
        const obj = JSON.parse(trimmed);
        flush();
        segments.push(...parseRuntimePayload(obj));
        continue;
      } catch (_) {}
    }

    // ── Legacy inline format: [message] {...} / [ping] {} ────────────────────
    const legacyMatch = trimmed.match(/^\[([^\]]+)\]\s*(.*)$/);
    if (legacyMatch) {
      const evt = String(legacyMatch[1] || '').trim();
      const body = String(legacyMatch[2] || '').trim();
      flush();
      if (body.startsWith('{') && body.endsWith('}')) {
        try {
          const obj = JSON.parse(body);
          segments.push(...parseRuntimePayload(obj, evt));
          continue;
        } catch (_) {}
      }
      segments.push({ role: 'system', text: evt ? `[${evt}] ${body}` : body });
      continue;
    }

    // ── SSE event: ─────────────────────────────────────────────────────────────
    if (/^event:\s*/i.test(trimmed)) {
      flush();
      pendingSseEvent = trimmed.replace(/^event:\s*/i, '').trim();
      continue;
    }

    // ── SSE data: ──────────────────────────────────────────────────────────────
    if (/^data:\s*/i.test(trimmed)) {
      const payloadText = trimmed.replace(/^data:\s*/i, '').trim();
      if (payloadText) {
        try {
          const obj = JSON.parse(payloadText);
          flush();
          segments.push(...parseRuntimePayload(obj, pendingSseEvent || 'sse'));
          continue;
        } catch (_) {}
      }
    }

    // ── Markdown role markers ──────────────────────────────────────────────────
    // Pattern: **[Role]** optional-timestamp
    // The role tag may have 0, 1, or 2 asterisks on each side.
    // We strip the tag AND any trailing timestamp (YYYY-MM-DD HH:MM:SS style).
    const roleTagRe = /^\*{0,2}\[(User|Assistant|System|Unknown)\]\*{0,2}\s*/i;
    const timestampRe = /^\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:\d{2})?\s*/;

    if (roleTagRe.test(line)) {
      flush();
      const afterTag = line.replace(roleTagRe, '');
      // Strip timestamp that follows the tag on the same line
      const messageText = afterTag.replace(timestampRe, '').trim();

      const roleMatch = line.match(roleTagRe);
      const rawRole = (roleMatch?.[1] || 'system').toLowerCase();

      // Map "unknown" → assistant (it's typically the upstream echo)
      const role = rawRole === 'unknown' ? 'assistant' : rawRole;

      current = { role, lines: messageText ? [messageText] : [] };
      continue;
    }

    // ── Section divider ────────────────────────────────────────────────────────
    if (/^---+$/.test(trimmed)) {
      flush();
      segments.push({ role: 'divider', text: '---' });
      continue;
    }

    // ── Markdown headings ──────────────────────────────────────────────────────
    if (/^#{1,3}\s/.test(line)) {
      flush();
      segments.push({ role: 'meta', text: line.replace(/^#+\s/, '') });
      continue;
    }

    // ── Session header lines ───────────────────────────────────────────────────
    if (/^-\s+(Account|NodeOps Session ID|Started|Ended|End Reason):/i.test(trimmed)) {
      flush();
      segments.push({ role: 'system', text: trimmed });
      continue;
    }

    // ── Blank line ─────────────────────────────────────────────────────────────
    if (trimmed === '') {
      if (current) current.lines.push('');
      continue;
    }

    // ── Regular text ───────────────────────────────────────────────────────────
    if (current) {
      current.lines.push(line);
    } else if (trimmed) {
      segments.push({ role: 'system', text: trimmed });
    }
  }

  flush();

  // Filter: keep dividers and anything with non-empty text.
  // Also deduplicate consecutive identical assistant echoes (unknown lines often mirror user input).
  const filtered = segments.filter((s) => s.role === 'divider' || (s.text && s.text.trim()));

  // Remove consecutive duplicates where an assistant message immediately follows a user
  // message with identical text (the [unknown] echo pattern in session files).
  const deduped = [];
  for (let i = 0; i < filtered.length; i++) {
    const prev = deduped[deduped.length - 1];
    const cur = filtered[i];
    // Skip assistant echo that is identical to the preceding user message
    if (
      prev &&
      prev.role === 'user' &&
      cur.role === 'assistant' &&
      cur.text.trim() === prev.text.trim()
    ) {
      continue;
    }
    deduped.push(cur);
  }

  return deduped;
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

function FileNode({ node, accountId, depth = 0 }) {
  const [open, setOpen] = useState(false);
  const [content, setContent] = useState(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  const isDir = node.type === 'directory' || node.is_dir === true || Array.isArray(node.children);
  const indent = depth * 16 + 8;

  const handleClick = async () => {
    if (isDir) {
      setOpen((v) => !v);
      return;
    }
    if (content !== null) {
      setContent(null);
      return;
    }
    if (!accountId) {
      showToast('No account for workspace', 'error');
      return;
    }
    try {
      setLoading(true);
      const res = await api.getFileContent(accountId, node.path || node.name);
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
          {(node.children || []).map((child, i) => (
            <FileNode key={i} node={child} accountId={accountId} depth={depth + 1} />
          ))}
        </>
      )}
    </div>
  );
}

function SessionFilesTab({ accountId, accountEmail }) {
  const [tree, setTree] = useState(null);
  const [loading, setLoading] = useState(false);

  const loadTree = useCallback(async () => {
    if (!accountId) {
      setTree([]);
      return;
    }
    try {
      setLoading(true);
      const res = await api.getFileTree(accountId, '');
      const nodes = res.data ?? res ?? [];
      setTree(Array.isArray(nodes) ? nodes : []);
    } catch (e) {
      showToast(`Failed to load workspace: ${e.message}`, 'error');
      setTree([]);
    } finally {
      setLoading(false);
    }
  }, [accountId]);

  useEffect(() => {
    setTree(null);
    loadTree();
  }, [loadTree]);

  if (!accountId) {
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
        <FileNode key={i} node={node} accountId={accountId} />
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
  accountDir,
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
      await api.sendSessionMessage(sessionId || 'local-pending', accountId, {
        text: text.trim() || null,
        image_url: imageDataUrl || null,
        image_mime: imageMime || null,
        no_reply: false,
        model: buildModelRef(modelId) || undefined,
        project_name: projectName || null,
        task_id: taskId || null,
        account: accountDir || null,
        session_file: sessionFile || null,
      });
      setText('');
      clearImage();
      showToast('消息已发送', 'success');
      onSent?.();
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

// ─── Live SSE message stream ──────────────────────────────────────────────────
function LiveMessages({ project, taskId }) {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [connected, setConnected] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    const appendRows = (rows) => {
      if (!Array.isArray(rows) || rows.length === 0) return;
      setMessages((prev) => [...prev, ...rows]);
    };

    const rowsFromTaskMessage = (msg) => {
      if (!msg || typeof msg !== 'object') return [];
      // Upstream format: { info: { role }, parts: [...] }
      if (msg.info && Array.isArray(msg.parts)) {
        return parseRuntimePayload(msg);
      }
      const role = normalizeRole(msg.role);
      const text = String(msg.content || msg.message || msg.text || '').trim();
      if (text) return [{ role: role || 'assistant', text }];
      if (msg.raw && typeof msg.raw === 'object') {
        return parseRuntimePayload(msg.raw);
      }
      return [];
    };

    const rowsFromEvent = (eventType, payload) => {
      if (!payload || typeof payload !== 'object') return [];

      if (eventType === 'runtime_sse') {
        const runtimeEvent = payload?.data?.event || payload.event || '';
        const runtimePayload = payload?.data?.data ?? payload?.data ?? payload;
        return parseRuntimePayload(runtimePayload, runtimeEvent);
      }

      if (eventType === 'message') {
        return rowsFromTaskMessage(payload);
      }

      if (eventType === 'status') {
        const status = payload?.status || payload?.data?.status;
        if (!status) return [];
        return [{ role: 'system', text: `[status] ${status}` }];
      }

      if (eventType === 'error') {
        const err = payload?.error || payload?.data?.error || JSON.stringify(payload);
        return [{ role: 'system', text: `[error] ${String(err)}` }];
      }

      return [];
    };

    api.getTaskMessages(project, taskId)
      .then((res) => {
        const msgs = res.data ?? res ?? [];
        const rows = Array.isArray(msgs) ? msgs.flatMap(rowsFromTaskMessage) : [];
        setMessages(rows);
      })
      .catch(() => {})
      .finally(() => setLoading(false));

    const es = api.createTaskEventSource(project, taskId);
    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);

    es.addEventListener('message', (e) => {
      try {
        const data = JSON.parse(e.data);
        appendRows(rowsFromEvent('message', data));
      } catch (_) {
        if (e.data) appendRows([{ role: 'system', text: e.data }]);
      }
    });

    es.addEventListener('status', (e) => {
      try {
        const data = JSON.parse(e.data);
        appendRows(rowsFromEvent('status', data));
      } catch (_) {}
    });

    es.addEventListener('runtime_sse', (e) => {
      try {
        const data = JSON.parse(e.data);
        appendRows(rowsFromEvent('runtime_sse', data));
      } catch (_) {}
    });

    es.addEventListener('error', (e) => {
      try {
        const data = JSON.parse(e.data);
        appendRows(rowsFromEvent('error', data));
      } catch (_) {}
    });

    return () => {
      es.close();
      setConnected(false);
    };
  }, [project, taskId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '16px', fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: 'rgba(0,168,136,0.6)' }}>
        <RefreshCw size={11} style={{ animation: 'spin 1s linear infinite' }} />
        loading live messages…
      </div>
    );
  }

  return (
    <div style={{ borderTop: '1px solid #e2e8f0', marginTop: 8 }}>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '8px 16px',
        borderBottom: '1px solid #e2e8f0',
      }}>
        <Activity size={11} style={{ color: '#00a888' }} />
        <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 10, color: '#00a888', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
          live stream
        </span>
        {connected && (
          <span style={{
            width: 6,
            height: 6,
            borderRadius: '50%',
            background: '#00a888',
            boxShadow: '0 0 4px rgba(0,168,136,0.6)',
            animation: 'pulseDot 2s ease-in-out infinite',
          }} />
        )}
        <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 10, color: '#64748b', marginLeft: 'auto' }}>
          {messages.length} events
        </span>
      </div>

      <div style={{ padding: '4px 0' }}>
        {messages.length === 0 && (
          <p style={{ padding: '8px 16px', fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: '#94a3b8', fontStyle: 'italic' }}>
            no live events yet
          </p>
        )}
        {messages.map((msg, i) => {
          const role = msg.role || 'system';
          const text = msg.text || msg.content || msg.message || JSON.stringify(msg);
          const isUser = role === 'user';
          const isAssistant = role === 'assistant';
          return (
            <div key={i} style={{ padding: '2px 16px' }}>
              <div style={{
                fontFamily: 'JetBrains Mono, monospace',
                fontSize: 11,
                lineHeight: 1.5,
                padding: '6px 10px',
                background: isUser ? 'rgba(0,168,136,0.08)'
                  : isAssistant ? '#f1f5f9'
                  : 'rgba(241,245,249,0.5)',
                borderLeft: `2px solid ${isUser ? '#00a888' : isAssistant ? '#4a9eff' : '#cbd5e1'}`,
                color: '#334155',
              }}>
                {role && (
                  <span style={{ fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.1em', opacity: 0.6, display: 'block', marginBottom: 2 }}>
                    {role}
                  </span>
                )}
                <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{text}</pre>
              </div>
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

// ─── Main SessionView ─────────────────────────────────────────────────────────
export default function SessionView() {
  const { selectedNode } = useAppStore();
  const { tasks, accounts, fetchAccounts } = useDataStore();

  const [rawContent, setRawContent] = useState(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('chat');
  const bottomRef = useRef(null);

  const { project, taskId, accountDir, accountEmail, sessionFile, sessionId: selectedSessionId } = selectedNode || {};

  const taskList = tasks[project] || [];
  const task = taskList.find((t) => (t.id || t.task_id || t.taskId) === taskId);
  const isLive = task && [
    'running', 'monitoring', 'pending', 'switching', 'syncing', 'pushing',
    'acquiring_account', 'auto_registering_account',
    'bootstrapping_runtime', 'creating_session', 'sending_message',
  ].includes(task.status);

  const loadContent = useCallback(async () => {
    if (!project || !taskId || !sessionFile) return;
    try {
      setLoading(true);
      const res = await api.getSessionContent(project, taskId, accountDir || accountEmail || '', sessionFile);
      const payload = res?.data ?? res ?? {};
      const content = typeof payload === 'string'
        ? payload
        : (payload?.content ?? res?.content ?? '');
      setRawContent(typeof content === 'string' ? content : '');
    } catch (e) {
      showToast(`Failed to load session: ${e.message}`, 'error');
      setRawContent('');
    } finally {
      setLoading(false);
    }
  }, [project, taskId, accountDir, accountEmail, sessionFile]);

  useEffect(() => {
    setRawContent(null);
    setActiveTab('chat');
    loadContent();
  }, [loadContent]);

  useEffect(() => {
    if (!accounts || accounts.length === 0) {
      fetchAccounts();
    }
  }, [accounts, fetchAccounts]);

  useEffect(() => {
    if (rawContent !== null) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [rawContent]);

  const segments = rawContent ? parseSessionContent(rawContent) : [];
  const userMsgs = segments.filter((s) => s.role === 'user').length;
  const asstMsgs = segments.filter((s) => s.role === 'assistant').length;

  const headerAccountEmail = extractHeaderValue(rawContent, 'Account');
  const effectiveAccountEmail = accountEmail || headerAccountEmail;
  const headerSessionId = extractHeaderValue(rawContent, 'NodeOps Session ID');
  const effectiveSessionId = headerSessionId || selectedSessionId;

  const matchedAccount = (accounts || []).find((a) => a.email === effectiveAccountEmail);
  const effectiveAccountId = matchedAccount?.id || task?.current_account_id || '';

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
              {effectiveAccountEmail && (
                <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: '#6b7280' }}>
                  {effectiveAccountEmail}
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
              {segments.length > 0 && (
                <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 10, color: '#94a3b8' }}>
                  {userMsgs}↑ {asstMsgs}↓
                </span>
              )}
            </div>
          </div>

          <button
            onClick={loadContent}
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
              flexShrink: 0,
            }}
            onMouseEnter={(e) => { e.currentTarget.style.color = '#334155'; e.currentTarget.style.background = '#f1f5f9'; }}
            onMouseLeave={(e) => { e.currentTarget.style.color = '#6b7280'; e.currentTarget.style.background = 'transparent'; }}
          >
            <RefreshCw size={11} style={loading ? { animation: 'spin 1s linear infinite' } : {}} />
            刷新
          </button>
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
          <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0', background: '#f8fafc' }}>
            {loading ? (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 128, gap: 8, fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: 'rgba(0,168,136,0.6)' }}>
                <RefreshCw size={12} style={{ animation: 'spin 1s linear infinite' }} />
                loading session…
              </div>
            ) : segments.length === 0 ? (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 128 }}>
                <p style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 12, color: '#94a3b8', fontStyle: 'italic' }}>
                  {sessionFile ? 'Empty session — no messages yet' : 'No session selected'}
                </p>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, paddingTop: 8, paddingBottom: 8 }}>
                {segments.map((seg, i) => (
                  <MessageBubble key={i} segment={seg} />
                ))}
              </div>
            )}

            {isLive && project && taskId && <LiveMessages project={project} taskId={taskId} />}
            <div ref={bottomRef} />
          </div>

          <SessionComposer
            sessionId={effectiveSessionId}
            accountId={effectiveAccountId}
            projectName={project}
            taskId={taskId}
            accountDir={accountDir || effectiveAccountEmail}
            sessionFile={sessionFile}
            onSent={loadContent}
          />
        </div>
      )}

      {/* ── Files tab ── */}
      {activeTab === 'files' && (
        <div style={{ flex: 1, overflowY: 'auto' }}>
          <SessionFilesTab accountId={effectiveAccountId} accountEmail={effectiveAccountEmail} />
        </div>
      )}

      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        @keyframes pulseDot { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
      `}</style>
    </div>
  );
}
