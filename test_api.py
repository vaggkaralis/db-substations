#!/usr/bin/env python
"""
Quick test script to verify Flask API works before deployment
Run this locally to test all endpoints
"""
import requests
import json
import time

# Configuration
LOCAL_URL = 'http://localhost:5000/api'
CLOUD_URL = 'https://YOUR_RAILWAY_URL.up.railway.app/api'  # Update after deployment

def test_health(base_url):
    """Test health endpoint"""
    print(f"\n🏥 Testing health check at {base_url}...")
    try:
        response = requests.get(f'{base_url}/health')
        if response.status_code == 200:
            print("✅ Server is healthy")
            return True
        else:
            print(f"❌ Server returned {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

def test_get_substations(base_url):
    """Test getting substations"""
    print(f"\n📋 Testing GET /substations...")
    try:
        response = requests.get(f'{base_url}/substations')
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Got {len(data.get('data', []))} substations")
            return True
        else:
            print(f"❌ Got status {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

def test_add_substation(base_url):
    """Test adding a substation"""
    print(f"\n➕ Testing POST /substations...")
    try:
        payload = {
            'name': f'Test Sub {int(time.time())}',
            'location': 'Test Location',
            'adoption_date': '2024-01-01'
        }
        response = requests.post(f'{base_url}/substations', json=payload)
        if response.status_code == 201:
            data = response.json()
            sub_id = data.get('id')
            print(f"✅ Added substation with ID {sub_id}")
            return sub_id
        else:
            print(f"❌ Got status {response.status_code}: {response.text}")
            return None
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return None

def test_add_element(base_url, sub_id):
    """Test adding an element"""
    print(f"\n➕ Testing POST /elements...")
    try:
        payload = {
            'substation_id': sub_id,
            'element_type': 'Διακόπτης Ισχύος',
            'name': f'Test Element {int(time.time())}',
            'serial_number': 'SN-001',
            'maintenance_date': '2024-01-15',
            'voltage_level': '20 KV',
            'manufacturer': 'Test Co',
            'type': 'Type A'
        }
        response = requests.post(f'{base_url}/elements', json=payload)
        if response.status_code == 201:
            data = response.json()
            elem_id = data.get('id')
            print(f"✅ Added element with ID {elem_id}")
            return elem_id
        else:
            print(f"❌ Got status {response.status_code}: {response.text}")
            return None
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return None

def test_get_elements(base_url, sub_id):
    """Test getting elements for a substation"""
    print(f"\n📋 Testing GET /elements?substation_id={sub_id}...")
    try:
        response = requests.get(f'{base_url}/elements?substation_id={sub_id}')
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Got {len(data.get('data', []))} elements")
            return True
        else:
            print(f"❌ Got status {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

def run_tests(base_url, name):
    """Run all tests"""
    print(f"\n{'='*60}")
    print(f"Testing {name}")
    print(f"{'='*60}")
    
    # Health check
    if not test_health(base_url):
        print(f"\n❌ Cannot reach server at {base_url}")
        return False
    
    # Get substations
    if not test_get_substations(base_url):
        return False
    
    # Add substation
    sub_id = test_add_substation(base_url)
    if not sub_id:
        return False
    
    # Add element
    elem_id = test_add_element(base_url, sub_id)
    if not elem_id:
        return False
    
    # Get elements
    if not test_get_elements(base_url, sub_id):
        return False
    
    print(f"\n✅ All tests passed for {name}!")
    return True

if __name__ == '__main__':
    print("\n🧪 DB Substations API Test Suite\n")
    
    # Test local server first
    print("Testing LOCAL server (make sure 'python api_server.py' is running)...")
    local_ok = run_tests(LOCAL_URL, "LOCAL SERVER")
    
    # Test cloud server (only if Railway URL is set)
    if 'YOUR_RAILWAY_URL' not in CLOUD_URL:
        print("\n\nTesting CLOUD server...")
        cloud_ok = run_tests(CLOUD_URL, "RAILWAY SERVER")
    
    print(f"\n{'='*60}")
    print("✅ Test suite complete!")
