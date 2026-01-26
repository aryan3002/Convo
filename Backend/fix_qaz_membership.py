"""
Quick fix script to add missing shop_members entry for qaz shop.
Run this to fix the "Access denied" error.
"""
import asyncio
from sqlalchemy import select
from app.core.db import AsyncSessionLocal
from app.models import Shop, ShopMember, ShopMemberRole

async def fix_membership():
    async with AsyncSessionLocal() as session:
        # Find the qaz shop
        result = await session.execute(
            select(Shop).where(Shop.slug == "qaz")
        )
        shop = result.scalar_one_or_none()
        
        if not shop:
            print("❌ Shop 'qaz' not found")
            return
        
        print(f"✓ Found shop: id={shop.id}, slug={shop.slug}, name={shop.name}")
        
        # Check if there's already a shop_members entry
        result = await session.execute(
            select(ShopMember).where(ShopMember.shop_id == shop.id)
        )
        existing_members = result.scalars().all()
        
        if existing_members:
            print(f"✓ Shop already has {len(existing_members)} member(s):")
            for member in existing_members:
                print(f"  - user_id={member.user_id}, role={member.role}")
            return
        
        # Need to get the user_id from localStorage
        print("\n⚠️  No shop members found!")
        print("Please provide the owner's user_id (from localStorage.getItem('owner_user_id')):")
        user_id = input("user_id: ").strip()
        
        if not user_id:
            print("❌ No user_id provided")
            return
        
        # Create the shop_members entry
        member = ShopMember(
            shop_id=shop.id,
            user_id=user_id,
            role=ShopMemberRole.OWNER.value
        )
        session.add(member)
        await session.commit()
        
        print(f"\n✅ Successfully added {user_id} as OWNER of shop '{shop.slug}'")
        print("You should now be able to access /s/qaz/owner/cab/setup")

if __name__ == "__main__":
    asyncio.run(fix_membership())
