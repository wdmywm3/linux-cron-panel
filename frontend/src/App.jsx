import { useState, useEffect, useCallback } from 'react'

const tableStyle = {
  width: '100%',
  minWidth: 0,
  background: 'white',
  borderRadius: '8px',
  boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
  borderCollapse: 'collapse',
  tableLayout: 'fixed'
}

const cellStyle = {
  padding: '12px 16px',
  textAlign: 'left',
  borderBottom: '1px solid #eee',
  verticalAlign: 'middle'
}

const headerStyle = {
  ...cellStyle,
  background: '#f8f9fa',
  fontWeight: 600,
  color: '#555'
}

const nameCellStyle = {
  ...cellStyle,
  width: '16%',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap'
}

const cronCellStyle = {
  ...cellStyle,
  width: '10%',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap'
}

const commandCellStyle = {
  ...cellStyle,
  width: '34%',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap'
}

const lastRunCellStyle = {
  ...cellStyle,
  width: '18%',
  whiteSpace: 'nowrap'
}

const actionsCellStyle = {
  ...cellStyle,
  width: '22%'
}

const columnWidths = {
  name: '16%',
  cron: '10%',
  command: '34%',
  lastRun: '18%',
  actions: '22%'
}

const statusStyle = {
  padding: '4px 12px',
  borderRadius: '12px',
  fontSize: '12px',
  fontWeight: 500,
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  minWidth: '56px',
  whiteSpace: 'nowrap'
}

const buttonStyle = {
  padding: '6px 0',
  border: 'none',
  borderRadius: '4px',
  cursor: 'pointer',
  fontSize: '12px',
  color: 'white',
  whiteSpace: 'nowrap',
  display: 'inline-block',
  minWidth: '58px',
  textAlign: 'center'
}

const buttonGroupStyle = {
  display: 'flex',
  alignItems: 'center',
  flexWrap: 'nowrap',
  gap: '8px'
}

