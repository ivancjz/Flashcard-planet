from enum import Enum


class AssetClass(str, Enum):
    TCG = "TCG"
    SEALED = "SEALED"
    SPORTS = "SPORTS"
    OTHER = "OTHER"


class AlertType(str, Enum):
    PRICE_UP_THRESHOLD = "PRICE_UP_THRESHOLD"
    PRICE_DOWN_THRESHOLD = "PRICE_DOWN_THRESHOLD"
    TARGET_PRICE_HIT = "TARGET_PRICE_HIT"
    PREDICT_SIGNAL_CHANGE = "PREDICT_SIGNAL_CHANGE"
    PREDICT_UP_PROBABILITY_ABOVE = "PREDICT_UP_PROBABILITY_ABOVE"
    PREDICT_DOWN_PROBABILITY_ABOVE = "PREDICT_DOWN_PROBABILITY_ABOVE"


class AlertDirection(str, Enum):
    ABOVE = "ABOVE"
    BELOW = "BELOW"


class SignalLabel(str, Enum):
    BREAKOUT = "BREAKOUT"
    MOVE = "MOVE"
    WATCH = "WATCH"
    IDLE = "IDLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class AccessTier(str, Enum):
    FREE = "free"
    PLUS = "plus"
    PRO  = "pro"


class CatalystEventType(str, Enum):
    INFLUENCER = "INFLUENCER"
    SUPPLY = "SUPPLY"
    TOURNAMENT = "TOURNAMENT"
    RELEASE = "RELEASE"
    REPRINT = "REPRINT"
    PRICE_CHANGE = "PRICE_CHANGE"
    ANNIVERSARY = "ANNIVERSARY"
    COLLABORATION = "COLLABORATION"
    LIMITED_PRODUCT = "LIMITED_PRODUCT"
    POLICY = "POLICY"
    SOCIAL_TREND = "SOCIAL_TREND"

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            normalized = value.strip().upper()
            for member in cls:
                if member.value == normalized:
                    return member
        return None
