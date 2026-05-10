# Chat 消息链路最小改造计划（3 处改动）

> 日期：2026-05-10  
> 目标：前端只显示对话消息；session 文件只存对话消息；移除 raw SSE 污染与重复来源

## 落地状态（2026-05-10）

- [x] 改动 1：后端停掉 raw SSE 落盘，session 文件仅写 user/assistant。
- [x] 改动 2：`/api/events/session/{session_id}` 不再透传 raw SSE，改为语义化事件（`message/message_part/status/error`）。
- [x] 改动 3：前端移除 raw SSE 解析器，Chat 仅渲染后端消息。

---

## 病根（精确版）

1. `backend/services/task_engine.py`  
   `_consume_sse_stream()` / `_flush_sse_event()` 调用了 `session_recorder.append_raw_sse()`，把 `status/context/ping/message.part.updated` 等原始事件写入了 session 文件。

2. `backend/api/events.py`  
   `stream_session_events()` 原样透传上游 SSE，前端被迫在 `SessionView.jsx` 做复杂事件解析，展示层混入了控制事件。

3. 同一条用户消息存在双写路径  
   task loop 发送后有一条本地写入，再被消息轮询路径写一次，造成 `[User]` 重复。

---

## 改动 1（后端）：停掉 raw SSE 写入，保留纯消息写入

文件：
- `backend/services/task_engine.py`
- `backend/services/session_recorder.py`

动作：
1. 删除 `append_raw_sse()` 调用点（不再把原始 SSE 落盘）。
2. session 文件只允许 `append_message(role, content)` 写入。
3. 对 task loop 消息写入做单路径收敛，避免同一条 user 消息被写两次。

验收：
1. `session-*.md` 不再出现 `[status]`、`[context]`、`[message.updated]`、raw `event:/data:` 块。
2. 同一轮消息中 `[User]` 不重复。

---

## 改动 2（后端）：SSE 接口不再透传原始块

文件：
- `backend/api/events.py`

动作：
1. `stream_session_events()` 不再直接转发 runtime 原始 SSE 文本。
2. 统一输出已经语义化的消息事件（仅 user/assistant）与必要状态事件。

验收：
1. 前端不再收到原始 `event:/data:` chunk。
2. 事件类型精简后可直接渲染，不需要复杂分支解析。

---

## 改动 3（前端）：删除原始 SSE 解析器，仅渲染消息

文件：
- `frontend/src/components/SessionView.jsx`

动作：
1. 移除 `parseRuntimePayload()` 及围绕 `runtime_sse` 的复杂解析分支。
2. Chat 区域只渲染后端提供的 `user/assistant` 文本消息。
3. session 详情页与 `.md` 内容保持同一语义（都是“可读消息视图”）。

验收：
1. Chat 页面只显示用户和助手文本。
2. 不再显示 `status/context/message.updated/ping`。
3. 样式一致，不再出现“有些句子有样式、有些没有”。

---

## 不做的事（明确删除）

1. 不新增复杂标准消息对象层（先不引入 `client_msg_id` / 新 schema）。
2. 不做三阶段迁移工程。
3. 不改 task loop、账号切换等与本问题无关模块。
