/**
 * ChatGPT × Antigravity Bridge - Frontend Application Logic
 */

class BridgeApp {
  constructor() {
    this.currentView = 'dashboard';
    this.activeTaskId = null;
    this.eventSource = null;
    this.apiKey = localStorage.getItem('agb_session_key') || '';
    this.projects = [];

    this.init();
  }

  async init() {
    this.setupTheme();
    this.setupNavigation();
    this.setupModals();
    this.setupKeyboardShortcuts();

    // Check system status
    await this.checkStatus();
    setInterval(() => this.checkStatus(), 10000);

    // Initial data load
    await this.loadProjects();
    await this.loadRecentTasks();
    await this.loadChatGptInfo();
    await this.loadMcpTools();

    // Setup OpenAPI URL display
    const openapiUrl = window.location.origin + '/api/v1/chatgpt/openapi.json';
    const codeEl = document.getElementById('openapi-url-code');
    if (codeEl) codeEl.innerText = openapiUrl;

    const sseUrlEl = document.getElementById('mcp-sse-url');
    if (sseUrlEl) sseUrlEl.innerText = window.location.origin + '/mcp/sse';
  }

  getHeaders() {
    const headers = { 'Content-Type': 'application/json' };
    if (this.apiKey) {
      headers['Authorization'] = `Bearer ${this.apiKey}`;
    }
    return headers;
  }

  // --- Theme Management ---
  setupTheme() {
    const savedTheme = localStorage.getItem('agb_theme') || 'dark';
    document.documentElement.setAttribute('data-theme', savedTheme);

    const toggleBtn = document.getElementById('theme-toggle');
    if (toggleBtn) {
      toggleBtn.addEventListener('click', () => {
        const current = document.documentElement.getAttribute('data-theme');
        const next = current === 'light' ? 'dark' : 'light';
        document.documentElement.setAttribute('data-theme', next);
        localStorage.setItem('agb_theme', next);
      });
    }
  }

  // --- Navigation ---
  setupNavigation() {
    const navItems = document.querySelectorAll('.nav-item[data-view]');
    navItems.forEach(item => {
      item.addEventListener('click', () => {
        const view = item.getAttribute('data-view');
        this.switchView(view);
      });
    });
  }

  switchView(viewName) {
    this.currentView = viewName;
    document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
    const activeNav = document.querySelector(`.nav-item[data-view="${viewName}"]`);
    if (activeNav) activeNav.classList.add('active');

    document.querySelectorAll('.view-section').forEach(s => s.classList.remove('active'));
    const targetSection = document.getElementById(`view-${viewName}`);
    if (targetSection) targetSection.classList.add('active');

    // Update Topbar title
    const titles = {
      dashboard: 'Command Center',
      tasks: 'Tasks & Timeline',
      chatgpt: 'ChatGPT Integration Setup',
      mcp: 'Model Context Protocol (MCP) Server',
      projects: 'Projects Context',
      security: 'API Keys & Security',
      audit: 'Security Audit Logs'
    };
    document.getElementById('page-title').innerText = titles[viewName] || 'Bridge';

    // Lazy loads
    if (viewName === 'tasks') this.loadTasksList();
    if (viewName === 'projects') this.loadProjects();
    if (viewName === 'security') this.loadApiKeys();
    if (viewName === 'audit') this.loadAuditLogs();
  }

  // --- Status & Health ---
  async checkStatus() {
    try {
      const res = await fetch('/api/v1/system/status');
      if (!res.ok) throw new Error('Status check failed');
      const data = await res.json();

      const pill = document.getElementById('agent-status-pill');
      const dot = document.getElementById('agent-status-dot');
      const text = document.getElementById('agent-status-text');

      const provider = data.active_provider;
      const isOk = provider.status === 'connected';

      dot.style.backgroundColor = isOk ? 'var(--accent-green)' : 'var(--accent-red)';
      text.innerText = `${provider.display_name}: ${provider.status.toUpperCase()}`;

      // Update dashboard cards
      document.getElementById('dash-provider').innerText = provider.display_name;
      document.getElementById('dash-provider-desc').innerText = `Status: ${provider.status} | ID: ${provider.id}`;
      document.getElementById('dash-running-tasks').innerText = data.stats.running_tasks;
      document.getElementById('dash-active-sessions').innerText = data.stats.active_sessions;
      document.getElementById('dash-latency').innerText = `${provider.latency_ms} ms`;
    } catch (e) {
      document.getElementById('agent-status-text').innerText = 'Bridge Offline';
    }
  }

