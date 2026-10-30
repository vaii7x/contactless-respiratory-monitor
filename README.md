# PhaseBreathe — Final Windows Package

## Requirements
Windows 10/11, Python 3.10+, Node.js LTS, Arduino IDE with ESP32 board support.

## Run
1. Extract the ZIP.
2. Open `firmware/phasebreathe_esp32.ino` in Arduino IDE; select ESP32 Dev Module and your COM port; upload.
3. Close Arduino Serial Monitor and Serial Plotter.
4. Double-click `setup.bat` once.
5. Double-click `start_backend.bat` and keep it open.
6. Double-click `start_dashboard.bat` in another window and keep it open.
7. Open the local URL printed by Vite (usually http://localhost:5173), choose COM9 or the detected ESP32 port, and click Connect device.

## Wiring
HC-SR04 VCC -> ESP32 VIN/5V (if VIN supplies 5V); TRIG -> GPIO 5; ECHO -> GPIO 18 through voltage divider; GND -> GND.
Two 10kΩ resistors: ECHO -> 10kΩ -> junction -> GPIO18; junction -> 10kΩ -> GND. Never connect 5V ECHO directly to ESP32 GPIO.

## Fixes
- Access denied: close Arduino Serial Monitor/Plotter and any other serial application. Then disconnect/reconnect from dashboard.
- Zero samples: upload included firmware, close Serial Monitor, reconnect. Backend accepts both included `DIST,19.45` lines and the old `Distance: 19.45 cm | ...` format.
- Missing dependencies: run `setup.bat` again.
- Missing COM port: unplug/replug ESP32, refresh port list.

The dashboard stores sessions in `backend/phasebreathe.db` and can export CSV. The median filter, EMA, peak detector, and moving average provide an experimental candidate rate only. Not validated for medical use; low movement does not mean breathing has stopped.
