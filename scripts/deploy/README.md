# 生产部署指南（47.95.5.18）

## 架构

```
外网 47.95.5.18:80 (Nginx)
  ├── /          → frontend（运营后台）
  ├── /api/*     → backend（FastAPI，含 /api/ares/signal）
  └── MongoDB/Redis 在 Docker 内

MySQL（用户/计费/问股/站内信）→ 宿主机 47.95.5.18:13306（.env 中 MYSQL_*）
```

## 一、服务器首次准备（在 47.95.5.18 上执行一次）

### 1. 安装 Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# 重新登录后验证
docker --version
docker compose version
```

### 2. 上传项目

**方式 A：Git（推荐）**

```bash
sudo mkdir -p /opt/tradingagents
sudo chown $USER:$USER /opt/tradingagents
cd /opt/tradingagents
git clone <你的仓库地址> .
```

**方式 B：从 Windows 推送（见下文 `push_and_deploy.ps1`）**

### 3. 配置 .env

```bash
cd /opt/tradingagents
cp .env.example .env   # 或从本机复制已有 .env
vim .env
```

**必须检查：**

| 变量 | 说明 |
|------|------|
| `MYSQL_HOST` | 容器访问宿主机 MySQL，可用 `47.95.5.18` 或 `172.17.0.1` |
| `MYSQL_PORT` | `13306` |
| `MYSQL_PASSWORD` | 数据库密码 |
| `WECHAT_MINI_APP_ID` / `SECRET` | 小程序登录 |
| `DASHSCOPE_API_KEY` 等 | 问股/研报 LLM |
| `ARES_SIGNAL_TOKEN` | 外部信号推送鉴权（可选，建议配置） |

### 4. 首次全量部署

```bash
chmod +x scripts/deploy/deploy_prod.sh
./scripts/deploy/deploy_prod.sh all
```

### 5. 开放防火墙

```bash
# 若使用 firewalld
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --reload

# 云服务器安全组：放行 TCP 80（及 443 若上 HTTPS）
```

---

## 二、日常更新部署

### 在服务器上（已 SSH 登录 47.95.5.18）

```bash
cd /opt/tradingagents

# 拉代码（若用 Git）
git pull

# 仅后端/API 变更（最常用，含信号接口、问股 SSE 等）
./scripts/deploy/deploy_prod.sh backend

# 前端运营后台变更
./scripts/deploy/deploy_prod.sh frontend

# 全量重建
./scripts/deploy/deploy_prod.sh all
```

### 在 Windows 开发机一键推送 + 部署

```powershell
# 1. 复制并编辑配置
copy scripts\deploy\deploy.config.example scripts\deploy\deploy.config
# 修改 DEPLOY_HOST、DEPLOY_USER、DEPLOY_PATH、SSH_KEY

# 2. 推送并部署（默认仅 backend）
powershell -ExecutionPolicy Bypass -File scripts\deploy\push_and_deploy.ps1

# 全量部署
powershell -ExecutionPolicy Bypass -File scripts\deploy\push_and_deploy.ps1 -Mode all
```

---

## 三、验证

```bash
# 健康检查
curl http://47.95.5.18/api/health

# 外部信号接口（买点示例）
curl -X POST http://47.95.5.18/api/ares/signal \
  -H "Content-Type: application/json" \
  -d '{"msgtype":"text","text":{"content":"[关注] 600378.SSE\n时间: 2026-07-11 10:15:04"}}'

# 若配置了 ARES_SIGNAL_TOKEN
curl -X POST http://47.95.5.18/api/ares/signal \
  -H "Content-Type: application/json" \
  -H "X-Ares-Signal-Token: 你的令牌" \
  -d '{"msgtype":"text","text":{"content":"[关注] 600378.SSE\n时间: 2026-07-11 10:15:04"}}'
```

运营后台：`http://47.95.5.18`（admin / admin123）