  async pingProvider() {
    try {
      this.toast('Pinging agent provider...', 'info');
      const res = await fetch('/api/v1/system/ping', { method: 'POST', headers: this.getHeaders() });
      const data = await res.json();
      this.toast(`Pong from ${data.display_name} (${data.latency_ms} ms)`, 'success');
      this.checkStatus();
    } catch (e) {
      this.toast('Ping failed', 'error');
    }
  }

  // --- Tasks Operations ---
  async loadRecentTasks() {
    try {
      const res = await fetch('/api/v1/tasks?limit=10', { headers: this.getHeaders() });
      if (!res.ok) return;
      const tasks = await res.json();

      const tbody = document.getElementById('recent-tasks-tbody');
      if (!tasks.length) {
        tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-muted);">No tasks yet. Submit one with "+ New Task".</td></tr>';
        return;
      }

      tbody.innerHTML = tasks.map(t => `
        <tr>
          <td><code style="font-family: var(--font-mono);">${t.id}</code></td>
          <td style="max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${this.escapeHtml(t.prompt)}</td>
          <td><span class="badge">${t.priority}</span></td>
          <td><span class="badge badge-${t.status}">${t.status}</span></td>
          <td style="color: var(--text-muted);">${new Date(t.created_at).toLocaleTimeString()}</td>
          <td style="font-family: var(--font-mono);">${t.duration_seconds ? t.duration_seconds + 's' : '--'}</td>
          <td>
            <button class="btn btn-secondary btn-sm" onclick="app.inspectTask('${t.id}')">View</button>
            ${t.status === 'running' ? `<button class="btn btn-danger btn-sm" onclick="app.cancelTask('${t.id}')">Cancel</button>` : ''}
            ${t.status === 'completed' ? `<button class="btn btn-primary btn-sm" onclick="app.openContinueModal('${t.id}', '${this.escapeHtml(t.prompt)}')">Continue</button>` : ''}
          </td>
        </tr>
      `).join('');
    } catch (e) {
      console.error(e);
    }
  }

  async loadTasksList() {
    try {
      const res = await fetch('/api/v1/tasks?limit=50', { headers: this.getHeaders() });
      if (!res.ok) return;
      const tasks = await res.json();

      const container = document.getElementById('tasks-master-list');
      if (!tasks.length) {
        container.innerHTML = '<p style="font-size: 12px; color: var(--text-muted);">No tasks found.</p>';
        return;
      }

      container.innerHTML = tasks.map(t => `
        <div class="metric-card" style="padding: 0.75rem; cursor: pointer; border-left: 3px solid ${this.getStatusColor(t.status)};" onclick="app.inspectTask('${t.id}')">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.25rem;">
            <span style="font-family: var(--font-mono); font-size: 11px; font-weight: 600;">${t.id}</span>
            <span class="badge badge-${t.status}">${t.status}</span>
          </div>
          <div style="font-size: 12px; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${this.escapeHtml(t.prompt)}</div>
          <div style="font-size: 11px; color: var(--text-muted); margin-top: 0.25rem;">${new Date(t.created_at).toLocaleTimeString()}</div>
        </div>
      `).join('');

      // Auto-select first task if none selected
      if (!this.activeTaskId && tasks.length > 0) {
        this.inspectTask(tasks[0].id);
      }
    } catch (e) {
      console.error(e);
    }
  }

  async inspectTask(taskId) {
    this.activeTaskId = taskId;
    this.switchView('tasks');

    try {
      const res = await fetch(`/api/v1/tasks/${taskId}`, { headers: this.getHeaders() });
      if (!res.ok) throw new Error('Task fetch failed');
      const task = await res.json();

      document.getElementById('detail-task-id').innerText = `Task: ${task.id}`;
      document.getElementById('detail-task-meta').innerText =
        `Project: ${task.project_id} | Status: ${task.status.toUpperCase()} | Priority: ${task.priority} | Session: ${task.session_id || 'N/A'}`;

      // Prompt view
      document.getElementById('detail-prompt-box').innerHTML = `
        <div style="background: var(--bg-input); padding: 0.75rem; border-radius: 6px; font-size: 13px; border: 1px solid var(--border-color);">
          <strong style="color: var(--accent-cyan); font-size: 11px; display: block; margin-bottom: 0.25rem;">ARCHITECT PROMPT:</strong>
          ${this.escapeHtml(task.prompt)}
        </div>
      `;

      // Action buttons
      const actionsEl = document.getElementById('detail-actions');
      actionsEl.innerHTML = '';
      if (task.status === 'running' || task.status === 'queued') {
        actionsEl.innerHTML += `<button class="btn btn-danger btn-sm" onclick="app.cancelTask('${task.id}')">Cancel Task</button>`;
      }
      if (task.status === 'completed') {
        actionsEl.innerHTML += `<button class="btn btn-primary btn-sm" onclick="app.openContinueModal('${task.id}', '${this.escapeHtml(task.prompt)}')">Continue Session</button>`;
      }

      // Response preview
      const respBox = document.getElementById('detail-response-box');
      if (task.antigravity_response) {
        respBox.innerText = task.antigravity_response.full_text || task.antigravity_response.summary || JSON.stringify(task.antigravity_response, null, 2);
      } else if (task.error_info) {
        respBox.innerText = `Error: ${JSON.stringify(task.error_info, null, 2)}`;
      } else {
        respBox.innerText = 'Task is currently processing or queued...';
      }

      // Start SSE stream for real-time logs
      this.subscribeTaskLogs(task.id);
    } catch (e) {
      this.toast('Failed to load task details', 'error');
    }
  }

  subscribeTaskLogs(taskId) {
    if (this.eventSource) {
      this.eventSource.close();
    }

    const logsContainer = document.getElementById('terminal-logs-container');
    logsContainer.innerHTML = '';

    this.eventSource = new EventSource(`/api/v1/tasks/${taskId}/events`);
    this.eventSource.addEventListener('log', (e) => {
      try {
        const log = JSON.parse(e.data);
        const line = document.createElement('div');
        line.className = 'log-line';

        const timeStr = log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : '00:00:00';
        let msgClass = '';
        if (log.level === 'tool' || log.tool_name) msgClass = 'tool';
        if (log.level === 'error') msgClass = 'error';
        if (log.level === 'thought') msgClass = 'thought';

        line.innerHTML = `
          <span class="log-time">[${timeStr}]</span>
          <span class="log-msg ${msgClass}">${this.escapeHtml(log.message)}</span>
        `;
        logsContainer.appendChild(line);
        logsContainer.scrollTop = logsContainer.scrollHeight;
      } catch (err) {
        console.error(err);
      }
    });

    this.eventSource.onerror = () => {
      // Event source closed or ended
    };
  }

  async submitNewTask() {
    const projectSelect = document.getElementById('new-task-project-select');
    const prioritySelect = document.getElementById('new-task-priority');
    const promptInput = document.getElementById('new-task-prompt');

    const prompt = promptInput.value.trim();
    if (!prompt) {
      this.toast('Please enter an architectural prompt', 'warning');
      return;
    }

    const payload = {
      project_id: projectSelect.value,
      priority: prioritySelect.value,
      prompt: prompt,
    };

    try {
      const res = await fetch('/api/v1/tasks', {
        method: 'POST',
        headers: this.getHeaders(),
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Task dispatch failed');
      }

      const task = await res.json();
      this.toast(`Task ${task.id} dispatched successfully!`, 'success');
      this.closeModals();
      promptInput.value = '';

      // Switch to tasks view and inspect
      await this.loadRecentTasks();
      this.inspectTask(task.id);
    } catch (e) {
      this.toast(e.message, 'error');
    }
  }

  openContinueModal(parentId, promptText) {
    document.getElementById('continue-parent-info').innerText = `Continuing from parent task: ${parentId}`;
    document.getElementById('modal-continue-task').classList.add('active');
    document.getElementById('continue-task-prompt').focus();
    this._continueParentId = parentId;
  }

  async submitContinueTask() {
    const promptInput = document.getElementById('continue-task-prompt');
    const prompt = promptInput.value.trim();
    if (!prompt) return;

    try {
      const res = await fetch(`/api/v1/tasks/${this._continueParentId}/continue`, {
        method: 'POST',
        headers: this.getHeaders(),
        body: JSON.stringify({ prompt: prompt }),
      });

      if (!res.ok) throw new Error('Continuation failed');
      const childTask = await res.json();
      this.toast(`Continuation task ${childTask.id} created!`, 'success');
      this.closeModals();
      promptInput.value = '';
      this.inspectTask(childTask.id);
    } catch (e) {
      this.toast(e.message, 'error');
    }
  }

  async cancelTask(taskId) {
    try {
      const res = await fetch(`/api/v1/tasks/${taskId}/cancel`, {
        method: 'POST',
        headers: this.getHeaders(),
      });
      if (!res.ok) throw new Error('Cancellation failed');
      this.toast(`Task ${taskId} cancelled`, 'info');
      this.loadRecentTasks();
      if (this.activeTaskId === taskId) this.inspectTask(taskId);
    } catch (e) {
      this.toast(e.message, 'error');
    }
  }

  // --- Projects ---
  async loadProjects() {
    try {
      const res = await fetch('/api/v1/projects', { headers: this.getHeaders() });
      if (!res.ok) return;
      this.projects = await res.json();

      // Populate project select in New Task modal
      const select = document.getElementById('new-task-project-select');
      if (select) {
        select.innerHTML = this.projects.map(p => `<option value="${p.id}">${p.name} (${p.workspace_path})</option>`).join('');
      }

      // Populate projects table
      const tbody = document.getElementById('projects-tbody');
      if (tbody) {
        tbody.innerHTML = this.projects.map(p => `
          <tr>
            <td><code style="font-family: var(--font-mono);">${p.id}</code></td>
            <td style="font-weight: 600;">${p.name}</td>
            <td style="font-family: var(--font-mono); font-size: 12px; color: var(--text-secondary);">${p.workspace_path}</td>
            <td><span class="badge badge-queued">${p.active_tasks_count || 0} active</span></td>
            <td style="color: var(--text-muted);">${new Date(p.created_at).toLocaleDateString()}</td>
            <td>
              <button class="btn btn-secondary btn-sm" onclick="app.inspectProjectContext('${p.id}')">Inspect Context</button>
            </td>
          </tr>
        `).join('');
      }
    } catch (e) {
      console.error(e);
    }
  }

  async submitNewProject() {
    const name = document.getElementById('new-project-name').value.trim();
    const path = document.getElementById('new-project-path').value.trim();
    const instructions = document.getElementById('new-project-instructions').value.trim();

    if (!name || !path) {
      this.toast('Name and workspace path are required', 'warning');
      return;
    }

    try {
      const res = await fetch('/api/v1/projects', {
        method: 'POST',
        headers: this.getHeaders(),
        body: JSON.stringify({ name, workspace_path: path, instructions }),
      });

      if (!res.ok) throw new Error('Failed to create project');
      this.toast('Project workspace added!', 'success');
      this.closeModals();
      await this.loadProjects();
    } catch (e) {
      this.toast(e.message, 'error');
    }
  }

  async inspectProjectContext(projectId) {
    try {
      const res = await fetch(`/api/v1/projects/${projectId}/context`, { headers: this.getHeaders() });
      if (!res.ok) throw new Error('Context inspection failed');
      const ctx = await res.json();
      alert(`Project: ${ctx.name}\nFiles Count: ${ctx.tracked_files_summary.length}\nTracked Files Preview:\n${ctx.tracked_files_summary.slice(0, 10).join('\n')}`);
    } catch (e) {
      this.toast(e.message, 'error');
    }
  }

  // --- API Keys ---
  async loadApiKeys() {
    try {
      const res = await fetch('/api/v1/api-keys', { headers: this.getHeaders() });
      if (!res.ok) return;
      const keys = await res.json();

      const tbody = document.getElementById('api-keys-tbody');
      tbody.innerHTML = keys.map(k => `
        <tr>
          <td style="font-weight: 600;">${k.name}</td>
          <td><code style="font-family: var(--font-mono);">${k.key_prefix}</code></td>
          <td>${k.scopes.map(s => `<span class="badge" style="margin-right: 4px;">${s}</span>`).join('')}</td>
          <td><span class="badge ${k.is_active ? 'badge-completed' : 'badge-failed'}">${k.is_active ? 'Active' : 'Revoked'}</span></td>
          <td style="color: var(--text-muted);">${new Date(k.created_at).toLocaleDateString()}</td>
          <td>
            ${k.is_active ? `<button class="btn btn-danger btn-sm" onclick="app.revokeKey('${k.id}')">Revoke</button>` : '--'}
          </td>
        </tr>
      `).join('');
    } catch (e) {
      console.error(e);
    }
  }

  async generateApiKey() {
    const name = document.getElementById('new-key-name').value.trim();
    const expires = document.getElementById('new-key-expires').value;
    if (!name) return;

    try {
      const res = await fetch('/api/v1/api-keys', {
        method: 'POST',
        headers: this.getHeaders(),
        body: JSON.stringify({
          name: name,
          expires_in_days: expires ? parseInt(expires) : null,
        }),
      });

      if (!res.ok) throw new Error('Failed to generate key');
      const keyData = await res.json();

      // Show key secret modal
      const body = document.getElementById('new-key-body');
      const footer = document.getElementById('new-key-footer');
      body.innerHTML = `
        <div style="background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.3); padding: 1rem; border-radius: 6px;">
          <p style="font-size: 13px; font-weight: 600; color: var(--accent-green); margin-bottom: 0.5rem;">API Key Created Successfully!</p>
          <p style="font-size: 12px; color: var(--text-secondary); margin-bottom: 0.75rem;">Copy this secret key immediately. You will NOT be able to view it again.</p>
          <input type="text" class="form-control" style="font-family: var(--font-mono); font-size: 12px; background: #000;" value="${keyData.raw_key}" readonly id="generated-key-val">
        </div>
      `;
      footer.innerHTML = `
        <button class="btn btn-primary" onclick="app.copyToClipboard(document.getElementById('generated-key-val').value)">Copy Secret</button>
        <button class="btn btn-secondary" onclick="app.closeModals(); app.loadApiKeys();">Done</button>
      `;

      // Save to localStorage for convenience in developer testing
      this.apiKey = keyData.raw_key;
      localStorage.setItem('agb_session_key', keyData.raw_key);
    } catch (e) {
      this.toast(e.message, 'error');
    }
  }

  async revokeKey(keyId) {
    if (!confirm('Are you sure you want to revoke this API key? External clients will immediately lose access.')) return;
    try {
      await fetch(`/api/v1/api-keys/${keyId}`, { method: 'DELETE', headers: this.getHeaders() });
      this.toast('Key revoked', 'info');
      this.loadApiKeys();
    } catch (e) {
      this.toast(e.message, 'error');
    }
  }

  // --- Audit Logs ---
  async loadAuditLogs() {
    try {
      const res = await fetch('/api/v1/audit-logs', { headers: this.getHeaders() });
      if (!res.ok) return;
      const logs = await res.json();

      const tbody = document.getElementById('audit-tbody');
      tbody.innerHTML = logs.map(l => `
        <tr>
          <td style="color: var(--text-muted); font-size: 12px;">${new Date(l.timestamp).toLocaleString()}</td>
          <td style="font-weight: 600;">${l.actor}</td>
          <td><span class="badge">${l.action}</span></td>
          <td><code style="font-family: var(--font-mono); font-size: 11px;">${l.resource_type}:${l.resource_id || ''}</code></td>
          <td><span class="badge ${l.status === 'success' ? 'badge-completed' : 'badge-failed'}">${l.status}</span></td>
          <td style="font-family: var(--font-mono); font-size: 11px;">${l.ip_address}</td>
        </tr>
      `).join('');
    } catch (e) {
      console.error(e);
    }
  }

  // --- ChatGPT & MCP ---
  async loadChatGptInfo() {
    try {
      const res = await fetch('/api/v1/chatgpt/instructions');
      if (res.ok) {
        const data = await res.json();
        const ta = document.getElementById('chatgpt-instructions-textarea');
        if (ta) ta.value = data.instructions;
      }
    } catch (e) {}
  }

  async loadMcpTools() {
    try {
      const tbody = document.getElementById('mcp-tools-tbody');
      if (!tbody) return;
      tbody.innerHTML = `
        <tr>
          <td><code style="font-family: var(--font-mono); color: var(--accent-cyan);">bridge_get_project_context</code></td>
          <td>Retrieve repository context, system instructions, and file trees managed by the Bridge.</td>
          <td><code>project_id</code></td>
        </tr>
        <tr>
          <td><code style="font-family: var(--font-mono); color: var(--accent-cyan);">bridge_report_task_progress</code></td>
          <td>Emit a real-time progress update or tool execution status to the Bridge and ChatGPT.</td>
          <td><code>task_id, message</code></td>
        </tr>
        <tr>
          <td><code style="font-family: var(--font-mono); color: var(--accent-cyan);">bridge_store_task_artifact</code></td>
          <td>Store generated code artifacts, test logs, or build output for a task.</td>
          <td><code>task_id, filename, content</code></td>
        </tr>
        <tr>
          <td><code style="font-family: var(--font-mono); color: var(--accent-cyan);">bridge_query_task_history</code></td>
          <td>Retrieve history of recent tasks, instructions, and decisions made by ChatGPT architect.</td>
          <td><code>project_id</code></td>
        </tr>
      `;
    } catch (e) {}
  }

  // --- Modals & Shortcuts ---
  setupModals() {
    document.getElementById('btn-new-task').addEventListener('click', () => {
      document.getElementById('modal-new-task').classList.add('active');
      document.getElementById('new-task-prompt').focus();
    });

    document.getElementById('btn-submit-task').addEventListener('click', () => this.submitNewTask());
    document.getElementById('btn-submit-continue').addEventListener('click', () => this.submitContinueTask());

    document.getElementById('btn-ping').addEventListener('click', () => this.pingProvider());

    const btnAddProj = document.getElementById('btn-add-project');
    if (btnAddProj) {
      btnAddProj.addEventListener('click', () => {
        document.getElementById('modal-add-project').classList.add('active');
      });
      document.getElementById('btn-submit-project').addEventListener('click', () => this.submitNewProject());
    }

    const btnNewKey = document.getElementById('btn-new-key');
    if (btnNewKey) {
      btnNewKey.addEventListener('click', () => {
        document.getElementById('modal-new-key').classList.add('active');
      });
      document.getElementById('btn-generate-key').addEventListener('click', () => this.generateApiKey());
    }
  }

  setupKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        this.closeModals();
      }
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        if (document.getElementById('modal-new-task').classList.contains('active')) {
          this.submitNewTask();
        } else if (document.getElementById('modal-continue-task').classList.contains('active')) {
          this.submitContinueTask();
        }
      }
    });
  }

  closeModals() {
    document.querySelectorAll('.modal-backdrop').forEach(m => m.classList.remove('active'));
  }

  toast(msg, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = 'toast';
    const colors = {
      info: 'var(--accent-blue)',
      success: 'var(--accent-green)',
      warning: 'var(--accent-amber)',
      error: 'var(--accent-red)',
    };
    toast.style.borderLeft = `4px solid ${colors[type] || colors.info}`;
    toast.innerText = msg;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
  }

  copyToClipboard(text) {
    navigator.clipboard.writeText(text);
    this.toast('Copied to clipboard!', 'success');
  }

  copyInstructions() {
    const val = document.getElementById('chatgpt-instructions-textarea').value;
    this.copyToClipboard(val);
  }

  getStatusColor(status) {
    const colors = {
      queued: '#9ca3af',
      running: '#60a5fa',
      completed: '#34d399',
      failed: '#f87171',
      cancelled: '#fbbf24',
    };
    return colors[status] || '#9ca3af';
  }

  escapeHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }
}

// Instantiate global app
window.app = new BridgeApp();
