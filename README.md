# Linux Cron Panel

Linux 定时任务 Web 管理界面。

## 功能

为了解决 OpenClaw 所有 cron 任务必须通过大模型执行而浪费 token 而诞生的面板，配合 skill 使用。

- 查看所有 Linux cron 任务（解析 `crontab -l`）
- 显示最后执行时间和状态
- 手动运行任务
- 启用/禁用任务
- 编辑任务（cron 表达式、命令、日志文件、名称）
- 查看任务日志（最近 100 行）

## 架构

- **后端**: Python 标准库（http.server），零依赖
- **前端**: React + Vite（自动构建）
- **端口**: 5002

## 快速开始

复制以下指令给 OpenClaw：

```
帮我安装这个技能https://clawhub.ai/wdmywm3/linux-cron-panel，并按照技能要求配置相关项目。
```

## 手动安装

```bash
# 克隆仓库
git clone https://github.com/wdmywm3/linux-cron-panel.git ~/.openclaw/linux-cron-panel

# 进入目录并启动
cd ~/.openclaw/linux-cron-panel
bash start.sh
```

访问 http://localhost:5002

> 首次运行时会自动安装前端依赖并构建。

## WSL2 特殊配置

如果是 WSL2 Linux 安装，注意需要开启 WSL2 的 mirror 模式，然后在 Windows 入站规则里开启 5002 端口。

### 开启 WSL2 Mirror 模式

在 Windows 用户目录创建或编辑 `.wslconfig` 文件：

```ini
[wsl2]
networkingMode=mirrored
```

然后执行：
```bash
wsl --shutdown
```

重启 WSL2 后生效。

### Windows 防火墙配置

在 Windows PowerShell（管理员）中执行：

```powershell
New-NetFirewallRule -DisplayName "Linux Cron Panel" -Direction Inbound -LocalPort 5002 -Protocol TCP -Action Allow
```

## API 接口

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/version` | 版本信息 |
| GET | `/api/tasks` | 列出所有任务 |
| GET | `/api/tasks/<id>` | 获取任务详情 |
| GET | `/api/tasks/<id>/log` | 获取日志内容 |
| POST | `/api/tasks/<id>/run` | 手动运行 |
| POST | `/api/tasks/<id>/toggle` | 切换启用/禁用 |
| PUT | `/api/tasks/<id>` | 更新任务配置 |
| DELETE | `/api/tasks/<id>` | 删除任务 |
| POST | `/api/report-run` | 运行结果回调 |

## 故障排查

- **端口占用**: `lsof -i :5002`
- **权限问题**: 确保可执行 crontab 命令
- **构建失败**: 确保 Node.js >= 18
