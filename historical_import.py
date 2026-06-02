"""
historical_import.py  —  Season Setup & Management Script
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Season-agnostic setup tool. Edit PREV_SEASON / CURR_SEASON each year.

Commands:
  --import        Pull previous season data, apply promo/rel, build master JSON
  --rematch       Match returning managers to new-season FPL IDs, remove leavers
  --configure     Auto-generate competition structure once manager count is final

Seasons are referenced by label (e.g. "2025/26") not "S4/S5", making this
reusable every year without renaming variables.
"""

import argparse, json, time, math, requests
from itertools import combinations

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG — update these each season
# ─────────────────────────────────────────────────────────────────────────────

PREV_SEASON_LABEL = "2025/26"
CURR_SEASON_LABEL = "2026/27"
PREV_LEAGUE_ID    = 666513
CURR_LEAGUE_ID    = 666513   # update when new-season league is created
LEAGUE_NAME       = "Torquay Free Agents"

PROMO_RELEGATE_PLACES = 2    # recalculated dynamically in --configure

# Previous season division assignments: entry_id (str) → division name
PREV_DIVISION_ASSIGNMENTS = {
   "5769435": "League Two",
    "4459437": "League Two",
    "1635682": "League One",
    "2486128": "League One",
    "3301913": "Premier League",
    "3260288": "League One",
    "5776116": "League Two",
    "5612331": "League Two",
    "8940746": "Premier League",
    "1311386": "League One",
    "3609421": "Premier League",
    "320115": "Championship",
    "8193": "Championship",
    "108342": "Premier League",
    "5763571": "League Two",
    "530": "Premier League",
    "4594048": "Premier League",
    "1892805": "Championship",
    "4769141": "League Two",
    "292826": "Championship",
    "4699530": "League One",
    "303717": "Championship",
    "4578493": "League Two",
    "3712865": "League One",
    "1384647": "Championship"
}

# Cup groups (populated by --configure, or set manually before GW1)
CUP_GROUPS = {}

PREV_ARCHIVE_FILE = f"season_{PREV_SEASON_LABEL.replace('/','-')}_import.json"
MASTER_FILE       = "league_master.json"

# ─────────────────────────────────────────────────────────────────────────────

BASE_URL       = "https://fantasy.premierleague.com/api/"
DIVISION_ORDER = ["Premier League", "Championship", "League One", "League Two"]

# ─────────────────────────────────────────────────────────────────────────────
# API helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get(url, retries=3):
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.RequestException as e:
            print(f"    ⚠  Attempt {attempt+1} failed: {e}")
            time.sleep(1.5 * (attempt + 1))
    print(f"    ✗  Failed: {url}")
    return {}

def fetch_league_managers(league_id):
    managers, page = [], 1
    while True:
        data = _get(f"{BASE_URL}leagues-classic/{league_id}/standings/?page_standings={page}")
        results = data.get('standings', {}).get('results', [])
        if not results:
            break
        managers.extend(results)
        if not data.get('standings', {}).get('has_next', False):
            break
        page += 1
    return managers

def fetch_history(entry_id):
    return _get(f"{BASE_URL}entry/{entry_id}/history/")

def fetch_entry_info(entry_id):
    return _get(f"{BASE_URL}entry/{entry_id}/")

# ─────────────────────────────────────────────────────────────────────────────
# Dynamic competition structure calculator
# ─────────────────────────────────────────────────────────────────────────────

def _choose_cup_group_count(total_managers, target_group_size=4, max_group_size=5):
    """
    Prefer groups of 4. If that does not divide cleanly, allow groups of 5
    so group sizes stay tidy and every manager plays everyone once.
    """
    # Exact groups of 4 are ideal.
    if total_managers % 4 == 0:
        return total_managers // 4

    # Exact groups of 5 are the clean fallback, e.g. 25 → 5 groups of 5.
    if total_managers % 5 == 0:
        return total_managers // 5

    # Otherwise choose the count that keeps all groups between 4 and 5 where possible.
    candidates = []
    for group_count in range(1, total_managers + 1):
        min_size = total_managers // group_count
        max_size = math.ceil(total_managers / group_count)
        if min_size >= 3 and max_size <= max_group_size:
            # Prefer sizes closest to 4, then fewer oversized groups.
            avg_size = total_managers / group_count
            candidates.append((abs(avg_size - target_group_size), max_size, group_count))
    if candidates:
        return sorted(candidates)[0][2]

    return max(1, math.ceil(total_managers / max_group_size))


def _round_robin_round_count(group_size):
    """Number of matchdays needed for one full round-robin, including bye rounds."""
    return group_size if group_size % 2 == 1 else max(0, group_size - 1)


