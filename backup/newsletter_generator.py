"""
newsletter_generator.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Builds the JSON payload that feeds the GW newsletter poster.

Takes:
  - gw_results   (from GetData.gather_all_manager_data)
  - master_data  (league_master.json)
  - gameweek     (int)

Returns a clean dict that the React poster (gw_poster.jsx) renders.

Usage (from main.py or standalone):
    from newsletter_generator import build_newsletter_payload
    payload = build_newsletter_payload(gameweek, gw_results, master_data)
    # payload is saved as gw_{N}_newsletter.json for the poster to consume
"""

import json
import statistics
from collections import Counter
from collections import defaultdict


# ─────────────────────────────────────────────────────────────────────────────
# Captaincy display logic
# ─────────────────────────────────────────────────────────────────────────────

def _format_manager_names(managers_list):
    """
    Formats a list of manager dicts into a readable name string.
      1 manager  → "Alice"
      2 managers → "Alice & Bob"
      3+         → "3 managers"
    """
    names = [m.get('name', '?') for m in managers_list]
    if len(names) == 1:
        return names[0]
    elif len(names) == 2:
        return f"{names[0]} & {names[1]}"
    else:
        return f"{len(names)} managers"


def _build_captaincy_block(most_captained_name, most_captained_count,
                            best_managers, best_pts,
                            worst_managers, worst_pts):
    """
    Builds the captaincy payload dict applying all display rules.

    Golden Armband rules:
      - If the top-scoring captain IS the most popular captain:
          → show player + pts only, no manager names
      - If the top-scoring captain is NOT the most popular:
          → If all golden-armband managers captained the SAME player:
              · 1–2 managers: name them + player + pts
              · 3+: "X managers" + player + pts
          → If golden-armband managers captained DIFFERENT players
            (e.g. two players tied on highest pts):
              · List each player+pts group individually

    Dud Captaincy follows identical rules.
    """

    def _armband_entry(managers_list, pts, most_captained_name):
        """
        Returns a structured entry for golden armband or dud captaincy.
        Fields:
          - display_type: 'popular_match' | 'single_player' | 'multi_player'
          - player_groups: list of {player, pts, managers_str}
          - suppress_managers: bool (True when player IS the most popular)
        """
        # Group managers by which player they captained
        by_player = {}
        for m in managers_list:
            player = m.get('captain_name', '?')
            by_player.setdefault(player, []).append(m)

        players = list(by_player.keys())

        if len(players) == 1:
            # Everyone who got this score captained the same player
            player = players[0]
            is_popular_match = (player == most_captained_name)
            managers_str = _format_manager_names(managers_list) if not is_popular_match else None
            return {
                'display_type': 'popular_match' if is_popular_match else 'single_player',
                'suppress_managers': is_popular_match,
                'player_groups': [{
                    'player': player,
                    'pts': pts,
                    'managers_str': managers_str,
                }]
            }
        else:
            # Multiple players tied on the same pts — list each group
            groups = []
            for player, mgr_list in by_player.items():
                is_pop = (player == most_captained_name)
                groups.append({
                    'player': player,
                    'pts': pts,
                    'managers_str': _format_manager_names(mgr_list) if not is_pop else None,
                    'suppress_managers': is_pop,
                })
            return {
                'display_type': 'multi_player',
                'suppress_managers': False,
                'player_groups': groups,
            }

    golden = _armband_entry(best_managers,  best_pts,  most_captained_name)
    dud    = _armband_entry(worst_managers, worst_pts, most_captained_name)

    return {
        'most_captained':       most_captained_name,
        'most_captained_count': most_captained_count,
        'golden_armband':       golden,
        'dud_captaincy':        dud,
    }


def _render_captaincy_lines(entry):
    """
    Returns display-ready HTML lines for a captaincy entry.

    Format is intentionally aligned with Most Captained:
      Player (points)
      manager count / manager names
    """
    def _line(player, pts, managers_str=None):
        manager_html = (
            f"<br><span class='cap-value-muted'>{managers_str}</span>"
            if managers_str else ""
        )
        return f"<b>{player} ({pts} pts)</b>{manager_html}"

    if entry['display_type'] == 'popular_match':
        g = entry['player_groups'][0]
        return [_line(g['player'], g['pts'])]

    if entry['display_type'] == 'single_player':
        g = entry['player_groups'][0]
        return [_line(g['player'], g['pts'], g.get('managers_str'))]

    lines = []
    for g in entry['player_groups']:
        lines.append(_line(
            g['player'],
            g['pts'],
            None if g.get('suppress_managers') else g.get('managers_str')
        ))
    return lines

