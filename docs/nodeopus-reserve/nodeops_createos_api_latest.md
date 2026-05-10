# NodeOps CreateOS 最新接口文档（唯一维护）

更新时间：2026-05-10  
文档定位：本文件作为 `nodeopus-reserve` 下唯一维护的最新版接口文档。

---

## 1. 数据来源与覆盖范围

- 抓包文件：`network_capture_stop_auto_2026-05-08T15-39-39-128Z.json`
- 抓包摘要：`network_capture_stop_auto_2026-05-08T15-39-39-128Z.summary.md`
- 增量抓包文件：`network_capture_stop_auto_2026-05-10T01-38-32-469Z.json`
- 增量抓包摘要：`network_capture_stop_auto_2026-05-10T01-38-32-469Z.summary.md`
- 请求总数：1561
- 采集页面：`https://createos.nodeops.network/`
- 本次用户操作覆盖：
  1. 注册/登录（邮箱 OTP）
  2. 兑换积分
  3. 创建/进入 agent 会话并发消息、收消息
  4. 浏览 workspace 文件
  5. 点击打包下载

补充静态分析（用于补齐请求体结构/前端下载逻辑）：

- `js/latest_live_20260508_from_capture/_next/static/chunks/1140-a119cc3ed840198c.js`
- `js/latest_live_20260508_from_capture/_next/static/chunks/9073-6adb4d0888767376.js`
- `js/latest_live_20260508_from_capture/_next/static/chunks/app/chat/c/%5BsessionId%5D/page-b4e39201552430cb.js`

---

## 2. 分层架构（2026-05-08 实测）

### 2.1 认证层（OTP）

- Host: `oneclick-backend.nodeops.xyz`
- Base: `https://oneclick-backend.nodeops.xyz/api`
- 关键接口：
  - `POST /v1/login`
  - `POST /v1/login/verify`

### 2.2 账户积分层

- Host: `api-createos.nodeops.network`
- Base: `https://api-createos.nodeops.network/v1`
- 关键接口：
  - `GET /credits`
  - `GET /skus/credit`
  - `GET /payments/credit-conversion-rate`
  - `GET /credits/openrouter/topup-settings`
  - `POST /credits/openrouter`

### 2.3 控制面（部署/额度轮询）

- Host: `stage-vibe-coder-api.nodeops.xyz`
- Base: `https://stage-vibe-coder-api.nodeops.xyz/api/v1`
- 关键接口：
  - `GET /deployments`
  - `POST /deployments/pi-agent`
  - `GET /deployments/{deploymentId}`
  - `GET /usage`（高频）

### 2.4 Runtime（会话、消息、文件）

- Host（本次动态）：`quizzical-gagarin5-343434.orak.nodeops.app`
- 说明：runtime host 是动态分配，不能硬编码。
- 关键接口：
  - `GET|POST /session`
  - `GET|POST /session/{sessionId}/message`
  - `GET /session/{sessionId}/event?token=...`（SSE）
  - `GET /session/{sessionId}/context`
  - `GET /session/{sessionId}/subagents`
  - `POST /session/{sessionId}/abort`（JS 中确认，抓包本轮未触发）
  - `GET /file?path=...`
  - `GET /file/content?path=...`
  - `GET /file/status`
  - `GET /health`（JS 中确认）
  - `POST /preview` body `{"port":8080}`（JS 中确认）

---

## 3. 鉴权与关键 Header（原样样本）

### 3.1 X-Auth-Token（控制面 / 积分层）

实测样本（来自 `POST /v1/credits/openrouter` 与 `POST /api/v1/deployments/pi-agent`）：

```http
X-Auth-Token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdWQiOiJmZWlqaWRmZzU1K2J1MHd6YkBnbWFpbC5jb20iLCJleHAiOjE3Nzg0MjY3OTcsImlhdCI6MTc3ODI1Mzk5Nywic3ViIjoiNDkxZDI1ZWItYzExNC00NTliLWExYzYtOWE1MWU5ODE2NDkxIn0.b9P38I9nRoyMpYHRPCM87y4CTlrjOzkjSXkCj0JzZ5Q
ReferralURL: https://nodeops.network
Content-Type: application/json
```

### 3.2 Runtime 双 token 头

实测样本（来自 `POST /session/{id}/message`）：

