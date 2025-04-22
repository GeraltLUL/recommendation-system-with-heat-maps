from flask import Blueprint, render_template, request, flash, redirect, url_for, abort, current_app
from flask_login import login_required, current_user
from sqlalchemy import desc, asc, func, distinct

from . import db
from .models import GameEvent
from .admin import analyst_or_admin_required, admin_required

# Define the blueprint
bp = Blueprint('db_viewer', __name__, url_prefix='/database')

@bp.route('/sessions')
@login_required
@analyst_or_admin_required
def view_sessions():
    """Displays a list of game sessions with summary info."""
    page = request.args.get('page', 1, type=int)
    per_page = 30 # Show more sessions per page
    filter_level_id = request.args.get('level_id', '').strip()

    # Query to get session summaries
    # We need session_id, first level_id, min timestamp, max timestamp, count
    subquery = db.session.query(
        GameEvent.session_id,
        func.min(GameEvent.level_id).label('first_level_id'), # Get one level ID (e.g., the min alphabetically)
        func.min(GameEvent.timestamp).label('start_time'),
        func.max(GameEvent.timestamp).label('end_time'),
        func.count(GameEvent.id).label('event_count')
    ).group_by(GameEvent.session_id).subquery()

    query = db.session.query(subquery)

    # Apply level filter if provided
    if filter_level_id:
        # We need to join back to GameEvent to filter by level_id associated with the session
        # This is a bit complex, maybe filter on the first_level_id for simplicity?
        # Or filter sessions based on *any* event matching the level ID
        query = query.filter(subquery.c.session_id.in_(
            db.session.query(GameEvent.session_id).filter(GameEvent.level_id == filter_level_id).distinct()
        ))
        
    # Default sort: newest sessions first
    query = query.order_by(desc(subquery.c.end_time))

    try:
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        sessions = pagination.items
    except Exception as e:
        current_app.logger.error(f"Error querying sessions: {e}", exc_info=True)
        flash("Error loading session list.", "danger")
        pagination = None
        sessions = []
        
    # Get distinct levels for the filter dropdown
    available_levels = []
    try:
         levels_query = db.session.query(GameEvent.level_id)\
                             .filter(GameEvent.level_id.isnot(None))\
                             .distinct().order_by(GameEvent.level_id)
         available_levels = [level[0] for level in levels_query.all()]
    except Exception as e:
         current_app.logger.error(f"Error querying available levels for filter: {e}", exc_info=True)

    return render_template(
        'database_sessions.html', 
        sessions=sessions, 
        pagination=pagination,
        available_levels=available_levels,
        filter_level_id=filter_level_id
    )

@bp.route('/session/<string:session_id>')
@login_required
@analyst_or_admin_required
def view_session_events(session_id):
    """Display GameEvents for a specific session with filtering and sorting."""
    page = request.args.get('page', 1, type=int)
    per_page = 50 # Show more events per page for a single session

    # --- Filtering (within session) --- 
    filter_event_type = request.args.get('event_type', '').strip()
    # filter_level_id is not needed here, session is specific
    filter_event_data = request.args.get('event_data_query', '').strip()

    # Base query filtered by session_id
    query = GameEvent.query.filter(GameEvent.session_id == session_id)

    if filter_event_type:
        query = query.filter(GameEvent.event_type == filter_event_type)
    if filter_event_data:
        query = query.filter(GameEvent.event_data.ilike(f'%{filter_event_data}%'))

    # --- Sorting --- 
    sort_by = request.args.get('sort_by', 'timestamp') 
    order = request.args.get('order', 'asc') # Default to chronological order within session
    # print(f"--- Sorting requested: sort_by='{sort_by}', order='{order}'") # DEBUG
    order_func = desc if order == 'desc' else asc

    sortable_columns = {
        'id': GameEvent.id,
        'timestamp': GameEvent.timestamp,
        'event_type': GameEvent.event_type,
        'level_id': GameEvent.level_id, # Might change within session
    }

    sort_column_obj = sortable_columns.get(sort_by) # Get column object
    if sort_column_obj is not None:
        # print(f"--- Applying sort: {order_func.__name__}({sort_column_obj})") # DEBUG
        query = query.order_by(order_func(sort_column_obj))
    else:
        sort_by = 'timestamp' # Fallback to default
        # print(f"--- Applying fallback sort: asc(GameEvent.timestamp) (original sort_by='{sort_by}')") # DEBUG
        query = query.order_by(asc(GameEvent.timestamp))
        order = 'asc' # Ensure order reflects fallback

    # DEBUG query print removed for brevity

    # --- Pagination --- 
    try:
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        events = pagination.items
    except Exception as e:
        current_app.logger.error(f"Error querying events for session {session_id}: {e}", exc_info=True)
        flash(f"Error loading events for session {session_id}.", "danger")
        pagination = None
        events = []

    # --- Prepare filter data for template (event types within this session) --- 
    distinct_event_types = []
    if events: # Query only if there are events to avoid unnecessary query
        try:
            types_query = db.session.query(GameEvent.event_type)\
                                .filter(GameEvent.session_id == session_id)\
                                .distinct().order_by(GameEvent.event_type)
            distinct_event_types = [item[0] for item in types_query.all()]
        except Exception as e:
            current_app.logger.error(f"Error querying event types for session {session_id}: {e}", exc_info=True)

    return render_template(
        'database_events.html', 
        session_id=session_id, # Pass session ID for context
        events=events, 
        pagination=pagination,
        # Pass filter values back to template
        filter_event_type=filter_event_type,
        filter_event_data=filter_event_data,
        distinct_event_types=distinct_event_types,
        # Pass sorting values back to template
        current_sort_by=sort_by,
        current_order=order
    )

