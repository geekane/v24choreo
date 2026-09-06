# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

"X for Choreo" — a proxy/VPN deployment for the Choreo PaaS built around Cloudflare Argo Tunnel. It exposes vless/vmess/trojan/shadowsocks nodes (via a sing-box binary), an optional Nezha monitoring agent, and an optional ttyd web-SSH terminal, all fronted by Cloudflare. Originally by fscarmen2 ([Argo-X-Choreo](https://github.com/fscarmen2/Argo-X-Choreo)); this fork carries local build/deploy fixes.

The repo is intentionally declarative — almost all logic is shell/JS template generation rather than a compiled application. There are no tests and no lint step.

## Layout

- `files/` — everything copied into the container image (see Dockerfile).
  - `server.js` — the Node/Express control web app (the entry point, sets `ENTRYPOINT ["node", "server.js"]`).
  - `entrypoint.sh` — the core bootstrap. Generates the sing-box config, the Argo tunnel config + node-list exporter, and the PM2 ecosystem file, then launches PM2.
  - `web.js` — an ELF **binary**, not JavaScript despite the name. It is the sing-box/xray-like core proxy (`run -c /tmp/config.json`).
  - `nezha-agent`, `ttyd` — prebuilt static Go ELF binaries (Nezha monitoring client; ttyd web-terminal daemon).
  - `package.json` — Node deps for `server.js` only.
- `Dockerfile` — builds the image: copies `files/*` to `/home/choreouser`, installs `pm2` and `cloudflared`, runs as `choreouser` (uid 10001).
- `.trivyignore` — suppresses CVEs known to be compiled into the shipped Go binaries (`web.js`, `nezha-agent`) and unfixable without upgrading the Go toolchain. Add entries here rather than "fixing" those binaries.
- `scratch/` and the root `*.json`/`*.messages.json` files — untracked local scratch/debug output, not part of the deploy.

## Runtime flow

1. Docker runs `node server.js` → Express app starts on `$PORT` (default 3000) and immediately shells out to `bash entrypoint.sh`.
2. `entrypoint.sh`:
   - `generate_config` → writes `/tmp/config.json` (sing-box inbound ports 8080 vless-with-fallbacks; 3001 vless, 3002 vmess, 3003 trojan, 3004 shadowsocks, all WS on `/$WSPATH-<proto>`, loopback only). Includes a WARP wireguard outbound that routes `openai.com`/`ai.com` for ChatGPT unlocking.
   - `generate_argo` → writes `/tmp/argo.sh` + `/tmp/tunnel.yml` (maps `ARGO_DOMAIN`→8080, `WEB_DOMAIN`→3000, optional `SSH_DOMAIN`→2222). `argo.sh` also prints the export-ready node links (V2rayN / 小火箭 / Clash).
   - `generate_pm2_file` → writes `/tmp/ecosystem.config.js` and starts `web` (sing-box) and `argo` (cloudflared), plus `nezha` and `ttyd` apps if their env vars are set.
3. `server.js` serves status/diagnostics behind HTTP Basic auth, and reverse-proxies `/ssh` → ttyd (2222) and everything else → sing-box (8080).

## Environment variables (all consumed by `entrypoint.sh` / `server.js`)

| Var | Required | Default | Purpose |
|---|---|---|---|
| `ARGO_AUTH` | yes | — | Cloudflare Argo `TunnelSecret` JSON **or** a `cloudflared` token (`eyJ…` JWT / base64url). |
| `ARGO_DOMAIN` | yes | — | Argo tunnel hostname (proxy node traffic). |
| `WEB_DOMAIN` | yes | — | Hostname for the control/diagnostics web UI (→3000). |
| `UUID` | no | `de04add9-…` | Shared id/password for all proxies. |
| `WSPATH` | no | `argo` | WS path prefix (must not start with `/`). |
| `NEZHA_SERVER`/`NEZHA_PORT`/`NEZHA_KEY` | no | — | Nezha agent connection; all three must be set together. |
| `NEZHA_TLS` | no | — | Set to `1` to enable Nezha over TLS. |
| `SSH_DOMAIN` | no | — | Hostname for ttyd web-SSH (→2222); enables the ttyd PM2 app. |
| `WEB_USERNAME`/`WEB_PASSWORD` | no | `admin`/`password` | Basic-auth creds for the web UI and ttyd. |
| `PORT` | no | 3000 | Node app port (Choreo injects this). |

Web UI paths (Basic-auth protected): `/list` (node links), `/status` (`ps -ef`), `/listen` (`ss -nltp`), `/info` (OS/RAM), `/test` (read-only FS check).

## Key gotchas

- **`ARGO_AUTH` two modes.** `entrypoint.sh` branches on whether it contains `TunnelSecret` (JSON → `tunnel.yml` config mode) vs. a JWT/token (`--token` mode). Token mode is forced to `--protocol http2` because Choreo runs on Azure Kubernetes where UDP/7844 is blocked, breaking quic handshakes. Recent commits (9013e52, 67d79f9) tightened the JWT-detection regex and sanitization (stripping quotes/newlines/spaces) — keep both modes working when touching this.
- **The `web.js` file is a compiled binary.** Do not edit or "fix" it directly; it's sing-box, not Node source. Security scanners will flag it and `nezha-agent` — those CVEs belong in `.trivyignore`, not in source changes.
- **There are no tests / no build step to run locally.** Local verification is limited to reading/reviewing the shell and JS template generation. The Dockerfile references `npm install -r package.json` (non-standard but harmless); `package.json` still declares `start: node server.js`.
- **No lint config** exists for either JS or shell in this repo.
- Authenticated endpoints execute shell commands (`entrypoint.sh`, `ps -ef`, `ss -nltp`); they are behind Basic auth and are intended for a single operator, but treat any change to how these endpoints are reached as security-sensitive.

## Commands

No test/lint/build commands apply. To run the control app locally (for reviewing only — full functionality needs the binaries, Docker, and Argo credentials):

```sh
cd files && npm install && node server.js
```

Docker build (untested locally, requires the prebuilt binaries to already be valid for linux/amd64):

```sh
docker build -t x-for-choreo .
```