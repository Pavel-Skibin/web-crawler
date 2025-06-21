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
        this.updateProgress(); // Первый вызов сразу
        this.progressInterval = setInterval(() => this.updateProgress(), 2000);
        // Обновляем время выполнения каждую секунду
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
        // Показываем карточку прогресса
        if (this.elements.progressCard) {
            this.elements.progressCard.style.display = 'block';
            this.elements.progressCard.className = `card progress-card ${data.status || 'running'}`;
        }
        // Обновляем прогресс-бар
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
        // Обновляем статус
        if (this.elements.currentStatus) {
            this.elements.currentStatus.textContent = this.getStatusText(data.status);
            this.elements.currentStatus.className = `badge ${this.getStatusBadgeClass(data.status)}`;
        }
        // Обновляем информацию
        if (this.elements.currentUrl) {
            this.elements.currentUrl.textContent = data.current_url || 'Не указано';
        }
        if (this.elements.pagesProcessed) {
            this.elements.pagesProcessed.textContent = data.pages_processed || 0;
        }
        if (this.elements.totalPages) {
            this.elements.totalPages.textContent = data.total_pages || 0;
        }
        if (this.elements.lastUpdate) {
            this.elements.lastUpdate.textContent = data.updated_at || 'Только что';
        }
        if (this.elements.progressMessage) {
            this.elements.progressMessage.textContent = data.message || 'Выполнение задания...';
        }
        // Обновляем статус задания в основной карточке
        if (this.elements.jobStatus) {
            this.elements.jobStatus.textContent = data.status || 'running';
            this.elements.jobStatus.className = `badge ${this.getStatusBadgeClass(data.status)}`;
        }
        // Обновляем alert
        if (this.elements.statusAlert) {
            this.elements.statusAlert.className = `alert ${this.getAlertClass(data.status)} mb-0`;
        }
        // Если задание завершено, останавливаем обновления и обновляем страницу
        if (data.status === 'completed' || data.status === 'failed') {
            this.stopTracking();
            if (this.elements.progressSpinner) {
                this.elements.progressSpinner.style.display = 'none';
            }
            if (this.elements.progressTitle) {
                this.elements.progressTitle.textContent = data.status === 'completed' ?
                    'Задание завершено успешно' : 'Задание завершено с ошибкой';
            }
            // Показываем уведомление о завершении
            this.showCompletionNotification(data.status === 'completed');
            // Обновляем страницу через 3 секунды для загрузки результатов
            setTimeout(() => {
                location.reload();
            }, 3000);
        }
    }

    updateInactiveJob(data) {
        // Скрываем карточку прогресса
        if (this.elements.progressCard) {
            this.elements.progressCard.style.display = 'none';
        }
        if (this.isJobActive) {
            // Было активно, но теперь нет - обновляем страницу
            location.reload();
        }
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
        // Создаем временное уведомление
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
        // Удаляем уведомление через 5 секунд
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