function App() {
  const [tasks, setTasks] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [selectedTask, setSelectedTask] = useState(null)
  const [editingTask, setEditingTask] = useState(null)
  const [showModal, setShowModal] = useState(false)
  const [tooltip, setTooltip] = useState({ visible: false, text: '', x: 0, y: 0 })

  const fetchTasks = useCallback(async () => {
    try {
      const res = await fetch('/api/tasks')
      if (!res.ok) throw new Error('Failed to fetch tasks')
      const data = await res.json()
      const nextTasks = Array.isArray(data.tasks) ? data.tasks : []
      if (nextTasks.length > 0 || !data.error) {
        setTasks(nextTasks)
      }
      setError(data.error || null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    setLoading(true)
    fetchTasks()
    const interval = setInterval(fetchTasks, 10000)
    return () => clearInterval(interval)
  }, [fetchTasks])

  const runTask = async (id) => {
    try {
      const res = await fetch(`/api/tasks/${id}/run`, { method: 'POST' })
      if (!res.ok) throw new Error('Failed to run task')
      setTimeout(fetchTasks, 2000)
    } catch (e) {
      alert('运行失败: ' + e.message)
    }
  }

  const toggleTask = async (id) => {
    try {
      const res = await fetch(`/api/tasks/${id}/toggle`, { method: 'POST' })
      if (!res.ok) throw new Error('Failed to toggle task')
      fetchTasks()
    } catch (e) {
      alert('切换失败: ' + e.message)
    }
  }

  const openEdit = (task) => {
    const displayName = task.name && task.name !== 'null' ? task.name : task.id
    setEditingTask({
      id: task.id,
      name: displayName,
      cron_expr: task.cron_expr,
      command: task.command,
      log_file: task.log_file,
      enabled: task.enabled
    })
    setShowModal(true)
  }

  const saveEdit = async () => {
    try {
      const res = await fetch(`/api/tasks/${editingTask.id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: editingTask.name,
          cron_expr: editingTask.cron_expr,
          command: editingTask.command,
          log_file: editingTask.log_file,
          enabled: editingTask.enabled
        })
      })
      if (!res.ok) throw new Error('Failed to save')
      setShowModal(false)
      fetchTasks()
    } catch (e) {
      alert('保存失败: ' + e.message)
    }
  }

  const viewLog = async (task) => {
    setSelectedTask(task)
    try {
      const res = await fetch(`/api/tasks/${task.id}/log`)
      if (!res.ok) throw new Error('Failed to fetch log')
      const text = await res.text()
      setSelectedTask({ ...task, logContent: text })
    } catch (e) {
      setSelectedTask({ ...task, logContent: '无法加载日志: ' + e.message })
    }
  }

  const statusClass = (task) => {
    if (!task.enabled) return 'disabled'
    if (task.last_status === 'running') return 'running'
    if (task.last_status === 'success') return 'success'
    if (task.last_status === 'failure') return 'failure'
    return ''
  }

  const statusLabel = (task) => {
    if (!task.enabled) return '已禁用'
    if (task.last_status === 'running') return '运行中'
    if (task.last_status === 'success') return '成功'
    if (task.last_status === 'failure') return '失败'
    return '-'
  }

  const getStatusColor = (task) => {
    const cls = statusClass(task)
    if (cls === 'success') return { background: '#d4edda', color: '#155724' }
    if (cls === 'failure') return { background: '#f8d7da', color: '#721c24' }
    if (cls === 'running') return { background: '#fff3cd', color: '#856404' }
    if (cls === 'disabled') return { background: '#e2e3e5', color: '#383d41' }
    return {}
  }

  const showTooltip = (text, event) => {
    if (!text) return
    setTooltip({
      visible: true,
      text,
      x: event.clientX + 12,
      y: event.clientY + 12
    })
  }

  const moveTooltip = (event) => {
    setTooltip((prev) => {
      if (!prev.visible) return prev
      return {
        ...prev,
        x: event.clientX + 12,
        y: event.clientY + 12
      }
    })
  }

  const hideTooltip = () => {
    setTooltip((prev) => ({ ...prev, visible: false }))
  }

  return (
    <div style={{ maxWidth: '1800px', margin: '0 auto', padding: '20px', fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif', background: '#f5f7fa', minHeight: '100vh' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <h1 style={{ fontSize: '24px', color: '#2c3e50', margin: 0 }}>⏰ Linux Cron Panel</h1>
        <button 
          onClick={fetchTasks}
          style={{ padding: '8px 16px', background: '#3498db', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', fontSize: '14px' }}
        >
          🔄 刷新
        </button>
      </header>

      {error && <div style={{ color: 'red', marginBottom: '20px' }}>错误: {error}</div>}

      {loading && tasks.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '40px', color: '#999' }}>加载中...</div>
      ) : tasks.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '40px', color: '#999' }}>暂无定时任务</div>
      ) : (
        <div className="table-responsive-wrapper">
          <table style={tableStyle} className="tasks-table">
            <colgroup>
              <col style={{ width: columnWidths.name }} />
              <col style={{ width: columnWidths.cron }} />
              <col style={{ width: columnWidths.command }} />
              <col style={{ width: columnWidths.lastRun }} />
              <col style={{ width: columnWidths.actions }} />
            </colgroup>
            <thead className="tasks-thead">
              <tr>
                <th style={{ ...headerStyle, width: columnWidths.name }}>名称</th>
                <th style={{ ...headerStyle, width: columnWidths.cron }}>Cron 表达式</th>
                <th style={{ ...headerStyle, width: columnWidths.command }}>命令</th>
                <th style={{ ...headerStyle, width: columnWidths.lastRun }}>最后执行</th>
                <th style={{ ...headerStyle, width: columnWidths.actions }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {tasks.map(task => (
                <tr key={task.id} style={{ borderBottom: '1px solid #eee' }} className="task-row">
                  <td style={nameCellStyle} className="col-name" data-label="名称">
                    <div
                      style={{ fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                      onMouseEnter={(e) => showTooltip(task.name && task.name !== 'null' ? task.name : task.id, e)}
                      onMouseMove={moveTooltip}
                      onMouseLeave={hideTooltip}
                    >
                      {task.name && task.name !== 'null' ? task.name : task.id}
                    </div>
                    <div
                      className="task-uuid-inline"
                      style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                    >
                      {task.id}
                    </div>
                  </td>
                  <td style={cronCellStyle} className="col-cron" data-label="Cron 表达式">
                    <code style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{task.cron_expr}</code>
                  </td>
                  <td
                    style={commandCellStyle}
                    className="col-command"
                    data-label="命令"
                    onMouseEnter={(e) => showTooltip(task.command, e)}
                    onMouseMove={moveTooltip}
                    onMouseLeave={hideTooltip}
                  >
                    {task.command}
                  </td>
                  <td style={lastRunCellStyle} className="col-last-run" data-label="最后执行">
                    <div className="last-run-content">
                      <span style={{ ...statusStyle, ...getStatusColor(task) }}>
                        {statusLabel(task)}
                      </span>
                      <span className="last-run-time">{task.last_run || '-'}</span>
                    </div>
                  </td>
                  <td style={actionsCellStyle} className="col-actions" data-label="操作">
                    <div style={buttonGroupStyle}>
                      <button style={{ ...buttonStyle, background: '#28a745' }} onClick={() => runTask(task.id)}>运行</button>
                      <button style={{ ...buttonStyle, background: '#6c757d' }} onClick={() => toggleTask(task.id)}>{task.enabled ? '禁用' : '启用'}</button>
                      <button style={{ ...buttonStyle, background: '#17a2b8' }} onClick={() => openEdit(task)}>编辑</button>
                      <button style={{ ...buttonStyle, background: '#6f42c1' }} onClick={() => viewLog(task)}>日志</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Edit Modal */}
      {showModal && editingTask && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }} onClick={(e) => { if (e.target === e.currentTarget) setShowModal(false) }}>
          <div style={{ background: 'white', borderRadius: '8px', width: '500px', maxWidth: '90%', boxShadow: '0 4px 16px rgba(0,0,0,0.2)', overflow: 'hidden' }}>
            <div style={{ padding: '16px 20px', borderBottom: '1px solid #eee', display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '18px', fontWeight: 600 }}>
              <span>编辑任务</span>
              <button style={{ background: 'none', border: 'none', fontSize: '24px', cursor: 'pointer', color: '#999', padding: 0, lineHeight: 1 }} onClick={() => setShowModal(false)}>×</button>
            </div>
            <div style={{ padding: '20px' }}>
              <label style={{ display: 'block', marginBottom: '6px', fontWeight: 500, color: '#555' }}>名称</label>
              <input type="text" style={{ width: '100%', padding: '8px', marginBottom: '16px', border: '1px solid #ddd', borderRadius: '4px', fontSize: '14px' }} value={editingTask.name} onChange={(e) => setEditingTask({...editingTask, name: e.target.value})} />
              <label style={{ display: 'block', marginBottom: '6px', fontWeight: 500, color: '#555' }}>Cron 表达式</label>
              <input type="text" style={{ width: '100%', padding: '8px', marginBottom: '16px', border: '1px solid #ddd', borderRadius: '4px', fontSize: '14px' }} value={editingTask.cron_expr} onChange={(e) => setEditingTask({...editingTask, cron_expr: e.target.value})} />
              <label style={{ display: 'block', marginBottom: '6px', fontWeight: 500, color: '#555' }}>命令</label>
              <textarea rows="3" style={{ width: '100%', padding: '8px', marginBottom: '16px', border: '1px solid #ddd', borderRadius: '4px', fontSize: '14px' }} value={editingTask.command} onChange={(e) => setEditingTask({...editingTask, command: e.target.value})} />
              <label style={{ display: 'block', marginBottom: '6px', fontWeight: 500, color: '#555' }}>日志文件</label>
              <input type="text" style={{ width: '100%', padding: '8px', marginBottom: '16px', border: '1px solid #ddd', borderRadius: '4px', fontSize: '14px' }} value={editingTask.log_file} onChange={(e) => setEditingTask({...editingTask, log_file: e.target.value})} />
              <label style={{ display: 'flex', alignItems: 'center', marginBottom: '6px', fontWeight: 500, color: '#555' }}>
                <input type="checkbox" style={{ marginRight: '8px' }} checked={editingTask.enabled} onChange={(e) => setEditingTask({...editingTask, enabled: e.target.checked})} /> 启用
              </label>
            </div>
            <div style={{ padding: '16px 20px', borderTop: '1px solid #eee', textAlign: 'right' }}>
              <button style={{ padding: '10px 20px', background: '#6c757d', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', marginRight: '8px' }} onClick={() => setShowModal(false)}>取消</button>
              <button style={{ padding: '10px 20px', background: '#3498db', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }} onClick={saveEdit}>保存</button>
            </div>
          </div>
        </div>
      )}

      {/* Log Modal */}
      {selectedTask && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }} onClick={(e) => { if (e.target === e.currentTarget) setSelectedTask(null) }}>
          <div style={{ background: 'white', borderRadius: '8px', width: '800px', maxWidth: '90%', height: '80vh', boxShadow: '0 4px 16px rgba(0,0,0,0.2)', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <div style={{ padding: '16px 20px', borderBottom: '1px solid #eee', display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '18px', fontWeight: 600 }}>
              <span>日志: {selectedTask.name}</span>
              <button style={{ background: 'none', border: 'none', fontSize: '24px', cursor: 'pointer', color: '#999', padding: 0, lineHeight: 1 }} onClick={() => setSelectedTask(null)}>×</button>
            </div>
            <div style={{ padding: '20px', overflow: 'auto', flex: 1, background: '#f8f9fa', fontFamily: 'monospace', fontSize: '12px', whiteSpace: 'pre-wrap' }}>
              {selectedTask.logContent || '加载中...'}
            </div>
            <div style={{ padding: '16px 20px', borderTop: '1px solid #eee', textAlign: 'right' }}>
              <button style={{ padding: '10px 20px', background: '#6c757d', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }} onClick={() => setSelectedTask(null)}>关闭</button>
            </div>
          </div>
        </div>
      )}

      {tooltip.visible && (
        <div
          style={{
            position: 'fixed',
            left: tooltip.x,
            top: tooltip.y,
            maxWidth: '520px',
            padding: '8px 10px',
            fontSize: '12px',
            lineHeight: 1.4,
            color: '#fff',
            background: 'rgba(33, 37, 41, 0.95)',
            borderRadius: '6px',
            boxShadow: '0 4px 16px rgba(0,0,0,0.25)',
            pointerEvents: 'none',
            zIndex: 2000,
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word'
          }}
        >
          {tooltip.text}
        </div>
      )}
    </div>
  )
}

export default App
