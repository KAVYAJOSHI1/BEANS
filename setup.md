# Blockchain Forensics Framework – Setup Guide

**Version:** 1.0  
**Target OS:** Ubuntu 20.04 LTS / 22.04 LTS  
**Estimated Setup Time:** 30-45 minutes  
**Skill Level:** Intermediate (comfortable with CLI, Docker, Python)

---

## Pre-Setup Checklist

Before starting, ensure you have:
- [ ] Ubuntu 20.04 LTS or later
- [ ] `sudo` access
- [ ] Internet connection (for package downloads)
- [ ] ~50GB free disk space minimum (for database + data)
- [ ] 16GB RAM minimum (32GB recommended)
- [ ] Ports available: 5432 (PostgreSQL), 7687 (Neo4j), 5000 (Flask API), 3000 (React UI)

---

## Phase 1: System Dependencies

### 1.1 Update System Packages

```bash
sudo apt update
sudo apt upgrade -y
```

### 1.2 Install Core Dependencies

```bash
sudo apt install -y \
  build-essential \
  curl \
  wget \
  git \
  python3-dev \
  python3-pip \
  python3-venv \
  postgresql \
  postgresql-contrib \
  libpq-dev \
  npm \
  nodejs \
  docker.io \
  docker-compose \
  openjdk-11-jdk
```

### 1.3 Verify Installations

```bash
# Python
python3 --version  # Should be 3.8+

# PostgreSQL
psql --version    # Should be 12+

# Node/npm
node --version    # Should be 14+
npm --version     # Should be 6+

# Docker
docker --version  # Should be 20+
```

---

## Phase 2: Database Setup

### 2.1 PostgreSQL Configuration

```bash
# Start PostgreSQL service
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Switch to postgres user
sudo -u postgres psql

# Inside postgres shell, run:
```

```sql
-- Create database and user
CREATE USER forensics_user WITH PASSWORD 'change_me_secure_password_here';
CREATE DATABASE blockchain_forensics OWNER forensics_user;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE blockchain_forensics TO forensics_user;

-- Connect to database
\c blockchain_forensics

-- Create schema
CREATE SCHEMA forensics;
ALTER USER forensics_user SET search_path TO forensics, public;

-- Exit
\q
```

### 2.2 PostgreSQL Tables

Save the following as `db_schema.sql`:

