# ares.zhystech.cn — 基于本机 Dify nginx（docker-nginx-1）

## 目录对照

| 宿主机 | 容器内 |
|--------|--------|
| `/opt/dify1113/docker/nginx/conf.d` | `/etc/nginx/conf.d` |
| `/opt/dify1113/docker/volumes/certbot/conf` | `/etc/letsencrypt` |
| `/opt/dify1113/docker/volumes/certbot/www` | `/var/www/html` |
| `/opt/dify1113/docker/nginx/ssl` | `/etc/ssl` |

Ares 入口：`127.0.0.1:18888`（宿主机）→ 容器内用 `172.17.0.1:18888`

---

## 步骤 1：申请证书（Let's Encrypt）

确认 DNS：`ares.zhystech.cn` → `47.95.5.18`

```bash
# 看 Dify 是否已有 certbot 容器
docker ps -a --format '{{.Names}}' | grep -i certbot

# 方式 A：已有 certbot 容器（名称按实际改）
docker run --rm \
  -v /opt/dify1113/docker/volumes/certbot/conf:/etc/letsencrypt \
  -v /opt/dify1113/docker/volumes/certbot/www:/var/www/html \
  certbot/certbot certonly --webroot -w /var/www/html \
  -d ares.zhystech.cn --email 你的邮箱@zhystech.cn --agree-tos --no-eff-email

# 若 webroot 失败（80 被 Dify 抢走 ACME），可临时用 standalone（需短暂停 80）或 DNS 验证
```

证书落盘后应存在：

```bash
ls -la /opt/dify1113/docker/volumes/certbot/conf/live/ares.zhystech.cn/
# fullchain.pem  privkey.pem
```

若已有 `*.zhystech.cn` 通配符证书，可跳过申请，下面 ssl 路径改成通配符那套。

---

## 步骤 2：写入站点配置

```bash
cat > /opt/dify1113/docker/nginx/conf.d/ares.zhystech.cn.conf << 'EOF'
# Ares 小程序 / 运营后台 — https://ares.zhystech.cn → tradingagents:18888

upstream ares_backend {
    # Docker 默认桥访问宿主机已映射端口
    server 172.17.0.1:18888;
    keepalive 8;
}

server {
    listen 80;
    server_name ares.zhystech.cn;

    # ACME 续期
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl;
    http2 on;
    server_name ares.zhystech.cn;

    ssl_certificate     /etc/letsencrypt/live/ares.zhystech.cn/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ares.zhystech.cn/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers off;

    client_max_body_size 100M;

    location / {
        proxy_pass http://ares_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_buffering off;
        proxy_connect_timeout 120s;
        proxy_send_timeout 3600s;
        proxy_read_timeout 3600s;
    }
}
EOF
```

---

## 步骤 3：探测反代目标 + 重载 Nginx

```bash
# 容器能否打到 Ares
docker exec docker-nginx-1 wget -qO- --timeout=3 http://172.17.0.1:18888/health || \
docker exec docker-nginx-1 wget -qO- --timeout=3 http://172.17.0.1:18888/api/health

# 若不通，查宿主机网关 IP 后改 upstream
ip -4 addr show docker0
# 或改用: server 宿主机内网IP:18888;

docker exec docker-nginx-1 nginx -t && docker exec docker-nginx-1 nginx -s reload

curl -sI https://ares.zhystech.cn/health
curl -sI https://ares.zhystech.cn/api/health
```

---

## 步骤 4：Ares / 小程序 / 微信

服务器 `tradingagents/.env`：

```env
PUBLIC_URL=https://ares.zhystech.cn
ALLOWED_ORIGINS=["https://ares.zhystech.cn","http://47.95.5.18:18888"]
```

```bash
cd /opt/tradingagents   # 或你的实际路径
# 改完 .env 后 recreate backend（CORS）
docker compose -f docker-compose.hub.nginx.47.yml \
  -f docker-compose.hub.nginx.47.dify-redis.yml \
  up -d --force-recreate backend
```

小程序 `BASE_URL`（仓库已改）：`https://ares.zhystech.cn`

微信公众平台 → 开发管理 → 开发设置 → **request 合法域名**：

```
ares.zhystech.cn
```

（界面填域名即可，不要带 `https://` 或端口；需备案通过。）

然后重新上传体验版。

---

## 注意

- **不要**再给 `tradingagents-nginx` 映射 443
- Dify 原有站点不受影响（不同 `server_name`）
- 证书续期后一般无需改 conf（仍指向 `live/ares.zhystech.cn/`）
