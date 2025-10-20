"""Importer registry for ComfyVN."""

from comfyvn.importers.renpy import RenpyImporter
from comfyvn.importers.kirikiri import KiriKiriImporter
from comfyvn.importers.nscripter import NscripterImporter
from comfyvn.importers.yuris import YuRISImporter
from comfyvn.importers.catsystem2 import CatSystem2Importer
from comfyvn.importers.bgi import BGIImporter
from comfyvn.importers.reallive import RealLiveImporter
from comfyvn.importers.unity import UnityVNImporter
from comfyvn.importers.tyrano import TyranoImporter
from comfyvn.importers.livemaker import LiveMakerImporter

ALL_IMPORTERS = [
    RenpyImporter(),
    KiriKiriImporter(),
    NscripterImporter(),
    YuRISImporter(),
    CatSystem2Importer(),
    BGIImporter(),
    RealLiveImporter(),
    UnityVNImporter(),
    TyranoImporter(),
    LiveMakerImporter(),
]

BY_ID = {imp.id: imp for imp in ALL_IMPORTERS}


def get_importer(engine_id: str):
    key = engine_id.lower()
    for importer in ALL_IMPORTERS:
        if importer.id == key or importer.label.lower() == key:
            return importer
    raise KeyError(engine_id)


__all__ = ["ALL_IMPORTERS", "BY_ID", "get_importer"]