```sql
-- Create transactions table
CREATE TABLE forensics.transactions (
    txid VARCHAR(64) PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    input_addresses TEXT[],
    output_addresses TEXT[],
    input_amounts NUMERIC[],
    output_amounts NUMERIC[],
    total_input NUMERIC,
    total_output NUMERIC,
    fee NUMERIC,
    script_type VARCHAR(50),
    block_height BIGINT,
    created_at TIMESTAMP DEFAULT NOW(),
    INDEX idx_timestamp (timestamp),
    INDEX idx_addresses (input_addresses, output_addresses)
);

-- Create network observations table
CREATE TABLE forensics.network_observations (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    src_ip VARCHAR(45),
    dst_ip VARCHAR(45),
    src_port INT,
    dst_port INT,
    src_asn VARCHAR(20),
    src_country VARCHAR(2),
    dst_asn VARCHAR(20),
    dst_country VARCHAR(2),
    bytes_in BIGINT,
    bytes_out BIGINT,
    protocol VARCHAR(10),
    created_at TIMESTAMP DEFAULT NOW(),
    INDEX idx_timestamp (timestamp),
    INDEX idx_ips (src_ip, dst_ip),
    INDEX idx_asn (src_asn, dst_asn)
);

-- Create wallet profiles table
CREATE TABLE forensics.wallet_profiles (
    address VARCHAR(64) PRIMARY KEY,
    first_seen TIMESTAMP,
    last_seen TIMESTAMP,
    transaction_count INT DEFAULT 0,
    total_received NUMERIC DEFAULT 0,
    total_sent NUMERIC DEFAULT 0,
    mixing_participation BOOLEAN DEFAULT FALSE,
    risk_score NUMERIC DEFAULT 0,
    threat_classification VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Create correlations table
CREATE TABLE forensics.correlations (
    id SERIAL PRIMARY KEY,
    entity_type VARCHAR(50),  -- WALLET, IP, ASN
    entity_id VARCHAR(256),
    correlated_entity_type VARCHAR(50),
    correlated_entity_id VARCHAR(256),
    correlation_type VARCHAR(50),  -- FUNDED_BY, MIXES_WITH, BROADCASTS_FROM, etc.
    confidence NUMERIC,
    created_at TIMESTAMP DEFAULT NOW(),
    INDEX idx_entities (entity_type, entity_id),
    INDEX idx_correlated (correlated_entity_type, correlated_entity_id)
);

-- Create threat intelligence table
CREATE TABLE forensics.threat_intelligence (
    id SERIAL PRIMARY KEY,
    entity_type VARCHAR(50),
    entity_id VARCHAR(256),
    source VARCHAR(100),  -- CHAINALYSIS, ELLIPTIC, LE_TIP, etc.
    threat_type VARCHAR(100),  -- RANSOMWARE, MIXING, DARKNET, etc.
    incident_name VARCHAR(256),
    confidence NUMERIC,
    created_at TIMESTAMP DEFAULT NOW(),
    INDEX idx_entity (entity_type, entity_id)
);

-- Create alerts table
CREATE TABLE forensics.alerts (
    id SERIAL PRIMARY KEY,
    entity_type VARCHAR(50),
    entity_id VARCHAR(256),
    alert_type VARCHAR(100),
    reason TEXT,
    evidence JSONB,
    automated_score NUMERIC,
    investigator_confidence NUMERIC,
    status VARCHAR(50) DEFAULT 'OPEN',
    assigned_to VARCHAR(256),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    INDEX idx_entity (entity_type, entity_id),
    INDEX idx_status (status),
    INDEX idx_created (created_at DESC)
);

-- Create case files table
CREATE TABLE forensics.case_files (
    id SERIAL PRIMARY KEY,
    case_name VARCHAR(256),
    incident_type VARCHAR(100),
    linked_entities TEXT[],
    notes TEXT,
    assigned_to VARCHAR(256),
    status VARCHAR(50) DEFAULT 'OPEN',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    INDEX idx_case_name (case_name),
    INDEX idx_status (status)
);

-- Create audit log table
CREATE TABLE forensics.audit_log (
    id SERIAL PRIMARY KEY,
    action VARCHAR(256),
    investigator VARCHAR(256),
    entity_type VARCHAR(50),
    entity_id VARCHAR(256),
    details JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    INDEX idx_investigator (investigator),
    INDEX idx_created (created_at DESC)
);
```

Apply schema:

```bash
# Connect to database and run schema
sudo -u postgres psql blockchain_forensics -f db_schema.sql

# Verify tables created
sudo -u postgres psql blockchain_forensics -c "\dt forensics.*"
```

### 2.3 Neo4j Setup (Docker)

```bash
# Pull Neo4j image
docker pull neo4j:latest

# Run Neo4j container
docker run -d \
  --name neo4j-forensics \
  -p 7687:7687 \
  -p 7474:7474 \
  -e NEO4J_AUTH=neo4j/change_me_secure_password \
  -e NEO4JLABS_PLUGINS=apoc \
  -v neo4j_data:/data \
  neo4j:latest

# Wait for startup (check logs)
docker logs -f neo4j-forensics

# Once ready, access at http://localhost:7474
# Default creds: neo4j / change_me_secure_password
```

Create Neo4j constraints:

```bash
# Copy the following commands into Neo4j Browser at http://localhost:7474

CREATE CONSTRAINT wallet_addr IF NOT EXISTS FOR (w:Wallet) REQUIRE w.address IS UNIQUE;
CREATE CONSTRAINT ip_addr IF NOT EXISTS FOR (i:IP) REQUIRE i.ip IS UNIQUE;
CREATE CONSTRAINT asn_id IF NOT EXISTS FOR (a:ASN) REQUIRE a.asn IS UNIQUE;
CREATE CONSTRAINT txid_unique IF NOT EXISTS FOR (t:Transaction) REQUIRE t.txid IS UNIQUE;

CREATE INDEX idx_wallet_score IF NOT EXISTS FOR (w:Wallet) ON (w.risk_score);
CREATE INDEX idx_ip_country IF NOT EXISTS FOR (i:IP) ON (i.country);
CREATE INDEX idx_tx_timestamp IF NOT EXISTS FOR (t:Transaction) ON (t.timestamp);
```

---

## Phase 3: Python Backend Setup

### 3.1 Create Virtual Environment

```bash
# Navigate to your project directory
mkdir -p ~/blockchain-forensics
cd ~/blockchain-forensics

# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip setuptools wheel
```

### 3.2 Install Python Dependencies

Create `requirements.txt`:

```
Flask==2.3.0
Flask-CORS==4.0.0
psycopg2-binary==2.9.6
sqlalchemy==2.0.15
neo4j==5.8.1
pandas==2.0.2
numpy==1.24.3
scikit-learn==1.2.2
requests==2.31.0
python-dotenv==1.0.0
python-dateutil==2.8.2
geoip2==4.7.0
MaxMind-DB-Writer==1.7.0
gunicorn==20.1.0
```

Install:

```bash
pip install -r requirements.txt
```

### 3.3 Create Flask Application Structure

Create directory structure:

```bash
mkdir -p app/{routes,models,utils,data}
mkdir -p data/{raw,processed,threat_intel}
mkdir -p tests
```

Create `app/__init__.py`:

```python
from flask import Flask
from flask_cors import CORS
import logging

def create_app():
    app = Flask(__name__)
    CORS(app)
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Register blueprints
    from app.routes import api, data, investigation
    app.register_blueprint(api.bp)
    app.register_blueprint(data.bp)
    app.register_blueprint(investigation.bp)
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=5000)
```

### 3.4 Database Connection Module

Create `app/models/database.py`:

```python
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from neo4j import GraphDatabase
import logging

logger = logging.getLogger(__name__)

# PostgreSQL connection
POSTGRES_URL = os.getenv(
    'DATABASE_URL',
    'postgresql://forensics_user:change_me_secure_password@localhost:5432/blockchain_forensics'
)

engine = create_engine(POSTGRES_URL, echo=False, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Neo4j connection
NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'change_me_secure_password')

neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

def get_db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_neo4j_session():
    return neo4j_driver.session()
```

### 3.5 Core Data Models

Create `app/models/transaction.py`:

```python
from sqlalchemy import Column, String, TIMESTAMP, NUMERIC, Integer, ARRAY, Index, Boolean
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index('idx_timestamp', 'timestamp'),
        Index('idx_addresses', 'input_addresses', 'output_addresses'),
        {'schema': 'forensics'}
    )
    
    txid = Column(String(64), primary_key=True)
    timestamp = Column(TIMESTAMP, nullable=False)
    input_addresses = Column(ARRAY(String), nullable=False)
    output_addresses = Column(ARRAY(String), nullable=False)
    input_amounts = Column(ARRAY(NUMERIC), nullable=False)
    output_amounts = Column(ARRAY(NUMERIC), nullable=False)
    total_input = Column(NUMERIC)
    total_output = Column(NUMERIC)
    fee = Column(NUMERIC)
    script_type = Column(String(50))
    block_height = Column(Integer)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)

class WalletProfile(Base):
    __tablename__ = "wallet_profiles"
    __table_args__ = {'schema': 'forensics'}
    
    address = Column(String(64), primary_key=True)
    first_seen = Column(TIMESTAMP)
    last_seen = Column(TIMESTAMP)
    transaction_count = Column(Integer, default=0)
    total_received = Column(NUMERIC, default=0)
    total_sent = Column(NUMERIC, default=0)
    mixing_participation = Column(Boolean, default=False)
    risk_score = Column(NUMERIC, default=0)
    threat_classification = Column(String(50))
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)

class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        Index('idx_entity', 'entity_type', 'entity_id'),
        Index('idx_status', 'status'),
        Index('idx_created', 'created_at'),
        {'schema': 'forensics'}
    )
    
    id = Column(Integer, primary_key=True)
    entity_type = Column(String(50))
    entity_id = Column(String(256))
    alert_type = Column(String(100))
    reason = Column(String(1000))
    evidence = Column(String(5000))  # JSON serialized
    automated_score = Column(NUMERIC)
    investigator_confidence = Column(NUMERIC)
    status = Column(String(50), default='OPEN')
    assigned_to = Column(String(256))
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)
```

