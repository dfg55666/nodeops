# NodeOps Manager — 项目计划文档

> 日期：2026-05-09
> 状态：后端核心已落地（FastAPI + task loop + SSE + skills），联调与前端收口中

---

## 一、项目定位

NodeOps 多账号集中管控平台。管理多个 NodeOps 账号，跨账号调度 AI 施工任务，额度耗尽自动切号续跑。

**两个使用者：**
- **人**：通过 Web UI 管理项目、查看对话、浏览文件、手动操作
- **AI（Claude Code）**：通过 HTTP Skill API 创建任务、查询状态

---

## 二、核心功能

### 1. 账号管理
- 维护多个 NodeOps 账号（邮箱 + token）
- 追踪每个账号的额度状态（available / exhausted / disabled）
- 登录、token 刷新、OTP 验证等封装在账号模块内部，对外只暴露"给我一个可用账号"
- 账号锁定机制：被某个 task 占用时其他 task 不能用

### 2. 项目管理
- 一个 project = 一个 GitHub 仓库
- 一个 project 下可以有多个 task
- project 配置：名称、GitHub URL、描述

### 3. 任务循环系统（核心）
- 创建 task 时指定：所属 project、mode（auto/oneshot）、要发送的消息
- **auto 模式**：额度耗尽后自动执行 → 下载 workspace → git push → 切换账号 → 新会话 → 发送消息 → 继续
- **oneshot 模式**：额度耗尽后停止，等待人工处理
- 每轮会话记录保存为 .md 文件，commit 到仓库，新 AI 自己去仓库里读

### 4. 对话查看
- 实时查看当前会话的消息流（后端订阅 NodeOps SSE → 转发给前端）
- 历史会话记录查看（从 .md 文件读取）

### 5. Workspace 文件浏览
- 通过 NodeOps `/file` + `/file/content` API 浏览远程文件树
- 查看文件内容
- 下载整个 workspace

### 6. Skill API
- 给 Claude Code 调用的 HTTP 接口
- 创建任务、查询状态、取消任务等

---

## 三、技术栈

| 层 | 技术 | 说明 |
|----|------|------|
| 前端 | React + Vite | 开发模式直接跑，不构建 |
| 后端 | Python FastAPI | 异步，httpx 请求，uvicorn 运行 |
| 数据存储 | JSON + MD 文件 | 不用数据库 |
| Git 操作 | 直接调 git 命令 | SSH key 认证，机器已配好 |
| 实时通信 | SSE | 后端订阅 NodeOps SSE → 转发给前端 |

**不使用：** Docker、数据库、nginx、部署平台。源码直接本地运行。

---

## 四、数据存储结构

```
data/
├── config.json                       # 全局配置
├── accounts.json                     # 账号池
└── projects/
    └── my-blog/                      # 一个 project
        ├── project.json              # github_url, 描述等
        ├── repo/                     # git clone 下来的仓库
        │   ├── src/                  # 项目源码（从 workspace 覆盖）
        │   ├── .nodeops/             # 任务元数据目录（commit 到仓库）
        │   │   ├── task-001/
        │   │   │   ├── session-1.md  # 第1轮会话记录
        │   │   │   └── session-2.md  # 第2轮（切号后）
        │   │   └── task-002/
        │   │       └── session-1.md
        │   └── ...
        └── tasks/
            ├── task-001.json         # 任务配置（mode, status, message, 当前账号等）
            └── task-002.json
```

### accounts.json 结构
```json
[
  {
    "id": "uuid",
    "email": "acc1@gmail.com",
    "auth_token": "eyJ...",
    "token_expires_at": "2026-05-10T00:00:00Z",
    "deployment_id": "cc564a03-...",
    "runtime_host": "quizzical-gagarin5-343434.orak.nodeops.app",
    "project_token": "eyJ...",
    "credits_remaining": 850,
    "status": "available",
    "locked_by_task": null,
    "last_used_at": "2026-05-09T14:00:00Z"
  }
]
```

