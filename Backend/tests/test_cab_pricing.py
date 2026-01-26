"""
Tests for cab_pricing module.

Run with: pytest tests/test_cab_pricing.py -v
"""

import pytest
from decimal import Decimal

from app.cab_pricing import (
    calculate_cab_price,
    round_up_to_step,
    PriceCalculation,
)


# ============================================================================
# ROUND UP TO STEP TESTS
# ============================================================================

class TestRoundUpToStep:
    """Tests for the round_up_to_step function."""
    
    def test_round_up_basic(self):
        """72.8 rounds up to 75 with step 5."""
        result = round_up_to_step(Decimal("72.8"), Decimal("5"))
        assert result == Decimal("75")
    
    def test_exact_multiple_stays_same(self):
        """70.0 stays at 70 with step 5 (already a multiple)."""
        result = round_up_to_step(Decimal("70.0"), Decimal("5"))
        assert result == Decimal("70")
    
    def test_slightly_over_rounds_up(self):
        """70.01 rounds up to 75 with step 5."""
        result = round_up_to_step(Decimal("70.01"), Decimal("5"))
        assert result == Decimal("75")
    
    def test_slightly_under_rounds_up(self):
        """69.99 rounds up to 70 with step 5."""
        result = round_up_to_step(Decimal("69.99"), Decimal("5"))
        assert result == Decimal("70")
    
    def test_small_value(self):
        """3.5 rounds up to 5 with step 5."""
        result = round_up_to_step(Decimal("3.5"), Decimal("5"))
        assert result == Decimal("5")
    
    def test_step_10(self):
        """73 rounds up to 80 with step 10."""
        result = round_up_to_step(Decimal("73"), Decimal("10"))
        assert result == Decimal("80")
    
    def test_step_1(self):
        """5.25 rounds up to 6 with step 1."""
        result = round_up_to_step(Decimal("5.25"), Decimal("1"))
        assert result == Decimal("6")
    
    def test_zero_step_returns_value(self):
        """Zero step returns original value."""
        result = round_up_to_step(Decimal("72.8"), Decimal("0"))
        assert result == Decimal("72.8")
    
    def test_negative_step_returns_value(self):
        """Negative step returns original value."""
        result = round_up_to_step(Decimal("72.8"), Decimal("-5"))
        assert result == Decimal("72.8")


# ============================================================================
# CALCULATE CAB PRICE TESTS
# ============================================================================

class TestCalculateCabPrice:
    """Tests for the calculate_cab_price function."""
    
    def test_basic_calculation(self):
        """18.2 miles * $4/mile = $72.80, rounded to $75."""
        result = calculate_cab_price(
            distance_miles=18.2,
            per_mile_rate=4.0,
            rounding_step=5.0,
            minimum_fare=0.0,
        )
        
        assert result.distance_miles == Decimal("18.2")
        assert result.per_mile_rate == Decimal("4.0")
        assert result.raw_price == Decimal("72.80")
        assert result.final_price == Decimal("75")
    
    def test_exact_multiple_no_change(self):
        """17.5 miles * $4/mile = $70.00, stays at $70."""
        result = calculate_cab_price(
            distance_miles=17.5,
            per_mile_rate=4.0,
            rounding_step=5.0,
            minimum_fare=0.0,
        )
        
        assert result.raw_price == Decimal("70.00")
        assert result.final_price == Decimal("70")
    
    def test_minimum_fare_applied(self):
        """Short trip: 5 miles * $4 = $20, but minimum is $25."""
        result = calculate_cab_price(
            distance_miles=5.0,
            per_mile_rate=4.0,
            rounding_step=5.0,
            minimum_fare=25.0,
        )
        
        assert result.raw_price == Decimal("20.00")
        assert result.final_price == Decimal("25")  # Minimum applied
    
    def test_minimum_fare_not_needed(self):
        """Long trip exceeds minimum fare."""
        result = calculate_cab_price(
            distance_miles=20.0,
            per_mile_rate=4.0,
            rounding_step=5.0,
            minimum_fare=25.0,
        )
        
        assert result.raw_price == Decimal("80.00")
        assert result.final_price == Decimal("80")  # Minimum not needed
    
    def test_vehicle_multiplier_suv(self):
        """SUV multiplier: 18.2 * $4 * 1.3 = $94.64, rounded to $95."""
        result = calculate_cab_price(
            distance_miles=18.2,
            per_mile_rate=4.0,
            rounding_step=5.0,
            minimum_fare=0.0,
            vehicle_multiplier=1.3,
        )
        
        assert result.vehicle_multiplier == Decimal("1.3")
        # 18.2 * 4 = 72.8, * 1.3 = 94.64
        assert result.adjusted_price == Decimal("94.64")
        assert result.final_price == Decimal("95")
    
    def test_vehicle_multiplier_van(self):
        """Van multiplier: 10 * $4 * 1.5 = $60."""
        result = calculate_cab_price(
            distance_miles=10.0,
            per_mile_rate=4.0,
            rounding_step=5.0,
            minimum_fare=0.0,
            vehicle_multiplier=1.5,
        )
        
        # 10 * 4 = 40, * 1.5 = 60
        assert result.adjusted_price == Decimal("60.00")
        assert result.final_price == Decimal("60")  # Already multiple of 5
    
    def test_zero_distance(self):
        """Zero distance with minimum fare."""
        result = calculate_cab_price(
            distance_miles=0.0,
            per_mile_rate=4.0,
            rounding_step=5.0,
            minimum_fare=15.0,
        )
        
        assert result.raw_price == Decimal("0.00")
        assert result.final_price == Decimal("15")  # Minimum applied
    
    def test_decimal_precision(self):
        """Test decimal precision with complex values."""
        result = calculate_cab_price(
            distance_miles=Decimal("12.345"),
            per_mile_rate=Decimal("3.99"),
            rounding_step=Decimal("5.00"),
            minimum_fare=Decimal("0.00"),
        )
        
        # 12.345 * 3.99 = 49.2565... -> rounds to 49.26 for raw
        # Rounded up to nearest 5 = 50
        assert result.final_price == Decimal("50")
    
    def test_no_rounding_step(self):
        """With zero rounding step, no rounding applied."""
        result = calculate_cab_price(
            distance_miles=18.2,
            per_mile_rate=4.0,
            rounding_step=0.0,
            minimum_fare=0.0,
        )
        
        assert result.raw_price == Decimal("72.80")
        assert result.final_price == Decimal("72.80")
    
    def test_small_rounding_step(self):
        """$1 rounding step: 72.80 rounds to 73."""
        result = calculate_cab_price(
            distance_miles=18.2,
            per_mile_rate=4.0,
            rounding_step=1.0,
            minimum_fare=0.0,
        )
        
        assert result.raw_price == Decimal("72.80")
        assert result.final_price == Decimal("73")


