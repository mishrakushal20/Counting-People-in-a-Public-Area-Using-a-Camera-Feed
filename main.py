import cv2
import numpy as np
import os
import time
import threading
import requests
import logging

from flask import Flask, Response, request, redirect, render_template, jsonify
from ultralytics import YOLO
from deep_sort_realtime.deepsort_tracker import DeepSort
from tracker.trackableobject import TrackableObject
from imutils.video import FPS

import firebase_admin
from firebase_admin import credentials, firestore

# 🔥 NEW: GLOBAL CONFIG
from config import SYSTEM_CONFIG

# =====================================================
# BASIC SETUP
# =====================================================

print("\n>>> SMART CROWD COUNT SYSTEM STARTED <<<\n")

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# =====================================================
# HEATMAP CONFIG
# =====================================================

GRID_COLS = 8
GRID_ROWS = 5

MAX_DENSITY = 10
DECAY = 0.85

HEATMAP_STATE = {
    "zones": [0] * (GRID_COLS * GRID_ROWS)
}

def normalize_density(v):
    return min(v, MAX_DENSITY)

# =====================================================
# GLOBAL STATE
# =====================================================

output_frame = None
stop_processing = False
processing_thread = None

LIVE_DATA = {
    "entered": 0,
    "exited": 0,
    "inside": 0
}

# =====================================================
# FLASK APP
# =====================================================

app = Flask(__name__)

@app.route("/")
def home():
    return redirect("/login")

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")

@app.route("/heatmap")
def heatmap():
    return render_template("heatmap.html")

@app.route("/admin-settings")
def admin_settings():
    return render_template("admin_settings.html")

@app.route("/login")
def login_page():
    return render_template("login.html")

@app.route("/register")
def register():
    return render_template("register.html")

@app.route("/analytics")
def analytics():
    return render_template("analytics.html")



# =====================================================
# ✅ ADMIN SYSTEM SETTINGS API (NEW)
# =====================================================

@app.route("/bridge/system-settings", methods=["GET"])
def bridge_system_settings():
    try:
        r = requests.get("http://127.0.0.1:5005/api/settings/grouped")
        data = r.json()

        for s in data["data"]["detection"]:
            if s["key"] == "detection_confidence_threshold":
                SYSTEM_CONFIG["confidence"] = float(s["value"])
            elif s["key"] == "detection_fps":
                SYSTEM_CONFIG["fps"] = int(s["value"])
            elif s["key"] == "max_people_count":
                SYSTEM_CONFIG["max_people"] = int(s["value"])

        logging.info(f"BRIDGE SYNCED: {SYSTEM_CONFIG}")
        return jsonify(SYSTEM_CONFIG)

    except Exception as e:
        logging.error(f"Bridge error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/system-settings", methods=["POST"])
def update_system_settings():
    data = request.json

    SYSTEM_CONFIG["confidence"] = float(data["confidence"])
    SYSTEM_CONFIG["fps"] = int(data["fps"])
    SYSTEM_CONFIG["max_people"] = int(data["max_people"])

    logging.info(f"System config updated: {SYSTEM_CONFIG}")

    return jsonify({"status": "ok"})

def auto_sync_system_settings(interval=10):
    """
    Periodically sync system settings from admin backend (5005)
    """
    while True:
        try:
            requests.get(
                "http://127.0.0.1:5000/bridge/system-settings",
                timeout=3
            )
        except Exception as e:
            logging.warning(f"Auto-sync failed: {e}")

        time.sleep(interval)


# =====================================================
# LIVE STREAM
# =====================================================

def gen_frames():
    global output_frame
    while True:
        if output_frame is None:
            time.sleep(0.05)
            continue

        ret, buffer = cv2.imencode(".jpg", output_frame)
        if not ret:
            continue

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" +
            buffer.tobytes() + b"\r\n"
        )

@app.route("/processed-video")
def processed_video():
    return Response(
        gen_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )

# =====================================================
# APIs
# =====================================================

@app.route("/live-data")
def live_data():
    return jsonify(LIVE_DATA)

@app.route("/heatmap_data")
def heatmap_data():
    return jsonify({
        "rows": GRID_ROWS,
        "cols": GRID_COLS,
        "max": MAX_DENSITY,
        "zones": HEATMAP_STATE["zones"]
    })

@app.route("/analytics-data")
def analytics_data():
    return jsonify({
        "peak": LIVE_DATA["inside"],     # demo peak
        "average": LIVE_DATA["inside"],  # demo avg
        "alerts": 1 if LIVE_DATA["inside"] > SYSTEM_CONFIG["max_people"] else 0,

        # demo graph data
        "hourly": [5, 12, 18, 30, 42, 38, 25],
        "zones": {
            "Gate A": 15,
            "Hall": 40,
            "Corridor": 22,
            "Exit": 8
        }
    })


