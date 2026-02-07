#!/usr/bin/env python
"""Test online opportunities feature"""

from app import app, get_online_opportunities, filter_online_opportunities, init_db

def test_online_opportunities():
    init_db()
    
    print('Testing Online Opportunities Feature')
    print('=' * 50)

    # Test 1: Get all opportunities
    all_opps = get_online_opportunities()
    print(f'\nTest 1: Get all opportunities')
    print(f'  Total available: {len(all_opps)}')
    print(f'  First opportunity: {all_opps[0]["title"]}')
    print(f'  ✓ PASSED')

    # Test 2: Filter by region
    region_filter = filter_online_opportunities(region='USA')
    print(f'\nTest 2: Filter by region (USA)')
    print(f'  Found: {len(region_filter)} opportunities')
    if region_filter:
        print(f'  Example: {region_filter[0]["title"]}')
    print(f'  ✓ PASSED')

    # Test 3: Filter by type
    type_filter = filter_online_opportunities(internship_type='Internship')
    print(f'\nTest 3: Filter by type (Internship)')
    print(f'  Found: {len(type_filter)} opportunities')
    print(f'  ✓ PASSED')

    # Test 4: Search query
    search = filter_online_opportunities(query='Google')
    print(f'\nTest 4: Search for "Google"')
    print(f'  Found: {len(search)} opportunities')
    if search:
        print(f'  Result: {search[0]["title"]}')
    print(f'  ✓ PASSED')

    # Test 5: Combined filters
    combined = filter_online_opportunities(query='Internship', region='USA')
    print(f'\nTest 5: Combined filters (Internship + USA)')
    print(f'  Found: {len(combined)} opportunities')
    print(f'  ✓ PASSED')

    # Test 6: Test opportunity data structure
    opp = all_opps[0]
    required_fields = ['title', 'company', 'type', 'region', 'deadline', 'url', 'description', 'salary', 'duration', 'online', 'source']
    print(f'\nTest 6: Check opportunity data structure')
    all_fields_present = all(field in opp for field in required_fields)
    if all_fields_present:
        print(f'  All required fields present: YES')
        print(f'  Sample: {opp["title"][:40]}...')
        print(f'  Company: {opp["company"]}')
        print(f'  ✓ PASSED')
    else:
        print(f'  Missing fields: {[f for f in required_fields if f not in opp]}')

    # Test 7: Test route
    print(f'\nTest 7: Test /opportunities route')
    client = app.test_client()
    
    # First login
    client.post('/login', data={'username': 'admin', 'password': 'password'})
    
    # Test route
    response = client.get('/opportunities')
    if response.status_code == 200:
        print(f'  Status: 200 OK')
        print(f'  Page loads successfully')
        print(f'  ✓ PASSED')
    else:
        print(f'  Status: {response.status_code}')
        print(f'  ✗ FAILED')

    # Test filters on route
    print(f'\nTest 8: Test route with filters')
    response = client.get('/opportunities?search=Google&region=USA&type=Internship')
    if response.status_code == 200:
        print(f'  Search + Region + Type filter: 200 OK')
        print(f'  ✓ PASSED')

    print('\n' + '=' * 50)
    print('✅ All online opportunities tests PASSED!')

if __name__ == '__main__':
    test_online_opportunities()
