import os
import re
import math
import uuid
import random
from datetime import datetime, date, timedelta
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_file
from flask_session import Session
import psycopg2
from psycopg2 import sql, Error
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import pandas as pd
from dotenv import load_dotenv
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
import calendar
import sys
import logging

# ====================================
# INITIALIZATION & CONFIGURATION
# ====================================
load_dotenv()
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'fallback_secret_key')
app.config['SESSION_TYPE'] = 'filesystem'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
Session(app)


# ====================================
# DATABASE HELPER
# ====================================
def get_db_connection():
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            database=os.getenv('DB_NAME', 'ecoquant'),
            user=os.getenv('DB_USER', 'postgres'),
            password=os.getenv('DB_PASSWORD', ''),
            port=os.getenv('DB_PORT', '5432')
        )
        return conn
    except Exception:
        raise

def get_secure_db_connection(user_id=None, role='app_user'):
    """
    Returns a DB connection with RLS context set.
    Use this for all user-scoped operations.
    """
    conn = get_db_connection()
    try:
        # If user_id is not provided, try to get from session
        if user_id is None and 'user_id' in session:
            user_id = session['user_id']
            # Also try to get role from session if not explicitly "app_admin"
            if 'role' in session:
                 role = 'app_admin' if session['role'] == 'admin' else 'app_user'

        if user_id:
            cur = conn.cursor()
            # Switch to restricted role
            # Note: We must execute this first
            cur.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role)))
            
            # Set variable for RLS policies
            cur.execute("SELECT set_config('app.user_id', %s, false)", (str(user_id),))
            cur.close()
        return conn
    except Exception as e:
        conn.close()
        raise e


# ====================================
# CALCULATION HELPERS
# ====================================
def calculate_emissions_data(data):
    try:
        # Convert empty strings to 0 for numeric fields
        numeric_fields = ['asphalt_t', 'aggregate_t', 'cement_t', 'steel_t', 'diesel_l', 
                         'electricity_kwh', 'transport_km', 'material_weight', 'water_use', 'waste_t',
                         'recycled_pct', 'renewable_pct']
        for field in numeric_fields:
            if field in data and data[field] in ['', None]:
                data[field] = 0

        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get emission factors and convert to float
        cur.execute("SELECT name, co2e_per_unit FROM emission_factors")
        factors = {row[0]: float(row[1]) for row in cur.fetchall()}
        
        # Calculate emissions (all in kg)
        total_co2e_kg = 0
        breakdown = {
            "Materials": 0,
            "Equipment Fuel": 0,
            "Electricity": 0,
            "Transport": 0 
        }
        
        # Helper function to safely get float values
        def get_float(key, default=0.0):
            value = data.get(key, default)
            if value in ['', None]:
                return 0.0
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        # Material emissions
        materials = [
            ("asphalt_t", "Asphalt"),
            ("aggregate_t", "Aggregate"),
            ("cement_t", "Cement"),
            ("steel_t", "Steel")
        ]
        
        for field, factor_name in materials:
            value = get_float(field)
            emission = value * factors.get(factor_name, 0)
            breakdown["Materials"] += emission
            total_co2e_kg += emission
        
        # Equipment fuel
        diesel_val = get_float("diesel_l")
        diesel_emission = diesel_val * factors.get('Diesel', 0)
        breakdown["Equipment Fuel"] = diesel_emission
        total_co2e_kg += diesel_emission
        
        # Electricity
        electricity_val = get_float("electricity_kwh")
        electricity_emission = electricity_val * factors.get('Electricity', 0)
        breakdown["Electricity"] = electricity_emission
        total_co2e_kg += electricity_emission
        
        # Transport - FIXED CALCULATION
        transport_tkm = get_float("transport_tkm")
        transport_emission = transport_tkm * factors.get('Transport', 0)

        breakdown["Transport"] = transport_emission
        total_co2e_kg += transport_emission
        
        # Calculate credits
        recycled_pct = get_float("recycled_pct") / 100
        renewable_pct = get_float("renewable_pct") / 100
        reduction_kg = total_co2e_kg * (recycled_pct * 0.3 + renewable_pct * 0.4)
        reduction_pct = (reduction_kg / total_co2e_kg) * 100 if total_co2e_kg > 0 else 0
        credits = reduction_kg / 1000  # Convert kg to tons
        
        # Convert all to tons for frontend display
        result = {
            "total_co2e": round(total_co2e_kg / 1000, 2),  # kg to tons
            "breakdown": {k: round(v / 1000, 2) for k, v in breakdown.items()},  # kg to tons
            "credits": round(credits, 2),
            "reduction_pct": round(reduction_pct, 2)
        }
        
        return result
    except Exception as e:
        return {
            "total_co2e": 0,
            "breakdown": {
                "Materials": 0,
                "Equipment Fuel": 0,
                "Electricity": 0,
                "Transport": 0
            },
            "credits": 0,
            "reduction_pct": 0
        }


def generate_recommendations(emission_data, project_type=None):
    recommendations = []
    
    # Get emission breakdown
    materials_emissions = emission_data['breakdown'].get('Materials', 0)
    equipment_emissions = emission_data['breakdown'].get('Equipment Fuel', 0)
    electricity_emissions = emission_data['breakdown'].get('Electricity', 0)
    transport_emissions = emission_data['breakdown'].get('Transport', 0)
    total_emissions = emission_data['total_co2e']
    
    # Material-related recommendations - expanded list
    material_recommendations = [
        {
            'title': 'Use Recycled Materials',
            'description': 'Incorporate recycled asphalt pavement (RAP) and supplementary cementitious materials (SCMs) to reduce material-related emissions by up to 30%.',
            'impact': 'High',
            'cost': 800000,
            'category': 'Materials'
        },
        {
            'title': 'Use Warm Mix Asphalt',
            'description': 'Switch to warm mix asphalt technology which requires lower production temperatures (20-40°C less), reducing energy consumption and emissions by 15-30%.',
            'impact': 'Medium',
            'cost': 500000,
            'category': 'Materials'
        },
        {
            'title': 'Optimize Material Quantities',
            'description': 'Use advanced modeling to optimize material quantities, reducing waste by 10-15% and associated emissions.',
            'impact': 'Medium',
            'cost': 300000,
            'category': 'Materials'
        },
        {
            'title': 'Local Sourcing',
            'description': 'Source materials locally to reduce transportation distances and associated emissions by 20-40%.',
            'impact': 'Medium',
            'cost': 200000,
            'category': 'Materials'
        }
    ]
    
    # Equipment-related recommendations
    equipment_recommendations = [
        {
            'title': 'Electrify Equipment',
            'description': 'Replace diesel-powered equipment with electric alternatives where feasible to eliminate direct emissions and reduce noise pollution.',
            'impact': 'High',
            'cost': 2500000,
            'category': 'Equipment'
        },
        {
            'title': 'Implement Equipment Idling Policy',
            'description': 'Reduce unnecessary idling of construction equipment to save 10-15% fuel and reduce emissions.',
            'impact': 'Low',
            'cost': 50000,
            'category': 'Equipment'
        },
        {
            'title': 'Equipment Efficiency Upgrade',
            'description': 'Upgrade to newer, more efficient equipment models that consume 15-25% less fuel.',
            'impact': 'Medium',
            'cost': 1500000,
            'category': 'Equipment'
        },
        {
            'title': 'Regular Maintenance Program',
            'description': 'Implement a rigorous maintenance schedule to keep equipment operating at peak efficiency, reducing fuel consumption by 5-10%.',
            'impact': 'Low',
            'cost': 200000,
            'category': 'Equipment'
        }
    ]
    
    # Energy-related recommendations
    energy_recommendations = [
        {
            'title': 'Switch to Solar Power',
            'description': 'Install solar panels at site offices and batch plants to reduce grid electricity dependence by 40-60%.',
            'impact': 'High',
            'cost': 1200000,
            'category': 'Energy'
        },
        {
            'title': 'Use Energy-Efficient Lighting',
            'description': 'Replace conventional lighting with LED fixtures to reduce electricity consumption by 50-70%.',
            'impact': 'Medium',
            'cost': 300000,
            'category': 'Energy'
        },
        {
            'title': 'Energy Monitoring System',
            'description': 'Install real-time energy monitoring to identify waste patterns and optimize consumption, reducing usage by 10-20%.',
            'impact': 'Medium',
            'cost': 400000,
            'category': 'Energy'
        },
        {
            'title': 'Peak Load Management',
            'description': 'Implement strategies to shift energy-intensive operations to off-peak hours, reducing costs and grid strain.',
            'impact': 'Low',
            'cost': 150000,
            'category': 'Energy'
        }
    ]
    
    # Transport-related recommendations
    transport_recommendations = [
        {
            'title': 'Optimize Logistics',
            'description': 'Implement route optimization software and increase local sourcing of materials to reduce transport emissions by 15-25%.',
            'impact': 'Medium',
            'cost': 300000,
            'category': 'Logistics'
        },
        {
            'title': 'Use Low-Emission Vehicles',
            'description': 'Replace older diesel trucks with newer, more efficient models or consider alternative fuel vehicles, reducing emissions by 20-30%.',
            'impact': 'Medium',
            'cost': 1500000,
            'category': 'Logistics'
        },
        {
            'title': 'Consolidate Deliveries',
            'description': 'Coordinate with suppliers to consolidate deliveries, reducing the number of trips and associated emissions by 10-20%.',
            'impact': 'Low',
            'cost': 100000,
            'category': 'Logistics'
        },
        {
            'title': 'Intermodal Transportation',
            'description': 'Use rail or water transport for long-distance material movement where possible, reducing emissions by 40-70%.',
            'impact': 'High',
            'cost': 800000,
            'category': 'Logistics'
        }
    ]
    
    # General recommendations
    general_recommendations = [
        {
            'title': 'Conduct Energy Audit',
            'description': 'Perform a comprehensive energy audit to identify additional energy-saving opportunities across all operations.',
            'impact': 'Medium',
            'cost': 250000,
            'category': 'General'
        },
        {
            'title': 'Implement Waste Management Plan',
            'description': 'Develop and implement a construction waste management plan to reduce landfill waste by 30-50% and associated emissions.',
            'impact': 'Medium',
            'cost': 400000,
            'category': 'General'
        },
        {
            'title': 'Carbon Capture Technology',
            'description': 'Explore emerging carbon capture technologies for high-emission processes like concrete production.',
            'impact': 'High',
            'cost': 3500000,
            'category': 'General'
        },
        {
            'title': 'Employee Training Program',
            'description': 'Implement sustainability training for all employees to foster emission-reducing behaviors and practices.',
            'impact': 'Low',
            'cost': 300000,
            'category': 'General'
        }
    ]
    
    # Project-type specific recommendations
    project_specific_recommendations = []
    if project_type:
        if 'Building' in project_type or 'Construction' in project_type:
            project_specific_recommendations.extend([
                {
                    'title': 'Implement Green Building Practices',
                    'description': 'Adopt green building standards like LEED or IGBC to improve overall sustainability and reduce operational emissions.',
                    'impact': 'High',
                    'cost': 1000000,
                    'category': 'General'
                },
                {
                    'title': 'Optimize Building Orientation',
                    'description': 'Design building orientation to maximize natural light and reduce artificial lighting needs by 15-25%.',
                    'impact': 'Medium',
                    'cost': 200000,
                    'category': 'Design'
                }
            ])
        elif 'Road' in project_type or 'Highway' in project_type:
            project_specific_recommendations.extend([
                {
                    'title': 'Use Permeable Pavement',
                    'description': 'Implement permeable pavement solutions to manage stormwater and reduce environmental impact.',
                    'impact': 'Medium',
                    'cost': 700000,
                    'category': 'Materials'
                },
                {
                    'title': 'Optimize Road Grade',
                    'description': 'Design road grades to minimize vehicle fuel consumption over the lifecycle of the road.',
                    'impact': 'Medium',
                    'cost': 400000,
                    'category': 'Design'
                }
            ])
    
    # Select recommendations based on emission profile
    all_recommendations = []
    
    # Add recommendations based on emission hotspots
    if materials_emissions > total_emissions * 0.3:  # If materials account for >30% of emissions
        all_recommendations.extend(material_recommendations)
    
    if equipment_emissions > total_emissions * 0.2:  # If equipment account for >20% of emissions
        all_recommendations.extend(equipment_recommendations)
    
    if electricity_emissions > total_emissions * 0.15:  # If electricity account for >15% of emissions
        all_recommendations.extend(energy_recommendations)
    
    if transport_emissions > total_emissions * 0.25:  # If transport account for >25% of emissions
        all_recommendations.extend(transport_recommendations)
    
    # Always include some general recommendations
    all_recommendations.extend(general_recommendations)
    
    # Add project-specific recommendations
    all_recommendations.extend(project_specific_recommendations)
    
    # If no specific issues found, provide a broader set of recommendations
    if not all_recommendations:
        all_recommendations.extend(material_recommendations[:2])
        all_recommendations.extend(equipment_recommendations[:2])
        all_recommendations.extend(energy_recommendations[:1])
        all_recommendations.extend(transport_recommendations[:1])
        all_recommendations.extend(general_recommendations[:2])
    
    # Remove duplicates by title
    unique_recommendations = []
    seen_titles = set()
    
    for rec in all_recommendations:
        if rec['title'] not in seen_titles:
            seen_titles.add(rec['title'])
            unique_recommendations.append(rec)
    
    return unique_recommendations


@app.route('/refresh-recommendations/<project_id>', methods=['POST'])
def refresh_recommendations(project_id):
    try:
        if 'user_id' not in session:
            return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Check project ownership
        cur.execute("SELECT user_id FROM projects WHERE id = %s", (project_id,))
        project = cur.fetchone()
        if not project or project[0] != session['user_id']:
            cur.close()
            conn.close()
            return jsonify({"status": "error", "message": "Unauthorized access to project"}), 403
        
        # Get current project data including emissions
        cur.execute("""
            SELECT p.type, 
                   e.asphalt_t, e.aggregate_t, e.cement_t, e.steel_t,
                   e.diesel_l, e.electricity_kwh, e.transport_tkm,
                   e.water_use, e.waste_t, e.recycled_pct, e.renewable_pct
            FROM projects p
            LEFT JOIN emissions e ON p.id = e.project_id
            WHERE p.id = %s
        """, (project_id,))
        
        project_data = cur.fetchone()
        if not project_data:
            cur.close()
            conn.close()
            return jsonify({"status": "error", "message": "Project data not found"}), 404
        
        # Convert to dictionary format for calculate_emissions_data
        data = {
            'project_type': project_data[0],
            'asphalt_t': project_data[1] or 0,
            'aggregate_t': project_data[2] or 0,
            'cement_t': project_data[3] or 0,
            'steel_t': project_data[4] or 0,
            'diesel_l': project_data[5] or 0,
            'electricity_kwh': project_data[6] or 0,
            'transport_tkm': project_data[7] or 0,
            'water_use': project_data[8] or 0,
            'waste_t': project_data[9] or 0,
            'recycled_pct': project_data[10] or 0,
            'renewable_pct': project_data[11] or 0
        }
        
        # Calculate current emissions
        emission_data = calculate_emissions_data(data)
        
        # Generate NEW recommendations based on current data
        recommendations = generate_recommendations(emission_data, data['project_type'])
        
        # Select 2 unique recommendations to return
        selected_recommendations = []
        seen_titles = set()
        
        # Try to get diverse recommendations (different categories)
        category_priority = ['Materials', 'Equipment', 'Energy', 'Logistics', 'General']
        categorized_recs = {category: [] for category in category_priority}
        
        for rec in recommendations:
            category = rec.get('category', 'General')
            if category in categorized_recs:
                categorized_recs[category].append(rec)
        
        # Select one recommendation from high priority categories first
        for category in category_priority:
            if categorized_recs[category] and len(selected_recommendations) < 2:
                rec = random.choice(categorized_recs[category])
                if rec['title'] not in seen_titles:
                    selected_recommendations.append(rec)
                    seen_titles.add(rec['title'])
        
        # If we still need more, select randomly from all
        while len(selected_recommendations) < 2 and recommendations:
            rec = random.choice(recommendations)
            if rec['title'] not in seen_titles:
                selected_recommendations.append(rec)
                seen_titles.add(rec['title'])
        
        cur.close()
        conn.close()
        
        return jsonify({
            "status": "success", 
            "recommendations": selected_recommendations,
            "message": "New recommendations generated based on current project data"
        })
    except Exception as e:
        if 'conn' in locals():
            conn.rollback()
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()
        return jsonify({"status": "error", "message": "Server error. Please try again later or contact support."}), 500


