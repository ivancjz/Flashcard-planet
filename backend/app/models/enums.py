from enum import Enum


class AssetClass(str, Enum):
    TCG = "TCG"
    SPORTS = "SPORTS"
    OTHER = "OTHER"


class AlertType(str, Enum):
    PRICE_UP_THRESHOLD = "PRICE_UP_THRESHOLD"
    PRICE_DOWN_THRESHOLD = "PRICE_DOWN_THRESHOLD"
    TARGET_PRICE_HIT = "TARGET_PRICE_HIT"


class AlertDirection(str, Enum):
    ABOVE = "ABOVE"
    BELOW = "BELOW"
