from unittest import TestCase

from backend.app.core.price_sources import (
    PROVIDER_1_SLOT,
    get_configured_price_providers,
    get_price_source_label,
    get_primary_price_source,
)


class PriceSourcesTests(TestCase):
    def test_default_provider_slot_configuration_exposes_provider_1(self):
        providers = get_configured_price_providers()

        self.assertEqual(len(providers), 1)
        self.assertEqual(providers[0].slot, PROVIDER_1_SLOT)
        self.assertEqual(providers[0].source, "pokemon_tcg_api")
        self.assertTrue(providers[0].is_primary)
        self.assertEqual(get_primary_price_source(), "pokemon_tcg_api")

    def test_price_source_label_uses_registry_and_safe_fallback(self):
        self.assertEqual(get_price_source_label("pokemon_tcg_api"), "Pokemon TCG API")
        self.assertEqual(get_price_source_label("future_provider"), "Future Provider")