### 3.6 API Routes

Create `app/routes/api.py`:

```python
from flask import Blueprint, jsonify, request
from app.models.database import SessionLocal, get_neo4j_session
from app.models.transaction import Transaction, WalletProfile, Alert
import logging

bp = Blueprint('api', __name__, url_prefix='/api')
logger = logging.getLogger(__name__)

@bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy'}), 200

@bp.route('/alerts', methods=['GET'])
def get_alerts():
    """Retrieve all alerts, optionally filtered by status"""
    status = request.args.get('status', 'OPEN')
    limit = request.args.get('limit', 100, type=int)
    
    db = SessionLocal()
    try:
        alerts = db.query(Alert).filter(Alert.status == status).limit(limit).all()
        return jsonify([{
            'id': a.id,
            'entity_type': a.entity_type,
            'entity_id': a.entity_id,
            'alert_type': a.alert_type,
            'reason': a.reason,
            'automated_score': float(a.automated_score or 0),
            'status': a.status,
            'created_at': a.created_at.isoformat()
        } for a in alerts]), 200
    except Exception as e:
        logger.error(f"Error retrieving alerts: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@bp.route('/wallet/<address>', methods=['GET'])
def get_wallet(address):
    """Retrieve wallet profile"""
    db = SessionLocal()
    try:
        wallet = db.query(WalletProfile).filter(WalletProfile.address == address).first()
        if not wallet:
            return jsonify({'error': 'Wallet not found'}), 404
        
        return jsonify({
            'address': wallet.address,
            'first_seen': wallet.first_seen.isoformat(),
            'last_seen': wallet.last_seen.isoformat(),
            'transaction_count': wallet.transaction_count,
            'total_received': float(wallet.total_received or 0),
            'total_sent': float(wallet.total_sent or 0),
            'mixing_participation': wallet.mixing_participation,
            'risk_score': float(wallet.risk_score or 0),
            'threat_classification': wallet.threat_classification
        }), 200
    except Exception as e:
        logger.error(f"Error retrieving wallet: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@bp.route('/transaction/<txid>', methods=['GET'])
def get_transaction(txid):
    """Retrieve transaction details"""
    db = SessionLocal()
    try:
        tx = db.query(Transaction).filter(Transaction.txid == txid).first()
        if not tx:
            return jsonify({'error': 'Transaction not found'}), 404
        
        return jsonify({
            'txid': tx.txid,
            'timestamp': tx.timestamp.isoformat(),
            'input_addresses': tx.input_addresses,
            'output_addresses': tx.output_addresses,
            'input_amounts': [float(a) for a in tx.input_amounts],
            'output_amounts': [float(a) for a in tx.output_amounts],
            'fee': float(tx.fee or 0),
            'script_type': tx.script_type,
            'block_height': tx.block_height
        }), 200
    except Exception as e:
        logger.error(f"Error retrieving transaction: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()
```

Create `app/routes/data.py`:

```python
from flask import Blueprint, request, jsonify
from app.models.database import SessionLocal
from app.models.transaction import Transaction, WalletProfile
import json
import logging
from datetime import datetime

bp = Blueprint('data', __name__, url_prefix='/api/data')
logger = logging.getLogger(__name__)

@bp.route('/ingest-transactions', methods=['POST'])
def ingest_transactions():
    """Ingest transaction data from JSON"""
    try:
        data = request.get_json()
        transactions = data.get('transactions', [])
        
        db = SessionLocal()
        for tx_data in transactions:
            tx = Transaction(
                txid=tx_data['txid'],
                timestamp=datetime.fromisoformat(tx_data['timestamp']),
                input_addresses=tx_data.get('input_addresses', []),
                output_addresses=tx_data.get('output_addresses', []),
                input_amounts=tx_data.get('input_amounts', []),
                output_amounts=tx_data.get('output_amounts', []),
                total_input=sum(float(a) for a in tx_data.get('input_amounts', []) or [0]),
                total_output=sum(float(a) for a in tx_data.get('output_amounts', []) or [0]),
                fee=float(tx_data.get('fee', 0)),
                script_type=tx_data.get('script_type'),
                block_height=tx_data.get('block_height')
            )
            db.merge(tx)
        
        db.commit()
        db.close()
        
        return jsonify({'status': 'success', 'count': len(transactions)}), 200
    except Exception as e:
        logger.error(f"Error ingesting transactions: {e}")
        return jsonify({'error': str(e)}), 500
```

### 3.7 Run Flask Backend

```bash
# Set environment variables
export FLASK_APP=app/__init__.py
export FLASK_ENV=development

# Run application
python -m flask run --host=0.0.0.0 --port=5000

# Should see output:
# * Running on http://0.0.0.0:5000
# * Debug mode: on
```

Test health endpoint:

```bash
curl http://localhost:5000/api/health
# Should return: {"status": "healthy"}
```

---

## Phase 4: Frontend React Setup

### 4.1 Create React App

```bash
# In a separate terminal, navigate to project
cd ~/blockchain-forensics

# Create React app
npx create-react-app frontend

# Navigate into frontend
cd frontend
```

### 4.2 Install Frontend Dependencies

```bash
npm install axios react-router-dom recharts cytoscape-react

# For styling
npm install tailwindcss postcss autoprefixer
npx tailwindcss init -p
```

### 4.3 Create Dashboard Component

Create `src/components/AlertDashboard.jsx`:

