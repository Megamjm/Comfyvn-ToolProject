from PySide6.QtGui import QAction

from pathlib import Path
def synth_voice(text:str, voice:str="neutral"):
    outdir=Path("exports/tts"); outdir.mkdir(parents=True, exist_ok=True)
    # stub: write a .txt as placeholder for wav
    name=f"{voice}_{abs(hash(text))%10_000}.txt"
    fp=outdir/name
    fp.write_text(f"VOICE={voice}\nTEXT={text}", encoding="utf-8")
    return str(fp)