### task-001.json 结构
```json
{
  "id": "task-001",
  "project": "my-blog",
  "mode": "auto",
  "status": "running",
  "message": "克隆 https://github.com/user/blog\n阅读 .nodeops/task-001/ 下的历史记录\n继续完成博客系统的搭建",
  "current_account_id": "uuid",
  "current_session_id": "nodeops-session-uuid",
  "loop_count": 2,
  "max_loops": 10,
  "loops": [
    {
      "index": 1,
      "account_email": "acc1@gmail.com",
      "session_id": "...",
      "started_at": "...",
      "ended_at": "...",
      "end_reason": "credit_exhausted",
      "git_commit": "abc123"
    }
  ],
  "created_at": "...",
  "updated_at": "..."
}
```

### session-N.md 格式
```markdown
# Session 2 - Task 001
- Account: acc2@gmail.com
- Started: 2026-05-09 15:00
- Ended: 2026-05-09 15:42
- End Reason: credit_exhausted

## Messages

（SSE 消息流原样记录）
```

直接把 SSE 收到的消息缓存追加写入，不做额外处理。

---

## 五、前端布局

两栏布局：左侧项目树 + 右侧内容区。

```
┌──────────────────────┬────────────────────────────────────────────────────┐
│  项目树（280px）      │                                                    │
│                      │              右侧区域（按选中节点切换）               │
│  ▼ my-blog           │                                                    │
│    ▼ task-001 🟢     │  ┌──────────┬──────────┬──────────┐               │
│      ▼ acc1@gmail    │  │ 💬 对话   │ 📁 文件  │ ⚙ 设置   │               │
│        session-1 ✅  │  └──────────┴──────────┴──────────┘               │
│        session-2 ✅  │                                                    │
│      ▼ acc2@gmail    │  点 session → 对话记录                              │
│        session-3 🔄  │  点 task → 任务总览 + workspace 文件浏览             │
│    ▶ task-002 ⏸     │  点 project → 项目概览                              │
│  ▶ another-project   │                                                    │
│                      │                                                    │
│  ──────────────      │                                                    │
│  [+ 新建项目]         │                                                    │
│  [📋 账号管理]        │                                                    │
└──────────────────────┴────────────────────────────────────────────────────┘
```

底部状态栏：当前活跃任务数、总账号数、可用账号数。

---

## 六、后端架构

```
backend/
├── main.py                    # FastAPI + uvicorn 入口
├── requirements.txt
├── api/
│   ├── accounts.py            # 账号 CRUD
│   ├── projects.py            # 项目 CRUD
│   ├── tasks.py               # 任务管理（创建/启动/取消/状态查询）
│   ├── sessions.py            # 会话消息代理（查看当前/历史消息）
│   ├── files.py               # workspace 文件代理（文件树/内容）
│   ├── events.py              # SSE 转发给前端
│   └── skills.py              # Claude Code 调用的精简接口
├── services/
│   ├── nodeops_client.py      # NodeOps 四层 API 封装（核心）
│   ├── task_engine.py         # 任务循环引擎（状态机）
│   ├── account_pool.py        # 账号池（选号/锁定/释放）
│   ├── workspace_sync.py      # 下载 workspace 文件 + git push
│   ├── credit_monitor.py      # 额度监控（轮询 usage/credits）
│   └── session_recorder.py    # SSE 消息 → 追加写入 .md 文件
└── storage/
    └── file_store.py          # JSON/MD 文件读写工具
```

---

## 七、NodeOps API 封装（nodeops_client.py）

按 API 文档的四层架构封装：

### 认证层 — oneclick-backend.nodeops.xyz
- `login(email)` → POST /api/v1/login
- `verify_otp(email, code)` → POST /api/v1/login/verify → 返回 auth_token

### 积分层 — api-createos.nodeops.network
- `get_credits(auth_token)` → GET /v1/credits（有 500 重试）
- `get_topup_settings(auth_token)` → GET /v1/credits/openrouter/topup-settings
- `topup_credits(auth_token, payload)` → POST /v1/credits/openrouter

### 控制面 — stage-vibe-coder-api.nodeops.xyz
- `list_deployments(auth_token)` → GET /api/v1/deployments
- `create_deployment(auth_token)` → POST /api/v1/deployments/pi-agent
- `get_deployment(auth_token, id)` → GET /api/v1/deployments/{id} → runtime_host + project_token
- `get_usage(auth_token)` → GET /api/v1/usage

