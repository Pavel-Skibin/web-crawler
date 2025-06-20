// Dashboard JavaScript

class DashboardProgressTracker {
    constructor() {
        this.activeJobs = new Set();
        this.updateInterval = null;
        this.elements = this.getElements();
        this.init();
    }

    getElements() {
        return {
            activeJobsAlert: document.getElementById('active-jobs-alert'),
            activeJobsText: document.getElementById('active-jobs-text'),
            runningJobsCount: document.getElementById('running-jobs')
        };
    }

    init() {
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
        if (this.elements.activeJobsAlert && this.elements.activeJobsText) {
            const count = this.activeJobs.size;
            this.elements.activeJobsText.textContent = `У вас ${count} активных заданий. Прогресс обновляется автоматически.`;
            this.elements.activeJobsAlert.classList.remove('d-none');
        }
    }

    hideActiveJobsAlert() {
        if (this.elements.activeJobsAlert) {
            this.elements.activeJobsAlert.classList.add('d-none');
        }
    }

    startTracking() {
        this.updateProgress();
        this.updateInterval = setInterval(() => this.updateProgress(), 5000);
    }

    stopTracking() {
        if (this.updateInterval) {
            clearInterval(this.updateInterval);
            this.updateInterval = null;
        }
        this.hideActiveJobsAlert();
    }

    updateProgress() {
        this.activeJobs.forEach(jobId => {
            fetch(`/api/job/${jobId}/progress`)
                .then(response => response.json())
                .then(data => {
                    if (data.active) {
                        this.updateJobRow(jobId, data);
                    } else {
                        this.activeJobs.delete(jobId);
                        if (this.activeJobs.size === 0) {
                            this.stopTracking();
                            location.reload();
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

        const progressBar = document.getElementById(`progress-${jobId}`);
        if (progressBar) {
            const progress = Math.min(100, Math.max(0, data.progress || 0));
            progressBar.style.width = progress + '%';
            progressBar.innerHTML = `<small>${progress}%</small>`;
        }

        if (this.elements.runningJobsCount) {
            this.elements.runningJobsCount.textContent = this.activeJobs.size;
        }
    }
}

// Dashboard namespace
const Dashboard = {
    tracker: null,

    init() {
        this.tracker = new DashboardProgressTracker();
        this.initDeleteForm();
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
    }
};

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    Dashboard.init();
});

// Export for global access
window.Dashboard = Dashboard;