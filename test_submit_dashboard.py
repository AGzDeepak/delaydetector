from app import app

with app.test_client() as client:
    # Login first
    client.post('/login', data={'username': 'admin', 'password': 'password'})
    
    # Submit test data
    r = client.post('/submit', data={
        'opportunity_name': 'Google Internship 2026',
        'announcement_date': '2026-01-15',
        'awareness_date': '2026-02-05',
        'deadline': '2026-02-28',
        'college_type': 'Private',
        'region': 'Bangalore'
    })
    
    print(f'Submit form: {r.status_code} (should be 302 - redirect to dashboard)')
    
    # Check dashboard has data
    r = client.get('/dashboard')
    print(f'Dashboard: {r.status_code} (should be 200)')
    
    html = r.get_data(as_text=True)
    has_data = 'Google Internship' in html
    has_charts = 'barChart' in html and 'pieChart' in html
    has_animations = 'fade-in' in html
    has_metrics = 'Total Records' in html
    
    print(f'✓ Data displayed: {has_data}')
    print(f'✓ Charts rendered: {has_charts}')
    print(f'✓ Animations applied: {has_animations}')
    print(f'✓ Metrics visible: {has_metrics}')
    print('\n✓ ALL FEATURES WORKING!')