# ====================================
# MIDDLEWARE
# ====================================
@app.before_request
def require_auth():
    if request.endpoint == 'static':
        return
    
    auth_routes = [
        'public_home', 'login', 'register', 
        'download_report', 'download_project_report',
        'verify_session'
    ]
    
    if request.endpoint not in auth_routes and 'user_id' not in session:
        return redirect(url_for('login'))
    

# ====================================
# AUTHENTICATION ROUTES
# ====================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        try:
            conn = get_db_connection() # Admin/Raw connection for login lookup
            cur = conn.cursor()
            # Updated to fetch role and use password_hash
            cur.execute("SELECT id, password_hash, role FROM users WHERE username = %s", (username,))
            user = cur.fetchone()
            cur.close()
            conn.close()
            
            if user and check_password_hash(user[1], password):
                session['user_id'] = user[0]
                session['username'] = username
                session['role'] = user[2] if len(user) > 2 and user[2] else 'user'
                return redirect(url_for('dashboard'))
            else:
                return render_template('login.html', error='Invalid credentials')
        except Exception as e:
            return render_template('login.html', error=str(e))
    
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        password_hash = generate_password_hash(password)
        
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO users (username, email, password_hash, role) VALUES (%s, %s, %s, 'user') RETURNING id",
                (username, email, password_hash)
            )
            user_id = cur.fetchone()[0]
            conn.commit()
            cur.close()
            conn.close()
            
            session['user_id'] = user_id
            session['username'] = username
            return redirect(url_for('dashboard'))
        except Exception as e:
            return render_template('register.html', error=str(e))
    
    return render_template('register.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('public_home'))


@app.route('/verify-session')
def verify_session():
    if 'user_id' in session:
        return jsonify({
            "status": "success",
            "user_id": session['user_id'],
            "username": session.get('username', '')
        })
    return jsonify({"status": "error"}), 401


@app.context_processor
def inject_user_context():
    return dict(
        current_user_name=session.get('username'),
        current_user_role=session.get('role', 'user')
    )

# ====================================
# PUBLIC ROUTES
# ====================================
@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('public_home')) 


@app.route('/home')
def public_home():
    username = session.get('username') if 'user_id' in session else None
    return render_template('index.html', username=username)


# ====================================
# PROJECT STATUS CALCULATION HELPER
# ====================================
def calculate_project_status(start_date, end_date):
    """Calculate project status based on current date and project dates"""
    today = date.today()
    
    # Handle different date formats
    if isinstance(start_date, str):
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        except ValueError:
            return "Unknown"
    
    if isinstance(end_date, str):
        try:
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return "Unknown"
    
    # Check if dates are valid
    if not start_date or not end_date:
        return "Unknown"
    
    if today < start_date:
        return "Planning"
    elif start_date <= today <= end_date:
        return "In Progress"
    elif today > end_date:
        return "Completed"
    else:
        return "Unknown"


# ====================================
# DASHBOARD & PROJECT ROUTES
# ====================================
@app.route('/dashboard')
def dashboard():
    try:
        conn = get_secure_db_connection()
        cur = conn.cursor()
        
        # Get user's projects with aggregated data
        cur.execute("""
            SELECT p.id, p.name, p.type, p.start_date, p.end_date,
                COALESCE(SUM(
                    e.asphalt_t * ef_asphalt.co2e_per_unit +
                    e.aggregate_t * ef_aggregate.co2e_per_unit +
                    e.cement_t * ef_cement.co2e_per_unit +
                    e.steel_t * ef_steel.co2e_per_unit +
                    e.diesel_l * ef_diesel.co2e_per_unit +
                    e.electricity_kwh * ef_electricity.co2e_per_unit +
                    e.transport_tkm * ef_transport.co2e_per_unit
                ) / 1000, 0) AS total_co2e_tons,
                COALESCE(SUM(cc.credits_earned), 0) AS credits
            FROM projects p
            LEFT JOIN emissions e ON p.id = e.project_id
            LEFT JOIN carbon_credits cc ON p.id = cc.project_id
            JOIN emission_factors ef_asphalt ON ef_asphalt.name = 'Asphalt'
            JOIN emission_factors ef_aggregate ON ef_aggregate.name = 'Aggregate'
            JOIN emission_factors ef_cement ON ef_cement.name = 'Cement'
            JOIN emission_factors ef_steel ON ef_steel.name = 'Steel'
            JOIN emission_factors ef_diesel ON ef_diesel.name = 'Diesel'
            JOIN emission_factors ef_electricity ON ef_electricity.name = 'Electricity'
            JOIN emission_factors ef_transport ON ef_transport.name = 'Transport'
            WHERE p.user_id = %s
            GROUP BY p.id, p.name, p.type, p.start_date, p.end_date
        """, (session['user_id'],))
        
        projects = []
        total_co2e_tons = 0.0  # Initialize as float
        total_credits = 0.0    # Initialize as float
        
        for row in cur.fetchall():
            project_id = row[0]
            # Convert to float to avoid Decimal issues
            total_co2e_kg = float(row[5]) * 1000  # Convert back to kg for reduction calculation
            
            # Calculate status based on dates
            start_date = row[3]
            end_date = row[4]
            status = calculate_project_status(start_date, end_date) if start_date and end_date else "Unknown"
            
            # Convert to float and calculate reduction percentage
            co2e_tons = float(row[5])
            credits = float(row[6])
            reduction_pct = (credits * 1000 / total_co2e_kg * 100) if total_co2e_kg > 0 else 0
            reduction_pct = round(reduction_pct, 2)
            
            projects.append({
                'id': row[0],
                'name': row[1],
                'type': row[2],
                'date': row[3].strftime('%Y-%m-%d') if row[3] else '',
                'co2e': co2e_tons,
                'credits': credits,
                'reduction': reduction_pct,
                'status': status  # Use calculated status
            })
            total_co2e_tons += co2e_tons
            total_credits += credits

        # Calculate emissions by scope
        cur.execute("""
            SELECT 
                SUM(e.diesel_l * ef_diesel.co2e_per_unit) / 1000 AS scope1,
                SUM(e.electricity_kwh * ef_electricity.co2e_per_unit) / 1000 AS scope2,
                SUM(
                    e.asphalt_t * ef_asphalt.co2e_per_unit +
                    e.aggregate_t * ef_aggregate.co2e_per_unit +
                    e.cement_t * ef_cement.co2e_per_unit +
                    e.steel_t * ef_steel.co2e_per_unit +
                    e.transport_tkm * ef_transport.co2e_per_unit
                ) / 1000 AS scope3
            FROM emissions e
            JOIN projects p ON e.project_id = p.id
            JOIN emission_factors ef_diesel ON ef_diesel.name = 'Diesel'
            JOIN emission_factors ef_electricity ON ef_electricity.name = 'Electricity'
            JOIN emission_factors ef_asphalt ON ef_asphalt.name = 'Asphalt'
            JOIN emission_factors ef_aggregate ON ef_aggregate.name = 'Aggregate'
            JOIN emission_factors ef_cement ON ef_cement.name = 'Cement'
            JOIN emission_factors ef_steel ON ef_steel.name = 'Steel'
            JOIN emission_factors ef_transport ON ef_transport.name = 'Transport'
            WHERE p.user_id = %s
        """, (session['user_id'],))
        
        scopes_row = cur.fetchone()
        # Convert all values to float
        scopes = {
            'scope1': float(scopes_row[0]) if scopes_row[0] else 0.0,
            'scope2': float(scopes_row[1]) if scopes_row[1] else 0.0,
            'scope3': float(scopes_row[2]) if scopes_row[2] else 0.0
        }

        # Generate month labels for the last 6 months
        months = []
        today = datetime.now()
        for i in range(5, -1, -1):  # Last 6 months including current
            month_date = today - timedelta(days=30*i)
            months.append(month_date.strftime('%b %Y'))

        # Initialize with zeros as floats
        timeline_actual = [0.0] * 6
        timeline_projected = [0.0] * 6

        # Get project emissions with dates
        cur.execute("""
            SELECT 
                p.id,
                p.start_date,
                p.end_date,
                COALESCE(SUM(
                    e.asphalt_t * ef_asphalt.co2e_per_unit +
                    e.aggregate_t * ef_aggregate.co2e_per_unit +
                    e.cement_t * ef_cement.co2e_per_unit +
                    e.steel_t * ef_steel.co2e_per_unit +
                    e.diesel_l * ef_diesel.co2e_per_unit +
                    e.electricity_kwh * ef_electricity.co2e_per_unit +
                    e.transport_tkm * ef_transport.co2e_per_unit
                ) / 1000, 0) AS total_emissions_tons
            FROM projects p
            LEFT JOIN emissions e ON p.id = e.project_id
            JOIN emission_factors ef_asphalt ON ef_asphalt.name = 'Asphalt'
            JOIN emission_factors ef_aggregate ON ef_aggregate.name = 'Aggregate'
            JOIN emission_factors ef_cement ON ef_cement.name = 'Cement'
            JOIN emission_factors ef_steel ON ef_steel.name = 'Steel'
            JOIN emission_factors ef_diesel ON ef_diesel.name = 'Diesel'
            JOIN emission_factors ef_electricity ON ef_electricity.name = 'Electricity'
            JOIN emission_factors ef_transport ON ef_transport.name = 'Transport'
            WHERE p.user_id = %s
            GROUP BY p.id, p.start_date, p.end_date
        """, (session['user_id'],))

        projects_emissions = cur.fetchall()

        # For each project, distribute emissions across its duration
        for project in projects_emissions:
            project_id, start_date, end_date, total_emissions = project
            
            # Convert to float to avoid Decimal issues
            total_emissions_float = float(total_emissions) if total_emissions else 0.0
            
            if not start_date or not end_date or total_emissions_float == 0:
                continue
                
            # Convert to datetime objects if they aren't already
            if isinstance(start_date, str):
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            if isinstance(end_date, str):
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            
            # Calculate project duration in days
            duration_days = (end_date - start_date).days
            if duration_days <= 0:
                continue
                
            # Calculate daily emissions rate
            daily_emissions = total_emissions_float / duration_days
            
            # For each month in our timeline, calculate how many project days fall in that month
            for i, month_label in enumerate(months):
                # Parse month label to get month and year
                month_str, year_str = month_label.split()
                month_num = list(calendar.month_abbr).index(month_str[:3])
                year_num = int(year_str)
                
                # Get first and last day of the month
                _, month_days = calendar.monthrange(year_num, month_num)
                month_start = date(year_num, month_num, 1)
                month_end = date(year_num, month_num, month_days)
                
                # Calculate overlap between project dates and this month
                overlap_start = max(start_date, month_start)
                overlap_end = min(end_date, month_end)
                
                if overlap_start <= overlap_end:
                    overlap_days = (overlap_end - overlap_start).days + 1
                    month_emissions = daily_emissions * overlap_days
                    timeline_actual[i] += month_emissions  # Now both are floats

        # Calculate projected values (90% of actual)
        timeline_projected = [val * 0.9 for val in timeline_actual]

        # Create timeline object
        timeline = {
            'labels': months,
            'actual': timeline_actual,
            'projected': timeline_projected
        }
        
        cur.close()
        conn.close()
        
        return render_template('dashboard.html', 
                               projects=projects, 
                               total_co2e=total_co2e_tons,
                               total_credits=total_credits,
                               username=session.get('username', 'User'),
                               scopes=scopes,
                               timeline=timeline)
    except Exception as e:
        return render_template('error.html', error=str(e))


def update_project_statuses():
    try:
        # Status update can be done via secure connection (role defaults to user or admin if scheduled)
        # Assuming run by a logged in user trigger or system. 
        # If system, we might need a bypass or specific user. 
        # For now, let's keep raw connection for background tasks or safe updates, 
        # but if this is user-triggered, it should probably be secure.
        # Given it runs on dashboard load logic (maybe?), actually it's separate.
        # Let's use get_db_connection() for system maintenance to avoid RLS hiding things.
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get all projects
        cur.execute("SELECT id, start_date, end_date, status FROM projects")
        projects = cur.fetchall()
        
        for project in projects:
            project_id, start_date, end_date, current_status = project
            if start_date and end_date:
                new_status = calculate_project_status(start_date, end_date)
                if new_status != current_status:
                    cur.execute(
                        "UPDATE projects SET status = %s WHERE id = %s",
                        (new_status, project_id)
                    )
        
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error updating project statuses: {e}")


@app.route('/new-project')
def new_project():
    username = session.get('username') if 'user_id' in session else None
    return render_template('new_project.html', username=username)


