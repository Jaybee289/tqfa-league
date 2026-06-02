from collections import Counter


# ---------------------------------------------------------------------------
# Player helpers
# ---------------------------------------------------------------------------

def get_player_name(player_id, players_map):
    if player_id and player_id in players_map:
        return players_map[player_id]['web_name']
    return "Unknown Player"


def get_player_team(player_id, players_map):
    if player_id and player_id in players_map:
        return players_map[player_id]['team']
    return "Unknown Team"


# ---------------------------------------------------------------------------
# Team building
# ---------------------------------------------------------------------------

def build_team(picks, live_elements, players_map):
    """Replicates FPL's auto-sub logic to return final XI and bench."""
    starters = [p for p in picks if p['position'] <= 11]
    bench = sorted([p for p in picks if p['position'] > 11], key=lambda x: x['position'])
    final_xi = list(starters)
    final_bench = list(bench)

    non_playing_indices = [
        i for i, s in enumerate(final_xi)
        if live_elements.get(s['element'], {}).get('stats', {}).get('minutes', 0) == 0
    ]
    used_bench_indices = set()

    for starter_idx in non_playing_indices:
        starter_to_replace = final_xi[starter_idx]
        starter_type = players_map[starter_to_replace['element']]['element_type']

        for bench_idx, bench_player in enumerate(final_bench):
            if bench_idx in used_bench_indices:
                continue
            if live_elements.get(bench_player['element'], {}).get('stats', {}).get('minutes', 0) > 0:
                bench_type = players_map[bench_player['element']]['element_type']
                valid_swap = False
                if starter_type == 1:
                    if bench_type == 1:
                        valid_swap = True
                else:
                    if bench_type != 1:
                        temp_xi = [p for i, p in enumerate(final_xi) if i != starter_idx] + [bench_player]
                        temp_formation = Counter(
                            players_map[p['element']]['element_type'] for p in temp_xi
                        )
                        if temp_formation.get(2, 0) >= 3 and temp_formation.get(4, 0) >= 1:
                            valid_swap = True
                if valid_swap:
                    final_xi[starter_idx], final_bench[bench_idx] = bench_player, starter_to_replace
                    used_bench_indices.add(bench_idx)
                    break

    return final_xi, final_bench


def calculate_original_team_score(prev_gw_picks, live_elements):
    original_score = 0
    starters = [p for p in prev_gw_picks if p['position'] <= 11]
    bench = [p for p in prev_gw_picks if p['position'] > 11]
    non_playing_starters = 0
    for pick in starters:
        player_id = pick['element']
        player_live_stats = live_elements.get(player_id, {}).get('stats', {})
        if player_live_stats.get('minutes', 0) == 0:
            non_playing_starters += 1
        original_score += player_live_stats.get('total_points', 0) * pick['multiplier']
    if non_playing_starters > 0:
        for bench_player in bench:
            if non_playing_starters == 0:
                break
            b_stats = live_elements.get(bench_player['element'], {}).get('stats', {})
            if b_stats.get('minutes', 0) > 0:
                original_score += b_stats.get('total_points', 0)
                non_playing_starters -= 1
    return original_score

# ---------------------------------------------------------------------------
# Division standings sorter — full season tiebreaker chain
#
# Priority (all descending unless noted):
#   1. Total FPL points (season)
#   2. Captain points (season)
#   3. Goals scored (season)
#   4. Net defensive score (season)
#   5. Vice captain points (season)
#   6. Overall FPL rank (ascending — lower number is better)
# ---------------------------------------------------------------------------

def get_division_sort_key(manager_id, master_data):
    m = master_data['managers'][manager_id]
    totals = m.get('season_totals', {})
    return (
        m['stats'].get('total_points', 0),                          # 1
        totals.get('total_captain_pts', 0),                         # 2
        totals.get('goals_scored', 0),                              # 3
        totals.get('net_defensive_score', 0),                       # 4
        totals.get('total_vice_pts', 0),                            # 5
        -m.get('current_overall_rank', 9_999_999)                   # 6 (lower rank = better)
    )


def sorted_division_standings(division_name, master_data):
    """Returns manager IDs sorted by division standing rules."""
    div = master_data['divisions'][division_name]
    return sorted(
        div.get('manager_ids', []),
        key=lambda mid: get_division_sort_key(mid, master_data),
        reverse=True
    )


# ---------------------------------------------------------------------------
# Block helpers
# ---------------------------------------------------------------------------

def get_current_block(gameweek, master_data):
    for block_name, block_data in master_data['competitions']['blocks'].items():
        if gameweek in block_data['gws']:
            return block_name, block_data
    return None, None


def is_block_final_gw(gameweek, master_data):
    block_name, block_data = get_current_block(gameweek, master_data)
    if block_data and gameweek == block_data['gws'][-1]:
        return block_name, block_data
    return None, None


# ---------------------------------------------------------------------------
# Cup knockout round labeller
# ---------------------------------------------------------------------------

def get_knockout_round_label(num_remaining):
    """Returns the round name based on number of managers still in the cup."""
    mapping = {
        16: "Last 16 (1st Leg)",
        8:  "Quarter-Final (1st Leg)",
        4:  "Semi-Final (1st Leg)",
        2:  "Final",
    }
    return mapping.get(num_remaining, f"Knockout ({num_remaining} remaining)")
