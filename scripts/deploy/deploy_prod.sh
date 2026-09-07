#!/usr/bin/env bash
# =============================================================================
# Ares 生产环境部署脚本（在服务器 47.95.5.18 上执行）
#
# 用法:
#   chmod +x scripts/deploy/deploy_prod.sh
#   ./scripts/deploy/deploy_prod.sh                  # 全量构建并启动
#   ./scripts/deploy/deploy_prod.sh backend          # 仅重建 backend（常用）
#   ./scripts/deploy/deploy_prod.sh up               # 不构建，直接 up -d
#   ./scripts/deploy/deploy_prod.sh status           # 查看状态
#   ./scripts/deploy/deploy_prod.sh logs backend     # 查看日志
#   ./scripts/deploy/deploy_prod.sh health           # 健康检查
#
# 环境变量（可选）:
#   COMPOSE_FILE=docker-compose.hub.nginx.47.yml
#   # 多个 overlay 用冒号分隔，例如 Dify Redis + HTTPS:
#   COMPOSE_OVERRIDE=docker-compose.hub.nginx.47.dify-redis.yml:docker-compose.hub.nginx.47.https.yml
#   PUBLIC_URL=https://mp.example.com
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.hub.nginx.yml}"
COMPOSE_OVERRIDE="${COMPOSE_OVERRIDE:-}"
DEPLOY_HOST="${DEPLOY_HOST:-47.95.5.18}"
PUBLIC_URL="${PUBLIC_URL:-http://${DEPLOY_HOST}}"

load_public_url_from_env() {
  [[ -f ".env" ]] || return 0
  local url port
  url=$(grep -m1 '^PUBLIC_URL=' .env 2>/dev/null | cut -d= -f2- | tr -d '\r"' || true)
  if [[ -n "$url" ]]; then
    PUBLIC_URL="$url"
    return 0
  fi
  port=$(grep -m1 '^NGINX_PORT=' .env 2>/dev/null | cut -d= -f2- | tr -d '\r' || true)
  if [[ -n "$port" && "$port" != "80" ]]; then
    PUBLIC_URL="http://${DEPLOY_HOST}:${port}"
  fi
}
MODE="${1:-all}"
SERVICE="${2:-}"

log()  { echo -e "${CYAN}[deploy]${NC} $*"; }
ok()   { echo -e "${GREEN}[ok]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*"; }
fail() { echo -e "${RED}[fail]${NC} $*"; exit 1; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "未找到命令: $1"
}

compose() {
  local -a args=(-f "$COMPOSE_FILE")
  if [[ -n "${COMPOSE_OVERRIDE:-}" ]]; then
    local ov
    # 支持冒号或空格分隔多个 overlay
    for ov in ${COMPOSE_OVERRIDE//:/ }; do
      [[ -z "$ov" ]] && continue
      [[ -f "$ov" ]] || fail "找不到 Compose overlay: $ov"
      args+=(-f "$ov")
    done
  fi
  docker compose "${args[@]}" "$@"
}

check_prerequisites() {
  require_cmd docker
  docker compose version >/dev/null 2>&1 || fail "需要 Docker Compose v2（docker compose）"
  [[ -f "$COMPOSE_FILE" ]] || fail "找不到 $COMPOSE_FILE"
  [[ -f ".env" ]] || fail "缺少 .env，请从 .env.example 复制并配置 API Key / MySQL / 微信等"
  load_public_url_from_env
  log "公网地址: ${PUBLIC_URL}（来自 PUBLIC_URL 或 NGINX_PORT）"
  [[ -n "${COMPOSE_OVERRIDE}" ]] && log "Compose 叠加: ${COMPOSE_OVERRIDE}"
  if [[ -f "scripts/deploy/pull_base_images.sh" ]]; then
    bash scripts/deploy/pull_base_images.sh || warn "基础镜像拉取失败，可手动执行 pull_base_images.sh"
  fi
  ok "前置检查通过"
}

ensure_dirs() {
  mkdir -p logs data uploads
  ok "目录 logs/ data/ uploads/ 已就绪"
}

build_services() {
  local target="${1:-all}"
  # 国内 ECS：backend 基础镜像走 DaoCloud，避免 docker.io metadata 超时
  local python_base="${PYTHON_BASE:-docker.m.daocloud.io/library/python:3.10-slim-bookworm}"
  local build_args=(--build-arg "PYTHON_BASE=${python_base}")
  case "$target" in
    all)
      log "构建全部服务（backend + frontend + nginx）..."
      compose build "${build_args[@]}"
      ;;
    backend)
      log "仅构建 backend..."
      compose build "${build_args[@]}" backend
      ;;
    frontend)
      log "仅构建 frontend..."
      compose build frontend
      ;;
    nginx)
      log "仅构建 nginx..."
      compose build nginx
      ;;
    *)
      fail "未知构建目标: $target（可选: all|backend|frontend|nginx）"
      ;;
  esac
  ok "构建完成"
}

start_services() {
  local recreate="${1:-}"
  log "启动服务..."
  if [[ "$recreate" == "force" ]]; then
    compose up -d --force-recreate
  else
    compose up -d
  fi
  ok "服务已启动"
}

ensure_dependencies() {
  log "启动依赖服务（mongodb + frontend + nginx）..."
  compose up -d mongodb frontend nginx
  wait_mongodb_healthy
}

