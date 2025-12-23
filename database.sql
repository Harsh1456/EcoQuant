-- =====================================================
-- EcoQuant Database Schema for AWS RDS PostgreSQL
-- =====================================================

-- Create database roles (run separately if needed)
-- CREATE ROLE app_user WITH LOGIN PASSWORD 'your_secure_password';
-- CREATE ROLE app_admin WITH LOGIN PASSWORD 'your_admin_password';

-- =====================================================
-- TABLES
-- =====================================================

-- Users table
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    email VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL DEFAULT 'hash',
    role VARCHAR(20) DEFAULT 'user',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Projects table
CREATE TABLE projects (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    name VARCHAR(200) NOT NULL,
    type VARCHAR(100),
    location VARCHAR(200),
    start_date DATE,
    end_date DATE,
    status VARCHAR(50) DEFAULT 'Active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_projects_user FOREIGN KEY (user_id) 
        REFERENCES users(id) ON DELETE CASCADE
);

-- Emission factors table
CREATE TABLE emission_factors (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    co2e_per_unit NUMERIC(10,4) NOT NULL,
    unit VARCHAR(50) NOT NULL,
    category VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Emissions table
CREATE TABLE emissions (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL,
    asphalt_t NUMERIC(10,2) DEFAULT 0,
    aggregate_t NUMERIC(10,2) DEFAULT 0,
    cement_t NUMERIC(10,2) DEFAULT 0,
    steel_t NUMERIC(10,2) DEFAULT 0,
    diesel_l NUMERIC(10,2) DEFAULT 0,
    electricity_kwh NUMERIC(10,2) DEFAULT 0,
    transport_tkm NUMERIC(10,2) DEFAULT 0,
    water_use NUMERIC(10,2) DEFAULT 0,
    waste_t NUMERIC(10,2) DEFAULT 0,
    recycled_pct NUMERIC(5,2) DEFAULT 0,
    renewable_pct NUMERIC(5,2) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_emissions_project FOREIGN KEY (project_id) 
        REFERENCES projects(id) ON DELETE CASCADE
);

-- Recommendations table
CREATE TABLE recommendations (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL,
    title VARCHAR(200) NOT NULL,
    description TEXT,
    impact VARCHAR(50),
    cost NUMERIC(10,2),
    category VARCHAR(100),
    display_order INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_recommendations_project FOREIGN KEY (project_id) 
        REFERENCES projects(id) ON DELETE CASCADE
);

-- Carbon credits table
CREATE TABLE carbon_credits (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    credits_earned NUMERIC(10,2) NOT NULL DEFAULT 0,
    credits_used NUMERIC(10,2) DEFAULT 0,
    listed_quantity NUMERIC(10,2) DEFAULT 0,
    credit_value NUMERIC(12,2) DEFAULT 0,
    transaction_type VARCHAR(50) DEFAULT 'ISSUANCE',
    status VARCHAR(50) DEFAULT 'available',
    issued_at DATE DEFAULT CURRENT_DATE,
    source VARCHAR(20) DEFAULT 'ISSUANCE',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_carbon_credits_project FOREIGN KEY (project_id) 
        REFERENCES projects(id) ON DELETE CASCADE,
    CONSTRAINT fk_carbon_credits_user FOREIGN KEY (user_id) 
        REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT chk_credits_earned_positive CHECK (credits_earned >= 0),
    CONSTRAINT chk_credit_value_positive CHECK (credit_value >= 0),
    CONSTRAINT chk_transaction_type CHECK (
        transaction_type IN ('ISSUANCE', 'PURCHASE', 'TRANSFER')
    )
);

-- Marketplace listings table
CREATE TABLE marketplace_listings (
    id SERIAL PRIMARY KEY,
    credit_id INTEGER NOT NULL,
    seller_id INTEGER NOT NULL,
    quantity_available NUMERIC(10,2) NOT NULL,
    price_per_credit NUMERIC(10,2) NOT NULL,
    status VARCHAR(50) DEFAULT 'active',
    listed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_marketplace_credit FOREIGN KEY (credit_id) 
        REFERENCES carbon_credits(id) ON DELETE CASCADE,
    CONSTRAINT fk_marketplace_seller FOREIGN KEY (seller_id) 
        REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT chk_quantity_positive CHECK (quantity_available >= 0),
    CONSTRAINT chk_price_positive CHECK (price_per_credit > 0),
    CONSTRAINT chk_status CHECK (status IN ('active', 'sold', 'cancelled'))
);

-- Credit transactions table
CREATE TABLE credit_transactions (
    id SERIAL PRIMARY KEY,
    listing_id INTEGER,
    buyer_id INTEGER NOT NULL,
    seller_id INTEGER NOT NULL,
    credit_id INTEGER,
    quantity NUMERIC(10,2) NOT NULL,
    total_price NUMERIC(12,2) NOT NULL,
    transaction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_credit_trans_listing FOREIGN KEY (listing_id) 
        REFERENCES marketplace_listings(id) ON DELETE SET NULL,
    CONSTRAINT fk_credit_trans_buyer FOREIGN KEY (buyer_id) 
        REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_credit_trans_seller FOREIGN KEY (seller_id) 
        REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_credit_trans_credit FOREIGN KEY (credit_id) 
        REFERENCES carbon_credits(id) ON DELETE SET NULL,
    CONSTRAINT chk_different_users CHECK (buyer_id <> seller_id)
);

-- Carbon credit transactions table
CREATE TABLE carbon_credit_transactions (
    id SERIAL PRIMARY KEY,
    from_user_id INTEGER,
    to_user_id INTEGER,
    quantity NUMERIC(10,2) NOT NULL,
    price_per_credit NUMERIC(10,2),
    total_price NUMERIC(10,2),
    from_project_id INTEGER,
    to_project_id INTEGER,
    listing_id INTEGER,
    transaction_type VARCHAR(20) NOT NULL,
    status VARCHAR(20) DEFAULT 'PENDING',
    payment_reference VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_cct_from_user FOREIGN KEY (from_user_id) 
        REFERENCES users(id),
    CONSTRAINT fk_cct_to_user FOREIGN KEY (to_user_id) 
        REFERENCES users(id),
    CONSTRAINT fk_cct_from_project FOREIGN KEY (from_project_id) 
        REFERENCES projects(id),
    CONSTRAINT fk_cct_to_project FOREIGN KEY (to_project_id) 
        REFERENCES projects(id),
    CONSTRAINT fk_cct_listing FOREIGN KEY (listing_id) 
        REFERENCES marketplace_listings(id)
);

-- Audit logs table
CREATE TABLE audit_logs (
    id SERIAL PRIMARY KEY,
    table_name VARCHAR(50) NOT NULL,
    record_id INTEGER,
    action VARCHAR(20) NOT NULL,
    old_data JSONB,
    new_data JSONB,
    changed_by INTEGER,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Reports table
CREATE TABLE reports (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    project_id INTEGER,
    name VARCHAR(255) NOT NULL,
    file_path TEXT NOT NULL,
    file_size INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- INDEXES
-- =====================================================

CREATE INDEX idx_reports_user_id ON reports(user_id);
CREATE INDEX idx_reports_project_id ON reports(project_id);

-- =====================================================
-- FUNCTIONS
-- =====================================================

-- Function to calculate project emissions and credits
CREATE OR REPLACE FUNCTION calculate_project_emissions(project_id INTEGER)
RETURNS TABLE(total_co2e_kg NUMERIC, credits_earned NUMERIC)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        COALESCE(SUM(
            e.asphalt_t * ef_asphalt.co2e_per_unit +
            e.aggregate_t * ef_aggregate.co2e_per_unit +
            e.cement_t * ef_cement.co2e_per_unit +
            e.steel_t * ef_steel.co2e_per_unit +
            e.diesel_l * ef_diesel.co2e_per_unit +
            e.electricity_kwh * ef_electricity.co2e_per_unit +
            e.transport_tkm * ef_transport.co2e_per_unit
        ), 0) AS total_co2e_kg,
        COALESCE(SUM(
            (e.asphalt_t * ef_asphalt.co2e_per_unit +
            e.aggregate_t * ef_aggregate.co2e_per_unit +
            e.cement_t * ef_cement.co2e_per_unit +
            e.steel_t * ef_steel.co2e_per_unit +
            e.diesel_l * ef_diesel.co2e_per_unit +
            e.electricity_kwh * ef_electricity.co2e_per_unit +
            e.transport_tkm * ef_transport.co2e_per_unit) *
            (e.recycled_pct * 0.3 + e.renewable_pct * 0.4) / 100
        ) / 1000, 0) AS credits_earned
    FROM emissions e
    JOIN emission_factors ef_asphalt ON ef_asphalt.name = 'Asphalt'
    JOIN emission_factors ef_aggregate ON ef_aggregate.name = 'Aggregate'
    JOIN emission_factors ef_cement ON ef_cement.name = 'Cement'
    JOIN emission_factors ef_steel ON ef_steel.name = 'Steel'
    JOIN emission_factors ef_diesel ON ef_diesel.name = 'Diesel'
    JOIN emission_factors ef_electricity ON ef_electricity.name = 'Electricity'
    JOIN emission_factors ef_transport ON ef_transport.name = 'Transport'
    WHERE e.project_id = calculate_project_emissions.project_id;
END;
$$;

-- Function to log carbon credit changes
CREATE OR REPLACE FUNCTION log_carbon_credit_changes()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO audit_logs (table_name, record_id, action, old_data, new_data, changed_by, changed_at)
    VALUES (
        TG_TABLE_NAME,
        COALESCE(NEW.id, OLD.id),
        TG_OP,
        row_to_json(OLD),
        row_to_json(NEW),
        NULLIF(current_setting('app.user_id', true), '')::INTEGER,
        NOW()
    );
    RETURN NEW;
END;
$$;

-- =====================================================
-- TRIGGERS
-- =====================================================

CREATE TRIGGER audit_carbon_credits
AFTER INSERT OR UPDATE OR DELETE ON carbon_credits
FOR EACH ROW
EXECUTE FUNCTION log_carbon_credit_changes();

-- =====================================================
-- ROW LEVEL SECURITY (RLS) POLICIES
-- =====================================================

-- Enable RLS on tables
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE emissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE carbon_credits ENABLE ROW LEVEL SECURITY;

-- User owns their profile
CREATE POLICY user_owns_profile ON users
    USING (id = (current_setting('app.user_id', true))::INTEGER);

-- User owns their projects
CREATE POLICY user_owns_project ON projects
    USING (user_id = (current_setting('app.user_id', true))::INTEGER);

-- User owns emissions for their projects
CREATE POLICY user_owns_emissions ON emissions
    USING (project_id IN (
        SELECT id FROM projects 
        WHERE user_id = (current_setting('app.user_id', true))::INTEGER
    ));

-- User owns credits for their projects or directly assigned to them
CREATE POLICY user_owns_credits ON carbon_credits
    USING (
        project_id IN (
            SELECT id FROM projects 
            WHERE user_id = (current_setting('app.user_id', true))::INTEGER
        ) OR 
        user_id = (current_setting('app.user_id', true))::INTEGER
    );

-- =====================================================
-- GRANT PERMISSIONS
-- =====================================================

-- Grant schema usage
GRANT USAGE ON SCHEMA public TO app_user;

-- Grant table permissions to app_user
GRANT SELECT, INSERT, UPDATE ON TABLE users TO app_user;
GRANT SELECT, INSERT, UPDATE ON TABLE projects TO app_user;
GRANT SELECT, INSERT, UPDATE ON TABLE emission_factors TO app_user;
GRANT SELECT, INSERT, UPDATE ON TABLE emissions TO app_user;
GRANT SELECT, INSERT, UPDATE ON TABLE recommendations TO app_user;
GRANT SELECT, INSERT, UPDATE ON TABLE carbon_credits TO app_user;
GRANT SELECT, INSERT, UPDATE ON TABLE marketplace_listings TO app_user;
GRANT SELECT, INSERT, UPDATE ON TABLE credit_transactions TO app_user;
GRANT SELECT, INSERT ON TABLE carbon_credit_transactions TO app_user;
GRANT SELECT, INSERT, UPDATE ON TABLE reports TO app_user;

-- Grant sequence permissions to app_user
GRANT SELECT, USAGE ON ALL SEQUENCES IN SCHEMA public TO app_user;

-- Grant all permissions to app_admin
GRANT ALL ON ALL TABLES IN SCHEMA public TO app_admin;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO app_admin;

-- =====================================================
-- SAMPLE DATA (Optional - Insert emission factors)
-- =====================================================

INSERT INTO emission_factors (name, co2e_per_unit, unit, category) VALUES
    ('Asphalt', 0.0940, 'kg CO2e/kg', 'Materials'),
    ('Aggregate', 0.0048, 'kg CO2e/kg', 'Materials'),
    ('Cement', 0.9200, 'kg CO2e/kg', 'Materials'),
    ('Steel', 1.8500, 'kg CO2e/kg', 'Materials'),
    ('Diesel', 2.6800, 'kg CO2e/L', 'Fuel'),
    ('Electricity', 0.4330, 'kg CO2e/kWh', 'Energy'),
    ('Transport', 0.0620, 'kg CO2e/tkm', 'Logistics')
ON CONFLICT (name) DO NOTHING;

-- =====================================================
-- NOTES
-- =====================================================
-- 1. Remember to create database roles before running this script:
--    CREATE ROLE app_user WITH LOGIN PASSWORD 'your_password';
--    CREATE ROLE app_admin WITH LOGIN PASSWORD 'your_password';
--
-- 2. Update passwords in the role creation commands above
--
-- 3. RLS policies use app.user_id setting. Set it in your application:
--    SET app.user_id = <user_id>;
--
-- 4. This script is idempotent for emission_factors but will fail 
--    if tables already exist. Drop existing tables first if needed.
--
-- 5. Consider backing up your data before running this script.