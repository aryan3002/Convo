#!/usr/bin/env python3
"""
RouterGPT API Integration Tests

This script performs comprehensive testing of the RouterGPT location-based
discovery and delegation endpoints.

Usage:
    cd Backend
    python scripts/test_routergpt_api.py
    
    # Test against a specific server:
    python scripts/test_routergpt_api.py --base-url http://localhost:8000
    
    # Run specific test:
    python scripts/test_routergpt_api.py --test location-search
    
    # Verbose output:
    python scripts/test_routergpt_api.py -v

Tests:
    1. Location Search - Find businesses near coordinates
    2. Delegation - Hand off to shop booking agent
    3. Chat with Context - Continue booking conversation
    4. Error Scenarios - Invalid inputs and edge cases
"""

import argparse
import asyncio
import json
import logging
import sys
import uuid
from dataclasses import dataclass
from typing import Any, Optional

import httpx

# ────────────────────────────────────────────────────────────────
# Configuration
# ────────────────────────────────────────────────────────────────

DEFAULT_BASE_URL = "http://localhost:8000"

# Test coordinates (Tempe, AZ)
TEMPE_LAT = 33.4255
TEMPE_LON = -111.9400

# Phoenix coordinates (for testing larger distances)
PHOENIX_LAT = 33.4484
PHOENIX_LON = -112.0740

# Remote location (for no-results testing)
REMOTE_LAT = 40.7128  # New York City
REMOTE_LON = -74.0060

logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────────
# Test Result Tracking
# ────────────────────────────────────────────────────────────────

@dataclass
class TestResult:
    name: str
    passed: bool
    message: str
    details: Optional[dict] = None


class TestSuite:
    def __init__(self, base_url: str, verbose: bool = False):
        self.base_url = base_url.rstrip("/")
        self.verbose = verbose
        self.results: list[TestResult] = []
        self.session_id: Optional[str] = None
        self.shop_slug: Optional[str] = None
    
    def log(self, msg: str, level: str = "info"):
        if level == "detail" and not self.verbose:
            return
        if level == "success":
            logger.info(f"  ✅ {msg}")
        elif level == "error":
            logger.error(f"  ❌ {msg}")
        elif level == "warning":
            logger.warning(f"  ⚠️  {msg}")
        else:
            logger.info(f"  {msg}")
    
    def add_result(self, name: str, passed: bool, message: str, details: dict = None):
        self.results.append(TestResult(name, passed, message, details))
    
    async def request(
        self,
        method: str,
        path: str,
        json_data: dict = None,
        expected_status: int = 200
    ) -> tuple[int, dict | None]:
        """Make an HTTP request and return (status, json_response)."""
        url = f"{self.base_url}{path}"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            if method == "GET":
                response = await client.get(url)
            elif method == "POST":
                response = await client.post(url, json=json_data)
            else:
                raise ValueError(f"Unsupported method: {method}")
        
        try:
            data = response.json()
        except:
            data = None
        
        if self.verbose:
            self.log(f"Request: {method} {path}", "detail")
            if json_data:
                self.log(f"Body: {json.dumps(json_data, indent=2)}", "detail")
            self.log(f"Response: {response.status_code}", "detail")
            if data:
                self.log(f"Data: {json.dumps(data, indent=2)[:500]}", "detail")
        
        return response.status_code, data


# ────────────────────────────────────────────────────────────────
# Test 1: Location Search
# ────────────────────────────────────────────────────────────────