def _distribute_gws(start_gw, end_gw, count, blocked=None):
    """Evenly distribute `count` GWs between start/end inclusive, avoiding blocked GWs."""
    blocked = set(blocked or [])
    available = [gw for gw in range(start_gw, end_gw + 1) if gw not in blocked]
    if count <= 0:
        return []
    if len(available) < count:
        raise ValueError(
            f"Not enough available GWs between GW{start_gw} and GW{end_gw} for {count} rounds."
        )
    if count == 1:
        return [available[len(available) // 2]]
    step = (len(available) - 1) / (count - 1)
    selected = []
    used = set()
    for i in range(count):
        idx = round(i * step)
        # Avoid duplicates caused by rounding.
        while idx in used and idx + 1 < len(available):
            idx += 1
        while idx in used and idx - 1 >= 0:
            idx -= 1
        used.add(idx)
        selected.append(available[idx])
    return sorted(selected)


def _build_cup_calendar(total_managers, group_count, largest_group_size, knockout_target=16, prefer_single_playoff=False):
    """
    Builds a cup calendar that works backwards from a GW37 final.

    Knockout target is exactly 16 managers:
      - Last 16, QF and SF are two-legged.
      - Final is GW37.
      - A gap GW separates the start of each knockout round.
      - Playoff rounds are inserted before the Last 16 if needed.
    """
    # Fixed endgame: L16/QF/SF home+away, final GW37.
    knockout_rounds = {
        'Last 16': [28, 29],
        'Quarter-final': [31, 32],
        'Semi-final': [34, 35],
        'Final': [37],
    }
    knockout_gws = [gw for values in knockout_rounds.values() for gw in values]

    auto_qualify = max(0, min(largest_group_size, knockout_target // group_count))
    auto_total = auto_qualify * group_count
    playoff_spots = max(0, knockout_target - auto_total)

    # Build the smallest playoff path that still produces exactly the
    # remaining knockout places. A one-round playoff needs 2x entrants; for a
    # single final spot we prefer a four-team PO SF + PO F when available.
    available_non_auto = max(0, total_managers - auto_total)
    playoff_gws = []
    playoff_rounds = []
    playoff_entrants = 0
    if playoff_spots > 0 and available_non_auto > 0:
        if playoff_spots == 1 and available_non_auto >= 4 and not prefer_single_playoff:
            playoff_entrants = 4
            playoff_rounds = ['Playoff semi-final', 'Playoff final']
            playoff_gws = [24, 26]
        else:
            playoff_entrants = min(available_non_auto, playoff_spots * 2)
            # If there are not enough playoff candidates to run a clean
            # one-round playoff, all selected candidates qualify automatically.
            playoff_rounds = ['Playoff final'] if playoff_entrants > playoff_spots else []
            playoff_gws = [26] if playoff_rounds else []

    first_post_group_gw = min(playoff_gws or knockout_gws)
    group_rounds = _round_robin_round_count(largest_group_size)
    # Keep group stage clear of GW1 and leave space before playoffs/knockouts.
    group_gws = _distribute_gws(5, first_post_group_gw - 3, group_rounds)

    return {
        'auto_qualify': auto_qualify,
        'playoff_spots': playoff_spots,
        'playoff_entrants': playoff_entrants,
        'playoff_rounds': playoff_rounds,
        'playoff_gws': playoff_gws,
        'group_stage_gws': group_gws,
        'knockout_rounds': knockout_rounds,
        'knockout_gws': knockout_gws,
        'final_gw': 37,
        'knockout_target': knockout_target,
    }


def _build_lms_schedule(total_managers, cup_gws, final_gw=38):
    """
    Build an LMS schedule around cup weeks so the final has exactly 2 managers.
    Normal scheduled GWs eliminate one manager; double-elim GWs eliminate two.
    """
    skipped = set(cup_gws) | {1}
    regular_gws = [gw for gw in range(2, final_gw) if gw not in skipped]
    eliminations_needed = max(0, total_managers - 2)

    if eliminations_needed == 0:
        return {
            'schedule': [final_gw],
            'double_elim_gws': [],
            'final_gw': final_gw,
            'skipped_gws': sorted(skipped),
        }

    lms_schedule = []
    double_elim_gws = []

    if len(regular_gws) >= eliminations_needed:
        step = len(regular_gws) / eliminations_needed
        picked = []
        for i in range(eliminations_needed):
            idx = min(int(i * step), len(regular_gws) - 1)
            picked.append(regular_gws[idx])
        # Dedupe while preserving order; fill gaps if rounding duplicated.
        seen = set()
        lms_schedule = []
        for gw in picked:
            if gw not in seen:
                seen.add(gw)
                lms_schedule.append(gw)
        for gw in regular_gws:
            if len(lms_schedule) >= eliminations_needed:
                break
            if gw not in seen:
                seen.add(gw)
                lms_schedule.append(gw)
        lms_schedule = sorted(lms_schedule)
    else:
        lms_schedule = list(regular_gws)
        doubles_needed = eliminations_needed - len(regular_gws)
        if doubles_needed > 0:
            # Put unavoidable double eliminations through the middle of LMS,
            # not at the end, so the closing weeks feel like a proper run-in.
            middle = regular_gws[len(regular_gws)//4: max(len(regular_gws)//4 + 1, (len(regular_gws)*3)//4)] or regular_gws
            if doubles_needed >= len(middle):
                double_elim_gws = middle[:doubles_needed]
            else:
                step = (len(middle) - 1) / max(doubles_needed - 1, 1)
                double_elim_gws = sorted({middle[round(i * step)] for i in range(doubles_needed)})
                for gw in middle:
                    if len(double_elim_gws) >= doubles_needed:
                        break
                    if gw not in double_elim_gws:
                        double_elim_gws.append(gw)
                double_elim_gws = sorted(double_elim_gws)

    lms_schedule.append(final_gw)
    lms_schedule = sorted(set(lms_schedule))

    return {
        'schedule': lms_schedule,
        'double_elim_gws': sorted(double_elim_gws),
        'final_gw': final_gw,
        'skipped_gws': sorted(skipped),
    }


def calculate_competition_structure(total_managers):
    """
    Given total manager count, returns the full competition structure:
    - Division sizes (balanced, skill-weighted)
    - Promo/relegation places
    - Cup groups, full round-robin group calendar, playoff calendar and KO calendar
    - LMS schedule that avoids cup GWs and finishes with two managers in the final
    """

    # ── Divisions ────────────────────────────────────────────────────────────
    num_divs = 4
    base_size = total_managers // num_divs
    remainder = total_managers % num_divs
    div_sizes = {}
    extras = remainder
    for i, div in enumerate(DIVISION_ORDER):
        size = base_size
        if extras > 0 and i in [1, 2]:
            size += 1
            extras -= 1
        elif extras > 0:
            size += 1
            extras -= 1
        div_sizes[div] = size

    smallest_div = min(div_sizes.values())
    if smallest_div <= 5:
        promo_rel = 1
    elif smallest_div <= 8:
        promo_rel = 2
    else:
        promo_rel = 3

    # ── Cup groups/calendar ──────────────────────────────────────────────────
    group_count = _choose_cup_group_count(total_managers)
    base_group_size = total_managers // group_count
    largest_group_size = math.ceil(total_managers / group_count)

    cup_calendar = _build_cup_calendar(
        total_managers=total_managers,
        group_count=group_count,
        largest_group_size=largest_group_size,
        knockout_target=16,
    )

    # If the two-round playoff path creates exactly one LMS double-elimination,
    # simplify the Cup playoff instead: top two non-auto qualifiers go straight
    # to a PO Final. This avoids creating a single random-feeling LMS double.
    _trial_cup_gws = set(cup_calendar['group_stage_gws']) | set(cup_calendar['playoff_gws']) | set(cup_calendar['knockout_gws'])
    _trial_lms = _build_lms_schedule(total_managers, _trial_cup_gws, final_gw=38)
    if (
        len(_trial_lms.get('double_elim_gws', [])) == 1
        and cup_calendar.get('playoff_spots') == 1
        and cup_calendar.get('playoff_entrants', 0) >= 4
    ):
        cup_calendar = _build_cup_calendar(
            total_managers=total_managers,
            group_count=group_count,
            largest_group_size=largest_group_size,
            knockout_target=16,
            prefer_single_playoff=True,
        )

    cup = {
        'group_count': group_count,
        'group_size': largest_group_size,
        'min_group_size': base_group_size,
        'auto_qualify': cup_calendar['auto_qualify'],
        'playoff_spots': cup_calendar['playoff_spots'],
        'playoff_entrants': cup_calendar['playoff_entrants'],
        'playoff_rounds': cup_calendar['playoff_rounds'],
        'playoff_gws': cup_calendar['playoff_gws'],
        'matches_per_team': largest_group_size - 1,
        'group_rounds': _round_robin_round_count(largest_group_size),
        'group_stage_gws': cup_calendar['group_stage_gws'],
        'knockout_rounds': cup_calendar['knockout_rounds'],
        'knockout_gws': cup_calendar['knockout_gws'],
        'final_gw': cup_calendar['final_gw'],
        'knockout_target': cup_calendar['knockout_target'],
    }

    # ── LMS schedule ─────────────────────────────────────────────────────────
    cup_gws = set(cup['group_stage_gws']) | set(cup['playoff_gws']) | set(cup['knockout_gws'])
    lms = _build_lms_schedule(total_managers, cup_gws, final_gw=38)

    return {
        'total_managers': total_managers,
        'divisions': {
            'sizes': div_sizes,
            'promo_rel_places': promo_rel,
        },
        'cup': cup,
        'lms': lms,
    }

def print_structure_summary(structure):
    print(f"\n{'━'*60}")
    print(f"  COMPETITION STRUCTURE — {structure['total_managers']} managers")
    print(f"{'━'*60}")
    print(f"\n  Divisions:")
    for div, size in structure['divisions']['sizes'].items():
        print(f"    {div:<18} {size} managers")
    pr = structure['divisions']['promo_rel_places']
    print(f"    Promo/rel places: {pr} per boundary")

    cup = structure['cup']
    print(f"\n  Cup:")
    print(f"    {cup['group_count']} groups of {cup['group_size']}")
    print(f"    {cup['group_rounds']} group matchdays → GWs {cup['group_stage_gws']}")
    print(f"    Auto-qualify: {cup['auto_qualify']} per group → {cup['auto_qualify'] * cup['group_count']} managers")
    if cup.get('playoff_spots', 0):
        print(f"    Playoff: {cup['playoff_entrants']} managers for {cup['playoff_spots']} spot(s) → GWs {cup['playoff_gws']}")
    print(f"    Knockout GWs: {cup['knockout_gws']} (Final GW{cup.get('final_gw', 37)})")

    lms = structure['lms']
    print(f"\n  LMS:")
    print(f"    Schedule ({len(lms['schedule'])} GWs): {lms['schedule']}")
    if lms['double_elim_gws']:
        print(f"    Double eliminations: GWs {lms['double_elim_gws']}")
    print(f"    Skipped (cup) GWs: {lms['skipped_gws']}")
    print(f"{'━'*60}\n")


# ─────────────────────────────────────────────────────────────────────────────
# Snake-draft cup group seeder
# ─────────────────────────────────────────────────────────────────────────────

def _cup_group_label(index):
    """Return spreadsheet-style group labels: Group A, ..., Group Z, Group AA."""
    letters = []
    n = index + 1
    while n:
        n, rem = divmod(n - 1, 26)
        letters.append(chr(65 + rem))
    return "Group " + "".join(reversed(letters))


def seed_cup_groups_snake(manager_ids_ranked, num_groups):
    """
    Snake-draft seeding: ranked managers are distributed across groups so
    that each group has a balanced spread of ability.

    Rank 1 → Group A, Rank 2 → Group B, ..., then snakes back.

    Returns dict: group_name → [manager_ids]
    """
    groups = {_cup_group_label(i): [] for i in range(num_groups)}
    group_names = list(groups.keys())
    direction = 1
    idx = 0

    for manager_id in manager_ids_ranked:
        groups[group_names[idx]].append(manager_id)
        idx += direction
        if idx >= num_groups:
            idx = num_groups - 1
            direction = -1
        elif idx < 0:
            idx = 0
            direction = 1

    return groups


def assign_divisions_balanced(manager_ids_ranked, div_sizes):
    """
    Assigns managers to divisions using skill-balanced distribution.
    Rather than top-N in PL, uses snake-style within each division tier
    so that a 20-manager league doesn't put 5 elite managers all in PL.

    Strategy: divide ranked list into division-sized chunks, then within
    each chunk apply snake ordering so the division's internal table is
    balanced rather than top-loaded.

    Returns dict: manager_id → division_name
    """
    assignments = {}
    pos = 0
    for div in DIVISION_ORDER:
        size = div_sizes.get(div, 0)
        chunk = manager_ids_ranked[pos:pos + size]
        pos += size
        for m_id in chunk:
            assignments[m_id] = div
    return assignments


# ─────────────────────────────────────────────────────────────────────────────
# Round-robin fixture generator
# ─────────────────────────────────────────────────────────────────────────────

def generate_round_robin_fixtures(group_members, group_gws, group_name):
    """
    Generates one fixture per team per matchday using a round-robin algorithm.
    Returns list of fixture dicts for insertion into cup['fixtures'].
    """
    n = len(group_members)
    teams = list(group_members)
    if n % 2 == 1:
        teams.append(None)   # bye
    half = len(teams) // 2
    fixtures = []

    # Only generate the number of rounds this group actually needs.
    # This matters for mixed group sizes: a 4-team group needs 3 rounds even
    # if the overall cup calendar has 5 group-stage GWs for 5-team groups.
    needed_rounds = _round_robin_round_count(n)
    for round_idx, gw in enumerate(group_gws[:needed_rounds]):
        round_fixtures = []
        for i in range(half):
            home = teams[i]
            away = teams[len(teams) - 1 - i]
            if home is not None and away is not None:
                round_fixtures.append({
                    "gw": gw,
                    "group": group_name,
                    "home": home,
                    "away": away,
                    "round": f"Group Stage GW{gw}"
                })
        fixtures.extend(round_fixtures)
        # Rotate teams (keep teams[0] fixed)
        teams = [teams[0]] + [teams[-1]] + teams[1:-1]

    return fixtures


# ─────────────────────────────────────────────────────────────────────────────
# Promo/rel
# ─────────────────────────────────────────────────────────────────────────────

def apply_promo_rel(prev_records, promo_places):
    by_div = {d: [] for d in DIVISION_ORDER}
    for m_id, rec in prev_records.items():
        div = rec.get('prev_division', 'League Two')
        if div not in DIVISION_ORDER:
            div = 'League Two'
        by_div[div].append((m_id, rec.get('prev_total_points', 0)))

    for d in by_div:
        by_div[d].sort(key=lambda x: x[1], reverse=True)

    assignments = {}
    n = len(DIVISION_ORDER)
    for i, div in enumerate(DIVISION_ORDER):
        ranked = by_div[div]
        for pos, (m_id, _) in enumerate(ranked):
            target = div
            if i > 0 and pos < promo_places:
                target = DIVISION_ORDER[i - 1]
            elif i < n - 1 and pos >= len(ranked) - promo_places:
                target = DIVISION_ORDER[i + 1]
            assignments[m_id] = target
    return assignments


def movement_label(prev_div, curr_div):
    if not prev_div or prev_div == curr_div:
        return "stayed"
    if prev_div not in DIVISION_ORDER:
        return "new"
    return "promoted" if DIVISION_ORDER.index(curr_div) < DIVISION_ORDER.index(prev_div) else "relegated"


# ─────────────────────────────────────────────────────────────────────────────
# Master JSON builders
# ─────────────────────────────────────────────────────────────────────────────

def blank_manager(name, entry_name, division, prev_data, is_new=False):
    return {
        "name": name,
        "entry_name": entry_name,
        "division": division,
        "is_new_manager": is_new,
        "prev_season_reference": {
            "season":       prev_data.get("prev_season", PREV_SEASON_LABEL),
            "division":     prev_data.get("prev_division", "N/A"),
            "total_points": prev_data.get("prev_total_points", 0),
            "final_rank":   prev_data.get("prev_final_rank", 0),
        },
        "stats": {"total_points": 0, "lms_alive": True},
        "current_overall_rank": 9_999_999,
        "season_totals": {
            "defensive_points_gained": 0, "defensive_points_lost": 0,
            "net_defensive_score": 0, "goals_scored": 0, "assists": 0,
            "bonus_points": 0, "yellow_cards": 0, "red_cards": 0,
            "total_captain_pts": 0, "total_vice_pts": 0,
            "highest_gw_score": 0, "best_captain_score": 0,
            "best_autosub_score": 0, "bench_points_total": 0,
            "net_transfer_cost": 0,
            "net_transfer_points_gained": 0,
            "differential_points": 0,
        },
        "block_stats": {"current_block_points": 0, "block_wins": []},
        "cup_stats": {
            "group": None, "match_points": 0,
            "cup_fpl_points_sum": 0, "cup_goals_sum": 0,
            "cup_defensive_sum": 0, "cup_captain_sum": 0,
            "cup_vice_sum": 0, "qualified": False, "knockout_stage": None,
            "knockout_fpl_points_sum": 0, "knockout_captain_sum": 0,
            "knockout_goals_sum": 0, "knockout_net_defensive_sum": 0,
            "knockout_vice_sum": 0, "last_overall_rank": 9_999_999,
        },
        "accolades": {
            "talent_scout_best_player": None,
            "talent_scout_points": 0,
        }
    }


def skeleton_master(total_managers, structure):
    lms = structure['lms']
    cup = structure['cup']
    return {
        "league_metadata": {
            "league_id":          CURR_LEAGUE_ID,
            "league_name":        LEAGUE_NAME,
            "season":             CURR_SEASON_LABEL,
            "prev_season":        PREV_SEASON_LABEL,
            "last_processed_gw":  0,
            "total_managers":     total_managers,
        },
        "managers": {},
        "divisions": {d: {"manager_ids": [], "standings": {}} for d in DIVISION_ORDER},
        "competitions": {
            "blocks": {
                f"Block {i+1}": {"gws": gws, "winner_id": None, "winner_name": None}
                for i, gws in enumerate([
                    [1,2,3,4,5],[6,7,8,9,10],[11,12,13,14,15],[16,17,18,19,20],
                    [21,22,23,24,25],[26,27,28,29,30],[31,32,33,34],[35,36,37,38]
                ])
            },
            "lms": {
                "schedule":         lms['schedule'],
                "double_elim_gws":  lms['double_elim_gws'],
                "final_gw":         lms['final_gw'],
                "active_ids":       [],
                "eliminated":       {},
                "winner_id":        None, "winner_name": None,
                "runner_up_id":     None, "runner_up_name": None,
            },
            "cup": {
                "total_managers":     total_managers,
                "num_groups":         cup['group_count'],
                "group_size":         cup['group_size'],
                "auto_qualify_places": cup['auto_qualify'],
                "playoff_spots":      cup['playoff_spots'],
                "group_stage_gws":    cup['group_stage_gws'],
                "playoff_gws":        cup.get('playoff_gws', []),
                "playoff_gw":         cup.get('playoff_gws', [None])[-1] if cup.get('playoff_gws') else None,
                "playoff_entrants":   cup.get('playoff_entrants', 0),
                "playoff_rounds":     cup.get('playoff_rounds', []),
                "knockout_rounds":    cup.get('knockout_rounds', {}),
                "knockout_gws":       cup['knockout_gws'],
                "final_gw":           cup.get('final_gw', 37),
                "groups":             {},
                "group_standings":    {},
                "qualified_ids":      [],
                "playoff_result":     None,
                "fixtures":           {},
                "knockout_bracket":   {},
                "knockout_results":   {},
            }
        },
        "promotion_relegation": {
            "places": structure['divisions']['promo_rel_places'],
            "note":   "Top league ignores promotion, bottom league ignores relegation.",
            "last_season_changes": {}
        },
        "accolades": {
            "prizes": {
                "Golden Boot":    {"manager_id": None, "manager_name": None, "value": 0, "metric": "goals_scored"},
                "Playmaker":      {"manager_id": None, "manager_name": None, "value": 0, "metric": "assists"},
                "Golden Glove":   {"manager_id": None, "manager_name": None, "value": 0, "metric": "net_defensive_score"},
                "Captain King":   {"manager_id": None, "manager_name": None, "value": 0, "metric": "total_captain_pts"},
            },
            "fun": {
                "Bonus Magnet":   {"manager_id": None, "manager_name": None, "value": 0, "metric": "bonus_points"},
                "Card Dealer":    {"manager_id": None, "manager_name": None, "value": 0, "metric": "cards_total"},
                "Talent Scout":   {"manager_id": None, "manager_name": None, "value": 0, "metric": "differential_points"},
                "Transfer Wizard":{"manager_id": None, "manager_name": None, "value": 0, "metric": "net_transfer_points_gained"},
            }
        },
        "rules_reference": {
            "division_tiebreakers": [
                "fpl_points_this_season", "captain_points_this_season",
                "goals_scored_this_season", "net_defensive_score_this_season",
                "vice_captain_points_this_season", "overall_rank"
            ],
            "lms_tiebreakers": [
                "gw_points", "captain_points", "goals_scored",
                "net_defensive_score", "vice_captain_points", "overall_rank"
            ],
            "cup_group_tiebreakers": [
                "group_points", "cup_fpl_points_sum", "cup_captain_sum",
                "cup_goals_sum", "net_defensive_score", "cup_vice_sum", "overall_rank"
            ],
            "cup_knockout_tiebreakers": [
                "knockout_fpl_points_sum", "knockout_captain_points",
                "knockout_goals_scored", "knockout_net_defensive_score",
                "knockout_vice_captain_points", "overall_rank"
            ]
        },
        "gw_history": {}
    }


# ─────────────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────────────

def run_import():
    """Step 1: Pull previous season data, build initial master."""
    print("=" * 60)
    print(f"  IMPORTING {PREV_SEASON_LABEL} DATA")
    print("=" * 60)

    if not PREV_DIVISION_ASSIGNMENTS:
        print(f"\n⚠️  PREV_DIVISION_ASSIGNMENTS is empty — all managers default to League Two.")

    print(f"\n[1/3] Fetching {PREV_SEASON_LABEL} managers from league {PREV_LEAGUE_ID}...")
    prev_raw = fetch_league_managers(PREV_LEAGUE_ID)
    print(f"      {len(prev_raw)} managers found.")

    print(f"\n[2/3] Fetching history...")
    prev_records = {}
    for i, entry in enumerate(prev_raw, 1):
        m_id = str(entry['entry'])
        print(f"  ({i}/{len(prev_raw)}) {entry['player_name']}...")
        history = fetch_history(m_id)
        current = history.get('current', [])
        final_gw = current[-1] if current else {}
        prev_records[m_id] = {
            "name":              entry['player_name'],
            "entry_name":        entry['entry_name'],
            "prev_entry_id":     m_id,
            "prev_season":       PREV_SEASON_LABEL,
            "prev_division":     PREV_DIVISION_ASSIGNMENTS.get(m_id, "League Two"),
            "prev_total_points": entry.get('total', final_gw.get('total_points', 0)),
            "prev_final_rank":   final_gw.get('overall_rank', 0),
            "curr_entry_id":     None,
            "active":            True,
        }
        time.sleep(0.3)

    with open(PREV_ARCHIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(prev_records, f, indent=2, ensure_ascii=False)
    print(f"\n      ✅  Archive saved → {PREV_ARCHIVE_FILE}")

    # Use prev count for initial structure estimate
    structure = calculate_competition_structure(len(prev_records))
    print_structure_summary(structure)

    promo_assignments = apply_promo_rel(prev_records, structure['divisions']['promo_rel_places'])
    master = skeleton_master(len(prev_records), structure)

    for m_id, rec in prev_records.items():
        div = promo_assignments.get(m_id, "League Two")
        master["managers"][m_id] = blank_manager(rec['name'], rec['entry_name'], div, rec)
        master["divisions"][div]["manager_ids"].append(m_id)
        master["promotion_relegation"]["last_season_changes"][m_id] = {
            "prev_division": rec['prev_division'],
            "curr_division": div,
            "movement": movement_label(rec['prev_division'], div)
        }

    master["competitions"]["lms"]["active_ids"] = list(master["managers"].keys())
    _write(master)
    _print_division_summary(master)
    print("✅  Done. Next: run --rematch once new season FPL IDs are available.")


def run_rematch(auto=False):
    """Step 2: Match new-season IDs, remove leavers, seed new joiners."""
    print("=" * 60)
    print(f"  REMATCHING {PREV_SEASON_LABEL} → {CURR_SEASON_LABEL}")
    print("=" * 60)

    prev_records = _load_json(PREV_ARCHIVE_FILE)
    master = _load_json(MASTER_FILE)

    print(f"\nFetching {CURR_SEASON_LABEL} league {CURR_LEAGUE_ID}...")
    curr_raw = fetch_league_managers(CURR_LEAGUE_ID)
    curr_by_name = {e['player_name'].strip().lower(): e for e in curr_raw}
    curr_all_ids = {str(e['entry']) for e in curr_raw}
    matched_curr_ids = set()

    matched, unmatched, new_entries = [], [], []

    # ── Match by name ─────────────────────────────────────────────────────────
    for prev_id, rec in prev_records.items():
        key = rec['name'].strip().lower()
        if key in curr_by_name:
            e = curr_by_name[key]
            curr_id = str(e['entry'])
            matched.append({'prev_id': prev_id, 'curr_id': curr_id,
                            'name': rec['name'], 'auto': True})
            matched_curr_ids.add(curr_id)
            prev_records[prev_id]['curr_entry_id'] = curr_id
        else:
            unmatched.append({'prev_id': prev_id, 'name': rec['name']})

    # ── Manual resolution for unmatched ───────────────────────────────────────
    unresolved_curr = [e for e in curr_raw if str(e['entry']) not in matched_curr_ids]
    manual_matches = []

    if unmatched:
        print(f"\n{'─'*50}")
        print("  UNMATCHED FROM PREVIOUS SEASON")
        print(f"{'─'*50}")
        for rec in unmatched:
            print(f"\n  Previous: {rec['name']} (ID: {rec['prev_id']})")
            if not auto and unresolved_curr:
                for i, e in enumerate(unresolved_curr, 1):
                    print(f"    {i}. {e['player_name']} — {e['entry_name']} (ID: {e['entry']})")
                choice = input("  Match number, 'remove' to remove from league, or 'skip': ").strip()
                if choice.isdigit():
                    idx = int(choice) - 1
                    if 0 <= idx < len(unresolved_curr):
                        chosen = unresolved_curr[idx]
                        curr_id = str(chosen['entry'])
                        manual_matches.append({'prev_id': rec['prev_id'], 'curr_id': curr_id,
                                               'name': rec['name'], 'auto': False})
                        matched_curr_ids.add(curr_id)
                        prev_records[rec['prev_id']]['curr_entry_id'] = curr_id
                        prev_records[rec['prev_id']]['active'] = True
                        unresolved_curr = [e for e in unresolved_curr if str(e['entry']) != curr_id]
                        print(f"  ✅ Matched → ID {curr_id}")
                elif choice.lower() == 'remove':
                    prev_records[rec['prev_id']]['active'] = False
                    print(f"  🗑  {rec['name']} marked as removed.")
                else:
                    prev_records[rec['prev_id']]['active'] = False
                    print(f"  Skipped — {rec['name']} will be removed.")
            else:
                # Auto mode: unmatched = removed
                prev_records[rec['prev_id']]['active'] = False
                print(f"  [auto] {rec['name']} not found — removed.")

    # ── New managers (in curr league, not matched to anyone) ──────────────────
    new_entries = [e for e in curr_raw if str(e['entry']) not in matched_curr_ids]

    new_with_rank = []
    if new_entries:
        print(f"\nFetching FPL ranks for {len(new_entries)} new managers...")
        for e in new_entries:
            info = fetch_entry_info(str(e['entry']))
            rank = info.get('summary_overall_rank', 9_999_999)
            new_with_rank.append({'entry': e, 'rank': rank})
            time.sleep(0.3)
        new_with_rank.sort(key=lambda x: x['rank'])

    # ── Build active manager list ─────────────────────────────────────────────
    # Active prev managers (matched)
    active_prev = {
        rec.get('curr_entry_id') or rec['prev_entry_id']: rec
        for rec in prev_records.values()
        if rec.get('active', True) and rec.get('curr_entry_id')
    }

    total_managers = len(active_prev) + len(new_with_rank)
    print(f"\n  Active returning: {len(active_prev)}")
    print(f"  New joiners:      {len(new_with_rank)}")
    print(f"  Total:            {total_managers}")

    # Recalculate structure with actual count
    structure = calculate_competition_structure(total_managers)
    print_structure_summary(structure)

    # Rebuild promo assignments from active returning managers only
    active_prev_records = {
        curr_id: prev_records[next(
            k for k, v in prev_records.items() if v.get('curr_entry_id') == curr_id
        )]
        for curr_id in active_prev
    }
    promo_assignments = apply_promo_rel(active_prev_records, structure['divisions']['promo_rel_places'])

    # ── Assign new managers to appropriate divisions ───────────────────────────
    # Calculate average prev-season rank per division
    div_avg_ranks = {}
    for div in DIVISION_ORDER:
        ranks = [
            rec['prev_final_rank'] for rec in active_prev_records.values()
            if rec.get('prev_division') == div and rec.get('prev_final_rank', 0) > 0
        ]
        div_avg_ranks[div] = sum(ranks) / len(ranks) if ranks else 9_999_999

    # Find division capacity remaining after returning managers
    div_counts = {div: 0 for div in DIVISION_ORDER}
    for div in promo_assignments.values():
        div_counts[div] = div_counts.get(div, 0) + 1

    div_capacities = structure['divisions']['sizes']

    for nw in new_with_rank:
        new_rank = nw['rank']
        # Find best-fit division: closest average rank with space
        best_div = None
        best_diff = float('inf')
        for div in DIVISION_ORDER:
            if div_counts.get(div, 0) < div_capacities.get(div, 999):
                diff = abs(div_avg_ranks.get(div, 9_999_999) - new_rank)
                if diff < best_diff:
                    best_diff = diff
                    best_div = div
        if not best_div:
            best_div = "League Two"

        curr_id = str(nw['entry']['entry'])
        promo_assignments[curr_id] = best_div
        div_counts[best_div] = div_counts.get(best_div, 0) + 1

        active_prev_records[curr_id] = {
            "name": nw['entry']['player_name'],
            "entry_name": nw['entry']['entry_name'],
            "prev_entry_id": None,
            "prev_season": PREV_SEASON_LABEL,
            "prev_division": "N/A — new manager",
            "prev_total_points": 0,
            "prev_final_rank": nw['rank'],
            "curr_entry_id": curr_id,
        }
        print(f"  → {nw['entry']['player_name']} (rank {nw['rank']:,}) → {best_div}")

    # ── Build new master ──────────────────────────────────────────────────────
    master = skeleton_master(total_managers, structure)
    promo_log = {}

    # Get all curr-season entries by ID for name lookup
    curr_entries_by_id = {str(e['entry']): e for e in curr_raw}
    for nw in new_with_rank:
        curr_entries_by_id[str(nw['entry']['entry'])] = nw['entry']

    for curr_id, rec in active_prev_records.items():
        div = promo_assignments.get(curr_id, "League Two")
        curr_entry = curr_entries_by_id.get(curr_id, {})
        name = curr_entry.get('player_name', rec['name'])
        entry_name = curr_entry.get('entry_name', rec.get('entry_name', ''))
        is_new = rec.get('prev_division') in (None, "N/A — new manager")

        master["managers"][curr_id] = blank_manager(name, entry_name, div, rec, is_new)
        master["divisions"][div]["manager_ids"].append(curr_id)
        promo_log[curr_id] = {
            "prev_division": rec.get("prev_division", "N/A"),
            "curr_division": div,
            "movement": movement_label(rec.get("prev_division"), div)
        }

    master["promotion_relegation"]["last_season_changes"] = promo_log
    master["competitions"]["lms"]["active_ids"] = list(master["managers"].keys())

    # Save archive
    with open(PREV_ARCHIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(prev_records, f, indent=2, ensure_ascii=False)

    _write(master)
    _print_division_summary(master)

    removed = [rec['name'] for rec in prev_records.values() if not rec.get('active', True)]
    if removed:
        print(f"\n  Removed from league: {', '.join(removed)}")
    print(f"\n✅  Rematch complete. Run --configure once manager count is final.")


def run_configure():
    """Step 3: Finalise competition structure and generate cup fixtures."""
    master = _load_json(MASTER_FILE)
    total = len(master['managers'])

    print(f"\n  Configuring for {total} managers...")
    structure = calculate_competition_structure(total)
    print_structure_summary(structure)

    confirm = input("  Apply this structure? [y/n]: ").strip().lower()
    if confirm != 'y':
        print("  Aborted.")
        return

    # ── Update LMS schedule ───────────────────────────────────────────────────
    lms = master['competitions']['lms']
    lms['schedule']        = structure['lms']['schedule']
    lms['double_elim_gws'] = structure['lms']['double_elim_gws']
    lms['final_gw']        = structure['lms']['final_gw']
    lms['skipped_gws']     = structure['lms'].get('skipped_gws', [])

    # ── Seed cup groups (snake draft by prev season rank) ─────────────────────
    cup = master['competitions']['cup']
    cup['num_groups']          = structure['cup']['group_count']
    cup['group_size']          = structure['cup']['group_size']
    cup['auto_qualify_places'] = structure['cup']['auto_qualify']
    cup['playoff_spots']       = structure['cup']['playoff_spots']
    cup['playoff_entrants']    = structure['cup'].get('playoff_entrants', 0)
    cup['playoff_rounds']      = structure['cup'].get('playoff_rounds', [])
    cup['playoff_gws']         = structure['cup'].get('playoff_gws', [])
    cup['group_stage_gws']     = structure['cup']['group_stage_gws']
    cup['knockout_rounds']     = structure['cup'].get('knockout_rounds', {})
    cup['knockout_gws']        = structure['cup']['knockout_gws']
    cup['final_gw']            = structure['cup'].get('final_gw', 37)

    # Sort managers by prev season rank (lower = better)
    ranked_ids = sorted(
        master['managers'].keys(),
        key=lambda m: master['managers'][m].get(
            'prev_season_reference', {}
        ).get('final_rank', 9_999_999)
    )

    groups = seed_cup_groups_snake(ranked_ids, structure['cup']['group_count'])
    cup['groups'] = groups

    for group_name, members in groups.items():
        for m_id in members:
            if m_id in master['managers']:
                master['managers'][m_id]['cup_stats']['group'] = group_name

    # ── Generate round-robin fixtures ─────────────────────────────────────────
    all_fixtures = {}
    for group_name, members in groups.items():
        fixtures = generate_round_robin_fixtures(
            members, structure['cup']['group_stage_gws'], group_name
        )
        for f in fixtures:
            gw_key = str(f['gw'])
            all_fixtures.setdefault(gw_key, []).append(f)

    cup['fixtures'] = all_fixtures

    # ── Update division structure ─────────────────────────────────────────────
    master['promotion_relegation']['places'] = structure['divisions']['promo_rel_places']
    master['league_metadata']['total_managers'] = total

    _write(master)

    print(f"\n  Cup groups (snake draft):")
    for gname, members in groups.items():
        names = [master['managers'][m]['name'] for m in members if m in master['managers']]
        print(f"    {gname}: {', '.join(names)}")

    print(f"\n✅  Structure configured. Ready for GW1.")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"✗  {path} not found.")
        return {}

def _write(master):
    with open(MASTER_FILE, "w", encoding="utf-8") as f:
        json.dump(master, f, indent=2, ensure_ascii=False)
    print(f"\n  ✅  {MASTER_FILE} written.")

def _print_division_summary(master):
    print(f"\n{'━'*60}  DIVISION ASSIGNMENTS  {'━'*60}")
    log = master["promotion_relegation"].get("last_season_changes", {})
    for div in DIVISION_ORDER:
        ids = master["divisions"][div]["manager_ids"]
        print(f"\n  {div} ({len(ids)} managers)")
        for m_id in ids:
            m = master["managers"].get(m_id, {})
            move = log.get(m_id, {}).get("movement", "")
            tag = {"promoted": "⬆", "relegated": "⬇", "new": "🆕", "stayed": " "}.get(move, " ")
            ref = m.get("prev_season_reference", {})
            print(f"    {tag} {m.get('name','?'):<26} {ref.get('division','N/A'):<18} {ref.get('total_points',0)} pts")


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Torquay FPL — Season Setup")
    parser.add_argument("--import",     dest="do_import",  action="store_true")
    parser.add_argument("--rematch",    action="store_true")
    parser.add_argument("--configure",  action="store_true")
    parser.add_argument("--auto",       action="store_true")
    args = parser.parse_args()

    if args.do_import:
        run_import()
    elif args.rematch:
        run_rematch(auto=args.auto)
    elif args.configure:
        run_configure()
    else:
        parser.print_help()