小程序 `miniprogram/utils/api.js`：

```js
const BASE_URL = 'http://47.95.5.18'
```

微信开发者工具 → 详情 → 本地设置 → **不校验合法域名**（开发阶段）；上线需配置小程序 request 合法域名。

---

## 四、常用运维命令

```bash
./scripts/deploy/deploy_prod.sh status    # 容器状态
./scripts/deploy/deploy_prod.sh health    # API 健康
./scripts/deploy/deploy_prod.sh logs backend
docker compose -f docker-compose.hub.nginx.yml ps
```

---

## 五、脚本说明

| 文件 | 用途 |
|------|------|
| `scripts/deploy/deploy_prod.sh` | 在 Linux 服务器执行构建/启动/检查 |
| `scripts/deploy/push_and_deploy.ps1` | Windows 同步代码并 SSH 触发部署 |
| `scripts/deploy/deploy.config.example` | 推送部署配置模板 |

---

## 六、MySQL 连接问题

backend 容器若报 MySQL 连接失败，在 `.env` 中尝试：

```env
MYSQL_HOST=172.17.0.1
# 或
MYSQL_HOST=host.docker.internal
```

并在 `docker-compose.hub.nginx.yml` 的 backend 下增加（如尚未配置）：

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

然后：`./scripts/deploy/deploy_prod.sh backend`

---

## 七、宿主机已有 MongoDB / Redis（47.95.5.18）

**不建议再部署第二套**（默认占用 `27017`/`6379`，会与现有实例端口冲突）。

### 推荐：复用已有 MongoDB / Redis

- **MongoDB**：同一实例，使用独立库名 `tradingagents`
- **Redis**：同一实例，默认 `db 0`（可用 `REDIS_DB=1` 与其它应用隔离）

使用不含 mongodb/redis 的 compose：

```bash
export COMPOSE_FILE=docker-compose.hub.nginx.external.yml
./scripts/deploy/deploy_prod.sh all
```

`.env` 示例（backend 在 Docker 内访问宿主机）：

```env
MONGODB_HOST=host.docker.internal
MONGODB_PORT=27017
REDIS_HOST=host.docker.internal
REDIS_PORT=6379
MYSQL_HOST=host.docker.internal
MYSQL_PORT=13306
```

### 若必须两套并存

改 **不同端口**（如 MongoDB `27018`、Redis `6380`），并同步修改 compose 与 backend 环境变量；需双倍资源，一般无必要。

### 复用 Dify 同款 Redis（你当前环境）

Dify 配置里 `REDIS_HOST=redis` 是 **Dify Docker 网络内的服务名**，Ares 容器默认解析不了，需二选一：

**方式 A：Redis 已映射到宿主机 6379（常见）**

`.env`：

```env
REDIS_HOST=host.docker.internal
REDIS_PORT=6379
REDIS_PASSWORD=difyai123456
REDIS_DB=1
REDIS_ENABLED=true
```

> 使用 `REDIS_DB=1`（或其它 1–15），**不要与 Dify 共用 db 0**，避免 key 冲突。

**方式 B：Ares 加入 Dify 的 Docker 网络**

```bash
docker network ls | grep -i dify   # 查网络名，如 dify_default
```

在 `docker-compose.hub.nginx.external.yml` 的 `backend` 下增加：

```yaml
networks:
  - tradingagents-network
  - dify_default   # 改为实际网络名

# 文件末尾 networks 段增加:
# dify_default:
#   external: true
```

`.env` 可用 Dify 同款：

```env
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=difyai123456
REDIS_DB=1
```

**Ares 不需要** Dify 的 `REDIS_USERNAME`、`REDIS_USE_SSL`、Sentinel/Cluster 等变量（当前代码未实现）。

**验证：**

```bash
docker exec tradingagents-backend python -c "
from app.core.config import settings
print(settings.REDIS_URL.replace(settings.REDIS_PASSWORD,'***'))
"
curl http://47.95.5.18/api/health
```

