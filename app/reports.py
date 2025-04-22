from flask import Blueprint, render_template, abort, current_app, flash
from flask_login import login_required
from sqlalchemy import func, distinct
import numpy as np

# Assuming reports.py is inside 'app' directory
from . import db 
from .models import GameEvent
from .analysis import cluster_level_zones
from .admin import analyst_or_admin_required # Use existing decorator
from .recommendations import generate_recommendations # Import the new function

# Define the blueprint
bp = Blueprint('reports', __name__, url_prefix='/reports')

@bp.route('/') # Route for the selection page
@login_required
@analyst_or_admin_required
def select_level_report():
    """Displays a page to select a level for reporting."""
    try:
        # Query distinct, non-null level IDs
        levels_query = db.session.query(GameEvent.level_id)\
                             .filter(GameEvent.level_id.isnot(None))\
                             .distinct().order_by(GameEvent.level_id)
        available_levels = [level[0] for level in levels_query.all()]
    except Exception as e:
        current_app.logger.error(f"Error querying available levels: {e}", exc_info=True)
        available_levels = []
        flash("Could not load available levels.", "danger")
        
    return render_template('reports/select_level.html', levels=available_levels)

@bp.route('/level/<string:level_id>')
@login_required
@analyst_or_admin_required
def level_report(level_id):
    """Generates and displays a detailed report for a specific level."""
    
    # --- Query Basic Level Metrics --- 
    unique_sessions_count = 'N/A'
    event_counts_dict = {}
    total_activity_duration = 'N/A'
    time_range = (None, None)
    
    try:
        # Count unique sessions for this level
        unique_sessions_query = db.session.query(func.count(distinct(GameEvent.session_id)))\
                                        .filter(GameEvent.level_id == level_id)
        unique_sessions_count = unique_sessions_query.scalar()
        
        # Count key events (example: position_update, jump, interact, death)
        event_counts_query = db.session.query(GameEvent.event_type, func.count(GameEvent.id))\
                                .filter(GameEvent.level_id == level_id)\
                                .group_by(GameEvent.event_type)
        event_counts_dict = dict(event_counts_query.all())

        # Estimate activity time (approximation)
        # Get min/max timestamp for the level (can be slow on large tables without index)
        time_range_query = db.session.query(func.min(GameEvent.timestamp), func.max(GameEvent.timestamp))\
                             .filter(GameEvent.level_id == level_id)
        time_range = time_range_query.first()
        
        if time_range and time_range[0] and time_range[1]:
            total_activity_duration = time_range[1] - time_range[0]
        else:
            total_activity_duration = None # Explicitly None if no range
            
    except Exception as e:
        # Use Flask's logger
        current_app.logger.error(f"Error querying metrics for level {level_id}: {e}", exc_info=True)
        # Keep default 'N/A' values set above
        
    # --- Query available Session IDs for this level ---
    available_sessions = []
    try:
        sessions_query = db.session.query(GameEvent.session_id)\
                            .filter(GameEvent.level_id == level_id)\
                            .filter(GameEvent.session_id.isnot(None))\
                            .distinct().order_by(GameEvent.session_id) # Optional: order them
        available_sessions = [session[0] for session in sessions_query.all()]
    except Exception as e:
        current_app.logger.error(f"Error querying sessions for level {level_id}: {e}", exc_info=True)
        # Continue without session list if query fails

    # --- Get Zone Clustering Data --- 
    # Using default parameters for now
    zone_data = {}
    try:
        zone_data = cluster_level_zones(level_id=level_id)
    except Exception as e:
         current_app.logger.error(f"Error running clustering for level {level_id}: {e}", exc_info=True)
         # Add error info to zone_data to display on page
         zone_data = {"error": "Clustering failed.", "details": str(e)}
    
    # --- Generate Recommendations ---
    recommendations = []
    try:
        # Pass the results we already have
        recommendations = generate_recommendations(
            level_id=level_id,
            zone_data=zone_data, 
            event_counts=event_counts_dict
        )
    except Exception as e:
         current_app.logger.error(f"Error generating recommendations for level {level_id}: {e}", exc_info=True)
         # Add a generic error message to recommendations if generation fails
         recommendations.append("Ошибка при формировании автоматических рекомендаций.")
         
    # Check if level exists (basic check based on if any data was found)
    if unique_sessions_count == 0 and not zone_data.get('zones') and zone_data.get('noise_points', 0) == 0:
         abort(404, description=f"Level '{level_id}' not found or has no associated event data.")

    return render_template(
        'reports/level_report.html',
        level_id=level_id,
        unique_sessions=unique_sessions_count,
        event_counts=event_counts_dict,
        total_duration=total_activity_duration, 
        time_range=time_range, # Pass tuple for potential display
        zone_data=zone_data,
        available_sessions=available_sessions, # Pass session list to template
        recommendations=recommendations # Pass recommendations to template
    ) 