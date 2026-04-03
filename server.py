#!/usr/bin/env python3
"""
Linux Cron Panel - Linux Cron 任务管理界面
使用 Python 内置 http.server，零依赖
"""

import os
import json
import subprocess
import threading
import re
import urllib.parse
import hashlib
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

# 配置
STATE_FILE = os.path.expanduser('~/.openclaw/cron-panel/state.json')
WORKDIR = os.path.dirname(os.path.abspath(__file__))

if __name__ == '__main__':
    import sys
    sys.path.insert(0, os.path.join(WORKDIR, 'backend'))
    from server import run_server
    run_server(5002)
    raise SystemExit(0)

# 默认结构
def default_task(id, raw_line, cron_expr, command, log_file=None):
    return {
        "id": id,
        "name": id,
        "raw_line": raw_line,
        "cron_expr": cron_expr,
        "command": command,
        "log_file": log_file or f"/tmp/{id}.log",
        "enabled": not raw_line.strip().startswith('#'),
        "last_run": None,
        "last_status": None,
        "last_exit_code": None,
        "last_output_snippet": None,
        "history": []
    }

def load_state():
    if not os.path.exists(STATE_FILE):
        return {"tasks": {}, "version": "1.0"}
    try:
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    except:
        return {"tasks": {}, "version": "1.0"}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def read_crontab_lines():
    try:
        result = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
    except FileNotFoundError:
        return None, '系统中找不到 crontab 命令'
    except Exception as e:
        return None, f'读取 crontab 失败: {e}'
    if result.returncode != 0:
        stderr = (result.stderr or '').strip()
        if 'no crontab for' in stderr.lower():
            return [], None
        return None, f'读取 crontab 失败: {stderr or "未知错误"}'
    stdout = result.stdout.strip()
    return stdout.split('\n') if stdout else [], None

def parse_crontab_line(line):
    raw_line = line.rstrip('\n')
    line = raw_line.strip()
    if not line:
        return None
    enabled = not line.startswith('#')
    content = line[1:].strip() if not enabled else line
    parts = content.split(None, 5)
    if len(parts) < 6:
        return None
    cron_expr = ' '.join(parts[:5])
    command = parts[5]
    name = None
    comment_match = re.search(r'\s+#\s*name:\s*(.+?)(?:\s*\|.*)?$', command)
    if comment_match:
        name = comment_match.group(1).strip()
        command = command[:comment_match.start()].strip()
    log_file = None
    redirect_match = re.search(r'>>\s*(\S+)\s*2>&1', command)
    if redirect_match:
        log_file = redirect_match.group(1)
        command = re.sub(r'\s*>>\s*\S+\s*2>&1', '', command).strip()
    return {"cron_expr": cron_expr, "command": command, "log_file": log_file, "name": name, "enabled": enabled, "raw_line": raw_line}

def generate_task_id(cmd):
    if not cmd or not cmd.strip():
        return "unknown-task"
    clean_cmd = cmd.strip()
    first_segment = clean_cmd.split(';', 1)[0].strip()
    cd_match = re.match(r'^cd\s+([^\s;&|]+)\s*&&\s*(.+)$', first_segment)
    if cd_match:
        cd_path = os.path.basename(cd_match.group(1).rstrip('/'))
        if cd_path:
            task_id = re.sub(r'[^a-zA-Z0-9_-]', '-', cd_path).strip('-')
            if task_id and task_id.lower() not in ("null", "none"):
                return task_id
        first_segment = cd_match.group(2).strip()
    core_cmd = re.split(r'\s*(?:&&|\|\|)\s*', first_segment)[0].strip()
    tokens = core_cmd.split()
    candidate = tokens[0] if tokens else ''
    base = os.path.basename(candidate)
    if base in ('python', 'python3', 'bash', 'sh') and len(tokens) > 1:
        base = os.path.basename(tokens[1])
    task_id = re.sub(r'[^a-zA-Z0-9_-]', '-', base).strip('-')
    if not task_id or len(task_id) < 2 or task_id.lower() in ("null", "none"):
        cmd_hash = hashlib.md5(clean_cmd.encode()).hexdigest()[:8]
        task_id = f"task-{cmd_hash}"
    return task_id

