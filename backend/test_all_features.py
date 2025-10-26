#!/usr/bin/env python3
"""
Comprehensive test script for Homebound backend
Tests both local and production environments
"""

import asyncio
import json
import sys
from datetime import datetime, timedelta
import httpx

# Configuration
LOCAL_BASE_URL = "http://127.0.0.1:8001"
PROD_BASE_URL = "https://homebound.onrender.com"

# Test email - use your real email to receive notifications
TEST_EMAIL = "test@example.com"  # Change this to your email
TEST_PHONE = "+15551234567"  # Change this to your phone number


class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def print_header(text):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}")
    print(f" {text}")
    print(f"{'='*60}{Colors.RESET}")


def print_success(text):
    print(f"{Colors.GREEN}✓ {text}{Colors.RESET}")


def print_error(text):
    print(f"{Colors.RED}✗ {text}{Colors.RESET}")


def print_info(text):
    print(f"{Colors.YELLOW}ℹ {text}{Colors.RESET}")


async def test_health(client, env_name):
    """Test health endpoint"""
    print(f"\n{Colors.BOLD}Testing Health Endpoint ({env_name}):{Colors.RESET}")
    try:
        response = await client.get("/health")
        if response.status_code == 200:
            print_success(f"Health check passed: {response.json()}")
            return True
        else:
            print_error(f"Health check failed: {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Health check error: {e}")
        return False


