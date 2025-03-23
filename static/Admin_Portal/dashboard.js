// Monthly Appointments Chart
const months = JSON.parse('{{ monthly_appointments|map(attribute="month")|list|tojson|safe }}');
const appointmentCounts = JSON.parse('{{ monthly_appointments|map(attribute="count")|list|tojson|safe }}');

new Chart(document.getElementById('appointmentsChart'), {
    type: 'line',
    data: {
        labels: months,
        datasets: [{
            label: 'Monthly Appointments',
            data: appointmentCounts,
            backgroundColor: 'rgba(52, 152, 219, 0.2)',
            borderColor: 'rgba(52, 152, 219, 1)',
            borderWidth: 2,
            tension: 0.4
        }]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false
    }
});

// User Type Distribution Chart
const userTypes = JSON.parse('{{ user_type_distribution|map(attribute="user_type")|list|tojson|safe }}');
const userCounts = JSON.parse('{{ user_type_distribution|map(attribute="count")|list|tojson|safe }}');

new Chart(document.getElementById('userDistributionChart'), {
    type: 'doughnut',
    data: {
        labels: userTypes,
        datasets: [{
            data: userCounts,
            backgroundColor: [
                'rgba(52, 152, 219, 0.7)',
                'rgba(46, 204, 113, 0.7)',
                'rgba(155, 89, 182, 0.7)',
                'rgba(230, 126, 34, 0.7)'
            ],
            borderWidth: 1
        }]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false
    }
});

// Appointment Status Chart
const statusTypes = JSON.parse('{{ appointment_status_stats|map(attribute="status")|list|tojson|safe }}');
const statusCounts = JSON.parse('{{ appointment_status_stats|map(attribute="count")|list|tojson|safe }}');

new Chart(document.getElementById('appointmentStatusChart'), {
    type: 'pie',
    data: {
        labels: statusTypes,
        datasets: [{
            data: statusCounts,
            backgroundColor: [
                'rgba(46, 204, 113, 0.7)',
                'rgba(52, 152, 219, 0.7)',
                'rgba(241, 196, 15, 0.7)',
                'rgba(231, 76, 60, 0.7)',
                'rgba(155, 89, 182, 0.7)'
            ],
            borderWidth: 1
        }]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false
    }
});