# ─────────────────────────────────────────────────────────────────────────────
# Main payload builder
# ─────────────────────────────────────────────────────────────────────────────

def build_newsletter_payload(gameweek, gw_results, master_data):
    """
    Assembles all sections of the GW newsletter into a single dict.
    """
    managers = list(gw_results.values())
    manager_ids = list(gw_results.keys())
    lms = master_data['competitions']['lms']
    blocks = master_data['competitions']['blocks']
    divisions = master_data['divisions']
    m_data = master_data['managers']

    # ── League player ownership / strategy ──────────────────────────────────────
    manager_count = len(managers)

    starting_owner_counts = Counter()
    squad_owner_counts = Counter()
    player_points = {}
    player_names = {}
    player_managers = defaultdict(list)

    for m in managers:
        manager_name = m.get("name", "")

        seen_starting = set()
        for p in m.get("starting_xi_players", []):
            pid = p.get("id")
            if not pid:
                continue

            seen_starting.add(pid)
            player_points[pid] = p.get("points", 0)
            player_names[pid] = p.get("name", "")
            player_managers[pid].append(manager_name)

        for pid in seen_starting:
            starting_owner_counts[pid] += 1

        seen_squad = set()
        for p in m.get("squad_players", []):
            pid = p.get("id")
            if not pid:
                continue

            seen_squad.add(pid)
            player_names[pid] = p.get("name", "")
            player_points[pid] = p.get("points", 0)

        for pid in seen_squad:
            squad_owner_counts[pid] += 1


    strategic_candidates = []

    for pid, owners in starting_owner_counts.items():
        points = player_points.get(pid, 0)

        # Avoid a 2-point one-manager pick winning just because ownership is low.
        if points <= 0:
            continue

        ownership_pct = round((owners / manager_count) * 100)

        strategic_candidates.append({
            "player": player_names.get(pid, ""),
            "points": points,
            "owners": owners,
            "ownership_pct": ownership_pct,
            "managers": player_managers.get(pid, []),
        })

    strategic_candidates = sorted(
        strategic_candidates,
        key=lambda x: (
            x["points"],
            -x["owners"]
        ),
        reverse=True
    )

    # Best high-scoring low-owned player.
    # Optional ownership cap keeps this as a true differential.
    strategic_pick = next(
        (p for p in strategic_candidates if p["owners"] <= 5), None
    )

    # Highest-scoring player who was started but not captained by anyone in the league.
    non_captained_candidates = []
    for pid, owners in starting_owner_counts.items():
        player = player_names.get(pid, '')
        if not player:
            continue
        captained_by = sum(1 for m in managers if m.get('captain_name') == player)
        if captained_by > 0:
            continue
        points = player_points.get(pid, 0)
        if points <= 0:
            continue
        non_captained_candidates.append({
            "player": player,
            "points": points,
            "owners": owners,
            "ownership_pct": round((owners / manager_count) * 100),
            "managers": player_managers.get(pid, []),
        })

    best_non_captained = max(
        non_captained_candidates,
        key=lambda x: (x.get("points", 0), x.get("owners", 0)),
        default=None
    )

    league_template = []

    for pid, owners in squad_owner_counts.most_common(8):
        league_template.append({
            "player": player_names.get(pid, ""),
            "owners": owners,
            "ownership_pct": round((owners / manager_count) * 100),
            "points": player_points.get(pid, 0),
        })

    # ── Division weekly snapshot ────────────────────────────────────────────────
    division_weekly = []

    for div_name, div_data in divisions.items():
        div_manager_ids = [
            str(mid)
            for mid in div_data.get('manager_ids', [])
            if str(mid) in gw_results
        ]

        div_scores = [
            gw_results[mid]
            for mid in div_manager_ids
        ]

        if not div_scores:
            continue

        best = max(
            div_scores,
            key=lambda x: x.get('net_gw_points', 0)
        )

        avg = round(
            statistics.mean(m.get('net_gw_points', 0) for m in div_scores)
        )

        best_score = best.get('net_gw_points', 0)

        division_weekly.append({
            "division": div_name,
            "best_manager": best.get('name', ''),
            "best_score": best_score,
            "average": avg,
            "above_average": best_score - avg,
        })

    # ── Scores ────────────────────────────────────────────────────────────────
    sorted_by_score = sorted(managers, key=lambda x: x.get('net_gw_points', 0), reverse=True)
    league_avg = round(statistics.mean(m.get('net_gw_points', 0) for m in managers))

    # ── Captaincy ─────────────────────────────────────────────────────────────
    cap_counts = Counter(m.get('captain_name', '') for m in managers)
    most_captained_name, most_captained_count = cap_counts.most_common(1)[0]

    def _normal_captain_score(m):
        # Golden Armband/Dud should be judged as normal x2 captaincy.
        # This prevents Triple Captain from turning a good x2 captain into an artificial x3 winner.
        raw = m.get('captain_raw_points')
        if raw is not None:
            return raw * 2
        return m.get('captain_points', 0)

    best_cap_pts  = max(_normal_captain_score(m) for m in managers)
    worst_cap_pts = min(_normal_captain_score(m) for m in managers)

    best_cap_managers  = [m for m in managers if _normal_captain_score(m) == best_cap_pts]
    worst_cap_managers = [m for m in managers if _normal_captain_score(m) == worst_cap_pts]

    captaincy = _build_captaincy_block(
        most_captained_name, most_captained_count,
        best_cap_managers,  best_cap_pts,
        worst_cap_managers, worst_cap_pts,
    )

    # ── Transfers ──────────────────────────────────────────────────────────────
    transfer_managers = [m for m in managers if m.get('net_transfer_cost', 0) > 0 or m.get('net_transfer_points', 0) != 0]
    best_transfer  = max(transfer_managers, key=lambda x: x.get('net_transfer_points', 0), default=None)
    worst_transfer = min(transfer_managers, key=lambda x: x.get('net_transfer_points', 0), default=None)
    transfer_reports_all = []

    for m in transfer_managers:
        report = m.get("transfer_report", {})

        if not report:
            continue

        transfer_reports_all.append({
            "manager": m.get("name", ""),
            "net_gain": report.get("net_gain", 0),
            "gross_gain": report.get("gross_gain", 0),
            "cost": report.get("cost", 0),
            "points_in": report.get("points_in", 0),
            "points_out": report.get("points_out", 0),
            "transfer_count": report.get("transfer_count", 0),
            "ins": report.get("ins", []),
            "outs": report.get("outs", []),
        })

    best_transfer_report = max(
        transfer_reports_all,
        key=lambda x: x.get("net_gain", 0),
        default=None
    )

    worst_transfer_report = min(
        transfer_reports_all,
        key=lambda x: x.get("net_gain", 0),
        default=None
    )

    transfer_reports = {
        "best": best_transfer_report,
        "worst": worst_transfer_report,
    }

    def _top_transfer_players(direction):
        """Most transferred players from this league this GW.

        direction is either 'ins' or 'outs'. Counts unique manager transfer
        actions and carries the GW player points for display context.
        """
        grouped = {}
        for report in transfer_reports_all:
            manager = report.get("manager", "")
            for player in report.get(direction, []) or []:
                pid = str(player.get("id") or player.get("name") or "")
                if not pid:
                    continue
                grouped.setdefault(pid, {
                    "id": pid,
                    "name": player.get("name", ""),
                    "points": player.get("points", 0),
                    "count": 0,
                    "managers": [],
                })
                grouped[pid]["count"] += 1
                if manager:
                    grouped[pid]["managers"].append(manager)

        return sorted(
            grouped.values(),
            key=lambda x: (x.get("count", 0), x.get("points", 0), x.get("name", "")),
            reverse=True
        )[:3]

    team_value_entries = sorted(
        [
            {
                "manager": m.get("name", ""),
                "team": m.get("display_name", ""),
                "value": m.get("team_value"),
            }
            for m in managers
            if m.get("team_value") is not None
        ],
        key=lambda x: x.get("value", 0),
        reverse=True
    )

    show_team_values = (
        gameweek > 1
        and team_value_entries
        and any(abs(float(t.get("value", 0)) - 100.0) > 0.001 for t in team_value_entries)
    )

    transfer_market = {
        "most_transferred_in": _top_transfer_players("ins"),
        "most_transferred_out": _top_transfer_players("outs"),
        "most_valuable_teams": team_value_entries[:3] if show_team_values else [],
        "lowest_value_teams": sorted(team_value_entries, key=lambda x: x.get("value", 0))[:3] if show_team_values else [],
    }

    # ── Bench ─────────────────────────────────────────────────────────────────
    best_subbed = max(
        managers,
        key=lambda x: x.get('best_sub_score', 0),
        default={}
    )
    most_bench = max(managers, key=lambda x: x.get('bench_points', 0))

    # ── LMS ───────────────────────────────────────────────────────────────────
    lms_event = None
    def _lms_week_sort_key(mid):
        s = gw_results.get(str(mid), {})
        return (
            s.get('net_gw_points', 0),
            s.get('captain_points', 0),
            s.get('goals_scored', 0),
            s.get('net_defensive_week', 0),
            s.get('vice_captain_raw_points', 0),
            -s.get('overall_rank', 9_999_999)
        )

    if str(gameweek) in lms.get('eliminated', {}):
        eliminated_name = lms['eliminated'][str(gameweek)]

        active_ids = [
            str(mid)
            for mid in lms.get('active_ids', [])
            if str(mid) in gw_results
        ]

        escaped = None
        eliminated_points = None
        survival_margin = None

        # Find eliminated manager's GW score by name
        eliminated_stats = next(
            (
                s for s in gw_results.values()
                if s.get("name") == eliminated_name
            ),
            None
        )

        if eliminated_stats:
            eliminated_points = eliminated_stats.get("net_gw_points", 0)

        if active_ids:
            escaped_id = sorted(active_ids, key=_lms_week_sort_key)[0]
            escaped_stats = gw_results.get(escaped_id, {})

            escaped_points = escaped_stats.get("net_gw_points", 0)

            escaped = {
                "name": escaped_stats.get("name", ""),
                "points": escaped_points,
            }

            if eliminated_points is not None:
                survival_margin = escaped_points - eliminated_points

        lms_event = {
            'type': 'elimination',
            'eliminated': eliminated_name,
            'eliminated_points': eliminated_points,
            'remaining': len(lms.get('active_ids', [])),
            'escaped': escaped,
            'survival_margin': survival_margin,
        }

    elif lms.get('winner_name') and gameweek == lms.get('final_gw'):
        lms_event = {
            'type': 'final',
            'winner': lms['winner_name'],
            'runner_up': lms.get('runner_up_name', '')
        }

    # ── Cup ─────────────────────────────────────────────────────────────────
    cup_week = None
    cup = master_data['competitions'].get('cup', {})

    if cup:
        fixtures_by_gw = cup.get("fixtures", {}) or {}

        def _manager_label(mid):
            mid = str(mid)
            return (
                gw_results.get(mid, {}).get("name")
                or m_data.get(mid, {}).get("name")
                or mid
            )

        def _fixture_payload(fixture, include_scores=False):
            home_id = str(fixture.get("home", ""))
            away_id = str(fixture.get("away", ""))
            item = {
                "gw": fixture.get("gw", gameweek),
                "group": fixture.get("group", ""),
                "round": fixture.get("round", cup.get("round", "Cup")),
                "home_id": home_id,
                "away_id": away_id,
                "home": _manager_label(home_id),
                "away": _manager_label(away_id),
            }
            if include_scores:
                item["home_score"] = gw_results.get(home_id, {}).get("net_gw_points")
                item["away_score"] = gw_results.get(away_id, {}).get("net_gw_points")
                if item["home_score"] is not None and item["away_score"] is not None:
                    if item["home_score"] > item["away_score"]:
                        item["result"] = f'{item["home"]} win'
                    elif item["away_score"] > item["home_score"]:
                        item["result"] = f'{item["away"]} win'
                    else:
                        item["result"] = "Draw"
            return item

        current_fixtures = fixtures_by_gw.get(str(gameweek), []) or fixtures_by_gw.get(gameweek, []) or []
        future_gws = sorted(
            int(gw) for gw, fixtures in fixtures_by_gw.items()
            if str(gw).isdigit() and int(gw) > int(gameweek) and fixtures
        )
        next_gw = future_gws[0] if future_gws else None
        next_fixtures = fixtures_by_gw.get(str(next_gw), []) if next_gw is not None else []

        cup_week = {
            "status": "active" if current_fixtures else cup.get("status", "inactive"),
            "round": (current_fixtures[0].get("round") if current_fixtures else cup.get("round", "")),
            "fixtures": [_fixture_payload(f, include_scores=True) for f in current_fixtures],
            "next_gw": next_gw,
            "next_round": (next_fixtures[0].get("round") if next_fixtures else ""),
            "next_fixtures": [_fixture_payload(f, include_scores=False) for f in next_fixtures[:6]],
            "message": "",
        }

    # ── Block ─────────────────────────────────────────────────────────────────
    current_block_name, current_block_data = None, None
    for bname, bdata in blocks.items():
        if gameweek in bdata['gws']:
            current_block_name = bname
            current_block_data = bdata
            break

    block_top3 = []
    if current_block_name:
        block_scores = [
            {
                'name': m.get('name', ''),
                'points': m_data.get(mid, {}).get('block_stats', {}).get('current_block_points', 0)
            }
            for mid, m in zip(manager_ids, managers)
        ]
        block_top3 = sorted(block_scores, key=lambda x: x['points'], reverse=True)[:3]

    # ── Division highlights ───────────────────────────────────────────────────
    division_highlights = {}
    for div_name, div_data in divisions.items():
        div_ids = div_data.get('manager_ids', [])
        div_results = [gw_results[mid] for mid in div_ids if mid in gw_results]
        if not div_results:
            continue
        weekly_winner = max(div_results, key=lambda x: x.get('net_gw_points', 0))
        weekly_avg = round(statistics.mean(m.get('net_gw_points', 0) for m in div_results))
        standings = div_data.get('standings', {})
        leader = standings.get('1', {})
        division_highlights[div_name] = {
            'weekly_winner': weekly_winner.get('name', ''),
            'weekly_winner_pts': weekly_winner.get('net_gw_points', 0),
            'weekly_avg': weekly_avg,
            'leader': leader.get('name', ''),
            'leader_pts': leader.get('total_points', 0),
        }

    # ── Chips ─────────────────────────────────────────────────────────────────
    chips_used = sorted(
        [
            {
                'name': m.get('name', ''),
                'chip': m.get('chip_used', ''),
                'score': m.get('chip_score', 0)
            }
            for m in managers
            if m.get('chip_used', 'None') not in ('None', 'none', '')
        ],
        key=lambda x: (x['chip'].lower(), -x['score'])
    )

   # ── Stat leaders — collect ALL tied managers per stat ────────────────────
    def _stat_group(mgrs, key_fn, mode='max'):
        """Returns (best_value, [manager_names]) for a stat, including all ties."""
        best_val = (max if mode == 'max' else min)(key_fn(m) for m in mgrs)
        names = [m.get('name', '?') for m in mgrs if key_fn(m) == best_val]
        return best_val, names

    def _names_str(names):
        """Formats a tied-names list for display: one per line as a list."""
        return names  # return raw list; html_generator renders each on its own line

    goals_val,   goals_names   = _stat_group(managers, lambda m: m.get('goals_scored', 0))
    assists_val, assists_names = _stat_group(managers, lambda m: m.get('assists', 0))
    bonus_val,   bonus_names   = _stat_group(managers, lambda m: m.get('bonus_points', 0))
    riser_val,   riser_names   = _stat_group(managers, lambda m: m.get('rank_change', 0))
    faller_val,  faller_names  = _stat_group(managers, lambda m: m.get('rank_change', 0), mode='min')
    def_val,     def_names     = _stat_group(managers, lambda m: m.get('net_defensive_week', 0))
    cap_val,     cap_names     = _stat_group(managers, _normal_captain_score)
    autosub_val, autosub_names = _stat_group(managers, lambda m: m.get('best_sub_score', 0))
    transfer_val, transfer_names = _stat_group(
        [m for m in managers if m.get('net_transfer_points', 0) > 0] or managers,
        lambda m: m.get('net_transfer_points', 0)
    )

    def _podium_hero(m):
        """Best starting XI player, excluding the manager's captain to avoid duplicated podium info."""
        captain_name = (m.get('captain_name') or '').strip()
        candidates = []

        for player in m.get('starting_xi_players', []):
            name = (player.get('name') or '').strip()
            if not name or name == captain_name:
                continue
            candidates.append({
                "name": name,
                "points": player.get('points', 0),
            })

        if not candidates:
            return ""

        hero = max(candidates, key=lambda p: p.get('points', 0))
        if hero.get('points', 0) <= 0:
            return ""

        return f"{hero['name']} ({hero['points']})"

    # ── Assemble payload ──────────────────────────────────────────────────────
    payload = {
        "gameweek":     gameweek,
        "league_name":  master_data['league_metadata']['league_name'],
        "season":       master_data['league_metadata']['season'],
        "league_avg":   league_avg,
        "division_weekly": division_weekly,

        "podium": [
            {
                "position": i + 1,
                "name": m.get('name', ''),
                "team": m.get('display_name', ''),
                "gw_points": m.get('gw_points', 0),
                "net_gw_points": m.get('net_gw_points', 0),
                "captain": m.get('captain_name', ''),
                "captain_pts": m.get('captain_points', 0),
                "chip": m.get('chip_used', 'None'),
                "hit": m.get('net_transfer_cost', 0),
                "gw_hero": _podium_hero(m),
            }
            for i, m in enumerate(sorted_by_score[:3])
        ],

        "wooden_spoon": {
            "name": sorted_by_score[-1].get('name', ''),
            "net_gw_points": sorted_by_score[-1].get('net_gw_points', 0),
        },

        "all_scores": [
            {
                "name": m.get('name', ''),
                "gw_points": m.get('gw_points', 0),
                "net_gw_points": m.get('net_gw_points', 0),
                "captain": m.get('captain_name', ''),
                "captain_pts": m.get('captain_points', 0),
                "chip": m.get('chip_used', 'None'),
            }
            for m in sorted_by_score
        ],

        # Full structured captaincy block — html_generator calls
        # _render_captaincy_line() from this module to produce display strings
        "captaincy": captaincy,

        "transfers": {
            "best_managers": transfer_names,
            "best_net":      transfer_val,
            "worst_manager": worst_transfer.get('name', '') if worst_transfer else '',
            "worst_net":     worst_transfer.get('net_transfer_points', 0) if worst_transfer else 0,
        },
        "transfer_reports": transfer_reports,
        "transfer_market": transfer_market,
        "strategic_pick": strategic_pick,
        "best_non_captained": best_non_captained,
        "league_template": league_template,
        "bench": {
            "most_bench_manager": most_bench.get('name', ''),
            "most_bench_pts":     most_bench.get('bench_points', 0),

            "best_bench_name":    most_bench.get('best_bench_name', ''),
            "best_bench_pts":     most_bench.get('best_bench_pts', 0),

            "best_sub_manager":   best_subbed.get('name', ''),
            "best_sub_name":      best_subbed.get('best_sub_name', ''),
            "best_sub_pts":       best_subbed.get('best_sub_score', 0),
        },

        # Each value is (stat_value, [list of manager names]) so the HTML
        # generator can render all tied managers on separate lines.
                
        "stat_leaders": {
            "most_goals":   (goals_val,    goals_names),
            "most_assists": (assists_val,  assists_names),
            "most_bonus":   (bonus_val,    bonus_names),
            "riser":        (riser_val,    riser_names) if gameweek > 1 else None,
            "faller":       (abs(faller_val), faller_names) if gameweek > 1 else None,
            "best_def":     (def_val,      def_names),
        },

        "chips": chips_used,
        "lms": lms_event,
        "block": {
            "name": current_block_name,
            "top3": block_top3,
            "is_final_gw": current_block_data and gameweek == current_block_data['gws'][-1] if current_block_data else False,
            "winner": current_block_data.get('winner_name') if current_block_data else None,
        } if current_block_name else None,

        "divisions": division_highlights,
    }

    return payload


def save_newsletter_payload(gameweek, payload, output_dir="."):
    """Saves the payload as a JSON file for the poster to consume."""
    import os
    path = os.path.join(output_dir, f"gw_{gameweek}_newsletter.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"  [Newsletter] Payload saved → {path}")
    return path
