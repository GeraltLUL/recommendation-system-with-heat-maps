from flask import current_app
# Импортируем новую функцию
from .analysis import get_event_coords_by_zone 

# --- Thresholds (can be moved to config later) ---
HIGH_DEATH_COUNT_THRESHOLD = 20 # Example: Warn if more than 20 deaths on level
# Новые пороги для "Зоны смерти"
ZONE_DEATH_THRESHOLD_ABS = 5  # Минимум N смертей в зоне для срабатывания
ZONE_DEATH_THRESHOLD_REL_AVG = 2.0 # Смертей в зоне в N раз больше среднего по зонам
ZONE_DEATH_THRESHOLD_REL_TOTAL = 0.1 # Смертей в зоне составляют > N% от всех смертей

def generate_recommendations(level_id, zone_data=None, event_counts=None, session_id=None): # Добавлен session_id
    """
    Generates a list of recommendations based on zone analysis and event counts.

    Args:
        level_id (str): The ID of the level being analyzed.
        zone_data (dict): The dictionary returned by the clustering analysis
                          (containing 'zones', 'parameters', 'error' etc.).
        event_counts (dict): A dictionary mapping event_type to its count for the level.
        session_id (str, optional): ID сессии (для фильтрации данных для правил).

    Returns:
        list: A list of strings, where each string is a recommendation.
    """
    recommendations = []

    if zone_data is None:
        zone_data = {} # Avoid errors if zone_data is missing
    if event_counts is None:
        event_counts = {} # Avoid errors if event_counts is missing

    zones = zone_data.get('zones', []) # Получаем список зон

    # --- Rule 1: Unpopular Zones ---
    unpopular_zones = []
    if zones: # Only run if clustering was successful and returned zones
        for zone in zones:
            # Use .get() for safety, cluster_id might be -1 for noise
            if zone.get('popularity') == 'unpopular' and zone.get('cluster_id', -1) != -1:
                unpopular_zones.append(zone)

        if unpopular_zones:
            # Format IDs safely, handling potential missing cluster_id
            zone_ids = [str(z.get('cluster_id', '?')) for z in unpopular_zones]
            recommendations.append(
                f"Обнаружены непопулярные зоны: ID(s) {', '.join(zone_ids)}. "
                f"Рассмотрите возможность добавления интереса/награды или улучшения навигации к этим зонам."
            )

    # --- Rule 2: High Total Deaths ---
    total_deaths = event_counts.get('death', 0)
    if total_deaths > HIGH_DEATH_COUNT_THRESHOLD:
        recommendations.append(
            f"Общее количество смертей на уровне ({total_deaths}) высокое. "
            f"Возможно, стоит пересмотреть общую сложность уровня или добавить точки сохранения/помощь."
        )
        
    # --- Rule 3: Zone of Death ---
    if zones and total_deaths > 0: # Запускаем только если есть зоны и смерти
        try:
            # Получаем координаты смертей, распределенные по зонам
            deaths_by_zone_coords = get_event_coords_by_zone(
                level_id,
                session_id=session_id, # Передаем session_id для фильтрации
                event_type='death',
                zones=zones
            )

            # Считаем количество смертей в каждой зоне
            death_counts_per_zone = {
                zone_id: len(coords)
                for zone_id, coords in deaths_by_zone_coords.items()
                if zone_id != -1 # Исключаем шум (-1) из анализа зон смерти
            }

            if death_counts_per_zone: # Если есть данные по смертям в зонах
                num_zones_with_deaths = len(death_counts_per_zone)
                # Используем общее количество смертей из event_counts для расчета среднего
                avg_deaths_per_zone = total_deaths / num_zones_with_deaths if num_zones_with_deaths > 0 else 0 

                problem_zones = []
                for zone in zones:
                    zone_id = zone.get('cluster_id')
                    if zone_id == -1 or zone_id is None: continue # Пропускаем шум

                    zone_deaths = death_counts_per_zone.get(zone_id, 0)

                    # Применяем пороги
                    is_problem = False
                    if zone_deaths >= ZONE_DEATH_THRESHOLD_ABS:
                         # Проверка относительных порогов (чтобы избежать срабатывания на очень маленьких уровнях)
                         # или если среднее = 0
                         relative_avg_check = avg_deaths_per_zone > 0 and zone_deaths > avg_deaths_per_zone * ZONE_DEATH_THRESHOLD_REL_AVG
                         relative_total_check = total_deaths > 0 and (zone_deaths / total_deaths) > ZONE_DEATH_THRESHOLD_REL_TOTAL
                         
                         if relative_avg_check or relative_total_check:
                            is_problem = True
                         # Consider edge case: if avg is 0 but deaths > abs threshold, maybe still flag?
                         elif avg_deaths_per_zone == 0:
                             is_problem = True # Flag if abs threshold met and avg is zero

                    if is_problem:
                        problem_zones.append({
                            "id": zone_id,
                            "deaths": zone_deaths,
                            "centroid_x": zone.get('centroid_x'),
                            "centroid_z": zone.get('centroid_z')
                        })

                if problem_zones:
                    # Сортируем проблемные зоны по убыванию смертей
                    problem_zones.sort(key=lambda z: z['deaths'], reverse=True)
                    rec_text = "Обнаружены зоны с аномально высоким уровнем смертей: "
                    zone_details = []
                    for pz in problem_zones:
                         coord_text = f"({pz['centroid_x']:.1f}, {pz['centroid_z']:.1f})" if pz['centroid_x'] is not None and pz['centroid_z'] is not None else ""
                         zone_details.append(f"Зона {pz['id']} ({pz['deaths']} смертей {coord_text})")
                    rec_text += "; ".join(zone_details)
                    rec_text += ". Рекомендуется пересмотреть сложность или добавить подсказки в этих зонах."
                    recommendations.append(rec_text)

        except Exception as e:
             current_app.logger.error(f"Error during 'Zone of Death' analysis for level {level_id}: {e}", exc_info=True)
             # Не добавляем специфическую ошибку, чтобы не загромождать вывод


    if not recommendations:
        recommendations.append("На данный момент автоматических рекомендаций по улучшению уровня не сформировано.")

    # Use logger if available, otherwise print
    try:
        current_app.logger.info(f"Generated {len(recommendations)} recommendations for level {level_id}")
    except RuntimeError: # Handle cases outside of app context if needed
         print(f"Generated {len(recommendations)} recommendations for level {level_id}")

    return recommendations

# --- Helper functions (can be added later if needed) ---
# def calculate_deaths_per_zone(level_id, zone_data):
#     # ... implementation ...
#     pass