@app.route('/save-project', methods=['POST'])
def save_project():
    if 'user_id' not in session:
        return jsonify({
            "status": "error", 
            "message": "Session expired. Please log in again.",
            "redirect": url_for('login')
        }), 401

    try:
        data = request.get_json()
        if not data:
            raise ValueError("No JSON data received")
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": "Invalid request format: " + str(e)
        }), 400
    
    # Validate dates
    try:
        start_date = datetime.strptime(data.get('start_date'), '%Y-%m-%d').date()
        end_date = datetime.strptime(data.get('end_date'), '%Y-%m-%d').date()
        
        if end_date < start_date:
            return jsonify({
                "status": "error",
                "message": "End date cannot be before start date"
            }), 400
            
        # Calculate status based on dates
        status = calculate_project_status(start_date, end_date)
    except (TypeError, ValueError) as e:
        return jsonify({
            "status": "error",
            "message": "Invalid date format. Use YYYY-MM-DD"
        }), 400

    try:
        conn = get_secure_db_connection()
        cur = conn.cursor()
        
        # Create new project with calculated status
        cur.execute(
            "INSERT INTO projects (name, type, location, start_date, end_date, user_id) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
            (data.get('project_name', 'New Project'),
            data.get('project_type', 'Infrastructure'),
            data.get('location', ''),
            data.get('start_date'),
            data.get('end_date'),
            session['user_id'])
        )
        project_id = cur.fetchone()[0]
        
        numeric_fields = ['asphalt_t', 'aggregate_t', 'cement_t', 'steel_t', 'diesel_l', 
                 'electricity_kwh', 'transport_tkm', 'water_use', 'waste_t',
                 'recycled_pct', 'renewable_pct']
        for field in numeric_fields:
            if field in data and data[field] in ['', None]:
                data[field] = 0

        # Save emissions data
        cur.execute(
            """INSERT INTO emissions (project_id, asphalt_t, aggregate_t, cement_t, steel_t, 
            diesel_l, electricity_kwh, transport_tkm, water_use, waste_t, recycled_pct, renewable_pct, calculated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())""",
            (project_id,
             data.get('asphalt_t', 0) or 0,
             data.get('aggregate_t', 0) or 0,
             data.get('cement_t', 0) or 0,
             data.get('steel_t', 0) or 0,
             data.get('diesel_l', 0) or 0,
             data.get('electricity_kwh', 0) or 0,
             data.get('transport_tkm', 0) or 0,
             data.get('water_use', 0) or 0,
             data.get('waste_t', 0) or 0,
             data.get('recycled_pct', 0) or 0,
             data.get('renewable_pct', 0) or 0)
        )
        
        # Calculate emissions for credits
        result = calculate_emissions_data(data)
        
        # Save carbon credits
        cur.execute(
            "INSERT INTO carbon_credits (project_id, credits_earned, credit_value) VALUES (%s, %s, %s)",
            (project_id, result['credits'], result['credits'] * 1000)  # Assuming ₹1000 per credit
        )
        
        # Generate recommendations based on project data and type
        project_type = data.get('project_type', '')
        recommendations = generate_recommendations(result, project_type)

        # Remove any duplicate recommendations
        unique_recommendations = []
        seen_titles = set()

        for rec in recommendations:
            if rec['title'] not in seen_titles:
                seen_titles.add(rec['title'])
                unique_recommendations.append(rec)

        # Save unique recommendations
        for i, rec in enumerate(unique_recommendations):
            try:
                cur.execute(
                    "INSERT INTO recommendations (project_id, title, description, impact, cost, category) VALUES (%s, %s, %s, %s, %s, %s)",
                    (project_id, rec['title'], rec['description'], rec['impact'], rec['cost'], rec.get('category', 'General'))
                )
            except psycopg2.Error as e:
                # If category column doesn't exist, insert without it
                cur.execute(
                    "INSERT INTO recommendations (project_id, title, description, impact, cost) VALUES (%s, %s, %s, %s, %s)",
                    (project_id, rec['title'], rec['description'], rec['impact'], rec['cost'])
                )
        
        conn.commit()
        return jsonify({
            "status": "success",
            "project_id": project_id,
            "redirect_url": f"/project/{project_id}"
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/project/<project_id>')
def project_detail(project_id):
    try:
        conn = get_secure_db_connection()
        cur = conn.cursor()
        
        # Get project details with emissions
        cur.execute("""
            SELECT p.id, p.name, p.type, p.location, p.start_date, p.end_date,
                COALESCE(SUM(
                    e.asphalt_t * ef_asphalt.co2e_per_unit +
                    e.aggregate_t * ef_aggregate.co2e_per_unit +
                    e.cement_t * ef_cement.co2e_per_unit +
                    e.steel_t * ef_steel.co2e_per_unit +
                    e.diesel_l * ef_diesel.co2e_per_unit +
                    e.electricity_kwh * ef_electricity.co2e_per_unit +
                    e.transport_tkm * ef_transport.co2e_per_unit
                ) / 1000, 0) AS total_co2e_tons,
                COALESCE(SUM(cc.credits_earned), 0) AS credits
            FROM projects p
            LEFT JOIN emissions e ON p.id = e.project_id
            LEFT JOIN carbon_credits cc ON p.id = cc.project_id
            JOIN emission_factors ef_asphalt ON ef_asphalt.name = 'Asphalt'
            JOIN emission_factors ef_aggregate ON ef_aggregate.name = 'Aggregate'
            JOIN emission_factors ef_cement ON ef_cement.name = 'Cement'
            JOIN emission_factors ef_steel ON ef_steel.name = 'Steel'
            JOIN emission_factors ef_diesel ON ef_diesel.name = 'Diesel'
            JOIN emission_factors ef_electricity ON ef_electricity.name = 'Electricity'
            JOIN emission_factors ef_transport ON ef_transport.name = 'Transport'
            WHERE p.id = %s AND p.user_id = %s
            GROUP BY p.id, p.name, p.type, p.location, p.start_date, p.end_date
        """, (project_id, session['user_id']))
        
        project = cur.fetchone()
        if not project:
            return redirect(url_for('dashboard'))

        # Calculate status based on dates
        start_date = project[4]  # index 4 is start_date
        end_date = project[5]    # index 5 is end_date
        status = calculate_project_status(start_date, end_date) if start_date and end_date else "Unknown"

        # Convert to float
        total_co2e_tons = float(project[6]) if project[6] else 0.0
        credits = float(project[7]) if project[7] else 0.0

        # Calculate and round reduction percentage
        total_co2e_kg = total_co2e_tons * 1000
        reduction_kg = credits * 1000
        reduction_pct = (reduction_kg / total_co2e_kg * 100) if total_co2e_kg > 0 else 0
        reduction_pct = round(reduction_pct, 2)

        project_data = {
            'id': project[0],
            'name': project[1],
            'type': project[2],
            'location': project[3],
            'date': project[4].strftime('%Y-%m-%d') if project[4] else '',
            'co2e': total_co2e_tons,
            'credits': credits,
            'reduction': reduction_pct,
            'status': status  # Use calculated status
        }
        
        # Get breakdown data
        cur.execute("""
            SELECT 
                SUM(e.asphalt_t * ef_asphalt.co2e_per_unit) / 1000 AS asphalt,
                SUM(e.aggregate_t * ef_aggregate.co2e_per_unit) / 1000 AS aggregate,
                SUM(e.cement_t * ef_cement.co2e_per_unit) / 1000 AS cement,
                SUM(e.steel_t * ef_steel.co2e_per_unit) / 1000 AS steel,
                SUM(e.diesel_l * ef_diesel.co2e_per_unit) / 1000 AS diesel,
                SUM(e.electricity_kwh * ef_electricity.co2e_per_unit) / 1000 AS electricity,
                SUM(e.transport_tkm * ef_transport.co2e_per_unit) / 1000 AS transport
            FROM emissions e
            JOIN emission_factors ef_asphalt ON ef_asphalt.name = 'Asphalt'
            JOIN emission_factors ef_aggregate ON ef_aggregate.name = 'Aggregate'
            JOIN emission_factors ef_cement ON ef_cement.name = 'Cement'
            JOIN emission_factors ef_steel ON ef_steel.name = 'Steel'
            JOIN emission_factors ef_diesel ON ef_diesel.name = 'Diesel'
            JOIN emission_factors ef_electricity ON ef_electricity.name = 'Electricity'
            JOIN emission_factors ef_transport ON ef_transport.name = 'Transport'
            WHERE e.project_id = %s
        """, (project_id,))
        
        breakdown_row = cur.fetchone()
        if breakdown_row:
            values = [float(val) if val is not None else 0.0 for val in breakdown_row]
        else:
            values = [0.0] * 7
        breakdown = {
            "labels": ["Asphalt", "Aggregate", "Cement", "Steel", "Diesel", "Electricity", "Transport"],
            "values": values  # Use converted values
        }

        cur.execute("""
            SELECT 
                'Materials' AS category,
                SUM(
                    e.asphalt_t * ef_asphalt.co2e_per_unit +
                    e.aggregate_t * ef_aggregate.co2e_per_unit +
                    e.cement_t * ef_cement.co2e_per_unit +
                    e.steel_t * ef_steel.co2e_per_unit
                ) / 1000 AS emissions
            FROM emissions e
            JOIN emission_factors ef_asphalt ON ef_asphalt.name = 'Asphalt'
            JOIN emission_factors ef_aggregate ON ef_aggregate.name = 'Aggregate'
            JOIN emission_factors ef_cement ON ef_cement.name = 'Cement'
            JOIN emission_factors ef_steel ON ef_steel.name = 'Steel'
            WHERE e.project_id = %s
            
            UNION ALL
            
            SELECT 
                'Equipment' AS category,
                SUM(e.diesel_l * ef_diesel.co2e_per_unit) / 1000
            FROM emissions e
            JOIN emission_factors ef_diesel ON ef_diesel.name = 'Diesel'
            WHERE e.project_id = %s
            
            UNION ALL
            
            SELECT 
                'Electricity' AS category,
                SUM(e.electricity_kwh * ef_electricity.co2e_per_unit) / 1000
            FROM emissions e
            JOIN emission_factors ef_electricity ON ef_electricity.name = 'Electricity'
            WHERE e.project_id = %s
            
            UNION ALL
            
            SELECT 
                'Transport' AS category,
                SUM(e.transport_tkm * ef_transport.co2e_per_unit) / 1000
            FROM emissions e
            JOIN emission_factors ef_transport ON ef_transport.name = 'Transport'
            WHERE e.project_id = %s
        """, (project_id, project_id, project_id, project_id))
        
        categories_data = cur.fetchall()
        categories = {
            'labels': [row[0] for row in categories_data],
            'values': [float(row[1]) if row[1] else 0.0 for row in categories_data]
        }

        # Get recommendations from database
        try:
            # Try to get all columns if they exist
            cur.execute("SELECT title, description, impact, cost, category FROM recommendations WHERE project_id = %s ORDER BY display_order", (project_id,))
        except psycopg2.Error as e:
            # If is_active column doesn't exist, get all recommendations
            cur.execute("SELECT title, description, impact, cost FROM recommendations WHERE project_id = %s LIMIT 2", (project_id,))

        recommendations = []
        for row in cur.fetchall():
            if len(row) == 5:  # With category
                recommendations.append({
                    'title': row[0],
                    'description': row[1],
                    'impact': row[2],
                    'cost': float(row[3]) if row[3] else 0.0,
                    'category': row[4] or 'General'
                })
            else:  # Without category
                recommendations.append({
                    'title': row[0],
                    'description': row[1],
                    'impact': row[2],
                    'cost': float(row[3]) if row[3] else 0.0,
                    'category': 'General'
                })
                
                cur.close()
                conn.close()
        
        return render_template('project_detail.html', 
                            project=project_data, 
                            breakdown=breakdown,
                            categories=categories,
                            recommendations=recommendations,  # Pass recommendations to template
                            username=session.get('username', 'User'))
    except Exception as e:
        return render_template('error.html', error=str(e))


@app.route('/carbon/credit/new', methods=['GET'])
def new_carbon_credit():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # Get user's projects
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM projects WHERE user_id = %s", (session['user_id'],))
    projects = [{'id': row[0], 'name': row[1]} for row in cur.fetchall()]
    cur.close()
    conn.close()
    
    return render_template('add_credit.html', 
                           projects=projects, 
                           username=session.get('username', 'User'))


@app.route('/carbon/credit', methods=['POST'])
def add_carbon_credit():
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    
    project_id = request.form['project_id']
    credits_earned = request.form['credits_earned']
    credit_value = request.form['credit_value']
    issued_at = request.form['issued_at'] or datetime.now().date()
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verify project belongs to user
        cur.execute("SELECT id FROM projects WHERE id = %s AND user_id = %s", 
                   (project_id, session['user_id']))
        if not cur.fetchone():
            return jsonify({"status": "error", "message": "Invalid project"}), 400
        
        cur.execute(
            "INSERT INTO carbon_credits (user_id, project_id, credits_earned, credit_value, issued_at) VALUES (%s, %s, %s, %s, %s)",
            (session['user_id'], project_id, credits_earned, credit_value, issued_at)
        )
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({"status": "success", "message": "Credit added successfully"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/carbon/credit/<credit_id>/edit', methods=['GET'])
def edit_carbon_credit_form(credit_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get credit details with project verification
        cur.execute("""
            SELECT cc.id, cc.project_id, cc.credits_earned, cc.credit_value, cc.issued_at, p.name
            FROM carbon_credits cc
            JOIN projects p ON cc.project_id = p.id
            WHERE cc.id = %s AND p.user_id = %s
        """, (credit_id, session['user_id']))
        credit = cur.fetchone()
        
        if not credit:
            return redirect(url_for('carbon'))
        
        credit_data = {
            'id': credit[0],
            'project_id': credit[1],
            'credits_earned': credit[2],
            'credit_value': credit[3],
            'issued_at': credit[4].strftime('%Y-%m-%d') if credit[4] else '',
            'project_name': credit[5]
        }

        
        cur.close()
        conn.close()
        
        return render_template('edit_credit.html', credit=credit_data, username=session.get('username', 'User'))
    except Exception as e:
        return render_template('error.html', error=str(e))


@app.route('/carbon/credit/<credit_id>', methods=['PUT'])
def update_carbon_credit(credit_id):
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    
    credits_earned = request.form['credits_earned']
    credit_value = request.form['credit_value']
    issued_at = request.form['issued_at']
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verify credit belongs to user
        cur.execute("""
            SELECT cc.id 
            FROM carbon_credits cc
            JOIN projects p ON cc.project_id = p.id
            WHERE cc.id = %s AND p.user_id = %s
        """, (credit_id, session['user_id']))
        if not cur.fetchone():
            return jsonify({"status": "error", "message": "Unauthorized"}), 403
        
        cur.execute(
            "UPDATE carbon_credits SET credits_earned = %s, credit_value = %s, issued_at = %s WHERE id = %s",
            (credits_earned, credit_value, issued_at, credit_id)
        )
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({"status": "success", "message": "Credit updated successfully"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/carbon/credit/<credit_id>', methods=['DELETE'])
def delete_carbon_credit(credit_id):
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verify credit belongs to user
        cur.execute("""
            SELECT cc.id 
            FROM carbon_credits cc
            JOIN projects p ON cc.project_id = p.id
            WHERE cc.id = %s AND p.user_id = %s
        """, (credit_id, session['user_id']))
        if not cur.fetchone():
            return jsonify({"status": "error", "message": "Unauthorized"}), 403
        
        cur.execute("DELETE FROM carbon_credits WHERE id = %s", (credit_id,))
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({"status": "success", "message": "Credit deleted successfully"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ====================================
# REPORTING ROUTES
# ====================================
@app.route('/reports')
def reports():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get user's reports with project names
    cur.execute("""
        SELECT r.id, r.name, r.created_at, r.file_size, p.name as project_name
        FROM reports r
        LEFT JOIN projects p ON r.project_id = p.id
        WHERE r.user_id = %s
        ORDER BY r.created_at DESC
    """, (session['user_id'],))
    
    reports = []
    for row in cur.fetchall():
        # Convert file size to MB
        size_mb = f"{row[3]/1024/1024:.1f} MB" if row[3] else '0 MB'
        reports.append({
            'id': row[0],
            'name': row[1],
            'created_at': row[2],
            'size': size_mb,
            'project_name': row[4]  # Add project name
        })
    
    # Get projects for report generation
    cur.execute("SELECT id, name FROM projects WHERE user_id = %s", (session['user_id'],))
    projects = [{'id': row[0], 'name': row[1]} for row in cur.fetchall()]
    
    cur.close()
    conn.close()
    
    return render_template('reports.html', 
                           reports=reports, 
                           projects=projects,
                           username=session.get('username', 'User'))


# ====================================
# FILE UPLOAD ROUTE
# ====================================
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "No file part"})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "error", "message": "No selected file"})
    
    if file:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        try:
            # Read CSV file
            df = pd.read_csv(filepath)
            
            # Handle column name variations
            column_map = {
                'asphalt': 'asphalt_t',
                'aggregate': 'aggregate_t',
                'cement': 'cement_t',
                'concrete': 'cement_t',
                'steel': 'steel_t',
                'diesel': 'diesel_l',
                'power': 'electricity_kwh',
                'electricity': 'electricity_kwh',
                'transport': 'transport_tkm',
                'distance': 'transport_tkm'
            }
            
            # Rename columns
            df.rename(columns=column_map, inplace=True, errors='ignore')
            
            # Get required columns
            required_cols = ['project_name', 'project_type', 'asphalt_t', 'aggregate_t', 
                            'cement_t', 'steel_t', 'diesel_l', 'electricity_kwh', 'transport_tkm']
            
            if not all(col in df.columns for col in required_cols):
                return jsonify({"status": "error", "message": "CSV missing required columns"})
            
            conn = get_db_connection()
            cur = conn.cursor()
            
            # Create project
            cur.execute(
                "INSERT INTO projects (name, type, user_id, status) VALUES (%s, %s, %s, 'Active') RETURNING id",
                (df.iloc[0]['project_name'], 
                 df.iloc[0]['project_type'], 
                 session['user_id'])
            )
            project_id = cur.fetchone()[0]
            
            # Process each row
            for _, row in df.iterrows():
                cur.execute(
                    """INSERT INTO emissions (project_id, asphalt_t, aggregate_t, cement_t, steel_t, 
                    diesel_l, electricity_kwh, transport_tkm, water_use, waste_t, recycled_pct, renewable_pct)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (project_id,
                     row.get('asphalt_t', 0),
                     row.get('aggregate_t', 0),
                     row.get('cement_t', 0),
                     row.get('steel_t', 0),
                     row.get('diesel_l', 0),
                     row.get('electricity_kwh', 0),
                     row.get('transport_tkm', 0),
                     row.get('water_use', 0),
                     row.get('waste_t', 0),
                     row.get('recycled_pct', 0),
                     row.get('renewable_pct', 0))
                )
            
            # Calculate and save credits
            first_row = df.iloc[0].to_dict()
            result = calculate_emissions_data(first_row)
            cur.execute(
                "INSERT INTO carbon_credits (project_id, credits_earned, credit_value) VALUES (%s, %s, %s)",
                (project_id, result['credits'], result['credits'] * 1000))
            
            conn.commit()
            cur.close()
            conn.close()
            
            return jsonify({
                "status": "success",
                "project_id": project_id,
                "project_name": df.iloc[0]['project_name'],
                "credits": result['credits'],
                "co2e": result['total_co2e']
            })
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
    
    return jsonify({"status": "error", "message": "File upload failed"})



# ====================================
# PAYMENT ROUTE
# ====================================
@app.route('/api/payment/process', methods=['POST'])
def process_payment():
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    
    try:
        data = request.get_json()
        amount = data.get('amount')
        transaction_id = data.get('transaction_id') # Optional, for reference
        
        # Simulate payment processing (90% success rate)
        if random.random() < 0.9:
            return jsonify({
                "status": "success",
                "reference": f"PAY_{uuid.uuid4().hex[:12].upper()}",
                "message": "Payment processed successfully"
            })
        else:
            return jsonify({
                "status": "error",
                "message": "Payment failed. Please try again."
            }), 400
            
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ====================================
# MARKETPLACE ROUTES
# ====================================

@app.route('/marketplace/listings')
def marketplace_listings():
    try:
        conn = get_secure_db_connection()
        cur = conn.cursor()
        
        # Get active marketplace listings with project info
        cur.execute("""
            SELECT ml.id, ml.quantity_available, ml.price_per_credit, ml.listed_at,
                   p.name as project_name, p.type as project_type, p.location,
                   u.username as seller_name,
                   cc.credits_earned, cc.credits_used,
                   (cc.credits_earned - COALESCE(cc.credits_used, 0)) as total_available
            FROM marketplace_listings ml
            JOIN carbon_credits cc ON ml.credit_id = cc.id
            JOIN projects p ON cc.project_id = p.id
            JOIN users u ON ml.seller_id = u.id
            WHERE ml.status = 'active' AND ml.quantity_available > 0
            ORDER BY ml.listed_at DESC
        """)
        
        listings = []
        for row in cur.fetchall():
            listings.append({
                'id': row[0],
                'quantity_available': float(row[1]),
                'price_per_credit': float(row[2]),
                'listed_at': row[3],
                'project_name': row[4],
                'project_type': row[5],
                'project_location': row[6],
                'seller_name': row[7],
                'credits_earned': float(row[8]),
                'credits_used': float(row[9]) if row[9] else 0,
                'total_available': float(row[10]) if row[10] else 0
            })
        
        cur.close()
        conn.close()
        
        return jsonify({"status": "success", "listings": listings})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500





@app.route('/marketplace/list', methods=['POST'])
def list_credits():
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    try:
        data = request.get_json()
        credit_id = data.get('credit_id')
        quantity = data.get('quantity')
        price_per_credit = data.get('price_per_credit')
        
        if not credit_id or not quantity or not price_per_credit:
            return jsonify({"status": "error", "message": "Missing required fields"}), 400
        
        conn = get_secure_db_connection()
        cur = conn.cursor()
        
        # Verify the credit belongs to the user
        cur.execute("""
            SELECT cc.id, cc.project_id, cc.credits_earned, COALESCE(cc.credits_used, 0) as credits_used,
                   (cc.credits_earned - COALESCE(cc.credits_used, 0) - COALESCE(cc.listed_quantity, 0)) as available_credits
            FROM carbon_credits cc
            JOIN projects p ON cc.project_id = p.id
            WHERE cc.id = %s AND p.user_id = %s
        """, (credit_id, session['user_id']))
        
        credit = cur.fetchone()
        if not credit:
            return jsonify({"status": "error", "message": "Credit not found"}), 404
        
        project_id = credit[1]
        available_credits = float(credit[4])
        
        if quantity > available_credits:
            return jsonify({"status": "error", "message": "Not enough credits available"}), 400
        
        # Start transaction
        conn.autocommit = False
        
        try:
            # Create the marketplace listing
            cur.execute("""
                INSERT INTO marketplace_listings (credit_id, seller_id, quantity_available, price_per_credit, status)
                VALUES (%s, %s, %s, %s, 'active')
                RETURNING id
            """, (credit_id, session['user_id'], quantity, price_per_credit))
            
            listing_id = cur.fetchone()[0]
            
            # Update source credit: increase listed_quantity
            cur.execute("""
                UPDATE carbon_credits 
                SET listed_quantity = COALESCE(listed_quantity, 0) + %s,
                    status = 'PENDING'
                WHERE id = %s
            """, (quantity, credit_id))
            
            # Log transaction
            cur.execute("""
                INSERT INTO carbon_credit_transactions 
                (from_user_id, quantity, from_project_id, listing_id, transaction_type, status, price_per_credit, created_at)
                VALUES (%s, %s, %s, %s, 'LISTING', 'COMPLETED', %s, NOW())
            """, (session['user_id'], quantity, project_id, listing_id, price_per_credit))
            
            conn.commit()
            return jsonify({"status": "success", "listing_id": listing_id})
            
        except Exception as e:
            conn.rollback()
            raise e
            
    except Exception as e:
        if 'conn' in locals() and conn:
            conn.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if 'conn' in locals() and conn:
            conn.autocommit = True
            cur.close()
            conn.close()



@app.route('/marketplace/buy/<int:listing_id>', methods=['POST'])
def buy_credits(listing_id):
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    try:
        data = request.get_json()
        print(f"DEBUG: buy_credits data: {data}")
        quantity = float(data.get('quantity', 0))
        destination_project_id = data.get('destination_project_id')
        
        if not quantity or quantity <= 0:
            return jsonify({"status": "error", "message": "Invalid quantity"}), 400
            
        if not destination_project_id:
            return jsonify({"status": "error", "message": "Please select a destination project"}), 400
        
        conn = get_secure_db_connection()
        cur = conn.cursor()
        
        # 1. Validate destination project belongs to buyer
        cur.execute("SELECT id FROM projects WHERE id = %s AND user_id = %s", 
                   (destination_project_id, session['user_id']))
        if not cur.fetchone():
            return jsonify({"status": "error", "message": "Invalid destination project"}), 400
        
        # 2. Get the listing details
        cur.execute("""
            SELECT ml.id, ml.credit_id, ml.quantity_available, ml.price_per_credit, ml.seller_id,
                   cc.project_id as source_project_id
            FROM marketplace_listings ml
            JOIN carbon_credits cc ON ml.credit_id = cc.id
            WHERE ml.id = %s AND ml.status = 'active'
        """, (listing_id,))
        
        listing = cur.fetchone()
        if not listing:
            cur.close()
            conn.close()
            return jsonify({"status": "error", "message": "Listing not found"}), 404
        
        listing_id_db, source_credit_id, available_quantity, price_per_credit, seller_id, source_project_id = listing
        available_quantity = float(available_quantity)
        price_per_credit = float(price_per_credit)
        
        if seller_id == session['user_id']:
            return jsonify({"status": "error", "message": "Cannot buy your own credits"}), 400
        
        if quantity > available_quantity:
            return jsonify({"status": "error", "message": "Not enough credits available"}), 400
        
        total_price = quantity * price_per_credit
        
        # Start transaction
        conn.autocommit = False
        
        try:
            # 3. Process Logic:
            # - Create new credit record for buyer (Allocated to destination project)
            # - Update marketplace listing (reduce quantity)
            # - Update seller's credit record (reduce listed_quantity, increase credits_used)
            # - Log transaction
            
            # Update marketplace listing
            new_quantity = available_quantity - quantity
            new_status = 'active'
            if new_quantity <= 0:
                new_status = 'sold'
                new_quantity = 0 # Ensure no negative
                
            cur.execute("""
                UPDATE marketplace_listings 
                SET quantity_available = %s, status = %s 
                WHERE id = %s
            """, (new_quantity, new_status, listing_id))
            
            # Update source carbon credit (mark as used/transferred)
            # We reduce listed_quantity because it's no longer listed (it's sold)
            # We increase credits_used because it's effectively gone from seller
            cur.execute("""
                UPDATE carbon_credits 
                SET credits_used = COALESCE(credits_used, 0) + %s,
                    listed_quantity = GREATEST(COALESCE(listed_quantity, 0) - %s, 0)
                WHERE id = %s
            """, (quantity, quantity, source_credit_id))
            
            # Create new carbon credit for buyer
            # CRITICAL FIX: Explicitly set user_id
            cur.execute("""
                INSERT INTO carbon_credits 
                (user_id, project_id, credits_earned, credit_value, source, status, issued_at)
                VALUES (%s, %s, %s, %s, 'PURCHASED', 'AVAILABLE', NOW())
                RETURNING id
            """, (session['user_id'], destination_project_id, quantity, total_price))
            
            new_credit_id = cur.fetchone()[0]
            
            # Record the transaction
            cur.execute("""
                INSERT INTO carbon_credit_transactions 
                (from_user_id, to_user_id, quantity, from_project_id, to_project_id, listing_id, 
                 transaction_type, status, price_per_credit, total_price, payment_reference, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, 'PURCHASE', 'COMPLETED', %s, %s, 'DUMMY_PAYMENT', NOW())
            """, (seller_id, session['user_id'], quantity, source_project_id, destination_project_id, listing_id,
                  price_per_credit, total_price))
            
            conn.commit()
            
            return jsonify({
                "status": "success", 
                "message": "Purchase completed successfully",
                "credit_id": new_credit_id,
                "quantity": quantity,
                "total_price": total_price
            })
            
        except Exception as e:
            conn.rollback()
            raise e
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if 'conn' in locals() and conn:
            conn.autocommit = True
            try:
                cur.close()
            except:
                pass
            try:
                conn.close()
            except:
                pass


@app.route('/edit-project/<project_id>', methods=['GET','POST'])
def edit_project(project_id):
    if request.method == 'POST':
        # Process form data
        name = request.form['name']
        ptype = request.form['type']
        location = request.form['location']
        start_date = request.form['start_date']
        end_date = request.form['end_date']
        
        # Calculate status based on dates
        try:
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
            status = calculate_project_status(start_date_obj, end_date_obj)
        except (TypeError, ValueError):
            return "Invalid date format", 400
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE projects 
            SET name = %s, type = %s, location = %s, 
                start_date = %s, end_date = %s
            WHERE id = %s
        """, (name, ptype, location, start_date, end_date, project_id))
        conn.commit()
        cur.close()
        conn.close()
        
        return redirect(url_for('project_detail', project_id=project_id))
    else:
        # Show edit form
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM projects WHERE id = %s", (project_id,))
        project = cur.fetchone()
        cur.close()
        conn.close()
        
        if project:
            project_data = {
                'id': project[0],
                'name': project[1],
                'type': project[2],
                'location': project[3],
                'start_date': project[4].strftime('%Y-%m-%d') if project[4] else '',
                'end_date': project[5].strftime('%Y-%m-%d') if project[5] else '',
                'status': project[6] or 'Active'
            }
            return render_template('edit_project.html', 
                                   project=project_data,
                                   username=session.get('username', 'User'))
        return redirect(url_for('dashboard'))


@app.route('/delete-project/<project_id>', methods=['DELETE'])
def delete_project(project_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Check if project belongs to user
        cur.execute("SELECT user_id FROM projects WHERE id = %s", (project_id,))
        project = cur.fetchone()
        
        if not project or project[0] != session['user_id']:
            return jsonify({"status": "error", "message": "Unauthorized"}), 403
        
        # Delete project and related data
        cur.execute("DELETE FROM projects WHERE id = %s", (project_id,))
        conn.commit()
        
        cur.close()
        conn.close()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/calculate', methods=['POST'])
def calculate():
    # Get data from JSON
    data = request.get_json()
    
    # Convert empty strings to 0 for numeric fields
    numeric_fields = ['asphalt_t', 'aggregate_t', 'cement_t', 'steel_t', 'diesel_l', 
                     'electricity_kwh', 'transport_tkm', 'water_use', 'waste_t',
                     'recycled_pct', 'renewable_pct']
    for field in numeric_fields:
        if field in data and data[field] == '':
            data[field] = 0

    # Calculate emissions
    result = calculate_emissions_data(data)
    
    return jsonify({
        "status": "success",
        "result": result
    })


# ====================================
# CARBON CREDIT ROUTES
# ====================================
@app.route('/carbon')
def carbon():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get projects with their credit summaries
    cur.execute("""
        SELECT p.id AS project_id, p.name AS project_name,
               COALESCE(SUM(cc.credits_earned), 0) AS total_credits,
               COALESCE(SUM(cc.credits_used), 0) AS used_credits,
               COALESCE(SUM(cc.listed_quantity), 0) AS listed_credits,
               COALESCE(SUM(cc.credits_earned) - COALESCE(SUM(cc.credits_used), 0) - COALESCE(SUM(cc.listed_quantity), 0), 0) AS available_credits,
               MAX(cc.issued_at) AS last_issued
        FROM projects p
        LEFT JOIN carbon_credits cc ON p.id = cc.project_id
        WHERE p.user_id = %s
        GROUP BY p.id, p.name
        ORDER BY last_issued DESC NULLS LAST
    """, (session['user_id'],))
    
    projects = []
    total_all_credits = 0
    total_available_credits = 0
    
    for row in cur.fetchall():
        project_credits = float(row[2]) if row[2] is not None else 0.0
        available_credits = float(row[5]) if row[5] is not None else 0.0
        total_all_credits += project_credits
        total_available_credits += available_credits
        
        projects.append({
            'id': row[0],
            'name': row[1],
            'total_credits': project_credits,
            'used_credits': float(row[3]) if row[3] is not None else 0.0,
            'listed_credits': float(row[4]) if row[4] is not None else 0.0,
            'available_credits': available_credits,
            'last_issued': row[6].strftime('%Y-%m-%d') if row[6] else 'N/A'
        })
    
    # Get detailed issuances for each project
    for project in projects:
        cur.execute("""
            SELECT id, credits_earned, credits_used, listed_quantity, 
                   (credits_earned - COALESCE(credits_used, 0) - listed_quantity) as available_quantity,
                   credit_value, issued_at, status
            FROM carbon_credits
            WHERE project_id = %s
            ORDER BY issued_at DESC
        """, (project['id'],))
        
        issuances = []
        for row in cur.fetchall():
            issuances.append({
                'id': row[0],
                'credits_earned': float(row[1]) if row[1] is not None else 0.0,
                'credits_used': float(row[2]) if row[2] is not None else 0.0,
                'listed_quantity': float(row[3]) if row[3] is not None else 0.0,
                'available_quantity': float(row[4]) if row[4] is not None else 0.0,
                'credit_value': float(row[5]) if row[5] is not None else 0.0,
                'issued_at': row[6].strftime('%Y-%m-%d') if row[6] else 'N/A',
                'status': row[7]
            })
        project['issuances'] = issuances
    
    # Get marketplace credits
    cur.execute("""
        SELECT ml.id, ml.quantity_available, ml.price_per_credit, ml.listed_at, ml.status,
               p.name as project_name, p.type as project_type, p.location,
               u.username as seller_name,
               cc.credits_earned, cc.credits_used, cc.listed_quantity
        FROM marketplace_listings ml
        JOIN carbon_credits cc ON ml.credit_id = cc.id
        JOIN projects p ON cc.project_id = p.id
        JOIN users u ON ml.seller_id = u.id
        WHERE ml.status = 'active' AND ml.quantity_available > 0
        AND ml.seller_id != %s
        ORDER BY ml.listed_at DESC
    """, (session['user_id'],))
    
    marketplace_credits = []
    for row in cur.fetchall():
        marketplace_credits.append({
            'id': row[0],
            'quantity_available': float(row[1]),
            'price_per_credit': float(row[2]),
            'listed_at': row[3],
            'status': row[4],
            'project_name': row[5],
            'project_type': row[6],
            'project_location': row[7],
            'seller_name': row[8],
            'credits_earned': float(row[9]),
            'credits_used': float(row[10]) if row[10] else 0,
            'listed_quantity': float(row[11]) if row[11] else 0
        })
    
    cur.close()
    conn.close()
    
    return render_template('carbon.html', 
                           projects=projects, 
                           marketplace_credits=marketplace_credits,
                           total_all_credits=total_all_credits,
                           total_available_credits=total_available_credits,
                           username=session.get('username', 'User'))


# ====================================
# REPORTING ROUTES
# ====================================

@app.route('/generate-report', methods=['POST'])
def generate_report():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # Get form data
    report_type = request.form.get('report_type')
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    project_id = request.form.get('projects')  # Single project ID
    file_format = request.form.get('format', 'pdf')
    
    # For annual reports, get all projects
    project_ids = []
    project_names = []
    if report_type == "Annual Sustainability Report":
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, name FROM projects WHERE user_id = %s", (session['user_id'],))
        projects = cur.fetchall()
        project_ids = [row[0] for row in projects]
        project_names = [row[1] for row in projects]
        cur.close()
        conn.close()
    elif project_id:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT name FROM projects WHERE id = %s", (project_id,))
        project_name = cur.fetchone()[0]
        project_ids = [project_id]
        project_names = [project_name]
        cur.close()
        conn.close()
    else:
        return "Please select at least one project", 400

    # Validate dates only if provided
    try:
        if start_date: 
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        if end_date: 
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            if start_date and start_date > end_date:
                return "Start date must be before end date", 400
    except ValueError:
        return "Invalid date format", 400

    # Create filename and paths
    timestamp = datetime.now().strftime("%Y%m%d")
    
    # Generate base filename based on report type
    if report_type == "Annual Sustainability Report":
        # For annual reports, use "Annual_Report" instead of listing all project names
        base_name = f"Annual_Report_{timestamp}"
    else:
        # For single project reports, use "project_name - report_type - date"
        # Clean the project name for filename (remove special characters)
        clean_project_name = re.sub(r'[^\w\s-]', '', project_names[0]).strip().replace(' ', '_')
        clean_report_type = re.sub(r'[^\w\s-]', '', report_type).strip().replace(' ', '_')
        base_name = f"{clean_project_name}_{clean_report_type}_{timestamp}"
    
    reports_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'reports')
    os.makedirs(reports_dir, exist_ok=True)
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Prepare report data
    report_data = []
    total_co2e = 0
    total_credits = 0
    
    for pid in project_ids:
        # Get project details
        cur.execute("SELECT name, type, start_date, end_date FROM projects WHERE id = %s", (pid,))
        project = cur.fetchone()
        
        # Get emissions data
        cur.execute("""
            SELECT 
                SUM(asphalt_t) AS asphalt,
                SUM(aggregate_t) AS aggregate,
                SUM(cement_t) AS cement,
                SUM(steel_t) AS steel,
                SUM(diesel_l) AS diesel,
                SUM(electricity_kwh) AS electricity,
                SUM(transport_tkm) AS transport
            FROM emissions
            WHERE project_id = %s
        """, (pid,))
        materials = cur.fetchone() or [0]*7
        
        # Calculate CO2e
        cur.execute("""
            SELECT 
                COALESCE(SUM(
                    e.asphalt_t * ef_asphalt.co2e_per_unit +
                    e.aggregate_t * ef_aggregate.co2e_per_unit +
                    e.cement_t * ef_cement.co2e_per_unit +
                    e.steel_t * ef_steel.co2e_per_unit +
                    e.diesel_l * ef_diesel.co2e_per_unit +
                    e.electricity_kwh * ef_electricity.co2e_per_unit +
                    e.transport_tkm * ef_transport.co2e_per_unit
                ) / 1000, 0) AS total_co2e
            FROM emissions e
            JOIN emission_factors ef_asphalt ON ef_asphalt.name = 'Asphalt'
            JOIN emission_factors ef_aggregate ON ef_aggregate.name = 'Aggregate'
            JOIN emission_factors ef_cement ON ef_cement.name = 'Cement'
            JOIN emission_factors ef_steel ON ef_steel.name = 'Steel'
            JOIN emission_factors ef_diesel ON ef_diesel.name = 'Diesel'
            JOIN emission_factors ef_electricity ON ef_electricity.name = 'Electricity'
            JOIN emission_factors ef_transport ON ef_transport.name = 'Transport'
            WHERE project_id = %s
        """, (pid,))
        project_co2e = cur.fetchone()[0] or 0
        
        # Get credits
        cur.execute("SELECT COALESCE(SUM(credits_earned), 0) FROM carbon_credits WHERE project_id = %s", (pid,))
        credits = cur.fetchone()[0] or 0
        
        total_co2e += float(project_co2e)
        total_credits += float(credits)
        
        report_data.append({
            'id': pid,
            'name': project[0],
            'type': project[1],
            'start_date': project[2].strftime('%Y-%m-%d') if project[2] else 'N/A',
            'end_date': project[3].strftime('%Y-%m-%d') if project[3] else 'N/A',
            'materials': [float(m) if m is not None else 0 for m in materials],  # Convert Decimals to floats
            'co2e': float(project_co2e),
            'credits': float(credits)
        })
    
    # Generate file based on format
    if file_format == 'pdf':
        filename = f"{base_name}.pdf"
        filepath = os.path.join(reports_dir, filename)
        
        from reportlab.lib.pagesizes import letter, A4, landscape
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors
        from reportlab.lib.units import inch
        from reportlab.pdfbase import pdfutils
        
        # Use A4 landscape for better table fitting
        doc = SimpleDocTemplate(filepath, pagesize=landscape(A4), 
                              topMargin=0.5*inch, bottomMargin=0.5*inch,
                              leftMargin=0.5*inch, rightMargin=0.5*inch)
        styles = getSampleStyleSheet()
        
        # Create custom styles with better formatting
        title_style = ParagraphStyle(
            'Title',
            parent=styles['Heading1'],
            fontName='Helvetica-Bold',
            fontSize=18,
            alignment=1,
            spaceAfter=6,
            textColor=colors.HexColor('#12303B')
        )

        subtitle_style = ParagraphStyle(
            'Subtitle',
            parent=styles['Heading2'],
            fontName='Helvetica',
            fontSize=12,
            alignment=1,
            spaceAfter=12,
            textColor=colors.HexColor('#0F7D5C')
        )
        
        report_title_style = ParagraphStyle(
            'ReportTitle',
            parent=styles['Heading2'],
            fontSize=18,
            alignment=1,
            spaceAfter=20,
            textColor=colors.HexColor('#0F7D5C'),
            fontName='Helvetica-Bold'
        )
        
        section_style = ParagraphStyle(
            'Section',
            parent=styles['Heading3'],
            fontSize=14,
            spaceBefore=20,
            spaceAfter=10,
            textColor=colors.HexColor('#2E4A62'),
            fontName='Helvetica-Bold'
        )
        
        body_style = ParagraphStyle(
            'BodyText',
            parent=styles['BodyText'],
            fontSize=10,
            spaceAfter=6,
            alignment=4
        )
        
        elements = []
        
        # Professional header
        current_date = datetime.now().strftime('%B %d, %Y')
        
        # Company name and report title in separate lines
        elements.append(Paragraph("EcoQuant", title_style))
        elements.append(Spacer(1, 0.1*inch))
        elements.append(Paragraph(report_type, report_title_style))
        elements.append(Spacer(1, 0.05*inch))
        
        # Professional divider
        divider = Table([[""]], colWidths=[10.5*inch])
        divider.setStyle(TableStyle([
            ('LINEABOVE', (0,0), (0,0), 2, colors.HexColor('#0F7D5C'))
        ]))
        elements.append(divider)
        elements.append(Spacer(1, 0.3*inch))
        
        # Report metadata in a clean format
        meta_data = [
            ["Report Generated:", current_date],
            ["Report Type:", report_type]
        ]
        
        # Add date range only if provided
        if start_date or end_date:
            if start_date and end_date:
                date_range = f"{start_date} to {end_date}"
            else:
                date_range = str(start_date or end_date)
            meta_data.append(["Date Range:", date_range])
        
        # Add project info for single project reports
        if report_type != "Annual Sustainability Report" and report_data:
            meta_data.append(["Project:", report_data[0]['name']])
        else:
            meta_data.append(["Projects Included:", f"{len(report_data)} projects"])
        
        meta_table = Table(meta_data, colWidths=[2*inch, 8.5*inch])
        meta_table.setStyle(TableStyle([
            ('ALIGN', (0,0), (0,-1), 'LEFT'),
            ('ALIGN', (1,0), (1,-1), 'LEFT'),
            ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
            ('FONTNAME', (1,0), (1,-1), 'Helvetica'),
            ('FONTSIZE', (0,0), (-1,-1), 10),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ]))
        elements.append(meta_table)
        elements.append(Spacer(1, 0.3*inch))
        
        # Executive summary
        elements.append(Paragraph("Executive Summary", section_style))
        
        summary_text = ""
        if report_type == "Project Emission Summary":
            offset_pct = (total_credits / total_co2e * 100) if total_co2e > 0 else 0
            summary_text = f"""
            This comprehensive emissions analysis evaluates the environmental impact of construction activities 
            and material usage. The project generated {total_co2e:.2f} tons of CO2 equivalent emissions through 
            various construction materials and energy consumption. Environmental mitigation efforts have resulted 
            in {total_credits:.2f} carbon credits, achieving a {offset_pct:.1f}% emission offset. This report 
            provides detailed breakdowns of emission sources and recommendations for further sustainability improvements.
            """
        elif report_type == "Carbon Credit Statement":
            credit_value = total_credits * 1000
            summary_text = f"""
            This financial statement provides a comprehensive overview of carbon credit holdings and transactions. 
            Current portfolio holds {total_credits:.2f} verified carbon credits with an estimated market value 
            of Rs {credit_value:,.2f}. All credits are generated through verified sustainable construction practices 
            and emission reduction activities, ensuring compliance with environmental standards and regulations.
            """
        elif report_type == "Compliance Report":
            offset_pct = (total_credits / total_co2e * 100) if total_co2e > 0 else 0
            compliance_status = "COMPLIANT" if offset_pct >= 10 else "MONITORING REQUIRED"
            summary_text = f"""
            This regulatory compliance assessment validates adherence to environmental standards and sustainability 
            requirements. Current emission offset ratio stands at {offset_pct:.1f}%, with compliance status: {compliance_status}. 
            The project demonstrates commitment to environmental stewardship through systematic emission tracking, 
            mitigation measures, and carbon credit generation aligned with regulatory frameworks.
            """
        elif report_type == "Annual Sustainability Report":
            offset_pct = (total_credits / total_co2e * 100) if total_co2e > 0 else 0
            avg_offset = offset_pct / len(report_data) if report_data else 0
            summary_text = f"""
            EcoQuant's Annual Sustainability Report showcases our organization's environmental performance and 
            commitment to sustainable infrastructure development. This comprehensive review covers {len(report_data)} 
            projects with combined emissions of {total_co2e:.2f} tons CO2e and {total_credits:.2f} carbon credits generated. 
            Our portfolio achieved an average emission offset of {avg_offset:.1f}% per project, demonstrating measurable 
            progress toward carbon neutrality and environmental responsibility.
            """
        
        elements.append(Paragraph(summary_text, body_style))
        elements.append(Spacer(1, 0.3*inch))
        
        # Type-specific content sections
        if report_type == "Carbon Credit Statement":
            elements.append(Paragraph("Credit Transactions", section_style))
            
            # Get credit transactions
            credit_headers = ["Date", "Transaction Type", "Credits", "Balance"]
            credit_rows = [credit_headers]
            
            for project in report_data:
                cur.execute("""
                    SELECT issued_at, credits_earned, credits_used 
                    FROM carbon_credits 
                    WHERE project_id = %s
                    ORDER BY issued_at
                """, (project['id'],))
                transactions = cur.fetchall()
                
                balance = 0
                for t in transactions:
                    credits_earned = t[1] or 0
                    credits_used = t[2] or 0
                    
                    # Add earned transaction
                    if credits_earned > 0:
                        balance += credits_earned
                        credit_rows.append([
                            t[0].strftime('%Y-%m-%d'),
                            "Credit Earned",
                            f"+{credits_earned:.2f}",
                            f"{balance:.2f}"
                        ])
                    
                    # Add used transaction if any
                    if credits_used > 0:
                        balance -= credits_used
                        credit_rows.append([
                            t[0].strftime('%Y-%m-%d'),
                            "Credit Used",
                            f"-{credits_used:.2f}",
                            f"{balance:.2f}"
                        ])
            
            credit_table = Table(credit_rows, repeatRows=1, colWidths=[2*inch, 2.5*inch, 1.5*inch, 1.5*inch])
            credit_table.setStyle(TableStyle([
                # Header styling
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2E4A62')),
                ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('FONTSIZE', (0,0), (-1,-1), 9),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('BOTTOMPADDING', (0,0), (-1,0), 8),
                ('TOPPADDING', (0,0), (-1,0), 8),
                
                # Data rows - WHITE background only
                ('BACKGROUND', (0,1), (-1,-1), colors.white),
                ('TEXTCOLOR', (0,1), (-1,-1), colors.black),
                ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
                
                # Grid and borders
                ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
                ('LINEABOVE', (0,1), (-1,1), 0.5, colors.grey),
            ]))
            elements.append(credit_table)
            
        else:
            if report_type == "Project Emission Summary":
                # Table 1: Project Overview
                elements.append(Paragraph("Project Overview", section_style))
                
                # Project details summary
                project_info = report_data[0]
                overview_data = [
                    ["Project Type:", project_info['type']],
                    ["Start Date:", project_info['start_date']],
                    ["End Date:", project_info['end_date']],
                    ["Total CO2e Emissions:", f"{project_info['co2e']:.2f} tons"],
                    ["Carbon Credits Earned:", f"{project_info['credits']:.2f} credits"],
                    ["Net Environmental Impact:", 
                    f"{((project_info['credits'] / project_info['co2e']) * 100):.1f}% offset" 
                    if project_info['co2e'] > 0 else "0.0% offset"]
                ]

                
                overview_table = Table(overview_data, colWidths=[3*inch, 4*inch])
                overview_table.setStyle(TableStyle([
                    ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
                    ('FONTNAME', (1,0), (1,-1), 'Helvetica'),
                    ('FONTSIZE', (0,0), (-1,-1), 10),
                    ('ALIGN', (0,0), (0,-1), 'LEFT'),
                    ('ALIGN', (1,0), (1,-1), 'LEFT'),
                    ('VALIGN', (0,0), (-1,-1), 'TOP'),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 5),
                    ('GRID', (0,0), (-1,-1), 0.5, colors.lightgrey),
                    ('BACKGROUND', (0,0), (-1,-1), colors.white),
                ]))
                elements.append(overview_table)
                elements.append(Spacer(1, 0.3*inch))
                
                # Table 2: Material Usage and Emissions Breakdown
                elements.append(Paragraph("Material Usage and Emissions Breakdown", section_style))
                
                material_headers = ["Material/Energy Source", "Quantity Used", "Unit", "CO2e Factor", "Total CO2e (kg)"]
                material_rows = [material_headers]
                
                # Get emission factors from database
                cur.execute("SELECT name, co2e_per_unit FROM emission_factors")
                db_factors = dict(cur.fetchall())
                
                # Define emission factors with proper units
                emission_factors = {
                    'Asphalt': {'factor': float(db_factors.get('Asphalt', 500)), 'unit': 'kg CO2e/t'},
                    'Aggregate': {'factor': float(db_factors.get('Aggregate', 20)), 'unit': 'kg CO2e/t'},
                    'Cement': {'factor': float(db_factors.get('Cement', 900)), 'unit': 'kg CO2e/t'},
                    'Steel': {'factor': float(db_factors.get('Steel', 2300)), 'unit': 'kg CO2e/t'},
                    'Diesel': {'factor': float(db_factors.get('Diesel', 2700)), 'unit': 'kg CO2e/L'},
                    'Electricity': {'factor': float(db_factors.get('Electricity', 820)), 'unit': 'kg CO2e/kWh'},
                    'Transport': {'factor': float(db_factors.get('Transport', 150)), 'unit': 'kg CO2e/tkm'}
                }
                
                materials_data = [
                    ('Asphalt', project_info['materials'][0], 'tons'),
                    ('Aggregate', project_info['materials'][1], 'tons'),
                    ('Cement', project_info['materials'][2], 'tons'),
                    ('Steel', project_info['materials'][3], 'tons'),
                    ('Diesel', project_info['materials'][4], 'liters'),
                    ('Electricity', project_info['materials'][5], 'kWh'),
                    ('Transport', project_info['materials'][6], 'tkm')
                ]
                
                total_emissions_kg = 0
                for material, quantity, unit in materials_data:
                    quantity_float = float(quantity) if quantity else 0
                    if quantity_float > 0:
                        factor_info = emission_factors.get(material, {'factor': 0, 'unit': 'N/A'})
                        co2e_kg = quantity_float * factor_info['factor']
                        total_emissions_kg += co2e_kg
                        
                        material_rows.append([
                            material,
                            f"{quantity_float:.2f}",
                            unit,
                            factor_info['unit'],
                            f"{co2e_kg:,.0f}"
                        ])
                
                # Add total row
                material_rows.append([
                    "TOTAL EMISSIONS", "", "", "", f"{total_emissions_kg:,.0f} kg ({total_emissions_kg/1000:.2f} tons)"
                ])
                
                material_table = Table(material_rows, repeatRows=1, 
                                     colWidths=[2.2*inch, 1.5*inch, 1.2*inch, 1.5*inch, 1.8*inch])
                material_table.setStyle(TableStyle([
                    # Header styling
                    ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2E4A62')),
                    ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                    ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0,0), (-1,-1), 9),
                    ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                    ('BOTTOMPADDING', (0,0), (-1,0), 8),
                    ('TOPPADDING', (0,0), (-1,0), 8),
                    
                    # Data rows - WHITE background
                    ('BACKGROUND', (0,1), (-1,-2), colors.white),
                    ('TEXTCOLOR', (0,1), (-1,-1), colors.black),
                    ('FONTNAME', (0,1), (-1,-2), 'Helvetica'),
                    
                    # Totals row styling
                    ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor('#F0F0F0')),
                    ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
                    
                    # Grid and borders
                    ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
                ]))
                elements.append(material_table)
                
                # Add recommendations section
                elements.append(Spacer(1, 0.3*inch))
                elements.append(Paragraph("Sustainability Recommendations", section_style))
                
                recommendations = """
                Based on the emissions analysis, consider the following sustainability improvements:
                • Explore alternative materials with lower carbon footprints (e.g., recycled aggregates, bio-asphalt)
                • Implement energy-efficient construction practices and equipment
                • Optimize transportation routes and methods to reduce logistics emissions
                • Consider renewable energy sources for on-site electricity needs
                • Investigate carbon capture technologies for high-emission materials like cement
                """
                
                elements.append(Paragraph(recommendations, body_style))
                
            elif report_type == "Annual Sustainability Report":
                elements.append(Paragraph("Projects Summary", section_style))
                
                project_headers = ["Project Name", "Type", "Start Date", "End Date", "CO2e (tons)", "Credits"]
                project_rows = [project_headers]
                
                for project in report_data:
                    project_rows.append([
                        project['name'],
                        project['type'],
                        project['start_date'],
                        project['end_date'],
                        f"{project['co2e'] or 0:.2f}",
                        f"{project['credits'] or 0:.2f}"
                    ])
                
                # Add totals row
                project_rows.append([
                    "TOTAL", "", "", "",
                    f"{total_co2e:.2f}",
                    f"{total_credits:.2f}"
                ])
                
                project_table = Table(project_rows, repeatRows=1, 
                                    colWidths=[2.8*inch, 1.5*inch, 1.3*inch, 1.3*inch, 1.3*inch, 1.3*inch])
                project_table.setStyle(TableStyle([
                    # Header styling
                    ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2E4A62')),
                    ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                    ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0,0), (-1,-1), 9),
                    ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                    ('BOTTOMPADDING', (0,0), (-1,0), 8),
                    ('TOPPADDING', (0,0), (-1,0), 8),
                    
                    # Data rows - WHITE background
                    ('BACKGROUND', (0,1), (-1,-2), colors.white),
                    ('TEXTCOLOR', (0,1), (-1,-1), colors.black),
                    ('FONTNAME', (0,1), (-1,-2), 'Helvetica'),
                    
                    # Totals row styling
                    ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor('#F0F0F0')),
                    ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
                    
                    # Grid and borders
                    ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
                ]))
                elements.append(project_table)
                
            else:
                project_headers = ["Project Name", "Type", "Start Date", "End Date", "CO2e (tons)", "Credits"]
                project_rows = [project_headers]
                
                for project in report_data:
                    project_rows.append([
                        project['name'],
                        project['type'],
                        project['start_date'],
                        project['end_date'],
                        f"{project['co2e'] or 0:.2f}",
                        f"{project['credits'] or 0:.2f}"
                    ])
                
                # Add totals row
                project_rows.append([
                    "TOTAL", "", "", "",
                    f"{total_co2e:.2f}",
                    f"{total_credits:.2f}"
                ])
                
                project_table = Table(project_rows, repeatRows=1, 
                                    colWidths=[3*inch, 1.5*inch, 1.3*inch, 1.3*inch, 1.3*inch, 1.3*inch])
                project_table.setStyle(TableStyle([
                    # Header styling
                    ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2E4A62')),
                    ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                    ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0,0), (-1,-1), 9),
                    ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                    ('BOTTOMPADDING', (0,0), (-1,0), 8),
                    ('TOPPADDING', (0,0), (-1,0), 8),
                    
                    # Data rows - WHITE background
                    ('BACKGROUND', (0,1), (-1,-2), colors.white),
                    ('TEXTCOLOR', (0,1), (-1,-1), colors.black),
                    ('FONTNAME', (0,1), (-1,-2), 'Helvetica'),
                    
                    # Totals row styling
                    ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor('#F0F0F0')),
                    ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
                    
                    # Grid and borders
                    ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
                ]))
                elements.append(project_table)
        
        # Professional footer
        elements.append(Spacer(1, 0.4*inch))
        footer_divider = Table([[""]], colWidths=[10.5*inch])
        footer_divider.setStyle(TableStyle([
            ('LINEABOVE', (0,0), (0,0), 1, colors.HexColor('#CCCCCC'))
        ]))
        elements.append(footer_divider)
        elements.append(Spacer(1, 0.1*inch))
        
        footer_text = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=9,
            alignment=1,
            textColor=colors.HexColor('#666666')
        )
        
        elements.append(Paragraph("EcoQuant - Sustainable Infrastructure Management", footer_text))
        elements.append(Paragraph(f"Generated on {current_date}", footer_text))
        
        doc.build(elements)
            
    # CSV
    elif file_format == 'csv':
        filename = f"{base_name}.csv"
        filepath = os.path.join(reports_dir, filename)
        
        data = []
        for project in report_data:
            data.append({
                'Project': project['name'],
                'Type': project['type'],
                'Start Date': project['start_date'],
                'End Date': project['end_date'],
                'Asphalt (t)': project['materials'][0] or 0,
                'Aggregate (t)': project['materials'][1] or 0,
                'Cement (t)': project['materials'][2] or 0,
                'Steel (t)': project['materials'][3] or 0,
                'Diesel (L)': project['materials'][4] or 0,
                'Electricity (kWh)': project['materials'][5] or 0,
                'Transport (tkm)': project['materials'][6] or 0,
                'Total CO2e (tons)': project['co2e'] or 0,
                'Credits Earned': project['credits'] or 0
            })
            
        # Add totals row
        totals = {
            'Project': 'TOTAL',
            'Asphalt (t)': sum(project['materials'][0] or 0 for project in report_data),
            'Aggregate (t)': sum(project['materials'][1] or 0 for project in report_data),
            'Cement (t)': sum(project['materials'][2] or 0 for project in report_data),
            'Steel (t)': sum(project['materials'][3] or 0 for project in report_data),
            'Diesel (L)': sum(project['materials'][4] or 0 for project in report_data),
            'Electricity (kWh)': sum(project['materials'][5] or 0 for project in report_data),
            'Transport (tkm)': sum(project['materials'][6] or 0 for project in report_data),
            'Total CO2e (tons)': total_co2e,
            'Credits Earned': total_credits
        }
        data.append(totals)
            
        df = pd.DataFrame(data)
        df.to_csv(filepath, index=False)
        
    # Excel
    elif file_format == 'excel':
        filename = f"{base_name}.xlsx"
        filepath = os.path.join(reports_dir, filename)
        
        data = []
        for project in report_data:
            data.append({
                'Project': project['name'],
                'Type': project['type'],
                'Start Date': project['start_date'],
                'End Date': project['end_date'],
                'Asphalt (t)': project['materials'][0] or 0,
                'Aggregate (t)': project['materials'][1] or 0,
                'Cement (t)': project['materials'][2] or 0,
                'Steel (t)': project['materials'][3] or 0,
                'Diesel (L)': project['materials'][4] or 0,
                'Electricity (kWh)': project['materials'][5] or 0,
                'Transport (tkm)': project['materials'][6] or 0,
                'Total CO2e (tons)': project['co2e'] or 0,
                'Credits Earned': project['credits'] or 0
            })
            
        # Add totals row
        totals = {
            'Project': 'TOTAL',
            'Asphalt (t)': sum(project['materials'][0] or 0 for project in report_data),
            'Aggregate (t)': sum(project['materials'][1] or 0 for project in report_data),
            'Cement (t)': sum(project['materials'][2] or 0 for project in report_data),
            'Steel (t)': sum(project['materials'][3] or 0 for project in report_data),
            'Diesel (L)': sum(project['materials'][4] or 0 for project in report_data),
            'Electricity (kWh)': sum(project['materials'][5] or 0 for project in report_data),
            'Transport (tkm)': sum(project['materials'][6] or 0 for project in report_data),
            'Total CO2e (tons)': total_co2e,
            'Credits Earned': total_credits
        }
        data.append(totals)
            
        df = pd.DataFrame(data)
        df.to_excel(filepath, index=False)
    
    # Save to database
    file_size = os.path.getsize(filepath)
    
    # Create report name for database (different from filename)
    if report_type == "Annual Sustainability Report":
        report_name = f"Annual Report - {datetime.now().strftime('%Y-%m-%d')}"
    else:
        report_name = f"{project_names[0]} - {report_type} - {datetime.now().strftime('%Y-%m-%d')}"

    # Determine the project ID to store (only for single project reports)
    project_id_to_store = project_ids[0] if len(project_ids) == 1 else None

    cur.execute(
        "INSERT INTO reports (user_id, name, file_path, file_size, project_id) VALUES (%s, %s, %s, %s, %s)",
        (session['user_id'], report_name, filepath, file_size, project_id_to_store)
    )
    conn.commit()
    cur.close()
    conn.close()
    
    return redirect(url_for('reports'))