```http
x-project-token: eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiNDkxZDI1ZWItYzExNC00NTliLWExYzYtOWE1MWU5ODE2NDkxIiwiZGVwbG95bWVudF9pZCI6ImNjNTY0YTAzLTc5ZWEtNDE5NC05ZDc5LTI2Yzk2NTMzMjVmOSIsImlzcyI6InZpYmUtY29kZXItYmUiLCJhdWQiOiJjYzU2NGEwMy03OWVhLTQxOTQtOWQ3OS0yNmM5NjUzMzI1ZjkiLCJleHAiOjE3ODA4NDYwNzUsImlhdCI6MTc3ODI1NDA3NSwibmJmIjoxNzc4MjU0MDc1LCJqdGkiOiJjMGNlNjM5OC1lMmYwLTQ3YzQtYjQ3OS1iOGUxNGE2NTc0MWYifQ.v6F1BXnW5vBJ0zOgquYnXhRdNRsTmj_1t3s5jLrvuY-guwtwZrIBfqXmrJMQMxazB489mcFqf4_M3hhVZBktdQ
y-gg-token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdWQiOiJmZWlqaWRmZzU1K2J1MHd6YkBnbWFpbC5jb20iLCJleHAiOjE3Nzg0MjY3OTcsImlhdCI6MTc3ODI1Mzk5Nywic3ViIjoiNDkxZDI1ZWItYzExNC00NTliLWExYzYtOWE1MWU5ODE2NDkxIn0.b9P38I9nRoyMpYHRPCM87y4CTlrjOzkjSXkCj0JzZ5Q
Content-Type: application/json
```

注意：`POST /session` 的一次样本里，`y-gg-token` 与 `x-project-token` 相同；而消息/文件请求中 `y-gg-token` 实测是用户 JWT。后端兼容时建议按页面行为保留两者。

### 3.3 SSE 样本

```http
GET /session/0462a773-3ccd-4fc1-a7e4-c1fd8f920581/event?token=eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9...BktdQ
Accept: text/event-stream
Cache-Control: no-cache
```

---

## 4. 关键链路时间线（本地时区）

- `2026-05-08 23:24:55` 触发 `POST /api/v1/login`
- `2026-05-08 23:25:30` 触发 `POST /api/v1/login/verify`
- `2026-05-08 23:26:54` 触发 `POST /v1/credits/openrouter`
- `2026-05-08 23:27:44` 触发 `POST /api/v1/deployments/pi-agent`
- `2026-05-08 23:27:53` 触发 `POST /session`
- `2026-05-08 23:27:56` 触发 `POST /session/{id}/message`
- `2026-05-08 23:27:56 ~ 23:35:06` 触发 `GET /session/{id}/message` 拉消息
- `2026-05-08 23:27:55 ~ 23:37:54` `GET /file?path=...` 拉目录
- `2026-05-08 23:27:56 ~ 23:37:55` `GET /file/content?path=...` 拉文件内容（用于浏览/打包下载）

---

## 5. 接口矩阵（按实测请求统计）

> 统计口径：当前抓包文件内 Method + Path + Status 计数。

### 5.1 认证

- `/api/v1/login`：`POST 200 x2`，`OPTIONS 204 x2`
- `/api/v1/login/verify`：`POST 200 x2`，`OPTIONS 204 x2`

### 5.2 积分

- `/v1/credits`：`GET 500 x3`，`GET 200 x2`，`OPTIONS 204 x3`
- `/v1/skus/credit`：`GET 200 x2`，`OPTIONS 204 x2`
- `/v1/payments/credit-conversion-rate`：`GET 200 x3`，`OPTIONS 204 x3`
- `/v1/credits/openrouter`：`POST 200 x1`，`OPTIONS 204 x1`
- `/v1/credits/openrouter/topup-settings`：`GET 200 x2`，`OPTIONS 204 x2`

### 5.3 控制面

- `/api/v1/deployments`：`GET 200 x2`，`OPTIONS 204 x2`
- `/api/v1/deployments/pi-agent`：`POST 201 x1`，`OPTIONS 204 x1`
- `/api/v1/deployments/{id}`：`GET 200 x1`，`OPTIONS 204 x1`
- `/api/v1/usage`：`GET 200 x71`，`OPTIONS 204 x69`

### 5.4 Runtime 会话/消息

- `/session`：`POST 200 x1`，`GET 200 x1`，`OPTIONS 200 x1`
- `/session/{id}/message`：`POST 200 x2`，`GET 200 x46`，`OPTIONS 200 x48`
- `/session/{id}/event`：`GET 200 x1`
- `/session/{id}/context`：`GET 200 x1`，`OPTIONS 200 x1`
- `/session/{id}/subagents`：`GET 200 x1`，`OPTIONS 200 x1`

