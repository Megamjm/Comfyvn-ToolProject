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

yaml
Copy code

---

## ⚙️ Setup

### 1. Install dependencies
Install Python 3.10+ and Git.  
Then in PowerShell (Windows):

bash
git clone https://github.com/<YOUR_USERNAME>/VN-Toolchain.git
cd VN-Toolchain
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
2. (Optional) Link to ComfyUI
Ensure your ComfyUI instance runs at:

cpp
Copy code
http://127.0.0.1:8188
or change the endpoint using an environment variable:

bash
Copy code
set COMFY_HOST=http://127.0.0.1:8188
3. Launch VN Toolchain
bash
Copy code
launch.bat
Then open the dashboard:
👉 http://127.0.0.1:5000

🖥️ Dashboard Overview
Section	Description
⚙️ Options	Configure polling, themes, and automation behavior.
🖼️ Gallery	Displays generated renders for approval/rejection.
🧠 Summary	Creates LLM scene summaries for dialogue export.
📦 Queue	Adds approved renders to the Ren'Py export queue.
🎮 Export / Play	Builds .rpy scene files and launches the VN.
🌐 Preview	Opens a web-based view of exported scripts.

🧩 Environment Variables
Variable	Default	Description
COMFY_HOST	http://127.0.0.1:8188	ComfyUI REST endpoint
VN_AUTH	0	Enable admin login (1 to require password)
VN_PASSWORD	admin	Default admin password
VN_DATA_DIR	data	Custom path for data directory

🎬 Using Ren'Py
Local SDK
Place your Ren'Py SDK folder next to this project:

Copy code
VNToolchain/
├─ renpy/
│   └─ renpy.exe
└─ launch_renpy.bat
Launch
Click ▶️ Play VN in the web dashboard
or run:

bash
Copy code
launch_renpy.bat
If no SDK is found, the launcher will prompt you to install it.

📦 Export Workflow
Generate or sync renders from ComfyUI (🔄 Sync ComfyUI)

Approve images (✅)

Generate summaries (🧠)

Add to export queue (📦)

Export to Ren'Py (🎮)

Play or preview scenes (▶️ / 🌐)

🔒 Security Notes
Authentication can be toggled via VN_AUTH=1 and VN_PASSWORD.

The web server runs locally by default (127.0.0.1).

🧰 Roadmap
Milestone	Description
✅ Core VN Flow	Queue → Gallery → Summary → Export → Launch
🚧 Scene Graph	Branching VN routes and dialogue linking
🚧 LLM Integration	Automatic script generation from chats
🚧 Theme Engine	Change visual themes (Sakura, Neon, etc.)
🚧 Sprite Generator	Multi-ControlNet consistent character sprites

🧾 License
MIT License © 2025
Contributors welcome — please open an issue or pull request!

🤝 Acknowledgements
ComfyUI

Ren'Py

SillyTavern

LM Studio

yaml
Copy code