@app.route('/download/report/<int:report_id>')
def download_report(report_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT file_path, name FROM reports WHERE id = %s AND user_id = %s", 
                   (report_id, session['user_id']))
        report = cur.fetchone()
        
        if report:
            # Determine file extension
            ext = os.path.splitext(report[0])[1]
            return send_file(
                report[0],
                as_attachment=True,
                download_name=f"{report[1]}{ext}"
            )
        return "Report not found", 404
    except Exception as e:
        return "Error downloading report", 500


@app.route('/delete-report/<int:report_id>', methods=['DELETE'])
def delete_report(report_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT file_path FROM reports WHERE id = %s AND user_id = %s", 
                   (report_id, session['user_id']))
        report = cur.fetchone()
        
        if report:
            # Delete physical file
            if os.path.exists(report[0]):
                os.remove(report[0])
            
            # Delete database record
            cur.execute("DELETE FROM reports WHERE id = %s", (report_id,))
            conn.commit()
            return jsonify({"status": "success"})
        
        return jsonify({"status": "error", "message": "Report not found"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/download/project/<project_id>')
def download_project_report(project_id):
    try:
        if 'user_id' not in session:
            return redirect(url_for('login'))
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get project details with emissions
        cur.execute("""
            SELECT p.id, p.name, p.type, p.location, p.start_date, p.end_date,
                COALESCE(SUM(
                    e.asphalt_t * ef_asphalt.co2e_per_unit +
                    e.aggregate_t * ef_aggregate.co2e_per_unit +
                    e.cement_t * ef_cement.co2e_per_unit +
                    e.steel_t * ef_steel.co2e_per_unit +
                    e.diesel_l * ef_diesel.co2e_per_unit +
                    e.electricity_kwh * ef_electricity.co2e_per_unit +
                    e.transport_tkm * ef_transport.co2e_per_unit
                ) / 1000, 0) AS total_co2e_tons,
                COALESCE(SUM(cc.credits_earned), 0) AS credits
            FROM projects p
            LEFT JOIN emissions e ON p.id = e.project_id
            LEFT JOIN carbon_credits cc ON p.id = cc.project_id
            JOIN emission_factors ef_asphalt ON ef_asphalt.name = 'Asphalt'
            JOIN emission_factors ef_aggregate ON ef_aggregate.name = 'Aggregate'
            JOIN emission_factors ef_cement ON ef_cement.name = 'Cement'
            JOIN emission_factors ef_steel ON ef_steel.name = 'Steel'
            JOIN emission_factors ef_diesel ON ef_diesel.name = 'Diesel'
            JOIN emission_factors ef_electricity ON ef_electricity.name = 'Electricity'
            JOIN emission_factors ef_transport ON ef_transport.name = 'Transport'
            WHERE p.id = %s AND p.user_id = %s
            GROUP BY p.id, p.name, p.type, p.location, p.start_date, p.end_date
        """, (project_id, session['user_id']))
        
        project = cur.fetchone()
        if not project:
            return "Project not found", 404

        # Extract and format dates correctly
        start_date = project[4]  # index 4 is start_date
        end_date = project[5]    # index 5 is end_date

        # Calculate status based on dates
        status = calculate_project_status(start_date, end_date) if start_date and end_date else "Unknown"

        # Convert to float
        total_co2e_tons = float(project[6]) if project[6] else 0.0
        credits = float(project[7]) if project[7] else 0.0

        # Calculate and round reduction percentage
        total_co2e_kg = total_co2e_tons * 1000
        reduction_kg = credits * 1000
        reduction_pct = (reduction_kg / total_co2e_kg * 100) if total_co2e_kg > 0 else 0
        reduction_pct = round(reduction_pct, 2)

        project_data = {
            'id': project[0],
            'name': project[1],
            'type': project[2],
            'location': project[3],
            'start_date': start_date.strftime('%Y-%m-%d') if start_date else 'N/A',
            'end_date': end_date.strftime('%Y-%m-%d') if end_date else 'N/A',
            'co2e': total_co2e_tons,
            'credits': credits,
            'reduction': reduction_pct,
            'status': status  # Use calculated status
        }
        
        # Get breakdown data
        cur.execute("""
            SELECT 
                SUM(e.asphalt_t * ef_asphalt.co2e_per_unit) / 1000 AS asphalt,
                SUM(e.aggregate_t * ef_aggregate.co2e_per_unit) / 1000 AS aggregate,
                SUM(e.cement_t * ef_cement.co2e_per_unit) / 1000 AS cement,
                SUM(e.steel_t * ef_steel.co2e_per_unit) / 1000 AS steel,
                SUM(e.diesel_l * ef_diesel.co2e_per_unit) / 1000 AS diesel,
                SUM(e.electricity_kwh * ef_electricity.co2e_per_unit) / 1000 AS electricity,
                SUM(e.transport_tkm * ef_transport.co2e_per_unit) / 1000 AS transport
            FROM emissions e
            JOIN emission_factors ef_asphalt ON ef_asphalt.name = 'Asphalt'
            JOIN emission_factors ef_aggregate ON ef_aggregate.name = 'Aggregate'
            JOIN emission_factors ef_cement ON ef_cement.name = 'Cement'
            JOIN emission_factors ef_steel ON ef_steel.name = 'Steel'
            JOIN emission_factors ef_diesel ON ef_diesel.name = 'Diesel'
            JOIN emission_factors ef_electricity ON ef_electricity.name = 'Electricity'
            JOIN emission_factors ef_transport ON ef_transport.name = 'Transport'
            WHERE e.project_id = %s
        """, (project_id,))
        
        breakdown_row = cur.fetchone()
        if breakdown_row:
            values = [float(val) if val is not None else 0.0 for val in breakdown_row]
        else:
            values = [0.0] * 7
            
        # Get category breakdown
        cur.execute("""
            SELECT 
                'Materials' AS category,
                SUM(
                    e.asphalt_t * ef_asphalt.co2e_per_unit +
                    e.aggregate_t * ef_aggregate.co2e_per_unit +
                    e.cement_t * ef_cement.co2e_per_unit +
                    e.steel_t * ef_steel.co2e_per_unit
                ) / 1000 AS emissions
            FROM emissions e
            JOIN emission_factors ef_asphalt ON ef_asphalt.name = 'Asphalt'
            JOIN emission_factors ef_aggregate ON ef_aggregate.name = 'Aggregate'
            JOIN emission_factors ef_cement ON ef_cement.name = 'Cement'
            JOIN emission_factors ef_steel ON ef_steel.name = 'Steel'
            WHERE e.project_id = %s
            
            UNION ALL
            
            SELECT 
                'Equipment' AS category,
                SUM(e.diesel_l * ef_diesel.co2e_per_unit) / 1000
            FROM emissions e
            JOIN emission_factors ef_diesel ON ef_diesel.name = 'Diesel'
            WHERE e.project_id = %s
            
            UNION ALL
            
            SELECT 
                'Electricity' AS category,
                SUM(e.electricity_kwh * ef_electricity.co2e_per_unit) / 1000
            FROM emissions e
            JOIN emission_factors ef_electricity ON ef_electricity.name = 'Electricity'
            WHERE e.project_id = %s
            
            UNION ALL
            
            SELECT 
                'Transport' AS category,
                SUM(e.transport_tkm * ef_transport.co2e_per_unit) / 1000
            FROM emissions e
            JOIN emission_factors ef_transport ON ef_transport.name = 'Transport'
            WHERE e.project_id = %s
        """, (project_id, project_id, project_id, project_id))
        
        categories_data = cur.fetchall()
        categories = {
            'labels': [row[0] for row in categories_data],
            'values': [float(row[1]) if row[1] else 0.0 for row in categories_data]
        }
        
        # Get recommendations
        cur.execute("SELECT * FROM recommendations WHERE project_id = %s", (project_id,))
        recommendations = []
        for row in cur.fetchall():
            recommendations.append({
                'id': row[0],
                'title': row[2],
                'description': row[3],
                'impact': row[4],
                'cost': float(row[5]) if row[5] else 0.0
            })
            
        cur.close()
        conn.close()
        
        # Create PDF in memory
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), 
                              topMargin=0.5*inch, bottomMargin=0.5*inch,
                              leftMargin=0.5*inch, rightMargin=0.5*inch)
        styles = getSampleStyleSheet()
        
        # Create custom styles
        title_style = ParagraphStyle(
            'Title',
            parent=styles['Heading1'],
            fontName='Helvetica-Bold',
            fontSize=18,
            alignment=1,
            spaceAfter=6,
            textColor=colors.HexColor('#12303B')
        )

        subtitle_style = ParagraphStyle(
            'Subtitle',
            parent=styles['Heading2'],
            fontName='Helvetica',
            fontSize=12,
            alignment=1,
            spaceAfter=12,
            textColor=colors.HexColor('#0F7D5C')
        )
        
        report_title_style = ParagraphStyle(
            'ReportTitle',
            parent=styles['Heading2'],
            fontSize=18,
            alignment=1,
            spaceAfter=20,
            textColor=colors.HexColor('#0F7D5C'),
            fontName='Helvetica-Bold'
        )
        
        section_style = ParagraphStyle(
            'Section',
            parent=styles['Heading3'],
            fontSize=14,
            spaceBefore=20,
            spaceAfter=10,
            textColor=colors.HexColor('#2E4A62'),
            fontName='Helvetica-Bold'
        )
        
        body_style = ParagraphStyle(
            'BodyText',
            parent=styles['BodyText'],
            fontSize=10,
            spaceAfter=6,
            alignment=4
        )
        
        elements = []
        
        # Header
        current_date = datetime.now().strftime('%B %d, %Y')
        elements.append(Paragraph("EcoQuant", title_style))
        elements.append(Spacer(1, 0.1*inch))
        elements.append(Paragraph("Project Emission Report", report_title_style))
        elements.append(Spacer(1, 0.05*inch))
        
        # Divider
        divider = Table([[""]], colWidths=[10.5*inch])
        divider.setStyle(TableStyle([
            ('LINEABOVE', (0,0), (0,0), 2, colors.HexColor('#0F7D5C'))
        ]))
        elements.append(divider)
        elements.append(Spacer(1, 0.3*inch))
        
        # Project metadata - using correct indices
        meta_data = [
            ["Report Generated:", current_date],
            ["Project Name:", project_data['name']],
            ["Project Type:", project_data['type']],
            ["Location:", project_data['location'] or "N/A"],
            ["Start Date:", project_data['start_date']],
            ["End Date:", project_data['end_date']],
            ["Status:", project_data['status']]  # Use calculated status
        ]

        meta_table = Table(meta_data, colWidths=[2*inch, 8.5*inch])
        meta_table.setStyle(TableStyle([
            ('ALIGN', (0,0), (0,-1), 'LEFT'),
            ('ALIGN', (1,0), (1,-1), 'LEFT'),
            ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
            ('FONTNAME', (1,0), (1,-1), 'Helvetica'),
            ('FONTSIZE', (0,0), (-1,-1), 10),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ]))
        elements.append(meta_table)
        elements.append(Spacer(1, 0.3*inch))
        
        # Executive summary
        elements.append(Paragraph("Executive Summary", section_style))
        
        summary_text = f"""
        This comprehensive emissions analysis evaluates the environmental impact of the {project[1]} project. 
        The project generated {total_co2e_tons:.2f} tons of CO2 equivalent emissions through various construction 
        materials and energy consumption. Environmental mitigation efforts have resulted in {credits:.2f} carbon 
        credits, achieving a {reduction_pct:.1f}% emission offset. This report provides detailed breakdowns of 
        emission sources and recommendations for further sustainability improvements.
        """
        
        elements.append(Paragraph(summary_text, body_style))
        elements.append(Spacer(1, 0.3*inch))
        
        # Key metrics
        elements.append(Paragraph("Key Metrics", section_style))
        
        metrics_data = [
            ["Total CO2e Emissions:", f"{total_co2e_tons:.2f} tons"],
            ["Carbon Credits Earned:", f"{credits:.2f} credits"],
            ["Emission Reduction:", f"{reduction_pct:.1f}%"],
            ["Project Status:", project_data['status']]  # Use calculated status
        ]
        
        metrics_table = Table(metrics_data, colWidths=[3*inch, 4*inch])
        metrics_table.setStyle(TableStyle([
            ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
            ('FONTNAME', (1,0), (1,-1), 'Helvetica'),
            ('FONTSIZE', (0,0), (-1,-1), 10),
            ('ALIGN', (0,0), (0,-1), 'LEFT'),
            ('ALIGN', (1,0), (1,-1), 'LEFT'),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
            ('GRID', (0,0), (-1,-1), 0.5, colors.lightgrey),
            ('BACKGROUND', (0,0), (-1,-1), colors.white),
        ]))
        elements.append(metrics_table)
        elements.append(Spacer(1, 0.3*inch))
        
        # Emissions breakdown by category
        elements.append(Paragraph("Emissions by Category", section_style))
        
        category_data = [["Category", "CO2e (tons)"]] + [
            [categories['labels'][i], f"{categories['values'][i]:.2f}"] 
            for i in range(len(categories['labels']))
        ]
        
        category_table = Table(category_data, repeatRows=1, colWidths=[4*inch, 2*inch])
        category_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2E4A62')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 10),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,0), 8),
            ('TOPPADDING', (0,0), (-1,0), 8),
            ('BACKGROUND', (0,1), (-1,-1), colors.white),
            ('TEXTCOLOR', (0,1), (-1,-1), colors.black),
            ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ]))
        elements.append(category_table)
        elements.append(Spacer(1, 0.3*inch))
        
        # Material breakdown
        elements.append(Paragraph("Material Emissions Breakdown", section_style))
        
        material_labels = ["Asphalt", "Aggregate", "Cement", "Steel", "Diesel", "Electricity", "Transport"]
        material_data = [["Material", "CO2e (tons)"]] + [
            [material_labels[i], f"{values[i]:.2f}"] 
            for i in range(len(values))
        ]
        
        material_table = Table(material_data, repeatRows=1, colWidths=[4*inch, 2*inch])
        material_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2E4A62')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 10),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,0), 8),
            ('TOPPADDING', (0,0), (-1,0), 8),
            ('BACKGROUND', (0,1), (-1,-1), colors.white),
            ('TEXTCOLOR', (0,1), (-1,-1), colors.black),
            ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ]))
        elements.append(material_table)
        
        # Add recommendations if any
        if recommendations:
            elements.append(PageBreak())
            elements.append(Paragraph("Sustainability Recommendations", section_style))
            
            for i, rec in enumerate(recommendations):
                elements.append(Paragraph(f"{i+1}. {rec['title']}", ParagraphStyle(
                    'RecommendationTitle',
                    parent=styles['Heading4'],
                    fontSize=12,
                    spaceAfter=6,
                    textColor=colors.HexColor('#2E4A62'),
                    fontName='Helvetica-Bold'
                )))
                
                elements.append(Paragraph(rec['description'], body_style))
                
                cost_data = [
                    ["Impact Level:", rec['impact']],
                    ["Estimated Cost:", f"Rs. {rec['cost']:,.2f}"]
                ]
                
                cost_table = Table(cost_data, colWidths=[2*inch, 4*inch])
                cost_table.setStyle(TableStyle([
                    ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
                    ('FONTNAME', (1,0), (1,-1), 'Helvetica'),
                    ('FONTSIZE', (0,0), (-1,-1), 10),
                    ('ALIGN', (0,0), (0,-1), 'LEFT'),
                    ('ALIGN', (1,0), (1,-1), 'LEFT'),
                    ('VALIGN', (0,0), (-1,-1), 'TOP'),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 5),
                ]))
                elements.append(cost_table)
                elements.append(Spacer(1, 0.2*inch))
        
        # Footer
        elements.append(Spacer(1, 0.4*inch))
        footer_divider = Table([[""]], colWidths=[10.5*inch])
        footer_divider.setStyle(TableStyle([
            ('LINEABOVE', (0,0), (0,0), 1, colors.HexColor('#CCCCCC'))
        ]))
        elements.append(footer_divider)
        elements.append(Spacer(1, 0.1*inch))
        
        footer_text = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=9,
            alignment=1,
            textColor=colors.HexColor('#666666')
        )
        
        elements.append(Paragraph("EcoQuant - Sustainable Infrastructure Management", footer_text))
        elements.append(Paragraph(f"Generated on {current_date}", footer_text))
        
        doc.build(elements)
        
        buffer.seek(0)
        return send_file(
            buffer, 
            as_attachment=True, 
            download_name=f"{project[1].replace(' ', '_')}_Report_{current_date.replace(' ', '_')}.pdf", 
            mimetype='application/pdf'
        )
        
    except Exception as e:
        return f"Error generating report: {str(e)}", 500


