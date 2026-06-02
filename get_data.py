import requests
from helpers import build_team, get_player_name, calculate_original_team_score


class GetData:
    BASE_URL = "https://fantasy.premierleague.com/api/"

    def __init__(self, league_id):
        self.league_id = league_id
        self.session = requests.Session()
        bootstrap = self.session.get(f"{self.BASE_URL}bootstrap-static/").json()
        self.players_map = {p['id']: p for p in bootstrap['elements']}

    def _get_data(self, url):
        """Helper to fetch data from a URL, with basic error handling."""
        try:
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"\nAPI Error: Could not fetch data from {url}. Error: {e}")
            return {}

    def _process_chip_data(
        self,
        active_chip,
        net_points,
        capt_raw,
        bench_points,
        previous_team_score=None,
    ):
        """
        Returns the pretty chip name and estimated point impact.

        Bench Boost:
        Final bench points.

        Triple Captain:
        Extra points gained from 3x captain instead of normal 2x captain.
        This equals the captain's base/raw points.

        Free Hit / Wildcard:
        Points gained compared with the previous GW squad's best valid XI,
        estimated using the previous GW picks scored in the current GW.
        """
        if active_chip == 'bboost':
            return 'Bench Boost', bench_points

        if active_chip == '3xc':
            return 'Triple Captain', capt_raw

        if active_chip in ('freehit', 'wildcard'):
            if previous_team_score is None:
                return ('Free Hit' if active_chip == 'freehit' else 'Wildcard'), 0

            return (
                'Free Hit' if active_chip == 'freehit' else 'Wildcard',
                net_points - previous_team_score
            )

        return "None", 0

    def gather_all_manager_data(self, gameweek):
        """
        Fetches and processes all manager data for a given gameweek.

        Returns a dict keyed by manager ID (str) with a full report card
        including all stats needed for every competition engine.
        """
        live_data = self._get_data(f"{self.BASE_URL}event/{gameweek}/live/")
        live_elements = {e['id']: e for e in live_data.get('elements', [])}

        standings = self._get_data(
            f"{self.BASE_URL}leagues-classic/{self.league_id}/standings/"
        )

        all_reports = {}

        for entry in standings.get('standings', {}).get('results', []):
            m_id = str(entry['entry'])
            picks_data = self._get_data(
                f"{self.BASE_URL}entry/{m_id}/event/{gameweek}/picks/"
            )
            history_data = self._get_data(f"{self.BASE_URL}entry/{m_id}/history/")
            transfers_raw = self._get_data(f"{self.BASE_URL}entry/{m_id}/transfers/")

            if not picks_data:
                print(f"  Warning: No picks data for manager {m_id}, skipping.")
                continue

            # ------------------------------------------------------------------
            # 1. Team building & core history
            # ------------------------------------------------------------------
            final_xi, final_bench = build_team(
                picks_data['picks'], live_elements, self.players_map
            )

            # FPL exposes official automatic substitutions separately. Prefer
            # this over inferred final-XI comparisons because it captures the
            # exact bench player(s) brought on by the game.
            official_auto_subs_raw = picks_data.get('automatic_subs', []) or []
            official_auto_sub_in_ids = {
                sub.get('element_in') for sub in official_auto_subs_raw
                if sub.get('element_in') is not None
            }
            
            starting_xi_players = []

            for p in final_xi:
                player_id = p["element"]
                player_static = self.players_map.get(player_id, {})
                player_live = live_elements.get(player_id, {}).get("stats", {})

                starting_xi_players.append({
                    "id": player_id,
                    "name": get_player_name(player_id, self.players_map),
                    "points": player_live.get("total_points", 0),
                    "position": player_static.get("element_type", 0),
                })


            squad_players = []

            for p in picks_data.get("picks", []):
                player_id = p["element"]
                player_static = self.players_map.get(player_id, {})
                player_live = live_elements.get(player_id, {}).get("stats", {})

                squad_players.append({
                    "id": player_id,
                    "name": get_player_name(player_id, self.players_map),
                    "points": player_live.get("total_points", 0),
                    "position": player_static.get("element_type", 0),
                    "original_position": p.get("position", 99),
                    "is_starting": p.get("position", 99) <= 11,
                    "is_final_xi": any(fp.get("element") == player_id for fp in final_xi),
                    "auto_subbed_on": (
                        player_id in official_auto_sub_in_ids
                        or (p.get("position", 99) > 11 and any(fp.get("element") == player_id for fp in final_xi))
                    ),
                })

            gw_h = next(
                (h for h in history_data.get('current', []) if h['event'] == gameweek), {}
            )
            prev_h = next(
                (h for h in history_data.get('current', []) if h['event'] == gameweek - 1), {}
            )

            transfer_cost = gw_h.get('event_transfers_cost', 0)
            net_gw_points = gw_h.get('points', 0) - transfer_cost
            rank_change = (
                prev_h.get('overall_rank', 0) - gw_h.get('overall_rank', 0)
            ) if prev_h else 0

            # ------------------------------------------------------------------
            # 2. Performance tracking across the starting XI
            # ------------------------------------------------------------------
            team_stats = {
                "goals": 0, "assists": 0, "bonus": 0,
                "yc": 0, "rc": 0,
                "goals_conceded_from_xi": 0
            }
            def_gain, def_loss = 0, 0
            gw_hero_name, gw_hero_pts = "", -1
            best_form_name, best_form_val = "", -1.0

            for pick in final_xi:
                p_id = pick['element']
                p_live = live_elements[p_id]['stats']
                p_static = self.players_map[p_id]
                p_pts = p_live.get('total_points', 0)
                p_name = get_player_name(p_id, self.players_map)
                p_type = p_static['element_type']

                # GW hero & best form
                if p_pts > gw_hero_pts:
                    gw_hero_pts, gw_hero_name = p_pts, p_name
                form_val = float(p_static.get('form', 0))
                if form_val > best_form_val:
                    best_form_val, best_form_name = form_val, p_name

                # Core accumulations
                team_stats["goals"] += p_live.get('goals_scored', 0)
                team_stats["assists"] += p_live.get('assists', 0)
                team_stats["bonus"] += p_live.get('bonus', 0)
                team_stats["yc"] += p_live.get('yellow_cards', 0)
                team_stats["rc"] += p_live.get('red_cards', 0)

                # Custom defensive points model
                if p_type in [1]:  # GK
                    if p_live.get('clean_sheets', 0) > 0:
                        def_gain += 4

                    # -1 for every 2 goals conceded
                    goals_conc = p_live.get('goals_conceded', 0)
                    def_loss += goals_conc // 2

                    # +1 for every 3 saves
                    saves = p_live.get('saves', 0)
                    def_gain += saves // 3

                    # +5 for every penalty saved
                    pens_saved = p_live.get('penalties_saved', 0)
                    def_gain += pens_saved * 5

                elif p_type == 2: # DEF
                    if p_live.get('clean_sheets', 0) > 0:
                        def_gain += 4

                    goals_conc = p_live.get('goals_conceded', 0)
                    def_loss += goals_conc // 2

                    if p_live.get('defensive_contribution', 0) >= 10:
                        def_gain += 2

                elif p_type == 3:  # MID
                    if p_live.get('clean_sheets', 0) > 0:
                        def_gain += 1
                    if p_live.get('defensive_contribution', 0) >= 12:
                        def_gain += 2
                        
                elif p_type == 4:  # FWD
                    if p_live.get('defensive_contribution', 0) >= 12:
                        def_gain += 2

            # ------------------------------------------------------------------
            # 3. Captaincy logic (handles vice-captain auto-activation)
            # ------------------------------------------------------------------
            orig_cap = next(p for p in picks_data['picks'] if p['is_captain'])
            orig_vice = next(p for p in picks_data['picks'] if p['is_vice_captain'])

            cap_played = live_elements[orig_cap['element']]['stats'].get('minutes', 0) > 0
            vice_played = live_elements[orig_vice['element']]['stats'].get('minutes', 0) > 0

            captain_switched_to_vice = False

            if cap_played:
                active_cap_id = orig_cap['element']
                active_vice_id = orig_vice['element']
                cap_mult = orig_cap['multiplier']
            elif vice_played:
                # Vice steps up as the active captain. Keep the original
                # captain multiplier so captain_points mirrors FPL scoring.
                active_cap_id = orig_vice['element']
                active_vice_id = orig_cap['element']
                cap_mult = orig_cap['multiplier']
                captain_switched_to_vice = True
            else:
                active_cap_id = orig_cap['element']
                active_vice_id = orig_vice['element']
                cap_mult = 1  # Neither played — no multiplier applied

            capt_raw = live_elements[active_cap_id]['stats']['total_points']
            capt_final = capt_raw * cap_mult
            vice_raw = (
                live_elements[active_vice_id]['stats']['total_points']
                if active_vice_id else 0
            )
            original_captain_raw = live_elements[orig_cap['element']]['stats']['total_points']
            original_vice_raw = live_elements[orig_vice['element']]['stats']['total_points']

            # ------------------------------------------------------------------
            # 4. Subs & chips
            # ------------------------------------------------------------------
            orig_bench_ids = {
                p['element'] for p in picks_data['picks'] if p['position'] > 11
            }
            sub_players = [p for p in final_xi if p['element'] in orig_bench_ids]
            best_sub = max(
                sub_players,
                key=lambda x: live_elements[x['element']]['stats']['total_points'],
                default=None
            )

            best_sub_pts = (
                live_elements[best_sub['element']]['stats']['total_points']
                if best_sub else 0
            )
            best_sub_name = (
                get_player_name(best_sub['element'], self.players_map)
                if best_sub else "None"
            )
            official_auto_subs = []
            for sub in official_auto_subs_raw:
                element_in = sub.get('element_in')
                element_out = sub.get('element_out')
                if not element_in:
                    continue
                official_auto_subs.append({
                    "id": element_in,
                    "name": get_player_name(element_in, self.players_map),
                    "points": live_elements.get(element_in, {}).get("stats", {}).get("total_points", 0),
                    "element_in": element_in,
                    "element_out": element_out,
                    "out_name": get_player_name(element_out, self.players_map) if element_out else "",
                })

            inferred_auto_subs = [
                {
                    "id": p["element"],
                    "name": get_player_name(p["element"], self.players_map),
                    "points": live_elements[p["element"]]["stats"].get("total_points", 0),
                    "element_in": p["element"],
                    "element_out": None,
                    "out_name": "",
                }
                for p in sub_players
            ]
            auto_subs = official_auto_subs if official_auto_subs else inferred_auto_subs

            if official_auto_subs:
                best_sub = max(
                    official_auto_subs,
                    key=lambda x: x.get('points', 0),
                    default=None
                )
                best_sub_pts = best_sub.get('points', 0) if best_sub else 0
                best_sub_name = best_sub.get('name', 'None') if best_sub else 'None'
            bench_points = sum(
                live_elements.get(p['element'], {}).get('stats', {}).get('total_points', 0)
                for p in final_bench
            )
            bench_players = [p for p in final_bench]
            best_bench_player = max(
                bench_players,
                key=lambda x: live_elements[x['element']]['stats']['total_points'],
                default=None
            )
            best_bench_pts = (
                live_elements[best_bench_player['element']]['stats']['total_points']
                 if best_bench_player else 0
            )
            best_bench_name = (
                get_player_name(best_bench_player['element'], self.players_map)
                if best_bench_player else "None"
            )

            active_chip_raw = (picks_data.get('active_chip') or "none").lower()
            previous_team_score = None

            if active_chip_raw in ('freehit', 'wildcard') and gameweek > 1:
                prev_picks_data = self._get_data(
                    f"{self.BASE_URL}entry/{m_id}/event/{gameweek - 1}/picks/"
                )

                if prev_picks_data and prev_picks_data.get('picks'):
                    previous_team_score = calculate_original_team_score(
                        prev_picks_data['picks'],
                        live_elements
                    )

            chip_name, chip_impact = self._process_chip_data(
                active_chip_raw,
                net_gw_points,
                capt_raw,
                bench_points,
                previous_team_score
            )

            # ------------------------------------------------------------------
            # 5. Transfer net points
            # ------------------------------------------------------------------
            gw_transfers = [t for t in transfers_raw if t.get('event') == gameweek]

            transfer_ins = []
            transfer_outs = []

            for t in gw_transfers:
                player_in_id = t.get('element_in')
                player_out_id = t.get('element_out')

                player_in_points = live_elements.get(player_in_id, {}).get('stats', {}).get('total_points', 0)
                player_out_points = live_elements.get(player_out_id, {}).get('stats', {}).get('total_points', 0)

                transfer_ins.append({
                    "id": player_in_id,
                    "name": get_player_name(player_in_id, self.players_map),
                    "points": player_in_points,
                })

                transfer_outs.append({
                    "id": player_out_id,
                    "name": get_player_name(player_out_id, self.players_map),
                    "points": player_out_points,
                })

            p_in = sum(p["points"] for p in transfer_ins)
            p_out = sum(p["points"] for p in transfer_outs)

            gross_transfer_gain = p_in - p_out
            net_transfer_pts = gross_transfer_gain - transfer_cost

            # ------------------------------------------------------------------
            # 6. Full report card
            # ------------------------------------------------------------------
            all_reports[m_id] = {
                # Identity
                "name": entry['player_name'],
                "display_name": entry['entry_name'],

                # Points
                "total_points": entry['total'],
                "gw_points": entry['event_total'],       # raw FPL GW score (pre-hit)
                "net_gw_points": net_gw_points,          # after transfer hits

                # Rank
                "overall_rank": gw_h.get('overall_rank', 0),
                "rank_change": rank_change,
                "team_value": picks_data['entry_history']['value'] / 10,

                # Captaincy
                "captain_name": get_player_name(active_cap_id, self.players_map),
                "captain_raw_points": capt_raw,          # active captain base points (no multiplier)
                "captain_points": capt_final,             # multiplied (used for competitions)
                "vice_captain_name": (
                    get_player_name(active_vice_id, self.players_map)
                    if active_vice_id else "None"
                ),
                "vice_captain_raw_points": vice_raw,
                "original_captain_name": get_player_name(orig_cap['element'], self.players_map),
                "original_captain_raw_points": original_captain_raw,
                "original_vice_captain_name": get_player_name(orig_vice['element'], self.players_map),
                "original_vice_captain_raw_points": original_vice_raw,
                "captain_switched_to_vice": captain_switched_to_vice,

                # Squad
                "starting_xi_players": starting_xi_players,
                "squad_players": squad_players,

                # Chip
                "chip_used": chip_name,
                "chip_score": chip_impact,

                # Bench
                "bench_points": bench_points,
                "best_sub_name": best_sub_name,
                "best_sub_score": best_sub_pts,
                "auto_subs": auto_subs,
                "best_bench_name": best_bench_name,
                "best_bench_pts": best_bench_pts,

                # Shout-outs
                "gw_hero": f"{gw_hero_name} ({gw_hero_pts})",
                "highest_form_player": f"{best_form_name} (Form: {best_form_val})",

                # Attacking
                "goals_scored": team_stats["goals"],
                "assists": team_stats["assists"],
                "bonus_points": team_stats["bonus"],

                # Defensive (custom model)
                "defensive_gain": def_gain,
                "defensive_loss": def_loss,
                "net_defensive_week": def_gain - def_loss,

                # Discipline
                "yellow_cards": team_stats["yc"],
                "red_cards": team_stats["rc"],

                # Transfers
                "net_transfer_points": net_transfer_pts,
                "net_transfer_cost": transfer_cost,
                "transfer_report": {
                    "ins": transfer_ins,
                    "outs": transfer_outs,
                    "points_in": p_in,
                    "points_out": p_out,
                    "gross_gain": gross_transfer_gain,
                    "cost": transfer_cost,
                    "net_gain": net_transfer_pts,
                    "transfer_count": len(gw_transfers),
                },
            }

        return all_reports
