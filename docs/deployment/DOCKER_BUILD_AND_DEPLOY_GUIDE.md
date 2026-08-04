# Docker 镜像打包和部署完整指南

> 📦 本指南详细介绍如何重新部署当前代码：从构建镜像到部署的完整流程

## 📋 目录

1. [快速开始](#快速开始)
2. [本地构建镜像](#本地构建镜像)
3. [使用 Docker Compose 部署](#使用-docker-compose-部署)
4. [推送到 Docker Hub](#推送到-docker-hub)
5. [多架构构建](#多架构构建)
6. [常见问题](#常见问题)

---

## 🚀 快速开始

### 前置要求

- **Docker**: 20.10+
- **Docker Compose**: 2.0+
- **至少 4GB 内存** 和 **20GB 磁盘空间**

验证安装：
```bash
docker --version
docker-compose --version
```

---

## 📦 本地构建镜像

### 方式一：使用 Docker Compose 构建（推荐）

这是最简单的方式，会自动构建所有服务：

```bash
# 1. 进入项目根目录
cd TradingAgents-CN

# 2. 配置环境变量（如果还没有）
cp .env.example .env
# 编辑 .env 文件，配置必要的 API 密钥

# 3. 构建所有镜像
docker-compose build

# 4. 构建特定服务
docker-compose build backend    # 只构建后端
docker-compose build frontend   # 只构建前端
```

**构建时间**：
- 后端镜像：约 10-20 分钟（首次构建）
- 前端镜像：约 5-10 分钟（首次构建）
- 后续构建（有缓存）：约 2-5 分钟

### 方式二：手动构建单个镜像

#### 构建后端镜像

```bash
# 构建后端镜像
docker build -f Dockerfile.backend -t tradingagents-backend:v1.0.0-preview .

# 查看镜像
docker images | grep tradingagents-backend
```

#### 构建前端镜像

```bash
# 构建前端镜像
docker build -f Dockerfile.frontend -t tradingagents-frontend:v1.0.0-preview .

# 查看镜像
docker images | grep tradingagents-frontend
```

### 构建参数说明

#### 后端镜像（Dockerfile.backend）

- **基础镜像**: `python:3.10-slim-bookworm`
- **支持架构**: amd64, arm64（通过 `TARGETARCH` 参数）
- **包含组件**:
  - Python 3.10 运行环境
  - Pandoc 3.8.2.1（文档转换）
  - wkhtmltopdf（PDF 生成）
  - 中文字体支持
  - 所有 Python 依赖

#### 前端镜像（Dockerfile.frontend）

- **构建阶段**: Node.js 22-alpine（使用 Yarn 1.22.22）
- **运行阶段**: Nginx alpine（提供静态文件服务）
- **包含组件**:
  - Vue 3 + Vite 构建产物
  - Nginx 配置（SPA 路由支持）
  - 静态资源（assets、docs）

### 优化构建速度

1. **使用构建缓存**：
```bash
# Docker Compose 会自动使用缓存
docker-compose build --no-cache  # 不使用缓存（完全重新构建）
```

2. **并行构建**：
```bash
# Docker Compose 默认并行构建
docker-compose build --parallel
```

3. **只构建变更的服务**：
```bash
# 只构建修改过的服务
docker-compose build backend
```

---

## 🐳 使用 Docker Compose 部署

### 步骤 1：准备配置文件

```bash
# 1. 确保 .env 文件存在
cp .env.example .env

# 2. 编辑 .env 文件，配置必要的环境变量
# 至少需要配置一个 LLM API 密钥：
#   - DEEPSEEK_API_KEY（推荐）
#   - DASHSCOPE_API_KEY（推荐）
#   - OPENAI_API_KEY（可选）
```

### 步骤 2：创建必要的目录

```bash
# 创建数据目录
mkdir -p logs data/cache data/exports data/reports config
```

### 步骤 3：启动服务

```bash
# 启动所有服务（后台运行）
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f

# 查看特定服务日志
docker-compose logs -f backend
```

### 步骤 4：验证部署

```bash
# 检查后端健康状态
curl http://localhost:8000/api/health

# 检查前端
curl http://localhost:3000

# 检查 MongoDB
docker exec tradingagents-mongodb mongo -u admin -p tradingagents123 --authenticationDatabase admin --eval "db.adminCommand('ping')"

# 检查 Redis
docker exec tradingagents-redis redis-cli -a tradingagents123 ping
```

### 步骤 5：导入初始配置（首次部署）

```bash
# 导入配置数据并创建默认用户
docker exec -it tradingagents-backend python scripts/import_config_and_create_user.py

# 重启后端以加载配置
docker-compose restart backend
```

**默认登录信息**：
- 用户名：`admin`
- 密码：`admin123`

### 常用管理命令

```bash
# 启动服务
docker-compose up -d

# 停止服务
docker-compose down

# 重启服务
docker-compose restart

# 重启特定服务
docker-compose restart backend

# 查看日志
docker-compose logs -f

# 查看服务状态
docker-compose ps

# 进入容器
docker exec -it tradingagents-backend bash
docker exec -it tradingagents-frontend sh

# 清理（⚠️ 会删除所有数据）
docker-compose down -v
```

---

## 📤 推送到 Docker Hub

### 步骤 1：登录 Docker Hub

```bash
# 登录 Docker Hub
docker login

# 或使用命令行直接登录
docker login -u YOUR_DOCKERHUB_USERNAME -p YOUR_PASSWORD
```

### 步骤 2：标记镜像

```bash
# 标记后端镜像
docker tag tradingagents-backend:v1.0.0-preview YOUR_DOCKERHUB_USERNAME/tradingagents-backend:v1.0.0-preview
docker tag tradingagents-backend:v1.0.0-preview YOUR_DOCKERHUB_USERNAME/tradingagents-backend:latest

# 标记前端镜像
docker tag tradingagents-frontend:v1.0.0-preview YOUR_DOCKERHUB_USERNAME/tradingagents-frontend:v1.0.0-preview
docker tag tradingagents-frontend:v1.0.0-preview YOUR_DOCKERHUB_USERNAME/tradingagents-frontend:latest
```

### 步骤 3：推送镜像

```bash
# 推送后端镜像
docker push YOUR_DOCKERHUB_USERNAME/tradingagents-backend:v1.0.0-preview
docker push YOUR_DOCKERHUB_USERNAME/tradingagents-backend:latest

# 推送前端镜像
docker push YOUR_DOCKERHUB_USERNAME/tradingagents-frontend:v1.0.0-preview
docker push YOUR_DOCKERHUB_USERNAME/tradingagents-frontend:latest
```

### 步骤 4：验证推送

访问 https://hub.docker.com/repositories/YOUR_DOCKERHUB_USERNAME 查看推送的镜像。

### 使用推送的镜像

创建 `docker-compose.hub.yml`：

```yaml
version: '3.8'

services:
  backend:
    image: YOUR_DOCKERHUB_USERNAME/tradingagents-backend:latest
    # ... 其他配置同 docker-compose.yml

  frontend:
    image: YOUR_DOCKERHUB_USERNAME/tradingagents-frontend:latest
    # ... 其他配置同 docker-compose.yml
```

然后使用：
```bash
docker-compose -f docker-compose.hub.yml up -d
```

---

## 🏗️ 多架构构建

如果需要支持 ARM 和 x86_64 两种架构，需要使用 Docker Buildx。

### Windows PowerShell 脚本

项目提供了自动化脚本：

```powershell
# 使用 PowerShell 脚本构建并推送多架构镜像
.\scripts\publish-docker-images.ps1 YOUR_DOCKERHUB_USERNAME v1.0.0-preview
```

### Linux/macOS 脚本

```bash
# 使用 Shell 脚本构建并推送多架构镜像
chmod +x scripts/publish-docker-images.sh
./scripts/publish-docker-images.sh YOUR_DOCKERHUB_USERNAME v1.0.0-preview
```

### 手动多架构构建

#### 1. 安装并配置 Buildx

```bash
# 创建 buildx builder
docker buildx create --name tradingagents-builder --use

# 启动 builder
docker buildx inspect --bootstrap

# 验证支持的平台
docker buildx ls
```

#### 2. 构建多架构镜像

```bash
# 构建并推送后端镜像（多架构）
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -f Dockerfile.backend \
  -t YOUR_DOCKERHUB_USERNAME/tradingagents-backend:v1.0.0-preview \
  -t YOUR_DOCKERHUB_USERNAME/tradingagents-backend:latest \
  --push .

# 构建并推送前端镜像（多架构）
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -f Dockerfile.frontend \
  -t YOUR_DOCKERHUB_USERNAME/tradingagents-frontend:v1.0.0-preview \
  -t YOUR_DOCKERHUB_USERNAME/tradingagents-frontend:latest \
  --push .
```

#### 3. 验证多架构镜像

```bash
# 查看镜像支持的架构
docker buildx imagetools inspect YOUR_DOCKERHUB_USERNAME/tradingagents-backend:latest
```

**注意**：
- 多架构构建需要较长时间（约 30-60 分钟）
- ARM 架构在 x86_64 机器上通过 QEMU 模拟，速度较慢
- 建议在 CI/CD 环境中进行多架构构建

---

## 🔧 常见问题

### 1. 构建失败：网络超时

**问题**：构建时下载依赖超时

**解决方案**：
```bash
# 配置 Docker 镜像加速（国内用户）
# 编辑 /etc/docker/daemon.json (Linux)
# 或 Docker Desktop -> Settings -> Docker Engine (Windows/macOS)
{
  "registry-mirrors": [
    "https://docker.mirrors.ustc.edu.cn",
    "https://hub-mirror.c.163.com"
  ]
}

# 重启 Docker
# Linux: sudo systemctl restart docker
# Windows/macOS: 重启 Docker Desktop
```

### 2. 构建失败：磁盘空间不足

**问题**：构建过程中磁盘空间不足

**解决方案**：
```bash
# 清理 Docker 系统
docker system prune -a

# 清理构建缓存
docker builder prune -a

# 查看磁盘使用
docker system df
```

### 3. 服务启动失败：端口被占用

**问题**：端口 8000、3000、27017、6379 被占用

**解决方案**：
```bash
# 查找占用端口的进程
# Windows
netstat -ano | findstr :8000

# Linux/macOS
lsof -i :8000

# 修改 docker-compose.yml 中的端口映射
ports:
  - "8001:8000"  # 改为其他端口
```

### 4. MongoDB 连接失败

**问题**：后端无法连接 MongoDB

**解决方案**：
```bash
# 检查 MongoDB 状态
docker-compose ps mongodb

# 查看 MongoDB 日志
docker-compose logs mongodb

# 重启 MongoDB
docker-compose restart mongodb

# 检查环境变量
docker exec tradingagents-backend env | grep MONGODB
```

### 5. 前端无法访问后端 API

**问题**：前端显示网络错误

**解决方案**：
```bash
# 检查后端是否运行
curl http://localhost:8000/api/health

# 检查 CORS 配置（.env 文件）
CORS_ORIGINS=http://localhost:3000,http://localhost:8080

# 检查前端环境变量
docker exec tradingagents-frontend env | grep VITE_API_BASE_URL

# 重启服务
docker-compose restart backend frontend
```

### 6. 镜像构建很慢

**优化建议**：
1. 使用 `.dockerignore` 排除不必要的文件
2. 利用 Docker 层缓存
3. 使用多阶段构建（已实现）
4. 在 CI/CD 环境中构建（网络更快）

### 7. 推送镜像到 Docker Hub 很慢

**解决方案**：
1. 使用代理（如果可用）
2. 在 GitHub Actions 中构建和推送（推荐）
3. 考虑使用国内镜像仓库（如阿里云容器镜像服务）

---

## 📚 相关文档

- [Docker 部署指南](./docker/DOCKER_DEPLOYMENT_v1.0.0.md)
- [Docker Hub 发布指南](./docker/DOCKER_PUBLISH_GUIDE.md)
- [多架构构建指南](./docker/BUILD_MULTIARCH_GUIDE.md)
- [快速部署指南](./docker/quick_deploy_with_docker_hub.md)

---

## 🎯 总结

### 本地开发部署流程

```bash
# 1. 构建镜像
docker-compose build

# 2. 启动服务
docker-compose up -d

# 3. 导入配置（首次）
docker exec -it tradingagents-backend python scripts/import_config_and_create_user.py

# 4. 访问系统
# 前端: http://localhost:3000
# 后端: http://localhost:8000
```

### 生产环境部署流程

```bash
# 1. 构建并推送镜像
docker-compose build
docker tag ...  # 标记镜像
docker push ...  # 推送镜像

# 2. 在服务器上拉取镜像
docker-compose -f docker-compose.hub.yml pull

# 3. 启动服务
docker-compose -f docker-compose.hub.yml up -d

# 4. 导入配置（首次）
docker exec -it tradingagents-backend python scripts/import_config_and_create_user.py
```

---

**最后更新**: 2025-02-13  
**版本**: v1.0.0-preview
