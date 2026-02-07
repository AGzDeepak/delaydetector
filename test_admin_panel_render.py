#!/usr/bin/env python
"""Test admin panel rendering"""

from app import app, init_db

# Initialize fresh database
init_db()

# Test admin panel route
client = app.test_client()

# Login as admin
print('Step 1: Login as admin...')
response = client.post('/login', data={
    'username': 'admin',
    'password': 'password'
}, follow_redirects=True)
print(f'  Status: {response.status_code}')

# Access admin panel
print('\nStep 2: Access admin panel...')
response = client.get('/admin')
print(f'  Status: {response.status_code}')

# Check if template renders correctly
if response.status_code == 200:
    content = response.data.decode('utf-8')
    
    # Check for raw template variables
    if '{{ admin_data' in content:
        print('  ⚠️  WARNING: Template variables not rendered!')
        print('  Found: {{ admin_data')
    else:
        print('  ✓ Template variables properly rendered')
    
    # Check for stat values
    if 'Total Users' in content:
        print('  ✓ Admin panel content loaded')
    
    # Check for rendered numbers
    if 'stat-value' in content:
        # Extract stat values
        import re
        stat_values = re.findall(r'<p class="stat-value">([^<]+)</p>', content)
        if stat_values:
            print(f'  ✓ Stat values found: {stat_values}')
        else:
            print('  Could not extract stat values')

print('\n✅ Admin panel test complete!')
