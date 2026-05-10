# Capture Summary: createos nodeops network (2026-02-16 12:21:20)

## File Location
- moved from: `C:\Users\22485\Downloads\mcp_chrome_network_capture_createos_nodeops_network_20260216_122120.json`
- moved to: `docs/nodeopus-reserve/capture/mcp_chrome_network_capture_createos_nodeops_network_20260216_122120.json`

## Quick Stats
- total requests: 102
- hosts:
  - `createos.nodeops.network`: 89
  - `api-createos.nodeops.network`: 13

## Turnstile/Captcha Check
- searched fields: `url`, `requestBody`, `responseBody`, `specificRequestHeaders`, `specificResponseHeaders`
- keywords: `turnstile`, `cf-turnstile`, `captcha`, `challenges.cloudflare.com`
- result: **no matches found**

## Registration-Stage Signal Check
- this capture does not include explicit signup/login OTP API calls (for example `/v1/auth/*`, `/login`, `/verify-otp`, `/register`).
- observed API calls are mainly:
  - `GET /v1/credits`
  - `GET /v1/skus/credit`
  - `GET /v1/payments/credit-conversion-rate`
  - `GET /v1/app-installations/github/installations`
- several requests include `X-Auth-Token` header (already authenticated session behavior), but no turnstile-related payload fields were observed.

## Conclusion
- in this capture, there is **no turnstile token field**.
- for registration-stage turnstile verification, a new capture must start before clicking `Login`/`Continue with Email` and include the full OTP flow.
