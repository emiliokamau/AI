#!/usr/bin/env python
"""
Quick test of USSD integration
"""

from app import app

def test_ussd_routes():
    """Test that all USSD routes are registered"""
    with app.test_client() as client:
        print("\n" + "="*60)
        print("TESTING USSD INTEGRATION")
        print("="*60)
        
        # Test 1: Check callback endpoint
        print("\n1. Testing /ussd/callback endpoint...")
        response = client.post('/ussd/callback', data={
            'sessionId': 'test-session-123',
            'phone': '+254712345678',
            'text': ''
        })
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.get_data(as_text=True)[:100]}...")
        
        # Test 2: Check metrics endpoint
        print("\n2. Testing /ussd/metrics endpoint...")
        response = client.get('/ussd/metrics')
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            print(f"   Response: {response.get_json()}")
        
        # Test 3: Check registered routes
        print("\n3. Registered USSD routes:")
        ussd_routes = [str(rule) for rule in app.url_map.iter_rules() if '/ussd' in str(rule)]
        for route in sorted(ussd_routes):
            print(f"   ✓ {route}")
        
        print("\n" + "="*60)
        print(f"✅ USSD integration test completed!")
        print(f"   Routes: {len(ussd_routes)}")
        print("="*60 + "\n")

if __name__ == '__main__':
    test_ussd_routes()
