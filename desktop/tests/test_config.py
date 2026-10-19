"""配置读写与密钥遮蔽：示例可用、密钥只进不出、坏配置给出能直接看的错误。

这里不碰用户真实的 %APPDATA%：所有落盘用例都在临时目录里，
只有"读仓库示例"一条走 assets/providers.example.json。
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from deai_app.core import config
from deai_app.core.config import ConfigError, Provider, Settings

SECRET = "sk-test-SECRET-1234567890"


def provider(name: str = "测试", base_url: str = "https://example.com/v1") -> Provider:
    return Provider(name=name, base_url=base_url, model="test-model", api_key=SECRET)


class TestConfigDir(unittest.TestCase):
    def test_env_override_wins(self) -> None:
        target = Path(tempfile.gettempdir()) / "deai-cfg-probe"
        with mock.patch.dict(os.environ, {config.ENV_DIR: str(target)}):
            self.assertEqual(config.config_dir(), target)

    def test_appdata_default(self) -> None:
        target = Path(tempfile.gettempdir()) / "deai-appdata-probe"
        with mock.patch.dict(os.environ, {config.ENV_DIR: "", "APPDATA": str(target)}):
            self.assertEqual(config.config_dir(), target / config.APP_FOLDER)

    def test_ensure_creates_directory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="deai-cfg-") as tmp:
            target = Path(tmp) / "nested" / "deai"
            with mock.patch.dict(os.environ, {config.ENV_DIR: str(target)}):
                self.assertFalse(target.exists())
                self.assertEqual(config.ensure_config_dir(), target)
                self.assertTrue(target.is_dir())


class TestMaskAndRedact(unittest.TestCase):
    def test_mask_empty(self) -> None:
        self.assertEqual(config.mask(""), "（未设置）")

    def test_mask_keeps_only_tail(self) -> None:
        masked = config.mask(SECRET)
        self.assertEqual(masked, f"«…{SECRET[-4:]}»")
        self.assertNotIn(SECRET, masked)

    def test_short_secret_is_fully_hidden(self) -> None:
        self.assertEqual(config.mask("12345678"), config.MASKED)
        self.assertEqual(config.mask("abc"), config.MASKED)

    def test_redact_replaces_all_known_secrets(self) -> None:
        text = f"请求头 Bearer {SECRET}，旧密钥 old-secret-999 也不该出现"
        redacted = config.redact(text, (SECRET, "old-secret-999"))
        self.assertNotIn(SECRET, redacted)
        self.assertNotIn("old-secret-999", redacted)
        self.assertEqual(redacted.count(config.MASKED), 2)

    def test_redact_ignores_too_short_secrets(self) -> None:
        # 太短的串替换会把正常文字一起吃掉，长度阈值是刻意的
        self.assertEqual(config.redact("abc 出现了", ("abc",)), "abc 出现了")
        self.assertEqual(config.redact("ab 出现了", ("",)), "ab 出现了")


class TestProvider(unittest.TestCase):
    def test_endpoint_appends_path(self) -> None:
        self.assertEqual(provider(base_url="https://api.example.com/v1").endpoint(),
                         "https://api.example.com/v1/chat/completions")

    def test_endpoint_handles_trailing_slash(self) -> None:
        self.assertEqual(provider(base_url="https://api.example.com/v1/").endpoint(),
                         "https://api.example.com/v1/chat/completions")

    def test_endpoint_accepts_full_url(self) -> None:
        full = "https://api.example.com/v1/chat/completions"
        self.assertEqual(provider(base_url=full).endpoint(), full)

    def test_validate_rejects_bad_scheme(self) -> None:
        with self.assertRaises(ConfigError) as ctx:
            provider(base_url="api.example.com/v1").validate()
        self.assertIn("http://", str(ctx.exception))

    def test_validate_rejects_empty_model(self) -> None:
        broken = Provider(name="测试", base_url="https://example.com/v1", model="", api_key=SECRET)
        with self.assertRaises(ConfigError) as ctx:
            broken.validate()
        self.assertIn("model", str(ctx.exception))

    def test_validate_rejects_missing_key_on_remote(self) -> None:
        broken = Provider(name="测试", base_url="https://example.com/v1", model="m", api_key="")
        with self.assertRaises(ConfigError) as ctx:
            broken.validate()
        self.assertIn("api_key", str(ctx.exception))

    def test_validate_allows_keyless_local_services(self) -> None:
        for host in ("127.0.0.1", "localhost", "0.0.0.0", "[::1]"):
            with self.subTest(host=host):
                Provider(name="本地", base_url=f"http://{host}:11434/v1", model="m").validate()

    def test_is_local_marks_only_loopback_hosts(self) -> None:
        for url in ("http://127.0.0.1:11434/v1", "http://localhost/v1",
                    "http://[::1]:8080/v1", "http://0.0.0.0:8080/v1"):
            with self.subTest(url=url):
                self.assertTrue(provider(base_url=url).is_local())
        for url in ("https://api.example.com/v1", "http://192.168.1.5:8080/v1"):
            with self.subTest(url=url):
                self.assertFalse(provider(base_url=url).is_local())

    def test_masked_never_contains_secret(self) -> None:
        data = provider().masked()
        self.assertNotIn(SECRET, json.dumps(data, ensure_ascii=False))
        self.assertEqual(data["model"], "test-model")


class TestProvidersFile(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="deai-providers-")
        self.dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write(self, payload) -> Path:
        path = self.dir / config.PROVIDERS_FILE
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def test_list_payload_and_defaults(self) -> None:
        self.write([{"name": "甲", "base_url": "https://a.example/v1", "model": "m-a"},
                    {"base_url": "https://b.example/v1", "model": "m-b", "temperature": 0.7}])
        providers = config.load_providers(self.dir)
        self.assertEqual([p.name for p in providers], ["甲", "m-b"])
        self.assertEqual(providers[0].temperature, 0.3)
        self.assertEqual(providers[0].max_tokens, 4096)
        self.assertEqual(providers[1].temperature, 0.7)

    def test_dict_payload(self) -> None:
        self.write({"providers": [{"name": "乙", "base_url": "https://b.example/v1",
                                   "model": "m-b", "timeout": 300}]})
        providers = config.load_providers(self.dir)
        self.assertEqual(len(providers), 1)
        self.assertEqual(providers[0].timeout, 300)

    def test_incomplete_entries_are_skipped(self) -> None:
        self.write({"providers": [{"name": "缺地址", "model": "m"},
                                  {"name": "缺模型", "base_url": "https://x.example/v1"},
                                  "不是对象",
                                  {"name": "完整", "base_url": "https://ok.example/v1", "model": "m"}]})
        providers = config.load_providers(self.dir)
        self.assertEqual([p.name for p in providers], ["完整"])

    def test_malformed_json_is_user_facing(self) -> None:
        (self.dir / config.PROVIDERS_FILE).write_text("{not json", encoding="utf-8")
        with self.assertRaises(ConfigError) as ctx:
            config.load_providers(self.dir)
        self.assertIn("不是合法 JSON", str(ctx.exception))
        self.assertIn(config.PROVIDERS_FILE, str(ctx.exception))

    def test_wrong_payload_shape_is_user_facing(self) -> None:
        self.write("oops")
        with self.assertRaises(ConfigError):
            config.load_providers(self.dir)
        self.write({"providers": "oops"})
        with self.assertRaises(ConfigError):
            config.load_providers(self.dir)

    def test_bad_numeric_field_names_the_provider(self) -> None:
        self.write([{"name": "坏温度", "base_url": "https://x.example/v1",
                     "model": "m", "temperature": "hot"}])
        with self.assertRaises(ConfigError) as ctx:
            config.load_providers(self.dir)
        self.assertIn("坏温度", str(ctx.exception))
        self.assertIn("temperature", str(ctx.exception))

    def test_missing_file_falls_back_to_bundled_example(self) -> None:
        providers = config.load_providers(self.dir)
        self.assertGreaterEqual(len(providers), 5)
        self.assertTrue(any(p.name == "本地 Ollama" for p in providers))
        self.assertTrue(all(p.api_key == "" for p in providers),
                        "仓库示例不许带密钥")

    def test_save_load_roundtrip(self) -> None:
        original = [provider("甲"), provider("乙", base_url="http://127.0.0.1:11434/v1")]
        path = config.save_providers(original, self.dir)
        self.assertEqual(path, self.dir / config.PROVIDERS_FILE)
        self.assertEqual(config.load_providers(self.dir), original)
        self.assertIn(SECRET, path.read_text(encoding="utf-8"))


class TestActiveProvider(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="deai-active-")
        self.dir = Path(self.tmp.name)
        config.save_providers([provider("甲"), provider("乙")], self.dir)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_default_is_first(self) -> None:
        self.assertEqual(config.active_provider("", self.dir).name, "甲")

    def test_lookup_by_name(self) -> None:
        self.assertEqual(config.active_provider("乙", self.dir).name, "乙")

    def test_unknown_name_lists_available(self) -> None:
        with self.assertRaises(ConfigError) as ctx:
            config.active_provider("丙", self.dir)
        message = str(ctx.exception)
        self.assertIn("丙", message)
        self.assertIn("甲", message)
        self.assertIn("乙", message)
        self.assertNotIn(SECRET, message)


class TestSettingsFile(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="deai-settings-")
        self.dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_missing_file_gives_defaults(self) -> None:
        self.assertEqual(config.load_settings(self.dir), Settings())

    def test_unknown_keys_are_ignored(self) -> None:
        (self.dir / config.SETTINGS_FILE).write_text(
            json.dumps({"preset": "公文", "future_key": 1}), encoding="utf-8")
        settings = config.load_settings(self.dir)
        self.assertEqual(settings.preset, "公文")
        self.assertEqual(settings.intensity, "中")

    def test_non_object_is_user_facing(self) -> None:
        (self.dir / config.SETTINGS_FILE).write_text("[1, 2]", encoding="utf-8")
        with self.assertRaises(ConfigError) as ctx:
            config.load_settings(self.dir)
        self.assertIn("JSON 对象", str(ctx.exception))

    def test_save_load_roundtrip(self) -> None:
        settings = Settings(active_provider="甲", preset="公文", intensity="高",
                            max_rounds=3, lang="en", auto_deai_after_translate=False)
        path = config.save_settings(settings, self.dir)
        self.assertEqual(path, self.dir / config.SETTINGS_FILE)
        self.assertEqual(config.load_settings(self.dir), settings)


if __name__ == "__main__":
    unittest.main()
