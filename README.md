# Linux Cron Panel

Linux 定时任务 Web 管理界面。

## 功能

- 📋 查看所有 Linux cron 任务（解析 `crontab -l`）
- 🕐 显示最后执行时间和状态
- ▶️ 手动运行任务
- ⏸️ 启用/禁用任务
- ✏️ 编辑任务（cron 表达式、命令、日志文件、名称）
- 📋 查看任务日志（最近 100 行）
- 🎨 美观的现代界面（React + Vite）

## 架构

- **后端**: Python 标准库（http.server），零依赖
- **前端**: React + Vite（自动构建）
- **端口**: 5002

## 快速开始

```bash
cd ~/.openclaw/linux-cron-panel
./start.sh
```

访问 http://localhost:5002

> 首次运行时会自动安装前端依赖并构建。

## systemd 服务（可选）

```bash
mkdir -p ~/.config/systemd/user
cp linux-cron-panel.service ~/.config/systemd/user/
systemctl --user enable --now linux-cron-panel.service
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

## 任务自动识别

- 任务 ID：自动生成的 UUID（如 `task_d9ea3ed9ef4443c3`）
- 名称：支持 `# panel:name: 任务名称` 注释
- 日志文件：自动检测 `>> /path/to/log 2>&1`
- 启用状态：自动检测 `#` 注释

## Wrapper 脚本

为确保任务执行后能正确回调 Panel，建议使用 wrapper 脚本：

```bash
~/.openclaw/linux-cron-panel/cron-wrappers/wrapper.sh TASK_ID COMMAND [args...]
```

详见 [cron-wrappers/wrapper.sh](cron-wrappers/wrapper.sh)

## 故障排查

- **端口占用**: `lsof -i :5002`
- **权限问题**: 确保可执行 crontab 命令
- **构建失败**: 确保 Node.js >= 18