# ====================================
# FILE UPLOAD ROUTE
# ====================================



# ====================================
# MARKETPLACE ROUTES
# ====================================

@app.route('/carbon/marketplace')
def carbon_marketplace():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get marketplace credits (same as in carbon route)
    cur.execute("""
        SELECT ml.id, ml.quantity_available, ml.price_per_credit, ml.listed_at, ml.status,
               p.name as project_name, p.type as project_type, p.location,
               u.username as seller_name,
               cc.credits_earned, cc.credits_used, cc.listed_quantity
        FROM marketplace_listings ml
        JOIN carbon_credits cc ON ml.credit_id = cc.id
        JOIN projects p ON cc.project_id = p.id
        JOIN users u ON ml.seller_id = u.id
        WHERE ml.status = 'active' AND ml.quantity_available > 0
        AND ml.seller_id != %s
        ORDER BY ml.listed_at DESC
    """, (session['user_id'],))
    
    marketplace_credits = []
    for row in cur.fetchall():
        marketplace_credits.append({
            'id': row[0],
            'quantity_available': float(row[1]),
            'price_per_credit': float(row[2]),
            'listed_at': row[3],
            'status': row[4],
            'project_name': row[5],
            'project_type': row[6],
            'project_location': row[7],
            'seller_name': row[8],
            'credits_earned': float(row[9]),
            'credits_used': float(row[10]) if row[10] else 0,
            'listed_quantity': float(row[11]) if row[11] else 0
        })
    
    cur.close()
    conn.close()
    
    return render_template('carbon_marketplace.html', 
                           marketplace_credits=marketplace_credits,
                           username=session.get('username', 'User'))