def normalize_task_name(task, fallback_name):
    current_name = task.get("name")
    if current_name in (None, "", "null", "None"):
        task["name"] = fallback_name
    return task

def get_all_tasks():
    state = load_state()
    tasks = state.get("tasks", {})
    crontab_lines, error = read_crontab_lines()
    if error:
        return {"tasks": list(tasks.values()), "error": error}
    parsed = {}
    for line in crontab_lines:
        parsed_line = parse_crontab_line(line)
        if parsed_line:
            cmd = parsed_line['command']
            task_id = generate_task_id(cmd)
            if task_id in tasks:
                task = tasks[task_id]
                task.update({
                    "cron_expr": parsed_line['cron_expr'],
                    "command": parsed_line['command'],
                    "log_file": parsed_line['log_file'] or task.get('log_file'),
                    "enabled": parsed_line['enabled'],
                    "raw_line": parsed_line.get('raw_line', line)
                })
                if parsed_line.get('name'):
                    task['name'] = parsed_line['name']
            else:
                task = default_task(id=task_id, raw_line=parsed_line.get('raw_line', line), cron_expr=parsed_line['cron_expr'], command=parsed_line['command'], log_file=parsed_line['log_file'])
                if parsed_line.get('name'):
                    task['name'] = parsed_line['name']
            normalize_task_name(task, task_id)
            parsed[task_id] = task
    state["tasks"] = parsed
    save_state(state)
    return {"tasks": list(parsed.values()), "error": None}

def apply_task_run_update(task, run_at=None, status=None, exit_code=None, output_snippet=None):
    run_time = run_at or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    normalized_exit_code = None
    if exit_code is not None and exit_code != '':
        try:
            normalized_exit_code = int(exit_code)
        except:
            normalized_exit_code = None
    resolved_status = status
    if not resolved_status:
        if normalized_exit_code is None:
            resolved_status = "success"
        else:
            resolved_status = "success" if normalized_exit_code == 0 else "failure"
    task["last_run"] = run_time
    task["last_status"] = resolved_status
    task["last_exit_code"] = normalized_exit_code
    if output_snippet is not None:
        output_text = str(output_snippet)
        task["last_output_snippet"] = output_text[-500:] if output_text else "(无输出)"
    history = task.get("history", [])
    history.insert(0, {"run_at": task["last_run"], "status": task["last_status"], "exit_code": task.get("last_exit_code")})
    if len(history) > 20:
        history = history[:20]
    task["history"] = history

def run_task_async(task_id, command):
    def run():
        state = load_state()
        task = state["tasks"].get(task_id)
        if not task:
            return
        task["last_run"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        task["last_status"] = "running"
        save_state(state)
        try:
            proc = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=WORKDIR)
            output, _ = proc.communicate()
            apply_task_run_update(task, run_at=task["last_run"], exit_code=proc.returncode, output_snippet=output)
        except Exception as e:
            apply_task_run_update(task, run_at=task["last_run"], status="failure", output_snippet=str(e))
        save_state(state)
    threading.Thread(target=run, daemon=True).start()

def toggle_task_in_crontab(task_id, enable):
    try:
        result = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
        lines = result.stdout.strip().split('\n') if result.stdout.strip() else []
        state = load_state()
        task = state["tasks"].get(task_id)
        if not task:
            print(f"Toggle error: task {task_id} not found")
            return False
        raw_line_stripped = task["raw_line"].strip()
        new_lines = []
        changed = False
        for line in lines:
            if line.strip() == raw_line_stripped:
                if enable:
                    new_line = line.lstrip('#').lstrip()
                else:
                    if not line.strip().startswith('#'):
                        new_line = '#' + line
                    else:
                        new_line = line
                new_lines.append(new_line)
                changed = True
            else:
                new_lines.append(line)
        if not changed:
            # 即使没变也写回，确保一致性
            pass
        proc = subprocess.Popen(['crontab', '-'], input='\n'.join(new_lines) + '\n', text=True)
        stdout, stderr = proc.communicate()
        if proc.returncode != 0:
            print(f"Toggle error: crontab update failed: {stderr}")
            return False
        task["enabled"] = enable
        save_state(state)
        return True
    except Exception as e:
        print(f"Toggle error: {e}")
        return False

