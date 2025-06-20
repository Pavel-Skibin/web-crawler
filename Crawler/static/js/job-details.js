// Job Details JavaScript

class JobProgressTracker {
    constructor(jobId, isJobActive) {
        this.jobId = jobId;
        this.isJobActive = isJobActive;
        this.progressInterval = null;
        this.timeInterval = null;
        this.startTime = null;
        this.elements = this.getElements();

        if (this.isJobActive) {
            this.startTracking();
        }
    }

    getElements() {
        return {
            progressCard: document.getElementById('progress-card'),
            progressBar: document.getElementById('progress-bar'),
            progressText: document.getElementById('progress-text'),
            progressPercentage: document.getElementById('progress-percentage'),
            progressSpinner: document.getElementById('progress-spinner'),
            progressTitle: document.getElementById('progress-title'),
            currentStatus: document.getElementById('current-status'),
            currentUrl: document.getElementById('current-url'),
            pagesProcessed: document.getElementById('pages-processed'),
            totalPages: document.getElementById('total-pages'),
            lastUpdate: document.getElementById('last-update'),
            progressMessage: document.getElementById('progress-message'),
            executionTime: document.getElementById('execution-time'),
            jobStatus: document.getElementById('job-status'),
            totalCrawled: document.getElementById('total-crawled'),
            pagesCount: document.getElementById('pages-count'),
            statusAlert: document.getElementById('status-alert'),
            noPagesMessage: document.getElementById('no-pages-message')
        };
    }

    startTracking() {
        this.startTime = new Date();
        this.updateProgress();
        this.progressInterval = setInterval(() => this.updateProgress(), 2000);
        this.timeInterval = setInterval(() => this.updateExecutionTime(), 1000);
    }

    stopTracking() {
        if (this.progressInterval) {
            clearInterval(this.progressInterval);
            this.progressInterval = null;
        }
        if (this.timeInterval) {
            clearInterval(this.timeInterval);
            this.timeInterval = null;
        }
    }

    updateExecutionTime() {
        if (this.startTime && this.elements.executionTime) {
            const now = new Date();
            const diff = now - this.startTime;
            const hours = Math.floor(diff / 3600000);
            const minutes = Math.floor((diff % 3600000) / 60000);
            const seconds = Math.floor((diff % 60000) / 1000);

            const timeString = `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
            this.elements.executionTime.textContent = timeString;
        }
    }

    updateProgress() {
        fetch(`/api/job/${this.jobId}/progress`)
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    console.error('Ошибка получения прогресса:', data.error);
                    this.handleError('Ошибка получения прогресса: ' + data.error);
                    return;
                }

                if (data.active) {
                    this.updateActiveJob(data);
                } else {
                    this.updateInactiveJob(data);
                }
            })
            .catch(error => {
                console.error('Ошибка запроса прогресса:', error);
                this.handleError('Ошибка соединения с сервером');
            });
    }

    updateActiveJob(data) {
        if (this.elements.progressCard) {
            this.elements.progressCard.classList.remove('d-none');
            this.elements.progressCard.className = `card progress-card mb-4 ${data.status || 'running'}`;
        }

        const progress = Math.min(100, Math.max(0, data.progress || 0));
        if (this.elements.progressBar) {
            this.elements.progressBar.style.width = progress + '%';
            this.elements.progressBar.setAttribute('aria-valuenow', progress);
        }
        if (this.elements.progressText) {
            this.elements.progressText.textContent = progress + '%';
        }
        if (this.elements.progressPercentage) {
            this.elements.progressPercentage.textContent = progress + '%';
        }

        if (this.elements.currentStatus) {
            this.elements.currentStatus.textContent = this.getStatusText(data.status);
            this.elements.currentStatus.className = `badge ${this.getStatusBadgeClass(data.status)}`;
        }

        this.updateElements(data);

        if (data.status === 'completed' || data.status === 'failed') {
            this.handleCompletion(data.status);
        }
    }

    updateInactiveJob(data) {
        if (this.elements.progressCard) {
            this.elements.progressCard.classList.add('d-none');
        }

        if (this.isJobActive) {
            location.reload();
        }
    }

    updateElements(data) {
        const updates = {
            currentUrl: data.current_url || 'Не указано',
            pagesProcessed: data.pages_processed || 0,
            totalPages: data.total_pages || 0,
            lastUpdate: data.updated_at || 'Только что',
            progressMessage: data.message || 'Выполнение задания...'
        };

        Object.entries(updates).forEach(([key, value]) => {
            if (this.elements[key]) {
                this.elements[key].textContent = value;
            }
        });

        if (this.elements.jobStatus) {
            this.elements.jobStatus.textContent = data.status || 'running';
            this.elements.jobStatus.className = `badge ${this.getStatusBadgeClass(data.status)}`;
        }

        if (this.elements.statusAlert) {
            this.elements.statusAlert.className = `alert ${this.getAlertClass(data.status)} mb-0`;
        }
    }

    handleCompletion(status) {
        this.stopTracking();

        if (this.elements.progressSpinner) {
            this.elements.progressSpinner.style.display = 'none';
        }
        if (this.elements.progressTitle) {
            this.elements.progressTitle.textContent = status === 'completed' ?
                'Задание завершено успешно' : 'Задание завершено с ошибкой';
        }

        this.showCompletionNotification(status === 'completed');

        setTimeout(() => {
            location.reload();
        }, 3000);
    }

    handleError(message) {
        if (this.elements.progressMessage) {
            this.elements.progressMessage.textContent = message;
        }
        if (this.elements.statusAlert) {
            this.elements.statusAlert.className = 'alert alert-danger mb-0';
        }
    }

    showCompletionNotification(isSuccess) {
        const notification = document.createElement('div');
        notification.className = `alert alert-${isSuccess ? 'success' : 'danger'} alert-dismissible fade show position-fixed`;
        notification.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
        notification.innerHTML = `
            <i class="bi bi-${isSuccess ? 'check-circle' : 'exclamation-triangle'} me-2"></i>
            <strong>Задание ${isSuccess ? 'завершено успешно' : 'завершено с ошибкой'}!</strong>
            <br><small>Страница обновится через несколько секунд...</small>
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;

        document.body.appendChild(notification);

        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 5000);
    }

