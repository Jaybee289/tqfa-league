"""
main.py
Full pipeline for Torquay Free Agents FPL League.

Usage:
    python main.py --gw 12
    python main.py --gw 12 --dry-run          # fetch & process, no saves
    python main.py --season-end               # run promotion/relegation
"""

import argparse
import json
import sys
from datetime import datetime

from get_data import GetData
from competition_engine import CompetitionEngine
from newsletter_generator import build_newsletter_payload, save_newsletter_payload
from html_generator import build_poster, build_hub

MASTER_FILE  = "league_master.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_master():
    with open(MASTER_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_master(master, dry_run=False):
    if dry_run:
        print("  [Dry Run] Master JSON not saved.")
        return
    with open(MASTER_FILE, "w", encoding="utf-8") as f:
        json.dump(master, f, indent=2, ensure_ascii=False)
    print(f"  ✅  league_master.json saved.")


def snapshot_gw_history(master, gameweek, gw_results):
    """
    Stores a reusable snapshot of this GW in master['gw_history'].

    Keep this compact enough for league_master.json, but include the fields
    needed by the hub's season trackers: division movement, captaincy awards,
    strategy-room pick awards, chips, autosubs and transfer analysis.
    """
    master.setdefault('gw_history', {})[str(gameweek)] = {
        m_id: {
            "name":          stats['name'],
            "gw_points":     stats['gw_points'],
            "net_gw_points": stats['net_gw_points'],
            "total_points":  stats['total_points'],
            "overall_rank":  stats.get('overall_rank', 0),

            # Captaincy
            "captain_name": stats.get('captain_name', ''),
            "captain_raw_points": stats.get('captain_raw_points', 0),
            "captain_points": stats.get('captain_points', 0),
            "vice_captain_name": stats.get('vice_captain_name', ''),
            "vice_captain_raw_points": stats.get('vice_captain_raw_points', 0),
            "original_captain_name": stats.get('original_captain_name', ''),
            "original_captain_raw_points": stats.get('original_captain_raw_points', 0),
            "original_vice_captain_name": stats.get('original_vice_captain_name', ''),
            "original_vice_captain_raw_points": stats.get('original_vice_captain_raw_points', 0),
            "captain_switched_to_vice": stats.get('captain_switched_to_vice', False),

            # Squad/player data for Strategy Room season awards and autosubs
            "starting_xi_players": stats.get('starting_xi_players', []),
            "squad_players": stats.get('squad_players', []),
            "auto_subs": stats.get('auto_subs', []),
            "best_sub_name": stats.get('best_sub_name', ''),
            "best_sub_score": stats.get('best_sub_score', 0),

            # Chip/transfer/bench context
            "chip_used": stats.get('chip_used', 'None'),
            "chip_score": stats.get('chip_score', 0),
            "bench_points": stats.get('bench_points', 0),
            "best_bench_name": stats.get('best_bench_name', ''),
            "best_bench_pts": stats.get('best_bench_pts', 0),
            "net_transfer_points": stats.get('net_transfer_points', stats.get('net_transfer_points_gained', 0)),
        }
        for m_id, stats in gw_results.items()
    }


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_gameweek(gameweek, dry_run=False):
    print(f"\n{'='*60}")
    print(f"  PROCESSING GW{gameweek}  —  {datetime.now().strftime('%d %b %Y %H:%M')}")
    print(f"{'='*60}\n")

    # 1. Load state
    master = load_master()
    league_id = master['league_metadata']['league_id']

    if league_id == 0:
        print("ERROR: league_id is 0 in league_master.json. Run setup.py first.")
        sys.exit(1)

    # 2. Fetch data
    print("[1/6] Fetching GW data from FPL API...")
    fetcher = GetData(league_id)
    gw_results = fetcher.gather_all_manager_data(gameweek)

    if not gw_results:
        print("ERROR: No data returned from FPL API. Aborting.")
        sys.exit(1)

    print(f"      {len(gw_results)} managers fetched.\n")

    # 3. Snapshot to history
    snapshot_gw_history(master, gameweek, gw_results)

    # 4. Competition engine
    engine = CompetitionEngine(master)

    print("[2/6] Updating season totals & rolling windows...")
    engine.update_season_totals(gameweek, gw_results)

    print("[3/6] Processing Manager of the Block...")
    block_result = engine.process_block(gameweek, gw_results)

    print("[4/6] Updating division standings...")
    engine.update_division_standings()

    print("[5/6] Processing side competitions...")

    # LMS
    lms_result = None
    if gameweek in master['competitions']['lms']['schedule']:
        print("  Running LMS elimination...")
        lms_result = engine.process_lms_elimination(gameweek, gw_results)

    # Cup — group stage
    if gameweek in master['competitions']['cup']['group_stage_gws']:
        print("  Processing Cup group stage GW...")
        engine.process_cup_group_gw(gameweek, gw_results)

    # Cup — playoff (only on the designated playoff GW if triggered)
    playoff_gw = master['competitions']['cup'].get('playoff_gw')
    if gameweek == playoff_gw and master['competitions']['cup'].get('_playoff_ids'):
        print("  Resolving Cup 16th-place playoff...")
        engine.process_cup_playoff(gameweek, gw_results)

    # Cup — knockout
    ko_results = None
    if gameweek in master['competitions']['cup']['knockout_gws']:
        print("  Processing Cup knockout round...")
        ko_results = engine.process_cup_knockout_gw(gameweek, gw_results)

    # 5. Update last processed GW
    master['league_metadata']['last_processed_gw'] = gameweek

    # 6. Save master JSON
    print("\n[6/7] Saving...")
    save_master(master, dry_run=args.dry_run if hasattr(args, 'dry_run') else dry_run)

    # 7. Build HTML files
    print("[7/7] Generating HTML...")
    newsletter_payload = build_newsletter_payload(gameweek, gw_results, master)
    save_newsletter_payload(gameweek, newsletter_payload)
    
    if not dry_run:
        build_poster(gameweek, gw_results, master, newsletter_payload)
        build_hub(gameweek, master, gw_results=gw_results)

    # 8. Summary print
    _print_gw_summary(gameweek, gw_results, master, lms_result, block_result)


def run_season_end(dry_run=False):
    """Applies promotion/relegation at end of season."""
    print("\n[Season End] Applying promotion & relegation...")
    master = load_master()
    engine = CompetitionEngine(master)
    movements = engine.apply_promotion_relegation(
        places=master['promotion_relegation'].get('places', 2)
    )
    for div, moves in movements.items():
        if moves['promoted']:
            print(f"  {div} → Promoted: {', '.join(moves['promoted'])}")
        if moves['relegated']:
            print(f"  {div} → Relegated: {', '.join(moves['relegated'])}")
    save_master(master, dry_run=dry_run)


# ---------------------------------------------------------------------------
# Console summary
# ---------------------------------------------------------------------------

def _print_gw_summary(gameweek, gw_results, master, lms_result, block_result):
    """Prints a readable GW summary to the console."""
    print(f"\n{'─'*60}")
    print(f"  GW{gameweek} SUMMARY")
    print(f"{'─'*60}")

    sorted_managers = sorted(
        gw_results.items(),
        key=lambda x: x[1].get('net_gw_points', 0),
        reverse=True
    )

    print(f"  {'Pos':<4} {'Manager':<22} {'GW':>5} {'Net':>5} {'Cap':<18} {'Chip'}")
    print(f"  {'─'*4} {'─'*22} {'─'*5} {'─'*5} {'─'*18} {'─'*12}")
    for pos, (m_id, s) in enumerate(sorted_managers, 1):
        cap_str = f"{s.get('captain_name','?')} ({s.get('captain_points',0)})"
        print(
            f"  {pos:<4} {s['name']:<22} "
            f"{s.get('gw_points',0):>5} {s.get('net_gw_points',0):>5} "
            f"{cap_str:<18} {s.get('chip_used','None')}"
        )

    print(f"\n  Division Standings (top 3 per division):")
    for div_name, div_data in master['divisions'].items():
        standings = div_data.get('standings', {})
        if not standings:
            continue
        print(f"\n  [{div_name}]")
        for pos in ['1', '2', '3']:
            if pos in standings:
                e = standings[pos]
                print(f"    {pos}. {e['name']:<22} {e['total_points']} pts")

    if lms_result:
        print(f"\n  LMS: ", end="")
        if lms_result['type'] == 'elimination':
            remaining = len(master['competitions']['lms']['active_ids'])
            print(f"❌ {lms_result['loser']['name']} eliminated. {remaining} remain.")
        elif lms_result['type'] == 'final':
            print(f"🏆 Winner: {lms_result['winner']['name']}")

    if block_result:
        block_name, winner = block_result
        print(f"\n  Block: 🏅 {block_name} won by {winner['name']} ({winner['points']} pts) — £10 prize")

    print(f"\n{'─'*60}\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Torquay FPL League Pipeline")
    parser.add_argument("--gw", type=int, help="Gameweek number to process")
    parser.add_argument("--dry-run", action="store_true", help="Process but don't save")
    parser.add_argument("--season-end", action="store_true", help="Apply promo/relegation")

    args = parser.parse_args()

    if args.season_end:
        run_season_end(dry_run=args.dry_run)
    elif args.gw:
        run_gameweek(
            gameweek=args.gw,
            dry_run=args.dry_run
        )
    else:
        for i in range(1, 39):
            run_gameweek(
                gameweek=i,
                dry_run=args.dry_run
            )
        ## parser.print_help()