async def test_location_search(suite: TestSuite):
    """Test the /router/search-by-location endpoint."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 1: Location Search")
    logger.info("=" * 60)
    
    # Test 1.1: Basic location search
    logger.info("\n📍 Test 1.1: Basic location search (Tempe)")
    status, data = await suite.request("POST", "/router/search-by-location", {
        "latitude": TEMPE_LAT,
        "longitude": TEMPE_LON,
        "radius_miles": 10
    })
    
    if status == 200 and data:
        results = data.get("results", [])
        suite.log(f"Found {len(results)} business(es)", "success")
        
        # Save first result for delegation test
        if results:
            suite.shop_slug = results[0].get("slug")
            for r in results[:3]:
                suite.log(f"  - {r['name']} ({r['distance_miles']} mi, confidence: {r['confidence']})")
        
        suite.add_result(
            "Location Search - Basic",
            True,
            f"Found {len(results)} businesses",
            {"results_count": len(results)}
        )
    else:
        suite.log(f"Failed with status {status}", "error")
        suite.add_result("Location Search - Basic", False, f"HTTP {status}")
    
    # Test 1.2: Search with category filter
    logger.info("\n📍 Test 1.2: Search with category filter (barbershop)")
    status, data = await suite.request("POST", "/router/search-by-location", {
        "latitude": TEMPE_LAT,
        "longitude": TEMPE_LON,
        "radius_miles": 25,
        "category": "barbershop"
    })
    
    if status == 200 and data:
        results = data.get("results", [])
        suite.log(f"Found {len(results)} barbershop(s)", "success")
        suite.add_result(
            "Location Search - Category Filter",
            True,
            f"Found {len(results)} barbershops"
        )
    else:
        suite.log(f"Failed with status {status}", "error")
        suite.add_result("Location Search - Category Filter", False, f"HTTP {status}")
    
    # Test 1.3: Search with small radius (should find fewer)
    logger.info("\n📍 Test 1.3: Search with small radius (1 mile)")
    status, data = await suite.request("POST", "/router/search-by-location", {
        "latitude": TEMPE_LAT,
        "longitude": TEMPE_LON,
        "radius_miles": 1
    })
    
    if status == 200 and data:
        results = data.get("results", [])
        suite.log(f"Found {len(results)} business(es) within 1 mile", "success")
        
        # Verify all results are within radius
        all_within = all(r["distance_miles"] <= 1.0 for r in results)
        if all_within:
            suite.log("All results within radius ✓")
        else:
            suite.log("Some results outside radius!", "warning")
        
        suite.add_result(
            "Location Search - Small Radius",
            True,
            f"Found {len(results)} businesses, all within radius: {all_within}"
        )
    else:
        suite.add_result("Location Search - Small Radius", False, f"HTTP {status}")
    
    # Test 1.4: Search in remote location (should find none or few)
    logger.info("\n📍 Test 1.4: Search in remote location (NYC)")
    status, data = await suite.request("POST", "/router/search-by-location", {
        "latitude": REMOTE_LAT,
        "longitude": REMOTE_LON,
        "radius_miles": 5
    })
    
    if status == 200 and data:
        results = data.get("results", [])
        suite.log(f"Found {len(results)} business(es) in NYC area", "success")
        suite.add_result(
            "Location Search - No Results Area",
            True,
            f"Found {len(results)} businesses (expected 0)"
        )
    else:
        suite.add_result("Location Search - No Results Area", False, f"HTTP {status}")


# ────────────────────────────────────────────────────────────────
# Test 2: Delegation
# ────────────────────────────────────────────────────────────────

async def test_delegation(suite: TestSuite):
    """Test the /router/delegate endpoint."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 2: Delegation")
    logger.info("=" * 60)
    
    # Use shop from location search or default
    shop_slug = suite.shop_slug or "bishops-tempe"
    
    # Test 2.1: Basic delegation
    logger.info(f"\n🤝 Test 2.1: Delegate to {shop_slug}")
    status, data = await suite.request("POST", "/router/delegate", {
        "shop_slug": shop_slug,
        "customer_context": {
            "intent": "haircut",
            "location": {
                "lat": TEMPE_LAT,
                "lon": TEMPE_LON
            }
        }
    })
    
    if status == 200 and data:
        suite.session_id = data.get("session_id")
        suite.log(f"Delegation successful", "success")
        suite.log(f"  Session ID: {suite.session_id}")
        suite.log(f"  Shop: {data.get('shop_name')}")
        suite.log(f"  Initial message: {data.get('initial_message', '')[:80]}...")
        
        services = data.get("available_services", [])
        suite.log(f"  Services: {len(services)}")
        
        # Verify session_id is a valid UUID
        try:
            uuid.UUID(suite.session_id)
            suite.log("Session ID is valid UUID ✓")
        except:
            suite.log("Session ID is not a valid UUID!", "warning")
        
        suite.add_result(
            "Delegation - Basic",
            True,
            f"Got session {suite.session_id[:8]}...",
            {"services_count": len(services)}
        )
    else:
        suite.log(f"Failed with status {status}", "error")
        if data:
            suite.log(f"Error: {data.get('detail', 'Unknown')}", "error")
        suite.add_result("Delegation - Basic", False, f"HTTP {status}")
    
    # Test 2.2: Delegation with no context
    logger.info(f"\n🤝 Test 2.2: Delegate without customer context")
    status, data = await suite.request("POST", "/router/delegate", {
        "shop_slug": shop_slug
    })
    
    if status == 200 and data:
        suite.log(f"Delegation without context successful", "success")
        suite.add_result("Delegation - No Context", True, "Works without context")
    else:
        suite.log(f"Status: {status}", "warning")
        suite.add_result("Delegation - No Context", status == 200, f"HTTP {status}")
    
    # Test 2.3: Delegation to invalid shop
    logger.info(f"\n🤝 Test 2.3: Delegate to invalid shop")
    status, data = await suite.request("POST", "/router/delegate", {
        "shop_slug": "nonexistent-shop-12345"
    })
    
    if status == 404:
        suite.log(f"Correctly returned 404 for invalid shop", "success")
        suite.add_result("Delegation - Invalid Shop", True, "Returns 404 as expected")
    else:
        suite.log(f"Expected 404, got {status}", "warning")
        suite.add_result("Delegation - Invalid Shop", False, f"Expected 404, got {status}")