---

## 八、47.95.5.18 当前推荐拓扑（已清空旧 Mongo）

| 组件 | 方式 | 说明 |
|------|------|------|
| **MongoDB** | compose **全新** | `docker-compose.hub.nginx.47.yml` |
| **Redis** | 宿主机/Dify 共用 | `REDIS_DB=1`，密码 `difyai123456` |
| **MySQL** | 宿主机 `13306` | 与现网相同 `ares_ops` |

### 1. 准备 .env

**完整模板**（Ares 默认端口 **18888**，80/8080/8888 留给 Dify 等）：

```bash
chmod +x scripts/deploy/pick_nginx_port.sh
./scripts/deploy/pick_nginx_port.sh   # 自动推荐空闲端口

cp scripts/deploy/env.47.95.5.18.production.env .env
vi .env   # 按 pick_nginx_port 输出修改 NGINX_PORT / PUBLIC_URL / ALLOWED_ORIGINS
```

`deploy_prod.sh` 会自动从 `.env` 读取 `PUBLIC_URL` 或 `NGINX_PORT`，无需再 `export PUBLIC_URL`。

或合并片段（旧方式）：

```bash
cp scripts/deploy/env.47.95.5.18.example .env.snippet
# 将片段合并进服务器 .env，并补上 WECHAT_*、DASHSCOPE_* 等密钥
```

### 2. 首次部署（全新 Mongo 数据卷）

```bash
cd /opt/tradingagents
export COMPOSE_FILE=docker-compose.hub.nginx.47.yml

# 若曾存在旧卷且要彻底重来（会删除 Mongo 数据）:
# docker compose -f docker-compose.hub.nginx.47.yml down
# docker volume rm tradingagents_mongodb_data

./scripts/deploy/deploy_prod.sh all
```

### 3. 日常更新

```bash
export COMPOSE_FILE=docker-compose.hub.nginx.47.yml
./scripts/deploy/deploy_prod.sh backend
```

### 4. 验证

```bash
docker exec tradingagents-mongodb mongo -u admin -p tradingagents123 --authenticationDatabase admin --eval "db.adminCommand('ping')"
docker exec tradingagents-backend redis-cli -h host.docker.internal -p 6379 -a difyai123456 -n 1 ping
curl http://47.95.5.18/api/health
```

---

## 九、Docker 构建常见问题

### 1. pip 清华源 403（setuptools / pip）

**现象**：`HTTP error 403` 拉取 `setuptools` 或 `pip`。

**原因**：清华镜像对 Docker 构建环境常限流/拒绝；服务器上 `vi Dockerfile.backend` 手工改的版本可能不完整。

**处理**：

1. 用本仓库最新 `Dockerfile.backend`（含预装 setuptools + `--no-build-isolation` + 镜像回退链）
2. 从 Windows 同步到服务器，不要只在服务器手改：

```powershell
.\scripts\deploy\push_and_deploy.ps1
```

3. **不要用 `--no-cache`**，除非确有必要（会重跑 apt 层，耗时数小时）

```bash
# 推荐：利用缓存，只重建变更层
docker compose -f docker-compose.hub.nginx.47.yml build backend
```

### 2. 第 3 步 apt/pandoc 极慢（2+ 小时）

**原因**：旧版从 GitHub 下载 pandoc deb，国内 ECS 极慢。

**已优化**：改用阿里云 apt 源 + `apt install pandoc`；wkhtmltopdf 带 GitHub 镜像回退。

首次构建 step 3 约 **5–15 分钟** 属正常；完成后该层会缓存。

### 3. BAIDU_API_KEY 警告

可忽略，或于 `.env` 中配置百度语音相关密钥。

### 4. backend 反复重启 / 健康检查超时

**常见原因**：只执行了 `deploy_prod.sh backend`，旧脚本用 `--no-deps` **未启动 MongoDB 和 nginx**。

