"""Shared controlled risk levels for stored predictions and alert severity."""

from enum import Enum

from sqlalchemy import Enum as SqlEnum


class RiskLevel(str, Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


risk_level_enum = SqlEnum(
    RiskLevel, name="risk_level", create_constraint=True, validate_strings=True,
)
