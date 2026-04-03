#!/usr/bin/env python3
"""Linux Cron Panel API (pure Python stdlib, zero dependencies)"""

import os
import json
import subprocess
import threading
import re
import urllib.parse
import uuid
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

# Configuration
STATE_FILE = os.path.expanduser('~/.openclaw/linux-cron-panel/state.json')
FRONTEND_DIR = os.path.expanduser('~/.openclaw/linux-cron-panel/frontend/dist')
WORKDIR = os.path.dirname(os.path.abspath(__file__))
UUID_TASK_PATTERN = re.compile(r'^task_[0-9a-f]{16}$')
API_VERSION = "1.1.0"

def is_uuid_task_id(task_id):
    return bool(task_id and UUID_TASK_PATTERN.match(task_id))

def strip_legacy_report_callback(command):
    text = str(command or "").strip()
    pattern = r';\s*code=\$\?;\s*curl\s+-sS\s+-X\s+POST\s+https?://(?:127\.0\.0\.1|localhost):\d+/api/report-run\b.*?\|\|\s*true\s*$'
    return re.sub(pattern, '', text).strip()

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

def infer_default_name(command):
    clean_cmd = str(command or "").strip()
    if not clean_cmd:
        return "task"
    first_segment = clean_cmd.split(';', 1)[0].strip()
    cd_match = re.match(r'^cd\s+([^\s;&|]+)\s*&&\s*(.+)$', first_segment)
    if cd_match:
        first_segment = cd_match.group(2).strip()
    core_cmd = re.split(r'\s*(?:&&|\|\|)\s*', first_segment)[0].strip()
    tokens = core_cmd.split()
    candidate = tokens[0] if tokens else ''
    base = os.path.basename(candidate)
    if base in ('python', 'python3', 'bash', 'sh') and len(tokens) > 1:
        base = os.path.basename(tokens[1])
    name = re.sub(r'[^a-zA-Z0-9_-]', '-', base).strip('-')
    return name or "task"

