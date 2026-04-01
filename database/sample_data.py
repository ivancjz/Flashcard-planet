from datetime import datetime, timedelta, timezone
from decimal import Decimal

ASSETS = [
    {
        "asset_class": "TCG",
        "category": "Pokemon",
        "name": "Pikachu",
        "set_name": "Base Set",
        "card_number": "58/102",
        "year": 1999,
        "language": "EN",
        "variant": "Unlimited",
        "grade_company": None,
        "grade_score": None,
        "external_id": "pokemon-pikachu-base-58-102-unlimited",
    },
    {
        "asset_class": "TCG",
        "category": "Pokemon",
        "name": "Charizard",
        "set_name": "Base Set",
        "card_number": "4/102",
        "year": 1999,
        "language": "EN",
        "variant": "Unlimited",
        "grade_company": "PSA",
        "grade_score": 9.0,
        "external_id": "pokemon-charizard-base-4-102-psa9",
    },
    {
        "asset_class": "SPORTS",
        "category": "Basketball",
        "name": "LeBron James Rookie",
        "set_name": "Topps Chrome",
        "card_number": "111",
        "year": 2003,
        "language": "EN",
        "variant": "Base",
        "grade_company": "BGS",
        "grade_score": 9.5,
        "external_id": "sports-lebron-topps-chrome-111-bgs95",
    },
]

now = datetime.now(timezone.utc).replace(microsecond=0)

PRICE_HISTORY = {
    "pokemon-pikachu-base-58-102-unlimited": [
        {"price": Decimal("12.00"), "captured_at": now - timedelta(days=2)},
        {"price": Decimal("13.50"), "captured_at": now - timedelta(days=1)},
    ],
    "pokemon-charizard-base-4-102-psa9": [
        {"price": Decimal("950.00"), "captured_at": now - timedelta(days=2)},
        {"price": Decimal("1025.00"), "captured_at": now - timedelta(days=1)},
    ],
    "sports-lebron-topps-chrome-111-bgs95": [
        {"price": Decimal("1800.00"), "captured_at": now - timedelta(days=2)},
        {"price": Decimal("1750.00"), "captured_at": now - timedelta(days=1)},
    ],
}
