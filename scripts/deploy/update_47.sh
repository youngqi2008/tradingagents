#!/usr/bin/env bash
# =============================================================================
# 47.95.5.18 完整更新部署
#
# 流程:
#   1. 在 /root/yangqi/tradingagents 拉取最新 Git 代码
#   2. 同步到运行目录 /opt/tradingagents（不覆盖生产 .env / logs / data / uploads）
#   3. 在 /opt/tradingagents 执行 docker 构建与发布
#
# 用法（在服务器上）:
#   bash /root/yangqi/tradingagents/scripts/deploy/update_47.sh
#   bash /root/yangqi/tradingagents/scripts/deploy/update_47.sh all
#   bash /root/yangqi/tradingagents/scripts/deploy/update_47.sh backend
#   bash /root/yangqi/tradingagents/scripts/deploy/update_47.sh frontend
#
# 可选环境变量:
#   GIT_SRC=/root/yangqi/tradingagents
#   DEPLOY_DST=/opt/tradingagents
#   GIT_BRANCH=main          # 不设则拉取当前已检出分支
#   COMPOSE_FILE=docker-compose.hub.nginx.47.yml
#   COMPOSE_OVERRIDE=docker-compose.hub.nginx.47.dify-redis.yml
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

GIT_SRC="${GIT_SRC:-/root/yangqi/tradingagents}"
DEPLOY_DST="${DEPLOY_DST:-/opt/tradingagents}"
GIT_BRANCH="${GIT_BRANCH:-}"
MODE="${1:-all}"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.hub.nginx.47.yml}"
COMPOSE_OVERRIDE="${COMPOSE_OVERRIDE:-docker-compose.hub.nginx.47.dify-redis.yml}"

log()  { echo -e "${CYAN}[update]${NC} $*"; }
ok()   { echo -e "${GREEN}[ok]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*"; }
fail() { echo -e "${RED}[fail]${NC} $*"; exit 1; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "未找到命令: $1"
}

pull_source() {
  [[ -d "$GIT_SRC/.git" ]] || fail "不是 Git 仓库: $GIT_SRC"
  cd "$GIT_SRC"
  log "代码目录: $GIT_SRC"
  log "当前分支: $(git rev-parse --abbrev-ref HEAD) @ $(git rev-parse --short HEAD)"

  git fetch --all --prune
  if [[ -n "$GIT_BRANCH" ]]; then
    log "切换并拉取分支: $GIT_BRANCH"
    git checkout "$GIT_BRANCH"
    git pull --ff-only origin "$GIT_BRANCH"
  else
    local branch
    branch="$(git rev-parse --abbrev-ref HEAD)"
    log "拉取当前分支: $branch"
    git pull --ff-only origin "$branch"
  fi
  ok "代码已更新: $(git rev-parse --abbrev-ref HEAD) @ $(git log -1 --oneline)"
}

sync_to_runtime() {
  require_cmd rsync
  mkdir -p "$DEPLOY_DST"
  log "同步 $GIT_SRC  →  $DEPLOY_DST"
  log "保留运行目录: .env  logs/  data/  uploads/"

  rsync -a --delete \
    --exclude '.git/' \
    --exclude '.env' \
    --exclude '.env.local' \
    --exclude 'logs/' \
    --exclude 'data/' \
    --exclude 'uploads/' \
    --exclude 'node_modules/' \
    --exclude 'frontend/node_modules/' \
    --exclude 'miniprogram/node_modules/' \
    --exclude '__pycache__/' \
    --exclude '.pytest_cache/' \
    --exclude '.cursor/' \
    --exclude 'scripts/deploy/deploy.config' \
    "$GIT_SRC/" "$DEPLOY_DST/"

  if [[ ! -f "$DEPLOY_DST/.env" ]]; then
    warn "$DEPLOY_DST/.env 不存在"
    if [[ -f "$GIT_SRC/.env" ]]; then
      cp -a "$GIT_SRC/.env" "$DEPLOY_DST/.env"
      warn "已从 Git 目录复制一份 .env，请核对生产密钥"
    elif [[ -f "$DEPLOY_DST/scripts/deploy/env.47.95.5.18.production.env" ]]; then
      cp -a "$DEPLOY_DST/scripts/deploy/env.47.95.5.18.production.env" "$DEPLOY_DST/.env"
      warn "已用生产模板创建 .env，请立即填写密钥"
    else
      fail "运行目录没有 .env，无法部署"
    fi
  else
    ok "已保留现有 $DEPLOY_DST/.env"
  fi

  mkdir -p "$DEPLOY_DST/logs" "$DEPLOY_DST/data" "$DEPLOY_DST/uploads"
  ok "代码同步完成"
}

deploy_runtime() {
  chmod +x "$DEPLOY_DST/scripts/deploy/deploy_prod.sh" \
    "$DEPLOY_DST/scripts/deploy/pull_base_images.sh" 2>/dev/null || true

  export COMPOSE_FILE
  export COMPOSE_OVERRIDE
  cd "$DEPLOY_DST"
  log "开始发布 MODE=$MODE  COMPOSE_FILE=$COMPOSE_FILE"
  [[ -n "$COMPOSE_OVERRIDE" ]] && log "COMPOSE_OVERRIDE=$COMPOSE_OVERRIDE"
  bash "$DEPLOY_DST/scripts/deploy/deploy_prod.sh" "$MODE"
}

case "$MODE" in
  all|backend|frontend|up|status|health|restart)
    ;;
  -h|--help|help)
    sed -n '2,22p' "$0"
    exit 0
    ;;
  *)
    fail "未知模式: $MODE（all|backend|frontend|up|status|health|restart）"
    ;;
esac

require_cmd git
require_cmd docker
docker compose version >/dev/null 2>&1 || fail "需要 Docker Compose v2"

echo "========================================"
echo " Ares 更新部署  47.95.5.18"
echo " 源码: $GIT_SRC"
echo " 运行: $DEPLOY_DST"
echo " 模式: $MODE"
echo "========================================"

pull_source
sync_to_runtime
deploy_runtime
ok "全部完成"
