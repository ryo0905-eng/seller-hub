(function () {
    if (typeof Chart === "undefined") {
        return;
    }

    const readJson = function (id) {
        const element = document.getElementById(id);
        return element ? JSON.parse(element.textContent) : [];
    };

    const yenTick = function (value) {
        return Number(value).toLocaleString("ja-JP") + "円";
    };

    const colors = {
        yellow: "#f5b301",
        green: "#11845b",
        red: "#d92d20",
        blue: "#2563eb",
        gray: "#94a3b8",
        teal: "#0f766e",
    };

    const monthlyLabels = readJson("monthly-profit-labels");
    const monthlyValues = readJson("monthly-profit-values");
    const categoryLabels = readJson("category-profit-labels");
    const categoryValues = readJson("category-profit-values");
    const statusLabels = readJson("status-count-labels");
    const statusValues = readJson("status-count-values");

    const monthlyCanvas = document.getElementById("monthlyProfitChart");
    if (monthlyCanvas && monthlyLabels.length) {
        new Chart(monthlyCanvas, {
            type: "bar",
            data: {
                labels: monthlyLabels,
                datasets: [{
                    label: "実利益",
                    data: monthlyValues,
                    backgroundColor: monthlyValues.map(function (value) {
                        return value < 0 ? "rgba(217, 45, 32, 0.78)" : "rgba(17, 132, 91, 0.78)";
                    }),
                    borderRadius: 8,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: function (context) {
                                return yenTick(context.parsed.y);
                            },
                        },
                    },
                },
                scales: {
                    y: {
                        ticks: { callback: yenTick },
                        grid: { color: "rgba(148, 163, 184, 0.2)" },
                    },
                    x: {
                        grid: { display: false },
                    },
                },
            },
        });
    }

    const categoryCanvas = document.getElementById("categoryProfitChart");
    if (categoryCanvas && categoryLabels.length) {
        new Chart(categoryCanvas, {
            type: "bar",
            data: {
                labels: categoryLabels,
                datasets: [{
                    label: "実利益",
                    data: categoryValues,
                    backgroundColor: categoryValues.map(function (value) {
                        return value < 0 ? "rgba(217, 45, 32, 0.72)" : "rgba(245, 179, 1, 0.82)";
                    }),
                    borderRadius: 8,
                }],
            },
            options: {
                indexAxis: "y",
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: function (context) {
                                return yenTick(context.parsed.x);
                            },
                        },
                    },
                },
                scales: {
                    x: {
                        ticks: { callback: yenTick },
                        grid: { color: "rgba(148, 163, 184, 0.2)" },
                    },
                    y: {
                        grid: { display: false },
                    },
                },
            },
        });
    }

    const statusCanvas = document.getElementById("statusCountChart");
    if (statusCanvas) {
        new Chart(statusCanvas, {
            type: "doughnut",
            data: {
                labels: statusLabels,
                datasets: [{
                    data: statusValues,
                    backgroundColor: [colors.gray, colors.blue, colors.teal, colors.yellow],
                    borderColor: "#ffffff",
                    borderWidth: 3,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: "bottom",
                        labels: { usePointStyle: true, boxWidth: 8 },
                    },
                },
                cutout: "62%",
            },
        });
    }
})();
