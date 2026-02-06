// Hourly Crowd Chart
window.hourlyChart = new Chart(document.getElementById("hourlyChart"), {
  type: "line",
  data: {
    labels: ["9AM","10AM","11AM","12PM","1PM","2PM"],
    datasets: [{
      label: "People Count",
      data: [120, 180, 260, 320, 290, 210],
      borderWidth: 3,
      tension: 0.4
    }]
  },
  options: {
    responsive: true,
    plugins: { legend: { display: false } }
  }
});

// Zone-wise Chart
window.zoneChart = new Chart(document.getElementById("zoneChart"), {
  type: "bar",
  data: {
    labels: ["Zone A","Zone B","Zone C","Zone D"],
    datasets: [{
      label: "Avg Crowd",
      data: [220, 300, 140, 90]
    }]
  },
  options: {
    responsive: true,
    plugins: { legend: { display: false } }
  }
});