### 5.5 Runtime 文件

- `/file`：`GET 200 x65`，`OPTIONS 200 x63`
- `/file/content`：`GET 200 x223`，`OPTIONS 200 x221`
- `/file/status`：`GET 200 x32`，`OPTIONS 200 x32`

---

## 6. 请求体结构（由前端 JS 静态反查）

抓包本身对 request body 显示为 `[Binary data]`，故 body 结构来自 chunk 代码。

### 6.0 创建部署（2026-05-10 增量确认）

`POST /api/v1/deployments/pi-agent`

```json
{
  "prompt": "init"
}
```

说明：2026-05-10 实测中，对该接口发送 `{}` 会返回 `400` 且提示 `prompt is required`。  
后端必须带 `prompt`，否则会回退到旧 `/deployments` 链路，容易出现 runtime/token 不一致问题。

### 6.1 创建会话

`POST /session`

```json
{
  "title": "optional",
  "model": "optional"
}
```

### 6.2 发送消息

`POST /session/{sessionId}/message`

```json
{
  "parts": [
    { "type": "text", "text": "..." },
    { "type": "file", "mime": "image/png", "url": "data:image/png;base64,...." }
  ],
  "noReply": false,
  "system": "optional",
  "model": "optional",
  "agent": "optional"
}
```

---

## 7. “打包下载 workspace”真实机制（已确认）

结论：当前不是后端直接返回 zip；而是前端递归拉取目录与文件内容后，浏览器端 JSZip 打包下载。

证据（`page-b4e39201552430cb.js`）：

- `generateAsync({type:"blob"})`
- `s.download=\`${t||"project"}-${Date.now()}.zip\``
- 若 JSZip 不可用，fallback 为逐文件下载（`downloading files individually`）

抓包侧证据：

- `/file?path=` 与 `/file/content?path=...` 大量请求
- `file/content` GET 共 223 次，unique path 约 206 个
- 目录递归明显（`share/Sbird-ui/...` 深层路径被逐个读取）

---

## 8. 与旧链路的关键变化（必须注意）

1. runtime 域名从历史 `*.syra.nodeops.app` 迁移为本次 `*.orak.nodeops.app`。  
2. 控制面创建部署接口本次是 `POST /api/v1/deployments/pi-agent`（状态 201）。  
3. 文件“打包下载”当前前端本地组包，不是单一 `download zip` API。  
4. `y-gg-token` 行为不是固定值：会随调用路径在 “project token / user token” 间出现差异。  
5. `GET /v1/credits` 有间歇性 `500`，后续可恢复 `200`，调用方要做重试。  

---

## 9. 对接实现建议（面向你后续 HTTP 后端 + CLI）

### 9.1 最小调用闭环

1. OTP 登录：`/login` -> `/login/verify`，拿 `X-Auth-Token`
2. 创建部署：`POST /deployments/pi-agent`，随后 `GET /deployments/{id}` 取 runtime 信息
3. runtime 建会话：`POST /session`
4. 发消息：`POST /session/{id}/message`
5. 拉消息：`GET /session/{id}/message`
6. 文件树：`GET /file?path=`
7. 文件内容：`GET /file/content?path=...`
8. 整仓下载：递归 `file` + `file/content` 后本地打 zip（与前端一致）

### 9.2 对应你定义的工具

- `task.create(mode, prompt)`：封装登录/建部署/建会话/首条消息发送
- `message.pull`：拉取 `/session/{id}/message`；可加 SSE 旁路
- `file.tree`：调用 `/file?path=...`
- `file.download`：调用 `/file/content?path=...`
- `file.download_workspace`：递归 tree + content 后本地 zip

### 9.3 重试与轮询策略（建议）

- `GET /v1/credits`：500 时指数退避重试
- `GET /api/v1/usage`：5~10 秒轮询即可，不要贴前端频率
- `GET /session/{id}/message`：2~5 秒轮询；检测到 assistant 完成态后停止
- `OPTIONS` 预检在服务端直连时通常可省略（浏览器场景才需要）

---

## 10. 待补采集项（下一轮若要继续补全）

1. 用 debugger backend 抓带 body 的版本（`needResponseBody=true`）  
2. 明确 `POST /deployments/pi-agent` 完整请求体字段  
3. 明确 `GET /deployments/{id}` 返回中 runtime endpoint/token 字段名  
4. 覆盖 `POST /session/{id}/abort` 实际请求与响应样本  
