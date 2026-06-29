import os
import json
import secrets
import base64
import urllib.parse
import subprocess
import socket
from flask import Flask, request, render_template_string, redirect, session, jsonify

app = Flask(__name__)
app.secret_key = 'singbox-reality-panel-key'

CONFIG_DIR = '/etc/sing-box'
CONFIG_PATH = os.path.join(CONFIG_DIR, 'config.json')
PUB_KEY_PATH = os.path.join(CONFIG_DIR, 'public_key.txt')
PWD_PATH = os.path.join(CONFIG_DIR, 'panel_pwd.txt')
IP_PATH = os.path.join(CONFIG_DIR, 'server_ip.txt')
CERT_SOURCE_PATH = os.path.join(CONFIG_DIR, 'cert_source.txt')
SUB_TOKEN_PATH = os.path.join(CONFIG_DIR, 'sub_token.txt')

CERT_FILE = '/etc/sing-box/cert.pem'
KEY_FILE = '/etc/sing-box/key.pem'

sb_process = None

# --- 工具函数 ---
def get_file_content(path, default=""):
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                return f.read().strip()
        except:
            pass
    return default

def write_file_content(path, content):
    try:
        with open(path, 'w') as f:
            f.write(content.strip() + '\n')
    except Exception as e:
        print(f"写入文件 {path} 失败:", e)

def get_panel_password():
    return get_file_content(PWD_PATH, 'admin')

def get_server_ip():
    if os.path.exists(IP_PATH):
        return get_file_content(IP_PATH)
    try:
        import urllib.request
        return urllib.request.urlopen('https://api.ipify.org', timeout=3).read().decode('utf-8')
    except:
        return "127.0.0.1"

def get_sub_token():
    token = get_file_content(SUB_TOKEN_PATH)
    if not token:
        token = secrets.token_hex(16)
        write_file_content(SUB_TOKEN_PATH, token)
    return token

# 检测特定端口是否被宿主机其他进程占用
def is_port_occupied(port):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.4)
            # 尝试绑定端口，如果成功绑定说明该端口此时未被占用
            s.bind(('0.0.0.0', int(port)))
        return False
    except:
        return True

