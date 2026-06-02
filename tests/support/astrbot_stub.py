from __future__ import annotations

import logging
import os
import sys
import tempfile
import types
from dataclasses import dataclass
from importlib.util import find_spec


class AstrBotConfig(dict):
    pass


class AstrMessageEvent:
    def __init__(self, message_str: str = "", unified_msg_origin: str = "test-origin"):
        self.message_str = message_str
        self.unified_msg_origin = unified_msg_origin

    def plain_result(self, text: str):
        return {"type": "plain", "text": text}

    def chain_result(self, chain: list[object]):
        return {"type": "chain", "chain": chain}


class Context:
    async def llm_generate(self, *args, **kwargs):
        raise NotImplementedError

    async def get_current_chat_provider_id(self, umo=None):
        return "stub-provider"


class Star:
    def __init__(self, context: Context):
        self.context = context


@dataclass
class Plain:
    text: str


@dataclass
class File:
    file: str
    name: str | None = None


class _CommandGroup:
    def __init__(self, func):
        self.func = func
        self.__name__ = getattr(func, "__name__", "command_group")
        self.__doc__ = getattr(func, "__doc__", None)

    def __call__(self, *args, **kwargs):
        return self.func(*args, **kwargs)

    def command(self, name: str):
        def decorator(func):
            func.__paperos_command__ = name
            return func

        return decorator

    def group(self, name: str):
        def decorator(func):
            group = _CommandGroup(func)
            group.__paperos_group__ = name
            return group

        return decorator


class _Filter:
    @staticmethod
    def command_group(name: str):
        def decorator(func):
            group = _CommandGroup(func)
            group.__paperos_group__ = name
            return group

        return decorator

    @staticmethod
    def llm_tool(name: str):
        def decorator(func):
            func.__paperos_llm_tool__ = name
            return func

        return decorator


def _get_astrbot_data_path() -> str:
    return os.environ.get(
        "PAPEROS_TEST_DATA_DIR",
        os.path.join(tempfile.gettempdir(), "paperos-tests"),
    )


def install_astrbot_stub() -> None:
    """Install a minimal AstrBot module tree for tests.

    The real plugin runs inside AstrBot. Unit tests run outside that runtime, so
    this stub only provides the symbols imported by PaperOS modules.
    """

    if "astrbot.api" in sys.modules:
        return

    logger = logging.getLogger("paperos.tests.astrbot")

    astrbot_mod = types.ModuleType("astrbot")
    api_mod = types.ModuleType("astrbot.api")
    event_mod = types.ModuleType("astrbot.api.event")
    star_mod = types.ModuleType("astrbot.api.star")
    comp_mod = types.ModuleType("astrbot.api.message_components")
    core_mod = types.ModuleType("astrbot.core")
    utils_mod = types.ModuleType("astrbot.core.utils")
    path_mod = types.ModuleType("astrbot.core.utils.astrbot_path")

    api_mod.AstrBotConfig = AstrBotConfig
    api_mod.logger = logger
    event_mod.AstrMessageEvent = AstrMessageEvent
    event_mod.filter = _Filter
    star_mod.Context = Context
    star_mod.Star = Star
    comp_mod.Plain = Plain
    comp_mod.File = File
    path_mod.get_astrbot_data_path = _get_astrbot_data_path

    sys.modules["astrbot"] = astrbot_mod
    sys.modules["astrbot.api"] = api_mod
    sys.modules["astrbot.api.event"] = event_mod
    sys.modules["astrbot.api.star"] = star_mod
    sys.modules["astrbot.api.message_components"] = comp_mod
    sys.modules["astrbot.core"] = core_mod
    sys.modules["astrbot.core.utils"] = utils_mod
    sys.modules["astrbot.core.utils.astrbot_path"] = path_mod

    if find_spec("pypdf") is None:
        _install_pypdf_stub()


def _install_pypdf_stub() -> None:
    pypdf_mod = types.ModuleType("pypdf")
    errors_mod = types.ModuleType("pypdf.errors")

    class PdfReadError(Exception):
        pass

    class PdfReader:
        def __init__(self, path):
            self.path = path
            self.pages = [object()]

    pypdf_mod.PdfReader = PdfReader
    errors_mod.PdfReadError = PdfReadError
    sys.modules["pypdf"] = pypdf_mod
    sys.modules["pypdf.errors"] = errors_mod