# ============================================================================
# PRICE CALCULATION DATACLASS TESTS
# ============================================================================

class TestPriceCalculation:
    """Tests for PriceCalculation dataclass."""
    
    def test_to_dict(self):
        """Test serialization to dictionary."""
        result = calculate_cab_price(
            distance_miles=18.2,
            per_mile_rate=4.0,
            rounding_step=5.0,
            minimum_fare=0.0,
        )
        
        d = result.to_dict()
        
        assert d["distance_miles"] == 18.2
        assert d["per_mile_rate"] == 4.0
        assert d["rounding_step"] == 5.0
        assert d["minimum_fare"] == 0.0
        assert d["raw_price"] == 72.80
        assert d["final_price"] == 75.0


# ============================================================================
# EDGE CASE TESTS
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""
    
    def test_very_long_trip(self):
        """Test 100+ mile trip."""
        result = calculate_cab_price(
            distance_miles=150.0,
            per_mile_rate=4.0,
            rounding_step=5.0,
            minimum_fare=0.0,
        )
        
        assert result.raw_price == Decimal("600.00")
        assert result.final_price == Decimal("600")
    
    def test_very_short_trip(self):
        """Test 0.5 mile trip."""
        result = calculate_cab_price(
            distance_miles=0.5,
            per_mile_rate=4.0,
            rounding_step=5.0,
            minimum_fare=0.0,
        )
        
        assert result.raw_price == Decimal("2.00")
        assert result.final_price == Decimal("5")  # Rounds up to 5
    
    def test_high_per_mile_rate(self):
        """Test with higher per-mile rate."""
        result = calculate_cab_price(
            distance_miles=10.0,
            per_mile_rate=6.0,
            rounding_step=5.0,
            minimum_fare=0.0,
        )
        
        assert result.raw_price == Decimal("60.00")
        assert result.final_price == Decimal("60")
    
    def test_all_multipliers_combined(self):
        """Test minimum fare, vehicle multiplier, and rounding together."""
        result = calculate_cab_price(
            distance_miles=3.0,       # Short trip
            per_mile_rate=4.0,
            rounding_step=5.0,
            minimum_fare=30.0,        # High minimum
            vehicle_multiplier=1.3,   # SUV
        )
        
        # 3 * 4 = 12, * 1.3 = 15.6, rounds to 20
        # But minimum is 30
        assert result.adjusted_price == Decimal("15.60")
        assert result.final_price == Decimal("30")  # Minimum applied
