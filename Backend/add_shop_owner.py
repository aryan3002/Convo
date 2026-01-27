#!/usr/bin/env python3
"""
Quick script to add a user as OWNER to a shop.

Usage:
    python add_shop_owner.py <shop_slug> <clerk_user_id>

Example:
    python add_shop_owner.py radhe-radhe-rides user_2abc123xyz
"""

import asyncio
import sys
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models import Shop, ShopMember, ShopMemberRole
from app.core.config import get_settings


async def add_owner(shop_slug: str, user_id: str):
    """Add a user as OWNER to a shop."""
    
    # Get database URL from settings
    settings = get_settings()
    database_url = settings.database_url
    engine = create_async_engine(database_url, echo=True)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        async with session.begin():
            # Find the shop
            result = await session.execute(
                select(Shop).where(Shop.slug == shop_slug)
            )
            shop = result.scalar_one_or_none()
            
            if not shop:
                print(f"❌ Shop '{shop_slug}' not found!")
                return False
            
            print(f"✅ Found shop: {shop.name} (ID: {shop.id})")
            
            # Check if member already exists
            result = await session.execute(
                select(ShopMember).where(
                    ShopMember.shop_id == shop.id,
                    ShopMember.user_id == user_id
                )
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                print(f"⚠️  User {user_id} is already a member with role: {existing.role}")
                if existing.role != ShopMemberRole.OWNER.value:
                    print(f"🔧 Updating role to OWNER...")
                    existing.role = ShopMemberRole.OWNER.value
                    await session.flush()
                    print(f"✅ Updated role to OWNER")
                return True
            
            # Create new shop_member record
            member = ShopMember(
                shop_id=shop.id,
                user_id=user_id,
                role=ShopMemberRole.OWNER.value
            )
            session.add(member)
            await session.flush()
            
            print(f"✅ Added {user_id} as OWNER of shop {shop.name}")
            return True
    
    await engine.dispose()


async def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    
    shop_slug = sys.argv[1]
    user_id = sys.argv[2]
    
    print(f"Adding user '{user_id}' as OWNER to shop '{shop_slug}'...")
    success = await add_owner(shop_slug, user_id)
    
    if success:
        print("\n✅ Done! You should now be able to access the shop.")
    else:
        print("\n❌ Failed to add user.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
