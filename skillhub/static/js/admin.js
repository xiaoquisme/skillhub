/**
 * SkillHub Admin - User management UI (standalone page)
 */
const Admin = {
    bindEvents() {
        // Create user form
        const createUserForm = document.getElementById('create-user-form');
        if (createUserForm) {
            createUserForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const username = document.getElementById('new-username').value;
                const password = document.getElementById('new-password').value;
                const role = document.getElementById('new-role').value;

                try {
                    const response = await fetch('/api/users', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Authorization': 'Bearer ' + Auth.getToken(),
                        },
                        body: JSON.stringify({ username, password, role }),
                    });

                    if (!response.ok) {
                        const error = await response.json().catch(() => ({}));
                        throw new Error(error.detail || '创建用户失败');
                    }

                    createUserForm.reset();
                    this.loadUsers();
                } catch (err) {
                    alert(err.message);
                }
            });
        }

        // Load users button
        const loadUsersBtn = document.getElementById('load-users-btn');
        if (loadUsersBtn) {
            loadUsersBtn.addEventListener('click', () => this.loadUsers());
        }

        // Create project form
        const createProjectForm = document.getElementById('create-project-form');
        if (createProjectForm) {
            createProjectForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const name = document.getElementById('new-project-name').value;
                const display_name = document.getElementById('new-project-display-name').value || null;
                const description = document.getElementById('new-project-description').value || null;

                try {
                    const response = await fetch('/api/projects', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Authorization': 'Bearer ' + Auth.getToken(),
                        },
                        body: JSON.stringify({ name, display_name, description }),
                    });

                    if (!response.ok) {
                        const error = await response.json().catch(() => ({}));
                        throw new Error(error.detail || '创建项目失败');
                    }

                    createProjectForm.reset();
                    this.loadProjects();
                } catch (err) {
                    alert(err.message);
                }
            });
        }

        // Load projects button
        const loadProjectsBtn = document.getElementById('load-projects-btn');
        if (loadProjectsBtn) {
            loadProjectsBtn.addEventListener('click', () => this.loadProjects());
        }

        // Create marketplace source form
        const createMarketplaceForm = document.getElementById('create-marketplace-form');
        if (createMarketplaceForm) {
            createMarketplaceForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const name = document.getElementById('new-marketplace-name').value;
                const location = document.getElementById('new-marketplace-location').value;
                const source_ref = document.getElementById('new-marketplace-ref').value || null;
                const project = document.getElementById('new-marketplace-project').value || null;
                const sync_interval_minutes = parseInt(document.getElementById('new-marketplace-interval').value, 10) || 0;

                try {
                    const response = await fetch('/api/marketplaces', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Authorization': 'Bearer ' + Auth.getToken(),
                        },
                        body: JSON.stringify({ name, location, source_ref, project, sync_interval_minutes }),
                    });

                    if (!response.ok) {
                        const error = await response.json().catch(() => ({}));
                        throw new Error(error.detail || '添加源失败');
                    }

                    createMarketplaceForm.reset();
                    this.loadMarketplaces();
                } catch (err) {
                    alert(err.message);
                }
            });
        }

        // Load marketplaces button
        const loadMarketplacesBtn = document.getElementById('load-marketplaces-btn');
        if (loadMarketplacesBtn) {
            loadMarketplacesBtn.addEventListener('click', () => this.loadMarketplaces());
        }
    },

    async loadUsers() {
        const container = document.getElementById('users-list');
        if (!container) return;

        try {
            const response = await fetch('/api/users', {
                headers: { 'Authorization': 'Bearer ' + Auth.getToken() },
            });

            if (!response.ok) throw new Error('加载用户失败');

            const users = await response.json();

            if (users.length === 0) {
                container.innerHTML = '<p class="empty">暂无用户</p>';
                return;
            }

            container.innerHTML = users.map(user => `
                <div class="user-card">
                    <div class="user-info">
                        <strong>${this.escapeHtml(user.username)}</strong>
                        <span class="role-badge role-${user.role}">${user.role === 'admin' ? '管理员' : user.role === 'publisher' ? '发布者' : '观察者'}</span>
                    </div>
                    <div class="user-actions">
                        ${user.role !== 'admin' ? `
                            <button class="btn btn-sm btn-secondary" onclick="Admin.changeRole('${user.id}', '${user.role}')">修改角色</button>
                            <button class="btn btn-sm btn-danger" onclick="Admin.deleteUser('${user.id}', '${this.escapeHtml(user.username)}')">删除</button>
                        ` : ''}
                        <button class="btn btn-sm btn-secondary" onclick="Admin.resetPassword('${user.id}', '${this.escapeHtml(user.username)}')">重置密码</button>
                    </div>
                </div>
            `).join('');
        } catch (err) {
            container.innerHTML = '<p class="error">加载用户失败</p>';
            console.error(err);
        }
    },

    async changeRole(userId, currentRole) {
        const roles = ['admin', 'publisher', 'viewer'];
        const roleLabels = { admin: '管理员', publisher: '发布者', viewer: '观察者' };
        const newRole = prompt(`修改用户角色（当前: ${roleLabels[currentRole] || currentRole}）\n可选角色: ${roles.map(r => roleLabels[r]).join(', ')}`, currentRole);

        if (!newRole || newRole === currentRole) return;
        if (!roles.includes(newRole)) {
            alert('无效的角色');
            return;
        }

        try {
            const response = await fetch(`/api/users/${userId}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer ' + Auth.getToken(),
                },
                body: JSON.stringify({
                    username: 'placeholder',
                    password: 'placeholder',
                    role: newRole,
                }),
            });

            if (!response.ok) {
                const error = await response.json().catch(() => ({}));
                throw new Error(error.detail || '修改角色失败');
            }

            this.loadUsers();
        } catch (err) {
            alert(err.message);
        }
    },

    async deleteUser(userId, username) {
        if (!confirm(`确定要删除用户 "${username}" 吗？`)) return;

        try {
            const response = await fetch(`/api/users/${userId}`, {
                method: 'DELETE',
                headers: { 'Authorization': 'Bearer ' + Auth.getToken() },
            });

            if (!response.ok) {
                const error = await response.json().catch(() => ({}));
                throw new Error(error.detail || '删除用户失败');
            }

            this.loadUsers();
        } catch (err) {
            alert(err.message);
        }
    },

    async resetPassword(userId, username) {
        const newPassword = prompt(`为 "${username}" 输入新密码:`);
        if (!newPassword) return;

        try {
            const response = await fetch(`/api/users/${userId}/reset-password`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer ' + Auth.getToken(),
                },
                body: JSON.stringify({ new_password: newPassword }),
            });

            if (!response.ok) {
                const error = await response.json().catch(() => ({}));
                throw new Error(error.detail || '重置密码失败');
            }

            alert(`已重置 ${username} 的密码`);
        } catch (err) {
            alert(err.message);
        }
    },

    escapeHtml(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    },

    // ========== Project Management ==========

    async loadProjects() {
        const container = document.getElementById('projects-list');
        if (!container) return;

        try {
            const response = await fetch('/api/projects', {
                headers: { 'Authorization': 'Bearer ' + Auth.getToken() },
            });

            if (!response.ok) throw new Error('加载项目失败');

            const projects = await response.json();

            if (projects.length === 0) {
                container.innerHTML = '<p class="empty">暂无项目</p>';
                return;
            }

            container.innerHTML = projects.map(project => `
                <div class="user-card">
                    <div class="user-info">
                        <strong>${this.escapeHtml(project.display_name || project.name)}</strong>
                        <span class="role-badge">${project.name}</span>
                        ${project.description ? `<span class="text-muted">${this.escapeHtml(project.description)}</span>` : ''}
                    </div>
                    <div class="user-actions">
                        <button class="btn btn-sm btn-secondary" onclick="Admin.editProject('${project.id}', '${this.escapeHtml(project.name)}', '${this.escapeHtml(project.display_name || '')}', '${this.escapeHtml(project.description || '')}')">编辑</button>
                        <button class="btn btn-sm btn-danger" onclick="Admin.deleteProject('${project.id}', '${this.escapeHtml(project.display_name || project.name)}')">删除</button>
                    </div>
                </div>
            `).join('');
        } catch (err) {
            container.innerHTML = '<p class="error">加载项目失败</p>';
            console.error(err);
        }
    },

    async editProject(projectId, name, displayName, description) {
        const newName = prompt('项目名称 (英文):', name);
        if (newName === null) return;
        const newDisplayName = prompt('显示名称:', displayName);
        if (newDisplayName === null) return;
        const newDescription = prompt('描述:', description);
        if (newDescription === null) return;

        try {
            const response = await fetch(`/api/projects/${projectId}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer ' + Auth.getToken(),
                },
                body: JSON.stringify({
                    name: newName,
                    display_name: newDisplayName || null,
                    description: newDescription || null,
                }),
            });

            if (!response.ok) {
                const error = await response.json().catch(() => ({}));
                throw new Error(error.detail || '编辑项目失败');
            }

            this.loadProjects();
        } catch (err) {
            alert(err.message);
        }
    },

    async deleteProject(projectId, projectName) {
        if (!confirm(`确定要删除项目 "${projectName}" 吗？\n注意：如果项目下有技能，将无法删除。`)) return;

        try {
            const response = await fetch(`/api/projects/${projectId}`, {
                method: 'DELETE',
                headers: { 'Authorization': 'Bearer ' + Auth.getToken() },
            });

            if (!response.ok) {
                const error = await response.json().catch(() => ({}));
                throw new Error(error.detail || '删除项目失败');
            }

            this.loadProjects();
        } catch (err) {
            alert(err.message);
        }
    },

    // ========== Marketplace Sources ==========

    async loadMarketplaces() {
        const container = document.getElementById('marketplaces-list');
        if (!container) return;

        try {
            const response = await fetch('/api/marketplaces', {
                headers: { 'Authorization': 'Bearer ' + Auth.getToken() },
            });

            if (!response.ok) throw new Error('加载源列表失败');

            const sources = await response.json();

            if (sources.length === 0) {
                container.innerHTML = '<p class="empty">暂无 Marketplace 源</p>';
                return;
            }

            container.innerHTML = sources.map(source => {
                const lastSync = source.last_synced_at ? new Date(source.last_synced_at).toLocaleString() : '从未同步';
                const status = source.last_error
                    ? `<span class="role-badge" style="background:#fde8e8;color:#c81e1e">失败</span>`
                    : '';
                return `
                <div class="user-card">
                    <div class="user-info">
                        <strong>${this.escapeHtml(source.name)}</strong>
                        <span class="role-badge">${this.escapeHtml(source.location)}</span>
                        ${source.source_ref ? `<span class="text-muted">ref: ${this.escapeHtml(source.source_ref)}</span>` : ''}
                        <span class="text-muted">已导入 ${source.imported_skill_count} 个 skill · 上次同步: ${lastSync}</span>
                        ${status}
                        ${source.last_error ? `<span class="text-muted">${this.escapeHtml(source.last_error)}</span>` : ''}
                    </div>
                    <div class="user-actions">
                        <button class="btn btn-sm btn-primary" onclick="Admin.syncMarketplace('${source.id}', '${this.escapeHtml(source.name)}')">同步</button>
                        <button class="btn btn-sm btn-danger" onclick="Admin.deleteMarketplace('${source.id}', '${this.escapeHtml(source.name)}', ${source.imported_skill_count})">删除</button>
                    </div>
                </div>`;
            }).join('');
        } catch (err) {
            container.innerHTML = '<p class="error">加载源列表失败</p>';
            console.error(err);
        }
    },

    async syncMarketplace(sourceId, sourceName) {
        if (!confirm(`立即同步源 "${sourceName}" 吗？\n已本地修改的 skill 不会被覆盖。`)) return;

        try {
            const response = await fetch(`/api/marketplaces/${sourceId}/sync`, {
                method: 'POST',
                headers: { 'Authorization': 'Bearer ' + Auth.getToken() },
            });

            const report = await response.json().catch(() => ({}));
            if (!response.ok) {
                throw new Error(report.detail || '同步失败');
            }

            const lines = [
                `新增: ${(report.added || []).length}`,
                `更新: ${(report.updated || []).length}`,
                `未变化: ${(report.unchanged || []).length}`,
                `上游已移除: ${(report.missing || []).length}`,
                `跳过(名称冲突): ${(report.skipped_conflicts || []).length}`,
                `跳过(本地已修改): ${(report.skipped_local_edits || []).length}`,
            ];
            if ((report.warnings || []).length) lines.push(`警告: ${report.warnings.join('; ')}`);
            if ((report.errors || []).length) lines.push(`错误: ${report.errors.join('; ')}`);
            alert(`同步完成\n${lines.join('\n')}`);

            this.loadMarketplaces();
        } catch (err) {
            alert(err.message);
        }
    },

    async deleteMarketplace(sourceId, sourceName, importedCount) {
        if (!confirm(`确定要删除源 "${sourceName}" 吗？\n将同时删除它导入的 ${importedCount} 个 skill。`)) return;

        try {
            const response = await fetch(`/api/marketplaces/${sourceId}`, {
                method: 'DELETE',
                headers: { 'Authorization': 'Bearer ' + Auth.getToken() },
            });

            if (!response.ok) {
                const error = await response.json().catch(() => ({}));
                throw new Error(error.detail || '删除源失败');
            }

            this.loadMarketplaces();
        } catch (err) {
            alert(err.message);
        }
    },
};
