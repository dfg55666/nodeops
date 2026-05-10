# capture_nodeops_fullchain_20260303_191220 抓包摘要

- 文件：`docs/nodeopus-reserve/capture/capture_nodeops_fullchain_20260303_191220.json`
- 时间（UTC）：`2026-03-03T11:06:49Z` ~ `2026-03-03T11:09:30Z`
- 请求总数：`47`
- 终止原因：`user_request`
- 抓包页：`https://createos.nodeops.network/?modal=login`

## 本次闭环范围

本次主要覆盖 **CreateOS 积分兑换链路**（未覆盖 deployment/session 消息链路）：

1. 查询当前 credits：`GET /v1/credits`
2. 查询 credit SKU：`GET /v1/skus/credit`
3. 查询兑换汇率：`GET /v1/payments/credit-conversion-rate`
4. 执行兑换：`POST /v1/credits/openrouter`，body `{"credits":1}`
5. 兑换后再次查询 credits：`GET /v1/credits`

## 关键域名

- `api-createos.nodeops.network`（积分/支付）
- `createos.nodeops.network`（前端 Next.js 页面与 chunks）

> 说明：本次抓包未出现 `stage-vibe-coder-api.nodeops.xyz` 与 `*.syra.nodeops.app` 的 runtime 消息请求。

## 关键请求细节

- 兑换请求：`POST https://api-createos.nodeops.network/v1/credits/openrouter`
  - Request body：`{"credits":1}`
  - Header：携带 `X-Auth-Token`
  - 响应示例：`{"status":"success","data":{"message":"credits added successfully","credits":1,"new_limit":5,"old_limit":4,"remaining":5}}`

- 汇率请求：`GET /v1/payments/credit-conversion-rate?...`
  - 响应示例：`{"usdPerCredit":0.01,"creditsPerUsd":100,"currency":"USD"}`

- Credits 查询：`GET /v1/credits`
  - 返回 `amount` 及 plan 中 `lifetimeCreditAmount / lifetimeDebitAmount / lifetimeTopupAmount` 等字段。

## 新下载的前端 JS（用于接口反查）

- 目录：`docs/nodeopus-reserve/js/latest_live_20260303`
- 脚本清单：`docs/nodeopus-reserve/js/latest_live_20260303/_script_urls.txt`
- 抽取接口字符串：`docs/nodeopus-reserve/js/latest_live_20260303/api_strings_extracted.json`

已从 JS 中抽到的核心 API base：

- `https://stage-vibe-coder-api.nodeops.xyz/api/v1`
- `https://api-createos.nodeops.network/v1`
- `https://oneclick-backend.nodeops.xyz/api`
- `https://openrouter.ai/api/v1`

已抽到的关键路径（节选）：

- `/v1/login`, `/v1/login/verify`
- `/deployments`, `/usage`, `/deployments/{id}/preview`
- `/session`, `/session/{id}/message`, `/session/{id}/abort`, `/provider`
- `/credits`, `/skus/credit`, `/payments/credit-conversion-rate`, `/credits/openrouter`
