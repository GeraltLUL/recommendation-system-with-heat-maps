from flask import Blueprint, request, jsonify, current_app
from datetime import datetime, timezone, timedelta
import json

from . import db
from .models import GameEvent, User # Import necessary models
# Potentially import services if complex processing needed later
# from .services import process_incoming_event
from sqlalchemy import func # Needed for event counts
from .recommendations import generate_recommendations # Import for recommendations

# Define the blueprint
bp = Blueprint('api', __name__, url_prefix='/api')

def parse_iso_timestamp(timestamp_str):
    """Парсит строку ISO 8601, обрабатывая 'Z' и лишние доли секунды."""
    if not timestamp_str:
        return None
    try:
        # Заменяем 'Z' на '+00:00' для совместимости
        if timestamp_str.endswith('Z'):
            timestamp_str = timestamp_str[:-1] + '+00:00'

        # Проверяем и обрезаем доли секунды до 6 знаков
        dot_index = timestamp_str.find('.')
        # Ищем начало смещения (+ или -) после точки
        offset_index = -1
        plus_index = timestamp_str.find('+', dot_index if dot_index != -1 else 0)
        minus_index = timestamp_str.find('-', dot_index if dot_index != -1 else 0)
        if plus_index != -1 and minus_index != -1:
            offset_index = min(plus_index, minus_index)
        elif plus_index != -1:
            offset_index = plus_index
        elif minus_index != -1:
            offset_index = minus_index
        # else: offset_index remains -1 if no offset found
            
        if dot_index != -1:
            # Определяем конец дробной части (либо знак смещения, либо конец строки)
            end_fraction_index = offset_index if offset_index > dot_index else len(timestamp_str)
            fractional_part = timestamp_str[dot_index + 1 : end_fraction_index]

            if len(fractional_part) > 6:
                # Обрезаем до 6 знаков
                timestamp_str = timestamp_str[:dot_index + 1] + fractional_part[:6] + timestamp_str[end_fraction_index:]

        # Теперь парсим
        dt = datetime.fromisoformat(timestamp_str)

        # Убедимся, что время в UTC (на всякий случай, если +00:00 не было)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError as e:
        # Используем оригинальную строку в логе ошибки для ясности
        original_str = request.get_json().get('timeStamp', '') # Try to get original for log
        print(f"Warning: Could not parse timestamp string '{original_str}' (processed as '{timestamp_str}'), Error: {e}")
        return None

