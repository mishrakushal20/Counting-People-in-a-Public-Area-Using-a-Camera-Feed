function getHeatColor(value) {

    if (value >= 8) {
        return "#f44336";   // 🔴 Red – High crowd
    }
    else if (value >= 5) {
        return "#ff9800";   // 🟠 Orange – Medium crowd
    }
    else if (value >= 3) {
        return "#ffeb3b";   // 🟡 Yellow – Low–Medium crowd
    }
    else {
        return "#4caf50";   // 🟢 Green – Low crowd
    }
}

function loadHeatmap() {
    fetch("/heatmap_data")
        .then(res => res.json())
        .then(data => {
            const grid = document.getElementById("heatmapGrid");
            grid.innerHTML = "";

            data.zones.forEach(value => {
                const cell = document.createElement("div");
                cell.className = "cell";
                cell.style.backgroundColor = getHeatColor(value);
                cell.innerText = ""; // ❌ No numbers
                grid.appendChild(cell);
            });
        });
}

loadHeatmap();
setInterval(loadHeatmap, 2000); // update every 2 sec

