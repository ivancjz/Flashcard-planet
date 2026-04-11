"""Tests for LLM provider abstraction."""
from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch


class ProviderFactoryTests(unittest.TestCase):
    def test_default_provider_is_anthropic(self):
        env = {k: v for k, v in os.environ.items() if k != "LLM_PROVIDER"}
        with patch.dict(os.environ, env, clear=True):
            import backend.app.services.llm_provider as m
            self.assertIsInstance(m.get_llm_provider(), m.AnthropicProvider)

    def test_explicit_anthropic_returns_anthropic(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "anthropic"}):
            import backend.app.services.llm_provider as m
            self.assertIsInstance(m.get_llm_provider(), m.AnthropicProvider)

    def test_gemini_returns_gemini(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "gemini"}):
            import backend.app.services.llm_provider as m
            self.assertIsInstance(m.get_llm_provider(), m.GeminiProvider)

    def test_unknown_provider_falls_back_to_anthropic_and_logs(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "gpt-99"}):
            import backend.app.services.llm_provider as m
            with self.assertLogs("backend.app.services.llm_provider", level="WARNING"):
                result = m.get_llm_provider()
            self.assertIsInstance(result, m.AnthropicProvider)


class AnthropicProviderTests(unittest.TestCase):
    def test_returns_none_when_key_empty(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
            import backend.app.services.llm_provider as m
            result = m.AnthropicProvider().generate_text("sys", "user", 256)
            self.assertIsNone(result)

    def test_no_sdk_call_when_key_empty(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
            import backend.app.services.llm_provider as m
            original = m._Anthropic
            mock_cls = MagicMock()
            m._Anthropic = mock_cls
            try:
                m.AnthropicProvider().generate_text("sys", "user", 256)
                mock_cls.assert_not_called()
            finally:
                m._Anthropic = original


class GeminiProviderTests(unittest.TestCase):
    def test_returns_none_when_key_empty(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            import backend.app.services.llm_provider as m
            result = m.GeminiProvider().generate_text("sys", "user", 256)
            self.assertIsNone(result)

    def test_no_sdk_call_when_key_empty(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            import backend.app.services.llm_provider as m
            original = m._genai
            mock_genai = MagicMock()
            m._genai = mock_genai
            try:
                m.GeminiProvider().generate_text("sys", "user", 256)
                mock_genai.GenerativeModel.assert_not_called()
            finally:
                m._genai = original


class NoiseFallbackTests(unittest.TestCase):
    def test_filter_noise_returns_all_true_when_provider_returns_none(self):
        none_provider = MagicMock()
        none_provider.generate_text.return_value = None
        with patch(
            "backend.app.ingestion.noise_filter.get_llm_provider",
            return_value=none_provider,
        ):
            from backend.app.ingestion import noise_filter
            import importlib
            importlib.reload(noise_filter)
            result = noise_filter.filter_noise(["Charizard PSA 10", "50x bulk lot"])
            self.assertEqual(result, [True, True])
