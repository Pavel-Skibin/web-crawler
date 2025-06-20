// Create Job Form JavaScript

document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('createJobForm');
    const urlInput = document.getElementById('start_url');
    const submitBtn = form.querySelector('button[type="submit"]');

    // URL validation
    urlInput.addEventListener('blur', function() {
        const url = this.value;
        if (url && !url.match(/^https?:\/\/.+/)) {
            this.setCustomValidity('URL должен начинаться с http:// или https://');
            this.classList.add('is-invalid');
        } else {
            this.setCustomValidity('');
            this.classList.remove('is-invalid');
            if (url) {
                this.classList.add('is-valid');
            }
        }
    });

    // Form submission handling
    form.addEventListener('submit', function(e) {
        // Show loading state
        if (submitBtn) {
            Utils.showButtonLoading(submitBtn, 'Создание...');
        }

        // Basic validation
        if (!form.checkValidity()) {
            e.preventDefault();
            e.stopPropagation();
            Utils.hideButtonLoading(submitBtn);
        }

        form.classList.add('was-validated');
    });

    // Real-time validation feedback
    const inputs = form.querySelectorAll('input[required]');
    inputs.forEach(input => {
        input.addEventListener('input', function() {
            if (this.checkValidity()) {
                this.classList.remove('is-invalid');
                this.classList.add('is-valid');
            } else {
                this.classList.remove('is-valid');
                this.classList.add('is-invalid');
            }
        });
    });
});