@bp.route('/events', methods=['POST'])
def receive_events():
    """Принимает батч событий от игрового клиента (Unity)."""
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    
    # --- Валидация батча ---
    session_id = data.get('sessionId')
    level_id = data.get('levelId') # Может быть null/пустым, если не установлен
    position_updates = data.get('positionUpdates', [])
    player_actions = data.get('playerActions', [])

    if not session_id:
        return jsonify({"error": "Missing sessionId"}), 400
    if not isinstance(position_updates, list):
         return jsonify({"error": "Invalid format for positionUpdates (must be a list)"}), 400
    if not isinstance(player_actions, list):
         return jsonify({"error": "Invalid format for playerActions (must be a list)"}), 400

    events_added = []
    try:
        # --- Обработка обновлений позиции ---
        for pos_event in position_updates:
            if not isinstance(pos_event, dict): continue # Пропускаем невалидные элементы

            timestamp_str = pos_event.get('timeStamp')
            position_data = pos_event.get('position')

            event_timestamp = parse_iso_timestamp(timestamp_str)

            # Пропускаем событие, если время или позиция невалидны
            if event_timestamp is None or position_data is None or not isinstance(position_data, dict):
                print(f"Warning: Skipping invalid position_update event (timestamp or position missing/invalid): {pos_event}")
                continue

            event = GameEvent(
                event_type='position_update',
                timestamp=event_timestamp,
                session_id=session_id,
                level_id=level_id,
                position_x=position_data.get('x'),
                position_y=position_data.get('y'),
                position_z=position_data.get('z'),
                event_data=None # Для position_update пока не храним доп. данные
            )
            events_added.append(event)

        # --- Обработка действий игрока ---
        for action_event in player_actions:
            if not isinstance(action_event, dict): continue # Пропускаем невалидные элементы

            timestamp_str = action_event.get('timeStamp')
            event_type_str = action_event.get('eventType') # Тип действия (jump, interact, etc.)
            position_data = action_event.get('position')
            action_details = action_event.get('actionDetails') # Опциональные детали

            event_timestamp = parse_iso_timestamp(timestamp_str)

            # Пропускаем событие, если время, тип или позиция невалидны
            if event_timestamp is None or event_type_str is None or position_data is None or not isinstance(position_data, dict):
                print(f"Warning: Skipping invalid player_action event (timestamp, eventType, or position missing/invalid): {action_event}")
                continue

            # Сохраняем actionDetails как JSON строку в event_data
            event_data_json = None
            if action_details is not None:
                try:
                    # Создаем словарь для консистентности
                    event_data_dict = {"details": action_details}
                    event_data_json = json.dumps(event_data_dict)
                except TypeError:
                     print(f"Warning: Could not serialize actionDetails to JSON: {action_details}")


            event = GameEvent(
                event_type=event_type_str, # Используем тип действия
                timestamp=event_timestamp,
                session_id=session_id,
                level_id=level_id,
                position_x=position_data.get('x'),
                position_y=position_data.get('y'),
                position_z=position_data.get('z'),
                event_data=event_data_json # Сохраняем детали
            )
            events_added.append(event)

        # --- Сохранение всех событий батча в БД ---
        if events_added:
            db.session.add_all(events_added)
            db.session.commit()
            print(f"Successfully processed {len(events_added)} events for session {session_id}")
            return jsonify({"message": f"{len(events_added)} events received and processed"}), 201
        else:
            print(f"No valid events found in batch for session {session_id}")
            return jsonify({"message": "No valid events processed from the batch"}), 200

    except Exception as e:
        db.session.rollback()
        # Логируем ошибку подробнее
        import traceback
        print(f"Error processing event batch for session {session_id}: {e}")
        traceback.print_exc()
        return jsonify({"error": "Failed to process event batch due to server error"}), 500

# Add other API endpoints here later (e.g., for heatmap data)

@bp.route('/heatmap', methods=['GET'])
def get_heatmap_data():
    """Provides position data for generating a heatmap."""
    level_id = request.args.get('level_id')
    session_id = request.args.get('session_id') # Optional

    if not level_id:
        return jsonify({"error": "Missing required parameter: level_id"}), 400

    try:
        query = GameEvent.query.filter(
            GameEvent.event_type == 'position_update',
            GameEvent.level_id == level_id
        )

        if session_id:
            query = query.filter(GameEvent.session_id == session_id)

        # Select X and Z coordinates (Y is usually height in Unity)
        position_events = query.with_entities(
            GameEvent.position_x,
            # GameEvent.position_y,
            GameEvent.position_z
        ).filter(
            GameEvent.position_x.isnot(None),
            GameEvent.position_z.isnot(None)
        ).all()

        if not position_events:
             return jsonify({
                "levelId": level_id,
                "sessionId": session_id,
                "points": [],
                "message": "No position data found for the given criteria."
            })

        # --- Scaling Logic --- Find min/max and scale to fit 600x400 container ---
        min_x = min(p.position_x for p in position_events)
        max_x = max(p.position_x for p in position_events)
        min_z = min(p.position_z for p in position_events)
        max_z = max(p.position_z for p in position_events)

        range_x = max_x - min_x
        range_z = max_z - min_z

        # Target dimensions (slightly smaller than container for padding)
        target_width = 580
        target_height = 380
        padding = 10 # Padding from edges

        # Handle cases where range is zero (all points are the same)
        if range_x == 0 and range_z == 0:
            scale = 1 # No scaling needed, place in center
            offset_x = target_width / 2 + padding
            offset_y = target_height / 2 + padding
        elif range_x == 0:
            # Scale based on Z only
            scale = target_height / range_z if range_z > 0 else 1
            offset_x = target_width / 2 + padding # Center horizontally
            offset_y = padding
        elif range_z == 0:
            # Scale based on X only
            scale = target_width / range_x if range_x > 0 else 1
            offset_x = padding
            offset_y = target_height / 2 + padding # Center vertically
        else:
             # Calculate scale based on the dimension that needs more scaling
             scale_x = target_width / range_x
             scale_z = target_height / range_z
             scale = min(scale_x, scale_z) # Use smaller scale to fit and maintain aspect ratio
             offset_x = padding
             offset_y = padding

        heatmap_data = [
            {
                # Scale and translate coordinates
                "x": int(offset_x + (event.position_x - min_x) * scale),
                "y": int(offset_y + (event.position_z - min_z) * scale), # Use Z for Y axis
                "value": 1
            }
            for event in position_events
        ]
        # -----------------------------------------------------------------------------

        response_data = {
            "levelId": level_id,
            "sessionId": session_id,
            "min_x": min_x, # Include bounds for debugging/info
            "max_x": max_x,
            "min_z": min_z,
            "max_z": max_z,
            "scale": scale,
            "points": heatmap_data
        }

        return jsonify(response_data)

    except Exception as e:
        # Log the exception for debugging
        import traceback
        print(f"Error generating heatmap data for level '{level_id}', session '{session_id}': {e}")
        traceback.print_exc()
        return jsonify({"error": "Failed to retrieve heatmap data", "details": str(e)}), 500

