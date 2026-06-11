# AnyTLS Sing-box Panel

一个完全容器化的 **Sing-box（AnyTLS + Reality）专属可视化节点配置管理面板**。

通过简洁直观的 Web 管理界面，实现 AnyTLS 节点的快速部署、Reality 参数管理、多用户配置维护，以及订阅链接自动生成，让复杂的配置工作变得简单高效。

---

## ✨ 功能特性

### 🔐 Reality 密钥一键生成

* 自动调用 Sing-box 内核生成 Reality 密钥对。
* 服务端私钥（Private Key）与客户端公钥（Public Key）自动匹配。
* 无需手动执行命令，即可完成密钥重签。

### 🆔 Short ID 随机生成

* 一键生成符合规范的 16 位十六进制 Short ID。
* 自动写入配置并同步更新订阅信息。

### 👥 多用户管理

* 支持创建多个独立 AnyTLS 用户。
* 每个用户均可生成独立导入链接与二维码。
* 方便家庭成员、小团队或测试环境统一管理。

### ⚙️ 客户端深度兼容

自动适配主流客户端导入格式：

* v2rayN
* NekoBox
* sing-box

导出的 `anytls://` 链接自动对齐以下参数：

* `security=reality`
* `type=tcp`
* `pbk`
* `sid`
* `fp`

确保导入即用，无需额外修改。

### 🎭 自定义混淆策略

支持自定义 Padding Scheme：

* 可自由配置流量填充策略；
* 增强流量特征多样性；
* 满足不同场景下的个性化需求。

### 🔗 动态订阅系统

内置专属 Base64 订阅接口：

```
https://your-domain/sub
```

支持：

* 自动同步节点信息；
* 客户端定时更新；
* 一次配置，长期使用。

### 🔒 面板安全管理

支持直接在 Web 页面中修改管理员密码。

配置即时生效，无需重启容器。

---

# 🚀 快速部署

## 1. 创建工作目录

```bash
mkdir -p /opt/anytls-singbox
cd /opt/anytls-singbox
```

---

## 2. 准备项目文件

请将以下文件放置到工作目录中：

```
Dockerfile
entrypoint.sh
panel.py
docker-compose.yml
```

目录结构示例：

```text
/opt/anytls-singbox
├── Dockerfile
├── docker-compose.yml
├── entrypoint.sh
└── panel.py
```

---

## 3. 创建 Docker Compose 配置

```yaml
version: "3"

services:
  singbox-panel:
    image: ghcr.io/6106757-lab/sing-box-anytls-reality:latest
    container_name: anytls-singbox-panel

    restart: always

    network_mode: host

    volumes:
      - ./data:/etc/sing-box
```

### 参数说明

| 参数                     | 说明                          |
| ---------------------- | --------------------------- |
| `network_mode: host`   | 使用 Host 网络模式，支持 443 等真实端口监听 |
| `./data:/etc/sing-box` | 持久化所有配置与运行数据                |
| `restart: always`      | 开机自动启动                      |

---

## 4. 启动服务

```bash
docker compose up -d
```

查看运行状态：

```bash
docker ps
```

查看日志：

```bash
docker logs -f anytls-singbox-panel
```

---

# 📂 数据持久化

所有配置均保存在宿主机：

```text
/opt/anytls-singbox/data/
```

包含：

| 文件               | 说明             |
| ---------------- | -------------- |
| `config.json`    | Sing-box 主配置文件 |
| `public_key.txt` | Reality 客户端公钥  |
| `short_id.txt`   | 当前 Short ID    |
| `panel_pwd.txt`  | 面板管理员密码        |
| `users.json`     | 用户信息（如启用多用户）   |

迁移服务器时，仅需备份整个 `data` 目录即可。

---

# 📱 客户端使用

生成节点后，可通过以下方式导入：

### 链接导入

```text
anytls://xxxxxx
```

支持：

* NekoBox
* v2rayN
* sing-box

---

### 二维码导入

面板支持自动生成二维码。

手机客户端扫码即可完成配置。

---

### Base64 订阅

订阅地址示例：

```text
https://your-domain/sub
```

将订阅地址添加至客户端后，即可自动同步节点配置。

---

# 🔄 更新项目

如果使用 Docker Compose 部署：

```bash
docker compose pull
docker compose up -d
```

即可完成升级。

---

# 🛠️ 开发计划

* [ ] HTTPS 自动申请证书
* [ ] 节点在线状态检测
* [ ] Telegram 通知支持
* [ ] 流量统计功能
* [ ] WebSocket 支持
* [ ] 多实例管理

欢迎提交 Issue 与 Pull Request。

---

# ⭐ GitHub 发布流程

初始化仓库：

```bash
git init
git add .
git commit -m "Initial release"
git branch -M main
```

关联远程仓库：

```bash
git remote add origin https://github.com/6106757-lab/anytls-singbox.git
```

推送代码：

```bash
git push -u origin main
```

推送完成后，可通过 GitHub Actions 自动构建镜像并发布至：

```text
ghcr.io/你的GitHub用户名/anytls-singbox:latest
```

之后即可在任何支持 Docker 的环境中快速部署。

---

# ⚠️ 免责声明

本项目仅供学习、技术研究及个人合法用途使用。

使用者应自行遵守所在国家或地区的法律法规。任何因使用本项目而产生的直接或间接后果，均由使用者自行承担，项目作者不承担任何责任。

---

如果本项目对你有所帮助，欢迎点亮一个 ⭐ Star 支持项目持续更新。
