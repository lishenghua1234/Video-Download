#!/bin/bash
# ============================================================
# VideoSnap 视频下载器 - 甲骨云一键部署脚本
# 服务器：Ubuntu (Oracle Cloud VM.Standard.E2.1.Micro)
# 用法：chmod +x deploy.sh && sudo bash deploy.sh
# ============================================================

set -e

# -------------------- 配置区域 --------------------
APP_NAME="videosnap"
APP_DIR="/opt/videosnap"
DOMAIN="downloadvideo.catingking.dpdns.org"
APP_PORT=8001
SWAP_SIZE="2G"
REPO_URL="https://github.com/lishenghua1234/Video-Download.git"
# --------------------------------------------------

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err() { echo -e "${RED}[✗]${NC} $1"; exit 1; }

echo ""
echo "=========================================="
echo "  🎬 VideoSnap 部署脚本"
echo "=========================================="
echo ""

# 检查 root 权限
if [ "$EUID" -ne 0 ]; then
    err "请使用 sudo 运行此脚本"
fi

# ===== 第1步：创建交换空间 =====
echo ""
echo "--- [1/8] 创建 ${SWAP_SIZE} 交换空间 ---"
if [ ! -f /swapfile ]; then
    fallocate -l ${SWAP_SIZE} /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    # 写入 fstab 持久化
    grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
    log "交换空间创建完成 (${SWAP_SIZE})"
else
    log "交换空间已存在，跳过"
fi

# ===== 第2步：更新系统、安装基础工具 =====
echo ""
echo "--- [2/8] 更新系统并安装基础工具 ---"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y -qq
apt-get upgrade -y -qq
apt-get install -y -qq curl wget git build-essential nginx
log "基础工具安装完成"

# ===== 第3步：安装 Node.js 18.x =====
echo ""
echo "--- [3/8] 安装 Node.js ---"
if ! command -v node &> /dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash -
    apt-get install -y -qq nodejs
    log "Node.js $(node -v) 安装完成"
else
    log "Node.js $(node -v) 已安装，跳过"
fi

# ===== 第4步：安装 uv =====
echo ""
echo "--- [4/8] 安装 uv (Python 包管理器) ---"
if ! command -v uv &> /dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    log "uv 安装完成"
fi
# 确保 uv 在 PATH 中（当前会话和全局）
export PATH="/root/.local/bin:$PATH"
# 为所有用户添加 uv 到 PATH
cat > /etc/profile.d/uv-path.sh << 'EOF'
export PATH="/root/.local/bin:$PATH"
EOF
log "uv 路径配置完成: $(which uv)"

# ===== 第5步：部署应用代码 =====
echo ""
echo "--- [5/8] 部署应用代码 ---"
mkdir -p ${APP_DIR}

if [ ! -f "${APP_DIR}/main.py" ]; then
    log "正在从 GitHub 克隆代码..."
    git clone ${REPO_URL} ${APP_DIR}
    log "代码克隆完成"
else
    warn "代码已存在于 ${APP_DIR}，跳过克隆"
    warn "如需更新，请运行: cd ${APP_DIR} && git pull"
fi

cd ${APP_DIR}

# 使用 uv 同步 Python 依赖（uv 会自动下载安装对应版本的 Python）
log "通过 uv 安装 Python 和项目依赖（首次可能需要几分钟）..."
uv sync

# 安装 ig_node_module 的 Node.js 依赖
if [ -d "${APP_DIR}/ig_node_module" ] && [ -f "${APP_DIR}/ig_node_module/package.json" ]; then
    log "安装 ig_node_module Node.js 依赖..."
    cd ${APP_DIR}/ig_node_module
    npm install --production
    cd ${APP_DIR}
fi

log "应用代码和依赖部署完成"

# ===== 第6步：配置 iptables（甲骨云特有！） =====
echo ""
echo "--- [6/8] 配置 iptables 防火墙 ---"
# 甲骨云 Ubuntu 默认 iptables 会阻塞 80/443 端口，即使安全列表已放行
# 必须在系统层面也放行这些端口
if ! iptables -C INPUT -p tcp --dport 80 -j ACCEPT 2>/dev/null; then
    iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
    log "iptables: 端口 80 已放行"
else
    log "iptables: 端口 80 已放行（之前已配置）"
fi

if ! iptables -C INPUT -p tcp --dport 443 -j ACCEPT 2>/dev/null; then
    iptables -I INPUT 7 -m state --state NEW -p tcp --dport 443 -j ACCEPT
    log "iptables: 端口 443 已放行"
else
    log "iptables: 端口 443 已放行（之前已配置）"
fi

# 持久化 iptables 规则
apt-get install -y -qq iptables-persistent
netfilter-persistent save 2>/dev/null || true
log "iptables 规则已持久化"

# ===== 第7步：配置 systemd 服务 =====
echo ""
echo "--- [7/8] 配置 systemd 服务 ---"

# 获取 uv 的实际路径
UV_PATH=$(which uv)

cat > /etc/systemd/system/${APP_NAME}.service << EOF
[Unit]
Description=VideoSnap 视频下载服务
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${APP_DIR}
ExecStart=${UV_PATH} run uvicorn main:app --host 127.0.0.1 --port ${APP_PORT}
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

# 环境变量
Environment="PATH=/root/.local/bin:/usr/local/bin:/usr/bin:/bin"
Environment="HOME=/root"

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ${APP_NAME}
systemctl restart ${APP_NAME}

# 等待服务启动
sleep 3
if systemctl is-active --quiet ${APP_NAME}; then
    log "VideoSnap 服务已成功启动"
else
    warn "服务可能启动失败，请检查: journalctl -u ${APP_NAME} -n 20"
fi

# ===== 第8步：配置 Nginx =====
echo ""
echo "--- [8/8] 配置 Nginx 反向代理 ---"

cat > /etc/nginx/sites-available/${APP_NAME} << 'NGINXEOF'
server {
    listen 80;
    server_name downloadvideo.catingking.dpdns.org;

    # 客户端上传/下载大小限制（视频文件可能很大）
    client_max_body_size 1G;

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # 视频下载/合并需要较长超时
        proxy_connect_timeout 60s;
        proxy_send_timeout 600s;
        proxy_read_timeout 600s;

        # 关闭缓冲，支持流式传输（视频下载必须）
        proxy_buffering off;
        proxy_request_buffering off;
    }
}
NGINXEOF

# 启用配置
ln -sf /etc/nginx/sites-available/${APP_NAME} /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# 验证 Nginx 配置
nginx -t || err "Nginx 配置验证失败"

systemctl restart nginx
systemctl enable nginx
log "Nginx 反向代理配置完成"

# ===== 部署完成 =====
echo ""
echo "=========================================="
echo "  ✅ 部署完成！"
echo "=========================================="
echo ""
echo "📋 接下来请在 Cloudflare 添加 DNS 记录："
echo ""
echo "  类型:     A"
echo "  名称:     downloadvideo"
echo "  IPv4地址: 161.153.113.118"
echo "  代理状态: 已代理 ☁️ (橙色云朵)"
echo ""
echo "  Cloudflare SSL/TLS 设置为: 灵活 (Flexible)"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📌 常用运维命令："
echo "  查看状态:  systemctl status ${APP_NAME}"
echo "  查看日志:  journalctl -u ${APP_NAME} -f"
echo "  重启服务:  systemctl restart ${APP_NAME}"
echo "  更新代码:  cd ${APP_DIR} && git pull && uv sync && systemctl restart ${APP_NAME}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
