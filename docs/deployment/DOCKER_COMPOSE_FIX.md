# Docker Compose 问题修复指南

## 问题描述

在使用 `docker compose ps` 时遇到以下问题：

1. **警告**: `version` 属性已过时
2. **服务不健康**: `frontend` 和 `nginx` 服务显示 `unhealthy` 状态

## 修复内容

### 1. 移除过时的 `version` 属性

新版本的 Docker Compose（v2.0+）不再需要 `version` 属性，已从以下文件中移除：
- `docker-compose.yml`
- `docker-compose.hub.nginx.yml`

### 2. 修复健康检查问题

**问题原因**: `nginx:alpine` 镜像默认没有 `wget` 工具，导致健康检查失败。

**解决方案**:

#### 方案 A: 为前端服务安装 wget（已修复）

修改了 `Dockerfile.frontend`，在运行时阶段安装 `wget`：

```dockerfile
# 安装 wget 用于健康检查
RUN apk add --no-cache wget
```

#### 方案 B: 为 Nginx 服务创建自定义镜像（已修复）

创建了 `Dockerfile.nginx`，基于 `nginx:alpine` 并安装 `wget`：

```dockerfile
FROM nginx:alpine
RUN apk add --no-cache wget
```

修改了 `docker-compose.hub.nginx.yml`，使用自定义构建的 nginx 镜像：

```yaml
nginx:
  build:
    context: .
    dockerfile: Dockerfile.nginx
  image: tradingagents-nginx:latest
```

## 修复步骤

### 1. 重新构建镜像

```bash
# 重新构建前端镜像
docker-compose -f docker-compose.hub.nginx.yml build frontend

# 重新构建 Nginx 镜像
docker-compose -f docker-compose.hub.nginx.yml build nginx

# 或者一次性构建所有服务
docker-compose -f docker-compose.hub.nginx.yml build
```

### 2. 重启服务

```bash
# 停止服务
docker-compose -f docker-compose.hub.nginx.yml down

# 启动服务
docker-compose -f docker-compose.hub.nginx.yml up -d

# 查看服务状态
docker compose ps
```

### 3. 验证修复

```bash
# 检查服务健康状态
docker compose ps

# 应该看到所有服务都是 healthy 状态
# NAME                     STATUS
# tradingagents-backend    Up (healthy)
# tradingagents-frontend   Up (healthy)
# tradingagents-nginx      Up (healthy)
# tradingagents-mongodb    Up (healthy)
# tradingagents-redis      Up (healthy)
```

### 4. 查看日志（如果仍有问题）

```bash
# 查看前端日志
docker logs tradingagents-frontend

# 查看 Nginx 日志
docker logs tradingagents-nginx

# 查看所有服务日志
docker-compose -f docker-compose.hub.nginx.yml logs -f
```

## 健康检查说明

### Frontend 健康检查

```yaml
healthcheck:
  test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 30s
```

- 检查前端 Nginx 服务是否响应 HTTP 请求
- 每 30 秒检查一次
- 启动后等待 30 秒开始检查

### Nginx 健康检查

```yaml
healthcheck:
  test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 30s
```

- 检查 Nginx 的 `/health` 端点（在 `nginx/nginx.conf` 中定义）
- 每 30 秒检查一次
- 启动后等待 30 秒开始检查

## 常见问题

### Q: 构建镜像时提示找不到 Dockerfile.nginx？

**A**: 确保 `Dockerfile.nginx` 文件在项目根目录下。如果文件不存在，可以手动创建：

```bash
cat > Dockerfile.nginx << 'EOF'
FROM nginx:alpine
RUN apk add --no-cache wget
EOF
```

### Q: 健康检查仍然失败？

**A**: 检查以下几点：

1. **确认镜像已重新构建**:
   ```bash
   docker images | grep tradingagents
   ```

2. **检查容器内是否有 wget**:
   ```bash
   docker exec tradingagents-frontend which wget
   docker exec tradingagents-nginx which wget
   ```

3. **手动测试健康检查命令**:
   ```bash
   docker exec tradingagents-frontend wget --quiet --tries=1 --spider http://localhost
   docker exec tradingagents-nginx wget --quiet --tries=1 --spider http://localhost/health
   ```

4. **检查服务是否正常运行**:
   ```bash
   curl http://localhost:3000  # 前端
   curl http://localhost/health  # Nginx 健康检查
   ```

### Q: 不想使用自定义 Nginx 镜像怎么办？

**A**: 可以使用其他健康检查方法：

**选项 1**: 使用 `sh` 和 `test` 命令检查端口：

```yaml
healthcheck:
  test: ["CMD", "sh", "-c", "nc -z localhost 80 || exit 1"]
```

**选项 2**: 使用 `curl`（如果可用）：

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost/health"]
```

**选项 3**: 检查 Nginx 进程：

```yaml
healthcheck:
  test: ["CMD", "sh", "-c", "pgrep nginx || exit 1"]
```

## 相关文件

- `docker-compose.yml` - 基础 Docker Compose 配置
- `docker-compose.hub.nginx.yml` - 带 Nginx 反向代理的配置
- `Dockerfile.frontend` - 前端镜像构建文件
- `Dockerfile.nginx` - Nginx 镜像构建文件（新建）
- `nginx/nginx.conf` - Nginx 配置文件

## 更新日期

2025-02-13