wait_mongodb_healthy() {
  log "等待 MongoDB 就绪（最多 60 秒）..."
  local i
  for i in $(seq 1 30); do
    if compose ps mongodb 2>/dev/null | grep -q '(healthy)'; then
      ok "MongoDB 已就绪"
      return 0
    fi
    sleep 2
  done
  warn "MongoDB 未就绪，backend 可能反复重启；请检查: compose logs mongodb"
  return 1
}

recreate_backend() {
  ensure_dependencies
  log "强制重建 backend 容器..."
  compose up -d --force-recreate --no-deps backend
  ok "backend 已重建"
}

wait_healthy() {
  log "等待服务就绪（最多 120 秒）..."
  local i local_url port
  port=$(grep -m1 '^NGINX_PORT=' .env 2>/dev/null | cut -d= -f2- | tr -d '\r' || true)
  if [[ -n "$port" ]]; then
    local_url="http://127.0.0.1:${port}/api/health"
  fi
  for i in $(seq 1 24); do
    if [[ -n "$local_url" ]] && curl -sf "$local_url" >/dev/null 2>&1; then
      ok "API 健康检查通过（本机 ${local_url}）"
      if ! curl -sf "${PUBLIC_URL}/api/health" >/dev/null 2>&1; then
        warn "本机正常但 ${PUBLIC_URL} 不可达：多为 ECS 公网回环或安全组未放行 ${port:-80}，请用浏览器从外网访问验证"
      fi
      return 0
    fi
    if curl -sf "${PUBLIC_URL}/api/health" >/dev/null 2>&1; then
      ok "API 健康检查通过"
      return 0
    fi
    if docker exec tradingagents-backend curl -sf http://localhost:8000/api/health >/dev/null 2>&1; then
      compose up -d nginx frontend 2>/dev/null || true
    fi
    sleep 5
  done
  warn "健康检查超时"
  [[ -n "$local_url" ]] && log "请试: curl -s ${local_url}"
  log "或: curl -s ${PUBLIC_URL}/api/health（外网/安全组）"
  log "backend 容器内探测:"
  docker exec tradingagents-backend curl -sf http://localhost:8000/api/health 2>&1 || true
  log "最近 backend 日志:"
  compose logs --tail=40 backend 2>/dev/null || true
  compose ps
  return 1
}

show_status() {
  compose ps
  echo ""
  log "访问地址:"
  echo "  运营后台/前端: ${PUBLIC_URL}"
  echo "  API 文档:      ${PUBLIC_URL}/api/docs"
  echo "  健康检查:      ${PUBLIC_URL}/api/health"
  echo "  信号推送:      ${PUBLIC_URL}/api/ares/signal"
  echo ""
  log "小程序 BASE_URL 建议设为: ${PUBLIC_URL}"
}

health_check() {
  log "检查 ${PUBLIC_URL}/api/health"
  curl -sf "${PUBLIC_URL}/api/health" | head -c 500 || fail "健康检查失败"
  echo ""
  ok "健康检查成功"
}

show_logs() {
  local svc="${1:-}"
  if [[ -n "$svc" ]]; then
    compose logs -f --tail=200 "$svc"
  else
    compose logs -f --tail=100
  fi
}

mysql_hint() {
  if grep -q '^MYSQL_HOST=' .env 2>/dev/null; then
    local host port
    host=$(grep '^MYSQL_HOST=' .env | cut -d= -f2- | tr -d '\r')
    port=$(grep '^MYSQL_PORT=' .env | cut -d= -f2- | tr -d '\r' || echo 3306)
    log "MySQL 配置: ${host}:${port}"
    warn "若 backend 容器连不上 MySQL，可将 MYSQL_HOST 改为宿主机网关 IP 或 host.docker.internal"
  fi
}

case "$MODE" in
  all)
    check_prerequisites
    ensure_dirs
    mysql_hint
    build_services all
    start_services force
    wait_healthy || true
    show_status
    ;;
  backend)
    check_prerequisites
    ensure_dirs
    mysql_hint
    build_services backend
    recreate_backend
    wait_healthy || true
    show_status
    ;;
  frontend)
    check_prerequisites
    build_services frontend
    compose up -d --force-recreate --no-deps frontend nginx
    wait_healthy || true
    show_status
    ;;
  up)
    check_prerequisites
    ensure_dirs
    start_services
    wait_healthy || true
    show_status
    ;;
  down)
    compose down
    ok "服务已停止"
    ;;
  restart)
    compose restart
    wait_healthy || true
    show_status
    ;;
  status)
    show_status
    ;;
  health)
    health_check
    ;;
  logs)
    show_logs "$SERVICE"
    ;;
  pull)
    check_prerequisites
    compose pull
    start_services force
    wait_healthy || true
    show_status
    ;;
  *)
    cat <<EOF
用法: $0 <command> [service]

命令:
  all       全量构建并启动（首次部署）
  backend   仅重建 backend（代码/API 变更，最常用）
  frontend  仅重建 frontend + nginx
  up        不构建，直接 docker compose up -d
  down      停止所有容器
  restart   重启所有容器
  pull      拉取镜像并启动
  status    查看状态与访问地址
  health    调用 /api/health
  logs      查看日志，可选服务名: backend|frontend|nginx|mongodb|redis

示例:
  $0 backend
  $0 logs backend
  PUBLIC_URL=http://47.95.5.18 $0 health
EOF
    exit 1
    ;;
esac
