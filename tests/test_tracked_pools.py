from unittest import TestCase

from backend.app.core.tracked_pools import (
    BASE_SET_POOL_KEY,
    DEFAULT_HIGH_ACTIVITY_V2_LABEL,
    DEFAULT_HIGH_ACTIVITY_TRIAL_LABEL,
    HIGH_ACTIVITY_V2_POOL_KEY,
    HIGH_ACTIVITY_TRIAL_POOL_KEY,
    PRIMARY_SMART_OBSERVATION_POOL_KEY,
    TRIAL_POOL_KEY,
    get_primary_smart_observation_pool,
    get_tracked_pokemon_pools,
)


class TrackedPokemonPoolsTests(TestCase):
    def test_active_pools_contain_base_set_trial_and_v2(self):
        """High-Activity Trial (33-card) is retired; only 3 active pools expected by default."""
        pools = get_tracked_pokemon_pools()
        pool_by_key = {pool.key: pool for pool in pools}

        self.assertIn(BASE_SET_POOL_KEY, pool_by_key, "Base Set pool must be present")
        self.assertIn(TRIAL_POOL_KEY, pool_by_key, "SV151 Trial pool must be present")
        self.assertIn(HIGH_ACTIVITY_V2_POOL_KEY, pool_by_key, "High-Activity v2 pool must be present")

        # High-Activity Trial (33-card sv8pt5-148..180) is retired — not in default ingestion.
        self.assertNotIn(
            HIGH_ACTIVITY_TRIAL_POOL_KEY,
            pool_by_key,
            "High-Activity Trial pool should be retired (empty card IDs by default)",
        )

    def test_high_activity_v2_pool_has_expected_shape(self):
        pools = get_tracked_pokemon_pools()
        pool_by_key = {pool.key: pool for pool in pools}

        high_activity_v2_pool = pool_by_key[HIGH_ACTIVITY_V2_POOL_KEY]
        self.assertEqual(high_activity_v2_pool.label, DEFAULT_HIGH_ACTIVITY_V2_LABEL)
        self.assertEqual(len(high_activity_v2_pool.card_ids), 13)
        self.assertEqual(high_activity_v2_pool.card_ids[0], "sv8pt5-149")
        self.assertEqual(high_activity_v2_pool.card_ids[-1], "sv8pt5-179")
        self.assertEqual(
            high_activity_v2_pool.external_id_patterns[-2:],
            ("pokemontcg:sv8pt5-168:%", "pokemontcg:sv8pt5-179:%"),
        )

    def test_primary_smart_observation_pool_points_to_high_activity_v2(self):
        pool = get_primary_smart_observation_pool()

        self.assertIsNotNone(pool)
        self.assertEqual(pool.key, PRIMARY_SMART_OBSERVATION_POOL_KEY)
        self.assertEqual(pool.key, HIGH_ACTIVITY_V2_POOL_KEY)
        self.assertEqual(pool.label, DEFAULT_HIGH_ACTIVITY_V2_LABEL)

    def test_high_activity_trial_pool_key_constant_still_exported(self):
        """The constant remains for diagnostics comparisons against historical data."""
        self.assertEqual(HIGH_ACTIVITY_TRIAL_POOL_KEY, "high_activity_trial_pool")
        self.assertEqual(DEFAULT_HIGH_ACTIVITY_TRIAL_LABEL, "High-Activity Trial")