    getStatusText(status) {
        const statusMap = {
            'starting': 'Запуск',
            'running': 'Выполняется',
            'processing': 'Обработка',
            'completed': 'Завершено',
            'failed': 'Ошибка'
        };
        return statusMap[status] || status || 'Неизвестно';
    }

    getStatusBadgeClass(status) {
        const classMap = {
            'starting': 'bg-info',
            'running': 'bg-warning',
            'processing': 'bg-primary',
            'completed': 'bg-success',
            'failed': 'bg-danger'
        };
        return classMap[status] || 'bg-secondary';
    }

    getAlertClass(status) {
        const classMap = {
            'starting': 'alert-info',
            'running': 'alert-warning',
            'processing': 'alert-primary',
            'completed': 'alert-success',
            'failed': 'alert-danger'
        };
        return classMap[status] || 'alert-info';
    }
}

// Job Details namespace
const JobDetails = {
    tracker: null,

    init(jobId, isJobActive) {
        this.tracker = new JobProgressTracker(jobId, isJobActive);
        this.initDeleteForm();
        this.initExportButtons();
    },

    initDeleteForm() {
        const deleteForm = document.getElementById('deleteJobForm');
        if (deleteForm) {
            deleteForm.addEventListener('submit', function(e) {
                const submitBtn = this.querySelector('button[type="submit"]');
                if (submitBtn) {
                    Utils.showButtonLoading(submitBtn, 'Удаление...');
                }
            });
        }
    },

    initExportButtons() {
        const exportButtons = document.querySelectorAll('a[href*="export"]');
        exportButtons.forEach(button => {
            button.addEventListener('click', function() {
                const icon = this.querySelector('i');
                if (icon) {
                    const originalClass = icon.className;
                    icon.className = 'bi bi-arrow-down-circle-fill me-1';

                    setTimeout(() => {
                        icon.className = originalClass;
                    }, 2000);
                }
            });
        });
    },

    confirmDelete(jobId, jobName) {
        const modal = document.getElementById('deleteConfirmModal');
        const jobNameElement = document.getElementById('jobNameToDelete');
        const deleteForm = document.getElementById('deleteJobForm');

        if (jobNameElement) {
            jobNameElement.textContent = jobName;
        }

        if (deleteForm) {
            deleteForm.action = `/job/${jobId}/delete`;
        }

        if (modal) {
            const bootstrapModal = new bootstrap.Modal(modal);
            bootstrapModal.show();
        }
    },

    previewExport() {
        const modal = document.getElementById('exportPreviewModal');
        const content = document.getElementById('export-preview-content');

        if (!modal || !content) return;

        const bootstrapModal = new bootstrap.Modal(modal);
        bootstrapModal.show();

        content.innerHTML = `
            <div class="text-center py-4">
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">Загрузка...</span>
                </div>
                <p class="mt-3 text-muted">Подготовка данных для экспорта...</p>
            </div>
        `;

        const jobId = this.tracker ? this.tracker.jobId : window.jobId;

        fetch(`/job/${jobId}/export/preview`)
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    content.innerHTML = `
                        <div class="alert alert-danger">
                            <i class="bi bi-exclamation-triangle me-2"></i>
                            <strong>Ошибка:</strong> ${data.error}
                        </div>
                    `;
                    return;
                }

                content.innerHTML = this.generatePreviewHTML(data);
            })
            .catch(error => {
                console.error('Ошибка получения превью:', error);
                content.innerHTML = `
                    <div class="alert alert-danger">
                        <i class="bi bi-exclamation-triangle me-2"></i>
                        <strong>Ошибка загрузки данных</strong><br>
                        <small>Попробуйте обновить страницу или обратитесь к администратору</small>
                    </div>
                `;
            });
    },

    generatePreviewHTML(data) {
        return `
            <div class="row mb-4">
                <div class="col-md-6">
                    <div class="card border-primary">
                        <div class="card-header bg-primary text-white">
                            <h6 class="mb-0"><i class="bi bi-info-circle me-2"></i>Информация о задании</h6>
                        </div>
                        <div class="card-body">
                            <ul class="list-unstyled mb-0">
                                <li><strong>Название:</strong> ${data.job_info.name}</li>
                                <li><strong>Статус:</strong> <span class="badge bg-success">${data.job_info.status}</span></li>
                                <li><strong>Создано:</strong> ${new Date(data.job_info.created_at).toLocaleString('ru-RU')}</li>
                            </ul>
                        </div>
                    </div>
                </div>
                <div class="col-md-6">
                    <div class="card border-success">
                        <div class="card-header bg-success text-white">
                            <h6 class="mb-0"><i class="bi bi-bar-chart me-2"></i>Статистика данных</h6>
                        </div>
                        <div class="card-body">
                            <ul class="list-unstyled mb-0">
                                <li><strong>Страниц:</strong> <span class="badge bg-primary">${data.job_info.total_pages}</span></li>
                                <li><strong>Ссылок:</strong> <span class="badge bg-info">${data.job_info.total_links}</span></li>
                                <li><strong>Размер файла:</strong> <span class="badge bg-warning text-dark">~${data.data_size_estimate}</span></li>
                            </ul>
                        </div>
                    </div>
                </div>
            </div>

            ${data.sample_pages && data.sample_pages.length > 0 ? `
            <div class="card">
                <div class="card-header">
                    <h6 class="mb-0"><i class="bi bi-eye me-2"></i>Пример данных (первые 3 страницы)</h6>
                </div>
                <div class="card-body">
                    <div class="table-responsive">
                        <table class="table table-sm table-hover">
                            <thead class="table-dark">
                                <tr>
                                    <th>URL</th>
                                    <th>Заголовок</th>
                                    <th>Статус</th>
                                    <th>Слов</th>
                                    <th>Ссылок</th>
                                    <th>Глубина</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${data.sample_pages.map(page => `
                                    <tr>
                                        <td>
                                            <a href="${page.url}" target="_blank" class="text-decoration-none" title="${page.url}">
                                                <i class="bi bi-box-arrow-up-right me-1"></i>
                                                ${page.url.length > 40 ? page.url.substring(0, 40) + '...' : page.url}
                                            </a>
                                        </td>
                                        <td title="${page.title || ''}">
                                            ${page.title ? (page.title.length > 30 ? page.title.substring(0, 30) + '...' : page.title) : '<span class="text-muted">-</span>'}
                                        </td>
                                        <td>
                                            <span class="badge bg-${page.status_code === 200 ? 'success' : (page.status_code >= 300 && page.status_code < 400) ? 'warning' : 'danger'}">
                                                ${page.status_code}
                                            </span>
                                        </td>
                                        <td>
                                            <span class="badge bg-light text-dark">${page.content?.word_count || 0}</span>
                                        </td>
                                        <td>
                                            <span class="badge bg-light text-dark">${page.links?.length || 0}</span>
                                        </td>
                                        <td>
                                            <span class="badge bg-info">${page.depth}</span>
                                        </td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
            ` : '<div class="alert alert-info"><i class="bi bi-info-circle me-2"></i>Нет данных для предварительного просмотра</div>'}

            <div class="alert alert-light border mt-4">
                <div class="row">
                    <div class="col-md-8">
                        <h6><i class="bi bi-file-earmark-code me-2"></i>Структура JSON файла</h6>
                        <ul class="mb-0 small">
                            <li><strong>export_info</strong> - информация об экспорте (дата, пользователь, версия)</li>
                            <li><strong>job_info</strong> - полная информация о задании и параметрах</li>
                            <li><strong>crawled_data.pages</strong> - все собранные страницы с метаданными</li>
                            <li><strong>crawled_data.links</strong> - граф всех найденных ссылок</li>
                        </ul>
                    </div>
                    <div class="col-md-4 text-center">
                        <i class="bi bi-download display-4 text-success"></i>
                        <p class="small text-muted mt-2">Готов к скачиванию</p>
                    </div>
                </div>
            </div>
        `;
    }
};

// Export for global access
window.JobDetails = JobDetails;