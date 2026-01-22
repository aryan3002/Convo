from datetime import time

from sqlalchemy import select

from .core.config import get_settings
from .models import Service, Shop, Stylist


settings = get_settings()


async def seed_initial_data(session):
    result = await session.execute(select(Shop).where(Shop.name == settings.default_shop_name))
    shop = result.scalar_one_or_none()

    if not shop:
        # Generate slug from shop name
        slug = settings.default_shop_name.lower().replace(" ", "-").replace("'", "")
        shop = Shop(
            name=settings.default_shop_name,
            slug=slug,
            timezone="America/Phoenix"
        )
        session.add(shop)
        await session.flush()

    # Seed services if missing
    result = await session.execute(select(Service).where(Service.shop_id == shop.id))
    services = result.scalars().all()
    if not services:
        session.add_all(
            [
                Service(
                    shop_id=shop.id,
                    name="Men's Haircut",
                    duration_minutes=30,
                    price_cents=3500,
                ),
                Service(
                    shop_id=shop.id,
                    name="Women's Haircut",
                    duration_minutes=45,
                    price_cents=5500,
                ),
                Service(
                    shop_id=shop.id,
                    name="Beard Trim",
                    duration_minutes=15,
                    price_cents=2000,
                ),
                Service(
                    shop_id=shop.id,
                    name="Hair Color",
                    duration_minutes=90,
                    price_cents=12000,
                ),
            ]
        )

    result = await session.execute(select(Stylist).where(Stylist.shop_id == shop.id))
    stylists = result.scalars().all()
    if not stylists:
        session.add_all(
            [
                Stylist(
                    shop_id=shop.id,
                    name="Alex",
                    work_start=time(10, 0),
                    work_end=time(18, 0),
                    active=True,
                ),
                Stylist(
                    shop_id=shop.id,
                    name="Jamie",
                    work_start=time(11, 0),
                    work_end=time(19, 0),
                    active=True,
                ),
            ]
        )

    await session.commit()
