from PySide6.QtGui import QAction
from __future__ annotations

import json
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
from PySide6.QtCore import Qt, QPointF, QSize
from PySide6.QtGui import QPixmap, QPainter, QColor, QPen, QIcon
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QFileDialog, QFrame
try:
    from comfyvn.assets.pose_manager import PoseManager
except Exception:
    PoseManager = None  # type: ignore

def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    try: return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception: return None

def _normalize_skeleton(entry: Dict[str, Any]) -> Dict[int, Tuple[float, float]]:
    def to_xy(v):
        if isinstance(v,(list,tuple)) and len(v)>=2: return float(v[0]), float(v[1])
        if isinstance(v,dict) and 'x' in v and 'y' in v: return float(v['x']), float(v['y'])
        return None
    sk = entry.get("skeleton") or entry
    pts = sk.get("points") or sk.get("keypoints") or {}
    out: Dict[int, Tuple[float,float]] = {}
    if isinstance(pts, dict):
        for k,v in pts.items():
            xy = to_xy(v)
            if xy:
                try: out[int(k)] = xy
                except Exception: pass
    elif isinstance(pts, list):
        for item in pts:
            if isinstance(item, dict) and 'id' in item:
                xy = to_xy(item)
                if xy: out[int(item['id'])] = xy
    return out

def _draw_pose_pixmap(width:int, height:int, skeleton: Dict[int, Tuple[float,float]], normalized: bool=False) -> QPixmap:
    pix = QPixmap(width, height); pix.fill(QColor(18,18,18)); p=QPainter(pix)
    if skeleton:
        pen = QPen(QColor('#00FFAA')); pen.setWidth(3); p.setPen(pen)
        ids = sorted(skeleton.keys()); prev=None
        for i in ids:
            x,y = skeleton[i]
            px,py = (x*width, y*height) if normalized else (x,y)
            pt = QPointF(px,py); p.drawEllipse(pt,4,4)
            if prev is not None: p.drawLine(prev, pt)
            prev = pt
    p.end(); return pix

def _find_pose_files() -> List[Path]:
    roots=[Path('./data/poses'), Path('./comfyvn/data/poses')]; out=[]
    for r in roots:
        if r.exists(): out.extend(sorted(r.rglob('*.json')))
    return out

class PoseBrowser(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.title = QLabel('Pose Browser'); self.title.setStyleSheet('font-weight:bold;')
        self.list = QListWidget(); self.list.currentItemChanged.connect(self._on_select)
        self.preview = QLabel('No selection'); self.preview.setAlignment(Qt.AlignCenter); self.preview.setMinimumSize(QSize(320,480)); self.preview.setFrameShape(QFrame.StyledPanel)
        self.btn_reload = QPushButton('Reload'); self.btn_reload.clicked.connect(self.reload)
        self.btn_open = QPushButton('Open JSON…'); self.btn_open.clicked.connect(self._open_dialog)
        top = QHBoxLayout(); top.addWidget(self.title,1); top.addWidget(self.btn_reload); top.addWidget(self.btn_open)
        body = QHBoxLayout(); body.addWidget(self.list,1); body.addWidget(self.preview,2)
        root = QVBoxLayout(self); root.addLayout(top); root.addLayout(body)
        self.reload()

    def reload(self):
        self.list.clear()
        if PoseManager:
            try:
                pm = PoseManager()
                for rec in pm.list() or []:
                    p = Path(rec) if isinstance(rec,str) else Path(rec.get('path',''))
                    if p.suffix.lower()=='.json':
                        it = QListWidgetItem(p.stem); it.setData(Qt.UserRole, str(p)); it.setToolTip(str(p)); it.setIcon(QIcon(_draw_pose_pixmap(96,144,{},False))); self.list.addItem(it)
            except Exception: pass
        for f in _find_pose_files():
            it = QListWidgetItem(f.stem); it.setData(Qt.UserRole, str(f)); it.setToolTip(str(f)); it.setIcon(QIcon(_draw_pose_pixmap(96,144,{},False))); self.list.addItem(it)
        if self.list.count()==0: self.preview.setText('No pose files found')

    def _open_dialog(self):
        fn,_ = QFileDialog.getOpenFileName(self,'Open Pose JSON', str(Path('.').resolve()), 'Pose JSON (*.json)')
        if fn: p=Path(fn); it=QListWidgetItem(p.stem); it.setData(Qt.UserRole,str(p)); self.list.addItem(it)

    def _on_select(self, cur, prev):
        if not cur: self.preview.setText('No selection'); return
        p = Path(cur.data(Qt.UserRole)); entry = _load_json(p)
        if not entry: self.preview.setText('Failed to load'); return
        sk = _normalize_skeleton(entry); normalized=False
        if sk:
            vals=list(sk.values())
            if vals: normalized = max(max(abs(a),abs(b)) for a,b in vals) <= 1.05
        self.preview.setPixmap(_draw_pose_pixmap(384,576,sk,normalized))