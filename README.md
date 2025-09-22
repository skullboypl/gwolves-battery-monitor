# 🖱️ G-Wolves Battery Monitor

A lightweight Python tray utility that displays the **battery percentage of your G-Wolves Fenrir Max 8K (and similar WebHID mice)**.  
It uses **Playwright** to open [mouse.xyz](https://mouse.xyz), automatically connects to your dongle via the HID picker, and shows the current battery level in the system tray.

<img width="124" height="61" alt="{9F710745-2D2A-4189-B95E-280E9EAC97B5}" src="https://github.com/user-attachments/assets/28015347-a483-4c71-9a58-ac7f6cdfbd17" />

<img width="195" height="114" alt="{AF8AC9E8-BD7C-480C-9685-A24572C3971C}" src="https://github.com/user-attachments/assets/7c2612f7-a1ab-456b-9ad5-56c347c3f97c" />

---

## ✨ Features

- 🟢 Auto-detects and connects to your mouse via WebHID
- ⏱️ Refreshes battery level every 10 minutes
- 🖼️ Minimal tray icon with percentage text
- 🌑 Chromium runs in dark mode, hidden after connection
- 💾 Persistent Chromium profile in  
  `C:\ProgramData\GwovesBatteryChromium` (remembers HID permission)

---

## 📦 Installation

1. Clone the repo:

```sh
git clone https://github.com/skullboypl/gwolves-battery-monitor.git
cd gwolves-battery-monitor
```

2. Install dependencies:

```sh
pip install -r requirements.txt
```

3. Install Playwright browser:

```sh
playwright install chromium
```

---

## 🚀 Usage

Run the script:

```sh
python battery.py
```

- The first time, a **HID permission dialog** will appear → the app auto-confirms it.
- After connecting, the Chromium window is **hidden** and the tray icon updates with battery %.
- Right-click the tray icon for options:
  - **Refresh now** – manually refresh battery %
  - **Hide/Show window** – toggle Chromium visibility
  - **Quit** – exit the app

---

## 📂 Project structure

```
battery.py       # main script
requirements.txt # dependencies
README.md        # documentation
LICENSE          # MIT license
```

---

## ⚖️ License

[MIT](LICENSE) © 2025 Artur Spychalski