def default_task(id, raw_line, cron_expr, command, log_file=None, name=None):
    return {
        "id": id,
        "name": name or infer_default_name(command),
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

def generate_uuid_id():
    return f"task_{uuid.uuid4().hex[:16]}"

def parse_crontab_line(line):
    raw_line = line.rstrip('\n')
    text = raw_line.strip()
    if not text:
        return None
    enabled = not text.startswith('#')
    content = text[1:].strip() if not enabled else text
    parts = content.split(None, 5)
    if len(parts) < 6:
        return None
    cron_expr = ' '.join(parts[:5])
    command = parts[5].strip()
    panel_id = None
    name = None
    panel_match = re.search(r'\s+#\s*panel:id=([A-Za-z0-9_-]+)(?:\|name=([^#]*))?\s*$', command)
    if panel_match:
        panel_id = panel_match.group(1).strip()
        raw_name = (panel_match.group(2) or '').strip()
        if raw_name:
            name = raw_name
        command = command[:panel_match.start()].strip()
    else:
        comment_match = re.search(r'\s+#\s*name:\s*(.+?)\s*$', command)
        if comment_match:
            name = comment_match.group(1).strip()
            command = command[:comment_match.start()].strip()
    command = strip_legacy_report_callback(command)
    log_file = None
    redirect_match = re.search(r'\s*>>\s*(\S+)\s*2>&1\s*$', command)
    if redirect_match:
        log_file = redirect_match.group(1)
        command = command[:redirect_match.start()].strip()
    return {
        "cron_expr": cron_expr,
        "command": command,
        "log_file": log_file,
        "name": name,
        "enabled": enabled,
        "raw_line": raw_line,
        "panel_id": panel_id
    }

def normalize_task_name(task, fallback_name):
    current_name = task.get("name")
    if current_name in (None, "", "null", "None"):
        task["name"] = fallback_name
    return task

def compose_raw_line(task):
    name = str(task.get("name") or task["id"]).replace('|', '-').replace('\n', ' ').strip()
    command = strip_legacy_report_callback(str(task["command"]).strip())
    if task.get("log_file") and not re.search(r'>>\s*\S+\s*2>&1', command):
        command = f"{command} >> {task['log_file']} 2>&1"
    command = f"{command} # panel:id={task['id']}|name={name}"
    line = f"{task['cron_expr']} {command}"
    return line if task.get("enabled", True) else f"# {line}"

def write_crontab_lines(lines):
    input_str = '\n'.join(lines).strip('\n')
    if input_str:
        input_str += '\n'
    proc = subprocess.Popen(['crontab', '-'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    _, stderr = proc.communicate(input=input_str)
    if proc.returncode != 0:
        return (stderr or '未知错误').strip()
    return None

def find_line_index_by_task_id(lines, task_id):
    for i, line in enumerate(lines):
        parsed = parse_crontab_line(line)
        if parsed and parsed.get("panel_id") == task_id:
            return i
    return None

def upsert_task_in_crontab(task):
    lines, error = read_crontab_lines()
    if error:
        return error
    new_line = compose_raw_line(task)
    idx = find_line_index_by_task_id(lines, task["id"])
    if idx is None:
        lines.append(new_line)
    else:
        lines[idx] = new_line
    write_error = write_crontab_lines(lines)
    if write_error:
        return write_error
    task["raw_line"] = new_line
    return None

def remove_task_from_crontab(task_id):
    lines, error = read_crontab_lines()
    if error:
        return error
    new_lines = []
    for line in lines:
        parsed = parse_crontab_line(line)
        if parsed and parsed.get("panel_id") == task_id:
            continue
        new_lines.append(line)
    write_error = write_crontab_lines(new_lines)
    if write_error:
        return write_error
    return None

def sync_tasks_from_crontab():
    state = load_state()
    tasks = state.get("tasks", {}) or {}
    crontab_lines, error = read_crontab_lines()
    if error:
        return {"tasks": list(tasks.values()), "error": error}
    parsed = {}
    canonical_lines = []
    changed = False
    consumed_legacy_keys = set()
    for line in crontab_lines:
        parsed_line = parse_crontab_line(line)
        if parsed_line:
            original_panel_id = parsed_line.get("panel_id")
            task_id = original_panel_id if is_uuid_task_id(original_panel_id) else generate_uuid_id()
            if not is_uuid_task_id(original_panel_id):
                changed = True
            if task_id in tasks:
                task = tasks[task_id]
            else:
                legacy_key = None
                if original_panel_id and original_panel_id in tasks:
                    legacy_key = original_panel_id
                for current_id, current_task in tasks.items():
                    if legacy_key:
                        break
                    if current_id in consumed_legacy_keys:
                        continue
                    if current_task.get("cron_expr") == parsed_line.get("cron_expr") and current_task.get("command") == parsed_line.get("command"):
                        legacy_key = current_id
                        break
                if legacy_key:
                    consumed_legacy_keys.add(legacy_key)
                    task = tasks[legacy_key]
                    task["id"] = task_id
                else:
                    task = default_task(
                        id=task_id,
                        raw_line=parsed_line.get('raw_line', line),
                        cron_expr=parsed_line['cron_expr'],
                        command=parsed_line['command'],
                        log_file=parsed_line['log_file'],
                        name=parsed_line.get('name') or (original_panel_id if original_panel_id and not is_uuid_task_id(original_panel_id) else None)
                    )
            task.update({
                "id": task_id,
                "cron_expr": parsed_line['cron_expr'],
                "command": parsed_line['command'],
                "log_file": parsed_line['log_file'] or task.get('log_file'),
                "enabled": parsed_line['enabled'],
                "raw_line": parsed_line.get('raw_line', line)
            })
            if parsed_line.get('name'):
                task['name'] = parsed_line['name']
            normalize_task_name(task, infer_default_name(task.get("command")))
            canonical_line = compose_raw_line(task)
            if canonical_line.strip() != line.strip():
                changed = True
            task["raw_line"] = canonical_line
            parsed[task_id] = task
            canonical_lines.append(canonical_line)
    if changed:
        write_error = write_crontab_lines(canonical_lines)
        if write_error:
            state["tasks"] = parsed
            save_state(state)
            return {"tasks": list(parsed.values()), "error": f"迁移写入失败: {write_error}"}
    state["tasks"] = parsed
    save_state(state)
    return {"tasks": list(parsed.values()), "error": None}

def get_all_tasks():
    return sync_tasks_from_crontab()

def ensure_tasks_synced():
    sync_tasks_from_crontab()

def create_task(data):
    ensure_tasks_synced()
    cron_expr = (data.get("cron_expr") or "").strip()
    command = strip_legacy_report_callback((data.get("command") or "").strip())
    if not cron_expr or not command:
        return None, "cron_expr 和 command 必填"
    task_id = generate_uuid_id()
    task = default_task(
        id=task_id,
        raw_line="",
        cron_expr=cron_expr,
        command=command,
        log_file=(data.get("log_file") or f"/tmp/{task_id}.log").strip()
    )
    task["enabled"] = bool(data.get("enabled", True))
    if "name" in data:
        task["name"] = str(data.get("name") or "").strip()
    normalize_task_name(task, infer_default_name(task.get("command")))
    task["raw_line"] = compose_raw_line(task)
    error = upsert_task_in_crontab(task)
    if error:
        return None, error
    state = load_state()
    tasks = state.get("tasks", {})
    tasks[task_id] = task
    state["tasks"] = tasks
    save_state(state)
    return task, None

def update_task(task_id, data):
    ensure_tasks_synced()
    state = load_state()
    tasks = state.get("tasks", {})
    task = tasks.get(task_id)
    if not task:
        return None, "Task not found"
    if "name" in data:
        task["name"] = str(data.get("name") or "").strip()
    if "cron_expr" in data:
        task["cron_expr"] = str(data.get("cron_expr") or "").strip()
    if "command" in data:
        task["command"] = strip_legacy_report_callback(str(data.get("command") or "").strip())
    if "log_file" in data:
        task["log_file"] = str(data.get("log_file") or "").strip()
    if "enabled" in data:
        task["enabled"] = bool(data.get("enabled"))
    normalize_task_name(task, infer_default_name(task.get("command")))
    task["raw_line"] = compose_raw_line(task)
    error = upsert_task_in_crontab(task)
    if error:
        return None, error
    tasks[task_id] = task
    state["tasks"] = tasks
    save_state(state)
    return task, None

def delete_task(task_id):
    ensure_tasks_synced()
    state = load_state()
    tasks = state.get("tasks", {})
    if task_id not in tasks:
        return "Task not found"
    error = remove_task_from_crontab(task_id)
    if error:
        return error
    tasks.pop(task_id, None)
    state["tasks"] = tasks
    save_state(state)
    return None

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
    ensure_tasks_synced()
    state = load_state()
    task = state.get("tasks", {}).get(task_id)
    if not task:
        return False
    task["enabled"] = enable
    task["raw_line"] = compose_raw_line(task)
    error = upsert_task_in_crontab(task)
    if error:
        return False
    state["tasks"][task_id] = task
    save_state(state)
    return True

class handler(BaseHTTPRequestHandler):
    def send_json(self, status_code, payload):
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode('utf-8'))

    def do_GET(self):
        path = self.path.split('?')[0]
        if path == '/' or path.startswith('/index.html') or path.startswith('/assets/'):
            file_path = os.path.join(FRONTEND_DIR, path.lstrip('/') or 'index.html')
            if os.path.exists(file_path) and os.path.isfile(file_path):
                with open(file_path, 'rb') as f:
                    content = f.read()
                ext = os.path.splitext(file_path)[1]
                content_type = {
                    '.html': 'text/html',
                    '.js': 'application/javascript',
                    '.css': 'text/css',
                    '.json': 'application/json',
                    '.svg': 'image/svg+xml'
                }.get(ext, 'application/octet-stream')
                self.send_response(200)
                self.send_header('Content-Type', content_type)
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_error(404)
            return
        if path == '/api/tasks':
            payload = get_all_tasks()
            self.send_json(200, payload)
        elif path.startswith('/api/tasks/'):
            parts = [p for p in path.strip('/').split('/') if p]
            if len(parts) == 4 and parts[0] == 'api' and parts[1] == 'tasks' and parts[3] == 'log':
                task_id = urllib.parse.unquote(parts[2])
                ensure_tasks_synced()
                state = load_state()
                task = state["tasks"].get(task_id)
                if task:
                    if task.get('log_file'):
                        try:
                            with open(task['log_file'], 'r', encoding='utf-8', errors='ignore') as f:
                                lines = f.readlines()[-100:]
                            content = ''.join(lines)
                            self.send_response(200)
                            self.send_header('Content-Type', 'text/plain; charset=utf-8')
                            self.end_headers()
                            self.wfile.write(content.encode('utf-8'))
                        except Exception as e:
                            self.send_error(500, str(e))
                    else:
                        self.send_error(404, "Log not available")
                else:
                    self.send_error(404, "Task not found")
            elif len(parts) == 3 and parts[0] == 'api' and parts[1] == 'tasks':
                task_id = urllib.parse.unquote(parts[2])
                ensure_tasks_synced()
                state = load_state()
                task = state["tasks"].get(task_id)
                if task:
                    self.send_json(200, task)
                else:
                    self.send_error(404, "Task not found")
            else:
                self.send_error(404)
        elif path == '/api/status':
            ensure_tasks_synced()
            state = load_state()
            tasks = state["tasks"].values()
            total = len(tasks)
            enabled = sum(1 for t in tasks if t['enabled'])
            running = sum(1 for t in tasks if t.get('last_status') == 'running')
            failed = sum(1 for t in tasks if t.get('last_status') == 'failure')
            success = sum(1 for t in tasks if t.get('last_status') == 'success')
            self.send_json(200, {"total": total, "enabled": enabled, "disabled": total-enabled, "running": running, "failed": failed, "success": success})
        elif path == '/api/version':
            self.send_json(200, {
                "ok": True,
                "service": "linux-cron-panel",
                "version": API_VERSION,
                "now": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
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
            ensure_tasks_synced()
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
            self.send_json(200, {"ok": True, "task_id": task_id})
        elif path == '/api/tasks':
            task, error = create_task(data)
            if error:
                self.send_error(400, error)
                return
            self.send_json(201, task)
        elif path.startswith('/api/tasks/'):
            parts = [p for p in path.split('/') if p]
            if len(parts) >= 3 and parts[0] == 'api' and parts[1] == 'tasks':
                task_id = urllib.parse.unquote(parts[2])
                action = parts[3] if len(parts) > 3 else None
                if action == 'run':
                    ensure_tasks_synced()
                    state = load_state()
                    task = state["tasks"].get(task_id)
                    if not task:
                        self.send_error(404, "Task not found")
                        return
                    run_task_async(task_id, task['command'])
                    self.send_json(200, {"ok": True})
                elif action == 'toggle':
                    ensure_tasks_synced()
                    state = load_state()
                    task = state["tasks"].get(task_id)
                    if not task:
                        self.send_error(404, "Task not found")
                        return
                    success = toggle_task_in_crontab(task_id, not task.get('enabled', True))
                    if success:
                        self.send_json(200, {"ok": True})
                    else:
                        self.send_error(500, "Failed to toggle task in crontab")
                else:
                    task, error = update_task(task_id, data)
                    if error:
                        self.send_error(400, error)
                        return
                    self.send_json(200, task)
            else:
                self.send_error(404)
        else:
            self.send_error(404)

    def do_PUT(self):
        path = self.path.split('?')[0]
        parts = [p for p in path.split('/') if p]
        if not (len(parts) == 3 and parts[0] == 'api' and parts[1] == 'tasks'):
            self.send_error(404)
            return
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode('utf-8') if length else ''
        try:
            data = json.loads(body) if body else {}
        except:
            data = {}
        task_id = urllib.parse.unquote(parts[2])
        task, error = update_task(task_id, data)
        if error:
            self.send_error(400, error)
            return
        self.send_json(200, task)

    def do_DELETE(self):
        path = self.path.split('?')[0]
        parts = [p for p in path.split('/') if p]
        if not (len(parts) == 3 and parts[0] == 'api' and parts[1] == 'tasks'):
            self.send_error(404)
            return
        task_id = urllib.parse.unquote(parts[2])
        error = delete_task(task_id)
        if error:
            self.send_error(400, error)
            return
        self.send_json(200, {"ok": True, "id": task_id})

def run_server(port=5002):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    server = ThreadingHTTPServer(('0.0.0.0', port), handler)
    print(f"Linux Cron Panel API: http://localhost:{port}")
    server.serve_forever()

if __name__ == '__main__':
    run_server(5002)
