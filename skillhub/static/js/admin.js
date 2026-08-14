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
};