# HTML 页面（内嵌）
HTML = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Linux Cron Panel</title>
<style>
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f5f7fa; padding: 20px; }
.container { max-width: 1200px; margin: 0 auto; }
header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
h1 { font-size: 24px; color: #2c3e50; }
button { padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; font-size: 13px; }
.refresh { background: #3498db; color: white; }
.refresh:hover { background: #2980b9; }
table { width: 100%; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
th, td { padding: 12px 16px; text-align: left; border-bottom: 1px solid #eee; }
th { background: #f8f9fa; font-weight: 600; }
tr:hover { background: #f8f9fa; }
.status { padding: 4px 12px; border-radius: 12px; font-size: 12px; font-weight: 500; }
.success { background: #d4edda; color: #155724; }
.failure { background: #f8d7da; color: #721c24; }
.running { background: #fff3cd; color: #856404; }
.disabled { background: #e2e3e5; color: #383d41; }
.actions button { margin-right: 6px; }
.btn-run { background: #28a745; color: white; }
.btn-run:hover { background: #218838; }
.btn-toggle { background: #6c757d; color: white; }
.btn-edit { background: #17a2b8; color: white; }
.modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 1000; }
.modal-content { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); background: white; padding: 24px; border-radius: 8px; width: 500px; max-width: 90%; box-shadow: 0 4px 16px rgba(0,0,0,0.2); }
.modal-header { display: flex; justify-content: space-between; margin-bottom: 20px; }
.modal-body label { display: block; margin-bottom: 6px; font-weight: 500; }
.modal-body input, .modal-body textarea { width: 100%; padding: 8px; margin-bottom: 16px; border: 1px solid #ddd; border-radius: 4px; }
.modal-body input[type="checkbox"] { width: auto; margin-right: 8px; }
.modal-footer { text-align: right; }
.btn-save { padding: 10px 20px; background: #3498db; color: white; border: none; border-radius: 4px; cursor: pointer; }
.btn-cancel { padding: 10px 20px; background: #6c757d; color: white; border: none; border-radius: 4px; margin-right: 8px; cursor: pointer; }
.empty { text-align: center; padding: 40px; color: #999; }
.error { display: none; margin-bottom: 16px; color: #c0392b; background: #fdecea; padding: 12px 16px; border-radius: 8px; }
</style>
</head>
<body>
<div class="container">
<header>
<h1>⏰ Linux Cron Panel</h1>
<div>
<button class="refresh" onclick="loadTasks()">🔄 刷新</button>
</div>
</header>
<div id="error" class="error"></div>
<table>
<thead><tr><th>名称</th><th>Cron 表达式</th><th>命令</th><th>最后执行</th><th>状态</th><th>操作</th></tr></thead>
<tbody id="tasks"></tbody>
</table>
</div>
<div id="edit-modal" class="modal">
<div class="modal-content">
<div class="modal-header">
<h2>编辑任务</h2>
<span style="cursor:pointer;font-size:20px;" onclick="closeModal()">&times;</span>
</div>
<div class="modal-body">
<input type="hidden" id="edit-id">
<label>名称</label><input type="text" id="edit-name">
<label>Cron 表达式</label><input type="text" id="edit-cron">
<label>命令</label><textarea id="edit-command" rows="3"></textarea>
<label>日志文件</label><input type="text" id="edit-log">
<label><input type="checkbox" id="edit-enabled"> 启用</label>
</div>
<div class="modal-footer">
<button class="btn-cancel" onclick="closeModal()">取消</button>
<button class="btn-save" onclick="saveEdit()">保存</button>
</div>
</div>
</div>
<script>
function loadTasks() {
fetch('/api/tasks').then(r=>r.json()).then(data=>{
    const tbody = document.getElementById('tasks');
    const errorBox = document.getElementById('error');
    if (errorBox) {
        errorBox.textContent = data.error ? `错误: ${data.error}` : '';
        errorBox.style.display = data.error ? 'block' : 'none';
    }
    if (data.error && (!data.tasks || data.tasks.length===0)) {
        return;
    }
    if (!data.tasks || data.tasks.length===0) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty">暂无任务</td></tr>';
        return;
    }
    tbody.innerHTML = data.tasks.map(t=>`
        <tr>
            <td><strong>${t.name}</strong></td>
            <td><code>${t.cron_expr}</code></td>
            <td title="${t.command}">${t.command.length>50?t.command.substring(0,50)+'...':t.command}</td>
            <td>${t.last_run||'-'}</td>
            <td><span class="status ${t.enabled?(t.last_status||''):'disabled'}">${t.enabled?(t.last_status==='running'?'运行中':(t.last_status==='success'?'成功':(t.last_status==='failure'?'失败':'-'))):'已禁用'}</span></td>
            <td>
                <button class="btn-run" onclick="runTask('${t.id}')">▶ 运行</button>
                <button class="btn-toggle" onclick="toggleTask('${t.id}','${t.enabled}')">${t.enabled?'⏸ 禁用':'▶ 启用'}</button>
                <button class="btn-edit" onclick="editTask('${t.id}')">✏️ 编辑</button>
            </td>
        </tr>`).join('');
});
}
function runTask(id) {
fetch(`/api/tasks/${id}/run`, {method:'POST'}).then(r=>r.json()).then(d=>{
    if(d.ok){ alert('任务已开始执行'); setTimeout(loadTasks,1000); }
    else alert('启动失败: '+(d.error||'未知错误'));
});
}
function toggleTask(id, current) {
fetch(`/api/tasks/${id}/toggle`, {method:'POST'}).then(r=>r.json()).then(d=>{
    if(d.ok) loadTasks();
    else alert('操作失败: '+(d.error||'未知错误'));
});
}
function editTask(id) {
fetch(`/api/tasks/${id}`).then(r=>r.json()).then(d=>{
    document.getElementById('edit-id').value = d.id;
    document.getElementById('edit-name').value = d.name;
    document.getElementById('edit-cron').value = d.cron_expr;
    document.getElementById('edit-command').value = d.command;
    document.getElementById('edit-log').value = d.log_file;
    document.getElementById('edit-enabled').checked = d.enabled;
    document.getElementById('edit-modal').style.display = 'block';
});
}
function closeModal() { document.getElementById('edit-modal').style.display = 'none'; }
function saveEdit() {
    const id = document.getElementById('edit-id').value;
    const data = {
        name: document.getElementById('edit-name').value,
        cron_expr: document.getElementById('edit-cron').value,
        command: document.getElementById('edit-command').value,
        log_file: document.getElementById('edit-log').value,
        enabled: document.getElementById('edit-enabled').checked
    };
    fetch(`/api/tasks/${id}`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)})
        .then(r=>r.json()).then(d=>{
            if(d.ok){ closeModal(); loadTasks(); }
            else alert('保存失败: '+(d.error||'未知错误'));
        });
}
loadTasks();
setInterval(loadTasks, 10000);
</script>
</body></html>
'''

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split('?')[0]
        if path == '/' or path == '/index.html':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML.encode('utf-8'))
        elif path == '/api/tasks':
            payload = get_all_tasks()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode('utf-8'))
        elif path.startswith('/api/tasks/'):
            parts = [p for p in path.strip('/').split('/') if p]
            if len(parts) == 3 and parts[0] == 'api' and parts[1] == 'tasks':
                task_id = urllib.parse.unquote(parts[2])
                state = load_state()
                task = state["tasks"].get(task_id)
                if task:
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps(task).encode('utf-8'))
                else:
                    self.send_error(404, "Task not found")
            elif len(parts) == 2 and parts[0] == 'api' and parts[1] == 'tasks':
                tasks = get_all_tasks()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"tasks": tasks}).encode('utf-8'))
        elif path == '/api/status':
            state = load_state()
            tasks = state["tasks"].values()
            total = len(tasks)
            enabled = sum(1 for t in tasks if t['enabled'])
            running = sum(1 for t in tasks if t.get('last_status') == 'running')
            failed = sum(1 for t in tasks if t.get('last_status') == 'failure')
            success = sum(1 for t in tasks if t.get('last_status') == 'success')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"total": total, "enabled": enabled, "disabled": total-enabled, "running": running, "failed": failed, "success": success}).encode('utf-8'))
        else:
            self.send_error(404)

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode('utf-8') if length else ''
        try:
            data = json.loads(body) if body else {}
        except:
            data = {}
        path = self.path.split('?')[0]
        if path == '/api/report-run':
            task_id = data.get('task_id')
            if not task_id:
                self.send_error(400, "task_id is required")
                return
            state = load_state()
            task = state["tasks"].get(task_id)
            if not task:
                self.send_error(404, "Task not found")
                return
            apply_task_run_update(
                task,
                run_at=data.get('run_at'),
                status=data.get('status'),
                exit_code=data.get('exit_code'),
                output_snippet=data.get('output_snippet')
            )
            save_state(state)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "task_id": task_id}).encode('utf-8'))
        elif path.startswith('/api/tasks/'):
            parts = [p for p in path.split('/') if p]
            if len(parts) >= 3 and parts[0] == 'api' and parts[1] == 'tasks':
                task_id = urllib.parse.unquote(parts[2])
                action = parts[3] if len(parts) > 3 else None
                state = load_state()
                task = state["tasks"].get(task_id)
                if not task:
                    self.send_error(404, "Task not found")
                    return
                if action == 'run':
                    run_task_async(task_id, task['command'])
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(b'{"ok": true}')
                elif action == 'toggle':
                    success = toggle_task_in_crontab(task_id, not task['enabled'])
                    if success:
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/json')
                        self.end_headers()
                        self.wfile.write(b'{"ok": true}')
                    else:
                        self.send_response(500)
                        self.send_header('Content-Type', 'application/json')
                        self.end_headers()
                        self.wfile.write(b'{"error": "Failed to toggle task in crontab"}')
                else:
                    if 'name' in data: task['name'] = data['name']
                    if 'cron_expr' in data: task['cron_expr'] = data['cron_expr']
                    if 'command' in data: task['command'] = data['command']
                    if 'log_file' in data: task['log_file'] = data['log_file']
                    if 'enabled' in data: task['enabled'] = data['enabled']
                    task['raw_line'] = f"{task['cron_expr']} {task['command']} >> {task['log_file']} 2>&1"
                    try:
                        result = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
                        lines = result.stdout.strip().split('\n') if result.stdout.strip() else []
                        new_lines = []
                        for line in lines:
                            if line.strip() == task.get('_original_raw', task['raw_line']):
                                new_lines.append(task['raw_line'])
                            else:
                                new_lines.append(line)
                        if not any(line.strip() == task['raw_line'].strip() for line in new_lines):
                            new_lines.append(task['raw_line'])
                        proc = subprocess.Popen(['crontab', '-'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                        stdout, stderr = proc.communicate(input='\n'.join(new_lines) + '\n')
                    except Exception as e:
                        self.send_error(500, str(e))
                        return
                    task['_original_raw'] = task['raw_line']
                    save_state(state)
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(b'{"ok": true}')
            else:
                self.send_error(404)
        else:
            self.send_error(404)

def run_server(port=5002):
    server = ThreadingHTTPServer(('0.0.0.0', port), Handler)
    print(f"Linux Cron Panel started at http://localhost:{port}")
    server.serve_forever()

if __name__ == '__main__':
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    run_server(5002)