# =====================================================
# VIDEO UPLOAD
# =====================================================

@app.route("/upload", methods=["POST"])
def upload_video():
    global stop_processing, output_frame, processing_thread

    file = request.files.get("video")
    if not file:
        return "No video uploaded", 400

    video_path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(video_path)

    stop_processing = True
    time.sleep(1)

    stop_processing = False
    output_frame = None
    LIVE_DATA.update({"entered": 0, "exited": 0, "inside": 0})

    processing_thread = threading.Thread(
        target=people_counter,
        args=(video_path,),
        daemon=True
    )
    processing_thread.start()

    return redirect("/dashboard")

# =====================================================
# PEOPLE COUNTER + HEATMAP LOGIC
# =====================================================

def people_counter(video_path):
    global output_frame, stop_processing, LIVE_DATA, HEATMAP_STATE

    cred = credentials.Certificate(os.path.join(BASE_DIR, "serviceAccountKey.json"))
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    db = firestore.client()

    model = YOLO("yolov8n.pt")

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return

    tracker = DeepSort(max_age=30)
    trackableObjects = {}

    totalUp = 0
    totalDown = 0

    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))

    cell_w = W // GRID_COLS
    cell_h = H // GRID_ROWS

    fps_counter = FPS().start()
    frame_id = 0

    while cap.isOpened() and not stop_processing:
        ret, frame = cap.read()
        if not ret:
            break

        frame_id += 1

        # 🔥 FPS CONTROL (LIVE FROM ADMIN)
        if frame_id % max(1, SYSTEM_CONFIG["fps"]) != 0:
            continue

        # 🔥 CONFIDENCE FROM ADMIN
        results = model(
            frame,
            conf=SYSTEM_CONFIG["confidence"],
            verbose=False
        )[0]

        detections = []

        for box in results.boxes:
            if int(box.cls[0]) == 0:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                detections.append(
                    ([x1, y1, x2 - x1, y2 - y1], box.conf[0], "person")
                )

        tracks = tracker.update_tracks(detections, frame=frame)
        current_inside = 0

        zone_counts = [[0]*GRID_COLS for _ in range(GRID_ROWS)]

        for t in tracks:
            if not t.is_confirmed():
                continue

            l, t1, r, b = map(int, t.to_ltrb())
            cx, cy = (l + r) // 2, (t1 + b) // 2
            current_inside += 1

            col = min(cx // cell_w, GRID_COLS - 1)
            row = min(cy // cell_h, GRID_ROWS - 1)
            zone_counts[row][col] += 1

            to = trackableObjects.get(t.track_id)
            if to is None:
                to = TrackableObject(t.track_id, (cx, cy))
            else:
                direction = cy - np.mean([p[1] for p in to.centroids])
                to.centroids.append((cx, cy))

                if not to.counted:
                    if direction < 0 and cy < H // 2:
                        totalUp += 1
                        to.counted = True
                    elif direction > 0 and cy > H // 2:
                        totalDown += 1
                        to.counted = True

            trackableObjects[t.track_id] = to

            cv2.rectangle(frame, (l, t1), (r, b), (0, 255, 0), 2)
            cv2.putText(frame, f"ID {t.track_id}",
                        (l, t1 - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        (0, 255, 0), 2)

        flat = []
        for r in range(GRID_ROWS):
            for c in range(GRID_COLS):
                flat.append(zone_counts[r][c])

        new_zones = []
        for old, new in zip(HEATMAP_STATE["zones"], flat):
            value = int(old * DECAY + new)
            new_zones.append(normalize_density(value))

        HEATMAP_STATE["zones"] = new_zones

        LIVE_DATA.update({
            "entered": totalUp,
            "exited": totalDown,
            "inside": current_inside
        })

        db.collection("people_counter").document("live").set({
            **LIVE_DATA,
            "last_updated": firestore.SERVER_TIMESTAMP
        })

        output_frame = frame.copy()
        fps_counter.update()

    cap.release()
    fps_counter.stop()
    cv2.destroyAllWindows()

# =====================================================
# MAIN
# =====================================================
if __name__ == "__main__":
    print("🌐 Login:     http://127.0.0.1:5000/login")
    print("🌐 Dashboard: http://127.0.0.1:5000/dashboard")
    print("🌐 Heatmap:   http://127.0.0.1:5000/heatmap")
    print("🌐 Admin:     http://127.0.0.1:5000/admin-settings")

    sync_thread = threading.Thread(
        target=auto_sync_system_settings,
        daemon=True
    )
    sync_thread.start()

    app.run(host="0.0.0.0", port=5000, debug=False)

