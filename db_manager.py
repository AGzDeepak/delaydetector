#!/usr/bin/env python3
"""
Database Manager for Opportunity Inequality Tracker
Provides utilities to manage users, data, and audit logs
"""
import sqlite3
from pathlib import Path
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from tabulate import tabulate

DB_PATH = Path(__file__).parent / 'data.db'

def get_db():
    """Get database connection"""
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db

def list_users():
    """List all users in the system"""
    db = get_db()
    users = db.execute('SELECT id, username, created_at, updated_at FROM users ORDER BY id').fetchall()
    if not users:
        print("No users found.")
        return
    
    table_data = [[u['id'], u['username'], u['created_at'], u['updated_at']] for u in users]
    print(tabulate(table_data, headers=['ID', 'Username', 'Created', 'Updated'], tablefmt='grid'))
    db.close()

def create_user(username, password):
    """Create a new user"""
    db = get_db()
    try:
        db.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)',
                   (username, generate_password_hash(password)))
        db.commit()
        print(f"✓ User '{username}' created successfully")
    except sqlite3.IntegrityError:
        print(f"✗ Username '{username}' already exists")
    db.close()

def delete_user(user_id):
    """Delete a user and their related data"""
    db = get_db()
    user = db.execute('SELECT username FROM users WHERE id = ?', (user_id,)).fetchone()
    if not user:
        print(f"✗ User with ID {user_id} not found")
        return
    
    # Delete related records
    db.execute('DELETE FROM awareness_data WHERE user_id = ?', (user_id,))
    db.execute('DELETE FROM audit_log WHERE user_id = ?', (user_id,))
    db.execute('DELETE FROM users WHERE id = ?', (user_id,))
    db.commit()
    print(f"✓ User '{user['username']}' and all related data deleted")
    db.close()

def reset_password(user_id, new_password):
    """Reset a user's password"""
    db = get_db()
    user = db.execute('SELECT username FROM users WHERE id = ?', (user_id,)).fetchone()
    if not user:
        print(f"✗ User with ID {user_id} not found")
        return
    
    db.execute('UPDATE users SET password_hash = ? WHERE id = ?',
               (generate_password_hash(new_password), user_id))
    db.commit()
    print(f"✓ Password reset for user '{user['username']}'")
    db.close()

def list_awareness_data(user_id=None):
    """List awareness data, optionally filtered by user"""
    db = get_db()
    if user_id:
        rows = db.execute('''SELECT ad.*, u.username FROM awareness_data ad
                            LEFT JOIN users u ON ad.user_id = u.id
                            WHERE ad.user_id = ? ORDER BY ad.created_at DESC''', (user_id,)).fetchall()
    else:
        rows = db.execute('''SELECT ad.*, u.username FROM awareness_data ad
                            LEFT JOIN users u ON ad.user_id = u.id
                            ORDER BY ad.created_at DESC''').fetchall()
    
    if not rows:
        print("No awareness data found.")
        return
    
    table_data = [[r['username'], r['opportunity_name'], r['delay_days'], 
                   r['delay_category'], r['college_type'], r['region'], r['created_at']] 
                  for r in rows]
    print(tabulate(table_data, headers=['User', 'Opportunity', 'Delay (days)', 'Category', 
                                         'College', 'Region', 'Created'], tablefmt='grid'))
    db.close()

def get_statistics():
    """Get overall database statistics"""
    db = get_db()
    
    user_count = db.execute('SELECT COUNT(*) as c FROM users').fetchone()['c']
    data_count = db.execute('SELECT COUNT(*) as c FROM awareness_data').fetchone()['c']
    audit_count = db.execute('SELECT COUNT(*) as c FROM audit_log').fetchone()['c']
    
    avg_delay = db.execute('SELECT AVG(delay_days) as avg FROM awareness_data WHERE delay_days IS NOT NULL').fetchone()['avg']
    late_access = db.execute('SELECT COUNT(*) as c FROM awareness_data WHERE delay_category = "Late Access"').fetchone()['c']
    
    print("\n📊 Database Statistics:")
    print(f"  Total Users: {user_count}")
    print(f"  Total Submissions: {data_count}")
    print(f"  Audit Log Entries: {audit_count}")
    print(f"  Average Delay: {round(avg_delay, 2) if avg_delay else 'N/A'} days")
    print(f"  Late Access Count: {late_access}")
    late_percent = round((late_access / data_count * 100), 2) if data_count > 0 else 0
    print(f"  Late Access %: {late_percent}%\n")
    
    db.close()

