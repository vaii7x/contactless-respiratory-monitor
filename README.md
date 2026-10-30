# PhaseBreathe — Contactless Respiratory Monitor

PhaseBreathe measures a person's breathing rate **without touching them**. An ultrasonic distance sensor pointed at the chest picks up the tiny rise and fall of each breath, and a live dashboard shows the breathing rate, the breathing wave and warnings when breathing seems to pause.

> **Disclaimer:** this is an experimental prototype. It is **not a medical device**, has not been clinically validated, and cannot diagnose sleep apnea or any other condition. Low chest movement does not necessarily mean breathing has stopped.

---

## Contents
- [How it works](#how-it-works)
- [Features](#features)
- [Hardware](#hardware)
- [Software stack](#software-stack)
- [Setup and running](#setup-and-running)
- [Signal processing algorithms](#signal-processing-algorithms)
- [Dashboard guide](#dashboard-guide)
- [Architecture](#architecture)
- [API reference](#api-reference)
- [Database](#database)
- [Project structure](#project-structure)
- [Troubleshooting](#troubleshooting)
- [Limitations](#limitations)
- [Future work](#future-work)

---

## How it works

When you breathe in, your chest moves a few millimetres toward the sensor; when you breathe out, it moves away. The HC-SR04 sensor measures the distance to the chest **25 times per second**, so these movements show up as a wave.

```
[Chest] ~~ultrasound~~ [HC-SR04] --> [ESP32] --USB serial--> [Python backend] --WebSocket--> [Web dashboard]
                                                                    |
                                                               [SQLite DB] --> CSV export
```

1. **ESP32 firmware** fires the sensor every 40 ms and sends each distance to the PC over USB (`DIST,19.45`, or `INVALID` when there is no echo).
2. **Python backend** filters the signal, detects each breath, calculates breaths per minute, checks signal quality, detects breathing pauses and records sessions.
3. **React dashboard** shows everything live in the browser and lets you calibrate, record and export.

All data stays on your computer; nothing is sent to the internet.

---

## Features

**Measurement**
- Contactless respiratory rate (breaths per minute), 6–40 br/min
- Breathing classification: *slow* (< 12), *normal* (12–20), *fast* (> 20), based on the typical adult range
- Confidence indicator (±br/min) showing how consistent the last breaths were
- Personal calibration: 10 s of normal breathing tunes breath detection to the person
- Signal quality rating and valid-reading percentage

**Safety alerts**
- Possible apnea detection: no chest movement for 10 s or more
- Flashing red banner plus an audible beep every second during a pause
- Warnings for poor sensor aim, wiring faults and low signal

**Visualisation**
- Live 30-second chest-movement graph
- A dot marks every breath the algorithm counted, so detection can be checked by eye
- Live readouts for rate, distance, signal quality and sample rate

**Recording**
- Start/stop recording sessions to a local SQLite database
- Session summary: average, minimum and maximum rate, number of pauses, % valid readings
- Export all recordings as CSV

---

## Hardware

| Component | Purpose |
|---|---|
| ESP32 Dev Module | Drives the sensor and sends readings to the PC over USB |
| HC-SR04 ultrasonic sensor | Measures distance to the chest (40 kHz ultrasound) |
| 2 × 10 kΩ resistors | Voltage divider to protect the ESP32 from the 5 V ECHO signal |
| Breadboard, jumper wires, USB cable | Connections |

### Wiring

| HC-SR04 | ESP32 |
|---|---|
| VCC | VIN / 5V (when VIN supplies 5 V) |
| TRIG | GPIO 5 |
| ECHO | GPIO 18 **through the voltage divider** |
| GND | GND |

Voltage divider: `ECHO → 10 kΩ → junction → GPIO 18`, and `junction → 10 kΩ → GND`.

> ⚠️ Never connect the 5 V ECHO pin directly to an ESP32 GPIO; it can damage the board.
> The 10k/10k divider gives about 2.5 V, which is only just above the ESP32's logic-high level. A 10 kΩ (top) / 20 kΩ (bottom) divider gives about 3.3 V and is more reliable.

**Sensor placement:** aim the sensor squarely at the chest, keep it still, and avoid loose clothing or blankets between the sensor and the chest.

---

## Software stack

| Part | Technology |
|---|---|
| Firmware | Arduino C++ on ESP32 (Arduino IDE with ESP32 board support) |
| Backend | Python 3.10+, FastAPI, Uvicorn, pyserial, SQLite |
| Frontend | React 18, Vite 6, HTML5 Canvas, Web Audio API, WebSocket |
| Platform | Windows 10/11, Node.js LTS |

---

## Setup and running

**Requirements:** Windows 10/11, Python 3.10+, Node.js LTS, Arduino IDE with ESP32 board support.

1. Clone or download this repository.
2. Open `firmware/phasebreathe_esp32.ino` in Arduino IDE, select **ESP32 Dev Module** and your COM port, and upload.
3. Close the Arduino Serial Monitor and Serial Plotter (they lock the COM port).
4. Double-click **`setup.bat`** once. It creates a Python virtual environment and installs all Python and npm packages.
5. Double-click **`start_backend.bat`** and keep the window open (API on `http://127.0.0.1:8000`).
6. Double-click **`start_dashboard.bat`** in another window and keep it open.
7. Open the URL Vite prints (usually `http://localhost:5173`).
8. Pick the ESP32's COM port and click **Connect**.
9. Click **Calibrate** while the person breathes normally for 10 seconds.
10. Optionally click **Start session** to record.

---

## Signal processing algorithms

Every reading passes through these steps, in order (`backend/main.py`, `process_distance`):

| # | Step | What it does | Parameters |
|---|---|---|---|
| 1 | Ultrasonic ranging (ESP32) | Distance = echo time × 0.0343 cm/µs ÷ 2 | 25 Hz, 15 ms timeout |
| 2 | Range validation | Rejects impossible readings | 2–250 cm |
| 3 | Median filter | Removes single-sample spikes and ghost echoes | 5 samples |
| 4 | Exponential moving average | Smooths sensor noise while keeping fast breaths | α = 0.2 (~0.2 s lag) |
| 5 | Hysteresis peak detection | A peak counts only after the signal turns back by the threshold, so noise can't create false breaths | 0.25 cm default, or calibrated |
| 6 | Breath-cycle validation | Time between peaks = one breath; out-of-range cycles are ignored | 1.5–10 s (6–40 br/min) |
| 7 | Rate averaging | Rate = 60 ÷ cycle time, averaged for stability | last 3 breaths |
| 8 | Confidence | ± half the spread of the last 3 breath rates; red above ±3 | — |
| 9 | Classification | slow / normal / fast label | < 12, 12–20, > 20 br/min |
| 10 | Signal quality | Chest movement range over the last 5 s | < 0.25 cm low, < 1 cm fair, else variable |
| 11 | Stillness tracking | Time since the chest last moved | ≥ 0.15 cm counts as movement |
| 12 | Apnea detection | Flags a possible pause after breathing has been seen; clears the stale rate | ≥ 10 s without movement |
| 13 | Echo reliability | Share of valid readings; warns about aim or wiring | warn below 70% over ~5 s |
| 14 | Personal calibration | Threshold = 40% of the person's breath depth over 10 s | clamped 0.1–1.0 cm |

**Why these choices**
- **Median then EMA:** the median filter removes outliers that an average would smear; the EMA then removes remaining jitter. α = 0.2 at 25 Hz acts as a ~1 Hz low-pass filter, above the fastest breathing (~0.67 Hz) and below most noise.
- **Hysteresis instead of simple local maxima:** small wobbles smaller than the threshold can never be counted as breaths.
- **3-breath average:** responds to changes in breathing speed within a few breaths while still smoothing out irregular single breaths.
- **Calibration:** a fixed threshold misses shallow breathers or people far from the sensor; scaling it to each person's breath depth fixes that.
- **25 Hz sampling:** far above what breathing needs (Nyquist), giving enough samples for filtering.

---

## Dashboard guide

| Area | Shows |
|---|---|
| Header | COM port selector, connection light, Calibrate (with countdown), Connect/Disconnect |
| Respiratory rate | br/min, slow/normal/fast label, ± confidence |
| Distance | Smoothed chest distance and the breath threshold in use |
| Signal | Quality rating and number of pauses this connection |
| Sample rate | Measured Hz, % valid readings, no-echo count |
| Chest distance graph | Last 30 s of the breathing wave with breath markers, plus a status line |
| Apnea banner | Flashing alert with beep during a pause of 10 s or more |
| Recording | Start/stop session |
| Recent sessions | Start/end, samples, average rate (min–max), pauses, valid %; CSV export |

Notes:
- The beep starts working after your first click on the page (browsers block sound before user interaction).
- The banner doesn't flash if your system has *reduce motion* turned on.
- The dashboard reconnects to the backend automatically if it restarts.

---

## Architecture

- A background **reader thread** reads serial lines continuously and runs the full processing pipeline on every sample.
- Shared state is protected by locks because the reader thread and web requests run at the same time.
- A **30-second ring buffer** (750 samples) holds data for the live graph.
- The **WebSocket** sends the current state plus only the new samples every 100 ms; an *epoch* counter tells the browser to clear its graph after a reconnect.
- Recorded readings are written to SQLite in **batches of 25**, so database writes never block the serial reader.
- The serial parser also accepts the older `Distance: 19.45 cm | ...` firmware format.

**Serial protocol (ESP32 → PC, 115200 baud)**

| Line | Meaning |
|---|---|
| `PHASEBREATHE_READY` | Firmware started |
| `DIST,19.45` | Valid distance in cm |
| `INVALID` | No echo, or distance out of range |

---

## API reference

Base URL: `http://127.0.0.1:8000`

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/health` | Health check |
| GET | `/api/ports` | Available serial ports |
| GET | `/api/state` | Current state and 30 s history |
| POST | `/api/connect` | Body `{"port": "COM9", "baudrate": 115200}`; opens the port and starts reading |
| POST | `/api/disconnect` | Closes the port |
| POST | `/api/calibrate` | Starts 10 s personal calibration |
| POST | `/api/session/start` | Starts recording |
| POST | `/api/session/stop` | Stops recording and saves the session summary |
| GET | `/api/sessions` | Last 20 sessions with summary statistics |
| GET | `/api/export.csv` | All recorded readings as CSV |
| WS | `/ws` | Live stream: `{"state": {...}, "new": [...], "reset": bool}` every 100 ms |

---

## Database

SQLite file: `backend/phasebreathe.db` (created automatically; not committed to git).

```
sessions(id, started, ended, samples, apnea_events, valid_pct)
readings(id, session_id, timestamp, distance, rate, status)
```

Average, minimum and maximum rate per session are calculated from `readings`. Older databases are upgraded automatically on start-up.

CSV export columns: `session_id, timestamp_unix, distance_cm, estimated_rate_bpm, status`.

---

## Project structure

```
├── firmware/
│   └── phasebreathe_esp32.ino   ESP32 + HC-SR04 firmware (25 Hz)
├── backend/
│   ├── main.py                  FastAPI server, signal processing, database
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── main.jsx             React dashboard
│       └── style.css
├── setup.bat                    One-time install
├── start_backend.bat            Runs the API
└── start_dashboard.bat          Runs the dashboard
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| *Access denied* on the COM port | Close Arduino Serial Monitor/Plotter and any other serial app, then reconnect from the dashboard |
| Zero samples | Upload the included firmware, close Serial Monitor, reconnect |
| COM port missing | Unplug and replug the ESP32 |
| Missing dependencies | Run `setup.bat` again |
| "Backend not reachable" | Start `start_backend.bat` and keep it open |
| Low % valid / "check the ECHO wiring" | Aim the sensor squarely at the chest; check the voltage divider and ECHO wire |
| Breaths not detected | Click **Calibrate** while breathing normally; move the sensor closer or straighter |
| No beep during an alert | Click anywhere on the page once to allow sound |

---

## Limitations

- Not clinically validated; the rate is a candidate estimate only.
- Body movement, talking, coughing or a moving sensor can create false breaths or hide real ones.
- Ultrasound reflects poorly from angled surfaces, loose clothing and blankets.
- Only 6–40 breaths per minute are measured; very shallow breathing may be missed.
- Calibration assumes normal breathing for the full 10 s.
- The speed of sound is fixed for ~20 °C, so absolute distance shifts slightly with temperature (breath detection uses changes in distance, so it is mostly unaffected).
- Reconnecting the sensor in the middle of a recording undercounts that session's pauses and valid %.
- Single person, single sensor, local Windows use only.

---

## Future work

- Validation against a reference (manual counting, chest belt) with error statistics
- Frequency-based (FFT) rate estimate as a cross-check
- Motion-artefact detection
- Temperature compensation for the speed of sound
- mmWave radar or multiple sensors for robustness
- Wireless (Wi-Fi/Bluetooth) operation and mobile alerts
- Long-term sleep reports