@bp.route('/events/<int:event_id>/delete', methods=['POST'])
@login_required
@analyst_or_admin_required
def delete_event(event_id):
    """Deletes a specific GameEvent."""
    event_to_delete = db.session.get(GameEvent, event_id)
    if not event_to_delete:
        flash(f"Event with ID {event_id} not found.", "warning")
        return redirect(url_for('.view_sessions')) # Redirect to session list

    session_id_redirect = event_to_delete.session_id # Get session id before deleting
    try:
        db.session.delete(event_to_delete)
        db.session.commit()
        flash(f"Event #{event_id} deleted successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting event #{event_id}: {e}", "danger")
        import traceback
        traceback.print_exc()

    # Redirect back to the specific session view page it came from
    return redirect(url_for('.view_session_events', session_id=session_id_redirect))

@bp.route('/session/<string:session_id>/delete_all', methods=['POST'])
@login_required
@admin_required # Require admin for bulk delete
def delete_session_events_all(session_id):
    """Deletes ALL GameEvents for a specific session."""
    try:
        # Count events before deleting (optional, for flash message)
        count = GameEvent.query.filter_by(session_id=session_id).count()
        
        # Perform bulk delete
        deleted_count = GameEvent.query.filter_by(session_id=session_id).delete()
        db.session.commit()
        
        if deleted_count > 0:
            flash(f"Successfully deleted {deleted_count} events for session {session_id}.", "success")
        else:
            flash(f"No events found to delete for session {session_id}.", "info")
            
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting all events for session {session_id}: {e}", exc_info=True)
        flash(f"Error deleting events for session {session_id}.", "danger")

    # Redirect back to the main session list
    return redirect(url_for('.view_sessions'))

@bp.route('/level/<string:level_id>/delete_all', methods=['POST'])
@login_required
@admin_required # Require admin for bulk delete
def delete_level_events_all(level_id):
    """Deletes ALL GameEvents for a specific level."""
    if not level_id:
        flash("Level ID cannot be empty.", "warning")
        return redirect(url_for('.view_sessions'))
        
    try:
        # Count events before deleting
        count = GameEvent.query.filter_by(level_id=level_id).count()
        
        # Perform bulk delete
        deleted_count = GameEvent.query.filter_by(level_id=level_id).delete()
        db.session.commit()
        
        if deleted_count > 0:
            flash(f"Successfully deleted {deleted_count} events for level '{level_id}'.", "success")
        else:
            flash(f"No events found to delete for level '{level_id}'.", "info")
            
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting all events for level {level_id}: {e}", exc_info=True)
        flash(f"Error deleting events for level '{level_id}'.", "danger")

    # Redirect back to the main session list, preserving filter maybe?
    # For now, just redirect to the base list
    return redirect(url_for('.view_sessions'))