@app.route('/marketplace/my-listings')
def my_marketplace_listings():
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get user's marketplace listings
        cur.execute("""
            SELECT ml.id, ml.quantity_available, ml.price_per_credit, ml.listed_at, ml.status,
                   p.name as project_name, p.type as project_type,
                   cc.credits_earned, COALESCE(cc.credits_used, 0) as credits_used
            FROM marketplace_listings ml
            JOIN carbon_credits cc ON ml.credit_id = cc.id
            JOIN projects p ON cc.project_id = p.id
            WHERE ml.seller_id = %s
            ORDER BY ml.listed_at DESC
        """, (session['user_id'],))
        
        listings = []
        for row in cur.fetchall():
            listings.append({
                'id': row[0],
                'quantity_available': float(row[1]),
                'price_per_credit': float(row[2]),
                'listed_at': row[3],
                'status': row[4],
                'project_name': row[5],
                'project_type': row[6],
                'credits_earned': float(row[7]),
                'credits_used': float(row[8]) if row[8] else 0
            })
        
        cur.close()
        conn.close()
        
        return jsonify({"status": "success", "listings": listings})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/marketplace/listings')
def get_marketplace_listings():
    """Get all active marketplace listings excluding current user's listings"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get current user ID from session
        user_id = session.get('user_id')
        
        cur.execute("""
            SELECT ml.id, ml.quantity_available, ml.price_per_credit, ml.listed_at,
                   p.name as project_name, p.type as project_type, p.location,
                   u.username as seller_name,
                   cc.credits_earned, cc.credits_used,
                   (cc.credits_earned - COALESCE(cc.credits_used, 0)) as total_available
            FROM marketplace_listings ml
            JOIN carbon_credits cc ON ml.credit_id = cc.id
            JOIN projects p ON cc.project_id = p.id
            JOIN users u ON ml.seller_id = u.id
            WHERE ml.status = 'active' AND ml.quantity_available > 0
            AND ml.seller_id != %s  -- Exclude current user's listings
            ORDER BY ml.listed_at DESC
        """, (user_id,))
        
        listings = []
        for row in cur.fetchall():
            listings.append({
                'id': row[0],
                'quantity_available': float(row[1]),
                'price_per_credit': float(row[2]),
                'listed_at': row[3].isoformat() if row[3] else None,
                'project_name': row[4],
                'project_type': row[5],
                'project_location': row[6],
                'seller_name': row[7],
                'credits_earned': float(row[8]),
                'credits_used': float(row[9]) if row[9] else 0,
                'total_available': float(row[10]) if row[10] else 0
            })
        
        cur.close()
        conn.close()
        
        return jsonify({"status": "success", "listings": listings})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/marketplace/list', methods=['POST'])
def create_marketplace_listing():
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    try:
        data = request.get_json()
        credit_id = data.get('credit_id')
        quantity = float(data.get('quantity'))
        price_per_credit = float(data.get('price_per_credit'))
        
        if not credit_id or not quantity or not price_per_credit:
            return jsonify({"status": "error", "message": "Missing required fields"}), 400
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verify the credit belongs to the user and get available quantity
        cur.execute("""
            SELECT cc.id, cc.credits_earned, COALESCE(cc.credits_used, 0) as credits_used,
                   cc.listed_quantity, 
                   (cc.credits_earned - COALESCE(cc.credits_used, 0) - cc.listed_quantity) as available_credits,
                   p.id as project_id, p.name as project_name
            FROM carbon_credits cc
            JOIN projects p ON cc.project_id = p.id
            WHERE cc.id = %s AND p.user_id = %s
        """, (credit_id, session['user_id']))
        
        credit = cur.fetchone()
        if not credit:
            return jsonify({"status": "error", "message": "Credit not found"}), 404
        
        available_credits = float(credit[4])
        
        if quantity > available_credits:
            return jsonify({"status": "error", "message": f"Not enough credits available. You have {available_credits} credits available."}), 400
        
        # Update the listed quantity
        cur.execute("""
            UPDATE carbon_credits 
            SET listed_quantity = listed_quantity + %s 
            WHERE id = %s
        """, (quantity, credit_id))
        
        # Create the marketplace listing
        cur.execute("""
            INSERT INTO marketplace_listings (credit_id, seller_id, quantity_available, price_per_credit)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (credit_id, session['user_id'], quantity, price_per_credit))
        
        listing_id = cur.fetchone()[0]
        conn.commit()
        
        cur.close()
        conn.close()
        
        return jsonify({"status": "success", "message": "Credits listed successfully", "listing_id": listing_id})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/marketplace/buy/<int:listing_id>', methods=['POST'])