# 使用 OpenSSL 自动生成自签名证书
def generate_self_signed_cert(domain, cert_path, key_path):
    try:
        cmd = [
            "openssl", "req", "-x509", "-newkey", "rsa:2048", 
            "-keyout", key_path, "-out", cert_path, 
            "-sha256", "-days", "3650", "-nodes",
            "-subj", f"/CN={domain}"
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except Exception as e:
        print("生成自签名证书失败:", e)
        return False

# 管理 Sing-box 子进程
def restart_singbox_kernel():
    global sb_process
    if sb_process:
        try:
            sb_process.terminate()
            sb_process.wait(timeout=5)
        except Exception as e:
            print("停止旧进程出错:", e)
            
    print("正在启动 Sing-box 进程...")
    sb_process = subprocess.Popen(["/usr/local/bin/sing-box", "run", "-c", CONFIG_PATH])

# 加载配置
def load_config_data():
    config = {
        'users': [('admin', 'adminpassword')],
        'padding_scheme': "stop=3\n0=30-30\n1=100-400\n2=400-500,c,500-1000,c,500-1000,c,500-1000,c,500-1000",
        'server_ip': get_server_ip(),
        'sub_token': get_sub_token(),
        
        # Reality 默认参数
        'reality_enabled': False,
        'reality_port': '443',
        'reality_sni': 'yahoo.com',
        'private_key': '',
        'public_key': get_file_content(PUB_KEY_PATH),
        'short_id': '',
        
        # Standard TLS 默认参数
        'tls_enabled': False,
        'tls_port': '8443',
        'tls_sni': 'yourdomain.com',
        'cert_source': get_file_content(CERT_SOURCE_PATH, 'self_signed'),
        'cert_content': get_file_content(CERT_FILE),
        'key_content': get_file_content(KEY_FILE),
    }
    
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r') as f:
                data = json.load(f)
            inbounds = data.get('inbounds', [])
            
            if inbounds:
                first_ib = inbounds[0]
                users_list = []
                for u in first_ib.get('users', []):
                    users_list.append((u.get('name'), u.get('password')))
                if users_list:
                    config['users'] = users_list
                config['padding_scheme'] = '\n'.join(first_ib.get('padding_scheme', []))
            
            for ib in inbounds:
                tls = ib.get('tls', {})
                reality = tls.get('reality', {})
                if tls.get('enabled') and reality.get('enabled'):
                    config['reality_enabled'] = True
                    config['reality_port'] = str(ib.get('listen_port', 443))
                    config['reality_sni'] = tls.get('server_name', 'yahoo.com')
                    config['private_key'] = reality.get('private_key', '')
                    config['short_id'] = reality.get('short_id', '')
                elif tls.get('enabled'):
                    config['tls_enabled'] = True
                    config['tls_port'] = str(ib.get('listen_port', 8443))
                    config['tls_sni'] = tls.get('server_name', 'yourdomain.com')
                    
        except Exception as e:
            print("解析 config.json 失败:", e)
            
    return config

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Sing-box AnyTLS 融合版面板</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/qrcodejs@1.0.0/qrcode.min.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Inter', sans-serif; }
    </style>
</head>
<body class="bg-slate-50 text-slate-800 min-h-screen">
    <div class="container mx-auto max-w-4xl py-10 px-4 md:px-6">
        
        <!-- 头部 Card -->
        <div class="bg-white rounded-2xl shadow-sm border border-slate-100 p-6 mb-6">
            <div class="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div>
                    <h1 class="text-2xl font-bold tracking-tight text-slate-900">AnyTLS 融合控制台</h1>
                    <p class="text-sm text-slate-500 mt-1">集成一键 Reality 密钥对生成、Standard TLS自签名证书及高安全动态订阅</p>
                </div>
                <div class="flex items-center gap-3">
                    <!-- 运行状态探针 -->
                    <div class="flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-semibold border" id="statusBadge">
                        <span class="w-2.5 h-2.5 rounded-full" id="statusDot"></span>
                        <span id="statusText">正在检测状态...</span>
                    </div>
                    <a href="/logout" class="text-xs bg-slate-100 hover:bg-slate-200 text-slate-700 px-4 py-2 rounded-lg font-semibold transition">安全退出</a>
                </div>
            </div>
        </div>

        <!-- 导航选项卡 -->
        <div class="flex gap-2 mb-6 bg-slate-200/60 p-1 rounded-xl max-w-xs">
            <button onclick="switchTab('config-tab', this)" class="tab-btn flex-1 text-sm font-medium py-2 rounded-lg text-indigo-700 bg-white shadow-sm transition">系统配置</button>
            <button onclick="switchTab('security-tab', this)" class="tab-btn flex-1 text-sm font-medium py-2 rounded-lg text-slate-600 hover:text-slate-900 transition">面板安全</button>
        </div>

        <!-- TAB 1: 系统配置 -->
        <div id="config-tab" class="tab-content space-y-6">
            
            <!-- 订阅管理 Card -->
            <div class="bg-white rounded-2xl shadow-sm border border-slate-100 p-6 space-y-4">
                <div class="flex items-center justify-between border-b border-slate-100 pb-3">
                    <div class="flex items-center gap-2">
                        <span class="text-xl">🔒</span>
                        <h3 class="font-semibold text-slate-900">安全订阅分发中心</h3>
                    </div>
                    <span class="text-[10px] bg-emerald-50 text-emerald-700 font-bold px-2 py-0.5 rounded border border-emerald-100">已启用 Dynamic-Token 防扫</span>
                </div>
                <p class="text-xs text-slate-500">外部扫描器无法通过通用路径探测您的配置。如需分享或导入节点，请一键复制以下高强度安全订阅链接：</p>
                <div class="flex gap-2">
                    <input type="text" id="subUrlInput" readonly class="flex-1 bg-slate-50 border border-slate-200 rounded-xl px-4 py-2 text-xs text-slate-600 font-mono outline-none">
                    <button type="button" onclick="copySubUrl()" class="bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold px-5 rounded-xl transition shadow-sm">复制订阅</button>
                </div>
            </div>

            <form id="configForm" class="space-y-6">
                <!-- 公共网络配置 -->
                <div class="bg-white rounded-2xl shadow-sm border border-slate-100 p-6 space-y-4">
                    <h3 class="font-semibold text-slate-900 border-b border-slate-100 pb-3 flex items-center gap-2">🌐 公共核心参数</h3>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                            <label class="block text-xs font-semibold text-slate-500 mb-1.5">服务器公网 IP (用于节点导出)</label>
                            <input type="text" name="server_ip" value="{{ config.server_ip }}" class="w-full border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition" required>
                        </div>
                        <div>
                            <label class="block text-xs font-semibold text-slate-500 mb-1.5">自定义订阅安全 Token / 专属路径</label>
                            <div class="flex gap-2">
                                <input type="text" name="sub_token" id="subTokenInput" value="{{ config.sub_token }}" oninput="updateSubUrlDisplay(this.value)" class="flex-1 border border-slate-200 rounded-xl px-4 py-2 text-xs font-mono outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition" required>
                                <button type="button" onclick="randomizeSubToken()" class="bg-slate-100 hover:bg-slate-200 text-slate-700 px-4 rounded-xl text-xs font-semibold transition">随机</button>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- 模式一: Reality -->
                <div class="bg-white rounded-2xl shadow-sm border border-slate-100 p-6 space-y-4">
                    <div class="flex items-center justify-between border-b border-slate-100 pb-3">
                        <div class="flex items-center gap-2.5">
                            <input type="checkbox" name="reality_enabled" id="realityEnabledCheckbox" onchange="toggleServiceBlocks()" class="w-4 h-4 text-indigo-600 border-slate-300 rounded focus:ring-indigo-500" {% if config.reality_enabled %}checked{% endif %}>
                            <label for="realityEnabledCheckbox" class="font-semibold text-slate-900 cursor-pointer">服务一: AnyTLS + Reality 模式</label>
                        </div>
                        <button type="button" id="genKeyBtn" onclick="generateNewKeys()" class="text-xs bg-slate-50 hover:bg-slate-100 text-indigo-600 px-3 py-1.5 rounded-lg border border-slate-200 font-medium transition">
                            🔄 重新生成 Reality 密钥对
                        </button>
                    </div>
                    
                    <div id="realityFields" class="space-y-4">
                        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div>
                                <label class="block text-xs font-semibold text-slate-500 mb-1.5">监听端口 (Reality Port)</label>
                                <input type="number" name="reality_port" id="realityPortInput" value="{{ config.reality_port }}" class="w-full border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition" min="1" max="65535">
                            </div>
                            <div>
                                <label class="block text-xs font-semibold text-slate-500 mb-1.5">目标伪装域名 (Reality SNI)</label>
                                <input type="text" name="reality_sni" id="realitySniInput" value="{{ config.reality_sni }}" class="w-full border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition">
                            </div>
                        </div>
                        <div>
                            <label class="block text-[11px] font-semibold text-slate-400 mb-1">服务端私钥 (private_key - 绝对保密)</label>
                            <input type="text" name="private_key" id="privateKeyInput" value="{{ config.private_key }}" class="w-full border border-slate-200 rounded-xl px-4 py-2 text-xs font-mono outline-none bg-slate-50 text-slate-500" readonly>
                        </div>
                        <div>
                            <label class="block text-[11px] font-semibold text-slate-400 mb-1">客户端公钥 (public_key - 客户端链接需要)</label>
                            <input type="text" name="public_key" id="publicKeyInput" value="{{ config.public_key }}" class="w-full border border-slate-200 rounded-xl px-4 py-2 text-xs font-mono outline-none bg-slate-50 text-slate-500" readonly>
                        </div>
                        <div>
                            <label class="block text-[11px] font-semibold text-slate-400 mb-1">短期握手标识 ID (short_id)</label>
                            <div class="flex gap-2">
                                <input type="text" name="short_id" id="shortIdInput" value="{{ config.short_id }}" class="flex-1 border border-slate-200 rounded-xl px-4 py-2 text-xs font-mono outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition">
                                <button type="button" onclick="generateNewShortId()" class="bg-slate-100 hover:bg-slate-200 text-slate-700 px-4 rounded-xl text-xs font-semibold transition">随机</button>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- 模式二: Standard TLS -->
                <div class="bg-white rounded-2xl shadow-sm border border-slate-100 p-6 space-y-4">
                    <div class="flex items-center justify-between border-b border-slate-100 pb-3">
                        <div class="flex items-center gap-2.5">
                            <input type="checkbox" name="tls_enabled" id="tlsEnabledCheckbox" onchange="toggleServiceBlocks()" class="w-4 h-4 text-indigo-600 border-slate-300 rounded focus:ring-indigo-500" {% if config.tls_enabled %}checked{% endif %}>
                            <label for="tlsEnabledCheckbox" class="font-semibold text-slate-900 cursor-pointer">服务二: AnyTLS + Standard TLS 证书模式</label>
                        </div>
                    </div>
                    
                    <div id="tlsFields" class="space-y-4">
                        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div>
                                <label class="block text-xs font-semibold text-slate-500 mb-1.5">监听端口 (TLS Port)</label>
                                <input type="number" name="tls_port" id="tlsPortInput" value="{{ config.tls_port }}" class="w-full border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition" min="1" max="65535">
                            </div>
                            <div>
                                <label class="block text-xs font-semibold text-slate-500 mb-1.5">证书绑定域名/伪装域名 (Domain)</label>
                                <input type="text" name="tls_sni" id="tlsSniInput" value="{{ config.tls_sni }}" class="w-full border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition" placeholder="例如 x.606699.xyz">
                            </div>
                        </div>

                        <!-- 证书来源选择 -->
                        <div class="bg-slate-50/50 p-4 rounded-xl border border-slate-100 space-y-2.5">
                            <label class="block text-xs font-bold text-slate-700">📜 证书来源管理</label>
                            <div class="flex flex-col sm:flex-row gap-4 text-sm text-slate-600">
                                <label class="flex items-center gap-2 cursor-pointer">
                                    <input type="radio" name="cert_source" value="self_signed" onchange="toggleCertSource()" {% if config.cert_source == 'self_signed' %}checked{% endif %} class="w-4 h-4 text-indigo-600">
                                    自动生成自签名证书 (基于上方绑定域名)
                                </label>
                                <label class="flex items-center gap-2 cursor-pointer">
                                    <input type="radio" name="cert_source" value="manual" onchange="toggleCertSource()" {% if config.cert_source == 'manual' %}checked{% endif %} class="w-4 h-4 text-indigo-600">
                                    手动贴入真实域名证书 (CA 签发)
                                </label>
                            </div>
                        </div>

                        <div id="manualCertFields" class="space-y-3 hidden">
                            <div>
                                <label class="block text-[11px] font-semibold text-slate-400 mb-1">公钥 PEM 内容 (cert.pem / fullchain.cer)</label>
                                <textarea name="cert_content" rows="4" class="w-full border border-slate-200 rounded-xl p-3 font-mono text-xs outline-none bg-white focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition" placeholder="-----BEGIN CERTIFICATE-----&#10;...公钥内容...&#10;-----END CERTIFICATE-----">{{ config.cert_content }}</textarea>
                            </div>
                            <div>
                                <label class="block text-[11px] font-semibold text-slate-400 mb-1">私钥 PEM 内容 (key.pem / private.key)</label>
                                <textarea name="key_content" rows="4" class="w-full border border-slate-200 rounded-xl p-3 font-mono text-xs outline-none bg-white focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition" placeholder="-----BEGIN PRIVATE KEY-----&#10;...私钥内容...&#10;-----END PRIVATE KEY-----">{{ config.key_content }}</textarea>
                            </div>
                        </div>
                        
                        <div id="selfSignedNote" class="text-xs text-indigo-700 bg-indigo-50/50 p-3 rounded-xl border border-indigo-100/50 leading-relaxed hidden">
                            💡 <b>提示</b>：系统在保存时将自动调用 OpenSSL 签发一个 10 年期的自签名证书。导出的链接会自动追加 <code>allowInsecure=1</code> 安全参数，以便客户端成功连通。
                        </div>
                    </div>
                </div>

                <!-- 账号管理 -->
                <div class="bg-white rounded-2xl shadow-sm border border-slate-100 p-6 space-y-4">
                    <h3 class="font-semibold text-slate-900 border-b border-slate-100 pb-3 flex items-center justify-between">
                        <span>👥 用户配置与一键提取</span>
                        <button type="button" onclick="addUserRow()" class="text-xs text-indigo-600 hover:text-indigo-700 font-semibold transition">+ 新增账户</button>
                    </h3>
                    <div id="usersContainer" class="space-y-3">
                        {% for user, pwd in config.users %}
                        <div class="flex flex-col sm:flex-row gap-2 user-row items-center bg-slate-50/50 p-3 rounded-xl border border-slate-100">
                            <input type="text" name="username[]" value="{{ user }}" placeholder="用户名" class="w-full sm:flex-1 border border-slate-200 rounded-lg px-3 py-1.5 text-sm outline-none bg-white focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition" required>
                            <input type="text" name="password[]" value="{{ pwd }}" placeholder="密码" class="w-full sm:flex-1 border border-slate-200 rounded-lg px-3 py-1.5 text-sm outline-none bg-white focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition" required>
                            <div class="flex gap-2 w-full sm:w-auto mt-2 sm:mt-0">
                                <button type="button" onclick="showShare('{{ user }}', '{{ pwd }}')" class="flex-1 sm:flex-none bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-1.5 rounded-lg text-xs font-semibold transition shadow-sm">提取节点</button>
                                <button type="button" onclick="removeUserRow(this)" class="bg-rose-500 hover:bg-rose-600 text-white px-3 py-1.5 rounded-lg text-xs font-semibold transition">删除</button>
                            </div>
                        </div>
                        {% endfor %}
                    </div>
                </div>

                <!-- Padding-Scheme -->
                <div class="bg-white rounded-2xl shadow-sm border border-slate-100 p-6 space-y-3">
                    <h3 class="font-semibold text-slate-900 border-b border-slate-100 pb-3 flex items-center gap-2">📉 自定义混淆策略 (Padding-Scheme)</h3>
                    <textarea name="padding_scheme" id="paddingInput" rows="3" class="w-full border border-slate-200 rounded-xl p-3 font-mono text-xs outline-none bg-white focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition" required>{{ config.padding_scheme }}</textarea>
                </div>

                <!-- 保存提交 -->
                <div class="pt-4 border-t border-slate-100 flex flex-col sm:flex-row items-center justify-between gap-4">
                    <button type="submit" class="w-full sm:w-auto bg-indigo-600 hover:bg-indigo-700 text-white font-bold px-10 py-3.5 rounded-xl transition shadow-md hover:shadow-lg">
                        保存并重启内核
                    </button>
                    <span id="statusMsg" class="text-sm font-semibold"></span>
                </div>
            </form>
        </div>

        <!-- TAB 2: 安全设置 -->
        <div id="security-tab" class="tab-content hidden space-y-6">
            <div class="bg-white rounded-2xl shadow-sm border border-slate-100 p-6 space-y-4">
                <h3 class="text-lg font-bold text-slate-900 border-b border-slate-100 pb-3">🔑 修改面板管理密码</h3>
                <form id="pwdForm" class="space-y-4">
                    <div>
                        <label class="block text-xs font-semibold text-slate-500 mb-1.5">输入新密码</label>
                        <input type="password" name="new_password" class="w-full md:w-1/2 border border-slate-200 rounded-xl px-4 py-2.5 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition" required minlength="4">
                    </div>
                    <button type="submit" class="bg-indigo-600 hover:bg-indigo-700 text-white font-semibold px-6 py-2.5 rounded-xl transition shadow-sm">确认保存</button>
                    <span id="pwdStatus" class="text-sm font-semibold block mt-1"></span>
                </form>
            </div>
        </div>
    </div>

    <!-- 二维码与一键导入弹窗 -->
    <div id="shareModal" class="fixed inset-0 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center hidden p-4 z-50">
        <div class="bg-white rounded-2xl shadow-xl max-w-lg w-full p-6 space-y-4 overflow-y-auto max-h-[90vh]">
            <div class="flex justify-between items-center border-b border-slate-100 pb-3">
                <h3 class="font-bold text-slate-900 text-lg">节点一键导入</h3>
                <button onclick="closeShare()" class="text-slate-400 hover:text-slate-600 text-2xl font-semibold leading-none">&times;</button>
            </div>
            
            <!-- Reality 节点分享区 -->
            <div id="modalRealitySection" class="hidden space-y-3 border-b border-slate-100 pb-4">
                <h4 class="font-bold text-sm text-indigo-700">🟢 AnyTLS + Reality 节点</h4>
                <div class="flex gap-2">
                    <input type="text" id="shareUrlReality" readonly class="flex-1 border border-slate-200 bg-slate-50 rounded-xl px-3 py-1.5 text-xs outline-none">
                    <button onclick="copyToClipboard('shareUrlReality')" class="bg-indigo-600 text-white text-xs px-4 rounded-xl">复制</button>
                </div>
                <div class="flex flex-col items-center justify-center p-3 bg-slate-50 rounded-xl">
                    <div id="qrcodeReality" class="border p-2 bg-white rounded-lg shadow-sm"></div>
                </div>
            </div>

            <!-- Standard TLS 节点分享区 -->
            <div id="modalTlsSection" class="hidden space-y-3">
                <h4 class="font-bold text-sm text-emerald-700">🟢 AnyTLS + Standard TLS 证书节点</h4>
                <div class="flex gap-2">
                    <input type="text" id="shareUrlTls" readonly class="flex-1 border border-slate-200 bg-slate-50 rounded-xl px-3 py-1.5 text-xs outline-none">
                    <button onclick="copyToClipboard('shareUrlTls')" class="bg-emerald-600 text-white text-xs px-4 rounded-xl">复制</button>
                </div>
                <div class="flex flex-col items-center justify-center p-3 bg-slate-50 rounded-xl">
                    <div id="qrcodeTls" class="border p-2 bg-white rounded-lg shadow-sm"></div>
                </div>
            </div>
        </div>
    </div>

    <script>
        function switchTab(tabId, btn) {
            document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
            document.getElementById(tabId).classList.remove('hidden');
            
            document.querySelectorAll('.tab-btn').forEach(el => {
                el.className = "tab-btn flex-1 text-sm font-medium py-2 rounded-lg text-slate-600 hover:text-slate-900 transition";
            });
            btn.className = "tab-btn flex-1 text-sm font-medium py-2 rounded-lg text-indigo-700 bg-white shadow-sm transition";
        }

        // 实时获取内核运行状态并在顶部高亮
        function checkKernelStatus() {
            fetch('/status')
            .then(res => res.json())
            .then(data => {
                const badge = document.getElementById('statusBadge');
                const dot = document.getElementById('statusDot');
                const text = document.getElementById('statusText');
                
                if (data.status === 'running') {
                    badge.className = "flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-semibold border border-emerald-100 bg-emerald-50 text-emerald-700";
                    dot.className = "w-2 h-2 rounded-full bg-emerald-500 animate-pulse";
                    text.innerText = "运行中";
                } else {
                    badge.className = "flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-semibold border border-rose-100 bg-rose-50 text-rose-700";
                    dot.className = "w-2 h-2 rounded-full bg-rose-500";
                    text.innerText = "已停止";
                }
            });
        }

        setInterval(checkKernelStatus, 3000); // 3秒自动轮询

        function updateSubUrlDisplay(token) {
            const host = window.location.hostname;
            const panelPort = window.location.port ? ":" + window.location.port : "";
            const sanitizedToken = token.replace(/[^a-zA-Z0-9\-_]/g, '');
            document.getElementById('subUrlInput').value = "http://" + host + panelPort + "/sub/" + sanitizedToken;
        }

        function randomizeSubToken() {
            const chars = '0123456789abcdef';
            let token = '';
            for (let i = 0; i < 32; i++) {
                token += chars[Math.floor(Math.random() * 16)];
            }
            document.getElementById('subTokenInput').value = token;
            updateSubUrlDisplay(token);
        }

        window.addEventListener('DOMContentLoaded', () => {
            toggleServiceBlocks();
            updateSubUrlDisplay("{{ config.sub_token }}");
            checkKernelStatus();
        });

        function toggleServiceBlocks() {
            const rEnabled = document.getElementById('realityEnabledCheckbox').checked;
            const tEnabled = document.getElementById('tlsEnabledCheckbox').checked;
            
            const rFields = document.getElementById('realityFields');
            const tFields = document.getElementById('tlsFields');
            
            if (rEnabled) {
                rFields.classList.remove('opacity-40');
                rFields.querySelectorAll('input, button').forEach(el => el.disabled = false);
            } else {
                rFields.classList.add('opacity-40');
                rFields.querySelectorAll('input, button').forEach(el => {
                    if (el.id !== 'realityEnabledCheckbox') el.disabled = true;
                });
            }
            
            if (tEnabled) {
                tFields.classList.remove('opacity-40');
                tFields.querySelectorAll('input, select, radio').forEach(el => el.disabled = false);
                toggleCertSource(); 
            } else {
                tFields.classList.add('opacity-40');
                tFields.querySelectorAll('input, select, textarea, radio').forEach(el => {
                    if (el.id !== 'tlsEnabledCheckbox') el.disabled = true;
                });
            }
        }

        function toggleCertSource() {
            const tEnabled = document.getElementById('tlsEnabledCheckbox').checked;
            if (!tEnabled) return;

            const source = document.querySelector('input[name="cert_source"]:checked').value;
            const manualFields = document.getElementById('manualCertFields');
            const selfSignedNote = document.getElementById('selfSignedNote');

            if (source === 'manual') {
                manualFields.classList.remove('hidden');
                manualFields.querySelectorAll('textarea').forEach(el => el.disabled = false);
                selfSignedNote.classList.add('hidden');
            } else {
                manualFields.classList.add('hidden');
                manualFields.querySelectorAll('textarea').forEach(el => el.disabled = true);
                selfSignedNote.classList.remove('hidden');
            }
        }

        function addUserRow() {
            const container = document.getElementById('usersContainer');
            const row = document.createElement('div');
            row.className = 'flex flex-col sm:flex-row gap-2 user-row items-center bg-slate-50/50 p-3 rounded-xl border border-slate-100';
            row.innerHTML = `
                <input type="text" name="username[]" placeholder="用户名" class="w-full sm:flex-1 border border-slate-200 rounded-lg px-3 py-1.5 text-sm outline-none bg-white focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition" required>
                <input type="text" name="password[]" placeholder="密码" class="w-full sm:flex-1 border border-slate-200 rounded-lg px-3 py-1.5 text-sm outline-none bg-white focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition" required>
                <div class="flex gap-2 w-full sm:w-auto mt-2 sm:mt-0">
                    <button type="button" class="flex-1 sm:flex-none bg-slate-300 text-slate-500 px-4 py-1.5 rounded-lg text-xs font-semibold cursor-not-allowed" disabled>保存后可用</button>
                    <button type="button" onclick="removeUserRow(this)" class="bg-rose-500 hover:bg-rose-600 text-white px-3 py-1.5 rounded-lg text-xs font-semibold transition">删除</button>
                </div>
            `;
            container.appendChild(row);
        }

        function removeUserRow(btn) {
            const rows = document.querySelectorAll('.user-row');
            if (rows.length > 1) {
                btn.closest('.user-row').remove();
            } else {
                alert("至少需要保留一个账号！");
            }
        }

        function generateNewKeys() {
            if(!confirm("确定要重新生成 Reality 密钥对吗？这会让旧的 Reality 节点失效！")) return;
            fetch('/generate_keys')
            .then(res => res.json())
            .then(data => {
                document.getElementById('privateKeyInput').value = data.private_key;
                document.getElementById('publicKeyInput').value = data.public_key;
            });
        }

        function generateNewShortId() {
            fetch('/generate_short_id')
            .then(res => res.json())
            .then(data => {
                document.getElementById('shortIdInput').value = data.short_id;
            });
        }

        // 保存配置
        document.getElementById('configForm').addEventListener('submit', function(e) {
            e.preventDefault();
            
            const rEnabled = document.getElementById('realityEnabledCheckbox').checked;
            const tEnabled = document.getElementById('tlsEnabledCheckbox').checked;
            
            if(!rEnabled && !tEnabled) {
                alert("请至少启用一个服务模块（Reality 或 Standard TLS）！");
                return;
            }
            
            if(rEnabled && tEnabled) {
                const rp = document.getElementById('realityPortInput').value;
                const tp = document.getElementById('tlsPortInput').value;
                if(rp === tp) {
                    alert("Reality 端口与 Standard TLS 端口不能相同，请分别指定不同的端口。");
                    return;
                }
            }

            const status = document.getElementById('statusMsg');
            status.className = "text-sm font-semibold text-indigo-600";
            status.innerText = "⏳ 正在进行端口检测与保存配置中...";

            const formData = new FormData(this);
            fetch('/save', { method: 'POST', body: formData })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success') {
                    status.className = "text-sm font-semibold text-emerald-600";
                    status.innerText = "🎉 端口校验通过，配置已成功保存！";
                    setTimeout(() => { location.reload(); }, 1500);
                } else {
                    status.className = "text-sm font-semibold text-rose-600";
                    status.innerText = "❌ 失败: " + data.message;
                }
            });
        });

        // 修改密码
        document.getElementById('pwdForm').addEventListener('submit', function(e) {
            e.preventDefault();
            const status = document.getElementById('pwdStatus');
            status.innerText = "正在保存密码...";
            status.className = "text-sm text-indigo-600";

            const formData = new FormData(this);
            fetch('/change_password', { method: 'POST', body: formData })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success') {
                    status.className = "text-sm text-emerald-600";
                    status.innerText = "🎉 密码更新成功！";
                    this.reset();
                } else {
                    status.className = "text-sm text-rose-600";
                    status.innerText = "❌ 失败: " + data.message;
                }
            });
        });

        function copySubUrl() {
            const input = document.getElementById('subUrlInput');
            input.select();
            document.execCommand('copy');
            alert('订阅链接已复制！');
        }

        function showShare(user, pwd) {
            const serverIp = document.querySelector('input[name="server_ip"]').value;
            const rEnabled = document.getElementById('realityEnabledCheckbox').checked;
            const tEnabled = document.getElementById('tlsEnabledCheckbox').checked;
            const encodedPwd = encodeURIComponent(pwd);
            
            if (rEnabled) {
                const port = document.getElementById('realityPortInput').value;
                const sni = document.getElementById('realitySniInput').value;
                const pubKey = document.getElementById('publicKeyInput').value;
                const shortId = document.getElementById('shortIdInput').value;
                const remarks = encodeURIComponent("AnyTLS+Reality-" + user);
                
                const shareUrlReality = "anytls://" + encodedPwd + "@" + serverIp + ":" + port + 
                                       "?security=reality&sni=" + encodeURIComponent(sni) + 
                                       "&fp=chrome&pbk=" + encodeURIComponent(pubKey) + 
                                       "&sid=" + encodeURIComponent(shortId) + 
                                       "&type=tcp#" + remarks;
                                       
                document.getElementById('shareUrlReality').value = shareUrlReality;
                document.getElementById('modalRealitySection').classList.remove('hidden');
                
                const qrContainer = document.getElementById('qrcodeReality');
                qrContainer.innerHTML = "";
                new QRCode(qrContainer, {
                    text: shareUrlReality,
                    width: 140,
                    height: 140,
                    colorDark: "#000000",
                    colorLight: "#ffffff",
                    correctLevel: QRCode.CorrectLevel.L
                });
            } else {
                document.getElementById('modalRealitySection').classList.add('hidden');
            }

            if (tEnabled) {
                const port = document.getElementById('tlsPortInput').value;
                const sni = document.getElementById('tlsSniInput').value;
                const certSource = document.querySelector('input[name="cert_source"]:checked').value;
                const remarks = encodeURIComponent("AnyTLS+TLS-" + user);
                
                let insecureParam = "";
                if (certSource === 'self_signed') {
                    insecureParam = "&allowInsecure=1";
                }
                
                const shareUrlTls = "anytls://" + encodedPwd + "@" + serverIp + ":" + port + 
                                   "?security=tls&sni=" + encodeURIComponent(sni) + 
                                   insecureParam + "&type=tcp#" + remarks;
                                   
                document.getElementById('shareUrlTls').value = shareUrlTls;
                document.getElementById('modalTlsSection').classList.remove('hidden');
                
                const qrContainer = document.getElementById('qrcodeTls');
                qrContainer.innerHTML = "";
                new QRCode(qrContainer, {
                    text: shareUrlTls,
                    width: 140,
                    height: 140,
                    colorDark: "#000000",
                    colorLight: "#ffffff",
                    correctLevel: QRCode.CorrectLevel.L
                });
            } else {
                document.getElementById('modalTlsSection').classList.add('hidden');
            }

            document.getElementById('shareModal').classList.remove('hidden');
        }

        function closeShare() {
            document.getElementById('shareModal').classList.add('hidden');
        }

        function copyToClipboard(elementId) {
            const input = document.getElementById(elementId);
            input.select();
            document.execCommand('copy');
            alert('连接已成功复制！');
        }
    </script>