```jsx
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import './AlertDashboard.css';

const AlertDashboard = () => {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('OPEN');

  useEffect(() => {
    fetchAlerts();
  }, [filter]);

  const fetchAlerts = async () => {
    try {
      const response = await axios.get(`http://localhost:5000/api/alerts?status=${filter}`);
      setAlerts(response.data);
      setLoading(false);
    } catch (error) {
      console.error('Error fetching alerts:', error);
      setLoading(false);
    }
  };

  const getRiskColor = (score) => {
    if (score >= 80) return '#ff4444';
    if (score >= 60) return '#ff8800';
    if (score >= 40) return '#ffcc00';
    return '#44ff44';
  };

  if (loading) return <div className="loading">Loading alerts...</div>;

  return (
    <div className="alert-dashboard">
      <h1>Investigation Dashboard</h1>
      
      <div className="filter-controls">
        <button 
          onClick={() => setFilter('OPEN')}
          className={filter === 'OPEN' ? 'active' : ''}
        >
          Open ({alerts.length})
        </button>
        <button 
          onClick={() => setFilter('INVESTIGATING')}
          className={filter === 'INVESTIGATING' ? 'active' : ''}
        >
          Investigating
        </button>
        <button 
          onClick={() => setFilter('RESOLVED')}
          className={filter === 'RESOLVED' ? 'active' : ''}
        >
          Resolved
        </button>
      </div>

      <table className="alerts-table">
        <thead>
          <tr>
            <th>Entity Type</th>
            <th>Entity ID</th>
            <th>Alert Type</th>
            <th>Reason</th>
            <th>Risk Score</th>
            <th>Created</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {alerts.map((alert) => (
            <tr key={alert.id}>
              <td>{alert.entity_type}</td>
              <td className="monospace">{alert.entity_id.substring(0, 16)}...</td>
              <td>{alert.alert_type}</td>
              <td>{alert.reason}</td>
              <td>
                <span 
                  className="risk-score"
                  style={{ backgroundColor: getRiskColor(alert.automated_score) }}
                >
                  {alert.automated_score.toFixed(0)}
                </span>
              </td>
              <td>{new Date(alert.created_at).toLocaleDateString()}</td>
              <td>
                <button className="btn-investigate">Investigate</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default AlertDashboard;
```

Create `src/components/AlertDashboard.css`:

```css
.alert-dashboard {
  padding: 20px;
  background: #f5f5f5;
}

.alert-dashboard h1 {
  margin-bottom: 20px;
  color: #333;
}

.filter-controls {
  margin-bottom: 20px;
}

.filter-controls button {
  padding: 10px 15px;
  margin-right: 10px;
  border: 1px solid #ddd;
  background: white;
  cursor: pointer;
  border-radius: 4px;
}

.filter-controls button.active {
  background: #007bff;
  color: white;
  border-color: #007bff;
}

.alerts-table {
  width: 100%;
  border-collapse: collapse;
  background: white;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.alerts-table th {
  background: #333;
  color: white;
  padding: 12px;
  text-align: left;
}

.alerts-table td {
  padding: 12px;
  border-bottom: 1px solid #eee;
}

.alerts-table tr:hover {
  background: #f9f9f9;
}

.monospace {
  font-family: 'Courier New', monospace;
  font-size: 12px;
}

.risk-score {
  display: inline-block;
  padding: 4px 8px;
  color: white;
  border-radius: 3px;
  font-weight: bold;
  min-width: 30px;
  text-align: center;
}

.btn-investigate {
  padding: 6px 12px;
  background: #007bff;
  color: white;
  border: none;
  border-radius: 3px;
  cursor: pointer;
}

.btn-investigate:hover {
  background: #0056b3;
}

.loading {
  text-align: center;
  padding: 40px;
  font-size: 18px;
  color: #666;
}
```

### 4.4 Update App.js

Replace `src/App.js`:

```jsx
import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import AlertDashboard from './components/AlertDashboard';
import './App.css';

function App() {
  return (
    <Router>
      <div className="App">
        <header className="app-header">
          <h1>🔍 Blockchain Forensics Framework</h1>
          <p>Investigator-Centric Financial Crime Detection</p>
        </header>
        
        <Routes>
          <Route path="/" element={<AlertDashboard />} />
        </Routes>
      </div>
    </Router>
  );
}

export default App;
```

### 4.5 Run Frontend

```bash
# In frontend directory
npm start

# Should open http://localhost:3000 automatically
# Make sure backend is running on port 5000
```

---

## Phase 5: Data Ingestion

### 5.1 Prepare Sample Data

Create `data/sample_transactions.json`:

```json
{
  "transactions": [
    {
      "txid": "abc123def456...",
      "timestamp": "2024-01-15T14:32:00Z",
      "input_addresses": ["1A1z7agoat7agoat7agoat7agoat7ag"],
      "output_addresses": ["1A1z7agoat7agoat7agoat7agoat7ag", "1A1z7agoat7agoat7agoat7agoat7ag"],
      "input_amounts": [1.5],
      "output_amounts": [1.0, 0.49],
      "fee": 0.01,
      "script_type": "P2PKH",
      "block_height": 829640
    }
  ]
}
```

### 5.2 Ingest Data via API

```bash
curl -X POST http://localhost:5000/api/data/ingest-transactions \
  -H "Content-Type: application/json" \
  -d @data/sample_transactions.json
```

### 5.3 Load Threat Intelligence

Create `data/threat_intel.json`:

```json
{
  "threat_entities": [
    {
      "address": "1A1z7agoat...",
      "threat_type": "RANSOMWARE",
      "source": "CHAINALYSIS",
      "incident_name": "LOCKBIT_2024_JAN",
      "confidence": 0.95
    }
  ]
}
```

Load via API call (endpoint to be added in Phase 6).

---

## Phase 6: Run Full Stack

### 6.1 Terminal 1: PostgreSQL

```bash
# Ensure running
sudo systemctl status postgresql

# If not running:
sudo systemctl start postgresql
```

### 6.2 Terminal 2: Neo4j

```bash
# Check container status
docker ps | grep neo4j

# If not running:
docker start neo4j-forensics
```

### 6.3 Terminal 3: Flask Backend

```bash
cd ~/blockchain-forensics
source venv/bin/activate
export FLASK_APP=app/__init__.py
python -m flask run --host=0.0.0.0 --port=5000
```

### 6.4 Terminal 4: React Frontend

```bash
cd ~/blockchain-forensics/frontend
npm start
```

### 6.5 Verify All Services

```bash
# Health checks
curl http://localhost:5000/api/health        # Flask
curl http://localhost:3000                   # React
curl http://localhost:7474                   # Neo4j (browser)

# Database
sudo -u postgres psql blockchain_forensics -c "SELECT COUNT(*) FROM forensics.transactions;"
```

---

## Phase 7: Production Deployment

### 7.1 Environment Configuration

Create `.env` file:

```
# PostgreSQL
DATABASE_URL=postgresql://forensics_user:secure_password@localhost:5432/blockchain_forensics

# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=secure_password

# Flask
FLASK_ENV=production
SECRET_KEY=your_secret_key_here

# API
API_HOST=0.0.0.0
API_PORT=5000
```

### 7.2 Run with Gunicorn

```bash
# Install gunicorn (already in requirements.txt)

# Run Flask with Gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:create_app()
```

### 7.3 Nginx Reverse Proxy (Optional)

Create `/etc/nginx/sites-available/forensics`:

```nginx
upstream flask_app {
    server 127.0.0.1:5000;
}

upstream react_app {
    server 127.0.0.1:3000;
}

server {
    listen 80;
    server_name localhost;

    location /api/ {
        proxy_pass http://flask_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location / {
        proxy_pass http://react_app;
        proxy_set_header Host $host;
    }
}
```

Enable and restart:

```bash
sudo ln -s /etc/nginx/sites-available/forensics /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

---

## Phase 8: Verification Checklist

- [ ] PostgreSQL running and schema loaded
- [ ] Neo4j running and constraints created
- [ ] Flask backend responds to `/api/health`
- [ ] React frontend loads at http://localhost:3000
- [ ] Can ingest test transaction data
- [ ] Alert Dashboard displays populated table
- [ ] Can query individual wallets via API
- [ ] All databases contain test data

---

## Troubleshooting

### PostgreSQL Connection Error

```bash
# Check connection
psql -U forensics_user -d blockchain_forensics -h localhost

# If fails, reset password:
sudo -u postgres psql
ALTER USER forensics_user WITH PASSWORD 'new_password';
```

### Neo4j Connection Error

```bash
# Check logs
docker logs neo4j-forensics

# Restart container
docker restart neo4j-forensics
```

### Flask Port Already in Use

```bash
# Kill process on port 5000
lsof -ti:5000 | xargs kill -9

# Run on different port
python -m flask run --port=5001
```

### React Build Error

```bash
# Clear cache
rm -rf node_modules package-lock.json
npm install
npm start
```

---

## Next Steps

1. **Load Real Data:** Prepare blockchain CSV exports and network data
2. **Implement Correlation Engine:** Build pattern matching algorithms (Phase 3 of approach.md)
3. **Develop Investigation UI:** Expand React dashboard with case files, entity cards
4. **Integrate OSINT:** Connect threat intelligence feeds
5. **Testing:** Unit tests for data ingestion, correlation, scoring logic
6. **Monitoring:** Set up logging, alerting, performance monitoring

---

## Support & Documentation

- PostgreSQL: https://www.postgresql.org/docs/
- Neo4j: https://neo4j.com/docs/
- Flask: https://flask.palletsprojects.com/
- React: https://react.dev/
- Deployment: See approach.md Part 6

---

**Setup Complete!** 🎉

Your blockchain forensics framework is ready for data ingestion and investigation. Start by loading sample data and verifying the dashboard displays alerts correctly.