def purchase_credits(listing_id):
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    conn = None
    cur = None
    try:
        data = request.get_json()
        print(f"DEBUG: purchase_credits data: {data}")
        quantity = float(data.get('quantity', 0))
        # Accept destination_project_id or project_id
        buyer_project_id = data.get('destination_project_id') or data.get('project_id')
        payment_reference = data.get('payment_reference')
        
        if not quantity or quantity <= 0:
            return jsonify({"status": "error", "message": "Invalid quantity"}), 400
        
        if not buyer_project_id:
            return jsonify({"status": "error", "message": "Please select a project to assign the credits to"}), 400
        
        conn = get_db_connection()
        conn.autocommit = False
        cur = conn.cursor()
        
        # Get the listing details
        cur.execute("""
            SELECT ml.id, ml.credit_id, ml.quantity_available, ml.price_per_credit, ml.seller_id,
                   cc.credits_earned, COALESCE(cc.credits_used, 0) as credits_used,
                   cc.listed_quantity, cc.project_id as seller_project_id
            FROM marketplace_listings ml
            JOIN carbon_credits cc ON ml.credit_id = cc.id
            WHERE ml.id = %s AND ml.status = 'active'
        """, (listing_id,))
        
        listing = cur.fetchone()
        if not listing:
            return jsonify({"status": "error", "message": "Listing not found"}), 404
        
        listing_id_db, credit_id, available_quantity, price_per_credit, seller_id, earned, used, listed_qty, seller_project_id = listing
        available_quantity = float(available_quantity)
        price_per_credit = float(price_per_credit)
        
        if seller_id == session['user_id']:
            return jsonify({"status": "error", "message": "Cannot buy your own credits"}), 400
        
        if quantity > available_quantity:
            return jsonify({"status": "error", "message": "Not enough credits available"}), 400
        
        total_price = quantity * price_per_credit
        
        # Verify buyer's project belongs to them
        cur.execute("SELECT id, name FROM projects WHERE id = %s AND user_id = %s", 
                   (buyer_project_id, session['user_id']))
        buyer_project = cur.fetchone()
        if not buyer_project:
            return jsonify({"status": "error", "message": "Invalid project"}), 400
        
        # Update the marketplace listing
        new_quantity = available_quantity - quantity
        if new_quantity <= 0:
            cur.execute("UPDATE marketplace_listings SET quantity_available = 0, status = 'sold' WHERE id = %s", (listing_id,))
        else:
            cur.execute("UPDATE marketplace_listings SET quantity_available = %s WHERE id = %s", (new_quantity, listing_id))
        
        # Update the seller's carbon credit (reduce listed quantity and increase used quantity)
        cur.execute("""
            UPDATE carbon_credits 
            SET listed_quantity = GREATEST(listed_quantity - %s, 0),
                credits_used = COALESCE(credits_used, 0) + %s
            WHERE id = %s
        """, (quantity, quantity, credit_id))
        
        # Create a new carbon credit for the buyer
        # FIXED: Added user_id
        cur.execute("""
            INSERT INTO carbon_credits (user_id, project_id, credits_earned, credit_value, source, status, issued_at)
            VALUES (%s, %s, %s, %s, 'PURCHASED', 'AVAILABLE', NOW())
            RETURNING id
        """, (session['user_id'], buyer_project_id, quantity, total_price))
        
        new_credit_id = cur.fetchone()[0]
        
        # Record the transaction
        cur.execute("""
            INSERT INTO carbon_credit_transactions 
            (from_user_id, to_user_id, quantity, from_project_id, to_project_id, listing_id, 
             transaction_type, status, price_per_credit, total_price, payment_reference, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, 'PURCHASE', 'COMPLETED', %s, %s, %s, NOW())
        """, (seller_id, session['user_id'], quantity, seller_project_id, buyer_project_id, listing_id,
              price_per_credit, total_price, payment_reference))
        
        # Commit the transaction
        conn.commit()
        
        return jsonify({
            "status": "success", 
            "message": f"Purchase completed successfully. {quantity} credits added to {buyer_project[1]}",
            "credit_id": new_credit_id,
            "quantity": quantity,
            "total_price": total_price
        })
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        # Clean up without changing autocommit
        if cur:
            cur.close()
        if conn:
            conn.close()