- backend 连不上 `mongodb:27017` → 容器崩溃循环（`Up 1 second`）
- nginx 未启动 → `curl http://47.95.5.18/api/health` 永远失败

**处理**（服务器上）：

```bash
export COMPOSE_FILE=docker-compose.hub.nginx.47.yml

# 1. 启动全部运行时依赖
docker compose up -d mongodb frontend nginx

# 2. 查看 backend 崩溃原因
docker compose logs --tail=80 backend

# 3. 容器内直连探测（绕过 nginx）
docker exec tradingagents-backend curl -sf http://localhost:8000/api/health

# 4. 同步最新 deploy_prod.sh 后重新部署
./scripts/deploy/deploy_prod.sh backend
```

**首次部署务必用** `./scripts/deploy/deploy_prod.sh all`，不要只跑 backend。

若日志报 Redis/MySQL 连接失败，检查 `.env` 中 `REDIS_PASSWORD`、`MYSQL_HOST`（必要时改为 `172.17.0.1` 或 `47.95.5.18`）。

**注意**：`.env` 里 `REDIS_HOST=localhost` 在容器内无效，生产应设为 `host.docker.internal`。

### 5. mongo / frontend 镜像拉取超时（docker-0.unsee.tech / gcr.io）

**现象**：

```
Head "https://docker-0.unsee.tech/v2/library/mongo/manifests/4.4": context deadline exceeded
mongodb:27017: Name or service not known
```

**原因**：服务器 Docker 镜像加速不可用；MongoDB 未启动 → backend 崩溃。

**处理**：

```bash
chmod +x scripts/deploy/pull_base_images.sh
./scripts/deploy/pull_base_images.sh

# 或直接在 .env 指定国内镜像
echo 'MONGO_IMAGE=docker.m.daocloud.io/library/mongo:4.4' >> .env

export COMPOSE_FILE=docker-compose.hub.nginx.47.yml
docker compose up -d
```

backend/frontend/nginx 已设 `pull_policy: build`，**本地构建，不再从 Docker Hub 拉 hsliup/*`。

### 6. curl /api/health 返回 HTML 404

说明 **Ares nginx 未占用 80 端口**，响应来自 Dify 或其他服务。

```bash
ss -tlnp | grep ':80'
docker ps --format '{{.Names}}\t{{.Ports}}' | grep 80
```

若常用端口均被占用，运行 `./scripts/deploy/pick_nginx_port.sh`，在 `.env` 同步修改三处：

```env
NGINX_PORT=18888
PUBLIC_URL=http://47.95.5.18:18888
ALLOWED_ORIGINS=["http://47.95.5.18:18888",...]
```

阿里云安全组需放行所选端口。

### 7. Redis Connection refused（host.docker.internal:6379）

**现象**：`Error 111 connecting to host.docker.internal:6379. Connection refused`

**原因**：Dify Redis **未映射到宿主机**，只在 Dify docker 网络内可访问。

**处理**：

```bash
# 1. 查 Redis 容器与网络名
docker ps | grep -i redis
docker inspect $(docker ps --format '{{.Names}}' | grep -i redis | head -1) \
  --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}'

# 2. 修改 .env（示例网络名 docker_default，以实际为准）
DIFY_DOCKER_NETWORK=docker_default
REDIS_HOST=redis
REDIS_URL=redis://:difyai123456@redis:6379/1

# 3. 用 dify-redis overlay 重启
export COMPOSE_FILE=docker-compose.hub.nginx.47.yml
export COMPOSE_OVERRIDE=docker-compose.hub.nginx.47.dify-redis.yml
docker compose -f $COMPOSE_FILE -f $COMPOSE_OVERRIDE up -d --force-recreate backend

# 4. 验证
docker exec tradingagents-backend python -c "import socket; s=socket.create_connection(('redis',6379),3); print('OK')"
```
