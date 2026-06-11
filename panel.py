import os
import json
import secrets
import base64
import urllib.parse
import subprocess
from flask import Flask, request, render_template_string, redirect, session, jsonify

app = Flask(__name__)
app.secret_key = 'singbox-reality-panel-key'

CONFIG_DIR = '/etc/sing-box'
CONFIG_PATH = os.path.join(CONFIG_DIR, 'config.json')
PUB_KEY_PATH = os.path.join(CONFIG_DIR, 'public_key.txt')
PWD_PATH = os.path.join(CONFIG_DIR, 'panel_pwd.txt')
IP_PATH = os.path.join(CONFIG_DIR, 'server_ip.txt')

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
        'port': '443',
        'users': [('admin', 'adminpassword')],
        'padding_scheme': "stop=3\n0=30-30\n1=100-400\n2=400-500,c,500-1000,c,500-1000,c,500-1000,c,500-1000",
        'server_name': 'yahoo.com',
        'private_key': '',
        'public_key': get_file_content(PUB_KEY_PATH),
        'short_id': '',
        'server_ip': get_server_ip()
    }
    
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r') as f:
                data = json.load(f)
            inbound = data['inbounds'][0]
            config['port'] = str(inbound.get('listen_port', 443))
            
            # 解析用户
            users_list = []
            for u in inbound.get('users', []):
                users_list.append((u.get('name'), u.get('password')))
            if users_list:
                config['users'] = users_list
                
            # 解析混淆策略
            config['padding_scheme'] = '\n'.join(inbound.get('padding_scheme', []))
            
            # 解析 Reality
            tls = inbound.get('tls', {})
            config['server_name'] = tls.get('server_name', 'yahoo.com')
            
            reality = tls.get('reality', {})
            config['private_key'] = reality.get('private_key', '')
            config['short_id'] = reality.get('short_id', '')
        except Exception as e:
            print("解析 config.json 失败:", e)
            
    return config

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Sing-box Reality 旗舰版面板</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/qrcodejs@1.0.0/qrcode.min.js"></script>
</head>
<body class="bg-gray-50 text-gray-800 min-h-screen">
    <div class="container mx-auto max-w-4xl py-8 px-4">
        <div class="bg-white rounded-xl shadow-lg overflow-hidden p-6 md:p-8">
            <!-- 导航 -->
            <div class="flex justify-between items-center border-b pb-4 mb-6">
                <div>
                    <h1 class="text-2xl font-bold text-indigo-600">Sing-box AnyTLS+Reality 面板</h1>
                    <p class="text-xs text-gray-400 mt-1">集成一键生成 Reality 密钥对、Short ID 与动态订阅</p>
                </div>
                <div class="flex gap-2">
                    <button onclick="openTab('config-tab')" class="text-sm bg-indigo-50 text-indigo-700 px-4 py-2 rounded font-semibold">系统配置</button>
                    <button onclick="openTab('security-tab')" class="text-sm bg-gray-100 text-gray-700 px-4 py-2 rounded font-semibold">安全设置</button>
                    <a href="/logout" class="text-sm bg-red-100 text-red-700 px-4 py-2 rounded font-semibold">退出</a>
                </div>
            </div>

            <!-- TAB 1: 系统配置 -->
            <div id="config-tab" class="tab-content space-y-6">
                <!-- 动态订阅 -->
                <div class="bg-indigo-50 border border-indigo-200 rounded-lg p-4">
                    <h3 class="text-sm font-bold text-indigo-800 mb-1">🔗 我的动态订阅链接</h3>
                    <p class="text-xs text-indigo-600 mb-2">一键复制此链接贴入 NekoBox / v2rayN 等，将自动同步配置并带有公钥参数：</p>
                    <div class="flex gap-2">
                        <input type="text" id="subUrlInput" readonly class="flex-1 bg-white border border-indigo-300 rounded px-3 py-1.5 text-xs text-gray-600 outline-none">
                        <button type="button" onclick="copySubUrl()" class="bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold px-4 rounded shadow">复制订阅</button>
                    </div>
                </div>

                <form id="configForm" class="space-y-6">
                    <!-- 基本网络配置 -->
                    <div class="bg-gray-50 p-4 rounded-lg border space-y-4">
                        <h3 class="text-sm font-bold text-gray-700 border-b pb-1">🌐 核心服务参数</h3>
                        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                            <div>
                                <label class="block text-xs font-semibold text-gray-600 mb-1">服务器 IP (用于节点导出)</label>
                                <input type="text" name="server_ip" value="{{ config.server_ip }}" class="w-full border rounded px-3 py-1.5 text-sm outline-none" required>
                            </div>
                            <div>
                                <label class="block text-xs font-semibold text-gray-600 mb-1">监听端口 (Port)</label>
                                <input type="number" name="port" id="portInput" value="{{ config.port }}" class="w-full border rounded px-3 py-1.5 text-sm outline-none" required min="1" max="65535">
                            </div>
                            <div>
                                <label class="block text-xs font-semibold text-gray-600 mb-1">伪装目标域名 (server_name)</label>
                                <input type="text" name="server_name" id="serverNameInput" value="{{ config.server_name }}" class="w-full border rounded px-3 py-1.5 text-sm outline-none" required>
                            </div>
                        </div>
                    </div>

                    <!-- Reality 密钥专属管理板块 -->
                    <div class="bg-gray-50 p-4 rounded-lg border space-y-4">
                        <div class="flex justify-between items-center border-b pb-1">
                            <h3 class="text-sm font-bold text-gray-700">🔑 Reality 密钥与安全管理</h3>
                            <button type="button" onclick="generateNewKeys()" class="text-xs bg-indigo-50 hover:bg-indigo-100 text-indigo-700 px-3 py-1 rounded font-semibold border border-indigo-100">
                                🔄 重新生成全新密钥对
                            </button>
                        </div>
                        <div class="space-y-3">
                            <div>
                                <label class="block text-[11px] font-semibold text-gray-500 mb-1">服务端私钥 (private_key - 绝对保密)</label>
                                <input type="text" name="private_key" id="privateKeyInput" value="{{ config.private_key }}" class="w-full border rounded px-3 py-1.5 text-xs font-mono outline-none" required readonly>
                            </div>
                            <div>
                                <label class="block text-[11px] font-semibold text-gray-500 mb-1">客户端公钥 (public_key - 用于客户端导出分享)</label>
                                <input type="text" name="public_key" id="publicKeyInput" value="{{ config.public_key }}" class="w-full border bg-white rounded px-3 py-1.5 text-xs font-mono outline-none" required readonly>
                            </div>
                            <div class="grid grid-cols-1 md:grid-cols-2 gap-4 pt-1">
                                <div>
                                    <label class="block text-[11px] font-semibold text-gray-500 mb-1">短期握手标识 ID (short_id)</label>
                                    <div class="flex gap-2">
                                        <input type="text" name="short_id" id="shortIdInput" value="{{ config.short_id }}" class="flex-1 border rounded px-3 py-1.5 text-xs font-mono outline-none" required>
                                        <button type="button" onclick="generateNewShortId()" class="bg-gray-200 hover:bg-gray-300 text-gray-700 px-3 py-1 rounded text-xs">随机</button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- 账号管理 -->
                    <div class="bg-gray-50 p-4 rounded-lg border space-y-4">
                        <h3 class="text-sm font-bold text-gray-700 border-b pb-1">👥 用户管理与一键分享</h3>
                        <div id="usersContainer" class="space-y-2">
                            {% for user, pwd in config.users %}
                            <div class="flex gap-2 user-row items-center">
                                <input type="text" name="username[]" value="{{ user }}" placeholder="用户名" class="flex-1 border rounded px-3 py-1.5 text-sm outline-none" required>
                                <input type="text" name="password[]" value="{{ pwd }}" placeholder="密码" class="flex-1 border rounded px-3 py-1.5 text-sm outline-none" required>
                                <button type="button" onclick="showShare('{{ user }}', '{{ pwd }}')" class="bg-green-500 hover:bg-green-600 text-white px-4 py-1.5 rounded text-xs font-bold shadow">生成连接</button>
                                <button type="button" onclick="removeUserRow(this)" class="bg-red-500 hover:bg-red-600 text-white px-4 py-1.5 rounded text-xs">删除</button>
                            </div>
                            {% endfor %}
                        </div>
                        <button type="button" onclick="addUserRow()" class="text-xs bg-indigo-50 hover:bg-indigo-100 text-indigo-600 font-semibold px-4 py-2 rounded border border-indigo-100">
                            + 添加新用户
                        </button>
                    </div>

                    <!-- Padding-Scheme -->
                    <div class="bg-gray-50 p-4 rounded-lg border space-y-2">
                        <h3 class="text-sm font-bold text-gray-700 border-b pb-1">📉 自定义混淆策略 (Padding-Scheme)</h3>
                        <textarea name="padding_scheme" id="paddingInput" rows="4" class="w-full border rounded p-2 font-mono text-sm outline-none bg-white" required>{{ config.padding_scheme }}</textarea>
                    </div>

                    <div class="pt-4 border-t flex items-center justify-between">
                        <button type="submit" class="bg-indigo-600 hover:bg-indigo-700 text-white font-bold px-8 py-3 rounded shadow">
                            保存并重启内核
                        </button>
                        <span id="statusMsg" class="text-sm font-semibold"></span>
                    </div>
                </form>
            </div>

            <!-- TAB 2: 安全设置 -->
            <div id="security-tab" class="tab-content hidden space-y-6">
                <div class="bg-gray-50 rounded-lg p-6 border">
                    <h3 class="text-lg font-bold text-gray-800 mb-4">🔑 修改面板登录密码</h3>
                    <form id="pwdForm" class="space-y-4">
                        <div>
                            <label class="block text-sm text-gray-600 mb-1">输入新密码</label>
                            <input type="password" name="new_password" class="w-full md:w-1/2 border rounded px-3 py-2 outline-none" required minlength="4">
                        </div>
                        <button type="submit" class="bg-indigo-600 hover:bg-indigo-700 text-white font-bold px-6 py-2 rounded">确认保存</button>
                        <span id="pwdStatus" class="text-sm font-semibold block mt-2"></span>
                    </form>
                </div>
            </div>
        </div>
    </div>

    <!-- 二维码弹窗 -->
    <div id="shareModal" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center hidden p-4 z-50">
        <div class="bg-white rounded-xl shadow-lg max-w-md w-full p-6 space-y-4">
            <div class="flex justify-between items-center border-b pb-2">
                <h3 class="font-bold text-gray-800 text-lg">节点一键导入</h3>
                <button onclick="closeShare()" class="text-gray-400 hover:text-gray-600 text-xl font-bold">&times;</button>
            </div>
            <div>
                <p class="text-xs text-gray-500 mb-1">一键导入链接：</p>
                <div class="flex gap-1">
                    <input type="text" id="shareUrlInput" readonly class="flex-1 border bg-gray-50 rounded px-2 py-1 text-xs outline-none">
                    <button onclick="copyShareUrl()" class="bg-indigo-600 text-white text-xs px-3 py-1 rounded">复制</button>
                </div>
            </div>
            <div class="flex flex-col items-center justify-center p-4 bg-gray-50 rounded">
                <span class="text-xs text-gray-500 mb-2">使用客户端扫码直连：</span>
                <div id="qrcode" class="border p-2 bg-white rounded"></div>
            </div>
        </div>
    </div>

    <script>
        function openTab(tabId) {
            document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
            document.getElementById(tabId).classList.remove('hidden');
        }

        function addUserRow() {
            const container = document.getElementById('usersContainer');
            const row = document.createElement('div');
            row.className = 'flex gap-2 user-row items-center';
            row.innerHTML = `
                <input type="text" name="username[]" placeholder="用户名" class="flex-1 border rounded px-3 py-1.5 text-sm outline-none" required>
                <input type="text" name="password[]" placeholder="密码" class="flex-1 border rounded px-3 py-1.5 text-sm outline-none" required>
                <button type="button" class="bg-gray-300 text-gray-500 px-4 py-1.5 rounded text-xs font-bold cursor-not-allowed" disabled>保存后可用</button>
                <button type="button" onclick="removeUserRow(this)" class="bg-red-500 hover:bg-red-600 text-white px-4 py-1.5 rounded text-xs">删除</button>
            `;
            container.appendChild(row);
        }

        function removeUserRow(btn) {
            const rows = document.querySelectorAll('.user-row');
            if (rows.length > 1) {
                btn.parentElement.remove();
            } else {
                alert("至少需要保留一个账号！");
            }
        }

        function generateNewKeys() {
            if(!confirm("确定要重新生成 Reality 密钥对吗？这会让旧节点连接失效！")) return;
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
            const status = document.getElementById('statusMsg');
            status.className = "text-sm font-semibold text-blue-600";
            status.innerText = "正在应用配置并重启内核中...";

            const formData = new FormData(this);
            fetch('/save', { method: 'POST', body: formData })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success') {
                    status.className = "text-sm font-semibold text-green-600";
                    status.innerText = "🎉 保存成功，Sing-box 已重启运行！";
                    setTimeout(() => { location.reload(); }, 1500);
                } else {
                    status.className = "text-sm font-semibold text-red-600";
                    status.innerText = "❌ 失败: " + data.message;
                }
            });
        });

        // 修改密码
        document.getElementById('pwdForm').addEventListener('submit', function(e) {
            e.preventDefault();
            const status = document.getElementById('pwdStatus');
            status.innerText = "正在保存密码...";
            status.className = "text-sm text-blue-500";

            const formData = new FormData(this);
            fetch('/change_password', { method: 'POST', body: formData })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success') {
                    status.className = "text-sm text-green-600";
                    status.innerText = "🎉 密码更新成功！";
                    this.reset();
                } else {
                    status.className = "text-sm text-red-600";
                    status.innerText = "❌ 失败: " + data.message;
                }
            });
        });

        // 订阅配置
        const host = window.location.hostname;
        const panelPort = window.location.port ? ":" + window.location.port : "";
        document.getElementById('subUrlInput').value = "http://" + host + panelPort + "/sub";

        function copySubUrl() {
            const input = document.getElementById('subUrlInput');
            input.select();
            document.execCommand('copy');
            alert('订阅链接已复制！');
        }

        // 导出分享连接
        let qrcodeInstance = null;
        function showShare(user, pwd) {
            const serverIp = document.querySelector('input[name="server_ip"]').value;
            const port = document.getElementById('portInput').value;
            const sni = document.getElementById('serverNameInput').value;
            const pubKey = document.getElementById('publicKeyInput').value;
            const shortId = document.getElementById('shortIdInput').value;
            
            const encodedPwd = encodeURIComponent(pwd);
            const remarks = encodeURIComponent("AnyTLS+Reality-" + user);
            
            // 按照 v2rayN / NekoBox 标准缩写格式精准拼接
            const shareUrl = "anytls://" + encodedPwd + "@" + serverIp + ":" + port + 
                             "?security=reality&sni=" + encodeURIComponent(sni) + 
                             "&fp=chrome&pbk=" + encodeURIComponent(pubKey) + 
                             "&sid=" + encodeURIComponent(shortId) + 
                             "&type=tcp#" + remarks;

            document.getElementById('shareUrlInput').value = shareUrl;
            document.getElementById('shareModal').classList.remove('hidden');

            const qrContainer = document.getElementById('qrcode');
            qrContainer.innerHTML = "";
            qrcodeInstance = new QRCode(qrContainer, {
                text: shareUrl,
                width: 180,
                height: 180,
                colorDark: "#000000",
                colorLight: "#ffffff",
                correctLevel: QRCode.CorrectLevel.L
            });
        }

        function closeShare() {
            document.getElementById('shareModal').classList.add('hidden');
        }

        function copyShareUrl() {
            const input = document.getElementById('shareUrlInput');
            input.select();
            document.execCommand('copy');
            alert('节点链接已复制！');
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
</head>
<body class="bg-gray-100 flex items-center justify-center min-h-screen">
    <div class="bg-white p-8 rounded-lg shadow-md w-full max-w-sm">
        <h2 class="text-xl font-bold mb-4 text-center text-indigo-600">Sing-box 配置面板</h2>
        {% if error %}<div class="bg-red-100 text-red-700 p-2 rounded mb-4 text-sm">{{ error }}</div>{% endif %}
        <form action="/login" method="POST" class="space-y-4">
            <div>
                <label class="block text-sm text-gray-600">请输入登录密码</label>
                <input type="password" name="password" class="w-full border rounded px-3 py-2 outline-none focus:ring-2 focus:ring-indigo-400" required autofocus>
            </div>
            <button type="submit" class="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-2 rounded">进入面板</button>
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

# 实时调用内核生成公钥/私钥对
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

# 生成随机 Short ID
@app.route('/generate_short_id')
def generate_short_id_route():
    if not session.get('logged_in'):
        return jsonify({'status': 'error', 'message': '未登录'})
    return jsonify({'short_id': secrets.token_hex(8)})

# 动态订阅接口 (同样输出为 v2rayN 标准协议参数)
@app.route('/sub')
def sub_route():
    config = load_config_data()
    server_ip = get_server_ip()
    port = config['port']
    sni = config['server_name']
    pub_key = config['public_key']
    short_id = config['short_id']
    
    links = []
    for u, p in config['users']:
        encoded_pwd = urllib.parse.quote(p)
        remarks = urllib.parse.quote(f"AnyTLS+Reality-{u}")
        link = f"anytls://{encoded_pwd}@{server_ip}:{port}?security=reality&sni={urllib.parse.quote(sni)}&fp=chrome&pbk={urllib.parse.quote(pub_key)}&sid={urllib.parse.quote(short_id)}&type=tcp#{remarks}"
        links.append(link)
        
    sub_str = "\n".join(links)
    b64_sub = base64.b64encode(sub_str.encode('utf-8')).decode('utf-8')
    return b64_sub, 200, {'Content-Type': 'text/plain; charset=utf-8'}

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
        
    try:
        port = request.form.get('port')
        server_ip = request.form.get('server_ip')
        server_name = request.form.get('server_name')
        private_key = request.form.get('private_key')
        public_key = request.form.get('public_key')
        short_id = request.form.get('short_id')
        padding_scheme_raw = request.form.get('padding_scheme')
        
        usernames = request.form.getlist('username[]')
        passwords = request.form.getlist('password[]')
        
        # 1. 写入辅助文件
        write_file_content(IP_PATH, server_ip)
        write_file_content(PUB_KEY_PATH, public_key)
        write_file_content(os.path.join(CONFIG_DIR, 'short_id.txt'), short_id)
        
        # 2. 构造并生成规范的 JSON
        users_list = []
        for u, p in zip(usernames, passwords):
            if u.strip() and p.strip():
                users_list.append({
                    "name": u.strip(),
                    "password": p.strip()
                })
                
        padding_scheme = [line.strip() for line in padding_scheme_raw.strip().split('\n') if line.strip()]
        
        new_json_data = {
            "inbounds": [
                {
                    "type": "anytls",
                    "listen": "::",
                    "listen_port": int(port),
                    "users": users_list,
                    "padding_scheme": padding_scheme,
                    "tls": {
                        "enabled": True,
                        "server_name": server_name,
                        "reality": {
                            "enabled": True,
                            "handshake": {
                                "server": server_name,
                                "server_port": 443
                            },
                            "private_key": private_key,
                            "short_id": short_id
                        }
                    }
                }
            ]
        }
        
        with open(CONFIG_PATH, 'w') as f:
            json.dump(new_json_data, f, indent=4)
            
        # 3. 重启子进程
        restart_singbox_kernel()
        return jsonify({'status': 'success'})
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

if __name__ == '__main__':
    restart_singbox_kernel()
    app.run(host='0.0.0.0', port=8889)