@app.route('/api/marketplace/my-listings')
def get_my_listings():
    """Get the current user's marketplace listings"""
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get user's marketplace listings
        cur.execute("""
            SELECT ml.id, ml.quantity_available, ml.price_per_credit, ml.listed_at, ml.status,
                   p.name as project_name, p.type as project_type,
                   cc.credits_earned, COALESCE(cc.credits_used, 0) as credits_used
            FROM marketplace_listings ml
            JOIN carbon_credits cc ON ml.credit_id = cc.id
            JOIN projects p ON cc.project_id = p.id
            WHERE ml.seller_id = %s
            ORDER BY ml.listed_at DESC
        """, (session['user_id'],))
        
        listings = []
        for row in cur.fetchall():
            listings.append({
                'id': row[0],
                'quantity_available': float(row[1]),
                'price_per_credit': float(row[2]),
                'listed_at': row[3].isoformat() if row[3] else None,
                'status': row[4],
                'project_name': row[5],
                'project_type': row[6],
                'credits_earned': float(row[7]),
                'credits_used': float(row[8]) if row[8] else 0
            })
        
        cur.close()
        conn.close()
        
        return jsonify({"status": "success", "listings": listings})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/marketplace/listing/<int:listing_id>', methods=['DELETE'])
def delete_listing(listing_id):
    """Delete a marketplace listing"""
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verify the listing belongs to the user
        cur.execute("SELECT seller_id FROM marketplace_listings WHERE id = %s", (listing_id,))
        listing = cur.fetchone()
        
        if not listing or listing[0] != session['user_id']:
            return jsonify({"status": "error", "message": "Listing not found"}), 404
        
        # Delete the listing
        cur.execute("DELETE FROM marketplace_listings WHERE id = %s", (listing_id,))
        conn.commit()
        
        cur.close()
        conn.close()
        
        return jsonify({"status": "success", "message": "Listing deleted successfully"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/user/credits')
def get_user_credits():
    """Get the current user's available carbon credits"""
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get user's carbon credits with available quantity
        cur.execute("""
            SELECT cc.id, p.name as project_name, cc.credits_earned, 
                   COALESCE(cc.credits_used, 0) as credits_used,
                   cc.listed_quantity,
                   (cc.credits_earned - COALESCE(cc.credits_used, 0) - cc.listed_quantity) as available_credits,
                   cc.credit_value
            FROM carbon_credits cc
            JOIN projects p ON cc.project_id = p.id
            WHERE p.user_id = %s
            ORDER BY p.name
        """, (session['user_id'],))
        
        credits = []
        for row in cur.fetchall():
            credits.append({
                'id': row[0],
                'project_name': row[1],
                'credits_earned': float(row[2]),
                'credits_used': float(row[3]),
                'listed_quantity': float(row[4]),
                'available_credits': float(row[5]),
                'credit_value': float(row[6]) if row[6] else 0
            })
        
        cur.close()
        conn.close()
        
        return jsonify({"status": "success", "credits": credits})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/user/projects')
def get_user_projects():
    """Get the current user's projects for credit assignment"""
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get user's projects
        cur.execute("""
            SELECT id, name 
            FROM projects 
            WHERE user_id = %s
            ORDER BY name
        """, (session['user_id'],))
        
        projects = []
        for row in cur.fetchall():
            projects.append({
                'id': row[0],
                'name': row[1]
            })
        
        cur.close()
        conn.close()
        
        return jsonify({"status": "success", "projects": projects})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ====================================
# Payment Route
# ====================================
@app.route('/carbon/payment')
def carbon_payment():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    return render_template('payment.html', 
                           username=session.get('username', 'User'))

@app.route('/api/marketplace/complete-purchase', methods=['POST'])
def complete_purchase():
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    conn = None
    cur = None
    try:
        data = request.get_json()
        # Handle different parameter names from potential legacy/different logical flows
        listing_id = data.get('listingId') or data.get('listing_id')
        quantity = float(data.get('quantity', 0))
        buyer_project_id = data.get('projectId') or data.get('project_id') or data.get('destination_project_id')
        payment_reference = data.get('payment_reference') or data.get('paymentDetails', {}).get('reference') or 'LEGACY_PAYMENT'
        
        if not quantity or quantity <= 0:
            return jsonify({"status": "error", "message": "Invalid quantity"}), 400
        
        if not buyer_project_id:
            return jsonify({"status": "error", "message": "Please select a project to assign the credits to"}), 400
        
        conn = get_db_connection()
        conn.autocommit = False
        cur = conn.cursor()
        
        # Get the listing details
        cur.execute("""
            SELECT ml.id, ml.credit_id, ml.quantity_available, ml.price_per_credit, ml.seller_id,
                   cc.credits_earned, COALESCE(cc.credits_used, 0) as credits_used,
                   cc.listed_quantity, cc.project_id as seller_project_id
            FROM marketplace_listings ml
            JOIN carbon_credits cc ON ml.credit_id = cc.id
            WHERE ml.id = %s AND ml.status = 'active'
        """, (listing_id,))
        
        listing = cur.fetchone()
        if not listing:
            return jsonify({"status": "error", "message": "Listing not found"}), 404
        
        listing_id_db, credit_id, available_quantity, price_per_credit, seller_id, earned, used, listed_qty, seller_project_id = listing
        available_quantity = float(available_quantity)
        price_per_credit = float(price_per_credit)
        
        if seller_id == session['user_id']:
            return jsonify({"status": "error", "message": "Cannot buy your own credits"}), 400
        
        if quantity > available_quantity:
            return jsonify({"status": "error", "message": "Not enough credits available"}), 400
        
        total_price = quantity * price_per_credit
        
        # Verify buyer's project belongs to them
        cur.execute("SELECT id, name FROM projects WHERE id = %s AND user_id = %s", 
                   (buyer_project_id, session['user_id']))
        buyer_project = cur.fetchone()
        if not buyer_project:
            return jsonify({"status": "error", "message": "Invalid project"}), 400
        
        # Update the marketplace listing
        new_quantity = available_quantity - quantity
        if new_quantity <= 0:
            cur.execute("UPDATE marketplace_listings SET quantity_available = 0, status = 'sold' WHERE id = %s", (listing_id,))
        else:
            cur.execute("UPDATE marketplace_listings SET quantity_available = %s WHERE id = %s", (new_quantity, listing_id))
        
        # Update the seller's carbon credit (reduce listed quantity and increase used quantity)
        cur.execute("""
            UPDATE carbon_credits 
            SET listed_quantity = GREATEST(listed_quantity - %s, 0),
                credits_used = COALESCE(credits_used, 0) + %s
            WHERE id = %s
        """, (quantity, quantity, credit_id))
        
        # Create a new carbon credit for the buyer
        # FIXED: Explicitly set user_id and source
        cur.execute("""
            INSERT INTO carbon_credits (user_id, project_id, credits_earned, credit_value, source, status, issued_at)
            VALUES (%s, %s, %s, %s, 'PURCHASED', 'AVAILABLE', NOW())
            RETURNING id
        """, (session['user_id'], buyer_project_id, quantity, total_price))
        
        new_credit_id = cur.fetchone()[0]
        
        # Record the transaction
        cur.execute("""
            INSERT INTO carbon_credit_transactions 
            (from_user_id, to_user_id, quantity, from_project_id, to_project_id, listing_id, 
             transaction_type, status, price_per_credit, total_price, payment_reference, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, 'PURCHASE', 'COMPLETED', %s, %s, %s, NOW())
        """, (seller_id, session['user_id'], quantity, seller_project_id, buyer_project_id, listing_id,
              price_per_credit, total_price, payment_reference))
        
        conn.commit()
        
        return jsonify({
            "status": "success", 
            "message": f"Purchase completed successfully. {quantity} credits added to {buyer_project[1]}",
            "credit_id": new_credit_id,
            "quantity": quantity,
            "total_price": total_price
        })
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()



# ====================================
# MAIN ENTRY POINT
# ====================================
if __name__ == '__main__':
    # Configure logging for production
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]',
        handlers=[
            logging.FileHandler('app.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # For production, use port from environment or default to 5000
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)