# --- Endpoint for Zone Clustering --- 
from .analysis import cluster_level_zones # Import the clustering function

@bp.route('/zones', methods=['GET'])
def get_level_zones():
    """Performs clustering and generates recommendations, returns zones & recs."""
    level_id = request.args.get('level_id')
    session_id = request.args.get('session_id') # Optional
    
    # Allow overriding DBSCAN parameters via query string
    try:
        eps = float(request.args.get('eps', 0.3))
        min_samples = int(request.args.get('min_samples', 10))
    except ValueError:
        return jsonify({"error": "Invalid format for eps or min_samples parameters."}), 400

    if not level_id:
        return jsonify({"error": "Missing required parameter: level_id"}), 400

    recommendations = [] # Initialize recommendations list
    try:
        # --- 1. Perform Clustering --- 
        zone_data = cluster_level_zones(
            level_id=level_id, 
            session_id=session_id, 
            eps=eps, 
            min_samples=min_samples
        )
        
        # --- 2. Generate Recommendations (if clustering successful) ---
        if "error" not in zone_data:
            try:
                # Get event counts (filtered by session if provided)
                event_counts_query = db.session.query(GameEvent.event_type, func.count(GameEvent.id))\
                                        .filter(GameEvent.level_id == level_id)
                if session_id:
                     event_counts_query = event_counts_query.filter(GameEvent.session_id == session_id)
                event_counts_dict = dict(event_counts_query.group_by(GameEvent.event_type).all())
                
                # Generate recommendations based on current zone data and counts
                recommendations = generate_recommendations(
                    level_id=level_id,
                    zone_data=zone_data, 
                    event_counts=event_counts_dict,
                    session_id=session_id
                )
            except Exception as rec_e:
                 current_app.logger.error(f"Error generating recommendations within /api/zones for level {level_id}: {rec_e}", exc_info=True)
                 recommendations.append("Ошибка при формировании автоматических рекомендаций.")
        
        # --- 3. Prepare Response --- 
        # Add recommendations to the response, even if clustering had an error (e.g., not enough data)
        response_data = zone_data.copy()
        response_data['recommendations'] = recommendations
        
        return jsonify(response_data)

    except Exception as e:
        # Log the exception for debugging
        current_app.logger.error(f"Error during zone processing/recommendation for level '{level_id}', session '{session_id}': {e}", exc_info=True)
        return jsonify({
            "error": "Failed processing zones/recommendations", 
            "details": str(e),
            "recommendations": ["Ошибка при обработке данных для рекомендаций."] # Return error message
            }), 500 