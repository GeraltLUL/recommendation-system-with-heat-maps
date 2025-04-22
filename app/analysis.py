# app/analysis.py

import numpy as np
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import StandardScaler
from flask import current_app
from .models import GameEvent
from . import db # Might not be needed if only querying

def cluster_level_zones(level_id, session_id=None, eps=0.3, min_samples=10):
    """
    Performs DBSCAN clustering on position data (X, Z) for a given level ID.
    Calculates scaling parameters to map original coordinates to a target display area.

    Args:
        level_id (str): The ID of the level to analyze.
        session_id (str, optional): Filter by a specific session ID. Defaults to None.
        eps (float): DBSCAN parameter: Maximum distance between samples.
        min_samples (int): DBSCAN parameter: Minimum samples in a neighborhood.

    Returns:
        dict: A dictionary containing results including scaling parameters:
              {'levelId', 'sessionId', 'zones', 'noise_points', 'parameters', 'scaling'}
              or {'error': message}
    """
    
    # 1. Query Data
    query = GameEvent.query.filter(
        GameEvent.event_type == 'position_update',
        GameEvent.level_id == level_id,
        GameEvent.position_x.isnot(None),
        GameEvent.position_z.isnot(None)
    )
    if session_id:
        query = query.filter(GameEvent.session_id == session_id)
        
    # Fetch X and Z coordinates
    points = query.with_entities(GameEvent.position_x, GameEvent.position_z).all()

    if not points or len(points) < min_samples: # Need enough points for DBSCAN
        return {
            "levelId": level_id,
            "sessionId": session_id,
            "zones": [],
            "noise_points": len(points), # All points are noise if too few
            "parameters": {"eps": eps, "min_samples": min_samples},
            "scaling": None, # No scaling if no data
            "message": "Not enough data points for clustering."
        }

    points_array = np.array([(p[0], p[1]) for p in points])
    
    # --- Calculate Scaling Parameters --- 
    # Based on the actual points used for clustering
    min_x = np.min(points_array[:, 0])
    max_x = np.max(points_array[:, 0])
    min_z = np.min(points_array[:, 1])
    max_z = np.max(points_array[:, 1])

    range_x = max_x - min_x
    range_z = max_z - min_z

    target_width = 580 # Match heatmap target size
    target_height = 380
    padding = 10

    scale = 1.0 # Default scale
    offset_x = padding
    offset_y = padding
    
    if range_x == 0 and range_z == 0:
        offset_x = target_width / 2 + padding
        offset_y = target_height / 2 + padding
    elif range_x == 0:
        scale = target_height / range_z if range_z > 0 else 1
        offset_x = target_width / 2 + padding
    elif range_z == 0:
        scale = target_width / range_x if range_x > 0 else 1
        offset_y = target_height / 2 + padding
    else:
         scale_x = target_width / range_x
         scale_z = target_height / range_z
         scale = min(scale_x, scale_z)
    # Keep default offsets (padding) when both ranges > 0
         
    scaling_params = {
        "min_x": float(min_x), "max_x": float(max_x),
        "min_z": float(min_z), "max_z": float(max_z),
        "scale": float(scale), 
        "offset_x": float(offset_x),
        "offset_y": float(offset_y)
    }
    # ----------------------------------

    # 2. Scale Data
    scaler = StandardScaler()
    scaled_points = scaler.fit_transform(points_array)

    # 3. Apply DBSCAN
    dbscan = DBSCAN(eps=eps, min_samples=min_samples).fit(scaled_points)
    labels = dbscan.labels_
    unique_labels = set(labels)

    # 4. Analyze Clusters
    cluster_results = []
    noise_points_count = int(np.sum(labels == -1))

    all_sizes = []
    cluster_data_temp = {}

    for k in unique_labels:
        if k == -1: continue # Skip noise for now

        class_member_mask = (labels == k)
        cluster_points = points_array[class_member_mask] # Original coords
        cluster_size = cluster_points.shape[0]
        all_sizes.append(cluster_size)
        
        # Calculate centroid (mean) and potentially bounding box or convex hull later
        centroid = np.mean(cluster_points, axis=0)

        cluster_data_temp[k] = {
            "cluster_id": int(k),
            "size": cluster_size,
            "centroid_x": float(centroid[0]),
            "centroid_z": float(centroid[1]),
            # Add popularity later
        }

    # 5. Classify Popularity
    if all_sizes: # Check if there are any clusters found
        threshold_popular = np.percentile(all_sizes, 80) # Top 20% are popular
        threshold_unpopular = np.percentile(all_sizes, 20) # Bottom 20% are unpopular
    else:
        threshold_popular = 0
        threshold_unpopular = 0
        
    for k, cluster in cluster_data_temp.items():
        if cluster['size'] >= threshold_popular and threshold_popular > 0: # Check threshold > 0 to avoid classifying all as popular if only one cluster
            cluster['popularity'] = 'popular' # Green
        elif cluster['size'] <= threshold_unpopular:
            cluster['popularity'] = 'unpopular' # Red
        else:
            cluster['popularity'] = 'moderate' # Yellow/Orange
        cluster_results.append(cluster)

    # Sort results by size descending for clarity
    cluster_results.sort(key=lambda x: x['size'], reverse=True)

    return {
        "levelId": level_id,
        "sessionId": session_id,
        "zones": cluster_results,
        "noise_points": noise_points_count,
        "parameters": {"eps": eps, "min_samples": min_samples},
        "scaling": scaling_params # Add scaling info to response
    } 

