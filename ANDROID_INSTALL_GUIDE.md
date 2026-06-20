# Nova Creature — Android Installation Guide

## What You Get
- **Nova Creature** running on your Android phone
- Full brain routing (7 brain roles)
- People memory, lesson learning, permissions
- Access from ANY device on your WiFi network

## Requirements
- Android phone
- [Termux](https://termux.com/) (install from F-Droid, NOT Google Play)
- Python 3 (installed via Termux)
- WiFi network

---

## Installation

### Step 1: Install Termux
1. Download Termux from F-Droid: https://f-droid.org/packages/com.termux/
2. **Do NOT use the Google Play version** (it's outdated)
3. Open Termux and wait for the setup to complete

### Step 2: Extract Nova
1. Copy `nova_creature_android.zip` to your phone
2. In Termux, run:
```bash
cd ~
unzip /sdcard/Download/nova_creature_android.zip -d nova_creature
```

### Step 3: Run Setup
```bash
cd ~/nova_creature
bash ANDROID_SETUP_TERMUX.sh
```
This installs Python and sets up Nova.

### Step 4: Start Nova
```bash
bash ~/nova_run.sh
```
Nova starts and auto-opens in your browser.

---

## How to Access

### On the Same Phone
Open http://127.0.0.1:3000 in Chrome/Firefox

### From Another Device (Phone, Tablet, Laptop)
Open http://YOUR_ANDROID_IP:3000 in any browser
(YOUR_ANDROID_IP is shown when Nova starts)

---

## What Works

| Feature | Status | How |
|---------|--------|-----|
| Brain routing (7 roles) | ✅ REAL | Python server routes every question |
| People memory | ✅ REAL | Remembers names during session |
| Lesson learning | ✅ REAL | "Learn this: ..." stores lessons |
| Permission gates | ✅ REAL | mic/camera/speaker controls |
| Emergency stop | ✅ REAL | "stop all" disables sensors |
| Mock voice/camera | ✅ TEST | Test the pipeline without hardware |
| Web interface | ✅ REAL | Full HTML UI with route lights |
| PWA install | ✅ YES | Add to home screen (Chrome) |
| Multi-device access | ✅ YES | Any device on same WiFi |

## What's Mock (Not Real Hardware)
- Microphone input (needs Android app bridge)
- Camera input (needs Android app bridge)
- Speech-to-text (needs API key or local engine)
- Text-to-speech (needs Android TTS engine)

## Commands to Try
```
"What can you do?"
"Can you code?"
"My name is [your name]"
"What is my name?"
"Learn this: Nova should explain brain routes"
"Test yourself"
"Explain brain routes"
"Tell me about physics"
"allow mic"
"stop all"
```

## Stop Nova
Press Ctrl+C in Termux, or run:
```bash
kill $(pgrep -f nova_server_android.py)
```
