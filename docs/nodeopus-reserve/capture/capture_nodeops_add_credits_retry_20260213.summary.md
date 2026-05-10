# Network Capture Summary

- JSON: E:\Program Files (x86)\Visual Studio\project\dev\deepseek\orchids2api-main\docs\nodeopus-reserve\capture\capture_nodeops_add_credits_retry_20260213.json
- Summary: E:\Program Files (x86)\Visual Studio\project\dev\deepseek\orchids2api-main\docs\nodeopus-reserve\capture\capture_nodeops_add_credits_retry_20260213.summary.md
- GeneratedAt: 2026-02-13T01:32:34.382Z
- Backend: debugger
- Tab: Create - AI-Assisted App Builder with MCP Integration | CreateOS https://createos.nodeops.network/create
- RequestCount: 14
- Settings: {"maxCaptureTime":900000,"inactivityTimeout":0,"includeStatic":false,"urlInclude":[],"urlExclude":[],"bodyUrlInclude":[],"bodyUrlExclude":[],"disableCache":true,"maxRequests":100}

## Requests (preview 14/14)

### 1. POST https://createos.nodeops.network/cdn-cgi/rum?
- Meta: status=204 type=XHR mime=text/plain
- requestBody: 470 chars (truncated)

```
{"resources":[],"referrer":"https://createos.nodeops.network/","eventType":1,"firstPaint":468,"firstContentfulPaint":468,"startTime":1770946245746,"versions":{"fl":"2024.11.0","js":"2024.6.1","timings":1},"pageloadId":"32362e58-9fbd-4b8c-a3f0-f8c5a2c79f30","location":"https://createos.nodeops.network/create","nt":"navigate","timingsV2":{"nextHopProtocol":"h2","transferSize":13904,"decodedBodySize"…
```

### 2. POST https://createos.nodeops.network/cdn-cgi/zaraz/t
- Meta: status=200 type=Fetch mime=application/json
- requestBody: 601 chars (truncated)

```
{"name":"visibilityChange","data":{"__zcl_track":true,"__zcl_visibilityChange":true,"__zarazMCListeners":{"google-analytics_v4_fJTO":["visibilityChange"]},"visibilityChange":[{"state":"hidden","timestamp":1770946325380}],"__zarazClientEvent":true},"zarazData":{"executed":["Pageview","Pageview","Pageview","Pageview","Pageview"],"t":"Create - AI-Assisted App Builder with MCP Integration | CreateOS",…
```
- responseBody: 160 chars

```
{"e":["(function(w,d){{(function(w,d){zaraz.__zarazMCListeners={\"google-analytics_v4_fJTO\":[\"visibilityChange\"]};})(window,document);}})(window,document)"]}
```

### 3. POST https://createos.nodeops.network/cdn-cgi/zaraz/t
- Meta: status=200 type=Fetch mime=application/json
- requestBody: 602 chars (truncated)

```
{"name":"visibilityChange","data":{"__zcl_track":true,"__zcl_visibilityChange":true,"__zarazMCListeners":{"google-analytics_v4_fJTO":["visibilityChange"]},"visibilityChange":[{"state":"visible","timestamp":1770946329881}],"__zarazClientEvent":true},"zarazData":{"executed":["Pageview","Pageview","Pageview","Pageview","Pageview"],"t":"Create - AI-Assisted App Builder with MCP Integration | CreateOS"…
```
- responseBody: 160 chars

```
{"e":["(function(w,d){{(function(w,d){zaraz.__zarazMCListeners={\"google-analytics_v4_fJTO\":[\"visibilityChange\"]};})(window,document);}})(window,document)"]}
```

### 4. POST https://createos.nodeops.network/cdn-cgi/zaraz/t
- Meta: status=200 type=Fetch mime=application/json
- requestBody: 601 chars (truncated)

```
{"name":"visibilityChange","data":{"__zcl_track":true,"__zcl_visibilityChange":true,"__zarazMCListeners":{"google-analytics_v4_fJTO":["visibilityChange"]},"visibilityChange":[{"state":"hidden","timestamp":1770946333410}],"__zarazClientEvent":true},"zarazData":{"executed":["Pageview","Pageview","Pageview","Pageview","Pageview"],"t":"Create - AI-Assisted App Builder with MCP Integration | CreateOS",…
```
- responseBody: 333 chars

```
{"f":[["https://stats.g.doubleclick.net/g/collect?t=dc&aip=1&_r=3&v=1&_v=j86&tid=G-PQYEVJHKCE&cid=77529dd0-d609-45ef-a4b6-e688a4e06e22&_u=KGDAAEADQAAAAC%7E&z=521349152",{}]],"e":["(function(w,d){{(function(w,d){zaraz.__zarazMCListeners={\"google-analytics_v4_fJTO\":[\"visibilityChange\"]};})(window,document);}})(window,document)"]}
```

### 5. POST https://createos.nodeops.network/cdn-cgi/zaraz/t
- Meta: status=200 type=Fetch mime=application/json
- requestBody: 602 chars (truncated)

