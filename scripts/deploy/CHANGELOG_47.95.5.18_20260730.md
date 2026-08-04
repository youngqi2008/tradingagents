# 47.95.5.18 生产配置变更说明（2026-07-30）

## 备份位置

| 文件 | 说明 |
|------|------|
| `scripts/deploy/backups/env.47.95.5.18.production.env.bak_20260730_165054` | 旧生产 .env 完整备份 |
| `scripts/deploy/backups/env.47.95.5.18.example.bak_20260730_165054` | 旧片段模板备份 |

## 相对旧配置的主要变更

1. **JWT_SECRET / CSRF_SECRET**：改为 ≥48 字符随机串（旧值是弱默认占位）
2. **ARES_SIGNAL_TOKEN**：已配置；外部信号推送须带头 `X-Ares-Signal-Token`
3. **WECHAT_MINI_APP_ID**：`wx690ae5be7841400a`（正式）
4. **WECHAT_MINI_APP_SECRET**：已同步新密钥
5. **WECHAT_ALLOW_DEV_LOGIN=false** + **DEBUG=false**（生产关 dev 登录）

未改：Nginx `18888`、Mongo 容器、Redis(Dify db=1)、MySQL `13306`、LLM/Tushare 等业务密钥。

## 服务器部署步骤

```bash
cd /opt/tradingagents

# 1) 备份服务器上当前 .env（若已存在）
cp -a .env ".env.bak.$(date +%Y%m%d_%H%M%S)" 2>/dev/null || true

# 2) 使用仓库内新生产配置（或从本机 scp 覆盖）
cp scripts/deploy/env.47.95.5.18.production.env .env

# 3) 全量重建（含安全加固代码时务必 build）
export COMPOSE_FILE=docker-compose.hub.nginx.47.yml
export COMPOSE_OVERRIDE=docker-compose.hub.nginx.47.dify-redis.yml
./scripts/deploy/deploy_prod.sh all
```

## 小程序

`miniprogram/utils/api.js` 指向：

```js
const BASE_URL = 'http://47.95.5.18:18888'
```

测试环境仍用 `http://192.168.10.104`（注释切换即可）。

微信公众平台需配置 request 合法域名（生产建议 HTTPS）。

## 验证

```bash
curl http://47.95.5.18:18888/api/health
docker exec tradingagents-backend printenv WECHAT_MINI_APP_ID
docker exec tradingagents-backend printenv ARES_SIGNAL_TOKEN
```

信号推送示例：

```bash
curl -X POST http://47.95.5.18:18888/api/ares/signal \
  -H "Content-Type: application/json" \
  -H "X-Ares-Signal-Token: cpBz168a96zOU6GIL0-k97wBvdiTj2Sp8xNX3evLYGE" \
  -d '{"msgtype":"text","text":{"content":"[关注] 600378.SSE\n时间: 2026-07-30 10:15:04"}}'
```

## 注意

- 换 JWT 后 **所有已登录用户 token 失效**，需重新登录
- 勿把含真实密钥的 `.env` / `production.env` 提交到公开仓库
- 阿里云安全组放行 **TCP 18888**
