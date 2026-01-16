#!/usr/bin/env python3
"""
Demonstration of how test mocking works.
Run this to see what tests are actually doing.
"""
import asyncio
from unittest.mock import patch, Mock, AsyncMock, call


async def demonstrate_mocking():
    """Show how mocking intercepts calls."""

    print("=" * 70)
    print("DEMONSTRATION: How Test Mocking Works")
    print("=" * 70)
    print()

    # ========================================================================
    # Part 1: Without Mocking (Would touch real services)
    # ========================================================================
    print("📍 Part 1: WITHOUT MOCKING (commented out for safety)")
    print("-" * 70)
    print("If we ran this without mocks:")
    print("  from src.integrations.supabase import supabase_client")
    print("  user = supabase_client.get_user_by_phone('+1234567890')")
    print("  → Would query REAL PostgreSQL database")
    print("  → Would return real user or None")
    print()

    # ========================================================================
    # Part 2: WITH Mocking (Safe - no real calls)
    # ========================================================================
    print("📍 Part 2: WITH MOCKING (safe - no real calls)")
    print("-" * 70)

    # Set up mocks
    with patch("src.integrations.supabase.supabase_client") as mock_supabase:
        # Configure mock to return fake data
        fake_user = {
            "id": "user_test_123",
            "whatsapp_number": "+1234567890",
            "name": "Test User",
            "language": "fr"
        }
        mock_supabase.get_user_by_phone = Mock(return_value=fake_user)
        mock_supabase.save_message = AsyncMock(return_value=True)

        # Now import (gets the mocked version)
        from src.integrations.supabase import supabase_client

        # Make a call
        print("Calling: supabase_client.get_user_by_phone('+1234567890')")
        user = supabase_client.get_user_by_phone("+1234567890")

        print(f"✅ Returned: {user}")
        print(f"✅ Is it a mock? {isinstance(supabase_client, Mock)}")
        print(f"✅ Did it touch real database? NO! (intercepted by mock)")
        print()

        # Make another call
        print("Calling: await supabase_client.save_message(...)")
        result = await mock_supabase.save_message(
            user_id="user_test_123",
            role="user",
            content="Update task"
        )

        print(f"✅ Returned: {result}")
        print(f"✅ Was message saved to database? NO! (fake success)")
        print()

        # Check what was called
        print("📊 Mock Call History:")
        print(f"   get_user_by_phone called? {mock_supabase.get_user_by_phone.called}")
        print(f"   get_user_by_phone call count: {mock_supabase.get_user_by_phone.call_count}")
        print(f"   get_user_by_phone called with: {mock_supabase.get_user_by_phone.call_args}")
        print()
        print(f"   save_message called? {mock_supabase.save_message.called}")
        print(f"   save_message call count: {mock_supabase.save_message.call_count}")
        print(f"   save_message called with: {mock_supabase.save_message.call_args}")
        print()

    # ========================================================================
    # Part 3: What Tests Verify
    # ========================================================================
    print("📍 Part 3: WHAT TESTS ACTUALLY VERIFY")
    print("-" * 70)

    with patch("src.integrations.twilio.twilio_client") as mock_twilio, \
         patch("src.integrations.supabase.supabase_client") as mock_supabase:

        # Set up mocks
        mock_twilio.send_message = AsyncMock(return_value="SM_mock_123")
        mock_supabase.get_user_by_phone = Mock(return_value={
            "id": "user_123",
            "name": "Test",
            "language": "fr"
        })

        # Import services
        from src.integrations.twilio import twilio_client
        from src.integrations.supabase import supabase_client

        # Simulate what code does
        print("Simulating code execution:")
        print("  1. Look up user")
        user = supabase_client.get_user_by_phone("+1234567890")
        print(f"     ✅ Got user: {user['name']}")

        print("  2. Send response message")
        await twilio_client.send_message("+1234567890", "Bonjour!")
        print(f"     ✅ Message sent (mock)")

        print()
        print("Tests verify:")
        print(f"  ✅ User lookup was attempted: {mock_supabase.get_user_by_phone.called}")
        print(f"  ✅ Message send was attempted: {mock_twilio.send_message.called}")
        print(f"  ✅ Correct phone number used: {mock_twilio.send_message.call_args[0][0]}")
        print(f"  ✅ Correct message sent: {mock_twilio.send_message.call_args[0][1]}")
        print()

    # ========================================================================
    # Part 4: Benefits Summary
    # ========================================================================
    print("=" * 70)
    print("✅ BENEFITS OF MOCKED TESTS")
    print("=" * 70)
    print("1. ⚡ FAST: No network calls, no database I/O")
    print("2. 💰 FREE: No API costs (Claude tokens, Twilio messages)")
    print("3. 🎯 RELIABLE: No network issues, 100% reproducible")
    print("4. 🔒 SAFE: No production data affected")
    print("5. ✅ VERIFIES: Code logic, function calls, error handling")
    print()
    print("❌ WHAT THEY DON'T TEST:")
    print("1. Real database schema compatibility")
    print("2. Actual API response formats")
    print("3. Network latency and timeouts")
    print("4. Real data edge cases")
    print()
    print("💡 SOLUTION: Use BOTH mocked and real integration tests!")
    print("   - Mocked: Every commit (fast, cheap)")
    print("   - Real: Before releases (slow, thorough)")
    print("=" * 70)


if __name__ == "__main__":
    print()
    asyncio.run(demonstrate_mocking())
    print()
    print("✅ Demo complete! This is how all 60 tests work.")
    print()
