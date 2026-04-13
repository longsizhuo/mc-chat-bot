# 从零开始部署 MCBot（超详细版）

本指南假设你**什么都没装**，从一台全新的服务器/电脑开始，一步步教你跑起来。

## 目录

- [第一步：安装 Python 环境](#第一步安装-python-环境)
- [第二步：安装 mcrcon](#第二步安装-mcrcon)
- [第三步：开启 Minecraft 服务器 RCON](#第三步开启-minecraft-服务器-rcon)
- [第四步：安装 MCBot](#第四步安装-mcbot)
- [第五步：配置](#第五步配置)
- [第六步：运行](#第六步运行)
- [第七步：设为开机自启（可选）](#第七步设为开机自启可选)
- [常见问题](#常见问题)

---

## 第一步：安装 Python 环境

MCBot 需要 Python 3.10 或更高版本。

### Linux (Ubuntu / Debian)

```bash
# 更新软件源
sudo apt update

# 安装 Python 和 pip
sudo apt install -y python3 python3-pip python3-venv git gcc

# 验证
python3 --version   # 应该显示 3.10+
pip3 --version       # 应该显示 pip xx.x
```

如果 `pip3` 不可用：

```bash
# 方法1：直接安装
sudo apt install -y python3-pip

# 方法2：如果方法1不行
python3 -m ensurepip --upgrade
```

### Linux (CentOS / RHEL / Rocky)

```bash
sudo yum install -y python3 python3-pip git gcc
# 或
sudo dnf install -y python3 python3-pip git gcc
```

### macOS

```bash
# 安装 Homebrew（如果没有）
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 安装 Python
brew install python3 git

# 验证
python3 --version
pip3 --version
```

### Windows

1. 下载 Python：https://www.python.org/downloads/
2. **安装时勾选 "Add Python to PATH"**（非常重要！）
3. 安装 Git：https://git-scm.com/download/win
4. 打开 **PowerShell** 或 **命令提示符**，验证：

```powershell
python --version    # 应该显示 3.10+
pip --version       # 应该显示 pip xx.x
git --version
```

> **Windows 注意**：下面的命令中 `python3` 在 Windows 上可能需要改成 `python`，`pip3` 改成 `pip`。

---

## 第二步：安装 mcrcon

mcrcon 是一个 RCON 命令行客户端，MCBot 用它跟 Minecraft 服务器通信。

### Linux / macOS

```bash
# 下载源码
git clone https://github.com/Tiiffi/mcrcon.git
cd mcrcon

# 编译（需要 gcc）
gcc -o mcrcon mcrcon.c

# 安装到系统路径
sudo cp mcrcon /usr/local/bin/

# 验证
mcrcon --help

# 清理
cd .. && rm -rf mcrcon
```

如果没有 `gcc`：

```bash
# Ubuntu/Debian
sudo apt install -y gcc

# CentOS/RHEL
sudo yum install -y gcc

# macOS（安装 Xcode 命令行工具）
xcode-select --install
```

### Windows

1. 下载编译好的 mcrcon：https://github.com/Tiiffi/mcrcon/releases
2. 解压，将 `mcrcon.exe` 放到一个目录（比如 `C:\mcrcon\`）
3. 将这个目录添加到系统 PATH 环境变量
4. 打开新的 PowerShell，验证：

```powershell
mcrcon --help
```

---

## 第三步：开启 Minecraft 服务器 RCON

RCON (Remote Console) 是 Minecraft 服务器内置的远程控制功能，默认是**关闭的**，需要手动开启。

### 3.1 找到 server.properties

这个文件在你的 Minecraft 服务器根目录下。如果你是第一次启动服务器，先启动一次让它自动生成。

```bash
# 常见路径
ls /path/to/your/minecraft-server/server.properties
```

### 3.2 编辑 server.properties

用任意文本编辑器打开 `server.properties`，找到并修改以下三行：

```properties
# 开启 RCON（默认是 false，改成 true）
enable-rcon=true

# RCON 端口（默认 25575，一般不用改）
rcon.port=25575

# RCON 密码（必须设置一个！随便取一个复杂密码）
rcon.password=你的密码写在这里
```

> **安全提示**：
> - RCON 密码要足够复杂，不要用 123456 这种
> - 如果服务器暴露在公网，建议防火墙只对本机开放 25575 端口
> - 不要把密码提交到 Git

### 3.3 重启 Minecraft 服务器

修改 `server.properties` 后必须**重启服务器**才能生效。

```bash
# 如果用 systemd 管理
sudo systemctl restart minecraft

# 如果用 screen/tmux
# 在服务器控制台输入 stop，然后重新启动

# 如果直接跑的 java
# Ctrl+C 停止，然后重新运行启动命令
```

### 3.4 验证 RCON 是否开启

```bash
# 用 mcrcon 测试连接
mcrcon -H localhost -P 25575 -p 你的密码 "list"
```

如果成功，会显示类似：

```
There are 0 of a max of 20 players online:
```

如果失败，检查：
- 密码是否正确
- 服务器是否已重启
- 端口是否正确
- 防火墙是否阻止了 25575 端口

### 不同服务端的注意事项

| 服务端 | RCON 支持 | 备注 |
|--------|----------|------|
| 原版 (Vanilla) | 支持 | 直接改 server.properties |
| Fabric | 支持 | 同上 |
| Paper / Spigot | 支持 | 同上 |
| Forge | 支持 | 同上 |
| BungeeCord / Velocity | 不直接支持 | 需要在后端服务器上开启，不是在代理上 |
| 基岩版 | 不支持 | MCBot 仅支持 Java 版 |

---

## 第四步：安装 MCBot

```bash
# 克隆项目
git clone https://github.com/longsizhuo/mc-chat-bot.git
cd mc-chat-bot

# 创建虚拟环境（推荐，避免污染系统 Python）
python3 -m venv .venv

# 激活虚拟环境
source .venv/bin/activate        # Linux / macOS
# .venv\Scripts\activate         # Windows PowerShell
# .venv\Scripts\activate.bat     # Windows CMD

# 安装依赖
pip install -r requirements.txt
```

> **什么是虚拟环境？**
> 虚拟环境是一个隔离的 Python 环境，安装的包不会影响系统的其他 Python 项目。
> 如果你不想用虚拟环境，也可以直接 `pip3 install -r requirements.txt`，
> 遇到权限问题加 `--break-system-packages` 参数。

---

## 第五步：配置

```bash
# 复制配置模板
cp config.example.yml config.yml
```

用文本编辑器打开 `config.yml`，按下面的说明修改：

```yaml
# ===== 必须修改 =====

# 你的 Minecraft 服务器目录（绝对路径）
server_dir: "/home/你的用户名/minecraft-server"

# AI 设置
ai:
  # 选择一个 AI 模型提供商
  # deepseek - 便宜，中文好（推荐国内用户）
  # openai   - GPT，稳定
  # ollama   - 本地模型，完全免费
  provider: "deepseek"

  # API 密钥（去对应平台注册获取）
  # DeepSeek: https://platform.deepseek.com/api_keys
  # OpenAI:   https://platform.openai.com/api-keys
  api_key: "sk-你的密钥"

# RCON 设置（必须和 server.properties 里的一致）
rcon:
  password: "你在server.properties里设的密码"

# ===== 可选修改 =====

bot:
  name: "小方"       # Bot 在游戏里显示的名字
  language: "zh"      # zh 中文 / en 英文

backup:
  enabled: true       # 是否开启游戏日自动备份
  max_backups: 10     # 保留几份备份
```

### 获取 AI API Key

#### DeepSeek（推荐，便宜）

1. 访问 https://platform.deepseek.com
2. 注册账号
3. 进入 "API Keys" 页面
4. 创建新的 API Key
5. 复制到 `config.yml` 的 `api_key` 字段
6. 充值（很便宜，几块钱可以用很久）

#### OpenAI

1. 访问 https://platform.openai.com
2. 注册账号 + 绑定支付方式
3. 进入 API Keys 页面创建密钥

#### Ollama（免费，本地运行）

不需要 API Key，但需要本地安装 Ollama：

```bash
# 安装 Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 下载模型（选一个）
ollama pull llama3        # 通用，英文好
ollama pull qwen2         # 通义千问，中文好

# config.yml 里这样配置
# ai:
#   provider: "ollama"
#   model: "qwen2"        # 或 llama3
```

---

## 第六步：运行

```bash
# 确保在 mc-chat-bot 目录下
cd /path/to/mc-chat-bot

# 如果用了虚拟环境，先激活
source .venv/bin/activate

# 启动！
python3 run.py
```

看到以下输出说明启动成功：

```
[MCBot] Chat bot started!
[MCBot] Bot name: 小方
[MCBot] AI: deepseek (deepseek-chat)
[MCBot] Log: /path/to/minecraft-server/logs/latest.log
[MCBot] Status polling every 15s
[MCBot] Events: death roasts, PvP, join/leave, AFK, playtime,
[MCBot]         low HP, hunger, dimension, altitude, level up
[MCBot] Backup system running in background
[MCBot] Monitoring chat...
```

现在进入 Minecraft 服务器，在聊天框里打字试试！

按 `Ctrl+C` 停止 Bot。

---

## 第七步：设为开机自启（可选）

### Linux（systemd）

```bash
# 替换下面的路径为你的实际路径
MCBOT_DIR="/home/你的用户名/mc-chat-bot"
PYTHON_PATH="$MCBOT_DIR/.venv/bin/python3"
# 如果没用虚拟环境，改成：PYTHON_PATH="/usr/bin/python3"

sudo tee /etc/systemd/system/mcbot.service > /dev/null << EOF
[Unit]
Description=MCBot - Minecraft AI Chat Bot
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$MCBOT_DIR
ExecStart=$PYTHON_PATH $MCBOT_DIR/run.py -c $MCBOT_DIR/config.yml
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# 启用并启动
sudo systemctl daemon-reload
sudo systemctl enable mcbot      # 开机自启
sudo systemctl start mcbot       # 现在启动

# 查看状态
sudo systemctl status mcbot

# 查看日志
sudo journalctl -u mcbot -f
```

### Windows

可以用 "任务计划程序" 设置开机自启，或者用 NSSM 工具把 Python 脚本注册为 Windows 服务。

### macOS

可以用 launchd 创建 plist 文件实现开机自启。

---

## 常见问题

### Q: `pip3: command not found`

```bash
# Ubuntu/Debian
sudo apt install python3-pip

# 或者用 python3 -m pip 代替 pip3
python3 -m pip install -r requirements.txt
```

### Q: `gcc: command not found`（编译 mcrcon 时）

```bash
# Ubuntu/Debian
sudo apt install gcc

# CentOS/RHEL
sudo yum install gcc

# macOS
xcode-select --install
```

### Q: `ModuleNotFoundError: No module named 'yaml'`

```bash
pip3 install pyyaml
# 或
pip3 install -r requirements.txt
```

### Q: `externally-managed-environment` 错误

这是 Python 3.12+ 的新安全限制。解决方法：

```bash
# 方法1（推荐）：使用虚拟环境
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 方法2：强制安装（不推荐）
pip3 install -r requirements.txt --break-system-packages
```

### Q: RCON 连接失败 `Connection refused`

1. 确认 `server.properties` 中 `enable-rcon=true`
2. 确认服务器已经**重启**（不是 reload，是完全重启）
3. 确认密码正确
4. 确认端口没被防火墙阻止：
   ```bash
   # 查看端口是否在监听
   ss -tlnp | grep 25575
   
   # 如果用了 ufw 防火墙
   sudo ufw allow 25575/tcp
   ```

### Q: Bot 启动了但游戏里没反应

1. 检查 `config.yml` 中的 `server_dir` 路径是否正确
2. 检查日志文件是否存在：`ls /你的服务器路径/logs/latest.log`
3. 在游戏里说句话，然后看 MCBot 终端有没有输出
4. 确认 AI API Key 有效且有余额

### Q: 中文乱码

确保你的系统 locale 支持 UTF-8：

```bash
locale
# 应该包含 UTF-8

# 如果不是，设置：
export LANG=en_US.UTF-8
```

### Q: 能和基岩版一起用吗？

不能。MCBot 依赖 Java 版服务器的 RCON 功能和日志格式。基岩版服务器不支持 RCON。

如果你想让基岩版玩家加入 Java 版服务器，可以用 [GeyserMC](https://geysermc.org/)，MCBot 仍然正常工作。

### Q: 多个服务器能共用一个 MCBot 吗？

不能。每个 MCBot 实例只能绑定一个服务器。如果你有多个服务器，需要分别部署多个 MCBot，每个有自己的 `config.yml`。

---

还有问题？在 [GitHub Issues](https://github.com/longsizhuo/mc-chat-bot/issues) 提问。
