from unittest import TestCase

from backend.app.core.tracked_pools import (
    BASE_SET_POOL_KEY,
    DEFAULT_HIGH_ACTIVITY_TRIAL_LABEL,
    HIGH_ACTIVITY_TRIAL_POOL_KEY,
    TRIAL_POOL_KEY,
    get_tracked_pokemon_pools,
)


class TrackedPokemonPoolsTests(TestCase):
    def test_high_activity_trial_pool_is_configured_with_expected_shape(self):
        pools = get_tracked_pokemon_pools()
        pool_by_key = {pool.key: pool for pool in pools}

        self.assertIn(BASE_SET_POOL_KEY, pool_by_key)
        self.assertIn(TRIAL_POOL_KEY, pool_by_key)
        self.assertIn(HIGH_ACTIVITY_TRIAL_POOL_KEY, pool_by_key)

        high_activity_pool = pool_by_key[HIGH_ACTIVITY_TRIAL_POOL_KEY]
        self.assertEqual(high_activity_pool.label, DEFAULT_HIGH_ACTIVITY_TRIAL_LABEL)
        self.assertEqual(len(high_activity_pool.card_ids), 33)
        self.assertEqual(high_activity_pool.card_prefix, "sv8pt5")
        self.assertEqual(high_activity_pool.card_ids[0], "sv8pt5-148")
        self.assertEqual(high_activity_pool.card_ids[-1], "sv8pt5-180")
