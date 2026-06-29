#!/bin/sh
ARCH=$(uname -m)
case "$ARCH" in
  x86_64 | amd64) SB_ARCH="amd64" ;;
  aarch64 | arm64) SB_ARCH="arm64" ;;
  *) echo "不支持的系统架构: $ARCH"; exit 1 ;;
esac

# 自动检测并下载 Sing-box 内核
if [ ! -f "/usr/local/bin/sing-box" ]; then
    echo "正在追踪 GitHub 官方重定向获取 Sing-box 最新正式版版本号..."
    
    LATEST_VERSION=$(curl -sSL -I -o /dev/null -w "%{url_effective}" https://github.com/SagerNet/sing-box/releases/latest | awk -F'/' '{print $NF}' | sed 's/v//')
    LATEST_VERSION=${LATEST_VERSION:-"1.11.2"}
    
    echo "获取成功！检测到官方最新的正式版版本为: v${LATEST_VERSION}"
    FILENAME="sing-box-${LATEST_VERSION}-linux-${SB_ARCH}.tar.gz"
    DOWNLOAD_URL="https://github.com/SagerNet/sing-box/releases/download/v${LATEST_VERSION}/${FILENAME}"
    
    echo "正在从 ${DOWNLOAD_URL} 下载内核..."
    mkdir -p /tmp/sb_download
    if ! wget -O "/tmp/sb.tar.gz" "$DOWNLOAD_URL"; then
        echo "❌ 下载 v${LATEST_VERSION} 失败！"
        echo "🔄 尝试下载 v1.12.0 备用版本..."
        LATEST_VERSION="1.12.0"
        FILENAME="sing-box-${LATEST_VERSION}-linux-${SB_ARCH}.tar.gz"
        DOWNLOAD_URL="https://github.com/SagerNet/sing-box/releases/download/v${LATEST_VERSION}/${FILENAME}"
        wget -q -O "/tmp/sb.tar.gz" "$DOWNLOAD_URL"
    fi
    
    echo "正在解压并配置 Sing-box 内核..."
    tar -zxf /tmp/sb.tar.gz -C /tmp/
    cp /tmp/sing-box-*/sing-box /usr/local/bin/sing-box
    chmod +x /usr/local/bin/sing-box
    rm -rf /tmp/sb.tar.gz /tmp/sing-box-*
    echo "Sing-box 内核配置成功！"
fi

# 初始化配置文件（初始默认启动 Reality 在 443 端口，不开启 TLS 端口以避免无证书报错）
mkdir -p /etc/sing-box
if [ ! -f "/etc/sing-box/config.json" ]; then
    echo "首次运行，正在自动初始化出厂配置..."
    KEYS=$(/usr/local/bin/sing-box generate reality-keypair)
    PRIV_KEY=$(echo "$KEYS" | grep "PrivateKey:" | awk '{print $2}')
    PUB_KEY=$(echo "$KEYS" | grep "PublicKey:" | awk '{print $2}')
    SHORT_ID=$(openssl rand -hex 8)
    
    echo "$PUB_KEY" > /etc/sing-box/public_key.txt
    echo "$SHORT_ID" > /etc/sing-box/short_id.txt

    cat << INNER_EOF > /etc/sing-box/config.json
{
    "inbounds": [
        {
            "type": "anytls",
            "listen": "::",
            "listen_port": 443,
            "users": [
                {
                    "name": "admin",
                    "password": "adminpassword"
                }
            ],
            "padding_scheme": [
                "stop=3",
                "0=30-30",
                "1=100-400",
                "2=400-500,c,500-1000,c,500-1000,c,500-1000,c,500-1000"
            ],
            "tls": {
                "enabled": true,
                "server_name": "yahoo.com",
                "reality": {
                    "enabled": true,
                    "handshake": {
                        "server": "yahoo.com",
                        "server_port": 443
                    },
                    "private_key": "${PRIV_KEY}",
                    "short_id": "${SHORT_ID}"
                }
            }
        }
    ]
}
INNER_EOF
fi

# 启动 Web 面板
echo "启动 AnyTLS 多服务并存管理面板..."
exec python /app/panel.py
