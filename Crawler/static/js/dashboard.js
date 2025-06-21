class DashboardProgressTracker {
    constructor() {
        this.activeJobs = new Set();
        this.updateInterval = null;
        this.init();
    }

    init() {
        // Находим все активные задания
        document.querySelectorAll('tr[data-job-id]').forEach(row => {
            const statusBadge = row.querySelector('.badge');
            if (statusBadge && statusBadge.textContent.trim() === 'running') {
                const jobId = row.getAttribute('data-job-id');
                this.activeJobs.add(parseInt(jobId));
            }
        });
        if (this.activeJobs.size > 0) {
            this.showActiveJobsAlert();
            this.startTracking();
        }
    }

    showActiveJobsAlert() {
        const alert = document.getElementById('active-jobs-alert');
        const text = document.getElementById('active-jobs-text');
        if (alert && text) {
            const count = this.activeJobs.size;
            text.textContent = `У вас ${count} активных заданий. Прогресс обновляется автоматически.`;
            alert.style.display = 'block';
        }
    }

    startTracking() {
        this.updateProgress();
        this.updateInterval = setInterval(() => this.updateProgress(), 5000);
    }

    updateProgress() {
        this.activeJobs.forEach(jobId => {
            fetch(`/api/job/${jobId}/progress`)
                .then(response => response.json())
                .then(data => {
                    if (data.active) {
                        this.updateJobRow(jobId, data);
                    } else {
                        // Задание больше не активно
                        this.activeJobs.delete(jobId);
                        if (this.activeJobs.size === 0) {
                            this.stopTracking();
                            location.reload(); // Обновляем страницу
                        }
                    }
                })
                .catch(error => {
                    console.error(`Ошибка получения прогресса для задания ${jobId}:`, error);
                });
        });
    }

    updateJobRow(jobId, data) {
        const row = document.querySelector(`tr[data-job-id="${jobId}"]`);
        if (!row) return;
        // Обновляем прогресс-бар
        const progressBar = document.getElementById(`progress-${jobId}`);
        if (progressBar) {
            const progress = Math.min(100, Math.max(0, data.progress));
            progressBar.style.width = progress + '%';
            progressBar.innerHTML = `<small>${progress}%</small>`;
        }
        // Обновляем количество активных заданий в статистике
        const runningJobsElement = document.getElementById('running-jobs');
        if (runningJobsElement) {
            runningJobsElement.textContent = this.activeJobs.size;
        }
    }

    stopTracking() {
        if (this.updateInterval) {
            clearInterval(this.updateInterval);
            this.updateInterval = null;
        }
        // Скрываем alert
        const alert = document.getElementById('active-jobs-alert');
        if (alert) {
            alert.style.display = 'none';
        }
    }
}