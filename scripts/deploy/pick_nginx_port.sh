#!/usr/bin/env bash
# 在服务器上检测 Ares nginx 可用端口（80/8080/8888 常被 Dify 等占用）
set -euo pipefail

CANDIDATES=(18888 19080 28080 30088 18080 9080 10080 11080)

is_port_free() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ! ss -tln | grep -q ":${port} "
    return
  fi
  if command -v netstat >/dev/null 2>&1; then
    ! netstat -tln 2>/dev/null | grep -q ":${port} "
    return
  fi
  # 无法检测时假定可用
  return 0
}

echo "当前常用端口占用情况:"
for p in 80 8080 8888 "${CANDIDATES[@]}"; do
  if is_port_free "$p"; then
    echo "  ${p}  空闲"
  else
    echo "  ${p}  已占用"
  fi
done

for port in "${CANDIDATES[@]}"; do
  if is_port_free "$port"; then
    echo ""
    echo "推荐使用: ${port}"
    echo ""
    echo "在 .env 中设置:"
    echo "  NGINX_PORT=${port}"
    echo "  PUBLIC_URL=http://47.95.5.18:${port}"
    echo "  ALLOWED_ORIGINS=[\"http://47.95.5.18:${port}\",\"http://localhost:${port}\",\"http://127.0.0.1:${port}\"]"
    exit 0
  fi
done

echo "未找到候选空闲端口，请手动指定 NGINX_PORT" >&2
exit 1
