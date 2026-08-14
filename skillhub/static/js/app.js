/**
 * SkillHub Web UI Application
 */
(function() {
    'use strict';

    var searchInput = document.getElementById('search-input');
    var searchBtn = document.getElementById('search-btn');
    var categoryFilter = document.getElementById('category-filter');
    var sortFilter = document.getElementById('sort-filter');
    var projectFilter = document.getElementById('project-filter');
    var skillList = document.getElementById('skill-list');
    var modal = document.getElementById('skill-modal');
    var skillDetail = document.getElementById('skill-detail');
    var modalClose = document.querySelector('.modal-close');

    var allSkills = [];
    var categories = new Set();

    function applyI18n() {
        // Static HTML elements (with null checks for pages that may not have them)
        var el;
        if ((el = document.getElementById('page-title'))) el.textContent = t('app.title');
        if ((el = document.getElementById('tagline'))) el.textContent = t('app.tagline');
        if ((el = document.getElementById('footer-text'))) el.textContent = t('app.footer');
        if (searchInput) searchInput.placeholder = t('search.placeholder');
        if (searchBtn) searchBtn.textContent = t('search.btn');

        // Filter options
        var catOptions = categoryFilter.querySelectorAll('option');
        if (catOptions.length > 0) catOptions[0].textContent = t('filter.all_categories');

        var sortOptions = sortFilter.options;
        sortOptions[0].textContent = t('filter.sort_downloads');
        sortOptions[1].textContent = t('filter.sort_updated');
        sortOptions[2].textContent = t('filter.sort_created');
        sortOptions[3].textContent = t('filter.sort_name');
    }

    // Make loadSkills available globally for Admin to call
    window.loadSkills = async function(query, category, sort) {
        skillList.innerHTML = '<div class="loading">' + t('loading.skills') + '</div>';

        try {
            var project = projectFilter ? projectFilter.value : '';
            allSkills = await API.listSkills({ query, category, sort, project: project || undefined });
            categories = new Set(allSkills.map(s => s.category).filter(Boolean));
            updateCategoryFilter();
            renderSkills(allSkills);
        } catch (err) {
            skillList.innerHTML = '<div class="empty">' + t('error.server') + '</div>';
            console.error('Failed to load skills:', err);
        }
    };

    function updateCategoryFilter() {
        var current = categoryFilter.value;
        categoryFilter.innerHTML = '<option value="">' + t('filter.all_categories') + '</option>';

        Array.from(categories).sort().forEach(function(cat) {
            var option = document.createElement('option');
            option.value = cat;
            option.textContent = cat;
            if (cat === current) option.selected = true;
            categoryFilter.appendChild(option);
        });
    }

    function renderSkills(skills) {
        if (skills.length === 0) {
            skillList.innerHTML = '<div class="empty">' + t('empty.skills') + '</div>';
            return;
        }

        skillList.innerHTML = skills.map(function(skill) {
            return '<div class="skill-card" data-id="' + skill.id + '">' +
                '<h3>' + escapeHtml(skill.display_name || skill.name) + '</h3>' +
                '<p class="description">' + escapeHtml(skill.description || t('skill.no_description')) + '</p>' +
                '<div class="meta">' +
                    (skill.category ? '<span class="category">' + escapeHtml(skill.category) + '</span>' : '') +
                    (skill.project ? '<span class="tag project-tag">' + escapeHtml(skill.project) + '</span>' : '') +
                    (skill.tags || []).map(function(tag) { return '<span class="tag">' + escapeHtml(tag) + '</span>'; }).join('') +
                '</div>' +
            '</div>';
        }).join('');

        document.querySelectorAll('.skill-card').forEach(function(card) {
            card.addEventListener('click', function() { showSkillDetail(card.dataset.id); });
        });
    }

    async function showSkillDetail(skillId) {
        try {
            var skill = await API.getSkill(skillId);

            // Fetch SKILL.md content
            var skillMdContent = '';
            try {
                var mdResponse = await fetch('/api/skills/' + skillId + '/files/SKILL.md');
                if (mdResponse.ok) {
                    skillMdContent = await mdResponse.text();
                }
            } catch (e) {
                // SKILL.md not available
            }

            var filesHtml = '';
            if (skill.files && skill.files.length > 0) {
                filesHtml = '<div class="file-list">' +
                    '<h4>' + t('skill.detail.files') + ' (' + skill.files.length + ')</h4>' +
                    '<ul>' +
                        skill.files.map(function(f) { return '<li>' + escapeHtml(f.filename) + '</li>'; }).join('') +
                    '</ul>' +
                '</div>';
            }

            var mdHtml = '';
            if (skillMdContent) {
                mdHtml = '<div class="skill-content collapsed">' +
                    '<button class="collapse-toggle" onclick="this.parentElement.classList.toggle(\'collapsed\')">' +
                        '<span class="collapse-icon">▼</span> ' + t('skill.detail.skill_md') +
                    '</button>' +
                    '<div class="collapse-body">' +
                        '<pre><code>' + escapeHtml(skillMdContent) + '</code></pre>' +
                    '</div>' +
                '</div>';
            }

            var authorHtml = skill.author ?
                '<dt>' + t('skill.detail.author') + '</dt><dd>' + escapeHtml(skill.author) + '</dd>' : '';
            var categoryHtml = skill.category ?
                '<dt>' + t('skill.detail.category') + '</dt><dd>' + escapeHtml(skill.category) + '</dd>' : '';
            var projectHtml = skill.project ?
                '<dt>Project</dt><dd>' + escapeHtml(skill.project) + '</dd>' : '';
            var licenseHtml = skill.license ?
                '<dt>' + t('skill.detail.license') + '</dt><dd>' + escapeHtml(skill.license) + '</dd>' : '';
            var tagsHtml = (skill.tags || []).length > 0 ?
                '<dt>' + t('skill.detail.tags') + '</dt><dd>' + skill.tags.map(function(t) { return escapeHtml(t); }).join(', ') + '</dd>' : '';

            // Show delete button only if authenticated
            var deleteHtml = '';
            if (Auth.isLoggedIn()) {
                deleteHtml = '<div class="delete-section">' +
                    '<button class="btn btn-danger btn-sm delete-skill-btn">' + t('skill.detail.delete') + '</button>' +
                '</div>';
            }

            skillDetail.innerHTML =
                '<h2>' + escapeHtml(skill.display_name || skill.name) + '</h2>' +
                '<p class="description">' + escapeHtml(skill.description || t('skill.no_description_available')) + '</p>' +
                '<dl class="metadata">' +
                    '<dt>' + t('skill.detail.name') + '</dt><dd>' + escapeHtml(skill.name) + '</dd>' +
                    authorHtml + categoryHtml + projectHtml + licenseHtml + tagsHtml +
                    '<dt>' + t('skill.detail.updated') + '</dt><dd>' + formatDate(skill.updated_at) + '</dd>' +
                '</dl>' +
                filesHtml + mdHtml +
                '<div class="install-command">' +
                    '<code>skillhub install ' + escapeHtml(skill.name) + '</code>' +
                    '<button class="copy-btn" onclick="copyInstallCommand(\'' + escapeHtml(skill.name) + '\')">' + t('skill.detail.copy') + '</button>' +
                '</div>' +
                deleteHtml;

            modal.classList.remove('hidden');

            var deleteBtn = skillDetail.querySelector('.delete-skill-btn');
            if (deleteBtn) {
                deleteBtn.addEventListener('click', function() {
                    window.confirmDeleteSkill(skill.id, skill.display_name || skill.name);
                });
            }
        } catch (err) {
            console.error('Failed to load skill detail:', err);
        }
    }

    window.copyInstallCommand = function(name) {
        var cmd = 'skillhub install ' + name;
        navigator.clipboard.writeText(cmd).then(function() {
            var btn = document.querySelector('.copy-btn');
            if (btn) {
                btn.textContent = t('skill.detail.copied');
                setTimeout(function() { btn.textContent = t('skill.detail.copy'); }, 2000);
            }
        });
    };

    window.confirmDeleteSkill = async function(skillId, skillName) {
        var message = t('skill.detail.delete_confirm') + '\n\n' + skillName;
        if (!confirm(message)) return;

        try {
            await API.deleteSkill(skillId);
            modal.classList.add('hidden');
            performSearch();
        } catch (err) {
            console.error('Failed to delete skill:', err);
            alert(t('skill.detail.delete_error'));
        }
    };

    function setupEventListeners() {
        searchBtn.addEventListener('click', performSearch);
        searchInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') performSearch();
        });

        categoryFilter.addEventListener('change', performSearch);
        sortFilter.addEventListener('change', performSearch);

        if (projectFilter) {
            projectFilter.addEventListener('change', performSearch);
        }

        modalClose.addEventListener('click', function() { modal.classList.add('hidden'); });
        modal.addEventListener('click', function(e) {
            if (e.target === modal) modal.classList.add('hidden');
        });

        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') modal.classList.add('hidden');
        });
    }

    function performSearch() {
        var query = searchInput.value.trim();
        var category = categoryFilter.value;
        var sort = sortFilter.value;
        window.loadSkills(query || undefined, category || undefined, sort);
    }

    function escapeHtml(str) {
        if (!str) return '';
        var div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    function formatDate(isoString) {
        if (!isoString) return '';
        return isoString.slice(0, 10);
    }

    async function init() {
        await window.loadSkills();
        setupEventListeners();

        // Wait for translations to load before applying them
        document.addEventListener('i18n:ready', function() {
            applyI18n();
            window.loadSkills();
        });

        // If translations are already loaded, apply immediately
        if (getLocale() && window.t('app.title') !== 'app.title') {
            applyI18n();
        }
    }

    init();
})();