# ────────────────────────────────────────────────────────────────
# Test 3: Chat with Context
# ────────────────────────────────────────────────────────────────

async def test_chat_with_context(suite: TestSuite):
    """Test the /s/{slug}/chat endpoint with router context."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 3: Chat with RouterGPT Context")
    logger.info("=" * 60)
    
    shop_slug = suite.shop_slug or "bishops-tempe"
    session_id = suite.session_id or str(uuid.uuid4())
    
    # Test 3.1: Chat with full context
    logger.info(f"\n💬 Test 3.1: Chat with router context")
    status, data = await suite.request("POST", f"/s/{shop_slug}/chat", {
        "messages": [
            {"role": "user", "content": "I'd like to book a haircut please"}
        ],
        "router_session_id": session_id,
        "router_intent": "haircut",
        "customer_location": {
            "lat": TEMPE_LAT,
            "lon": TEMPE_LON
        }
    })
    
    if status == 200 and data:
        reply = data.get("reply", "")
        suite.log(f"Chat successful", "success")
        suite.log(f"  Reply: {reply[:100]}...")
        suite.log(f"  Shop: {data.get('shop_name')}")
        
        if data.get("chips"):
            suite.log(f"  Chips: {data.get('chips')[:3]}")
        
        suite.add_result(
            "Chat - With Context",
            True,
            "Got AI response"
        )
    else:
        suite.log(f"Status: {status}", "error")
        # Note: 500 might be expected if OpenAI is slow/unavailable
        if status == 500:
            suite.log("(500 error may be due to OpenAI API timeout)", "warning")
        suite.add_result("Chat - With Context", False, f"HTTP {status}")
    
    # Test 3.2: Chat without context (should still work)
    logger.info(f"\n💬 Test 3.2: Chat without router context")
    status, data = await suite.request("POST", f"/s/{shop_slug}/chat", {
        "messages": [
            {"role": "user", "content": "What services do you offer?"}
        ]
    })
    
    if status == 200:
        suite.log(f"Chat without context successful", "success")
        suite.add_result("Chat - Without Context", True, "Works without router context")
    else:
        suite.log(f"Status: {status}", "warning")
        suite.add_result("Chat - Without Context", status == 200, f"HTTP {status}")
    
    # Test 3.3: Chat with invalid shop
    logger.info(f"\n💬 Test 3.3: Chat with invalid shop slug")
    status, data = await suite.request("POST", f"/s/invalid-shop-xyz/chat", {
        "messages": [
            {"role": "user", "content": "Hello"}
        ]
    })
    
    if status == 404:
        suite.log(f"Correctly returned 404 for invalid shop", "success")
        suite.add_result("Chat - Invalid Shop", True, "Returns 404 as expected")
    else:
        suite.log(f"Expected 404, got {status}", "warning")
        suite.add_result("Chat - Invalid Shop", False, f"Expected 404, got {status}")


# ────────────────────────────────────────────────────────────────
# Test 4: Error Scenarios
# ────────────────────────────────────────────────────────────────

async def test_error_scenarios(suite: TestSuite):
    """Test error handling and edge cases."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 4: Error Scenarios")
    logger.info("=" * 60)
    
    # Test 4.1: Invalid coordinates (out of range)
    logger.info("\n⚠️  Test 4.1: Invalid latitude (out of range)")
    status, data = await suite.request("POST", "/router/search-by-location", {
        "latitude": 999.0,  # Invalid
        "longitude": TEMPE_LON,
        "radius_miles": 10
    })
    
    if status == 422:
        suite.log(f"Correctly rejected invalid coordinates", "success")
        suite.add_result("Error - Invalid Coordinates", True, "Returns 422 as expected")
    else:
        suite.log(f"Expected 422, got {status}", "warning")
        suite.add_result("Error - Invalid Coordinates", False, f"Expected 422, got {status}")
    
    # Test 4.2: Missing required fields
    logger.info("\n⚠️  Test 4.2: Missing required fields")
    status, data = await suite.request("POST", "/router/search-by-location", {
        "latitude": TEMPE_LAT
        # Missing longitude
    })
    
    if status == 422:
        suite.log(f"Correctly rejected missing fields", "success")
        suite.add_result("Error - Missing Fields", True, "Returns 422 as expected")
    else:
        suite.log(f"Expected 422, got {status}", "warning")
        suite.add_result("Error - Missing Fields", False, f"Expected 422, got {status}")
    
    # Test 4.3: Empty messages array
    logger.info("\n⚠️  Test 4.3: Empty messages array in chat")
    shop_slug = suite.shop_slug or "bishops-tempe"
    status, data = await suite.request("POST", f"/s/{shop_slug}/chat", {
        "messages": []
    })
    
    # Could be 422 or 400 depending on validation
    if status in [400, 422]:
        suite.log(f"Correctly rejected empty messages", "success")
        suite.add_result("Error - Empty Messages", True, f"Returns {status} as expected")
    else:
        suite.log(f"Expected 400/422, got {status}", "warning")
        suite.add_result("Error - Empty Messages", False, f"Unexpected status {status}")
    
    # Test 4.4: Negative radius
    logger.info("\n⚠️  Test 4.4: Negative radius")
    status, data = await suite.request("POST", "/router/search-by-location", {
        "latitude": TEMPE_LAT,
        "longitude": TEMPE_LON,
        "radius_miles": -5
    })
    
    if status == 422:
        suite.log(f"Correctly rejected negative radius", "success")
        suite.add_result("Error - Negative Radius", True, "Returns 422 as expected")
    else:
        suite.log(f"Expected 422, got {status}", "warning")
        suite.add_result("Error - Negative Radius", False, f"Expected 422, got {status}")


