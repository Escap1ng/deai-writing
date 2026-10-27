"""config — 供应商 profile 与用户设置的读写；密钥只进不出。

数据目录默认 %APPDATA%\\deai\\，仓库内只有一份不含密钥的 providers.example.json。
任何要显示给用户的文本都先过 redact()，异常里也不许带出 api_key 原文。
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit

from deai_app import paths

__all__ = [
    "ConfigError",
    "Provider",
    "Settings",
    "config_dir",
    "ensure_config_dir",
    "load_providers",
    "load_settings",
    "mask",
    "redact",
    "save_providers",
    "save_settings",
]

ENV_DIR = "DEAI_CONFIG_DIR"
APP_FOLDER = "deai"
PROVIDERS_FILE = "providers.json"
SETTINGS_FILE = "settings.json"
MASKED = "«密钥已隐藏»"
_TAIL = 4


class ConfigError(RuntimeError):
    """配置缺失或格式错误；message 直接面向用户。"""


@dataclass(frozen=True)
class Provider:
    """一套 OpenAI 兼容接口；换供应商只改这里，不改代码。"""

    name: str
    base_url: str
    model: str
    api_key: str = ""
    temperature: float = 0.3
    max_tokens: int = 4096
    timeout: int = 120

    def endpoint(self) -> str:
        base = self.base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"

    def is_local(self) -> bool:
        return _is_local(self.base_url)

    def validate(self) -> None:
        if not self.base_url.startswith(("http://", "https://")):
            raise ConfigError(f"{self.name}：base_url 要以 http:// 或 https:// 开头")
        if not self.model:
            raise ConfigError(f"{self.name}：model 不能为空")
        if not self.api_key and not _is_local(self.base_url):
            raise ConfigError(f"{self.name}：没有 api_key，本地服务除外")

    def masked(self) -> dict:
        data = asdict(self)
        data["api_key"] = mask(self.api_key)
        return data


@dataclass
class Settings:
    active_provider: str = ""
    preset: str = "论文"
    intensity: str = "中"
    max_rounds: int = 2
    lang: str = "自动"
    translate_target: str = "自动"
    auto_deai_after_translate: bool = True


def config_dir(create: bool = False) -> Path:
    override = os.environ.get(ENV_DIR, "").strip()
    if override:
        base = Path(override).expanduser()
    else:
        appdata = os.environ.get("APPDATA", "").strip()
        base = Path(appdata) / APP_FOLDER if appdata else Path.home() / ".config" / APP_FOLDER
    if create:
        base.mkdir(parents=True, exist_ok=True)
    return base


def ensure_config_dir() -> Path:
    return config_dir(create=True)


def mask(secret: str) -> str:
    if not secret:
        return "（未设置）"
    if len(secret) <= _TAIL * 2:
        return MASKED
    return f"«…{secret[-_TAIL:]}»"


def redact(text: str, secrets: tuple[str, ...] | list[str] = ()) -> str:
    """把已知密钥从任意待显示文本里换掉——异常信息、日志、状态栏都走这一道。"""
    out = text
    for secret in secrets:
        if secret and len(secret) > 4:
            out = out.replace(secret, MASKED)
    return out


def _read_json(path: Path, what: str) -> dict | list:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ConfigError(f"{what} 不是合法 JSON：{path}（{exc}）") from exc


def _is_local(base_url: str) -> bool:
    try:
        host = urlsplit(base_url).hostname or ""
    except ValueError:
        return False
    return host in ("127.0.0.1", "localhost", "::1", "0.0.0.0")


def _number(item: dict, key: str, cast, default, label: str):
    value = item.get(key, default)
    try:
        return cast(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"供应商“{label}”的 {key} 不是有效数字：{value!r}") from exc


def example_path() -> Path:
    return paths.ASSETS_DIR / "providers.example.json"


def load_providers(directory: Path | None = None) -> list[Provider]:
    """读用户的 providers.json；没有就读仓库自带的示例（示例不含密钥）。"""
    folder = directory or config_dir()
    path = folder / PROVIDERS_FILE
    if path.is_file():
        data = _read_json(path, "供应商配置")
    else:
        path = example_path()
        data = _read_json(path, "示例配置")
    if isinstance(data, list):
        raw = data
    elif isinstance(data, dict):
        raw = data.get("providers", [])
        if not isinstance(raw, list):
            raise ConfigError(f"供应商配置里的 providers 应是数组：{path}")
    else:
        raise ConfigError(f"供应商配置应是数组或含 providers 数组的对象：{path}")
    providers: list[Provider] = []
    for item in raw:
        if not isinstance(item, dict) or "base_url" not in item or "model" not in item:
            continue
        name = str(item.get("name") or item["model"])
        providers.append(
            Provider(
                name=name,
                base_url=str(item["base_url"]),
                model=str(item["model"]),
                api_key=str(item.get("api_key", "")),
                temperature=_number(item, "temperature", float, 0.3, name),
                max_tokens=_number(item, "max_tokens", int, 4096, name),
                timeout=_number(item, "timeout", int, 120, name),
            )
        )
    return providers


def active_provider(name: str = "", directory: Path | None = None) -> Provider:
    providers = load_providers(directory)
    if not providers:
        raise ConfigError("还没有可用配置：在 %APPDATA%\\deai\\providers.json 里填 base_url、model 与 api_key")
    if not name:
        return providers[0]
    for provider in providers:
        if provider.name == name:
            return provider
    names = "、".join(p.name for p in providers)
    raise ConfigError(f"找不到供应商“{name}”，现有：{names}")


def save_providers(providers: list[Provider], directory: Path | None = None) -> Path:
    folder = directory or ensure_config_dir()
    path = Path(folder) / PROVIDERS_FILE
    payload = {"providers": [asdict(p) for p in providers]}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_settings(directory: Path | None = None) -> Settings:
    folder = directory or config_dir()
    data = _read_json(Path(folder) / SETTINGS_FILE, "设置")
    if not isinstance(data, dict):
        raise ConfigError("设置文件应是一个 JSON 对象")
    known = {f for f in Settings.__dataclass_fields__}
    return Settings(**{k: v for k, v in data.items() if k in known})


def save_settings(settings: Settings, directory: Path | None = None) -> Path:
    folder = directory or ensure_config_dir()
    path = Path(folder) / SETTINGS_FILE
    path.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
