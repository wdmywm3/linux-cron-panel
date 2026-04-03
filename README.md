# Cron Panel

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
- **前端**: React + Vite（构建后静态文件）
- **端口**: 5000

## 快速开始

### 1. 安装并构建前端

```bash
cd ~/.openclaw/cron-panel/frontend
npm install        # 首次需要
npm run build      # 构建输出到 dist/
```

### 2. 启动服务

```bash
cd ~/.openclaw/cron-panel
./start.sh
# 或者手动:
# (cd frontend && npm run build)
# python3 backend/server.py
```

服务启动后访问: http://localhost:5000

### 3. 作为 systemd 服务（可选）

```bash
# 创建 user service
mkdir -p ~/.config/systemd/user
cp cron-panel.service ~/.config/systemd/user/
systemctl --user enable --now cron-panel.service
```

## 任务自动识别

后端会自动扫描 `crontab -l` 中的任务，并提取元数据：

- 任务 ID：从命令提取（如 `ikuai-l2tp-monitor.sh` → `ikuai-l2tp-monitor-sh`）
- 名称：支持 `# name: 任务名称` 注释
- 日志文件：自动检测 `>> /path/to/log 2>&1`
- 启用状态：自动检测 `#` 注释

## API 接口

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/tasks` | 列出所有任务 |
| GET | `/api/tasks/<id>` | 获取任务详情 |
| GET | `/api/tasks/<id>/log` | 获取日志内容 |
| POST | `/api/tasks/<id>/run` | 手动运行 |
| POST | `/api/tasks/<id>/toggle` | 切换启用/禁用 |
| POST | `/api/tasks/<id>` | 更新任务配置 |
| GET | `/api/status` | 统计信息 |

## 状态持久化

任务状态和运行历史存储在 `~/.openclaw/cron-panel/state.json`：

```json
{
  "tasks": {
    "ikuai-l2tp-monitor-sh": {
      "id": "...",
      "name": "...",
      "cron_expr": "...",
      "command": "...",
      "log_file": "...",
      "enabled": true,
      "last_run": "2026-04-02 20:00:00",
      "last_status": "success",
      "last_output_snippet": "...",
      "history": [...]
    }
  }
}
```

## 注意事项

- 修改任务配置会重写 crontab，建议先在 Linux crontab 中手动测试
- 日志文件路径必须是绝对路径，且有读取权限
- 手动运行的任务在后台线程执行，不会阻塞 Web 界面
- 如果任务 ID 重复（命令相同），会合并状态

## 故障排查

- **端口占用**: `lsof -i :5000` 查看，`kill <pid>` 结束进程
- **权限问题**: 确保可读取日志文件，可执行 crontab 命令
- **构建失败**: 确保 Node.js >= 18, npm >= 8

---

基于 Python 标准库 + React + Vite 构建。