def view_audit_log(limit=20):
    """View recent audit log entries"""
    db = get_db()
    logs = db.execute('''SELECT al.*, u.username FROM audit_log al
                         LEFT JOIN users u ON al.user_id = u.id
                         ORDER BY al.created_at DESC LIMIT ?''', (limit,)).fetchall()
    
    if not logs:
        print("No audit log entries found.")
        return
    
    table_data = [[l['username'], l['action'], l['table_name'], l['record_id'], 
                   l['changes'][:50], l['created_at']] for l in logs]
    print(tabulate(table_data, headers=['User', 'Action', 'Table', 'Record ID', 
                                         'Changes', 'Timestamp'], tablefmt='grid'))
    db.close()

def backup_database():
    """Create a backup of the database"""
    import shutil
    from datetime import datetime
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = DB_PATH.parent / f'data_backup_{timestamp}.db'
    shutil.copy2(DB_PATH, backup_path)
    print(f"✓ Database backed up to: {backup_path}")

def export_csv(output_file='export.csv'):
    """Export all awareness data to CSV"""
    import csv
    
    db = get_db()
    rows = db.execute('''SELECT ad.*, u.username FROM awareness_data ad
                         LEFT JOIN users u ON ad.user_id = u.id
                         ORDER BY ad.created_at DESC''').fetchall()
    
    if not rows:
        print("No data to export.")
        return
    
    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['User', 'Opportunity', 'Announcement Date', 'Awareness Date', 
                        'Deadline', 'Delay (days)', 'Category', 'Delay Ratio', 
                        'College Type', 'Region', 'Status', 'Submitted'])
        for r in rows:
            writer.writerow([r['username'], r['opportunity_name'], r['announcement_date'],
                           r['awareness_date'], r['deadline'], r['delay_days'],
                           r['delay_category'], r['delay_ratio'], r['college_type'],
                           r['region'], r['status'], r['created_at']])
    
    print(f"✓ Data exported to: {output_file}")
    db.close()

if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("Database Manager Commands:")
        print("  python db_manager.py list-users")
        print("  python db_manager.py create-user <username> <password>")
        print("  python db_manager.py delete-user <user_id>")
        print("  python db_manager.py reset-password <user_id> <new_password>")
        print("  python db_manager.py list-data [user_id]")
        print("  python db_manager.py statistics")
        print("  python db_manager.py audit-log [limit]")
        print("  python db_manager.py backup")
        print("  python db_manager.py export-csv [output_file]")
        sys.exit(0)
    
    command = sys.argv[1]
    
    if command == 'list-users':
        list_users()
    elif command == 'create-user' and len(sys.argv) >= 4:
        create_user(sys.argv[2], sys.argv[3])
    elif command == 'delete-user' and len(sys.argv) >= 3:
        delete_user(int(sys.argv[2]))
    elif command == 'reset-password' and len(sys.argv) >= 4:
        reset_password(int(sys.argv[2]), sys.argv[3])
    elif command == 'list-data':
        user_id = int(sys.argv[2]) if len(sys.argv) >= 3 else None
        list_awareness_data(user_id)
    elif command == 'statistics':
        get_statistics()
    elif command == 'audit-log':
        limit = int(sys.argv[2]) if len(sys.argv) >= 3 else 20
        view_audit_log(limit)
    elif command == 'backup':
        backup_database()
    elif command == 'export-csv':
        output_file = sys.argv[2] if len(sys.argv) >= 3 else 'export.csv'
        export_csv(output_file)
    else:
        print(f"Unknown command: {command}")