</body>
</html>
"""

LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>登录 Sing-box 配置面板</title>
    <meta charset="utf-8">
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
</head>
<body class="bg-slate-50 flex items-center justify-center min-h-screen p-4" style="font-family: 'Inter', sans-serif;">
    <div class="bg-white p-8 rounded-2xl shadow-sm border border-slate-100 w-full max-w-md space-y-6">
        <div class="text-center space-y-2">
            <h2 class="text-2xl font-bold tracking-tight text-slate-900">AnyTLS 控制台</h2>
            <p class="text-sm text-slate-400">请输入安全管理密码进行身份验证</p>
        </div>
        {% if error %}<div class="bg-rose-50 text-rose-600 border border-rose-100 p-3 rounded-xl text-center text-sm font-medium">{{ error }}</div>{% endif %}
        <form action="/login" method="POST" class="space-y-4">
            <div>
                <input type="password" name="password" placeholder="请输入管理密码" class="w-full border border-slate-200 rounded-xl px-4 py-3 text-sm outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition" required autofocus>
            </div>
            <button type="submit" class="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-3 rounded-xl transition shadow-md shadow-indigo-100">验证并进入面板</button>
        </form>
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    if not session.get('logged_in'):
        return render_template_string(LOGIN_TEMPLATE)
    config = load_config_data()
    return render_template_string(HTML_TEMPLATE, config=config)

@app.route('/login', methods=['POST'])
def login():
    pwd = request.form.get('password')
    if pwd == get_panel_password():
        session['logged_in'] = True
        return redirect('/')
    return render_template_string(LOGIN_TEMPLATE, error="密码错误！")

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect('/')

# 内核运行状态接口
@app.route('/status')
def status_route():
    global sb_process
    if sb_process and sb_process.poll() is None:
        return jsonify({'status': 'running'})
    return jsonify({'status': 'stopped'})

@app.route('/generate_keys')
def generate_keys_route():
    if not session.get('logged_in'):
        return jsonify({'status': 'error', 'message': '未登录'})
    try:
        res = subprocess.run(
            ["/usr/local/bin/sing-box", "generate", "reality-keypair"],
            capture_output=True, text=True, check=True
        )
        lines = res.stdout.strip().split('\n')
        priv = ""
        pub = ""
        for line in lines:
            if "PrivateKey:" in line:
                priv = line.split("PrivateKey:")[1].strip()
            if "PublicKey:" in line:
                pub = line.split("PublicKey:")[1].strip()
        return jsonify({'private_key': priv, 'public_key': pub})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/generate_short_id')
def generate_short_id_route():
    if not session.get('logged_in'):
        return jsonify({'status': 'error', 'message': '未登录'})
    return jsonify({'short_id': secrets.token_hex(8)})

# 动态安全订阅路由
@app.route('/sub/<token>')
def sub_route(token):
    correct_token = get_sub_token()
    if token != correct_token:
        return "Not Found", 404
        
    config = load_config_data()
    server_ip = get_server_ip()
    
    links = []
    for u, p in config['users']:
        encoded_pwd = urllib.parse.quote(p)
        
        # 1. Reality 节点
        if config['reality_enabled']:
            remarks_r = urllib.parse.quote(f"AnyTLS+Reality-{u}")
            link_r = f"anytls://{encoded_pwd}@{server_ip}:{config['reality_port']}?security=reality&sni={urllib.parse.quote(config['reality_sni'])}&fp=chrome&pbk={urllib.parse.quote(config['public_key'])}&sid={urllib.parse.quote(config['short_id'])}&type=tcp#{remarks_r}"
            links.append(link_r)
            
        # 2. Standard TLS 节点
        if config['tls_enabled']:
            remarks_t = urllib.parse.quote(f"AnyTLS+TLS-{u}")
            
            insecure_param = ""
            if config['cert_source'] == 'self_signed':
                insecure_param = "&allowInsecure=1"
                
            link_t = f"anytls://{encoded_pwd}@{server_ip}:{config['tls_port']}?security=tls&sni={urllib.parse.quote(config['tls_sni'])}&type=tcp{insecure_param}#{remarks_t}"
            links.append(link_t)
        
    sub_str = "\n".join(links)
    b64_sub = base64.b64encode(sub_str.encode('utf-8')).decode('utf-8')
    return b64_sub, 200, {'Content-Type': 'text/plain; charset=utf-8'}

@app.route('/sub')
def sub_block():
    return "Not Found", 404

@app.route('/reset_sub_token')
def reset_sub_token_route():
    if not session.get('logged_in'):
        return jsonify({'status': 'error', 'message': '未登录'})
    new_token = secrets.token_hex(16)
    write_file_content(SUB_TOKEN_PATH, new_token)
    return jsonify({'status': 'success', 'token': new_token})

@app.route('/change_password', methods=['POST'])
def change_password():
    if not session.get('logged_in'):
        return jsonify({'status': 'error', 'message': '未登录'})
    new_pwd = request.form.get('new_password')
    if not new_pwd:
        return jsonify({'status': 'error', 'message': '密码不能为空'})
    
    write_file_content(PWD_PATH, new_pwd)
    return jsonify({'status': 'success'})

@app.route('/save', methods=['POST'])
def save_config():
    if not session.get('logged_in'):
        return jsonify({'status': 'error', 'message': '未登录'})
        
    global sb_process
    old_process = sb_process
    
    try:
        server_ip = request.form.get('server_ip')
        write_file_content(IP_PATH, server_ip)
        
        # 提取并保存 Token
        sub_token_raw = request.form.get('sub_token', '').strip()
        sub_token = ''.join(c for c in sub_token_raw if c.isalnum() or c in '-_')
        if not sub_token:
            sub_token = secrets.token_hex(16)
        write_file_content(SUB_TOKEN_PATH, sub_token)
        
        # 提取账户和混淆参数
        usernames = request.form.getlist('username[]')
        passwords = request.form.getlist('password[]')
        
        users_list = []
        for u, p in zip(usernames, passwords):
            if u.strip() and p.strip():
                users_list.append({
                    "name": u.strip(),
                    "password": p.strip()
                })
                
        padding_scheme_raw = request.form.get('padding_scheme')
        padding_scheme = [line.strip() for line in padding_scheme_raw.strip().split('\n') if line.strip()]
        
        reality_enabled = request.form.get('reality_enabled') == 'on'
        tls_enabled = request.form.get('tls_enabled') == 'on'
        
        # 1. 为了确保安全可靠的检测，暂时停止当前的 Sing-box 释放它自己的端口
        if sb_process:
            try:
                sb_process.terminate()
                sb_process.wait(timeout=2)
            except:
                pass
            sb_process = None

        # 2. 对将要启用的新端口进行前置占用测试 (排除被 Nginx 或宿主机其他进程占用的可能)
        occupied_ports = []
        if reality_enabled:
            reality_port = request.form.get('reality_port')
            if is_port_occupied(reality_port):
                occupied_ports.append(f"Reality ({reality_port} 端口)")
                
        if tls_enabled:
            tls_port = request.form.get('tls_port')
            if is_port_occupied(tls_port):
                occupied_ports.append(f"Standard TLS ({tls_port} 端口)")
                
        if occupied_ports:
            # 检测到端口占用，恢复运行之前的正常进程并直接拒绝保存
            if old_process:
                restart_singbox_kernel()
            return jsonify({
                'status': 'error', 
                'message': f"端口占用冲突！以下配置端口已被宿主机的其他程序占用，请排查或更换端口后再试：{', '.join(occupied_ports)}"
            })
            
        # 3. 校验通过，开始写入新配置文件
        inbounds = []
        
        # Reality 入站构建
        if reality_enabled:
            reality_port = request.form.get('reality_port')
            reality_sni = request.form.get('reality_sni')
            private_key = request.form.get('private_key')
            public_key = request.form.get('public_key')
            short_id = request.form.get('short_id')
            
            write_file_content(PUB_KEY_PATH, public_key)
            write_file_content(os.path.join(CONFIG_DIR, 'short_id.txt'), short_id)
            
            inbounds.append({
                "type": "anytls",
                "listen": "::",
                "listen_port": int(reality_port),
                "users": users_list,
                "padding_scheme": padding_scheme,
                "tls": {
                    "enabled": True,
                    "server_name": reality_sni,
                    "reality": {
                        "enabled": True,
                        "handshake": {
                            "server": reality_sni,
                            "server_port": 443
                        },
                        "private_key": private_key,
                        "short_id": short_id
                    }
                }
            })
            
        # TLS 证书入站构建
        if tls_enabled:
            tls_port = request.form.get('tls_port')
            tls_sni = request.form.get('tls_sni')
            cert_source = request.form.get('cert_source', 'self_signed')
            
            write_file_content(CERT_SOURCE_PATH, cert_source)
            
            if cert_source == 'self_signed':
                success = generate_self_signed_cert(tls_sni, CERT_FILE, KEY_FILE)
                if not success:
                    # 恢复原进程
                    if old_process:
                        restart_singbox_kernel()
                    return jsonify({'status': 'error', 'message': '自签名证书生成失败，请确认环境是否具备 OpenSSL 指令集。'})
            else:
                cert_content = request.form.get('cert_content', '')
                key_content = request.form.get('key_content', '')
                write_file_content(CERT_FILE, cert_content)
                write_file_content(KEY_FILE, key_content)
            
            inbounds.append({
                "type": "anytls",
                "listen": "::",
                "listen_port": int(tls_port),
                "users": users_list,
                "padding_scheme": padding_scheme,
                "tls": {
                    "enabled": True,
                    "server_name": tls_sni,
                    "certificate_path": CERT_FILE,
                    "key_path": KEY_FILE
                }
            })
            
        new_json_data = {
            "inbounds": inbounds
        }
        
        with open(CONFIG_PATH, 'w') as f:
            json.dump(new_json_data, f, indent=4)
            
        # 重启 Sing-box
        restart_singbox_kernel()
        return jsonify({'status': 'success'})
        
    except Exception as e:
        # 万一崩溃，启动旧内核兜底
        if old_process:
            restart_singbox_kernel()
        return jsonify({'status': 'error', 'message': str(e)})

if __name__ == '__main__':
    restart_singbox_kernel()
    app.run(host='0.0.0.0', port=8889)
