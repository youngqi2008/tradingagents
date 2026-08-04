#!/usr/bin/env bash
# 在国内 ECS 预拉取 compose 依赖的基础镜像（避免 docker hub / gcr 超时）
set -euo pipefail

MONGO_TAG="${MONGO_TAG:-4.4}"
MONGO_IMAGE="${MONGO_IMAGE:-mongo:${MONGO_TAG}}"

log() { echo "[pull] $*"; }

pull_and_tag() {
  local mirror="$1"
  local name="$2"
  log "尝试: ${mirror}"
  if docker pull "${mirror}"; then
    docker tag "${mirror}" "${name}"
    log "已标记为 ${name}"
    return 0
  fi
  return 1
}

pull_mongo() {
  if docker image inspect "${MONGO_IMAGE}" >/dev/null 2>&1; then
    log "本地已有 ${MONGO_IMAGE}，跳过 Mongo"
    return 0
  fi
  log "拉取 MongoDB ${MONGO_TAG} ..."
  pull_and_tag "docker.m.daocloud.io/library/mongo:${MONGO_TAG}" "mongo:${MONGO_TAG}" && return 0
  pull_and_tag "registry.cn-hangzhou.aliyuncs.com/library/mongo:${MONGO_TAG}" "mongo:${MONGO_TAG}" && return 0
  docker pull "mongo:${MONGO_TAG}" && log "已从 Docker Hub 拉取 mongo:${MONGO_TAG}" && return 0
  echo "[pull] Mongo 拉取失败，可设 .env: MONGO_IMAGE=docker.m.daocloud.io/library/mongo:${MONGO_TAG}" >&2
  return 1
}

pull_frontend_base() {
  if docker image inspect "node:22-alpine" >/dev/null 2>&1; then
    log "本地已有 node:22-alpine，跳过"
  else
    log "拉取 node:22-alpine（前端构建）..."
    pull_and_tag "docker.m.daocloud.io/library/node:22-alpine" "node:22-alpine" \
      || docker pull "node:22-alpine" \
      || warn_node=1
  fi
  if ! docker image inspect "nginx:alpine" >/dev/null 2>&1; then
    pull_and_tag "docker.m.daocloud.io/library/nginx:alpine" "nginx:alpine" \
      || docker pull "nginx:alpine" \
      || true
  fi
}

warn_node=0
pull_mongo || exit 1
# 默认预拉前端基础镜像，避免 build 时 metadata 超时；仅需 mongo 时: PULL_NODE_IMAGE=0
if [[ "${PULL_NODE_IMAGE:-1}" != "0" ]]; then
  pull_frontend_base
  [[ "$warn_node" == "1" ]] && echo "[pull] node:22-alpine 未拉取成功，构建 frontend 时可能重试 Docker Hub" >&2
fi
log "基础镜像检查完成"
