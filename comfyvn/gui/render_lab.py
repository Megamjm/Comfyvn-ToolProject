# [replace test_render() body] // ComfyVN_Architect (Asset Sprite Research Branch)
def test_render(self):
    style = self.styles.get(self.cbo_style.currentText(), {})
    base = self.cbo_base.currentText()
    payload = {
        "character": {"id": "render_lab_char", "name": "RenderLab"},
        "style_id": style.get("id"),
        "base_model": base,
        "lora_stack": list(self.selected_loras),
        "controlnets": list(self.selected_control),
        "seed": 12345,
        "transparent": True
    }
    try:
        r = requests.post(f"{self.server_url}/render/char", json=payload, timeout=90)
        data = r.json()
        if r.status_code == 200 and data.get("status") == "ok":
            QMessageBox.information(self, "Render Lab",
                f"Rendered.\nExport: {data.get('export_path')}\nCached: {data.get('cached')}")
        else:
            QMessageBox.warning(self, "Render Lab", f"Response:\n{json.dumps(data, indent=2)}")
    except Exception as e:
        QMessageBox.critical(self, "Render Lab", f"Render call failed:\n{e}")