```
{"name":"visibilityChange","data":{"__zcl_track":true,"__zcl_visibilityChange":true,"__zarazMCListeners":{"google-analytics_v4_fJTO":["visibilityChange"]},"visibilityChange":[{"state":"visible","timestamp":1770946337085}],"__zarazClientEvent":true},"zarazData":{"executed":["Pageview","Pageview","Pageview","Pageview","Pageview"],"t":"Create - AI-Assisted App Builder with MCP Integration | CreateOS"…
```
- responseBody: 160 chars

```
{"e":["(function(w,d){{(function(w,d){zaraz.__zarazMCListeners={\"google-analytics_v4_fJTO\":[\"visibilityChange\"]};})(window,document);}})(window,document)"]}
```

### 6. GET https://api-createos.nodeops.network/v1/skus/credit
- Meta: status=200 type=XHR mime=application/json
- responseBody: 263 chars

```
{"status":"success","data":[{"sku":{"id":"00000000-0000-0000-0000-000000000007","productName":"credit","name":"credits","description":"credits","category":"ONE_TIME","metadata":null,"createdAt":"2026-01-30T06:27:04.317Z","updatedAt":"2026-01-30T06:27:04.317Z"}}]}
```

### 7. GET https://api-createos.nodeops.network/v1/payments/credit-conversion-rate?skuId=00000000-0000-0000-0000-000000000007&creditMultiplier=1&amount=1&paymentMethod=checkout
- Meta: status=200 type=XHR mime=application/json
- responseBody: 86 chars

```
{"status":"success","data":{"usdPerCredit":0.01,"creditsPerUsd":100,"currency":"USD"}}
```

### 8. OPTIONS https://api-createos.nodeops.network/v1/skus/credit
- Meta: status=204 type=Preflight
- errorText: Failed to get body: {"code":-32000,"message":"No resource with given identifier found"}

### 9. OPTIONS https://api-createos.nodeops.network/v1/payments/credit-conversion-rate?skuId=00000000-0000-0000-0000-000000000007&creditMultiplier=1&amount=1&paymentMethod=checkout
- Meta: status=204 type=Preflight
- errorText: Failed to get body: {"code":-32000,"message":"No resource with given identifier found"}

### 10. POST https://api-createos.nodeops.network/v1/credits/openrouter
- Meta: status=200 type=XHR mime=application/json
- requestBody: 13 chars

```
{"credits":1}
```
- responseBody: 129 chars

```
{"status":"success","data":{"credits":1,"message":"credits added successfully","new_limit":2,"old_limit":1,"remaining":1.557341}}
```

### 11. OPTIONS https://api-createos.nodeops.network/v1/credits/openrouter
- Meta: status=204 type=Preflight
- errorText: Failed to get body: {"code":-32000,"message":"No resource with given identifier found"}

### 12. GET https://stage-vibe-coder-api.nodeops.xyz/api/v1/usage
- Meta: status=200 type=XHR mime=application/json
- responseBody: 571 chars (truncated)

```
{"status":"success","data":{"hash":"7364a2ab247ac8f454dc534c3fbadd2edb87390c9a10522a6e8f3ae107e619bf","name":"autogen-user-a3b0b850-eac4-4284-932e-3476cdcb0bc5","label":"sk-or-v1-ff9...ecc","disabled":false,"limit":2,"limit_remaining":1.557341,"limit_reset":null,"include_byok_in_limit":false,"usage":0.442659,"usage_daily":0,"usage_weekly":0.442659,"usage_monthly":0.442659,"byok_usage":0,"byok_usag…
```

### 13. OPTIONS https://stage-vibe-coder-api.nodeops.xyz/api/v1/usage
- Meta: status=204 type=Preflight
- errorText: Failed to get body: {"code":-32000,"message":"No resource with given identifier found"}

### 14. POST https://createos.nodeops.network/cdn-cgi/zaraz/t
- Meta: status=200 type=Fetch mime=application/json
- requestBody: 601 chars (truncated)

```
{"name":"visibilityChange","data":{"__zcl_track":true,"__zcl_visibilityChange":true,"__zarazMCListeners":{"google-analytics_v4_fJTO":["visibilityChange"]},"visibilityChange":[{"state":"hidden","timestamp":1770946346699}],"__zarazClientEvent":true},"zarazData":{"executed":["Pageview","Pageview","Pageview","Pageview","Pageview"],"t":"Create - AI-Assisted App Builder with MCP Integration | CreateOS",…
```
- responseBody: 333 chars

```
{"f":[["https://stats.g.doubleclick.net/g/collect?t=dc&aip=1&_r=3&v=1&_v=j86&tid=G-PQYEVJHKCE&cid=77529dd0-d609-45ef-a4b6-e688a4e06e22&_u=KGDAAEADQAAAAC%7E&z=624307495",{}]],"e":["(function(w,d){{(function(w,d){zaraz.__zarazMCListeners={\"google-analytics_v4_fJTO\":[\"visibilityChange\"]};})(window,document);}})(window,document)"]}
```
