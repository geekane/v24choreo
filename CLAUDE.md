# CLAUDE.md

本文件为 Claude Code（claude.ai/code）在本仓库中工作提供指引。

## 项目是什么

「X for Choreo」—— 一个基于 Cloudflare Argo Tunnel、部署在 Choreo PaaS 上的代理/VPN 项目。它通过一个 sing-box 二进制暴露 vless/vmess/trojan/shadowsocks 节点，可选用哪吒（Nezha）监控探针，以及可选的 ttyd 网页 SSH 终端，所有流量都由 Cloudflare 前置。原作者为 fscarmen2（[Argo-X-Choreo](https://github.com/fscarmen2/Argo-X-Choreo)）；本仓库（fork）带有本地构建/部署相关的修复。

本仓库刻意采用声明式写法——几乎全部逻辑都是 shell / JS 模板生成，而非一个需要编译的应用程序。没有测试，也没有 lint 步骤。

## 目录结构

- `files/` —— 被拷贝进镜像的全部内容（见 Dockerfile）。
  - `server.js` —— Node/Express 控制面板网页应用（入口点，在 Dockerfile 中设为 `ENTRYPOINT ["node", "server.js"]`）。
  - `entrypoint.sh` —— 核心引导脚本。生成 sing-box 配置、Argo 隧道配置 + 节点导出脚本、PM2 ecosystem 配置文件，然后启动 PM2。
  - `web.js` —— 一个 ELF **二进制文件**，并非 JavaScript（虽然名字像）。它是 sing-box/xray 风格的核心代理（`run -c /tmp/config.json`）。
  - `nezha-agent`、`ttyd` —— 预编译的静态 Go ELF 二进制（哪吒监控客户端；ttyd 网页终端守护进程）。
  - `package.json` —— 仅为 `server.js` 声明的 Node 依赖。
- `Dockerfile` —— 构建镜像：把 `files/*` 拷贝到 `/home/choreouser`，安装 `pm2` 与 `cloudflared`，以 `choreouser`（uid 10001）运行。
- `.trivyignore` —— 忽略那些已知被编译进随包分发的 Go 二进制（`web.js`、`nezha-agent`）且在不升级 Go 工具链前提下无法修复的 CVE。应在此处添加条目，而不是去「修复」那些二进制。
- `scratch/` 以及根目录的 `*.json` / `*.messages.json` —— 未跟踪的本地 scratch / 调试产物，不属于部署内容。

## 运行时流程

1. Docker 运行 `node server.js` → Express 应用在 `$PORT`（默认 3000）上启动，并立即调用 `bash entrypoint.sh`。
2. `entrypoint.sh`：
   - `generate_config` → 写入 `/tmp/config.json`（sing-box 入站端口：8080 为带 fallback 的 vless；3001 vless、3002 vmess、3003 trojan、3004 shadowsocks，全部为 WS、路径 `/$WSPATH-<proto>`、仅回环）。包含一个 WARP wireguard 出站，将 `openai.com`/`ai.com` 路由到 WARP 以解锁 ChatGPT。
   - `generate_argo` → 写入 `/tmp/argo.sh` + `/tmp/tunnel.yml`（映射 `ARGO_DOMAIN`→8080、`WEB_DOMAIN`→3000，可选 `SSH_DOMAIN`→2222）。`argo.sh` 同时打印导出用的节点链接（V2rayN / 小火箭 / Clash）。
   - `generate_pm2_file` → 写入 `/tmp/ecosystem.config.js` 并启动 `web`（sing-box）与 `argo`（cloudflared）应用；若设置了相应的环境变量，还会追加 `nezha` 与 `ttyd` 应用。
3. `server.js` 在 HTTP Basic 认证之后提供状态/诊断服务，并将 `/ssh` 反向代理到 ttyd（2222），其余请求反向代理到 sing-box（8080）。

## 环境变量（均由 `entrypoint.sh` / `server.js` 消费）

| 变量 | 必填 | 默认值 | 用途 |
|---|---|---|---|
| `ARGO_AUTH` | 是 | — | Cloudflare Argo 的 `TunnelSecret` JSON **或** `cloudflared` token（`eyJ…` JWT / base64url）。 |
| `ARGO_DOMAIN` | 是 | — | Argo 隧道主机名（代理节点流量）。 |
| `WEB_DOMAIN` | 是 | — | 控制/诊断网页 UI 的主机名（→3000）。 |
| `UUID` | 否 | `de04add9-…` | 各协议共用的 id / 密码。 |
| `WSPATH` | 否 | `argo` | WS 路径前缀（不能以 `/` 开头）。 |
| `NEZHA_SERVER`/`NEZHA_PORT`/`NEZHA_KEY` | 否 | — | 哪吒探针连接；三者必须同时设置。 |
| `NEZHA_TLS` | 否 | — | 设为 `1` 以启用哪吒的 TLS。 |
| `SSH_DOMAIN` | 否 | — | ttyd 网页 SSH 的主机名（→2222）；启用 ttyd 的 PM2 应用。 |
| `WEB_USERNAME`/`WEB_PASSWORD` | 否 | `admin`/`password` | 网页 UI 与 ttyd 的 Basic 认证凭据。 |
| `PORT` | 否 | 3000 | Node 应用端口（由 Choreo 注入）。 |

网页 UI 路径（受 Basic 认证保护）：`/list`（节点链接）、`/status`（`ps -ef`）、`/listen`（`ss -nltp`）、`/info`（系统/内存）、`/test`（只读文件系统检测）。

## 关键注意事项

- **`ARGO_AUTH` 有两种模式。** `entrypoint.sh` 根据是否包含 `TunnelSecret` 来分支：JSON → `tunnel.yml` 配置模式；JWT/token → `--token` 模式。token 模式被强制为 `--protocol http2`，因为 Choreo 运行在 Azure Kubernetes 上，UDP/7844 被阻断会导致 quic 握手超时。近期提交（9013e52、67d79f9）收紧了 JWT 检测正则与清洗逻辑（去除引号/换行/空格）——改动相关代码时务必保证两种模式都可用。
- **`web.js` 是已编译的二进制文件。** 不要直接编辑或「修复」它；它是 sing-box，而非 Node 源码。安全扫描器会标记它以及 `nezha-agent`——这些 CVE 应写入 `.trivyignore`，而不是改源码。
- **没有测试，也没有本地构建步骤。** 本地验证仅限于阅读/审查 shell 与 JS 模板生成逻辑。Dockerfile 引用了 `npm install -r package.json`（非标准写法，但无害）；`package.json` 仍声明 `start: node server.js`。
- **没有 lint 配置**（JS 和 shell 都没有）。
- 受认证的端点会执行 shell 命令（`entrypoint.sh`、`ps -ef`、`ss -nltp`）；它们处于 Basic 认证之后，面向单一运维者，但对这些端点如何被访问的任何改动都应视为安全敏感。

## 常用命令

不适用于任何 test/lint/build 命令。本地运行控制面板应用（仅供审查——完整功能需要二进制、Docker 与 Argo 凭据）：

```sh
cd files && npm install && node server.js
```

Docker 构建（本地未验证，要求预编译二进制对 linux/amd64 有效）：

```sh
docker build -t x-for-choreo .
```