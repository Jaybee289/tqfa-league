"""
competition_engine.py
Handles all side-competition logic for Torquay Free Agents FPL League.

Competitions:
  - Manager of the Block   (8 blocks, highest cumulative net points wins £10)
  - Divisions              (PL / Championship / L1 / L2, promotion & relegation)
  - Last Man Standing      (weekly elimination, GW37 final)
  - Cup                    (group stage → two-legged knockout → single-leg final)

Tiebreaker chains are defined in league_master.json rules_reference and
mirrored here for clarity. Update both places if rules change.
"""

from helpers import (
    sorted_division_standings,
    get_current_block,
    is_block_final_gw,
)


# ===========================================================================
class CompetitionEngine:
# ===========================================================================

    DIVISION_ORDER = ["Premier League", "Championship", "League One", "League Two"]

    # Cup round structure — two-legged until the final
    # Each tuple: (round_label_leg1, round_label_leg2_or_None)
    CUP_ROUND_STRUCTURE = [
        ("Last 16 — 1st Leg",       "Last 16 — 2nd Leg"),
        ("Quarter-Final — 1st Leg", "Quarter-Final — 2nd Leg"),
        ("Semi-Final — 1st Leg",    "Semi-Final — 2nd Leg"),
        ("Final",                    None),   # single leg
    ]

    def __init__(self, master_data):
        self.data     = master_data
        self.managers = master_data['managers']
        self.rules    = master_data['rules_reference']

    # -----------------------------------------------------------------------
    # SHARED — season totals (call every GW before competition processing)
    # -----------------------------------------------------------------------

    def update_season_totals(self, gameweek, gw_results):
        """
        Accumulates season-wide stats for every manager.
        Also stores current_overall_rank for use in division tiebreakers.
        """
        # League-started ownership for the Talent Scout/Differential accolade.
        # Only final XI players under 20% league-started ownership count, using
        # raw player points rather than captain/chip multipliers.
        starting_counts = {}
        total_managers = max(len(gw_results), 1)
        for _stats in gw_results.values():
            seen = set()
            for player in _stats.get('starting_xi_players', []) or []:
                pid = player.get('id') or player.get('name')
                if pid is not None:
                    seen.add(pid)
            for pid in seen:
                starting_counts[pid] = starting_counts.get(pid, 0) + 1

        def _weekly_differential_points(stats):
            total = 0
            for player in stats.get('starting_xi_players', []) or []:
                pid = player.get('id') or player.get('name')
                if pid is None:
                    continue
                pct = (starting_counts.get(pid, 0) / total_managers) * 100
                if pct < 20:
                    total += player.get('points', 0) or 0
            return total

        def _player_name(player):
            return str(player.get('name') or player.get('web_name') or player.get('player_name') or player.get('id') or '')

        def _player_points(player):
            try:
                return float(player.get('points', player.get('total_points', player.get('event_points', 0))) or 0)
            except (TypeError, ValueError):
                return 0

        # Weekly Strategy Room season counters. These mirror the newsletter:
        # - Highest Scorers = top 3 final-XI players by raw points
        # - Best Differentials = top 3 final-XI players under 20% league-started
        # Managers who started these players receive season counters.
        player_entries = {}
        for _mid, _stats in gw_results.items():
            for _player in _stats.get('starting_xi_players', []) or []:
                _pid = _player.get('id') or _player.get('name')
                if _pid is None:
                    continue
                bucket = player_entries.setdefault(_pid, {
                    'pid': _pid,
                    'name': _player_name(_player),
                    'points': _player_points(_player),
                    'manager_ids': set(),
                })
                bucket['manager_ids'].add(_mid)
                bucket['points'] = max(bucket['points'], _player_points(_player))
                if not bucket.get('name'):
                    bucket['name'] = _player_name(_player)

        player_summaries = []
        for _pid, _entry in player_entries.items():
            _starters = len(_entry.get('manager_ids', set()))
            _pct = (_starters / total_managers) * 100
            player_summaries.append({**_entry, 'starters': _starters, 'pct': _pct})

        top_scorer_pick_ids = set()
        top_scorer_pick_details = {}
        for _entry in sorted(player_summaries, key=lambda p: (-p['points'], -p['starters'], str(p.get('name', '')).lower()))[:3]:
            top_scorer_pick_ids.update(_entry.get('manager_ids', set()))
        for _entry in player_summaries:
            for _mid in _entry.get('manager_ids', set()):
                current = top_scorer_pick_details.get(_mid)
                candidate = (_entry.get('points', 0) or 0, str(_entry.get('name', '') or ''))
                if current is None or candidate[0] > current[0]:
                    top_scorer_pick_details[_mid] = candidate

        best_differential_pick_ids = set()
        best_differential_score_by_manager = {}
        best_differential_detail_by_manager = {}
        differential_summaries = [p for p in player_summaries if p.get('pct', 100) < 20]
        for _entry in sorted(differential_summaries, key=lambda p: (-p['points'], -p['starters'], str(p.get('name', '')).lower()))[:3]:
            best_differential_pick_ids.update(_entry.get('manager_ids', set()))
        for _entry in differential_summaries:
            for _mid in _entry.get('manager_ids', set()):
                candidate_points = _entry.get('points', 0) or 0
                if candidate_points > best_differential_score_by_manager.get(_mid, 0):
                    best_differential_score_by_manager[_mid] = candidate_points
                    best_differential_detail_by_manager[_mid] = str(_entry.get('name', '') or '')

        captain_counts = {}
        for _stats in gw_results.values():
            _cap = str(_stats.get('captain_name') or _stats.get('active_captain_name') or _stats.get('captain') or '').strip()
            if _cap:
                captain_counts[_cap] = captain_counts.get(_cap, 0) + 1
        popular_captains = set()
        if captain_counts:
            _popular_count = max(captain_counts.values())
            popular_captains = {_cap for _cap, _count in captain_counts.items() if _count == _popular_count}

        league_avg_score = (
            sum((s.get('net_gw_points', 0) or 0) for s in gw_results.values()) / max(len(gw_results), 1)
        )

        for m_id, stats in gw_results.items():
            if m_id not in self.managers:
                continue
            m = self.managers[m_id]
            t = m.setdefault('season_totals', {
                'defensive_points_gained': 0, 'defensive_points_lost': 0,
                'net_defensive_score': 0, 'goals_scored': 0, 'assists': 0,
                'bonus_points': 0, 'yellow_cards': 0, 'red_cards': 0,
                'total_captain_pts': 0, 'total_vice_pts': 0,
                'highest_gw_score': 0, 'best_captain_score': 0, 'best_captain_detail': '',
                'best_vice_captain_score': 0, 'best_vice_captain_detail': '',
                'best_autosub_score': 0, 'best_auto_sub_score': 0, 'best_auto_sub_detail': '', 'bench_points_total': 0, 'best_left_behind_score': 0, 'best_left_behind_detail': '',
                'net_transfer_cost': 0,
                'net_transfer_points_gained': 0, 'best_transfer_score': 0, 'best_transfer_detail': '', 'worst_transfer_score': 0, 'worst_transfer_detail': '', 'differential_points': 0,
                'top_scorer_pick_count': 0, 'best_differential_pick_count': 0,
                'best_pick_score': 0, 'best_pick_detail': '',
                'best_differential_pick_score': 0, 'best_differential_pick_detail': '',
                'popular_armband_count': 0, 'differential_captain_count': 0, 'best_differential_captain_score': 0, 'best_differential_captain_detail': '', 'total_auto_sub_points': 0, 'lowest_gw_score': 0,
                'current_hot_streak': 0, 'hot_streak_best': 0,
                'current_cold_streak': 0, 'cold_streak_best': 0
            })

            # Newer season totals may be missing keys if the master was created
            # before this version. Backfill them before accumulating this GW.
            t.setdefault('best_captain_detail', '')
            t.setdefault('best_vice_captain_score', 0)
            t.setdefault('best_auto_sub_score', t.get('best_autosub_score', 0))
            t.setdefault('best_auto_sub_detail', t.get('best_autosub_detail', ''))
            t.setdefault('best_left_behind_score', 0)
            t.setdefault('best_left_behind_detail', '')
            t.setdefault('best_autosub_score', t.get('best_auto_sub_score', 0))
            t.setdefault('top_scorer_pick_count', 0)
            t.setdefault('best_differential_pick_count', 0)
            t.setdefault('best_pick_score', 0)
            t.setdefault('best_pick_detail', '')
            t.setdefault('best_differential_pick_score', 0)
            t.setdefault('best_differential_pick_detail', '')
            t.setdefault('popular_armband_count', 0)
            t.setdefault('differential_captain_count', 0)
            t.setdefault('best_differential_captain_score', 0)
            t.setdefault('best_differential_captain_detail', '')
            t.setdefault('total_auto_sub_points', 0)
            t.setdefault('lowest_gw_score', 0)
            t.setdefault('best_transfer_score', 0)
            t.setdefault('best_transfer_detail', '')
            t.setdefault('worst_transfer_score', 0)
            t.setdefault('worst_transfer_detail', '')
            t.setdefault('current_hot_streak', 0)
            t.setdefault('hot_streak_best', 0)
            t.setdefault('current_cold_streak', 0)
            t.setdefault('cold_streak_best', 0)

            t['defensive_points_gained'] += stats.get('defensive_gain', 0)
            t['defensive_points_lost']   += stats.get('defensive_loss', 0)
            t['net_defensive_score']      = t['defensive_points_gained'] - t['defensive_points_lost']
            t['goals_scored']     += stats.get('goals_scored', 0)
            t['assists']          += stats.get('assists', 0)
            t['bonus_points']     += stats.get('bonus_points', 0)
            t['yellow_cards']     += stats.get('yellow_cards', 0)
            t['red_cards']        += stats.get('red_cards', 0)
            # Season captain total uses the active captain at normal x2, including
            # vice-captain auto-swaps and normalising Triple Captain weeks.
            _cap_points = stats.get('captain_points', 0) or 0
            try:
                _cap_points_num = float(_cap_points)
            except (TypeError, ValueError):
                _cap_points_num = 0
            _orig_cap_name = str(stats.get('original_captain_name', stats.get('selected_captain_name', '')) or '').strip()
            _orig_vice_name = str(stats.get('original_vice_captain_name', stats.get('selected_vice_captain_name', '')) or '').strip()
            _active_cap_name = str(stats.get('captain_name', stats.get('active_captain_name', '')) or '').strip()
            _switched_names = bool(_active_cap_name and _orig_vice_name and _active_cap_name == _orig_vice_name and (not _orig_cap_name or _active_cap_name != _orig_cap_name))
            _switched = bool(stats.get('captain_switched_to_vice') or stats.get('vice_became_captain') or stats.get('used_vice_captain') or _switched_names)
            _orig_cap_raw = stats.get('original_captain_raw_points', stats.get('selected_captain_raw_points'))
            if _orig_cap_raw in (None, '', '—'):
                _orig_cap_raw = stats.get('captain_raw_points')
            try:
                _orig_cap_raw_num = float(_orig_cap_raw or 0)
            except (TypeError, ValueError):
                _orig_cap_raw_num = 0
            _vice_raw_probe = stats.get('original_vice_captain_raw_points', stats.get('selected_vice_captain_raw_points', stats.get('vice_captain_raw_points')))
            try:
                _vice_raw_probe_num = float(_vice_raw_probe or 0)
            except (TypeError, ValueError):
                _vice_raw_probe_num = 0
            _inferred_swap = (_orig_cap_raw_num == 0 and (_cap_points_num > 0 or _vice_raw_probe_num > 0))
            _raw_candidates = []
            if _switched or _inferred_swap:
                _raw_candidates.extend([
                    stats.get('original_vice_captain_raw_points'),
                    stats.get('selected_vice_captain_raw_points'),
                    stats.get('vice_captain_raw_points'),
                    stats.get('active_captain_raw_points'),
                ])
            _raw_candidates.extend([stats.get('active_captain_raw_points'), stats.get('captain_raw_points')])
            _normal_cap_total = 0
            for _raw in _raw_candidates:
                if _raw in (None, '', '—'):
                    continue
                try:
                    _raw_num = float(_raw or 0)
                except (TypeError, ValueError):
                    _raw_num = 0
                if _raw_num > 0:
                    _normal_cap_total = int(_raw_num * 2)
                    break
            if not _normal_cap_total and _cap_points_num:
                _chip_for_cap = str(stats.get('chip_used', stats.get('chip', ''))).lower()
                if _chip_for_cap in ('triple captain', '3xc', 'tc', 'triplecaptain'):
                    _normal_cap_total = int((_cap_points_num / 3) * 2)
                else:
                    _normal_cap_total = int(_cap_points_num)
            t['total_captain_pts'] += _normal_cap_total
            t['total_vice_pts']   += stats.get('vice_captain_raw_points', 0)
            t['bench_points_total'] += stats.get('bench_points', 0)
            t['net_transfer_cost'] += stats.get('net_transfer_cost', 0)

            chip_used_for_transfer = str(stats.get('chip_used', 'None')).lower()
            if chip_used_for_transfer not in ('free hit', 'freehit', 'wildcard'):
                t['net_transfer_points_gained'] = (
                    t.get('net_transfer_points_gained', 0)
                    + stats.get('net_transfer_points', stats.get('net_transfer_points_gained', 0))
                )

                # Best/worst single-GW transfer stories also exclude chip-reset weeks.
                report = stats.get('transfer_report', {}) or {}
                transfer_score = stats.get('net_transfer_points', stats.get('net_transfer_points_gained', None))
                if transfer_score is None:
                    transfer_score = report.get('net_gain', 0)
                try:
                    transfer_score = int(float(transfer_score or 0))
                except (TypeError, ValueError):
                    transfer_score = 0

                def _transfer_parts(item):
                    if isinstance(item, dict):
                        name = item.get('name') or item.get('web_name') or item.get('player_name') or item.get('element_name') or 'Player'
                        pts = item.get('points', item.get('gw_points', item.get('event_points', item.get('total_points'))))
                        pts_num = None
                        if pts not in (None, '', '—'):
                            try:
                                pts_num = int(float(pts))
                            except (TypeError, ValueError):
                                pts_num = 0
                        return name, pts_num
                    return (str(item), None) if item else ('', None)

                def _transfer_label(parts):
                    name, pts = parts
                    return f'{name} ({pts})' if pts is not None else name

                if transfer_score:
                    ins = report.get('ins') or stats.get('transfers_in') or []
                    outs = report.get('outs') or stats.get('transfers_out') or []
                    in_parts = [_transfer_parts(item) for item in ins]
                    out_parts = [_transfer_parts(item) for item in outs]
                    in_parts = [p for p in in_parts if p[0]]
                    out_parts = [p for p in out_parts if p[0]]
                    hit_cost = report.get('cost', stats.get('net_transfer_cost', stats.get('transfer_cost', 0))) or 0
                    try:
                        hit_cost = int(float(hit_cost))
                    except (TypeError, ValueError):
                        hit_cost = 0
                    gw_line = f'GW{gameweek}'
                    if hit_cost > 0:
                        gw_line += f' (Inc. -{hit_cost})'
                    lines = [gw_line]
                    max_len = max(len(in_parts), len(out_parts))
                    if max_len:
                        for idx in range(min(max_len, 3)):
                            in_item = in_parts[idx] if idx < len(in_parts) else None
                            out_item = out_parts[idx] if idx < len(out_parts) else None
                            if in_item and out_item:
                                delta = ''
                                if in_item[1] is not None and out_item[1] is not None:
                                    delta = f' {int(in_item[1] - out_item[1]):+d}'
                                lines.append(f'{_transfer_label(out_item)} → {_transfer_label(in_item)}{delta}')
                            elif in_item:
                                lines.append(f'In {_transfer_label(in_item)}')
                            elif out_item:
                                lines.append(f'Out {_transfer_label(out_item)}')
                    else:
                        lines.append('Transfer')
                    transfer_detail = '<br>'.join(lines)
                    if transfer_score > t.get('best_transfer_score', 0):
                        t['best_transfer_score'] = transfer_score
                        t['best_transfer_detail'] = transfer_detail
                    if t.get('worst_transfer_score', 0) == 0 or transfer_score < t.get('worst_transfer_score', 0):
                        t['worst_transfer_score'] = transfer_score
                        t['worst_transfer_detail'] = transfer_detail

            t['differential_points'] = t.get('differential_points', 0) + _weekly_differential_points(stats)

            active_cap = str(stats.get('captain_name') or stats.get('active_captain_name') or stats.get('captain') or '').strip()
            if active_cap and active_cap in popular_captains:
                t['popular_armband_count'] = t.get('popular_armband_count', 0) + 1

            # Best Differential Captain: active captain selected by under 20%
            # of the league, scored as normal x2 captaincy.
            if active_cap:
                selected_count = captain_counts.get(active_cap, 0)
                selected_pct = (selected_count / max(total_managers, 1)) * 100
                if selected_pct < 20:
                    t['differential_captain_count'] = t.get('differential_captain_count', 0) + 1
                    diff_cap_score = (stats.get('captain_raw_points', 0) or 0) * 2
                    if diff_cap_score > t.get('best_differential_captain_score', 0):
                        t['best_differential_captain_score'] = diff_cap_score
                        t['best_differential_captain_detail'] = f'{active_cap} · GW{gameweek}'

            if m_id in top_scorer_pick_ids:
                t['top_scorer_pick_count'] = t.get('top_scorer_pick_count', 0) + 1
            if m_id in top_scorer_pick_details:
                pick_score, pick_name = top_scorer_pick_details.get(m_id, (0, ''))
                if pick_score > t.get('best_pick_score', 0):
                    t['best_pick_score'] = pick_score
                    t['best_pick_detail'] = f'{pick_name} · GW{gameweek}'
            if m_id in best_differential_pick_ids:
                t['best_differential_pick_count'] = t.get('best_differential_pick_count', 0) + 1
            diff_score = best_differential_score_by_manager.get(m_id, 0) or 0
            if diff_score > t.get('best_differential_pick_score', 0):
                t['best_differential_pick_score'] = diff_score
                t['best_differential_pick_detail'] = f'{best_differential_detail_by_manager.get(m_id, "")} · GW{gameweek}'


            chip_used = stats.get('chip_used', 'None')
            if chip_used not in ('None', 'none', '', None):
                chip_score = stats.get('chip_score', 0)
                chip_stats = m.setdefault('chip_stats', {
                    'total_score': 0,
                    'chips_played': {},
                    'events': []
                })
                already_logged = any(e.get('gw') == gameweek for e in chip_stats.get('events', []))
                if not already_logged:
                    chip_stats['total_score'] = chip_stats.get('total_score', 0) + chip_score
                    chip_stats.setdefault('chips_played', {})[chip_used] = chip_stats.setdefault('chips_played', {}).get(chip_used, 0) + 1
                    chip_stats.setdefault('events', []).append({
                        'gw': gameweek,
                        'chip': chip_used,
                        'score': chip_score
                    })

            gw_net = stats.get('net_gw_points', 0)
            if gw_net > t['highest_gw_score']:
                t['highest_gw_score'] = gw_net
            if t.get('lowest_gw_score', 0) in (0, None) or gw_net < t.get('lowest_gw_score', gw_net):
                t['lowest_gw_score'] = gw_net

            if gw_net > league_avg_score:
                t['current_hot_streak'] = t.get('current_hot_streak', 0) + 1
                t['hot_streak_best'] = max(t.get('hot_streak_best', 0), t['current_hot_streak'])
            else:
                t['current_hot_streak'] = 0

            if gw_net < league_avg_score:
                t['current_cold_streak'] = t.get('current_cold_streak', 0) + 1
                t['cold_streak_best'] = max(t.get('cold_streak_best', 0), t['current_cold_streak'])
            else:
                t['current_cold_streak'] = 0
            # Best Captain Haul is always normal captaincy x2. Triple Captain
            # weeks still count, but are normalised from the active captain score.
            # Older rows can store the original non-playing captain raw score as 0
            # while captain_points already contains the active vice-captain return,
            # so do not let a zero raw value override a positive captain_points.
            cap_points = stats.get('captain_points', 0) or 0
            try:
                cap_points_num = float(cap_points)
            except (TypeError, ValueError):
                cap_points_num = 0

            switched_to_vice_for_cap = bool(
                stats.get('captain_switched_to_vice')
                or stats.get('vice_became_captain')
                or stats.get('used_vice_captain')
            )
            original_cap_raw = stats.get('original_captain_raw_points', stats.get('selected_captain_raw_points'))
            if original_cap_raw in (None, '', '—'):
                original_cap_raw = stats.get('captain_raw_points')
            try:
                original_cap_num = float(original_cap_raw or 0)
            except (TypeError, ValueError):
                original_cap_num = 0
            inferred_vice_swap_for_cap = (original_cap_num == 0 and cap_points_num > 0)

            cap_raw_candidates = []
            if switched_to_vice_for_cap or inferred_vice_swap_for_cap:
                cap_raw_candidates.extend([
                    stats.get('original_vice_captain_raw_points'),
                    stats.get('selected_vice_captain_raw_points'),
                    stats.get('vice_captain_raw_points'),
                    stats.get('active_captain_raw_points'),
                ])
            cap_raw_candidates.extend([
                stats.get('active_captain_raw_points'),
                stats.get('captain_raw_points'),
            ])

            cap = 0
            for cap_raw in cap_raw_candidates:
                if cap_raw in (None, '', '—'):
                    continue
                try:
                    cap_raw_num = float(cap_raw or 0)
                except (TypeError, ValueError):
                    cap_raw_num = 0
                if cap_raw_num > 0:
                    cap = int(cap_raw_num * 2)
                    break
            if not cap and cap_points_num:
                chip_for_cap = str(stats.get('chip_used', stats.get('chip', ''))).lower()
                if chip_for_cap in ('triple captain', '3xc', 'tc', 'triplecaptain'):
                    cap = int((cap_points_num / 3) * 2)
                else:
                    cap = int(cap_points_num)
            if cap > t['best_captain_score']:
                t['best_captain_score'] = cap
                cap_name = (
                    stats.get('captain_name')
                    or stats.get('active_captain_name')
                    or stats.get('original_vice_captain_name')
                    or stats.get('selected_vice_captain_name')
                    or stats.get('original_captain_name')
                    or stats.get('selected_captain_name')
                    or 'Captain'
                )
                t['best_captain_detail'] = f'{cap_name} · GW{gameweek}'
                t['best_captain_score_detail'] = t['best_captain_detail']

            # Best Vice Captain Haul only counts weeks where the selected vice
            # captain auto-activated because the selected captain did not play.
            # Store the score as normal captaincy x2 so it can be ranked exactly
            # like best_captain_score in the Accolades tab.
            active_captain_name = str(stats.get('captain_name', '') or '').strip()
            selected_vice_name = str(
                stats.get('original_vice_captain_name')
                or stats.get('selected_vice_captain_name')
                or stats.get('vice_captain_name')
                or ''
            ).strip()
            switched_to_vice = bool(
                stats.get('captain_switched_to_vice')
                or stats.get('vice_became_captain')
                or stats.get('used_vice_captain')
                or (active_captain_name and selected_vice_name and active_captain_name == selected_vice_name)
            )
            if switched_to_vice:
                vice_raw = stats.get('original_vice_captain_raw_points')
                if vice_raw in (None, '', '—'):
                    vice_raw = stats.get('selected_vice_captain_raw_points')
                if vice_raw in (None, '', '—'):
                    vice_raw = stats.get('captain_raw_points', stats.get('active_captain_raw_points', 0))
                try:
                    vice_score = int((float(vice_raw or 0)) * 2)
                except (TypeError, ValueError):
                    vice_score = 0
                if vice_score > t.get('best_vice_captain_score', 0):
                    t['best_vice_captain_score'] = vice_score
                    t['best_vice_captain_detail'] = f'{selected_vice_name or active_captain_name or "Vice captain"} · GW{gameweek}'

            # Best Auto-Sub only counts players who began on the bench but
            # ended in the final XI. Store it as a season-total best value,
            # mirroring best_captain_score / best_vice_captain_score so the
            # Accolades tab has a reliable source of truth going forward.
            auto_sub_best = 0
            auto_sub_best_name = ''
            for sub_event in stats.get('auto_subs', []) or []:
                try:
                    pts = int(float(sub_event.get('points', 0) or 0))
                    if pts > auto_sub_best:
                        auto_sub_best = pts
                        auto_sub_best_name = sub_event.get('name') or sub_event.get('player_name') or sub_event.get('web_name') or sub_event.get('element_name') or ''
                except (TypeError, ValueError):
                    pass

            if not auto_sub_best:
                final_ids = {
                    p.get('id') for p in (stats.get('starting_xi_players', []) or [])
                    if isinstance(p, dict) and p.get('id') is not None
                }
                for player in stats.get('squad_players', []) or []:
                    if not isinstance(player, dict):
                        continue
                    was_benched = (player.get('is_starting') is False) or ((player.get('original_position', 99) or 99) > 11)
                    made_final_xi = bool(player.get('is_final_xi')) or player.get('id') in final_ids
                    if was_benched and made_final_xi:
                        try:
                            pts = int(float(player.get('points', 0) or 0))
                            if pts > auto_sub_best:
                                auto_sub_best = pts
                                auto_sub_best_name = player.get('name') or player.get('web_name') or player.get('player_name') or ''
                        except (TypeError, ValueError):
                            pass

            if not auto_sub_best:
                try:
                    auto_sub_best = int(float(stats.get('best_sub_score', 0) or 0))
                except (TypeError, ValueError):
                    auto_sub_best = 0

            if auto_sub_best:
                t['total_auto_sub_points'] = t.get('total_auto_sub_points', 0) + auto_sub_best

            if auto_sub_best > t.get('best_auto_sub_score', 0):
                t['best_auto_sub_score'] = auto_sub_best
                t['best_auto_sub_detail'] = f'{auto_sub_best_name} · GW{gameweek}' if auto_sub_best_name else f'GW{gameweek}'
            if auto_sub_best > t.get('best_autosub_score', 0):
                t['best_autosub_score'] = auto_sub_best

            # Best single scorer left behind on the bench, excluding Bench Boost weeks.
            chip_name_for_bench = str(stats.get('chip_used', stats.get('chip', ''))).lower()
            if chip_name_for_bench not in ('bench boost', 'benchboost', 'bboost'):
                bench_best = 0
                bench_best_name = ''
                stored_bench_pts = stats.get('best_bench_pts')
                if stored_bench_pts not in (None, ''):
                    try:
                        bench_best = int(float(stored_bench_pts or 0))
                        bench_best_name = stats.get('best_bench_name', '') or ''
                    except (TypeError, ValueError):
                        bench_best = 0
                final_ids = {
                    p.get('id') for p in (stats.get('starting_xi_players', []) or [])
                    if isinstance(p, dict) and p.get('id') is not None
                }
                for player in stats.get('squad_players', []) or []:
                    if not isinstance(player, dict):
                        continue
                    is_bench = ((player.get('position', 0) or 0) > 11) or ((player.get('original_position', 0) or 0) > 11)
                    if is_bench and player.get('id') not in final_ids:
                        try:
                            pts = int(float(player.get('points', 0) or 0))
                            if pts > bench_best:
                                bench_best = pts
                                bench_best_name = player.get('name') or player.get('web_name') or player.get('player_name') or ''
                        except (TypeError, ValueError):
                            pass
                if bench_best > t.get('best_left_behind_score', 0):
                    t['best_left_behind_score'] = bench_best
                    t['best_left_behind_detail'] = f'{bench_best_name} · GW{gameweek}' if bench_best_name else f'GW{gameweek}'

            # Overall points & rank — used in division tiebreaker
            m['stats']['total_points'] = stats.get('total_points', 0)
            m['current_overall_rank']  = stats.get('overall_rank', 9_999_999)

        self.update_accolades()

    def update_accolades(self):
        """Populates master['accolades'] from current season totals."""
        def metric_value(manager, metric):
            season = manager.get('season_totals', {}) or {}
            if metric == 'cards_total':
                return season.get('cards_total', season.get('yellow_cards', 0) + season.get('red_cards', 0))
            return season.get(metric, manager.get('stats', {}).get(metric, 0)) or 0

        accolades = self.data.get('accolades', {})
        for section in ('prizes', 'fun'):
            for award_name, award in accolades.get(section, {}).items():
                metric = award.get('metric')
                if not metric:
                    continue

                best_id = None
                best_name = None
                best_value = None

                for m_id, manager in self.managers.items():
                    value = metric_value(manager, metric)
                    if best_value is None or value > best_value:
                        best_id = m_id
                        best_name = manager.get('name', '—')
                        best_value = value

                award['manager_id'] = best_id
                award['manager_name'] = best_name
                award['value'] = best_value or 0

    # -----------------------------------------------------------------------
    # MANAGER OF THE BLOCK
    # -----------------------------------------------------------------------

    def process_block(self, gameweek, gw_results):
        """
        Accumulates net GW points into the current block.
        On the closing GW, determines the winner and resets accumulators.
        Returns (block_name, winner_dict) or None.
        """
        block_name, block_data = get_current_block(gameweek, self.data)
        if not block_name:
            return None

        for m_id, stats in gw_results.items():
            if m_id not in self.managers:
                continue
            bs = self.managers[m_id].setdefault('block_stats', {
                'current_block_points': 0, 'block_wins': []
            })
            bs['current_block_points'] += stats.get('net_gw_points', 0)

        closing_block_name, closing_block_data = is_block_final_gw(gameweek, self.data)
        if not closing_block_name:
            return None

        candidates = [
            {
                'id': m_id,
                'name': m['name'],
                'points': m.get('block_stats', {}).get('current_block_points', 0)
            }
            for m_id, m in self.managers.items()
        ]

        winner = sorted(
            candidates,
            key=lambda x: (x['points'], -self.managers[x['id']]['stats'].get('total_points', 0)),
            reverse=True
        )[0]

        closing_block_data['winner_id']   = winner['id']
        closing_block_data['winner_name'] = winner['name']
        self.managers[winner['id']]['block_stats']['block_wins'].append(closing_block_name)

        for m_id in self.managers:
            if 'block_stats' in self.managers[m_id]:
                self.managers[m_id]['block_stats']['current_block_points'] = 0

        print(f"  [Block] {closing_block_name} winner: {winner['name']} ({winner['points']} pts)")
        return closing_block_name, winner

    # -----------------------------------------------------------------------
    # DIVISIONS
    # -----------------------------------------------------------------------

    def update_division_standings(self):
        """Rebuilds division standings tables from current season totals."""
        for div_name in self.DIVISION_ORDER:
            div = self.data['divisions'].get(div_name, {})
            ranked_ids = sorted_division_standings(div_name, self.data)
            div['standings'] = {
                str(pos + 1): {
                    'manager_id':   m_id,
                    'name':         self.managers[m_id]['name'],
                    'total_points': self.managers[m_id]['stats'].get('total_points', 0),
                    'captain_pts':  self.managers[m_id]['season_totals'].get('total_captain_pts', 0),
                    'goals_scored': self.managers[m_id]['season_totals'].get('goals_scored', 0),
                    'net_def':      self.managers[m_id]['season_totals'].get('net_defensive_score', 0),
                    'vice_pts':     self.managers[m_id]['season_totals'].get('total_vice_pts', 0),
                }
                for pos, m_id in enumerate(ranked_ids)
            }

    def apply_promotion_relegation(self, places=2):
        """
        Promotes top N from each division (except PL) and relegates bottom N
        (except League Two). Call at season end after finalising standings.
        """
        movements = {}
        num_divs = len(self.DIVISION_ORDER)

        for i, div_name in enumerate(self.DIVISION_ORDER):
            ranked_ids = sorted_division_standings(div_name, self.data)
            movements[div_name] = {'promoted': [], 'relegated': []}

            if i > 0:   # can promote upward
                for m_id in ranked_ids[:places]:
                    upper = self.DIVISION_ORDER[i - 1]
                    self.data['divisions'][upper]['manager_ids'].append(m_id)
                    self.data['divisions'][div_name]['manager_ids'].remove(m_id)
                    self.managers[m_id]['division'] = upper
                    movements[div_name]['promoted'].append(self.managers[m_id]['name'])

            if i < num_divs - 1:   # can relegate downward
                for m_id in ranked_ids[-places:]:
                    lower = self.DIVISION_ORDER[i + 1]
                    self.data['divisions'][lower]['manager_ids'].append(m_id)
                    self.data['divisions'][div_name]['manager_ids'].remove(m_id)
                    self.managers[m_id]['division'] = lower
                    movements[div_name]['relegated'].append(self.managers[m_id]['name'])

        self.data['promotion_relegation']['last_season_changes'] = movements
        return movements

    # -----------------------------------------------------------------------
    # LAST MAN STANDING
    # -----------------------------------------------------------------------

    def _gw_stats(self, gw_results, m_id):
        """Return this-GW stats for a manager, accepting str/int keyed gw_results."""
        if not gw_results:
            return {}
        mid = str(m_id)
        stats = gw_results.get(mid)
        if stats is None and mid.isdigit():
            stats = gw_results.get(int(mid))
        if stats is None:
            stats = gw_results.get(m_id)
        return stats or {}

    def _lms_sort_key(self, m_id, gw_results):
        """
        LMS tiebreaker tuple — ascending so index 0 = worst (eliminated).
        Chain: gw_points → captain_points → goals_scored →
               net_defensive_score → vice_captain_points → overall_rank.
        All values must come from this single gameweek, never season totals.
        """
        s = self._gw_stats(gw_results, m_id)
        return (
            s.get('net_gw_points', s.get('gw_points', 0)) or 0,
            s.get('captain_points', 0) or 0,
            s.get('goals_scored', 0) or 0,
            s.get('net_defensive_week', s.get('net_defensive_score', 0)) or 0,
            s.get('vice_captain_raw_points', s.get('vice_captain_points', 0)) or 0,
            -(s.get('overall_rank', 9_999_999) or 9_999_999),
        )

    def process_lms_elimination(self, gameweek, gw_results):
        """
        Runs LMS for a scheduled GW.

        Normal scheduled GWs eliminate one manager. GWs listed in
        lms['double_elim_gws'] eliminate two. The final GW declares a winner
        from the remaining pool using this-GW LMS tiebreakers.
        """
        lms = self.data['competitions']['lms']
        schedule = [int(gw) for gw in lms.get('schedule', [])]
        if int(gameweek) not in schedule:
            return None

        active_ids = [str(m_id) for m_id in lms.get('active_ids', [])]
        if not active_ids:
            print("  [LMS] No active managers — competition complete.")
            return None

        candidates = [m_id for m_id in active_ids if m_id in self.managers]
        final_gw = int(lms.get('final_gw', schedule[-1] if schedule else gameweek))

        # Final: rank whoever is left and declare the winner. This is robust to
        # a schedule/config issue that leaves more than two managers alive.
        if int(gameweek) == final_gw:
            ranked = sorted(candidates, key=lambda x: self._lms_sort_key(x, gw_results), reverse=True)
            if not ranked:
                return None
            winner_id = ranked[0]
            runner_id = ranked[1] if len(ranked) > 1 else None

            lms.update({
                'winner_id':     winner_id,
                'winner_name':   self.managers[winner_id]['name'],
                'runner_up_id':  runner_id,
                'runner_up_name': self.managers[runner_id]['name'] if runner_id else None,
                'active_ids':    [winner_id]
            })
            # Store any extra finalists as final-GW eliminations for audit.
            if len(ranked) > 2:
                lms.setdefault('final_eliminated_ids', {})[str(gameweek)] = ranked[2:]
                lms.setdefault('final_eliminated', {})[str(gameweek)] = [self.managers[m]['name'] for m in ranked[2:]]

            result = {
                'type': 'final',
                'winner':    {'id': winner_id, 'name': self.managers[winner_id]['name']},
                'runner_up': {'id': runner_id, 'name': self.managers[runner_id]['name']} if runner_id else None,
            }
            print(
                f"  [LMS] FINAL — Winner: {result['winner']['name']}"
                + (f" | Runner-up: {result['runner_up']['name']}" if runner_id else "")
            )
            return result

        # Normal / double elimination
        ranked = sorted(candidates, key=lambda x: self._lms_sort_key(x, gw_results))
        double_gws = {int(gw) for gw in lms.get('double_elim_gws', [])}
        elim_count = 2 if int(gameweek) in double_gws else 1
        elim_count = min(elim_count, max(0, len(ranked) - 2)) if len(ranked) > 2 else 0
        if elim_count <= 0:
            return None

        losers = ranked[:elim_count]
        for loser_id in losers:
            if loser_id in lms['active_ids']:
                lms['active_ids'].remove(loser_id)
            elif int(loser_id) in lms['active_ids']:
                lms['active_ids'].remove(int(loser_id))
            self.managers[loser_id]['stats']['lms_alive'] = False

        loser_names = [self.managers[mid]['name'] for mid in losers]
        # Keep old single-value field for compatibility, plus detailed fields.
        lms.setdefault('eliminated_ids', {})[str(gameweek)] = losers
        lms['eliminated'][str(gameweek)] = loser_names[0] if len(loser_names) == 1 else loser_names

        remaining = len(lms['active_ids'])
        print(f"  [LMS] GW{gameweek}: {', '.join(loser_names)} eliminated. {remaining} remain.")
        return {
            'type': 'elimination',
            'losers': [{'id': mid, 'name': self.managers[mid]['name']} for mid in losers],
            'loser': {'id': losers[0], 'name': self.managers[losers[0]]['name']},
            'survivors': [self.managers[m]['name'] for m in ranked[elim_count:]]
        }

    # -----------------------------------------------------------------------
    # CUP — GROUP STAGE
    # -----------------------------------------------------------------------

    def _cup_group_sort_key(self, cs):
        """
        Group stage tiebreaker (descending — best first).
        Chain: group_points → cup_fpl_points_sum → cup_captain_sum →
               cup_goals_sum → cup_defensive_sum → cup_vice_sum → overall_rank
        """
        return (
            cs.get('match_points', 0),
            cs.get('cup_fpl_points_sum', 0),
            cs.get('cup_captain_sum', 0),
            cs.get('cup_goals_sum', 0),
            cs.get('cup_defensive_sum', 0),
            cs.get('cup_vice_sum', 0),
            -cs.get('last_overall_rank', 9_999_999)  # lower rank = better
        )

    def process_cup_group_gw(self, gameweek, gw_results):
        """
        Processes a cup group-stage GW:
          1. Accumulates cumulative totals.
          2. Scores H2H fixtures (3/1/0).
          3. On the final group GW, finalises standings and qualification.
        """
        cup = self.data['competitions']['cup']
        if gameweek not in cup['group_stage_gws']:
            return

        fixtures_this_gw = cup.get('fixtures', {}).get(str(gameweek), [])
        participants = set()
        for fixture in fixtures_this_gw:
            if not isinstance(fixture, dict):
                continue
            if fixture.get('home') is not None:
                participants.add(str(fixture.get('home')))
            if fixture.get('away') is not None:
                participants.add(str(fixture.get('away')))

        def _ensure_cup_stats(m_id):
            return self.managers[m_id].setdefault('cup_stats', {
                'group': None, 'match_points': 0, 'played': 0,
                'cup_fpl_points_sum': 0, 'cup_goals_sum': 0,
                'cup_defensive_sum': 0,
                'cup_captain_sum': 0, 'cup_vice_sum': 0,
                'qualified': False, 'knockout_stage': None,
                'knockout_fpl_points_sum': 0, 'knockout_captain_sum': 0,
                'knockout_goals_sum': 0, 'knockout_net_defensive_sum': 0,
                'knockout_vice_sum': 0, 'last_overall_rank': 9_999_999
            })

        # Only managers with a cup fixture this GW should have cup totals
        # accumulated. This keeps bye weeks clear and makes the Played column
        # meaningful for odd-sized groups.
        for m_id in participants:
            if m_id not in self.managers:
                continue
            stats = self._gw_stats(gw_results, m_id)
            if not stats:
                continue
            cs = _ensure_cup_stats(m_id)
            cs['played'] = cs.get('played', cs.get('cup_played', 0)) + 1
            cs['cup_played'] = cs['played']
            cs['cup_fpl_points_sum']      += stats.get('net_gw_points', 0)
            cs['cup_goals_sum']           += stats.get('goals_scored', 0)
            cs['cup_defensive_sum']       += stats.get('net_defensive_week', 0)
            cs['cup_captain_sum']         += stats.get('captain_points', 0)
            cs['cup_vice_sum']            += stats.get('vice_captain_raw_points', 0)
            cs['last_overall_rank']        = stats.get('overall_rank', 9_999_999)

        # Score fixtures
        for fixture in fixtures_this_gw:
            if not isinstance(fixture, dict):
                continue
            h_id, a_id = str(fixture['home']), str(fixture['away'])
            if not self._gw_stats(gw_results, h_id) or not self._gw_stats(gw_results, a_id):
                continue
            _ensure_cup_stats(h_id)
            _ensure_cup_stats(a_id)
            h_score = self._gw_stats(gw_results, h_id).get('net_gw_points', 0)
            a_score = self._gw_stats(gw_results, a_id).get('net_gw_points', 0)
            fixture['home_score'] = h_score
            fixture['away_score'] = a_score
            if h_score > a_score:
                self.managers[h_id]['cup_stats']['match_points'] += 3
                fixture['winner'] = h_id
            elif a_score > h_score:
                self.managers[a_id]['cup_stats']['match_points'] += 3
                fixture['winner'] = a_id
            else:
                self.managers[h_id]['cup_stats']['match_points'] += 1
                self.managers[a_id]['cup_stats']['match_points'] += 1
                fixture['winner'] = None

        if gameweek == cup['group_stage_gws'][-1]:
            self._finalise_cup_groups(cup)

    def _finalise_cup_groups(self, cup):
        """
        Finalise group standings, auto-qualifiers and playoff entrants.

        Playoff entrants are selected by finishing-place tiers first. For a
        5x5 setup this means only 4th-place teams are compared for the PO SF;
        a strong 5th-place team cannot jump ahead of a weaker 4th-place team.
        """
        auto_places = int(cup.get('auto_qualify_places', cup.get('auto_qualify', 0)) or 0)
        playoff_spots = int(cup.get('playoff_spots', 0) or 0)
        playoff_entrants = int(cup.get('playoff_entrants', 0) or 0)
        cup.setdefault('group_standings', {})
        cup['qualified_ids'] = []

        ranked_by_group = {}
        for group_name, member_ids in cup.get('groups', {}).items():
            ranked = sorted(
                [str(m) for m in member_ids],
                key=lambda mid: self._cup_group_sort_key(self.managers[mid].get('cup_stats', {})),
                reverse=True
            )
            ranked_by_group[group_name] = ranked
            cup['group_standings'][group_name] = ranked

            for pos, m_id in enumerate(ranked):
                if pos < auto_places:
                    self.managers[m_id]['cup_stats']['qualified'] = True
                    if m_id not in cup['qualified_ids']:
                        cup['qualified_ids'].append(m_id)
                    print(f"  [Cup] {self.managers[m_id]['name']} qualifies from {group_name} (P{pos+1})")

        if playoff_spots <= 0:
            self._create_initial_knockout_fixtures(cup)
            return

        target_entrants = playoff_entrants or (playoff_spots * 2)
        selected = []
        max_group_size = max((len(ids) for ids in ranked_by_group.values()), default=0)
        # Place-tier selection: all 4ths, then all 5ths, etc. Sort within each
        # tier by official cup group tiebreakers.
        for pos in range(auto_places, max_group_size):
            tier = [ranked[pos] for ranked in ranked_by_group.values() if len(ranked) > pos]
            tier = sorted(
                tier,
                key=lambda m: self._cup_group_sort_key(self.managers[m].get('cup_stats', {})),
                reverse=True
            )
            for m_id in tier:
                if len(selected) >= target_entrants:
                    break
                selected.append(m_id)
            if len(selected) >= target_entrants:
                break

        cup['_playoff_ids'] = selected
        cup['playoff_candidates'] = selected

        if len(selected) <= playoff_spots:
            for q in selected:
                self.managers[q]['cup_stats']['qualified'] = True
                if q not in cup['qualified_ids']:
                    cup['qualified_ids'].append(q)
            cup.pop('_playoff_ids', None)
            self._create_initial_knockout_fixtures(cup)
            return

        self._create_cup_playoff_fixtures(cup, selected)
        names = [self.managers[m]['name'] for m in selected]
        cup['playoff_result'] = f"Playoff needed: {', '.join(names)}"
        print(f"  [Cup] Playoff required: {', '.join(names)}")

    def _create_cup_playoff_fixtures(self, cup, playoff_ids):
        """Create initial playoff fixtures from ranked playoff candidates."""
        playoff_gws = cup.get('playoff_gws') or ([cup.get('playoff_gw')] if cup.get('playoff_gw') else [])
        playoff_gws = sorted({int(gw) for gw in playoff_gws if gw not in (None, '', [])})
        if not playoff_gws or len(playoff_ids) < 2:
            return

        fixtures = cup.setdefault('fixtures', {})
        first_gw = str(playoff_gws[0])
        fixtures.setdefault(first_gw, [])

        # Clear any old auto-generated playoff fixtures for this GW.
        fixtures[first_gw] = [
            fx for fx in fixtures[first_gw]
            if not self._cup_round_is_playoff(fx)
        ]

        # Seed top v bottom, second v second-bottom, etc. If the calendar has
        # two playoff GWs this is a PO SF; otherwise each tie is effectively a
        # PO Final for one knockout place.
        ordered = [str(mid) for mid in playoff_ids]
        pairings = []
        for i in range(len(ordered) // 2):
            pairings.append((ordered[i], ordered[-(i + 1)]))
        round_label = 'Playoff SF' if len(playoff_gws) > 1 and len(pairings) > 1 else 'Playoff Final'

        for idx, (home, away) in enumerate(pairings, start=1):
            fixtures[first_gw].append({
                'gw': int(first_gw),
                'home': str(home),
                'away': str(away),
                'round': round_label,
                'tie_id': f'PO{idx}',
                'source': 'auto_playoff',
            })

    def _cup_single_gw_winner(self, home_id, away_id, gw_results):
        """One-GW cup tie-breaker chain."""
        h = self._gw_stats(gw_results, home_id)
        a = self._gw_stats(gw_results, away_id)
        h_key = (
            h.get('net_gw_points', 0),
            h.get('captain_points', 0),
            h.get('goals_scored', 0),
            h.get('net_defensive_week', 0),
            h.get('vice_captain_raw_points', 0),
            -h.get('overall_rank', 9_999_999),
        )
        a_key = (
            a.get('net_gw_points', 0),
            a.get('captain_points', 0),
            a.get('goals_scored', 0),
            a.get('net_defensive_week', 0),
            a.get('vice_captain_raw_points', 0),
            -a.get('overall_rank', 9_999_999),
        )
        return str(home_id) if h_key >= a_key else str(away_id)

    def _cup_round_is_playoff(self, fixture):
        """True for playoff fixtures, accepting old/new round labels."""
        label = str((fixture or {}).get('round', '')).strip().lower()
        return (
            label.startswith('playoff')
            or label.startswith('po ')
            or label in {'po sf', 'po f', 'posf', 'pof'}
            or 'playoff' in label
        )

    def _cup_fixtures_for_gw(self, cup, gameweek):
        """Return the mutable fixture list for a GW, accepting int/str keys."""
        fixtures_obj = cup.setdefault('fixtures', {})
        gw_int = int(gameweek)
        gw_str = str(gw_int)
        if isinstance(fixtures_obj, dict):
            if gw_str in fixtures_obj:
                return fixtures_obj[gw_str]
            if gw_int in fixtures_obj:
                return fixtures_obj[gw_int]
            fixtures_obj[gw_str] = []
            return fixtures_obj[gw_str]
        return []

    def process_cup_playoff(self, gameweek, gw_results):
        """Process Cup playoff SF/F fixtures for the final knockout place(s)."""
        cup = self.data['competitions']['cup']
        gameweek = int(gameweek)
        playoff_gws = cup.get('playoff_gws') or ([cup.get('playoff_gw')] if cup.get('playoff_gw') else [])
        playoff_gws = sorted({int(gw) for gw in playoff_gws if gw not in (None, '', [])})
        if gameweek not in playoff_gws:
            return None

        fixtures = self._cup_fixtures_for_gw(cup, gameweek)
        playoff_fixtures = [
            fx for fx in fixtures
            if isinstance(fx, dict) and self._cup_round_is_playoff(fx)
        ]

        # Backwards-compatible old mode: a single pool of playoff IDs in one GW.
        if not playoff_fixtures:
            playoff_ids = cup.get('_playoff_ids', [])
            if not playoff_ids:
                return None
            winner = max(playoff_ids, key=lambda m: (
                self._gw_stats(gw_results, m).get('net_gw_points', 0),
                self._gw_stats(gw_results, m).get('captain_points', 0),
                self._gw_stats(gw_results, m).get('goals_scored', 0),
                self._gw_stats(gw_results, m).get('net_defensive_week', 0),
                self._gw_stats(gw_results, m).get('vice_captain_raw_points', 0),
                -self._gw_stats(gw_results, m).get('overall_rank', 9_999_999),
            ))
            self.managers[winner]['cup_stats']['qualified'] = True
            if winner not in cup['qualified_ids']:
                cup['qualified_ids'].append(winner)
            cup['playoff_result'] = f"Playoff winner: {self.managers[winner]['name']}"
            cup.pop('_playoff_ids', None)
            self._create_initial_knockout_fixtures(cup)
            print(f"  [Cup] Playoff winner: {self.managers[winner]['name']}")
            return {'type': 'playoff', 'winner_id': winner, 'winner_name': self.managers[winner]['name']}

        results = []
        winners = []
        for fixture in playoff_fixtures:
            h_id = str(fixture['home'])
            a_id = str(fixture['away'])
            winner = self._cup_single_gw_winner(h_id, a_id, gw_results)
            winners.append(winner)
            result = {
                'round': fixture.get('round', 'Playoff'),
                'tie_id': fixture.get('tie_id'),
                'home_id': h_id,
                'away_id': a_id,
                'home_name': self.managers[h_id]['name'],
                'away_name': self.managers[a_id]['name'],
                'home_gw': self._gw_stats(gw_results, h_id).get('net_gw_points', 0),
                'away_gw': self._gw_stats(gw_results, a_id).get('net_gw_points', 0),
                'winner_id': winner,
                'winner_name': self.managers[winner]['name'],
            }
            fixture['home_score'] = result['home_gw']
            fixture['away_score'] = result['away_gw']
            fixture['winner_id'] = winner
            fixture['winner_name'] = self.managers[winner]['name']
            results.append(result)

        cup.setdefault('playoff_results', {})[str(gameweek)] = results

        is_final = any('final' in str(fx.get('round', '')).lower() for fx in playoff_fixtures)
        playoff_spots = cup.get('playoff_spots', 1)
        playoff_gws = [gw for gw in playoff_gws if gw]

        if is_final or len(winners) <= playoff_spots or gameweek == playoff_gws[-1]:
            for winner in winners[:playoff_spots]:
                self.managers[winner]['cup_stats']['qualified'] = True
                if winner not in cup['qualified_ids']:
                    cup['qualified_ids'].append(winner)
            names = [self.managers[w]['name'] for w in winners[:playoff_spots]]
            cup['playoff_result'] = f"Playoff winner: {', '.join(names)}"
            cup.pop('_playoff_ids', None)
            self._create_initial_knockout_fixtures(cup)
            print(f"  [Cup] Playoff winner(s): {', '.join(names)}")
            return results

        # SF complete: create final fixture on the next playoff GW.
        next_gws = [gw for gw in playoff_gws if gw > gameweek]
        if next_gws and len(winners) >= 2:
            final_gw = str(next_gws[0])
            cup.setdefault('fixtures', {}).setdefault(final_gw, [])
            cup['fixtures'][final_gw] = [
                fx for fx in cup['fixtures'][final_gw]
                if not self._cup_round_is_playoff(fx)
            ]
            cup['fixtures'][final_gw].append({
                'gw': int(final_gw),
                'home': str(winners[0]),
                'away': str(winners[1]),
                'round': 'Playoff Final',
                'tie_id': 'POF',
                'source': 'auto_playoff',
            })
            print(
                f"  [Cup] Playoff Final set: "
                f"{self.managers[winners[0]]['name']} v {self.managers[winners[1]]['name']} (GW{final_gw})"
            )

        return results

    # -----------------------------------------------------------------------
    # CUP — KNOCKOUT (two-legged until final, then single-leg)
    # -----------------------------------------------------------------------

    def _create_knockout_round_fixtures(self, cup, round_name, participants):
        """Create fixtures for a knockout round from an ordered participant list."""
        participants = [str(mid) for mid in participants if str(mid) in self.managers]
        if len(participants) < 2:
            return
        rounds = cup.get('knockout_rounds', {}) or {}
        gws = rounds.get(round_name, [])
        if not gws:
            return

        fixtures = cup.setdefault('fixtures', {})
        for gw in gws:
            fixtures.setdefault(str(gw), [])
            fixtures[str(gw)] = [
                fx for fx in fixtures[str(gw)]
                if not (fx.get('source') == 'auto_ko' and str(fx.get('round', '')).startswith(round_name))
            ]

        pairings = []
        for i in range(len(participants) // 2):
            pairings.append((participants[i], participants[-(i + 1)]))

        is_final = len(gws) == 1
        for idx, (home, away) in enumerate(pairings, start=1):
            tie_id = f"{round_name.replace(' ', '').upper()}{idx}"
            if is_final:
                fixtures[str(gws[0])].append({
                    'gw': int(gws[0]), 'home': home, 'away': away,
                    'round': round_name, 'tie_id': tie_id, 'source': 'auto_ko'
                })
            else:
                fixtures[str(gws[0])].append({
                    'gw': int(gws[0]), 'home': home, 'away': away,
                    'round': f'{round_name} — 1st Leg', 'tie_id': tie_id, 'source': 'auto_ko'
                })
                fixtures[str(gws[1])].append({
                    'gw': int(gws[1]), 'home': away, 'away': home,
                    'round': f'{round_name} — 2nd Leg', 'tie_id': tie_id, 'source': 'auto_ko'
                })
        cup.setdefault('knockout_bracket', {})[round_name] = participants
        print(f"  [Cup] {round_name} fixtures created for {len(participants)} managers")

    def _create_initial_knockout_fixtures(self, cup):
        """Create Last 16 fixtures once exactly enough managers have qualified."""
        target = int(cup.get('knockout_target', 16) or 16)
        qualified = [str(mid) for mid in cup.get('qualified_ids', []) if str(mid) in self.managers]
        if len(qualified) < target:
            return
        qualified = qualified[:target]
        # Sort qualified managers by group-stage performance so seeding is stable.
        qualified = sorted(
            qualified,
            key=lambda m: self._cup_group_sort_key(self.managers[m].get('cup_stats', {})),
            reverse=True
        )
        existing = cup.get('knockout_bracket', {}).get('Last 16')
        if existing:
            return
        self._reset_ko_accumulators(qualified)
        self._create_knockout_round_fixtures(cup, 'Last 16', qualified)

    def _maybe_create_next_knockout_round(self, cup, round_label, winners):
        """Create the next knockout round after a deciding leg/final."""
        lower = str(round_label).lower()
        if 'last 16' in lower:
            next_round = 'Quarter-final'
        elif 'quarter' in lower or lower.startswith('qf'):
            next_round = 'Semi-final'
        elif 'semi' in lower:
            next_round = 'Final'
        else:
            return
        if cup.get('knockout_bracket', {}).get(next_round):
            return
        self._reset_ko_accumulators(winners)
        self._create_knockout_round_fixtures(cup, next_round, winners)

    def _ko_sort_key(self, m_id):
        """
        Knockout tiebreaker tuple (descending — highest wins).
        Based on aggregate stats across both legs (or single GW for final).
        Chain: knockout_fpl_points_sum → knockout_captain_points →
               knockout_goals_scored → knockout_net_defensive_score →
               knockout_vice_captain_points → overall_rank
        """
        cs = self.managers[m_id].get('cup_stats', {})
        return (
            cs.get('knockout_fpl_points_sum', 0),
            cs.get('knockout_captain_sum', 0),
            cs.get('knockout_goals_sum', 0),
            cs.get('knockout_net_defensive_sum', 0),
            cs.get('knockout_vice_sum', 0),
            -cs.get('last_overall_rank', 9_999_999)
        )

    def _accumulate_ko_stats(self, m_id, stats):
        """Adds a single GW's stats to a manager's knockout accumulators."""
        cs = self.managers[m_id]['cup_stats']
        cs['knockout_fpl_points_sum']     += stats.get('net_gw_points', 0)
        cs['knockout_captain_sum']        += stats.get('captain_points', 0)
        cs['knockout_goals_sum']          += stats.get('goals_scored', 0)
        cs['knockout_net_defensive_sum']  += stats.get('net_defensive_week', 0)
        cs['knockout_vice_sum']           += stats.get('vice_captain_raw_points', 0)
        cs['last_overall_rank']            = stats.get('overall_rank', 9_999_999)

    def _reset_ko_accumulators(self, m_ids):
        """Resets knockout accumulators ahead of the next round."""
        for m_id in m_ids:
            if m_id in self.managers:
                cs = self.managers[m_id]['cup_stats']
                cs['knockout_fpl_points_sum']    = 0
                cs['knockout_captain_sum']       = 0
                cs['knockout_goals_sum']         = 0
                cs['knockout_net_defensive_sum'] = 0
                cs['knockout_vice_sum']          = 0

    def process_cup_knockout_gw(self, gameweek, gw_results):
        """
        Processes a knockout GW.

        Two-legged rounds (Last 16, QF, SF):
          - 1st leg: accumulate stats only, no result yet.
          - 2nd leg: accumulate stats, then decide winner on aggregate.

        Final: single GW decides the winner directly.

        Fixtures in cup['fixtures'][str(gw)] must include:
          {'home': m_id, 'away': m_id, 'round': 'Last 16 — 1st Leg', 'tie_id': 'T1'}

        tie_id groups both legs of the same fixture together.
        """
        cup = self.data['competitions']['cup']
        if gameweek not in cup['knockout_gws']:
            return None

        gw_fixtures = cup['fixtures'].get(str(gameweek), [])
        results = []

        for fixture in gw_fixtures:
            h_id    = str(fixture['home'])
            a_id    = str(fixture['away'])
            round_label = fixture.get('round', 'Knockout')
            tie_id  = fixture.get('tie_id', f"{h_id}v{a_id}")
            is_final = 'Final' in round_label and '1st' not in round_label and '2nd' not in round_label
            is_second_leg = '2nd Leg' in round_label

            # Accumulate this GW's stats for both managers
            h_stats = self._gw_stats(gw_results, h_id)
            a_stats = self._gw_stats(gw_results, a_id)
            if h_stats:
                self._accumulate_ko_stats(h_id, h_stats)
            if a_stats:
                self._accumulate_ko_stats(a_id, a_stats)

            h_gw = h_stats.get('net_gw_points', 0)
            a_gw = a_stats.get('net_gw_points', 0)

            result = {
                'round':      round_label,
                'tie_id':     tie_id,
                'home_id':    h_id,
                'away_id':    a_id,
                'home_name':  self.managers[h_id]['name'],
                'away_name':  self.managers[a_id]['name'],
                'home_gw':    h_gw,
                'away_gw':    a_gw,
                'decided':    False,
                'winner_id':  None,
                'winner_name': None,
            }

            # Decide winner on 2nd leg or final
            if is_second_leg or is_final:
                h_key = self._ko_sort_key(h_id)
                a_key = self._ko_sort_key(a_id)
                winner_id = h_id if h_key >= a_key else a_id
                loser_id  = a_id if h_key >= a_key else h_id

                result['decided']     = True
                result['winner_id']   = winner_id
                result['winner_name'] = self.managers[winner_id]['name']
                result['home_agg']    = self.managers[h_id]['cup_stats']['knockout_fpl_points_sum']
                result['away_agg']    = self.managers[a_id]['cup_stats']['knockout_fpl_points_sum']

                # Update stage labels
                self.managers[winner_id]['cup_stats']['knockout_stage'] = round_label
                self.managers[loser_id]['cup_stats']['knockout_stage']  = f"Out ({round_label})"

                # Reset accumulators for the winners ahead of next round
                self._reset_ko_accumulators([winner_id])

                if is_final:
                    cup['cup_winner_id']   = winner_id
                    cup['cup_winner_name'] = self.managers[winner_id]['name']
                    print(f"  [Cup] 🏆 CHAMPION: {self.managers[winner_id]['name']}")

                print(
                    f"  [Cup {round_label}] "
                    f"{self.managers[h_id]['name']} {result.get('home_agg', h_gw)} - "
                    f"{result.get('away_agg', a_gw)} {self.managers[a_id]['name']} "
                    f"→ {self.managers[winner_id]['name']} advances"
                )
            else:
                # 1st leg — just report the score
                print(
                    f"  [Cup {round_label}] "
                    f"{self.managers[h_id]['name']} {h_gw} - "
                    f"{a_gw} {self.managers[a_id]['name']} (1st leg)"
                )

            results.append(result)

        cup['knockout_results'][str(gameweek)] = results

        decided = [r for r in results if r.get('decided') and r.get('winner_id')]
        if decided:
            # A GW only contains one knockout round in the generated calendar.
            round_label = decided[0].get('round', '')
            lower_round = str(round_label).lower()
            is_true_final = ('final' in lower_round and 'semi' not in lower_round and 'quarter' not in lower_round and 'last 16' not in lower_round)
            if not is_true_final:
                winners = [r['winner_id'] for r in decided]
                self._maybe_create_next_knockout_round(cup, round_label, winners)

        return results