async def test_auth_flow(client, env_name):
    """Test complete authentication flow"""
    print(f"\n{Colors.BOLD}Testing Authentication Flow ({env_name}):{Colors.RESET}")

    # Step 1: Request magic link
    print_info("Requesting magic link...")
    try:
        response = await client.post(
            "/api/v1/auth/request-magic-link",
            json={"email": TEST_EMAIL}
        )
        if response.status_code == 200:
            print_success(f"Magic link requested: {response.json()}")
        else:
            print_error(f"Magic link request failed: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print_error(f"Magic link request error: {e}")
        return None

    # Step 2: Get the code (dev only)
    if "127.0.0.1" in str(client.base_url) or "localhost" in str(client.base_url):
        print_info("Getting magic code from dev endpoint...")
        try:
            response = await client.get(
                f"/api/v1/auth/_dev/peek-code?email={TEST_EMAIL}"
            )
            if response.status_code == 200:
                data = response.json()
                code = data.get("code")
                if code:
                    print_success(f"Magic code retrieved: {code}")
                else:
                    print_error("No code found")
                    return None
            else:
                print_error(f"Failed to get code: {response.status_code}")
                return None
        except Exception as e:
            print_error(f"Get code error: {e}")
            return None

        # Step 3: Verify code
        print_info("Verifying magic code...")
        try:
            response = await client.post(
                "/api/v1/auth/verify",
                json={"email": TEST_EMAIL, "code": code}
            )
            if response.status_code == 200:
                tokens = response.json()
                print_success(f"Authentication successful!")
                print_info(f"Access token: {tokens['access'][:50]}...")
                return tokens["access"]
            else:
                print_error(f"Verification failed: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            print_error(f"Verification error: {e}")
            return None
    else:
        print_info("Production environment - check your email for the code")
        print_info("Enter the 6-digit code from your email: ")
        code = input().strip()

        # Verify code
        print_info("Verifying magic code...")
        try:
            response = await client.post(
                "/api/v1/auth/verify",
                json={"email": TEST_EMAIL, "code": code}
            )
            if response.status_code == 200:
                tokens = response.json()
                print_success(f"Authentication successful!")
                return tokens["access"]
            else:
                print_error(f"Verification failed: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            print_error(f"Verification error: {e}")
            return None


async def test_plan_creation(client, token, env_name):
    """Test plan creation and timeline"""
    print(f"\n{Colors.BOLD}Testing Plan Creation ({env_name}):{Colors.RESET}")

    if not token:
        print_error("No authentication token - skipping plan tests")
        return None

    # Create a plan
    print_info("Creating a test plan...")
    now = datetime.utcnow()
    plan_data = {
        "title": f"Test Plan - {env_name}",
        "start_at": now.isoformat(),
        "eta_at": (now + timedelta(hours=2)).isoformat(),
        "grace_minutes": 30,
        "location_text": "Test Location",
        "notes": "This is a test plan",
        "contacts": [
            {
                "name": "Emergency Contact",
                "phone": TEST_PHONE,
                "email": TEST_EMAIL,
                "notify_on_overdue": True
            }
        ]
    }

    headers = {"Authorization": f"Bearer {token}"}

    try:
        response = await client.post(
            "/api/v1/plans",
            json=plan_data,
            headers=headers
        )
        if response.status_code == 200:
            plan = response.json()
            print_success(f"Plan created: ID={plan['id']}, Title={plan['title']}")
            print_info(f"Check-in token: {plan['checkin_token'][:20]}...")
            print_info(f"Check-out token: {plan['checkout_token'][:20]}...")

            # Get timeline
            print_info("Fetching timeline...")
            timeline_response = await client.get(
                f"/api/v1/plans/{plan['id']}/timeline",
                headers=headers
            )
            if timeline_response.status_code == 200:
                timeline = timeline_response.json()
                print_success(f"Timeline has {len(timeline['events'])} events")
                for event in timeline['events']:
                    print_info(f"  - {event['kind']} at {event['at']}")

            return plan
        else:
            print_error(f"Plan creation failed: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print_error(f"Plan creation error: {e}")
        return None


async def test_checkin_checkout(client, plan, env_name):
    """Test check-in and check-out"""
    print(f"\n{Colors.BOLD}Testing Check-in/Check-out ({env_name}):{Colors.RESET}")

    if not plan:
        print_error("No plan available - skipping check-in/out tests")
        return

    # Test check-in
    print_info("Testing check-in...")
    try:
        checkin_url = f"/t/{plan['checkin_token']}/checkin"
        response = await client.get(checkin_url)
        if response.status_code == 200:
            print_success(f"Check-in successful: {response.json()}")
        else:
            print_error(f"Check-in failed: {response.status_code}")
    except Exception as e:
        print_error(f"Check-in error: {e}")

    # Test check-out
    print_info("Testing check-out...")
    try:
        checkout_url = f"/t/{plan['checkout_token']}/checkout"
        response = await client.get(checkout_url)
        if response.status_code == 200:
            print_success(f"Check-out successful: {response.json()}")
        else:
            print_error(f"Check-out failed: {response.status_code}")
    except Exception as e:
        print_error(f"Check-out error: {e}")


async def test_environment(base_url, env_name):
    """Test a complete environment"""
    print_header(f"Testing {env_name} Environment")
    print_info(f"Base URL: {base_url}")

    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        # Run all tests
        health_ok = await test_health(client, env_name)

        if health_ok:
            token = await test_auth_flow(client, env_name)
            plan = await test_plan_creation(client, token, env_name)
            await test_checkin_checkout(client, plan, env_name)
        else:
            print_error("Skipping further tests due to health check failure")


async def main():
    """Main test runner"""
    print_header("HOMEBOUND COMPREHENSIVE TESTING")
    print_info(f"Test Email: {TEST_EMAIL}")
    print_info(f"Test Phone: {TEST_PHONE}")
    print_info("Make sure to update these with your real contact info!")

    # Test local environment
    await test_environment(LOCAL_BASE_URL, "LOCAL")

    # Ask if user wants to test production
    print(f"\n{Colors.BOLD}{Colors.YELLOW}Do you want to test PRODUCTION? (y/n): {Colors.RESET}")
    if input().strip().lower() == 'y':
        await test_environment(PROD_BASE_URL, "PRODUCTION")

    print_header("TESTING COMPLETE")
    print_info("Check your email and phone for notifications!")
    print_info("Monitor the scheduler logs to see overdue checks running")


if __name__ == "__main__":
    # First, update these with your real details
    print(f"{Colors.BOLD}{Colors.YELLOW}Before running tests:{Colors.RESET}")
    print("1. Update TEST_EMAIL with your real email")
    print("2. Update TEST_PHONE with your real phone number")
    print(f"\n{Colors.BOLD}Current values:{Colors.RESET}")
    print(f"  Email: {TEST_EMAIL}")
    print(f"  Phone: {TEST_PHONE}")
    print(f"\n{Colors.BOLD}Continue with these values? (y/n): {Colors.RESET}")

    if input().strip().lower() == 'y':
        asyncio.run(main())
    else:
        print("Please edit the script and update TEST_EMAIL and TEST_PHONE")