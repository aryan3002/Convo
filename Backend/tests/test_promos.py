from datetime import datetime, timezone

from app.main import (
    PromoCreateRequest,
    PromoEligibilityContext,
    PromoImpressionSnapshot,
    evaluate_promo_candidate,
    select_best_promo,
    validate_promo_payload,
)
from app.models import Promo, PromoDiscountType, PromoTriggerPoint, PromoType


def make_context(**overrides):
    now = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
    data = {
        "now_utc": now,
        "local_now": now,
        "local_day": "2025-01-01",
        "local_weekday": 2,
        "trigger_point": PromoTriggerPoint.AT_CHAT_START,
        "selected_service_id": None,
        "selected_service_price_cents": None,
        "email": "guest@example.com",
        "session_id": "session-1",
        "has_confirmed_booking": False,
    }
    data.update(overrides)
    return PromoEligibilityContext(**data)


def make_impressions(**overrides):
    data = {
        "session_shown": set(),
        "session_daily_shown": set(),
        "email_daily_shown": set(),
        "email_counts": {},
    }
    data.update(overrides)
    return PromoImpressionSnapshot(**data)


def make_promo(**overrides):
    promo = Promo(
        id=overrides.pop("id", 1),
        shop_id=1,
        type=overrides.pop("type", PromoType.DAILY_PROMO),
        trigger_point=overrides.pop("trigger_point", PromoTriggerPoint.AT_CHAT_START),
        service_id=overrides.pop("service_id", None),
        discount_type=overrides.pop("discount_type", PromoDiscountType.PERCENT),
        discount_value=overrides.pop("discount_value", 10),
        constraints_json=overrides.pop("constraints_json", None),
        custom_copy=overrides.pop("custom_copy", None),
        start_at_utc=overrides.pop("start_at_utc", None),
        end_at_utc=overrides.pop("end_at_utc", None),
        active=overrides.pop("active", True),
        priority=overrides.pop("priority", 0),
    )
    for key, value in overrides.items():
        setattr(promo, key, value)
    return promo


def test_validate_service_combo_requires_service_id_and_trigger():
    # When combo_service_ids is not provided, we get combo_service_ids_required error
    payload = PromoCreateRequest(
        type=PromoType.SERVICE_COMBO_PROMO,
        trigger_point=PromoTriggerPoint.AT_CHAT_START,
        service_id=None,
        discount_type=PromoDiscountType.PERCENT,
        discount_value=10,
    )
    errors = validate_promo_payload(payload, has_services=True, service_exists=False)
    assert "combo_service_ids_required" in errors
    assert "trigger_point_invalid_for_service_combo" in errors


def test_validate_seasonal_requires_window():
    payload = PromoCreateRequest(
        type=PromoType.SEASONAL_PROMO,
        trigger_point=PromoTriggerPoint.AT_CHAT_START,
        discount_type=PromoDiscountType.PERCENT,
        discount_value=15,
    )
    errors = validate_promo_payload(payload, has_services=True, service_exists=True)
    assert "seasonal_window_required" in errors


def test_daily_promo_respects_daily_limit():
    promo = make_promo(type=PromoType.DAILY_PROMO)
    context = make_context()
    impressions = make_impressions(email_daily_shown={promo.id})
    eligible, reasons = evaluate_promo_candidate(promo, context, impressions)
    assert not eligible
    assert "daily_limit_reached" in reasons


def test_first_user_promo_requires_no_booking():
    promo = make_promo(type=PromoType.FIRST_USER_PROMO)
    context = make_context(has_confirmed_booking=True)
    impressions = make_impressions()
    eligible, reasons = evaluate_promo_candidate(promo, context, impressions)
    assert not eligible
    assert "not_first_time" in reasons


def test_service_combo_requires_matching_service():
    promo = make_promo(
        type=PromoType.SERVICE_COMBO_PROMO,
        trigger_point=PromoTriggerPoint.AFTER_SERVICE_SELECTED,
        service_id=5,
    )
    context = make_context(selected_service_id=3, trigger_point=PromoTriggerPoint.AFTER_SERVICE_SELECTED)
    impressions = make_impressions()
    eligible, reasons = evaluate_promo_candidate(promo, context, impressions)
    assert not eligible
    assert "service_mismatch" in reasons


def test_select_best_promo_prefers_priority_then_specificity():
    daily = make_promo(id=1, type=PromoType.DAILY_PROMO, priority=1)
    combo = make_promo(
        id=2,
        type=PromoType.SERVICE_COMBO_PROMO,
        trigger_point=PromoTriggerPoint.AFTER_SERVICE_SELECTED,
        priority=1,
    )
    context = make_context()
    selected = select_best_promo([daily, combo], context)
    assert selected.id == combo.id


def test_combo_promo_with_combo_service_ids():
    """Test that combo promo matches when user selects one of the combo services."""
    promo = make_promo(
        type=PromoType.SERVICE_COMBO_PROMO,
        trigger_point=PromoTriggerPoint.AFTER_SERVICE_SELECTED,
        service_id=10,  # First combo service
        constraints_json={"combo_service_ids": [10, 20]},
    )
    # User selected service 10 (one of the combo pair)
    context = make_context(
        selected_service_id=10,
        trigger_point=PromoTriggerPoint.AFTER_SERVICE_SELECTED,
    )
    impressions = make_impressions()
    eligible, reasons = evaluate_promo_candidate(promo, context, impressions)
    assert eligible, f"Expected eligible but got reasons: {reasons}"


def test_combo_promo_with_combo_service_ids_other_service():
    """Test that combo promo matches when user selects the other combo service."""
    promo = make_promo(
        type=PromoType.SERVICE_COMBO_PROMO,
        trigger_point=PromoTriggerPoint.AFTER_SERVICE_SELECTED,
        service_id=10,
        constraints_json={"combo_service_ids": [10, 20]},
    )
    # User selected service 20 (the other service in the combo)
    context = make_context(
        selected_service_id=20,
        trigger_point=PromoTriggerPoint.AFTER_SERVICE_SELECTED,
    )
    impressions = make_impressions()
    eligible, reasons = evaluate_promo_candidate(promo, context, impressions)
    assert eligible, f"Expected eligible but got reasons: {reasons}"


def test_combo_promo_rejects_non_combo_service():
    """Test that combo promo is rejected if neither combo service is selected."""
    promo = make_promo(
        type=PromoType.SERVICE_COMBO_PROMO,
        trigger_point=PromoTriggerPoint.AFTER_SERVICE_SELECTED,
        service_id=10,
        constraints_json={"combo_service_ids": [10, 20]},
    )
    # User selected service 30 (not in the combo)
    context = make_context(
        selected_service_id=30,
        trigger_point=PromoTriggerPoint.AFTER_SERVICE_SELECTED,
    )
    impressions = make_impressions()
    eligible, reasons = evaluate_promo_candidate(promo, context, impressions)
    assert not eligible
    assert "service_mismatch" in reasons


def test_best_promo_selects_highest_discount_value():
    """Test that best promo selection prefers highest discount when price known."""
    promo_10 = make_promo(id=1, discount_type=PromoDiscountType.PERCENT, discount_value=10, priority=0)
    promo_25 = make_promo(id=2, discount_type=PromoDiscountType.PERCENT, discount_value=25, priority=0)
    context = make_context(selected_service_price_cents=10000)  # $100 service
    selected = select_best_promo([promo_10, promo_25], context)
    # 25% of $100 = $25 > 10% of $100 = $10
    assert selected.id == promo_25.id
