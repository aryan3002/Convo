"""
Initialize cab services for a shop.

Creates CabOwner and CabPricingRule records for a shop.
"""

import asyncio
import sys
from sqlalchemy import select
from app.core.db import get_session
from app.models import Shop
from app.cab_models import CabOwner, CabPricingRule


async def init_cab_services(shop_slug: str):
    """Initialize cab services for a shop."""
    async for session in get_session():
        # Find shop
        result = await session.execute(
            select(Shop).where(Shop.slug == shop_slug)
        )
        shop = result.scalar_one_or_none()
        
        if not shop:
            print(f"❌ Shop '{shop_slug}' not found")
            return
        
        print(f"Found shop: {shop.name} (id={shop.id}, slug={shop.slug})")
        
        # Check if CabOwner already exists
        result = await session.execute(
            select(CabOwner).where(CabOwner.shop_id == shop.id)
        )
        existing_owner = result.scalar_one_or_none()
        
        if existing_owner:
            print(f"✅ Cab services already enabled for {shop.name}")
            print(f"   Business Name: {existing_owner.business_name}")
        else:
            # Create CabOwner
            cab_owner = CabOwner(
                shop_id=shop.id,
                business_name=f"{shop.name} Cab Services",
                email=None,
                phone=None,
                is_active=True,
            )
            session.add(cab_owner)
            await session.flush()
            print(f"✅ Created CabOwner for {shop.name}")
        
        # Check if CabPricingRule exists
        result = await session.execute(
            select(CabPricingRule).where(CabPricingRule.shop_id == shop.id)
        )
        existing_pricing = result.scalar_one_or_none()
        
        if existing_pricing:
            print(f"✅ Pricing rule already exists")
            print(f"   Base rate: ${existing_pricing.base_rate_per_mile}/mile")
        else:
            # Create default pricing rule
            pricing_rule = CabPricingRule(
                shop_id=shop.id,
                base_rate_per_mile=2.50,  # $2.50 per mile
                minimum_fare=10.00,       # $10 minimum
                sedan_multiplier=1.0,     # Base rate
                suv_multiplier=1.3,       # 30% more
                van_multiplier=1.5,       # 50% more
                price_round_step=5.00,    # Round to nearest $5
            )
            session.add(pricing_rule)
            print(f"✅ Created default pricing rule")
            print(f"   Base rate: $2.50/mile")
            print(f"   Minimum fare: $10")
            print(f"   Sedan: 1.0x, SUV: 1.3x, Van: 1.5x")
        
        await session.commit()
        print(f"\n🎉 Cab services ready for {shop.name}!")
        print(f"   Visit: /s/{shop.slug}/owner/cab")
        break


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/init_cab_services.py <shop_slug>")
        print("Example: python scripts/init_cab_services.py popo")
        sys.exit(1)
    
    shop_slug = sys.argv[1]
    asyncio.run(init_cab_services(shop_slug))