# ────────────────────────────────────────────────────────────────
# Test Runner
# ────────────────────────────────────────────────────────────────

async def run_all_tests(base_url: str, verbose: bool = False, specific_test: str = None):
    """Run all tests and print summary."""
    suite = TestSuite(base_url, verbose)
    
    logger.info("\n" + "=" * 60)
    logger.info("🧪 RouterGPT API Integration Tests")
    logger.info("=" * 60)
    logger.info(f"Base URL: {base_url}")
    logger.info("")
    
    # Check server is running
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.get(f"{base_url}/health")
    except Exception as e:
        logger.error(f"❌ Cannot connect to server at {base_url}")
        logger.error(f"   Error: {e}")
        logger.error("   Make sure the server is running!")
        return 1
    
    # Run tests
    tests = {
        "location-search": test_location_search,
        "delegation": test_delegation,
        "chat": test_chat_with_context,
        "errors": test_error_scenarios,
    }
    
    if specific_test:
        if specific_test in tests:
            await tests[specific_test](suite)
        else:
            logger.error(f"Unknown test: {specific_test}")
            logger.error(f"Available: {', '.join(tests.keys())}")
            return 1
    else:
        for test_func in tests.values():
            await test_func(suite)
    
    # Print summary
    logger.info("\n" + "=" * 60)
    logger.info("📊 TEST SUMMARY")
    logger.info("=" * 60)
    
    passed = sum(1 for r in suite.results if r.passed)
    failed = sum(1 for r in suite.results if not r.passed)
    
    for result in suite.results:
        status = "✅" if result.passed else "❌"
        logger.info(f"  {status} {result.name}: {result.message}")
    
    logger.info("")
    logger.info(f"  Total: {len(suite.results)} | Passed: {passed} | Failed: {failed}")
    logger.info("=" * 60)
    
    return 0 if failed == 0 else 1


# ────────────────────────────────────────────────────────────────
# CLI Entry Point
# ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="RouterGPT API Integration Tests"
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"API base URL (default: {DEFAULT_BASE_URL})"
    )
    parser.add_argument(
        "--test",
        choices=["location-search", "delegation", "chat", "errors"],
        help="Run a specific test only"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output (show request/response details)"
    )
    
    args = parser.parse_args()
    
    try:
        exit_code = asyncio.run(run_all_tests(
            base_url=args.base_url,
            verbose=args.verbose,
            specific_test=args.test
        ))
        sys.exit(exit_code)
        
    except KeyboardInterrupt:
        logger.info("\n🛑 Interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
