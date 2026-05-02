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
            with patch.object(m.settings, "llm_provider", ""):
                self.assertIsInstance(m.get_llm_provider(), m.AnthropicProvider)

    def test_explicit_anthropic_returns_anthropic(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "anthropic"}):
            import backend.app.services.llm_provider as m
            self.assertIsInstance(m.get_llm_provider(), m.AnthropicProvider)

    def test_unknown_provider_falls_back_to_anthropic_and_logs(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "gpt-99"}):
            import backend.app.services.llm_provider as m
            with self.assertLogs("backend.app.services.llm_provider", level="WARNING"):
                result = m.get_llm_provider()
            self.assertIsInstance(result, m.AnthropicProvider)

    def test_provider_can_fall_back_to_settings_when_env_missing(self):
        env = {k: v for k, v in os.environ.items() if k != "LLM_PROVIDER"}
        with patch.dict(os.environ, env, clear=True):
            import backend.app.services.llm_provider as m
            with patch.object(m.settings, "llm_provider", "groq"):
                self.assertIsInstance(m.get_llm_provider(), m.GroqProvider)


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


class GroqProviderTests(unittest.TestCase):
    def test_returns_none_when_key_empty(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": ""}):
            import backend.app.services.llm_provider as m
            with patch.object(m.settings, "groq_api_key", ""):
                result = m.GroqProvider().generate_text("sys", "user", 256)
            self.assertIsNone(result)

    def test_no_sdk_call_when_key_empty(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": ""}):
            import backend.app.services.llm_provider as m
            original = m._httpx_client_cls
            mock_cls = MagicMock()
            m._httpx_client_cls = mock_cls
            try:
                with patch.object(m.settings, "groq_api_key", ""):
                    m.GroqProvider().generate_text("sys", "user", 256)
                mock_cls.assert_not_called()
            finally:
                m._httpx_client_cls = original

    def test_groq_returns_groq_provider(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "groq"}):
            import backend.app.services.llm_provider as m
            self.assertIsInstance(m.get_llm_provider(), m.GroqProvider)


class NoiseFallbackTests(unittest.TestCase):
    def test_filter_noise_returns_all_true_when_provider_returns_none(self):
        import importlib
        from backend.app.ingestion import noise_filter
        importlib.reload(noise_filter)
        none_provider = MagicMock()
        none_provider.generate_text.return_value = None
        with patch(
            "backend.app.ingestion.noise_filter.get_llm_provider",
            return_value=none_provider,
        ):
            result = noise_filter.filter_noise(["Charizard PSA 10", "50x bulk lot"])
            self.assertEqual(result, [True, True])


class SignalExplainerFallbackTests(unittest.TestCase):
    def test_explain_signal_returns_none_and_skips_commit_when_provider_returns_none(self):
        import importlib
        import uuid
        from backend.app.services import signal_explainer
        importlib.reload(signal_explainer)
        none_provider = MagicMock()
        none_provider.generate_text.return_value = None
        with patch(
            "backend.app.services.signal_explainer.get_llm_provider",
            return_value=none_provider,
        ):
            db = MagicMock()
            asset_mock = MagicMock()
            asset_mock.name = "Charizard"
            db.get.return_value = asset_mock
            signal = MagicMock()
            signal.asset_id = uuid.uuid4()
            signal.label = "IDLE"
            signal.price_delta_pct = None
            signal.confidence = 50
            signal.liquidity_score = 30
            signal.prediction = None
            result = signal_explainer.explain_signal(db, signal)
            self.assertIsNone(result)
            db.commit.assert_not_called()


class OpenAIProviderTests(unittest.TestCase):
    def test_returns_none_when_key_empty(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            import backend.app.services.llm_provider as m
            with patch.object(m.settings, "openai_api_key", ""):
                result = m.OpenAIProvider().generate_text("sys", "user", 256)
            self.assertIsNone(result)

    def test_no_http_call_when_key_empty(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            import backend.app.services.llm_provider as m
            original = m._httpx_client_cls
            mock_cls = MagicMock()
            m._httpx_client_cls = mock_cls
            try:
                with patch.object(m.settings, "openai_api_key", ""):
                    m.OpenAIProvider().generate_text("sys", "user", 256)
                mock_cls.assert_not_called()
            finally:
                m._httpx_client_cls = original

    def test_openai_provider_factory(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "openai"}):
            import backend.app.services.llm_provider as m
            self.assertIsInstance(m.get_llm_provider(), m.OpenAIProvider)


class FallbackLLMProviderTests(unittest.TestCase):
    def test_returns_primary_result_when_primary_succeeds(self):
        import backend.app.services.llm_provider as m
        primary = MagicMock()
        primary.generate_text.return_value = "primary result"
        fallback = MagicMock()
        provider = m.FallbackLLMProvider(primary, fallback)
        result = provider.generate_text("sys", "user", 256)
        self.assertEqual(result, "primary result")
        fallback.generate_text.assert_not_called()

    def test_falls_back_when_primary_returns_none(self):
        import backend.app.services.llm_provider as m
        primary = MagicMock()
        primary.generate_text.return_value = None
        fallback = MagicMock()
        fallback.generate_text.return_value = "fallback result"
        provider = m.FallbackLLMProvider(primary, fallback)
        result = provider.generate_text("sys", "user", 256)
        self.assertEqual(result, "fallback result")
        fallback.generate_text.assert_called_once()

    def test_returns_none_when_both_fail(self):
        import backend.app.services.llm_provider as m
        primary = MagicMock()
        primary.generate_text.return_value = None
        fallback = MagicMock()
        fallback.generate_text.return_value = None
        provider = m.FallbackLLMProvider(primary, fallback)
        result = provider.generate_text("sys", "user", 256)
        self.assertIsNone(result)


class ProviderRouterTests(unittest.TestCase):
    def test_signal_explanation_routes_to_openai_primary(self):
        import backend.app.services.llm_provider as m
        provider = m.get_llm_provider_for_task("signal_explanation")
        self.assertIsInstance(provider, m.FallbackLLMProvider)
        self.assertIsInstance(provider._primary, m.OpenAIProvider)
        self.assertIsInstance(provider._fallback, m.GroqProvider)

    def test_mapping_disambiguation_routes_to_groq_primary(self):
        import backend.app.services.llm_provider as m
        provider = m.get_llm_provider_for_task("mapping_disambiguation")
        self.assertIsInstance(provider, m.FallbackLLMProvider)
        self.assertIsInstance(provider._primary, m.GroqProvider)
        self.assertIsInstance(provider._fallback, m.OpenAIProvider)

    def test_structured_tagging_routes_to_openai_primary(self):
        import backend.app.services.llm_provider as m
        provider = m.get_llm_provider_for_task("structured_tagging")
        self.assertIsInstance(provider, m.FallbackLLMProvider)
        self.assertIsInstance(provider._primary, m.OpenAIProvider)
        self.assertIsInstance(provider._fallback, m.GroqProvider)

    def test_unknown_task_type_falls_back_to_anthropic_and_logs(self):
        import backend.app.services.llm_provider as m
        with self.assertLogs("backend.app.services.llm_provider", level="WARNING"):
            provider = m.get_llm_provider_for_task("nonexistent_task")
        self.assertIsInstance(provider, m.AnthropicProvider)


class AiMapperFallbackTests(unittest.TestCase):
    def test_map_batch_returns_pending_results_when_provider_returns_none(self):
        import importlib
        from backend.app.ingestion.matcher import ai_mapper
        importlib.reload(ai_mapper)
        none_provider = MagicMock()
        none_provider.generate_text.return_value = None
        with patch(
            "backend.app.ingestion.matcher.ai_mapper.get_llm_provider",
            return_value=none_provider,
        ):
            results = ai_mapper.map_batch(["Charizard VMAX PSA 10", "Pikachu Alt Art"])
            self.assertEqual(len(results), 2)
            self.assertTrue(all(r.status == "pending" for r in results))
