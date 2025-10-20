from PySide6.QtGui import QAction
from typing import List, Dict
class RoleplayAnalyzer:
    def participants(self, lines: List[Dict]) -> List[str]:
        seen=[]
        for l in lines:
            s=l.get('speaker') or 'Narrator'
            if s not in seen: seen.append(s)
        return seen