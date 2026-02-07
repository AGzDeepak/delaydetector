#!/usr/bin/env python
"""Test admin add user feature"""

from app import app, init_db
import sqlite3

def test_admin_add_user():
    init_db()
    client = app.test_client()
    
    # First, login as admin
    print('Step 1: Login as admin...')
    response = client.post('/login', data={
        'username': 'admin',
        'password': 'password'
    }, follow_redirects=True)
    print(f'  Status: {response.status_code}')
    
    # Now test adding a user through the admin form
    print('\nStep 2: Add new user via admin panel...')
    with client.session_transaction() as sess:
        sess['username'] = 'admin'
        sess['is_admin'] = True
    
    response = client.post('/admin/add-user', data={
        'username': 'testuser123',
        'email': 'test@example.com',
        'password': 'password123',
        'role': 'user'
    }, follow_redirects=True)
    print(f'  Status: {response.status_code}')
    
    # Verify user was created
    print('\nStep 3: Verify user was created in database...')
    db = sqlite3.connect('data.db')
    db.row_factory = sqlite3.Row
    user = db.execute('SELECT * FROM users WHERE username = ?', ('testuser123',)).fetchone()
    if user:
        print(f'  ✓ User created successfully!')
        print(f'    Username: {user["username"]}')
        print(f'    Email: {user["email"]}')
        print(f'    Role: {user["role"]}')
        print(f'    Created: {user["created_at"]}')
    else:
        print('  ✗ User not found')
    
    # Test adding an admin user
    print('\nStep 4: Add new ADMIN user...')
    response = client.post('/admin/add-user', data={
        'username': 'newadmin',
        'email': 'admin@example.com',
        'password': 'securepass99',
        'role': 'admin'
    }, follow_redirects=True)
    print(f'  Status: {response.status_code}')
    
    # Verify admin user was created
    admin_user = db.execute('SELECT * FROM users WHERE username = ?', ('newadmin',)).fetchone()
    if admin_user:
        print(f'  ✓ Admin user created successfully!')
        print(f'    Username: {admin_user["username"]}')
        print(f'    Role: {admin_user["role"]}')
    else:
        print('  ✗ Admin user not found')
    
    # Test password validation
    print('\nStep 5: Test password validation (should fail)...')
    response = client.post('/admin/add-user', data={
        'username': 'shortpass',
        'password': '123'  # Too short
    }, follow_redirects=True)
    print(f'  Status: {response.status_code}')
    
    # Test duplicate username prevention
    print('\nStep 6: Test duplicate username prevention...')
    response = client.post('/admin/add-user', data={
        'username': 'testuser123',  # Already exists
        'password': 'newpassword'
    }, follow_redirects=True)
    print(f'  Status: {response.status_code}')
    
    # List all users
    print('\nStep 7: List all users in database...')
    users = db.execute('SELECT id, username, role FROM users ORDER BY id').fetchall()
    print(f'  Total users: {len(users)}')
    for user in users:
        print(f'    - {user["username"]} ({user["role"]})')
    
    db.close()
    print('\n✅ All tests completed!')

if __name__ == '__main__':
    test_admin_add_user()