def get_event_coords_by_zone(level_id, session_id=None, event_type='death', zones=None):
    """
    Получает события указанного типа и распределяет их координаты по ближайшим зонам.

    Args:
        level_id (str): ID уровня.
        session_id (str, optional): ID сессии (если нужно фильтровать).
        event_type (str): Тип события для поиска (e.g., 'death').
        zones (list, optional): Список словарей зон из cluster_level_zones
                                (должен содержать 'cluster_id', 'centroid_x', 'centroid_z').
                                Если None, зоны не будут определены.

    Returns:
        dict: Словарь, где ключ - cluster_id, а значение - список кортежей (x, z)
              координат событий этого типа в данной зоне.
              Ключ -1 используется для событий, не попавших ни в одну зону (шум).
    """
    if not zones:
        return {}

    try:
        # 1. Запросить события нужного типа с координатами
        query = db.session.query(GameEvent.position_x, GameEvent.position_z)\
                    .filter(GameEvent.level_id == level_id)\
                    .filter(GameEvent.event_type == event_type)\
                    .filter(GameEvent.position_x.isnot(None))\
                    .filter(GameEvent.position_z.isnot(None))

        if session_id:
            query = query.filter(GameEvent.session_id == session_id)

        event_coords = query.all() # Список кортежей (x, z)

        if not event_coords:
            return {}

        # 2. Подготовить данные для сопоставления
        event_points = np.array([(x, z) for x, z in event_coords])
        zone_centroids = np.array([(z['centroid_x'], z['centroid_z']) for z in zones if z.get('cluster_id', -1) != -1])
        zone_ids = [z['cluster_id'] for z in zones if z.get('cluster_id', -1) != -1]

        if zone_centroids.shape[0] == 0: # Если зон нет (только шум в cluster_level_zones)
             return {-1: event_coords} # Все события считаем шумом

        events_by_zone = {zid: [] for zid in zone_ids}
        events_by_zone[-1] = [] # Для шума

        # 3. Сопоставить каждое событие с ближайшим центроидом зоны
        for i, point in enumerate(event_points):
            distances = np.linalg.norm(zone_centroids - point, axis=1)
            closest_zone_index = np.argmin(distances)
            # TODO: Возможно, добавить порог максимального расстояния до центроида,
            # чтобы считать событие шумом, если оно слишком далеко от любой зоны.
            # пока просто присваиваем ближайшей.
            assigned_zone_id = zone_ids[closest_zone_index]
            events_by_zone[assigned_zone_id].append(event_coords[i]) # Добавляем оригинальные координаты (x, z)

        return events_by_zone

    except Exception as e:
        current_app.logger.error(f"Error getting '{event_type}' events by zone for level {level_id}: {e}", exc_info=True)
        return {} # Возвращаем пустой словарь в случае ошибки