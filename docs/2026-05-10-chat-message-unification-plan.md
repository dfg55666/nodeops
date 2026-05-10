# Chat 消息统一化改造计划

> 日期：2026-05-10  
> 状态：Plan Draft（待执行）

---

## 1. 目标

把 NodeOps 会话链路统一成“后端解析、前端只展示消息文本”的模式，解决以下问题：

1. Chat 页面混入 SSE 控制事件（`status/context/message.updated`）导致样式混乱。
2. Session 文档混入原始 SSE 块，既不利于人读，也不利于 AI 续跑读取。
3. 用户消息偶发重复展示（同一条消息出现两次）。

---

## 2. 改造范围

### In Scope

1. 后端：SSE 事件解析、消息去重、消息持久化格式统一。
2. 前端：只消费“标准消息结构”，不再本地解析原始 SSE。
3. 会话文件：仅保存 `User/Assistant` 可读消息，不再保存 raw SSE。
4. 历史读取：兼容已有旧文件（只读兼容），新文件按新格式写入。

### Out of Scope

1. 模型策略、任务调度策略、账号注册流程。
2. 文件同步 / Git push 逻辑。
3. 上游 NodeOps 协议本身的变更。

---

## 3. 目标数据模型（单一真相源）

后端统一输出并存储：

```json
{
  "id": "msg_xxx",
  "session_id": "xxx",
  "role": "user|assistant",
  "content": "plain text",
  "created_at": "ISO8601",
  "status": "streaming|final",
  "client_msg_id": "optional"
}
```

约束：

1. 仅 `user/assistant` 两类消息对外可见。
2. `status/context/message.updated/message.part.updated/ping` 不入库、不出现在 UI。
3. 同一条用户消息以 `client_msg_id` 做幂等去重。

---

## 4. 实施步骤

## 阶段 A：后端解析器下沉（优先）

1. 在 `backend/services/task_engine.py` 的 SSE 消费路径中，新增“事件白名单 + 聚合器”：
   - 只产出 `user/assistant` 消息。
   - assistant 流式分片在后端聚合为单条最终消息（`final`）。
2. 在 `backend/services/session_recorder.py` 新增统一写入接口：
   - `append_user_message(...)`
   - `append_assistant_message(...)`
   - 移除/停用 raw SSE 写入调用点。
3. 在 `backend/api/sessions.py` / `backend/api/events.py` 对外只返回标准消息结构。

## 阶段 B：前端消费收敛

1. `frontend/src/components/SessionView.jsx` 删除 SSE 原始块渲染分支。
2. Chat 面板只渲染后端返回的标准消息数组。
3. 发送动作带 `client_msg_id`，避免前端 optimistic + 回读重复显示。

## 阶段 C：历史兼容与迁移

1. 旧会话文件读取时做“尽力提取 user/assistant 文本”兼容。
2. 新写入统一使用新格式，不再写老式 raw 片段。
3. 提供一次性可选脚本：将旧会话重写为纯消息格式（非强制）。

---

## 5. API 约定（改造后）

1. `POST /api/.../send`  
   - 入参支持：`content`, `model`, `client_msg_id`
   - 返回：ack + user message id

2. `GET /api/tasks/{...}/messages` 或 `GET /api/sessions/{...}`  
   - 返回：标准消息列表（无 raw SSE）

3. SSE（若保留）  
   - 仅推送标准消息增量，不推送上游原始 event 文本。

---

## 6. 验收标准

1. Chat 页面仅显示用户与助手最终文本，不出现 `status/context/message.updated`。
2. Session 文档只包含可读对话，不含 raw SSE 块。
3. 同一条用户发送不再重复出现两次。
4. 任务 loop 和手动会话两条链路行为一致。
5. 旧会话仍可读（允许“部分兼容”），新会话格式统一。

---

## 7. 风险与对策

1. **风险：** 上游 SSE 事件格式漂移  
   **对策：** 解析器按 schema 容错，未知事件直接忽略，不污染消息流。

2. **风险：** 流式内容聚合错误导致助手文本截断  
   **对策：** 引入 `message_id` 维度聚合 + 超时 flush + 单测覆盖。

3. **风险：** 前后端并行改造造成短期不兼容  
   **对策：** 后端先兼容旧前端字段，再切前端，最后清理兼容代码。

---

## 8. 执行顺序建议

1. 先改后端（解析、存储、接口）。
2. 再改前端（仅消费标准消息）。
3. 最后做旧格式兼容清理与回归测试。

---

## 9. 关键文件清单

1. `backend/services/task_engine.py`
2. `backend/services/session_recorder.py`
3. `backend/api/events.py`
4. `backend/api/sessions.py`
5. `frontend/src/components/SessionView.jsx`
6. `frontend/src/api.js`