### Runtime 层 — 动态 host（*.orak.nodeops.app）
- `create_session(runtime_host, project_token, auth_token, opts)` → POST /session
- `list_sessions(runtime_host, project_token, auth_token)` → GET /session
- `send_message(runtime_host, project_token, auth_token, session_id, parts)` → POST /session/{id}/message
- `get_messages(runtime_host, project_token, auth_token, session_id)` → GET /session/{id}/message
- `abort_session(runtime_host, project_token, auth_token, session_id)` → POST /session/{id}/abort
- `connect_sse(runtime_host, token, session_id)` → GET /session/{id}/event?token=...
- `get_file_tree(runtime_host, project_token, auth_token, path)` → GET /file?path=...
- `get_file_content(runtime_host, project_token, auth_token, path)` → GET /file/content?path=...
- `get_file_status(runtime_host, project_token, auth_token)` → GET /file/status

Headers 规则：
- 控制面/积分层：`X-Auth-Token` + `ReferralURL: https://nodeops.network`
- Runtime 层：`x-project-token` + `y-gg-token`（y-gg-token 通常等于 auth_token）

---

## 八、任务循环引擎（task_engine.py）

### 状态机

```
pending → running → monitoring
                      │
                      ├─ AI 正常完成（无额度错误）→ syncing → pushing → completed
                      │
                      ├─ 额度耗尽（auto 模式）→ syncing → pushing → switching → running（下一轮）
                      │
                      ├─ 额度耗尽（oneshot 模式）→ blocked
                      │
                      ├─ 所有账号耗尽 → blocked_no_account
                      │
                      └─ 达到 max_loops → stopped
```

### 额度耗尽检测（多信号融合）
1. `GET /api/v1/usage` 轮询 → credits 为 0
2. 发消息返回错误码
3. SSE 连接异常断开 + credits 确认为 0

### "完成"判定
- AI 停止回复（一段时间无新消息） + 额度没有归零 = completed
- 不解析 AI 回复内容，纯靠状态判断

### 自动切换流程（auto 模式）
1. 检测到额度耗尽
2. 下载当前 workspace 所有文件 → 覆盖到 project/repo/ 目录
3. 保存当前 session 的消息记录到 .nodeops/task-xxx/session-N.md
4. git add + commit + push
5. 释放当前账号（标记 exhausted）
6. 从账号池获取下一个可用账号（排除已用的）
7. 确保新账号有 deployment（登录 + 创建部署）
8. 创建新会话
9. 发送用户预设的消息（原样发送，不做变量替换）
10. 回到 monitoring 状态

---

## 九、Skill API（给 Claude Code 调用）

```
POST /api/skills/task/create     创建并启动任务
  body: { project, mode, message, max_loops }
  resp: { task_id, status }

GET  /api/skills/task/status     查询任务状态
  query: task_id
  resp: { task_id, status, loop_count, current_account, ... }

GET  /api/skills/task/list       列出所有任务
  resp: [ { task_id, project, status, ... } ]

POST /api/skills/task/cancel     取消任务
  body: { task_id }

GET  /api/skills/project/list    列出所有项目
  resp: [ { name, github_url, task_count } ]

GET  /api/skills/file/tree       查看当前 workspace 文件树
  query: task_id, path
  resp: [ { name, type, size } ]
```

Claude Code 直接用 curl 调用这些接口。

---

## 十、Git 操作流程

- 认证方式：SSH key（机器已配好）
- 创建 project 时：`git clone {github_url} data/projects/{name}/repo/`
- 每轮结束时：
  1. workspace 文件下载覆盖到 `repo/` 目录
  2. session 记录写入 `repo/.nodeops/{task_id}/session-N.md`
  3. `git add -A && git commit -m "Loop N" && git push`
- 新 AI 自己在会话里克隆仓库、读 .nodeops/ 历史

---

## 十一、启动方式

```bash
# 一键启动
./start.sh

# 或者分别启动
cd backend && uvicorn main:app --host 0.0.0.0 --port 8000
cd frontend && npm run dev
```

前端 Vite dev server 代理 /api 到后端 8000 端口。

---

## 十二、不做的事情

- 不用 Docker
- 不用数据库
- 不做部署
- 不做用户认证（本地工具，单用户）
- 不做消息内容解析/摘要（AI 自己看历史文件）
- 不做变量替换（消息由用户手写）
- 不集成复杂的 GitHub API（直接 git 命令）
