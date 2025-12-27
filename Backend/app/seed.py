from sqlalchemy import select

from .core.config import get_settings
from .models import Service, Shop, Stylist


settings = get_settings()


async def seed_initial_data(session):
    result = await session.execute(select(Shop).where(Shop.name == settings.default_shop_name))
    shop = result.scalar_one_or_none()

    if not shop:
        shop = Shop(name=settings.default_shop_name)
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
                    name="Haircut",
                    duration_minutes=30,
                    price_cents=3500,
                ),
                Service(
                    shop_id=shop.id,
                    name="Beard Trim",
                    duration_minutes=30,
                    price_cents=2000,
                ),
                Service(
                    shop_id=shop.id,
                    name="Haircut + Beard",
                    duration_minutes=60,
                    price_cents=5000,
                ),
            ]
        )

    result = await session.execute(select(Stylist).where(Stylist.shop_id == shop.id))
    stylists = result.scalars().all()
    if not stylists:
        session.add_all(
            [
                Stylist(shop_id=shop.id, name="Alex", active=True),
                Stylist(shop_id=shop.id, name="Sam", active=True),
            ]
        )

    await session.commit()
