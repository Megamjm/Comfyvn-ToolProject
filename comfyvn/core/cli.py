from __future__ import annotations
from PySide6.QtGui import QAction
import json, typer
from comfyvn.core.sdk import ComfyVN
app=typer.Typer(add_completion=False)
@app.command()
def login(url:str, email:str, password:str):
    c=ComfyVN(url); print(c.login(email,password))
@app.command()
def scenes(url:str, token:str):
    c=ComfyVN(url, token); print(json.dumps(c.scene_list(), indent=2))
def main(): app()
if __name__=='__main__': main()