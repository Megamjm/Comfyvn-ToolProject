from PySide6.QtGui import QAction
import re
from typing import List, Dict
class RoleplayParser:
    def parse_text(self, text: str) -> List[Dict]:
        lines=[]
        for raw in filter(None,[t.strip() for t in text.splitlines()]):
            m=re.match(r"^(\w+):\s*(.+)$", raw)
            lines.append({"speaker":m.group(1),"text":m.group(2)}) if m else lines.append({"speaker":"Narrator","text":raw})
        return lines