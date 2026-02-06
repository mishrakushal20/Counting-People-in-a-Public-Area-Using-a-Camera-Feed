
# Global System Configuration

SYSTEM_CONFIG = {
    "confidence": 0.5,      # YOLO detection confidence
    "fps": 10,              # Frame skip / processing rate
    "max_people": 1000      # Global max people threshold
}

# Alert Channel Toggles

ALERT_CONFIG = {
    "email": True,
    "sms": False,
    "webhook": False
}

# Runtime Status (Live Data)

RUNTIME_STATUS = {
    "current_count": 0,
    "system_state": "NORMAL",   # NORMAL | WARNING | CRITICAL
    "last_alert_time": {}
}
