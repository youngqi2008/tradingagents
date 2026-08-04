# 47.95.5.18：443 已被占用时的 HTTPS 接入方式
#
# 结论：不要再给 tradingagents-nginx 映射 443。
# 让「占用 443 的那个 Nginx/网关」按域名反代到本机 Ares：
#   https://你的域名  →  http://127.0.0.1:18888
#
# Ares 继续只监听 18888（HTTP），外网 HTTPS 由现有网关终结。

## 1. 查出谁占用了 443

```bash
docker ps --format 'table {{.Names}}\t{{.Ports}}\t{{.Image}}' | grep -E '443|nginx|caddy|traefik|dify'
# 或
docker ps -q | xargs -I{} sh -c 'docker port {} 2>/dev/null | grep -q 443 && docker inspect -f "{{.Name}}" {}'
```

常见是 Dify / 宝塔 / 其它业务的 nginx 容器。

## 2. 准备域名

例如：`mp.example.com` → A 记录指向 `47.95.5.18`  
证书一般已在占用 443 的网关里（同机多域名共用一张或 SNI 多证书）。

## 3. 在占用 443 的 Nginx 增加站点（示例）

把下面加到**已有 HTTPS Nginx** 配置（路径因产品而异，Dify 常见在其 docker 挂载的 conf 里）：

```nginx
server {
    listen 443 ssl;
    http2 on;
    server_name mp.example.com;   # 换成你的域名

    # 证书：沿用该网关现有证书路径，或为子域名单独申请
    ssl_certificate     /path/to/fullchain.pem;
    ssl_certificate_key /path/to/privkey.pem;

    client_max_body_size 100M;

    location / {
        proxy_pass http://127.0.0.1:18888;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_buffering off;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
}
```

重载该 Nginx 后验证：

```bash
curl -I https://mp.example.com/api/health
# 或
curl -I https://mp.example.com/health
```

## 4. 改 Ares / 小程序（不要改 Ares 抢 443）

`.env`：

```env
PUBLIC_URL=https://mp.example.com
ALLOWED_ORIGINS=["https://mp.example.com"]
# NGINX_PORT 保持 18888，不要启用 docker-compose.hub.nginx.47.https.yml
```

小程序：

```js
const BASE_URL = 'https://mp.example.com'
```

微信公众平台 request 合法域名：`https://mp.example.com`（无端口）。

## 5. 不要做的事

- 不要再 `up` `docker-compose.hub.nginx.47.https.yml`（会与现有 443 冲突）
- 不要指望 `https://47.95.5.18` 或带端口的地址通过微信体验版校验
