from PySide6.QtGui import QAction

def autoplay(branches:list, seed_choice:int=0):
    # deterministic walk: pick index seed_choice at each fork
    path=[]; idx=seed_choice
    for i,opts in enumerate(branches or []):
        if not isinstance(opts, list) or not opts:
            path.append({"step":i,"choice":None,"result":None}); continue
        pick=opts[min(idx, len(opts)-1)]
        path.append({"step":i,"choice":pick.get("id") if isinstance(pick,dict) else pick,"result":"ok"})
    return {"path":path,"end":"reached"}