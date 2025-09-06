# 🖱️ G-Wolves Battery Monitor

A lightweight Python tray utility that displays the **battery percentage of your G-Wolves Fenrir Max 8K (and similar WebHID mice)**.  
It uses **Playwright** to open [mouse.xyz](https://mouse.xyz), automatically connects to your dongle via the HID picker, and shows the current battery level in the system tray.

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
## ScreenShots

<img width="1432" height="972" alt="{ABD57444-CF54-4EFE-A846-60F3D34AED6A}" src="https://github.com/user-attachments/assets/08805c92-f521-46ac-9351-c0fcff33be6d" />
<img width="49" height="50" alt="{DD13A08D-DF2E-4B55-B11D-144810049012}" src="https://github.com/user-attachments/assets/7f246b26-cb2e-457d-ae60-ae04e1f09b5b" />
<img width="199" height="108" alt="{E3575894-1FA0-4E21-854F-6F4CFFBAB92F}" src="https://github.com/user-attachments/assets/2f6c7926-da8a-44e9-9c81-f1c33b9a0b80" />


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
