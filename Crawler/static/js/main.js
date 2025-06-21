// Обновление времени каждую секунду
function updateTime() {
    const now = new Date();
    const timeString = now.toLocaleString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
    const timeElement = document.getElementById('current-time');
    if (timeElement) {
        timeElement.textContent = timeString;
    }
}

// Запускаем обновление времени
setInterval(updateTime, 1000);
updateTime(); // Вызываем сразу

// Автоматическое скрытие alerts через 5 секунд
document.addEventListener('DOMContentLoaded', function() {
    const alerts = document.querySelectorAll('.alert:not(.alert-danger)');
    alerts.forEach(function(alert) {
        setTimeout(function() {
            const bootstrapAlert = new bootstrap.Alert(alert);
            bootstrapAlert.close();
        }, 5000);
    });
});