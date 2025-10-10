# 🎮 VN Toolchain — ComfyUI + Ren'Py Visual Novel Automation

**VN Toolchain** is a modular open-source suite that bridges  
**ComfyUI**, **SillyTavern**, **LM Studio**, and **Ren'Py**  
to generate visual-novel-style experiences directly from AI chat and renders.

It provides:
- 🧠 LLM → Scene/Dialogue → Render → Ren'Py pipeline
- 🧩 Flask-based web dashboard with configurable options
- 🖼️ Gallery for approving/rejecting ComfyUI renders
- 🎬 Automatic Ren'Py `.rpy` scene exporter
- ▶️ Launcher buttons for previewing and playing your VN
- 🔧 Full JSON/metadata sidecar tracking for re-renders

---

## 🧭 Project Structure
VNToolchain/
├─ server/ # Flask backend + templates
│ ├─ app.py # Main application file
│ ├─ templates/
│ │ └─ index.html # Web UI
│ └─ static/
│ └─ js/app.js # Client-side logic
│
├─ data/ # Runtime data (auto-generated)
│ ├─ assets/
│ ├─ gallery/
│ ├─ summaries/
│ ├─ export_queue/
│ └─ renpy_project/ # Output Ren'Py game project
│
├─ launch.bat # Start Flask server
├─ launch_renpy.bat # Launch or open Ren'Py project
├─ requirements.txt # Python dependencies
└─ .gitignore # Keeps local data & SDKs out of Git


## ⚙️ Setup

### 1. Install dependencies
Install Python 3.10+ and Git.  
Then in PowerShell (Windows):

```bash
git clone https://github.com/<YOUR_USERNAME>/VN-Toolchain.git
cd VN-Toolchain
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt