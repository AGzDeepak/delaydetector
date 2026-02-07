# 🎨 Blue & Black UI Design + Enhanced Database Management

## Color Scheme Update

The application has been redesigned with a modern **blue and black gradient** theme replacing the previous purple design:

### Background Gradient
```css
background: linear-gradient(135deg, #0a0e27 0%, #1a2332 50%, #1e3a5f 100%);
```
- **Dark Navy**: `#0a0e27` (top-left corner)
- **Deep Black-Blue**: `#1a2332` (center)
- **Rich Blue**: `#1e3a5f` (bottom-right corner)

### Accent Colors
- **Primary Blue**: `#0066cc` → `#0052a3` (buttons, gradients)
- **Cyan Accent**: `#00ccff` (borders, highlights)
- **Glass Transparency**: `rgba(255,255,255,0.08-0.15)` with `backdrop-filter: blur(20px)`

### Updated Components
- ✅ Login/Register pages with blue glass cards
- ✅ Submit form with blue accent bars and buttons
- ✅ Dashboard metrics with blue gradient cards
- ✅ Data tables with blue header background
- ✅ All buttons and CTAs with blue gradient
- ✅ Responsive design maintained across all devices

---

## 🗄️ Enhanced Database Architecture

### New Schema with Data Management

The database has been upgraded from a simple flat structure to a **robust relational database** with audit logging and user management.

#### Database Tables

##### 1. **users** Table
```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    email TEXT UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```
- **Purpose**: Store user account information with timestamps
- **Fields**: Account creation/update tracking

##### 2. **awareness_data** Table
```sql
CREATE TABLE awareness_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    opportunity_name TEXT NOT NULL,
    announcement_date TEXT NOT NULL,
    awareness_date TEXT NOT NULL,
    deadline TEXT NOT NULL,
    delay_days INTEGER,
    delay_category TEXT,
    delay_ratio REAL,
    college_type TEXT,
    region TEXT,
    description TEXT,
    status TEXT DEFAULT 'submitted',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id)
)
```
- **Purpose**: Store opportunity awareness submissions with full tracking
- **Features**: 
  - Foreign key relationship to users table
  - Automatic calculated fields (delay_days, delay_category, delay_ratio)
  - Status tracking for submissions
  - Timestamp tracking

##### 3. **audit_log** Table
```sql
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action TEXT NOT NULL,
    table_name TEXT,
    record_id INTEGER,
    changes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id)
)
```
- **Purpose**: Complete audit trail of all system activities
- **Features**:
  - Tracks INSERT, UPDATE, DELETE operations
  - Records what changed and who made changes
  - Immutable change history

---

## 📊 Database Manager CLI

A comprehensive command-line tool for managing users, data, and database operations.

### Installation
```bash
python db_manager.py
```

### Commands

#### **User Management**

###### List All Users
```bash
python db_manager.py list-users
```
**Output**: Table with user ID, username, creation date, and update date

###### Create New User
```bash
python db_manager.py create-user <username> <password>
```
**Example**:
```bash
python db_manager.py create-user john_doe securepass123
```

###### Delete User
```bash
python db_manager.py delete-user <user_id>
```
**Example**:
```bash
python db_manager.py delete-user 2
```
⚠️ **Warning**: Deletes user AND all related awareness data

###### Reset User Password
```bash
python db_manager.py reset-password <user_id> <new_password>
```
**Example**:
```bash
python db_manager.py reset-password 1 newpassword456
```

#### **Data Management**

###### List All Submission Data
```bash
python db_manager.py list-data
```
**Output**: Table with opportunity name, delay, category, college type, region, etc.

###### List User-Specific Data
```bash
python db_manager.py list-data <user_id>
```
**Example**:
```bash
python db_manager.py list-data 1
```

#### **Analytics & Reporting**

###### View Database Statistics
```bash
python db_manager.py statistics
```
**Output**:
```
📊 Database Statistics:
  Total Users: 5
  Total Submissions: 48
  Audit Log Entries: 127
  Average Delay: 18.5 days
  Late Access Count: 36
  Late Access %: 75.0%
```

###### View Audit Log
```bash
python db_manager.py audit-log [limit]
```
**Example**:
```bash
python db_manager.py audit-log 50
```
**Default**: Shows last 20 entries

#### **Data Export & Backup**

###### Create Database Backup
```bash
python db_manager.py backup
```
**Output**: `data_backup_20260206_194530.db`

Creates a timestamped copy of entire database for disaster recovery

###### Export to CSV
```bash
python db_manager.py export-csv [output_file]
```
**Example**:
```bash
python db_manager.py export-csv submissions_export.csv
```
**Default filename**: `export.csv`

**Export includes**:
- All opportunity submissions
- User names
- Delay calculations
- Categories and regions
- Submission timestamps

---

## 🔗 Data Relationships

```
users (1) ──── (many) awareness_data
  ↓                         ↓
  └─────────────────────────┘
                ↓
          audit_log
```

### User Data Flow
1. **User Registration** → Account created in `users` table
2. **Form Submission** → Data stored in `awareness_data` with `user_id` FK
3. **Action Logged** → Audit trail created in `audit_log`
4. **Dashboard View** → User sees only their data (filtered by user_id)

---

## 📈 Analytics Features

### Available Metrics
- Total submissions per user
- Average delay in days
- Percentage of late access
- Breakdown by delay category (Early/Medium/Late)
- Average delay ratio (0-1)
- Regional statistics
- College type statistics

### Audit Trail
- Who submitted data and when
- What data was submitted
- Changes to user accounts
- Complete history for compliance

---

## 🔒 Security Features

### Password Management
- Passwords hashed with werkzeug.security
- Never stored in plain text
- Password reset capability with new hash generation

### Data Isolation
- All data filtered by user_id
- Users can only see their submissions
- Audit log tracks all access

### Audit Trail
- Complete change history
- Action tracking for compliance
- Immutable audit log

---

## 💾 Database Backup & Recovery

### Automatic Backups
```bash
python db_manager.py backup
```
Creates timestamped backup: `data_backup_YYYYMMDD_HHMMSS.db`

### Restore from Backup
```bash
# To restore, manually copy backup file
cp data_backup_20260206_194530.db data.db
```

### CSV Export
```bash
python db_manager.py export-csv compliance_report.csv
```
Export all data for external analysis or archival

---

## 📝 Example Workflows

### Create Test Data
```bash
# Create test user
python db_manager.py create-user test_user password123

# Then submit data via web form at http://localhost:5000/submit
```

### Generate Report
```bash
# View stats
python db_manager.py statistics

# Export to CSV
python db_manager.py export-csv monthly_report.csv

# View audit trail
python db_manager.py audit-log 100
```

### Maintenance
```bash
# List all users and their submission counts
python db_manager.py list-users
python db_manager.py list-data

# Create backup before major changes
python db_manager.py backup

# Reset user password
python db_manager.py reset-password 5 newpass789
```

---

## 🎯 Next Steps

### Potential Enhancements
- **Multi-tenancy**: Support multiple organizations
- **Advanced Search**: Filter by date range, regions, college types
- **Role-based Access**: Admin, analyst, user roles
- **API Integration**: RESTful API for external systems
- **Notifications**: Email alerts for inequality signals
- **Machine Learning**: Predictive delay analysis
- **Data Visualization**: Advanced analytics dashboards

---

## 📞 Support

For issues or questions about the database manager:
```bash
python db_manager.py
```
Shows all available commands
