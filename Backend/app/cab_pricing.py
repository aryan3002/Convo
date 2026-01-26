"""
Cab Pricing Engine

Pure functions for calculating cab fare prices.
All functions are stateless and easily testable.

Pricing Formula:
    raw_price = distance_miles * per_mile_rate * vehicle_multiplier
    final_price = max(minimum_fare, ceil(raw_price / rounding_step) * rounding_step)

Example:
    18.2 miles * $4/mile = $72.80
    Round up to nearest $5 = $75.00
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_UP, ROUND_CEILING
from typing import Optional

from .cab_models import CabPricingRule, CabVehicleType


@dataclass
class PriceCalculation:
    """Result of a price calculation with full breakdown."""
    
    # Input values
    distance_miles: Decimal
    per_mile_rate: Decimal
    vehicle_multiplier: Decimal
    rounding_step: Decimal
    minimum_fare: Decimal
    
    # Calculated values
    base_price: Decimal       # distance * rate
    adjusted_price: Decimal   # base_price * vehicle_multiplier
    raw_price: Decimal        # adjusted_price (before rounding)
    final_price: Decimal      # after rounding and minimum fare
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "distance_miles": float(self.distance_miles),
            "per_mile_rate": float(self.per_mile_rate),
            "vehicle_multiplier": float(self.vehicle_multiplier),
            "rounding_step": float(self.rounding_step),
            "minimum_fare": float(self.minimum_fare),
            "base_price": float(self.base_price),
            "adjusted_price": float(self.adjusted_price),
            "raw_price": float(self.raw_price),
            "final_price": float(self.final_price),
        }


def round_up_to_step(value: Decimal, step: Decimal) -> Decimal:
    """
    Round a value UP to the nearest multiple of step.
    
    Examples:
        round_up_to_step(72.8, 5) = 75
        round_up_to_step(70.0, 5) = 70  # Already a multiple
        round_up_to_step(70.01, 5) = 75  # Slightly over
    
    Args:
        value: The value to round
        step: The rounding step (e.g., 5 for nearest $5)
    
    Returns:
        Value rounded up to nearest multiple of step
    """
    if step <= 0:
        return value
    
    # Calculate number of steps (rounded up)
    # Use ceiling division: ceil(value / step) * step
    remainder = value % step
    
    if remainder == 0:
        return value
    
    return value - remainder + step


def calculate_cab_price(
    distance_miles: Decimal | float,
    per_mile_rate: Decimal | float,
    rounding_step: Decimal | float = Decimal("5.00"),
    minimum_fare: Decimal | float = Decimal("0.00"),
    vehicle_multiplier: Decimal | float = Decimal("1.0"),
) -> PriceCalculation:
    """
    Calculate cab fare price with rounding and minimum fare.
    
    Formula:
        base_price = distance_miles * per_mile_rate
        adjusted_price = base_price * vehicle_multiplier
        raw_price = adjusted_price
        final_price = max(minimum_fare, round_up_to_step(raw_price, rounding_step))
    
    Args:
        distance_miles: Trip distance in miles
        per_mile_rate: Rate per mile (e.g., 4.00)
        rounding_step: Round final price up to nearest multiple (e.g., 5.00)
        minimum_fare: Minimum fare regardless of distance (e.g., 15.00)
        vehicle_multiplier: Multiplier for vehicle type (e.g., 1.3 for SUV)
    
    Returns:
        PriceCalculation with full breakdown
    
    Examples:
        >>> result = calculate_cab_price(18.2, 4.0, 5.0, 0.0)
        >>> result.raw_price
        Decimal('72.80')
        >>> result.final_price
        Decimal('75.00')
        
        >>> result = calculate_cab_price(5.0, 4.0, 5.0, 25.0)  # Short trip with minimum
        >>> result.raw_price
        Decimal('20.00')
        >>> result.final_price
        Decimal('25.00')  # Minimum fare applied
    """
    # Convert all inputs to Decimal for precision
    distance = Decimal(str(distance_miles))
    rate = Decimal(str(per_mile_rate))
    step = Decimal(str(rounding_step))
    minimum = Decimal(str(minimum_fare))
    multiplier = Decimal(str(vehicle_multiplier))
    
    # Calculate base price (distance * rate)
    base_price = (distance * rate).quantize(Decimal("0.01"), rounding=ROUND_UP)
    
    # Apply vehicle multiplier
    adjusted_price = (base_price * multiplier).quantize(Decimal("0.01"), rounding=ROUND_UP)
    
    # Raw price is the adjusted price before rounding
    raw_price = adjusted_price
    
    # Apply rounding step (round up to nearest multiple)
    if step > 0:
        rounded_price = round_up_to_step(raw_price, step)
    else:
        rounded_price = raw_price
    
    # Apply minimum fare
    final_price = max(minimum, rounded_price)
    
    return PriceCalculation(
        distance_miles=distance,
        per_mile_rate=rate,
        vehicle_multiplier=multiplier,
        rounding_step=step,
        minimum_fare=minimum,
        base_price=base_price,
        adjusted_price=adjusted_price,
        raw_price=raw_price,
        final_price=final_price,
    )


def calculate_cab_price_from_rule(
    distance_miles: Decimal | float,
    pricing_rule: CabPricingRule,
    vehicle_type: CabVehicleType = CabVehicleType.SEDAN_4,
) -> PriceCalculation:
    """
    Calculate cab fare using a CabPricingRule object.
    
    Convenience wrapper that extracts values from the pricing rule.
    
    Args:
        distance_miles: Trip distance in miles
        pricing_rule: CabPricingRule with pricing configuration
        vehicle_type: Vehicle type for multiplier lookup
    
    Returns:
        PriceCalculation with full breakdown
    """
    vehicle_multiplier = pricing_rule.get_vehicle_multiplier(vehicle_type)
    
    return calculate_cab_price(
        distance_miles=distance_miles,
        per_mile_rate=pricing_rule.per_mile_rate,
        rounding_step=pricing_rule.rounding_step,
        minimum_fare=pricing_rule.minimum_fare,
        vehicle_multiplier=vehicle_multiplier,
    )


# ============================================================================
# PRICING SNAPSHOT HELPERS
# ============================================================================

def create_pricing_snapshot(
    pricing_rule: CabPricingRule,
    vehicle_type: CabVehicleType,
) -> dict:
    """
    Create a snapshot of pricing parameters for storing with a booking.
    
    This snapshot is stored with the booking to ensure the quoted price
    can be verified later, even if the pricing rules change.
    
    Args:
        pricing_rule: Current pricing rule
        vehicle_type: Selected vehicle type
    
    Returns:
        Dict with snapshot values for storing in cab_booking
    """
    return {
        "per_mile_rate_snapshot": pricing_rule.per_mile_rate,
        "rounding_step_snapshot": pricing_rule.rounding_step,
        "minimum_fare_snapshot": pricing_rule.minimum_fare,
        "vehicle_multiplier_snapshot": pricing_rule.get_vehicle_multiplier(vehicle_type),
    }
