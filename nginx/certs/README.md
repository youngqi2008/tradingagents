# SSL 证书目录（勿提交私钥到 Git）
#
# 放入两个文件（文件名固定）:
#   fullchain.pem   # 证书链（Let's Encrypt 的 fullchain.pem）
#   privkey.pem     # 私钥
#
# 方式 A：Let's Encrypt（推荐，需已有域名解析到本机）
#   # 若 80 被占用，用 DNS 验证或临时停占用 80 的服务
#   certbot certonly --standalone -d mp.example.com
#   cp /etc/letsencrypt/live/mp.example.com/fullchain.pem /opt/tradingagents/nginx/certs/
#   cp /etc/letsencrypt/live/mp.example.com/privkey.pem /opt/tradingagents/nginx/certs/
#   chmod 644 fullchain.pem && chmod 600 privkey.pem
#
# 方式 B：阿里云 / 腾讯云 SSL 控制台下载 Nginx 格式证书后改名拷贝到此目录
#
# 微信小程序:
#   request 合法域名 = https://mp.example.com   （仅域名，无端口、无路径）
#   BASE_URL = 'https://mp.example.com'
