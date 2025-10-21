<!-- ComfyVN Architect | Phase 2/2 -->

# Phase 1 Workboard — Core Stabilization

**Goal:** Boot cleanly, stay up, and surface system state (metrics/logging) reliably. No exciting features here—just a rock-solid base.

**Scope (must land in Phase 1):**
- Server boot order & `/health` resilience
- GUI ↔ ServerBridge backoff & retry
- Metrics polling in GUI (no graphs perfection needed—just visible numbers)
- Logging path normalization to `./logs/` across launcher/server/gui
- Menu duplication fix

---

## Tasks & Acceptance Criteria

### 1) Server boot order / health
- [ ] Ensure single `create_app()` and deterministic startup
- [ ] `/health` returns 200 JSON within 2s of process start
- [ ] WS hub initializes without exceptions; idle ping ok

**Acceptance:**  
`tools/doctor_phase1.py --base http://127.0.0.1:8001` prints `"health_ok": true` and `"ws_hint": "ready or optional"`.

---

### 2) ServerBridge backoff in GUI
- [ ] On server not ready, GUI shows “Waiting for server…” (no crash)
- [ ] Exponential backoff (e.g., 0.5s → 1s → 2s → max 5s) with cancel
- [ ] “Reconnect” action in menu triggers immediate probe

**Acceptance:**  
Kill server, launch GUI: no traceback; visible non-blocking status; reconnect works when server returns.

---

### 3) Metrics polling (read path)
- [ ] GUI polls `/system/metrics` every 2–3s
- [ ] Basic render of CPU%, RAM%, (first GPU if present)
- [ ] No flood: concurrent requests capped; slow endpoint doesn’t freeze UI

**Acceptance:**  
With server running, GUI shows changing numbers; logs show no request pileups.

---

### 4) Logging path normalization
- [ ] All logs under `./logs/` (create if missing)
- [ ] `gui.log`, `server.log`, `launcher.log` rotate or cap at sensible size (OK to skip rotation this phase if size <10MB)
- [ ] Relative paths consistent on Windows & Linux

**Acceptance:**  
After full run, those three files exist and contain startup lines; `doctor_phase1` reports `"logs_ok": true`.

---

### 5) Menu duplication fix
- [ ] Single instance of top-level menus after reloads
- [ ] Regression guard: unit or smoke assert around menu count

**Acceptance:**  
Open/close/reload view 3x → still one set of menus.

---

## Nice-to-haves (if time)
- [ ] Minimal Jobs widget: count of queued/active/done via WS or poll
- [ ] Feature flags in `config/comfyvn.json` disable external connectors (LM Studio, ComfyUI, SillyTavern) during Phase 1

---

## Commands (quick smoke)

**Windows (PowerShell):**
```powershell
python tools/doctor_phase1.py --base http://127.0.0.1:8001
Get-Content -Tail 50 .\logs\server.log
Get-Content -Tail 50 .\logs\gui.log