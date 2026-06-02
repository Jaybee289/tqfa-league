"""
html_generator.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Generates two self-contained HTML files each gameweek:

  gw_{N}_poster.html  — Weekly debrief: scores, captaincy, stats, competitions
  league_hub.html     — Always-current: division tables, LMS, Cup, accolades

Both files are fully self-contained (no external dependencies).
Share via WhatsApp link, GitHub Pages, or any static file host.

Usage:
    from html_generator import build_poster, build_hub
    build_poster(gameweek, gw_results, master_data, payload, output_dir=".")
    build_hub(gameweek, master_data, output_dir=".")

Or called automatically from main.py after each GW.
"""

import os
from collections import Counter, defaultdict

DIVISION_ORDER = ["Premier League", "Championship", "League One", "League Two"]
DIV_ICONS = {"Premier League": "🦁", "Championship": "🍾",
             "League One": "1️⃣", "League Two": "2️⃣"}

# ─────────────────────────────────────────────────────────────────────────────
# Shared CSS (injected into both files)
# ─────────────────────────────────────────────────────────────────────────────

BASE_CSS = """
  :root {
    --bg:#ffffff; --surface:#f7f7f5; --surface2:#efefec;
    --border:rgba(0,0,0,0.09); --text:#1a1a1a; --muted:#6b6b6b;
    --accent:#185fa5; --green:#1d9e75; --amber:#ba7517; --red:#a32d2d;
    --radius:12px;
  }
  @media (prefers-color-scheme:dark) {
    :root { --bg:#191919; --surface:#242424; --surface2:#2e2e2e;
            --border:rgba(255,255,255,0.09); --text:#f0ede8; --muted:#888; }
  }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
         background:var(--bg); color:var(--text); max-width:480px;
         margin:0 auto; padding:12px 12px 48px; font-size:14px; }
  .card { background:var(--surface); border:0.5px solid var(--border);
          border-radius:var(--radius); padding:14px; margin-bottom:12px; }
  .section-label { font-size:11px; font-weight:700; letter-spacing:0.07em;
                   text-transform:uppercase; color:var(--muted); margin-bottom:10px; }
  table { width:100%; border-collapse:collapse; font-size:12px; }
  th { font-size:10px; color:var(--muted); font-weight:700; text-align:left;
       padding:3px 0 5px; border-bottom:0.5px solid var(--border); }
  td { padding:7px 0; border-bottom:0.5px solid var(--border); vertical-align:middle; }
  tr:last-child td { border-bottom:none; }
  .pos  { color:var(--muted); font-size:11px; min-width:18px; }
  .mname { font-size:13px; font-weight:500; }
  .num  { font-size:13px; font-weight:600; color:var(--accent);
          text-align:right; padding-right:8px; }
  .cen  { text-align:center; }
  .alive-pill { display:inline-block; font-size:11px; background:#eaf3de;
                color:#3b6d11; padding:3px 8px; border-radius:999px; margin:3px 3px 3px 0; }
  .elim-row { display:flex; align-items:center; gap:8px; padding:6px 0;
              border-bottom:0.5px solid var(--border); font-size:13px; }
  .elim-row:last-child { border-bottom:none; }
  .elim-gw { font-size:10px; background:#fcebeb; color:var(--red);
              padding:2px 7px; border-radius:999px; font-weight:700;
              min-width:40px; text-align:center; }
  .chip-badge { font-size:10px; background:#e6f1fb; color:#185fa5;
                padding:2px 6px; border-radius:999px; font-weight:600; white-space:nowrap; }
  .hit-badge  { font-size:10px; background:#fcebeb; color:var(--red);
                padding:2px 6px; border-radius:999px; font-weight:600; margin-left:4px; }
  .prize-badge { font-size:11px; background:#faeeda; color:#633806;
                 padding:2px 8px; border-radius:999px; font-weight:700; }
  .acc-row { display:flex; align-items:center; padding:7px 0;
             border-bottom:0.5px solid var(--border); gap:8px; font-size:13px; }
  .acc-row:last-child { border-bottom:none; }
  .acc-name { flex:0 0 130px; font-size:12px; }
  .acc-who  { flex:1; font-weight:500; }
  .acc-val  { font-size:14px; font-weight:700; color:var(--accent);
              min-width:36px; text-align:right; }
"""


def _render_css(css):
    """Render CSS stored with f-string-safe double braces."""
    return css.replace("{{", "{").replace("}}", "}")


# ─────────────────────────────────────────────────────────────────────────────
# Poster CSS
# Keep selectors in double-brace form because this project often embeds CSS in
# f-strings. _render_css() converts them back to normal CSS at render time.
# ─────────────────────────────────────────────────────────────────────────────

POSTER_CSS = """
  .toggle {{ width:100%;background:none;border:none;color:var(--text);font-family:inherit;
             font-size:11px;font-weight:700;letter-spacing:0.07em;text-transform:uppercase;
             cursor:pointer;display:flex;justify-content:space-between;align-items:center;padding:0; }}
  .chev {{ font-size:16px;color:var(--muted);transition:transform 0.2s; }}
  .chev.open {{ transform:rotate(180deg); }}
  .collapsible {{ display:none; }}
  .collapsible.open {{ display:block; }}
  .block-head{{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;margin-bottom:8px;}}
  .block-title{{font-size:13px;font-weight:800;}}
  .block-status{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.07em;font-weight:800;white-space:nowrap;}}
  .block-row{{display:flex;align-items:center;gap:8px;padding:7px 0;border-bottom:0.5px solid var(--border);font-size:13px;}}
  .block-row:last-child{{border-bottom:none;}}
  .block-medal{{font-size:16px;width:22px;text-align:center;flex:0 0 22px;}}
  .block-name{{flex:1;font-weight:600;min-width:0;}}
  .block-score-wrap{{text-align:right;flex:0 0 auto;}}
  .block-score{{font-weight:900;color:#00ff87;line-height:1.1;}}
  .block-gap{{font-size:10px;color:var(--muted);margin-top:2px;line-height:1.1;}}
  .block-complete{{margin-top:10px;border-top:0.5px solid var(--border);padding-top:10px;font-size:13px;}}
  .block-complete-title{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.07em;font-weight:800;margin-bottom:3px;}}
  .block-complete-winner{{font-size:14px;font-weight:900;color:#ffc226;}}
  .lms-box{{border-radius:12px;padding:12px;background:var(--surface2);border:0.5px solid var(--border);}}
  .lms-title{{font-size:14px;font-weight:800;line-height:1.25;color:var(--text);}}
  .lms-sub{{font-size:12px;color:var(--muted);margin-top:3px;line-height:1.35;}}
  .lms-key{{font-weight:900;}}
  .lms-key.danger{{color:#ff4d4d;}}
  .lms-key.good{{color:#00ff87;}}
  .lms-key.warn{{color:#ffc226;}}
  .lms-escaped{{margin-top:9px;border-top:0.5px solid var(--border);padding-top:8px;display:flex;justify-content:space-between;gap:10px;align-items:flex-start;}}
  .lms-escaped-margin{{font-size:10px;color:#ffc226;margin-top:2px;line-height:1.25;font-weight:800;}}
  .lms-escaped-label{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.07em;font-weight:800;}}
  .lms-escaped-name{{font-size:12px;font-weight:700;margin-top:2px;}}
  .lms-escaped-score{{font-size:13px;font-weight:900;color:#ffc226;white-space:nowrap;}}
  .division-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;}}
  .division-tile{{background:var(--surface2);border:0.5px solid var(--border);border-radius:12px;padding:11px;min-width:0;}}
  .division-tile-head{{display:flex;align-items:center;gap:6px;margin-bottom:7px;}}
  .division-icon{{font-size:15px;line-height:1;}}
  .division-name{{font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:0.07em;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
  .division-best{{font-size:13px;font-weight:800;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
  .division-score{{font-size:24px;font-weight:900;color:#00ff87;line-height:1;margin-top:5px;letter-spacing:-0.5px;}}
  .division-score-label{{font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:0.07em;margin-top:2px;}}
  .division-meta{{font-size:10px;color:var(--muted);margin-top:6px;line-height:1.35;}}
  .division-gap{{font-weight:800;color:var(--accent);}}
  .scores-list{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;}}
  @media(max-width:360px){{.scores-list{{grid-template-columns:repeat(2,1fr);}}}}
  .score-tile{{background:var(--surface2);border:0.5px solid var(--border);border-radius:12px;padding:9px;min-width:0;}}
  .score-tile-top{{display:flex;justify-content:space-between;align-items:center;gap:5px;margin-bottom:6px;}}
  .score-head-left{{display:flex;align-items:baseline;gap:5px;min-width:0;}}
  .score-rank{{font-size:9px;color:var(--muted);font-weight:900;letter-spacing:0.03em;}}
  .score-points{{font-size:18px;font-weight:900;line-height:1;color:var(--text);letter-spacing:-0.4px;}}
  .score-diff{{font-size:8px;font-weight:800;white-space:nowrap;opacity:0.85;}}
  .score-diff.good{{color:var(--green);}}
  .score-diff.bad{{color:var(--red);}}
  .score-name{{font-size:12px;font-weight:800;line-height:1.15;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
  .score-meta{{font-size:8px;color:var(--muted);margin-top:3px;line-height:1.25;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
  .score-meta-main{{font-weight:600;}}
  .score-meta-extra{{font-size:8px;opacity:0.9;}}
  .score-meta-sep{{display:inline-block;color:var(--accent);font-weight:900;font-size:9px;margin:0 3px;opacity:0.55;}}
  .cup-head{{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;margin-bottom:8px;}}
  .cup-title{{font-size:13px;font-weight:800;}}
  .cup-status{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.07em;font-weight:800;white-space:nowrap;}}
  .cup-fixture{{position:relative;background:var(--surface2);border:0.5px solid var(--border);border-radius:12px;padding:10px;margin-bottom:8px;}}
  .cup-fixture:last-child{{margin-bottom:0;}}
  .cup-side{{display:flex;justify-content:space-between;align-items:center;gap:8px;font-size:13px;}}
  .cup-side.right{{margin-top:6px;}}
  .cup-name{{font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
  .cup-score{{font-size:18px;font-weight:900;color:var(--text);line-height:1;}}
  .cup-vs{{font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:0.08em;font-weight:900;margin:5px 0;text-align:center;}}
  .cup-note{{font-size:10px;color:var(--muted);margin-top:7px;border-top:0.5px solid var(--border);padding-top:7px;line-height:1.3;}}
  .strategy-grid{{display:grid;grid-template-columns:1fr;gap:8px;}}
  .strategy-card{{background:var(--surface2);border:0.5px solid var(--border);border-radius:12px;padding:12px;min-width:0;overflow:hidden;}}
  .strategy-top{{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;min-width:0;width:100%;}}
  .strategy-top > div:first-child{{min-width:0;flex:1;}}
  .strategy-kicker{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.07em;font-weight:800;margin-bottom:3px;}}
  .strategy-player{{font-size:16px;font-weight:900;line-height:1.15;white-space:normal;overflow-wrap:anywhere;}}
  .strategy-score{{flex:0 0 auto;white-space:nowrap;font-size:17px;font-weight:900;color:var(--green);line-height:1.1;text-align:right;}}
  .strategy-meta{{font-size:11px;color:var(--muted);margin-top:8px;line-height:1.35;white-space:normal;overflow-wrap:anywhere;}}
  .strategy-managers{{font-size:11px;color:var(--muted);font-weight:700;margin-top:4px;line-height:1.35;white-space:normal;overflow-wrap:anywhere;}}
  .template-row{{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:7px 0;border-bottom:0.5px solid var(--border);}}
  .template-row:last-child{{border-bottom:none;padding-bottom:0;}}
  .template-player{{font-size:13px;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
  .template-meta{{font-size:11px;color:var(--muted);font-weight:700;white-space:nowrap;}}
  .transfer-story{{padding:10px 0;border-bottom:0.5px solid var(--border);}}
  .transfer-story:last-child{{border-bottom:none;padding-bottom:0;}}
  .transfer-story-top{{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;margin-bottom:8px;}}
  .transfer-story-main{{min-width:0;flex:1;}}
  .transfer-story-label{{display:flex;align-items:center;gap:6px;font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.07em;font-weight:800;margin-bottom:3px;}}
  .transfer-medal{{font-size:14px;line-height:1;}}
  .transfer-story-manager{{font-size:13px;font-weight:900;line-height:1.2;}}
  .transfer-story-sub{{font-size:10px;color:var(--muted);margin-top:2px;}}
  .transfer-gain{{font-size:18px;font-weight:900;line-height:1;}}
  .transfer-gain.good{{color:#00ff87;}}
  .transfer-gain.bad{{color:#ff4d4d;}}
  .transfer-gain.neutral{{color:var(--muted);}}

  .transfer-moves{{background:var(--surface2);border:0.5px solid var(--border);border-radius:10px;padding:8px;}}
  .transfer-move-row{{display:grid;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr) auto;gap:6px;align-items:center;padding:5px 0;border-bottom:0.5px solid var(--border);font-size:11px;}}
  .transfer-move-row:last-child{{border-bottom:none;padding-bottom:0;}}
  .transfer-move-from{{color:var(--muted);font-weight:600;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-align:right;}}
  .transfer-move-arrow{{color:var(--accent);font-weight:900;font-size:12px;line-height:1;}}
  .transfer-move-to{{color:var(--text);font-weight:700;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
  .transfer-move-gain{{font-weight:900;white-space:nowrap;text-align:right;}}
  .transfer-move-gain.good{{color:var(--green);}}
  .transfer-move-gain.bad{{color:var(--red);}}
  .transfer-move-gain.neutral{{color:var(--muted);}}

  .transfer-summary{{font-size:12px;font-weight:900;text-align:right;margin-top:7px;}}
  .transfer-summary.good{{color:var(--green);}}
  .transfer-summary.bad{{color:var(--red);}}
  .transfer-summary.neutral{{color:var(--muted);}}

  .transfer-market-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin-top:10px;}}
  .transfer-market-card{{background:var(--surface2);border:0.5px solid var(--border);border-radius:12px;padding:10px;min-width:0;}}
  .transfer-market-title{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.07em;font-weight:900;margin-bottom:7px;display:flex;align-items:center;gap:5px;}}
  .transfer-market-row{{display:flex;justify-content:space-between;align-items:flex-start;gap:8px;padding:6px 0;border-bottom:0.5px solid var(--border);}}
  .transfer-market-row:last-child{{border-bottom:none;padding-bottom:0;}}
  .transfer-market-name{{font-size:12px;font-weight:800;line-height:1.2;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
  .transfer-market-meta{{font-size:10px;color:var(--muted);margin-top:2px;line-height:1.25;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
  .transfer-market-value{{font-size:12px;font-weight:900;white-space:nowrap;font-variant-numeric:tabular-nums;}}
  .transfer-market-value.good{{color:var(--green);}}
  .transfer-market-value.bad{{color:var(--red);}}
  @media(max-width:380px){{.transfer-market-grid{{grid-template-columns:1fr;}}}}

  @media(max-width:360px){{.transfer-move-row{{grid-template-columns:minmax(0,1fr) auto minmax(0,1fr);}}.transfer-move-gain{{grid-column:1 / -1;text-align:right;}}}}
  






  .cap-item {{
    display:flex;
    align-items:flex-start;
    justify-content:space-between;
    gap:12px;
    padding:9px 0;
    border-bottom:0.5px solid var(--border);
  }}
  .cap-item:last-child {{
    border-bottom:none;
    padding-bottom:0;
  }}
  .cap-left {{
    display:flex;
    align-items:flex-start;
    gap:8px;
    flex:0 0 128px;
  }}
  .cap-icon {{
    font-size:16px;
    line-height:1.2;
    width:20px;
    text-align:center;
  }}
  .cap-label {{
    font-size:10px;
    color:var(--muted);
    text-transform:uppercase;
    letter-spacing:0.07em;
    font-weight:700;
    margin-top:2px;
  }}
  .cap-value {{
    flex:1;
    text-align:right;
    font-size:13px;
    font-weight:600;
    line-height:1.45;
  }}
  .cap-value-muted {{
    color:var(--muted);
    font-weight:500;
  }}
  .bench-row {{
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:12px;
    padding:9px 0;
    border-bottom:0.5px solid var(--border);
  }}
  .bench-row:last-child {{
    border-bottom:none;
    padding-bottom:0;
  }}
  .bench-row:first-of-type {{
    padding-top:0;
  }}
  .bench-label {{
    font-size:10px;
    color:var(--muted);
    text-transform:uppercase;
    letter-spacing:0.07em;
    font-weight:700;
    margin-bottom:3px;
  }}
  .bench-name {{
    font-size:13px;
    font-weight:700;
  }}
  .bench-detail {{
    font-size:11px;
    color:var(--muted);
    margin-top:2px;
    line-height:1.35;
  }}
  .bench-score {{
    background:#1e1e1e;
    border:0.5px solid rgba(255,255,255,0.08);
    border-radius:10px;
    padding:7px 9px;
    min-width:64px;
    text-align:center;
    font-size:18px;
    font-weight:900;
    color:#00ff87;
    line-height:1;
    white-space:nowrap;
  }}
  .bench-score.good {{
    color:#00ff87;
  }}
  .bench-score.bad {{
    color:#ff4d4d;
  }}
  .bench-score.warn {{
    color:#ffc226;
  }}
  .chip-group {{
    padding:10px 0;
    border-bottom:0.5px solid var(--border);
  }}
  .chip-group:last-child {{
    border-bottom:none;
    padding-bottom:0;
  }}
  .chip-group:first-child {{
    padding-top:0;
  }}
  .chip-group-head {{
    display:flex;
    align-items:flex-start;
    justify-content:space-between;
    gap:12px;
    margin-bottom:7px;
  }}
  .chip-group-title {{
    display:flex;
    align-items:center;
    gap:8px;
    font-size:13px;
    font-weight:700;
  }}
  .chip-icon {{
    font-size:18px;
    width:22px;
    text-align:center;
  }}
  .chip-group-meta {{
    font-size:10px;
    color:var(--muted);
    text-transform:uppercase;
    letter-spacing:0.05em;
    text-align:right;
    padding-top:2px;
  }}
  .chip-manager-row {{
    display:flex;
    justify-content:space-between;
    align-items:center;
    padding:4px 0 4px 30px;
    font-size:12px;
  }}
  .chip-manager-name {{
    color:var(--text);
  }}
  .chip-manager-score {{
    font-weight:800;
  }}
  .chip-manager-score.good {{
    color:#00ff87;
  }}
  .chip-manager-score.bad {{
    color:#ff4d4d;
  }}
  .stat-card-header {{
    display:flex;
    align-items:center;
    gap:6px;
    min-height:18px;
  }}
  .stat-card-icon {{
    font-size:15px;
    line-height:1;
  }}
  .stat-card-label {{
    font-size:10px;
    font-weight:700;
    letter-spacing:0.1em;
    text-transform:uppercase;
    color:rgba(255,255,255,0.45);
  }}
  .podium-row {{
    display:flex;
    align-items:center;
    gap:10px;
    padding:10px 0;
    border-bottom:0.5px solid var(--border);
  }}
  .podium-row:last-child {{
    border-bottom:none;
  }}
  .podium-medal {{
    font-size:24px;
    width:32px;
    text-align:center;
    flex:0 0 32px;
  }}
  .podium-main {{
    flex:1;
    min-width:0;
  }}
  .podium-name {{
    font-size:14px;
    font-weight:800;
    line-height:1.2;
  }}
  .podium-meta {{
    margin-top:4px;
    line-height:1.35;
  }}
  .podium-meta-main {{
    font-size:11px;
    color:var(--muted);
    white-space:nowrap;
    overflow:hidden;
    text-overflow:ellipsis;
  }}
  .podium-meta-extra {{
    font-size:11px;
    color:var(--muted);
    margin-top:2px;
    line-height:1.35;
  }}
  .podium-meta-sep {{
    display:inline-block;
    color:var(--accent);
    font-weight:900;
    font-size:12px;
    margin:0 5px;
    opacity:0.75;
  }}
  .podium-score-box {{
    background:#1e1e1e;
    border:0.5px solid rgba(255,255,255,0.08);
    border-radius:10px;
    padding:7px 9px;
    min-width:64px;
    text-align:center;
    flex:0 0 auto;
  }}
  .podium-score {{
    font-size:24px;
    font-weight:900;
    color:#00ff87;
    line-height:1;
    letter-spacing:-0.5px;
  }}
  .podium-score-label {{
    font-size:9px;
    color:rgba(255,255,255,0.48);
    text-transform:uppercase;
    letter-spacing:0.07em;
    margin-top:3px;
  }}
  .podium-rank-1 .podium-score {{
    font-size:28px;
  }}
  .podium-rank-1 .podium-score-box {{
    border-color:rgba(0,255,135,0.35);
  }}
  .info-row {{
    display:flex;
    justify-content:space-between;
    align-items:flex-start;
    gap:14px;
    font-size:13px;
    padding:7px 0;
    border-bottom:0.5px solid var(--border);
  }}
  .info-row:last-child {{
    border-bottom:none;
  }}
  .info-label {{
    color:var(--muted);
    flex:0 0 118px;
  }}
  .info-value {{
    flex:1;
    text-align:right;
    font-weight:500;
    line-height:1.45;
  }}
  .stack-line,
  .name-line {{
    display:block;
  }}
  .muted {{
    color:var(--muted);
  }}
  .stat-grid {{ display:grid;grid-template-columns:repeat(2,1fr);gap:10px; }}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Hub CSS
# ─────────────────────────────────────────────────────────────────────────────

HUB_CSS = """
  .hero{{text-align:center;padding:20px 0 16px;border-bottom:0.5px solid var(--border);margin-bottom:16px;}}
  .poster-link{{display:block;background:var(--accent);color:#fff;text-decoration:none;text-align:center;padding:12px;border-radius:var(--radius);font-weight:600;font-size:14px;margin-bottom:16px;}}
  .nav{{display:flex;gap:6px;overflow-x:auto;padding-bottom:4px;margin-bottom:16px;}}
  .nav::-webkit-scrollbar{{display:none;}}
  .nav-btn{{white-space:nowrap;font-size:12px;padding:6px 12px;border:0.5px solid var(--border);border-radius:999px;background:var(--surface);color:var(--text);cursor:pointer;font-family:inherit;}}
  .nav-btn.active{{background:var(--accent);color:#fff;border-color:transparent;font-weight:600;}}
  .section{{display:none;}}
  .section.active{{display:block;}}
  body.hub-page{{max-width:480px;}}
  @media(min-width:760px){{body.hub-page{{max-width:760px;padding-left:18px;padding-right:18px;}}}}
  @media(min-width:1040px){{body.hub-page{{max-width:920px;}}}}


  /* Hub divisions */
  .hub-divisions-scroll{{width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch;}}
  .hub-divisions-scroll::-webkit-scrollbar{{height:4px;}}
  .hub-divisions-scroll::-webkit-scrollbar-thumb{{background:var(--border);border-radius:999px;}}
  .hub-div-table{{width:100%;min-width:570px;table-layout:fixed;}}
  .hub-col-rank{{width:58px;}}
  .hub-col-manager{{width:132px;}}
  .hub-col-captain{{width:96px;}}
  .hub-col-gw{{width:44px;}}
  .hub-col-total{{width:58px;}}
  .hub-col-lms{{width:38px;}}
  .hub-col-cup{{width:38px;}}
  .hub-div-table th,.hub-div-table td{{padding-left:0;padding-right:0;}}
  .hub-division-spacer-row td{{border-bottom:none;padding:12px 0 0;}}
  .hub-division-title-cell{{padding:9px 0 7px!important;border-bottom:0.5px solid var(--border);font-size:13px;font-weight:900;color:var(--text);letter-spacing:0.01em;}}
  .hub-division-title-inner{{display:inline-flex;align-items:center;gap:7px;line-height:1.1;}}
  .hub-division-icon{{font-size:17px;line-height:1;}}
  .hub-rank-cell,.hub-rank-head{{text-align:left;}}
  .hub-manager-cell,.hub-manager-head{{text-align:left;}}
  .hub-captain-cell,.hub-captain-head{{text-align:left;}}
  .hub-number-cell,.hub-number-head{{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums;}}
  .hub-status-cell,.hub-status-head{{text-align:center;vertical-align:middle;white-space:nowrap;line-height:1;}}
  .hub-status-cell{{font-size:13px;}}
  .hub-status-head{{font-size:10px;}}
  .hub-div-table td.hub-rank-cell{{border-left:4px solid transparent;padding-left:8px;font-weight:900;color:var(--text);}}
  .hub-rank-wrap{{display:flex;align-items:center;gap:6px;line-height:1;}}
  .hub-rank-number{{min-width:13px;font-variant-numeric:tabular-nums;}}
  .hub-move-badge{{display:inline-flex;align-items:center;justify-content:center;min-width:16px;height:16px;padding:0 4px;border-radius:999px;font-size:9px;font-weight:900;line-height:1;letter-spacing:-0.02em;}}
  .hub-move-badge.up{{background:rgba(0,255,135,0.22);color:var(--green);}}
  .hub-move-badge.down{{background:rgba(255,77,77,0.22);color:var(--red);}}
  .hub-move-badge.same,.hub-move-badge.new{{width:14px;min-width:14px;height:14px;padding:0;background:rgba(148,163,184,0.38);color:transparent;}}
  .hub-div-table .hub-row-promotion td.hub-rank-cell{{border-left-color:var(--green);}}
  .hub-div-table .hub-row-relegation td.hub-rank-cell{{border-left-color:var(--red);}}
  .hub-div-table .hub-row-playoff td.hub-rank-cell{{border-left-color:var(--amber);}}
  .hub-manager-name{{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
  .hub-captain-cell{{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
  .hub-gw-cell{{font-weight:500;color:var(--text);}}
  .hub-total-cell{{font-weight:900;color:var(--text);text-align:right;}}
  .hub-total-head{{text-align:right;font-size:10px;color:var(--muted);font-weight:700;}}
  @media(min-width:700px){{
    .hub-div-table{{min-width:0;width:100%;}}
    .hub-col-rank{{width:72px;}}
    .hub-col-manager{{width:180px;}}
    .hub-col-captain{{width:140px;}}
    .hub-col-gw{{width:58px;}}
    .hub-col-total{{width:74px;}}
    .hub-col-lms{{width:52px;}}
    .hub-col-cup{{width:52px;}}
  }}

  /* Hub live status */
  .hub-live-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;}}
  @media(min-width:700px){{.hub-live-grid{{grid-template-columns:repeat(4,1fr);}}}}
  .hub-live-card{{background:var(--surface2);border:0.5px solid var(--border);border-radius:12px;padding:11px;min-width:0;display:flex;flex-direction:column;justify-content:space-between;gap:6px;}}
  .hub-live-kicker{{font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:0.07em;font-weight:900;}}
  .hub-live-title{{font-size:13px;font-weight:900;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--text);}}
  .hub-live-sub{{font-size:10px;color:var(--muted);font-weight:700;line-height:1.25;min-height:13px;}}
  .hub-live-link{{display:inline-flex;align-items:center;justify-content:center;align-self:flex-start;width:max-content;max-width:100%;border:0.5px solid rgba(86,156,255,0.55);background:rgba(86,156,255,0.14);color:#9ec5ff;border-radius:999px;padding:5px 8px;text-decoration:none;font-size:10px;font-weight:900;line-height:1;box-shadow:0 4px 14px rgba(0,0,0,0.12);}}
  .hub-live-link:hover{{border-color:rgba(86,156,255,0.85);background:rgba(86,156,255,0.2);}}
  .hub-live-card.live{{border-color:rgba(0,255,135,0.28);}}
  .hub-live-card.warn{{border-color:rgba(255,194,38,0.32);}}
  .hub-live-card.idle{{border-color:rgba(255,77,77,0.22);}}
  .hub-live-card.quiet .hub-live-title,
  .hub-live-card.idle .hub-live-title{{color:var(--muted);}}

  /* Hub cup */
  .hub-cup-overview{{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin-bottom:12px;}}
  @media(min-width:700px){{.hub-cup-overview{{grid-template-columns:repeat(4,1fr);}}}}
  .hub-cup-stat{{background:var(--surface2);border:0.5px solid var(--border);border-radius:12px;padding:10px;text-align:center;}}
  .hub-cup-stat-value{{font-size:18px;font-weight:900;line-height:1;color:var(--text);}}
  .hub-cup-stat-label{{font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:0.07em;font-weight:800;margin-top:4px;}}
  .hub-cup-group{{margin-bottom:16px;}}
  .hub-cup-group:last-child{{margin-bottom:0;}}
  .hub-cup-group-title{{font-size:13px;font-weight:900;color:var(--accent);margin-bottom:6px;}}
  .hub-cup-name{{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
  .hub-cup-fixture-card{{background:var(--surface2);border:0.5px solid var(--border);border-radius:12px;padding:12px;margin-bottom:10px;}}
  .hub-cup-fixture-card:last-child{{margin-bottom:0;}}
  .hub-cup-fixture-gw{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.07em;font-weight:900;margin-bottom:7px;}}
  .hub-cup-fixture-row{{display:grid;grid-template-columns:minmax(0,1fr) 20px minmax(0,1fr);gap:7px;align-items:center;padding:6px 0;border-bottom:0.5px solid var(--border);font-size:12px;}}
  .hub-cup-fixture-row:last-child{{border-bottom:none;padding-bottom:0;}}
  .hub-cup-side{{font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
  .hub-cup-side.away{{text-align:right;}}
  .hub-cup-vs{{font-size:9px;color:var(--muted);font-weight:900;text-align:center;}}
  .hub-cup-empty{{font-size:13px;color:var(--muted);line-height:1.35;}}
  .hub-bracket-round{{background:var(--surface2);border:0.5px solid var(--border);border-radius:12px;padding:12px;margin-bottom:10px;}}
  .hub-bracket-round:last-child{{margin-bottom:0;}}
  .hub-bracket-title{{font-size:13px;font-weight:900;margin-bottom:7px;}}
  .hub-bracket-row{{display:grid;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr);gap:8px;align-items:center;padding:6px 0;border-bottom:0.5px solid var(--border);font-size:12px;}}
  .hub-bracket-row:last-child{{border-bottom:none;padding-bottom:0;}}
  .hub-bracket-team{{font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
  .hub-bracket-team.away{{text-align:right;}}
  .hub-bracket-score{{font-size:11px;color:var(--accent);font-weight:900;white-space:nowrap;}}

  /* Hub Tie-breakers */
  .hub-tb-card{{background:var(--surface2);border:0.5px solid var(--border);border-radius:12px;padding:12px;margin-bottom:12px;}}
  .hub-tb-card:last-child{{margin-bottom:0;}}
  .hub-tb-head-row{{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;margin-bottom:8px;}}
  .hub-tb-title{{font-size:14px;font-weight:900;line-height:1.2;color:var(--text);}}
  .hub-tb-status{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.07em;font-weight:900;text-align:right;white-space:nowrap;}}
  .hub-tb-rules{{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 10px;}}
  .hub-tb-rule-pill{{display:inline-flex;align-items:center;gap:5px;background:var(--surface);border:0.5px solid var(--border);border-radius:999px;padding:4px 8px;font-size:10px;font-weight:800;line-height:1.1;color:var(--text);}}
  .hub-tb-rule-no{{display:inline-flex;align-items:center;justify-content:center;width:15px;height:15px;border-radius:999px;background:rgba(0,255,135,0.12);color:var(--green);font-size:8px;font-weight:900;flex:0 0 15px;}}
  .hub-tb-empty{{font-size:12px;color:var(--muted);line-height:1.35;border-top:0.5px solid var(--border);padding-top:9px;}}
  .hub-tb-group{{background:var(--surface);border:0.5px solid var(--border);border-radius:10px;padding:10px;margin-top:9px;}}
  .hub-tb-context{{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;margin-bottom:7px;}}
  .hub-tb-context-title{{font-size:12px;font-weight:900;color:var(--text);line-height:1.2;}}
  .hub-tb-context-meta{{font-size:9px;color:var(--muted);font-weight:800;text-align:right;line-height:1.25;}}
  .hub-tb-row{{display:grid;grid-template-columns:28px minmax(0,1fr) 44px 76px;gap:7px;align-items:center;padding:6px 0;border-bottom:0.5px solid var(--border);font-size:11px;}}
  .hub-tb-row:last-child{{border-bottom:none;padding-bottom:0;}}
  .hub-tb-pos{{font-size:9px;color:var(--muted);font-weight:900;}}
  .hub-tb-name{{font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
  .hub-tb-main{{font-weight:900;text-align:right;font-variant-numeric:tabular-nums;color:var(--text);}}
  .hub-tb-decider{{font-size:9px;color:var(--amber);font-weight:900;text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}

  /* Hub LMS */
  .hub-lms-count-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin-bottom:10px;}}
  .hub-lms-count-card{{background:var(--surface2);border:0.5px solid var(--border);border-radius:12px;padding:11px;text-align:center;}}
  .hub-lms-count-number{{font-size:24px;font-weight:900;line-height:1;color:var(--green);font-variant-numeric:tabular-nums;}}
  .hub-lms-count-number.muted-count{{color:var(--muted);}}
  .hub-lms-count-label{{font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:0.07em;font-weight:800;margin-top:4px;}}
  .hub-lms-box{{background:var(--surface2);border:0.5px solid var(--border);border-radius:12px;padding:12px;margin-bottom:12px;}}
  .hub-lms-label{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.07em;font-weight:800;margin-bottom:6px;}}
  .hub-lms-pill-wrap{{display:flex;flex-wrap:wrap;gap:6px;}}
  .hub-lms-pill{{display:inline-block;background:var(--surface);border:0.5px solid var(--border);border-radius:999px;padding:4px 8px;font-size:11px;font-weight:700;line-height:1.1;}}
  .hub-lms-history{{margin-top:2px;}}
  .hub-lms-elim-row{{display:grid;grid-template-columns:46px 24px minmax(0,1fr) 58px;gap:6px;align-items:center;padding:7px 0;border-bottom:0.5px solid var(--border);font-size:13px;}}
  .hub-lms-elim-row:last-child{{border-bottom:none;padding-bottom:0;}}
  .hub-lms-gw{{font-size:10px;color:var(--muted);font-weight:800;}}
  .hub-lms-zombie{{font-size:14px;text-align:center;}}
  .hub-lms-name{{font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;display:flex;align-items:center;gap:4px;min-width:0;}}
  .hub-lms-score{{font-size:11px;font-weight:900;color:var(--text);text-align:right;font-variant-numeric:tabular-nums;}}
  .hub-lms-score.muted{{color:var(--muted);}}
  .hub-lms-muted{{font-size:13px;color:var(--muted);}}
  .hub-lms-elim-wrap{{border-bottom:0.5px solid var(--border);}}
  .hub-lms-elim-wrap:last-child{{border-bottom:none;}}
  .hub-lms-elim-wrap .hub-lms-elim-row{{border-bottom:none;}}
  .hub-lms-escaped{{display:flex;justify-content:space-between;gap:8px;padding:0 0 7px 76px;font-size:10px;color:var(--muted);line-height:1.25;}}
  .hub-lms-escaped strong{{color:var(--text);}}

  .hub-block-card{{background:var(--surface2);border:0.5px solid var(--border);border-radius:12px;padding:12px;margin-bottom:10px;}}
  .hub-block-card:last-child{{margin-bottom:0;}}
  .hub-block-head{{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;margin-bottom:9px;}}
  .hub-block-title{{font-size:14px;font-weight:900;line-height:1.2;}}
  .hub-block-gws{{font-size:10px;color:var(--muted);font-weight:700;margin-top:3px;}}
  .hub-block-status{{font-size:10px;text-transform:uppercase;letter-spacing:0.07em;font-weight:900;white-space:nowrap;}}
  .hub-block-status.live{{color:var(--green);}}
  .hub-block-status.complete{{color:var(--amber);}}
  .hub-block-status.upcoming{{color:var(--muted);}}
  .hub-block-standings{{margin-top:4px;}}
  .hub-block-row{{display:flex;align-items:center;gap:8px;padding:7px 0;border-bottom:0.5px solid var(--border);font-size:13px;}}
  .hub-block-row:last-child{{border-bottom:none;padding-bottom:0;}}
  .hub-block-medal{{width:22px;text-align:center;font-size:16px;flex:0 0 22px;}}
  .hub-block-name{{flex:1;font-weight:700;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;display:flex;align-items:center;gap:4px;}}
  .hub-block-score-wrap{{text-align:right;flex:0 0 auto;min-width:64px;}}
  .hub-block-points{{display:block;font-size:13px;font-weight:900;color:var(--text);font-variant-numeric:tabular-nums;line-height:1.1;}}
  .hub-block-gap{{font-size:10px;color:var(--muted);margin-top:2px;line-height:1.1;white-space:nowrap;}}
  .hub-block-winner{{display:flex;align-items:center;justify-content:space-between;gap:10px;border-top:0.5px solid var(--border);padding-top:9px;margin-top:8px;font-size:13px;}}
  .hub-block-winner span{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.07em;font-weight:800;}}
  .hub-block-winner strong{{font-size:13px;font-weight:900;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
  .hub-block-muted{{font-size:13px;color:var(--muted);border-top:0.5px solid var(--border);padding-top:9px;}}

  .hub-acc-card{{background:var(--surface2);border:0.5px solid var(--border);border-radius:12px;padding:12px;margin-bottom:10px;}}
  .hub-acc-card:last-child{{margin-bottom:0;}}
  .hub-acc-title{{display:flex;align-items:center;gap:7px;font-size:13px;font-weight:900;line-height:1.2;margin-bottom:8px;}}
  .hub-acc-ranks{{margin-top:2px;}}
  .hub-acc-rank-row{{display:flex;align-items:center;gap:8px;padding:7px 0;border-bottom:0.5px solid var(--border);font-size:13px;}}
  .hub-acc-rank-row:last-child{{border-bottom:none;padding-bottom:0;}}
  .hub-acc-medal{{width:22px;text-align:center;font-size:16px;flex:0 0 22px;}}
  .hub-acc-manager{{flex:1;font-weight:700;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
  .hub-acc-value-wrap{{display:flex;flex-direction:column;align-items:flex-end;gap:2px;flex:0 0 auto;min-width:54px;}}
  .hub-acc-value{{font-size:13px;font-weight:900;color:var(--text);font-variant-numeric:tabular-nums;line-height:1.05;}}
  .hub-acc-tie{{font-size:8px;color:var(--amber);font-weight:900;letter-spacing:0.06em;text-transform:uppercase;white-space:nowrap;line-height:1.05;}}
  .hub-acc-empty{{font-size:13px;color:var(--muted);border-top:0.5px solid var(--border);padding-top:8px;}}

  .hub-chip-leaderboard{{background:var(--surface2);border:0.5px solid var(--border);border-radius:12px;padding:10px;}}
  .hub-chip-head{{display:grid;grid-template-columns:38px minmax(0,1fr) 54px;gap:8px;font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:0.07em;font-weight:800;padding:0 0 6px;border-bottom:0.5px solid var(--border);}}
  .hub-chip-row{{display:grid;grid-template-columns:38px minmax(0,1fr) 54px;gap:8px;align-items:flex-start;padding:10px 0;border-bottom:0.5px solid var(--border);font-size:12px;}}
  .hub-chip-row:last-child{{border-bottom:none;padding-bottom:0;}}
  .hub-chip-rank{{font-size:10px;color:var(--muted);font-weight:900;padding-top:2px;}}
  .hub-chip-main{{min-width:0;}}
  .hub-chip-manager-line{{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:6px;}}
  .hub-chip-manager{{font-weight:900;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0;}}
  .hub-chip-used{{font-size:9px;color:var(--muted);font-weight:800;white-space:nowrap;}}
  .hub-chip-pills{{display:flex;flex-wrap:wrap;gap:5px;}}
  .hub-chip-pill{{display:inline-flex;align-items:center;gap:4px;background:var(--surface);border:0.5px solid var(--border);border-radius:999px;padding:3px 7px;font-size:9px;line-height:1.15;max-width:100%;}}
  .hub-chip-pill-name{{font-weight:900;color:var(--text);white-space:nowrap;}}
  .hub-chip-pill-meta{{font-weight:800;color:var(--muted);white-space:nowrap;}}
  .hub-chip-none{{font-size:10px;color:var(--muted);font-weight:700;}}
  .hub-chip-score{{font-size:13px;font-weight:900;text-align:right;font-variant-numeric:tabular-nums;padding-top:2px;}}
  .hub-chip-score.good{{color:var(--green);}}
  .hub-chip-score.bad{{color:var(--red);}}
  .hub-chip-score.neutral{{color:var(--muted);}}
  .hub-chip-empty{{background:var(--surface2);border:0.5px solid var(--border);border-radius:12px;padding:12px;font-size:13px;color:var(--muted);line-height:1.35;}}
  .hub-chip-events{{display:flex;flex-wrap:wrap;gap:5px;margin-top:6px;}}
  .hub-chip-event{{font-size:9px;font-weight:900;line-height:1.15;white-space:nowrap;}}
  .hub-chip-event.good{{color:var(--green);}}
  .hub-chip-event.bad{{color:var(--red);}}
  .hub-chip-event.neutral{{color:var(--muted);}}
"""



# ─────────────────────────────────────────────────────────────────────────────
# HTML fragments
# ─────────────────────────────────────────────────────────────────────────────

def _captaincy_row(icon, label, value_html):
    return (
        f'<div class="cap-item">'
        f'<div class="cap-left">'
        f'<span class="cap-icon">{icon}</span>'
        f'<span class="cap-label">{label}</span>'
        f'</div>'
        f'<div class="cap-value">{value_html}</div>'
        f'</div>'
    )

def _cup_status_icon(master, manager_id, gameweek):
    cup = master.get('competitions', {}).get('cup', {})
    m = master.get('managers', {}).get(str(manager_id), {})
    cs = m.get('cup_stats', {})

    group_gws = cup.get('group_stage_gws', [])
    knockout_gws = cup.get('knockout_gws', [])

    # During the group stage, nobody is "out" until the group stage has finished.
    if group_gws and gameweek <= group_gws[-1]:
        return "✅"

    # After the group stage, qualified managers are still alive.
    if cs.get('qualified'):
        return "✅"

    # During/after knockout rounds, qualified=False means they are out.
    if knockout_gws and gameweek >= min(knockout_gws):
        return "😵"

    # After group stage but before knockouts/playoff, unqualified = out.
    if group_gws and gameweek > group_gws[-1]:
        return "😵"

    return "✅"

# ─────────────────────────────────────────────────────────────────────────────
# Competition tiebreaker helpers for hub display
# ─────────────────────────────────────────────────────────────────────────────

RULES_REFERENCE = {
    "division_tiebreakers": [
        "fpl_points_this_season",
        "captain_points_this_season",
        "goals_scored_this_season",
        "net_defensive_score_this_season",
        "vice_captain_points_this_season",
        "overall_rank",
    ],
    "lms_tiebreakers": [
        "gw_points",
        "captain_points",
        "goals_scored",
        "net_defensive_score",
        "vice_captain_points",
        "overall_rank",
    ],
    "cup_group_tiebreakers": [
        "group_points",
        "cup_fpl_points_sum",
        "cup_captain_sum",
        "cup_goals_sum",
        "net_defensive_score",
        "cup_vice_sum",
        "overall_rank",
    ],
    "cup_knockout_tiebreakers": [
        "knockout_fpl_points_sum",
        "knockout_captain_points",
        "knockout_goals_scored",
        "knockout_net_defensive_score",
        "knockout_vice_captain_points",
        "overall_rank",
    ],
    "block_tiebreakers": [
        "points_during_active_block",
        "captain_points",
        "goals_scored",
        "net_defensive_score",
        "vice_captain_points",
        "overall_rank",
    ],
}

TB_LABELS = {
    "fpl_points_this_season": "TB FPL",
    "captain_points_this_season": "TB CAP",
    "goals_scored_this_season": "TB G",
    "net_defensive_score_this_season": "TB DEF",
    "vice_captain_points_this_season": "TB VC",
    "overall_rank": "TB OR",
    "gw_points": "TB GW",
    "captain_points": "TB CAP",
    "goals_scored": "TB G",
    "net_defensive_score": "TB DEF",
    "vice_captain_points": "TB VC",
    "group_points": "TB GP",
    "cup_fpl_points_sum": "TB FPL",
    "cup_captain_sum": "TB CAP",
    "cup_goals_sum": "TB G",
    "cup_vice_sum": "TB VC",
    "knockout_fpl_points_sum": "TB FPL",
    "knockout_captain_points": "TB CAP",
    "knockout_goals_scored": "TB G",
    "knockout_net_defensive_score": "TB DEF",
    "knockout_vice_captain_points": "TB VC",
}

TB_DETAILS = {
    "fpl_points_this_season": "season FPL points",
    "captain_points_this_season": "captain points",
    "goals_scored_this_season": "goals scored",
    "net_defensive_score_this_season": "defensive score",
    "vice_captain_points_this_season": "vice-captain points",
    "overall_rank": "overall rank",
    "gw_points": "GW points",
    "captain_points": "captain points",
    "goals_scored": "goals scored",
    "net_defensive_score": "defensive score",
    "vice_captain_points": "vice-captain points",
    "group_points": "group points",
    "cup_fpl_points_sum": "cup FPL points",
    "cup_captain_sum": "cup captain points",
    "cup_goals_sum": "cup goals",
    "cup_vice_sum": "cup vice-captain points",
    "knockout_fpl_points_sum": "KO FPL points",
    "knockout_captain_points": "KO captain points",
    "knockout_goals_scored": "KO goals",
    "knockout_net_defensive_score": "KO defensive score",
    "knockout_vice_captain_points": "KO vice-captain points",
}


def _as_num(value, default=0):
    try:
        if value in (None, "", "—"):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _manager(master, mid):
    managers = master.get("managers", {})
    return managers.get(str(mid), managers.get(mid, {})) or {}


def _manager_name(master, mid):
    return _manager(master, mid).get("name", str(mid))


def _gw_row(manager, gw):
    history = manager.get("gw_history", {}) or {}
    return history.get(str(gw), history.get(gw, {})) or {}


def _gw_snapshot_row(master, mid, gw):
    history = master.get("gw_history", {}) or {}
    snapshot = history.get(str(gw), history.get(gw, {})) or {}
    return snapshot.get(str(mid), snapshot.get(mid, {})) or {}


def _division_movement_maps(master, div, div_entries, gameweek):
    """Return current and previous position maps for the current division members.

    Previous rank is based on the latest available total before the current GW.
    This gives an in-season movement indicator without needing extra stored state.
    """
    current_positions = {str(item["manager_id"]): pos for pos, item in enumerate(div_entries, 1)}

    if not gameweek or int(gameweek) <= 1:
        return current_positions, {}

    previous_gw = int(gameweek) - 1

    def _previous_total(item):
        mid = str(item["manager_id"])
        previous_row = _gw_snapshot_row(master, mid, previous_gw)
        if previous_row:
            return _as_num(previous_row.get("total_points"), 0)

        current_row = _gw_snapshot_row(master, mid, gameweek)
        current_gw_points = current_row.get("net_gw_points", current_row.get("gw_points", 0))
        if current_row:
            return _as_num(current_row.get("total_points"), item.get("total", 0)) - _as_num(current_gw_points, 0)

        manager = _manager(master, mid)
        season_total = item.get("total", manager.get("stats", {}).get("total_points", 0))
        return _as_num(season_total, 0)

    previous_entries = sorted(
        div_entries,
        key=lambda item: (
            _previous_total(item),
            _rule_value(master, item["manager_id"], "overall_rank"),
        ),
        reverse=True,
    )
    previous_positions = {str(item["manager_id"]): pos for pos, item in enumerate(previous_entries, 1)}
    return current_positions, previous_positions


def _division_movement_html(current_pos, previous_pos):
    if not previous_pos:
        return '<span class="hub-move-badge new" title="No previous rank">•</span>'

    movement = previous_pos - current_pos
    if movement > 0:
        label = '▲' if movement == 1 else f'▲{movement}'
        title = f'Moved up {movement} place' if movement == 1 else f'Moved up {movement} places'
        return f'<span class="hub-move-badge up" title="{title}">{label}</span>'
    if movement < 0:
        places = abs(movement)
        label = '▼' if places == 1 else f'▼{places}'
        title = f'Moved down {places} place' if places == 1 else f'Moved down {places} places'
        return f'<span class="hub-move-badge down" title="{title}">{label}</span>'
    return '<span class="hub-move-badge same" title="No movement">•</span>'


def _rule_value(master, mid, rule, gw=None, cup_stats=None):
    manager = _manager(master, mid)
    season = manager.get("season_totals", {}) or {}
    stats = manager.get("stats", {}) or {}
    gw_data = _gw_row(manager, gw) if gw is not None else {}
    cs = cup_stats if cup_stats is not None else (manager.get("cup_stats", {}) or {})

    aliases = {
        "fpl_points_this_season": ["total_points", "fpl_points", "points"],
        "captain_points_this_season": ["captain_points", "total_captain_pts", "captain_points_this_season"],
        "goals_scored_this_season": ["goals_scored", "goals"],
        "net_defensive_score_this_season": ["net_defensive_score", "defensive_score"],
        "vice_captain_points_this_season": ["vice_captain_points", "total_vice_captain_pts", "vice_points"],
        "overall_rank": ["overall_rank", "rank"],
        "points_during_active_block": ["points_during_active_block", "block_points", "current_block_points", "points", "total_points"],
        "gw_points": ["net_gw_points", "gw_points", "points"],
        "captain_points": ["captain_points", "captain_pts"],
        "goals_scored": ["goals_scored", "goals"],
        "net_defensive_score": ["net_defensive_score", "defensive_score"],
        "vice_captain_points": ["vice_captain_points", "vice_points"],
    }

    cup_aliases = {
        "group_points": ["match_points", "group_points"],
        "cup_fpl_points_sum": ["cup_fpl_points_sum", "fpl_points_sum"],
        "cup_captain_sum": ["cup_captain_sum", "captain_sum"],
        "cup_goals_sum": ["cup_goals_sum", "goals_sum"],
        "cup_vice_sum": ["cup_vice_sum", "vice_sum"],
        "knockout_fpl_points_sum": ["knockout_fpl_points_sum", "ko_fpl_points_sum"],
        "knockout_captain_points": ["knockout_captain_points", "ko_captain_points"],
        "knockout_goals_scored": ["knockout_goals_scored", "ko_goals_scored"],
        "knockout_net_defensive_score": ["knockout_net_defensive_score", "ko_net_defensive_score"],
        "knockout_vice_captain_points": ["knockout_vice_captain_points", "ko_vice_captain_points"],
    }

    if rule in cup_aliases:
        for key in cup_aliases[rule]:
            if key in cs:
                return _as_num(cs.get(key))

    sources = []
    if rule in ("gw_points", "captain_points", "goals_scored", "net_defensive_score", "vice_captain_points"):
        sources.append(gw_data)

    # For cup contexts, prefer cup_stats for shared metric names such as
    # net_defensive_score before falling back to season totals.
    if cup_stats is not None:
        sources.extend([cs, season, stats, manager])
    else:
        sources.extend([season, stats, manager, cs])

    for key in aliases.get(rule, [rule]):
        for source in sources:
            if key in source:
                val = source.get(key)
                # Lower overall rank is better, so invert it for comparison displays/sorting.
                if rule == "overall_rank":
                    return -_as_num(val, 999999999)
                return _as_num(val)

    if rule == "overall_rank":
        return -999999999
    return 0


def _first_tb_rule(master, manager_ids, rules, gw=None, cup_stats_by_mid=None):
    """Return the first rule that separates a tied group, otherwise None."""
    mids = [str(m) for m in manager_ids]
    if len(mids) < 2:
        return None

    for rule in rules:
        vals = []
        for mid in mids:
            cup_stats = (cup_stats_by_mid or {}).get(str(mid))
            vals.append(_rule_value(master, mid, rule, gw=gw, cup_stats=cup_stats))
        if len(set(vals)) > 1:
            return rule
    return None




def _tb_sort_key(master, mid, rules, gw=None, cup_stats=None, primary_value=None):
    """Build an official competition sort key. All returned values are high-is-better.

    primary_value can be supplied for competitions such as Block where the main
    points value is not one of the standard rule fields. The remaining rules are
    appended in the order defined in RULES_REFERENCE.
    """
    vals = []
    if primary_value is not None:
        vals.append(_as_num(primary_value))
    vals.extend(
        _rule_value(master, mid, rule, gw=gw, cup_stats=cup_stats)
        for rule in rules
    )
    return tuple(vals)


def _sort_by_official_tiebreakers(items, key_fn, reverse=True):
    """Stable wrapper for official high-is-better tiebreak ordering."""
    return sorted(items, key=key_fn, reverse=reverse)

def _tb_badge(rule):
    if not rule:
        return ""
    label = TB_LABELS.get(rule, "TB")
    detail = TB_DETAILS.get(rule, rule.replace("_", " "))
    return f'<span class="hub-tb-badge" title="Tiebreaker: {detail}">{label}</span>'

def _compact_number(value):
    value = int(value)

    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}m"

    if value >= 10_000:
        return f"{value / 1_000:.1f}k"

    return str(value)

def _tb_value_display(master, mid, rule, gw=None, cup_stats=None):
    if not rule:
        return ""

    raw_value = _rule_value(master, mid, rule, gw=gw, cup_stats=cup_stats)

    # _rule_value inverts overall_rank for sorting, so flip it back for display.
    if rule == "overall_rank":
        raw_value = abs(raw_value)

    label = TB_LABELS.get(rule, "TB").replace("TB ", "")
    value = _compact_number(raw_value) if float(raw_value).is_integer() else raw_value

    return (
        f'<span class="hub-tb-inline" title="{TB_DETAILS.get(rule, rule)}">'
        f'{label} {value}'
        f'</span>'
    )


def _tie_groups_by_value(items, value_key):
    groups = defaultdict(list)
    for item in items:
        groups[item.get(value_key)].append(item)
    return {k: v for k, v in groups.items() if len(v) > 1}



def _current_block_label(master, current_gw):
    blocks = master.get('competitions', {}).get('blocks', {})
    for bname, bdata in blocks.items():
        gws = bdata.get('gws', []) or []
        if current_gw in gws:
            return bname, gws
    return None, []


def _live_status_html(master, current_gw):
    comp = master.get('competitions', {}) or {}
    lms = comp.get('lms', {}) or {}
    cup = comp.get('cup', {}) or {}

    block_name, block_gws = _current_block_label(master, current_gw)
    block_live = bool(block_name)

    lms_schedule = sorted(set(lms.get('schedule', []) or []))
    lms_final = lms.get('final_gw')
    lms_live = current_gw in lms_schedule
    next_lms = next((gw for gw in lms_schedule if gw > current_gw), None)
    alive_count = len(lms.get("active_ids", []) or [])

    if lms_final == current_gw:
        lms_title = 'Final week'
        lms_sub = f'{alive_count} alive'
        lms_class = 'live'
    elif lms_live:
        lms_title = 'Elimination week'
        lms_sub = f'{alive_count} alive'
        lms_class = 'warn'
    else:
        lms_title = 'No elimination'
        lms_sub = f'Next GW{next_lms} · {alive_count} alive' if next_lms else f'{alive_count} alive · no scheduled GW'
        lms_class = 'idle'

    group_gws = cup.get('group_stage_gws', []) or []
    knockout_gws = cup.get('knockout_gws', []) or []
    playoff_gw = cup.get('playoff_gw')
    if current_gw in group_gws:
        cup_title = 'Group matchday'
        cup_sub = f'GW{current_gw}'
        cup_class = 'live'
    elif playoff_gw and current_gw == playoff_gw:
        cup_title = 'Playoff week'
        cup_sub = f'GW{current_gw}'
        cup_class = 'live'
    elif current_gw in knockout_gws:
        cup_title = 'Knockout tie'
        cup_sub = f'GW{current_gw}'
        cup_class = 'live'
    else:
        cup_title = 'Cup idle'
        next_cup = next((gw for gw in sorted(set(group_gws + knockout_gws + ([playoff_gw] if playoff_gw else []))) if gw > current_gw), None)
        cup_sub = f'Next GW{next_cup}' if next_cup else 'No scheduled GW'
        cup_class = 'idle'

    block_sub = f'Active · GWs {block_gws[0]}–{block_gws[-1]}' if block_gws else 'Between blocks'

    cards = [
        ('Gameweek', f'GW{current_gw}', f'<a class="hub-live-link" href="gw_{current_gw}_poster.html">↗ Open debrief</a>', 'live'),
        ('Block', block_name or 'No active block', block_sub, 'live' if block_live else 'quiet'),
        ('LMS', lms_title, lms_sub, lms_class),
        ('Cup', cup_title, cup_sub, cup_class),
    ]

    html = ''.join(
        f'<div class="hub-live-card {cls}">'
        f'<div class="hub-live-kicker">{label}</div>'
        f'<div class="hub-live-title">{title}</div>'
        f'<div class="hub-live-sub">{sub}</div>'
        f'</div>'
        for label, title, sub, cls in cards
    )
    return f'<div class="hub-live-grid">{html}</div>'

def _div_tables_html(master, gw_results=None, gameweek=None):
    gw_results = gw_results or {}

    rows = ""

    for div in DIVISION_ORDER:
        icon = DIV_ICONS[div]
        standings = master['divisions'][div].get('standings', {})

        rows += (
            f'<tr class="hub-division-spacer-row">'
            f'<td colspan="7"></td>'
            f'</tr>'

            f'<tr class="hub-division-title-row">'
            f'<td colspan="7" class="hub-division-title-cell"><span class="hub-division-title-inner"><span class="hub-division-icon">{icon}</span><span>{div}</span></span></td>'
            f'</tr>'

            f'<tr class="hub-division-header-row">'
            f'<th class="hub-rank-head">Rank</th>'
            f'<th class="hub-manager-head">Manager</th>'
            f'<th class="hub-captain-head">Captain</th>'
            f'<th class="hub-number-head">GW</th>'
            f'<th class="hub-number-head hub-total-head">Total</th>'
            f'<th class="hub-status-head">LMS</th>'
            f'<th class="hub-status-head">Cup</th>'
            f'</tr>'
        )

        # Sort displayed division standings using the official division tiebreaker order,
        # rather than trusting stored/insertion order. This keeps the visual table aligned
        # with the reason shown by the TB badge.
        div_entries = []
        for _, e in sorted(standings.items(), key=lambda x: int(x[0])):
            mid = str(e.get("manager_id"))
            mdata = _manager(master, mid)
            total = e.get("total_points", mdata.get("stats", {}).get("total_points", 0))
            div_entries.append({"entry": e, "manager_id": mid, "total": total})

        div_entries = _sort_by_official_tiebreakers(
            div_entries,
            key_fn=lambda x: _tb_sort_key(
                master,
                x["manager_id"],
                RULES_REFERENCE["division_tiebreakers"],
            ),
        )

        current_positions, previous_positions = _division_movement_maps(
            master,
            div,
            div_entries,
            gameweek,
        )

        for pos, item in enumerate(div_entries, 1):
            e = item["entry"]
            mid = item["manager_id"]

            m = master['managers'].get(mid, {})
            gw = gw_results.get(mid, {})

            captain_name = gw.get("captain_name", "—")
            captain_pts = gw.get("captain_points", 0)
            captain = f"{captain_name} ({captain_pts})" if captain_name != "—" else "—"

            gw_score = gw.get("net_gw_points", "—")
            total = item["total"]
            movement_html = _division_movement_html(
                current_positions.get(mid, pos),
                previous_positions.get(mid),
            )

            lms_icon = "✅" if m.get('stats', {}).get('lms_alive') else "🧟"
            cup_icon = _cup_status_icon(master, mid, gameweek or 0)
            
            manager_html = f'<span class="hub-manager-name">{e["name"]}</span>'

            promo_rel_places = master.get('promotion_relegation', {}).get('places', 2)
            division_size = len(div_entries)
            row_classes = []
            if pos <= promo_rel_places:
                row_classes.append('hub-row-promotion')
            if div != 'League Two' and pos > division_size - promo_rel_places:
                row_classes.append('hub-row-relegation')
            row_class_attr = f' class="{" ".join(row_classes)}"' if row_classes else ''

            rows += (
                f'<tr{row_class_attr}>'
                f'<td class="hub-rank-cell"><span class="hub-rank-wrap"><span class="hub-rank-number">{pos}</span>{movement_html}</span></td>'
                f'<td class="hub-manager-cell">{manager_html}</td>'
                f'<td class="hub-captain-cell">{captain}</td>'
                f'<td class="hub-number-cell hub-gw-cell">{gw_score}</td>'
                f'<td class="hub-number-cell hub-total-cell">{total}</td>'
                f'<td class="hub-status-cell">{lms_icon}</td>'
                f'<td class="hub-status-cell">{cup_icon}</td>'
                f'</tr>'
            )

    return (
        f'<div class="hub-divisions-scroll">'
        f'<table class="hub-div-table">'
        f'<colgroup>'
        f'<col class="hub-col-rank">'
        f'<col class="hub-col-manager">'
        f'<col class="hub-col-captain">'
        f'<col class="hub-col-gw">'
        f'<col class="hub-col-total">'
        f'<col class="hub-col-lms">'
        f'<col class="hub-col-cup">'
        f'</colgroup>'
        f'<tbody>'
        f'{rows}'
        f'</tbody>'
        f'</table>'
        f'</div>'
    )


def _lms_html(master):
    lms = master.get('competitions', {}).get('lms', {}) or {}
    mgrs = master.get('managers', {}) or {}

    def _manager_record(mid):
        return mgrs.get(str(mid), mgrs.get(mid, {})) or {}

    def _manager_name_local(mid):
        rec = _manager_record(mid)
        return rec.get('name', str(mid)) if rec else str(mid)

    def _gw_score(mid, gw):
        row = _gw_row(_manager_record(mid), gw)
        return row.get('net_gw_points', row.get('gw_points', row.get('points')))

    def _lms_sort_key(mid, gw):
        return _tb_sort_key(master, mid, RULES_REFERENCE['lms_tiebreakers'], gw=gw)

    active_names = sorted(
        [_manager_name_local(mid) for mid in lms.get('active_ids', []) if str(mid) in mgrs or mid in mgrs],
        key=lambda n: n.lower()
    )
    active_count = len(active_names)

    active_text = ''.join(f'<span class="hub-lms-pill">{name}</span>' for name in active_names) if active_names else '<span class="hub-lms-muted">No managers still alive</span>'

    elim_items = sorted((lms.get('eliminated', {}) or {}).items(), key=lambda x: int(x[0]))
    eliminated_count = len(elim_items)
    name_to_mid = {mdata.get('name'): str(mid) for mid, mdata in mgrs.items()}

    alive_ids = set(str(mid) for mid in mgrs.keys())
    elim_h = ''

    for g, name in elim_items:
        gw = int(g)
        eliminated_mid = name_to_mid.get(name)
        score = _gw_score(eliminated_mid, gw) if eliminated_mid else None
        score_html = f'<span class="hub-lms-score">{score} pts</span>' if score is not None else '<span class="hub-lms-score muted">—</span>'

        escaped_html = ''
        if eliminated_mid and eliminated_mid in alive_ids:
            remaining_ids = [mid for mid in alive_ids if mid != eliminated_mid and _gw_score(mid, gw) is not None]
            if remaining_ids:
                escaped_mid = sorted(remaining_ids, key=lambda mid: _lms_sort_key(mid, gw))[0]
                escaped_score = _gw_score(escaped_mid, gw)
                margin = None
                if escaped_score is not None and score is not None:
                    margin = _as_num(escaped_score) - _as_num(score)
                    margin = int(margin) if float(margin).is_integer() else margin
                margin_html = f' · survived by {margin} pt(s)' if margin is not None else ''
                escaped_html = (
                    f'<div class="hub-lms-escaped">'
                    f'<span>🛟 Scraped through: <strong>{_manager_name_local(escaped_mid)}</strong></span>'
                    f'<span>{escaped_score} pts{margin_html}</span>'
                    f'</div>'
                )
            alive_ids.remove(eliminated_mid)

        tb_html = ''
        if score is not None:
            tied_ids = []
            for mid in mgrs.keys():
                row_score = _gw_score(mid, gw)
                if row_score is not None and _as_num(row_score) == _as_num(score):
                    tied_ids.append(str(mid))
            if len(tied_ids) > 1:
                rule = _first_tb_rule(master, tied_ids, RULES_REFERENCE['lms_tiebreakers'], gw=gw)
                tb_html = _tb_badge(rule) or '<span class="hub-tb-badge">TB LEVEL</span>'

        name_html = f'<span>{name}</span>{tb_html}' if tb_html else name
        elim_h += (
            f'<div class="hub-lms-elim-wrap">'
            f'<div class="hub-lms-elim-row">'
            f'<span class="hub-lms-gw">GW{g}</span>'
            f'<span class="hub-lms-zombie">🧟</span>'
            f'<span class="hub-lms-name">{name_html}</span>'
            f'{score_html}'
            f'</div>'
            f'{escaped_html}'
            f'</div>'
        )

    if not elim_h:
        elim_h = '<div class="hub-lms-muted">No eliminations yet</div>'

    winner_html = ''
    if lms.get('winner_name'):
        runner = lms.get('runner_up_name') or '—'
        winner_html = (
            f'<div class="hub-lms-box hub-lms-winner-box">'
            f'<div class="hub-lms-label">Winner</div>'
            f'<div class="hub-lms-active">🏆 {lms.get("winner_name")}</div>'
            f'<div class="hub-lms-muted">Runner-up: {runner}</div>'
            f'</div>'
        )

    return (
        f'{winner_html}'
        f'<div class="hub-lms-count-grid">'
        f'<div class="hub-lms-count-card"><div class="hub-lms-count-number">{active_count}</div><div class="hub-lms-count-label">Still alive</div></div>'
        f'<div class="hub-lms-count-card"><div class="hub-lms-count-number muted-count">{eliminated_count}</div><div class="hub-lms-count-label">Eliminated</div></div>'
        f'</div>'
        f'<div class="hub-lms-box"><div class="hub-lms-label">Still alive</div><div class="hub-lms-pill-wrap">{active_text}</div></div>'
        f'<div class="hub-lms-history"><div class="hub-lms-label">Elimination history</div>{elim_h}</div>'
    )


def _cup_html(master, current_gw=None):
    cup  = master.get('competitions', {}).get('cup', {}) or {}
    mgrs = master.get('managers', {}) or {}
    current_gw = current_gw or master.get('league_metadata', {}).get('last_processed_gw', 0) or 0

    def _cup_sort_key(item):
        mid, cs = item["manager_id"], item["cup_stats"]
        return tuple(_rule_value(master, mid, rule, cup_stats=cs) for rule in RULES_REFERENCE["cup_group_tiebreakers"])

    auto_qualify = cup.get('auto_qualify', cup.get('auto_qualifiers_per_group', '—'))
    playoff_spots = cup.get('playoff_spots', cup.get('playoff_count', 0))
    group_gws = cup.get('group_stage_gws', []) or []
    knockout_gws = cup.get('knockout_gws', []) or []

    overview = (
        f'<div class="hub-cup-overview">'
        f'<div class="hub-cup-stat"><div class="hub-cup-stat-value">{len(cup.get("groups", {}) or {})}</div><div class="hub-cup-stat-label">Groups</div></div>'
        f'<div class="hub-cup-stat"><div class="hub-cup-stat-value">{auto_qualify}</div><div class="hub-cup-stat-label">Auto Q</div></div>'
        f'<div class="hub-cup-stat"><div class="hub-cup-stat-value">{playoff_spots}</div><div class="hub-cup-stat-label">Playoff</div></div>'
        f'<div class="hub-cup-stat"><div class="hub-cup-stat-value">{len(knockout_gws)}</div><div class="hub-cup-stat-label">KO GWs</div></div>'
        f'</div>'
    )

    groups_html = ""
    for grp, members in (cup.get('groups', {}) or {}).items():
        rows = ""
        group_items = []
        for mid in members:
            m = mgrs.get(str(mid), mgrs.get(mid, {})) or {}
            cs = m.get('cup_stats', {}) or {}
            group_items.append({
                "manager_id": str(mid),
                "name": m.get("name", str(mid)),
                "cup_stats": cs,
                "match_points": cs.get("match_points", cs.get("group_points", 0)),
            })

        group_items = sorted(group_items, key=_cup_sort_key, reverse=True)

        for item in group_items:
            cs = item["cup_stats"]
            q = '<span style="font-size:10px;background:#eaf3de;color:#3b6d11;padding:2px 6px;border-radius:999px;font-weight:700">Q</span>' if cs.get('qualified') else ''
            rows += (
                f'<tr>'
                f'<td class="mname"><span class="hub-cup-name">{item["name"]}</span></td>'
                f'<td class="num">{item["match_points"]}</td>'
                f'<td class="num">{cs.get("cup_fpl_points_sum",0)}</td>'
                f'<td class="cen">{q}</td>'
                f'</tr>'
            )

        groups_html += (
            f'<div class="hub-cup-group">'
            f'<div class="hub-cup-group-title">{grp}</div>'
            f'<table><tr><th>Manager</th><th>Pts</th><th>FPL</th><th>Q</th></tr>{rows}</table>'
            f'</div>'
        )

    if not groups_html:
        groups_html = '<div class="hub-cup-empty">No cup groups have been configured yet.</div>'

    fixtures = cup.get('fixtures', []) or []
    upcoming = []
    for fx in fixtures:
        gw = fx.get('gw') or fx.get('gameweek') or fx.get('event')
        if gw is None:
            continue
        try:
            gw_int = int(gw)
        except (TypeError, ValueError):
            continue
        if gw_int >= int(current_gw or 0):
            label = str(fx.get('round') or fx.get('group') or 'Cup fixture')
            if 'group' in label.lower() or fx.get('group'):
                upcoming.append((gw_int, fx))

    upcoming = sorted(upcoming, key=lambda x: (x[0], str(x[1].get('group', '')), str(x[1].get('home', ''))))[:12]
    by_gw = defaultdict(list)
    for gw, fx in upcoming:
        by_gw[gw].append(fx)

    fixtures_html = ""
    for gw in sorted(by_gw.keys()):
        rows = ""
        for fx in by_gw[gw]:
            home = _manager_name(master, fx.get('home')) if str(fx.get('home', '')).isdigit() else fx.get('home_name', fx.get('home', '—'))
            away = _manager_name(master, fx.get('away')) if str(fx.get('away', '')).isdigit() else fx.get('away_name', fx.get('away', '—'))
            rows += (
                f'<div class="hub-cup-fixture-row">'
                f'<span class="hub-cup-side">{home}</span>'
                f'<span class="hub-cup-vs">v</span>'
                f'<span class="hub-cup-side away">{away}</span>'
                f'</div>'
            )
        fixtures_html += (
            f'<div class="hub-cup-fixture-card">'
            f'<div class="hub-cup-fixture-gw">GW{gw}</div>'
            f'{rows}'
            f'</div>'
        )
    if not fixtures_html:
        fixtures_html = '<div class="hub-cup-empty">No upcoming group fixtures found.</div>'

    bracket_html = _cup_bracket_html(master, current_gw)

    return (
        f'{overview}'
        f'<div class="section-label">Group standings</div>'
        f'{groups_html}'
        f'<div class="section-label" style="margin-top:14px">Upcoming fixtures</div>'
        f'{fixtures_html}'
        f'<div class="section-label" style="margin-top:14px">Knockout bracket</div>'
        f'{bracket_html}'
    )


def _cup_bracket_html(master, current_gw=None):
    cup = master.get('competitions', {}).get('cup', {}) or {}
    fixtures = cup.get('fixtures', []) or []
    bracket = cup.get('knockout_bracket', {}) or {}
    results = cup.get('knockout_results', {}) or {}

    items = []
    for fx in fixtures:
        label = str(fx.get('round') or '')
        gw = fx.get('gw') or fx.get('gameweek') or fx.get('event')
        if label and 'group' not in label.lower():
            items.append((label, gw, fx))

    # Fallback for bracket dictionaries/lists.
    if not items and bracket:
        if isinstance(bracket, dict):
            for label, ties in bracket.items():
                if isinstance(ties, dict):
                    iterable = ties.values()
                else:
                    iterable = ties or []
                for fx in iterable:
                    if isinstance(fx, dict):
                        items.append((fx.get('round', label), fx.get('gw'), fx))
        elif isinstance(bracket, list):
            for fx in bracket:
                if isinstance(fx, dict):
                    items.append((fx.get('round', 'Knockout'), fx.get('gw'), fx))

    if not items:
        return '<div class="hub-cup-empty">The knockout bracket will appear once qualifiers are confirmed.</div>'

    by_round = defaultdict(list)
    for label, gw, fx in items:
        by_round[label or 'Knockout'].append((gw, fx))

    def _team_label(value, fallback='TBC'):
        if value in (None, '', '—'):
            return fallback
        return _manager_name(master, value) if str(value).isdigit() else str(value)

    html = ''
    for label in sorted(by_round.keys()):
        rows = ''
        for gw, fx in sorted(by_round[label], key=lambda x: (x[0] or 99, str(x[1].get('tie_id', '')))):
            home = _team_label(fx.get('home'), fx.get('home_name', 'TBC'))
            away = _team_label(fx.get('away'), fx.get('away_name', 'TBC'))
            hs = fx.get('home_score')
            aw = fx.get('away_score')
            score = f'{hs}–{aw}' if hs is not None and aw is not None else (f'GW{gw}' if gw else 'v')
            rows += (
                f'<div class="hub-bracket-row">'
                f'<span class="hub-bracket-team">{home}</span>'
                f'<span class="hub-bracket-score">{score}</span>'
                f'<span class="hub-bracket-team away">{away}</span>'
                f'</div>'
            )
        html += (
            f'<div class="hub-bracket-round">'
            f'<div class="hub-bracket-title">{label}</div>'
            f'{rows}'
            f'</div>'
        )
    return html


def _blocks_html(master, current_gw):
    blocks = master.get('competitions', {}).get('blocks', {})
    managers = master.get('managers', {})
    out = ""

    def _block_points_for_manager(mdata, bname, gws):
        block_stats = mdata.get('block_stats', {})

        if block_stats.get('current_block_points') is not None:
            return block_stats.get('current_block_points', 0)

        if isinstance(block_stats.get(bname), dict):
            b = block_stats.get(bname, {})
            return b.get('points', b.get('total_points', 0))

        total = 0
        history = mdata.get('gw_history', {})
        for gw in gws:
            row = history.get(str(gw), history.get(gw, {}))
            total += row.get('net_gw_points', row.get('points', row.get('gw_points', 0)))
        return total

    for bname, bdata in blocks.items():
        won = bdata.get('winner_name')
        gws = bdata.get('gws', [])

        start_gw = gws[0] if gws else "?"
        end_gw = gws[-1] if gws else "?"

        is_live = bool(not won and gws and start_gw <= current_gw <= end_gw)
        is_upcoming = bool(not won and gws and current_gw < start_gw)

        status = "Complete" if won else ("Live" if is_live else "Upcoming")
        status_class = "complete" if won else ("live" if is_live else "upcoming")

        top3 = []
        standings = bdata.get("standings", {})

        name_to_mid = {mdata.get("name"): str(mid) for mid, mdata in managers.items()}

        if standings:
            if isinstance(standings, dict):
                for pos in sorted(standings.keys(), key=lambda x: int(x)):
                    top3.append(standings[pos])
            elif isinstance(standings, list):
                top3 = standings

            for e in top3:
                if not e.get("manager_id") and e.get("name") in name_to_mid:
                    e["manager_id"] = name_to_mid[e.get("name")]

            # Stored block standings can arrive in old order, so re-sort them here
            # using block points first, then the official season tiebreakers.
            top3 = _sort_by_official_tiebreakers(
                top3,
                key_fn=lambda x: _tb_sort_key(
                    master,
                    x.get("manager_id", ""),
                    RULES_REFERENCE["block_tiebreakers"],
                    primary_value=x.get("points", x.get("total_points", 0)),
                ),
            )

        elif is_live:
            derived = []
            for mid, mdata in managers.items():
                pts = _block_points_for_manager(mdata, bname, gws)
                derived.append({"manager_id": str(mid), "name": mdata.get("name", str(mid)), "points": pts})

            top3 = _sort_by_official_tiebreakers(
                derived,
                key_fn=lambda x: _tb_sort_key(
                    master,
                    x.get("manager_id", ""),
                    RULES_REFERENCE["block_tiebreakers"],
                    primary_value=x.get("points", 0),
                ),
            )

        for e in top3:
            if not e.get("manager_id") and e.get("name") in name_to_mid:
                e["manager_id"] = name_to_mid[e.get("name")]

        leader_points = top3[0].get("points", top3[0].get("total_points", 0)) if top3 else 0
        rows = ""
        medals = ["🥇", "🥈", "🥉"]

        for i, e in enumerate(top3[:3]):
            name = e.get("name", "—")
            points = e.get("points", e.get("total_points", 0))
            mid = str(e.get("manager_id", ""))

            if won:
                gap_html = ""
            elif i == 0:
                gap_html = '<div class="hub-block-gap">leader</div>'
            else:
                gap = leader_points - points
                gap_html = f'<div class="hub-block-gap">{gap} behind</div>'

            name_html = f'<span>{name}</span>'

            rows += (
                f'<div class="hub-block-row">'
                f'<span class="hub-block-medal">{medals[i]}</span>'
                f'<span class="hub-block-name">{name_html}</span>'
                f'<span class="hub-block-score-wrap">'
                f'<span class="hub-block-points">{points}</span>'
                f'{gap_html}'
                f'</span>'
                f'</div>'
            )

        if won:
            body = (
                f'<div class="hub-block-winner">'
                f'<span>🏅 Winner</span>'
                f'<strong>{won}</strong>'
                f'</div>'
            )
            if rows:
                body = f'<div class="hub-block-standings">{rows}</div>{body}'
        elif rows:
            body = f'<div class="hub-block-standings">{rows}</div>'
        elif is_upcoming:
            body = '<div class="hub-block-muted">Block has not started yet</div>'
        else:
            body = '<div class="hub-block-muted">No block standings available yet</div>'

        out += (
            f'<div class="hub-block-card">'
            f'<div class="hub-block-head">'
            f'<div>'
            f'<div class="hub-block-title">{bname}</div>'
            f'<div class="hub-block-gws">GWs {start_gw}–{end_gw}</div>'
            f'</div>'
            f'<div class="hub-block-status {status_class}">{status}</div>'
            f'</div>'
            f'{body}'
            f'</div>'
        )

    return out


def _metric_value(manager, metric):
    """Read an accolade/chip metric from the most likely stored locations."""
    season = manager.get('season_totals', {}) or {}
    stats = manager.get('stats', {}) or {}

    if metric == "cards_total":
        return season.get('cards_total', season.get('yellow_cards', 0) + season.get('red_cards', 0))

    for source in (season, stats, manager, manager.get('accolades', {}) or {}):
        if metric in source:
            return source.get(metric, 0) or 0

    return 0


def _format_acc_value(value):
    """Keep accolade numbers compact while preserving negatives for transfer/chip-style metrics."""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return value


def _award_rankings(master, award):
    """Return the top three accolade value bands. Ties are shared, not broken."""
    managers = master.get('managers', {})
    metric = award.get('metric') if isinstance(award, dict) else None

    if metric:
        by_value = defaultdict(list)

        for mid, manager in managers.items():
            name = manager.get('name', '—')
            value = _metric_value(manager, metric)
            by_value[value].append({
                "manager_id": str(mid),
                "name": name,
                "value": value,
            })

        rankings = []
        medals = ["🥇", "🥈", "🥉"]

        for i, value in enumerate(sorted(by_value.keys(), reverse=True)[:3]):
            group = sorted(by_value[value], key=lambda r: r.get("name", "").lower())
            names = [r.get("name", "—") for r in group]
            rankings.append({
                "rank": i + 1,
                "medal": medals[i],
                "names": names,
                "name": ", ".join(names),
                "value": value,
                "joint_count": len(group),
            })

        return rankings

    # Fallback for older stored accolade shape with a single winner only.
    stored_name = award.get('manager_name') if isinstance(award, dict) else None
    stored_value = award.get('value', 0) if isinstance(award, dict) else 0

    if stored_name and stored_name not in ("None", "—"):
        return [{
            "rank": 1,
            "medal": "🥇",
            "names": [stored_name],
            "name": stored_name,
            "value": stored_value or 0,
            "joint_count": 1,
        }]

    return []


def _award_rows_from_defs(master, award_defs, icon):
    medals = ["🥇", "🥈", "🥉"]
    rows = ""

    for award_name, award in award_defs.items():
        rankings = _award_rankings(master, award)

        if rankings:
            rank_rows = ""
            for i, entry in enumerate(rankings[:3]):
                value = _format_acc_value(entry.get("value", 0))
                joint_count = entry.get("joint_count", 1)
                joint_html = (
                    f'<span class="hub-acc-tie">Joint x{joint_count}</span>'
                    if joint_count > 1
                    else ""
                )

                rank_rows += (
                    f'<div class="hub-acc-rank-row">'
                    f'<span class="hub-acc-medal">{entry.get("medal", medals[i])}</span>'
                    f'<span class="hub-acc-manager">{entry.get("name", "—")}</span>'
                    f'<span class="hub-acc-value-wrap">'
                    f'<span class="hub-acc-value">{value}</span>'
                    f'{joint_html}'
                    f'</span>'
                    f'</div>'
                )
        else:
            rank_rows = '<div class="hub-acc-empty">No data available yet</div>'

        rows += (
            f'<div class="hub-acc-card">'
            f'<div class="hub-acc-title">'
            f'<span>{icon}</span>'
            f'<span>{award_name}</span>'
            f'</div>'
            f'<div class="hub-acc-ranks">{rank_rows}</div>'
            f'</div>'
        )

    if not rows:
        rows = '<div class="muted" style="font-size:13px">No accolade data available yet</div>'

    return rows


def _accolades_html(master):
    accolades = master.get('accolades', {}) or {}
    prizes = dict(accolades.get('prizes', {}) or {})
    fun_acc = dict(accolades.get('fun', {}) or {})

    # Extra derived season-long races. These read from season_totals/stats via _metric_value.
    extra_prizes = {
        'Highest GW Score': {'metric': 'highest_gw_score'},
        'Best Captain Haul': {'metric': 'best_captain_score'},
        'Best Auto-Sub': {'metric': 'best_autosub_score'},
    }
    extra_fun = {
        'Bench Warmer': {'metric': 'bench_points_total'},
        'Differential King': {'metric': 'differential_points'},
        'Chip Master': {'metric': 'chip_total_score'},
    }

    # Populate chip_total_score dynamically so it can be ranked like other metrics.
    for _, manager in (master.get('managers', {}) or {}).items():
        chip_stats = manager.get('chip_stats', {}) or manager.get('chips', {}) or {}
        manager['chip_total_score'] = chip_stats.get('total_score', sum((e.get('score', 0) or 0) for e in chip_stats.get('events', []) or []))

    prize_defs = {**prizes, **extra_prizes}
    fun_defs = {**fun_acc, **extra_fun}

    prize_h = _award_rows_from_defs(master, prize_defs, '🏆')
    fun_h = _award_rows_from_defs(master, fun_defs, '🎭')
    return prize_h, fun_h


def _chip_leaderboard_html(master, gw_results=None):
    """Season chip leaderboard with chip-use pills, best/worst events and totals."""
    gw_results = gw_results or {}
    managers = master.get('managers', {}) or {}

    def _chip_pills_from_events(events, chips_played):
        clean_events = []
        if events:
            clean_events = sorted(events, key=lambda e: (e.get('gw') is None, e.get('gw') or 999, str(e.get('chip', ''))))
        elif isinstance(chips_played, dict):
            for chip_name, count in sorted(chips_played.items(), key=lambda x: str(x[0]).lower()):
                for _ in range(count or 0):
                    clean_events.append({'chip': chip_name, 'gw': None, 'score': None})

        seen = defaultdict(int)
        pills = ''
        for ev in clean_events:
            chip_name = ev.get('chip', 'Chip') or 'Chip'
            seen[chip_name] += 1
            chip_no = seen[chip_name]
            gw = ev.get('gw')
            score = ev.get('score')
            meta_bits = []
            if gw not in (None, '', '—'):
                meta_bits.append(f'GW{gw}')
            if score not in (None, ''):
                score_display = f'+{score}' if score > 0 else str(score)
                meta_bits.append(score_display)
            meta = f'<span class="hub-chip-pill-meta">{" · ".join(meta_bits)}</span>' if meta_bits else ''
            pills += f'<span class="hub-chip-pill"><span class="hub-chip-pill-name">{chip_name} #{chip_no}</span>{meta}</span>'
        return pills, clean_events

    entries = []
    for mid, manager in managers.items():
        chip_stats = manager.get('chip_stats', {}) or manager.get('chips', {}) or {}
        total_score = chip_stats.get('total_score')
        chips_played = chip_stats.get('chips_played', {}) or {}
        events = list(chip_stats.get('events', []) or [])

        if total_score is None:
            total_score = sum((e.get('score', 0) or 0) for e in events)

        gw = gw_results.get(str(mid), {}) or gw_results.get(mid, {}) or {}
        chip_used = gw.get('chip_used', 'None')
        if chip_used not in ('None', 'none', '', None) and not events and not chips_played:
            score = gw.get('chip_score', 0) or 0
            total_score = score
            chips_played = {chip_used: 1}
            events = [{'gw': gw.get('gameweek'), 'chip': chip_used, 'score': score}]

        chips_count = sum(chips_played.values()) if isinstance(chips_played, dict) else len(events)
        if chips_count or total_score:
            chip_pills, clean_events = _chip_pills_from_events(events, chips_played)
            scored_events = [e for e in clean_events if e.get('score') not in (None, '')]
            best = max(scored_events, key=lambda e: e.get('score', 0), default=None)
            worst = min(scored_events, key=lambda e: e.get('score', 0), default=None)
            avg = round((total_score or 0) / chips_count, 1) if chips_count else 0
            entries.append({
                'name': manager.get('name', '—'),
                'total_score': total_score or 0,
                'chips_count': chips_count,
                'chips_used_label': f'{chips_count}/8 used',
                'chip_pills': chip_pills,
                'best': best,
                'worst': worst,
                'avg': avg,
            })

    entries = sorted(entries, key=lambda x: (x['total_score'], x['chips_count'], x['name']), reverse=True)
    if not entries:
        return '<div class="hub-chip-empty">No chip leaderboard data available yet. Once chip usage is stored in the master file, rankings will appear here.</div>'

    rows = ''
    for pos, entry in enumerate(entries, 1):
        score = entry['total_score']
        score_display = f'+{score}' if score > 0 else str(score)
        score_class = 'good' if score > 0 else ('bad' if score < 0 else 'neutral')
        chip_pills = entry['chip_pills'] or '<span class="hub-chip-none">No chips logged</span>'

        def _event_summary(ev, label):
            if not ev:
                return ''
            chip = ev.get('chip', 'Chip')
            gw = ev.get('gw')
            score = ev.get('score', 0)
            display = f'+{score}' if score > 0 else str(score)
            cls = 'good' if score > 0 else ('bad' if score < 0 else 'neutral')
            gw_part = f' GW{gw}' if gw not in (None, '', '—') else ''
            return f'<span class="hub-chip-event {cls}">{label}: {chip}{gw_part} {display}</span>'

        rows += (
            f'<div class="hub-chip-row">'
            f'<div class="hub-chip-rank">#{pos}</div>'
            f'<div class="hub-chip-main">'
            f'<div class="hub-chip-manager-line"><span class="hub-chip-manager">{entry["name"]}</span><span class="hub-chip-used">{entry["chips_used_label"]} · avg {entry["avg"]}</span></div>'
            f'<div class="hub-chip-pills">{chip_pills}</div>'
            f'<div class="hub-chip-events">{_event_summary(entry["best"], "Best")}{_event_summary(entry["worst"], "Worst")}</div>'
            f'</div>'
            f'<div class="hub-chip-score {score_class}">{score_display}</div>'
            f'</div>'
        )

    return f'<div class="hub-chip-leaderboard"><div class="hub-chip-head"><span>Rank</span><span>Manager & chips</span><span>Score</span></div>{rows}</div>'


# ─────────────────────────────────────────────────────────────────────────────
# GW POSTER
# ─────────────────────────────────────────────────────────────────────────────

def _html_lines(lines, class_name="stack-line"):
    """Render a list of strings as stacked HTML divs."""
    if not lines:
        return '<div class="muted">—</div>'

    return "".join(
        f'<div class="{class_name}">{line}</div>'
        for line in lines
    )


def _label_value_row(label, value_html):
    """Reusable two-column row: label left, content right."""
    return (
        f'<div class="info-row">'
        f'<span class="info-label">{label}</span>'
        f'<span class="info-value">{value_html}</span>'
        f'</div>'
    )


def _name_lines(names):
    """Render tied manager names one per line."""
    if isinstance(names, list):
        return _html_lines(names, "name-line")
    return str(names)


def build_poster(gameweek, gw_results, master, payload, output_dir="."):
    """Generates the weekly GW debrief poster HTML."""

    sorted_scores = sorted(gw_results.items(),
                           key=lambda x: x[1]['net_gw_points'], reverse=True)

    # Scores table
    scores_rows = ""
    for pos, (mid, s) in enumerate(sorted_scores, 1):
        chip_text = (
            s.get("chip_used", "")
            if s.get("chip_used", "None") not in ("None", "none", "")
            else ""
        )
        hit_text = (
            f'-{s.get("net_transfer_cost", 0)} hit'
            if s.get("net_transfer_cost", 0) > 0
            else ""
        )
        meta_items = [
            f'{s.get("captain_name", "—")} captain ({s.get("captain_points", 0)})'
        ]

        if chip_text:
            meta_items.append(chip_text)
        if hit_text:
            meta_items.append(hit_text)

        diff = s.get("net_gw_points", 0) - payload.get("league_avg", 0)
        diff_display = f"+{diff}" if diff >= 0 else str(diff)
        diff_class = "good" if diff >= 0 else "bad"

        captain_meta = f'{s.get("captain_name", "—")} captain ({s.get("captain_points", 0)})'
        secondary_items = []

        if chip_text:
            secondary_items.append(chip_text)
        if hit_text:
            secondary_items.append(hit_text)

        separator = '<span class="score-meta-sep">•</span>'
        secondary_meta = separator.join(secondary_items)
        secondary_html = (
            f'<div class="score-meta score-meta-extra">{secondary_meta}</div>'
            if secondary_items
            else ''
        )

        scores_rows += (
            f'<div class="score-tile">'
            f'<div class="score-tile-top">'
            f'<div class="score-head-left">'
            f'<span class="score-rank">#{pos}</span>'
            f'<span class="score-points">{s["net_gw_points"]}</span>'
            f'</div>'
            f'<span class="score-diff {diff_class}">{diff_display}</span>'
            f'</div>'

            f'<div class="score-name">{s["name"]}</div>'
            f'<div class="score-meta score-meta-main">{captain_meta}</div>'
            f'{secondary_html}'
            f'</div>'
        )
    
    # Stat grid — dark pop cards matching reference screenshot style
    sl = payload['stat_leaders']
    tr = payload['transfers']

    # Colour palette: green=good, red=bad, cyan=neutral/rank, amber=bonus
    STAT_COLOURS = {
        'green':  '#00ff87',   # goals, def, transfer gain, assists
        'red':    '#ff4d4d',   # faller, cards
        'cyan':   '#00d4ff',   # riser
        'amber':  '#ffc226',   # bonus, bench
    }

    def _pop_stat_card(label, entry, colour, fmt_val=None, icon=''):
      """
      Dark pop-style stat card.
      entry = (value, [names]) or (value, "name")
      """
      val, names = entry
      display_val = fmt_val(val) if fmt_val else str(val)
      names_html = ", ".join(names) if isinstance(names, list) else str(names)

      return (
          f'<div style="background:#1e1e1e;border:0.5px solid rgba(255,255,255,0.08);'
          f'border-radius:12px;padding:14px 12px;display:flex;flex-direction:column;gap:4px">'
          f'<div class="stat-card-header">'
          f'<span class="stat-card-icon">{icon}</span>'
          f'<span class="stat-card-label">{label}</span>'
          f'</div>'
          f'<div style="font-size:26px;font-weight:800;color:{colour};line-height:1.1;'
          f'letter-spacing:-0.5px">{display_val}</div>'
          f'<div style="font-size:11px;color:rgba(255,255,255,0.5);line-height:1.5;margin-top:2px">'
          f'{names_html}</div>'
          f'</div>'
      )

    stat_cards = []

    if sl.get("riser"):
        stat_cards.append(_pop_stat_card("Biggest Riser", sl["riser"], STAT_COLOURS["cyan"], fmt_val=lambda v: f"+{v:,}", icon="📈"))
    if sl.get("faller"):
        stat_cards.append(_pop_stat_card("Biggest Faller", sl["faller"], STAT_COLOURS["red"], fmt_val=lambda v: f"−{v:,}", icon="📉"))

    stat_cards.extend([
        _pop_stat_card("Most Goals",       sl["most_goals"],    STAT_COLOURS["green"],                                icon="⚽"),
        _pop_stat_card("Most Assists",     sl["most_assists"],  STAT_COLOURS["green"],                                icon="🎯"),
        _pop_stat_card("Best Defense",     sl["best_def"],      STAT_COLOURS["green"], fmt_val=lambda v: f"+{v} pts", icon="🛡️"),
        _pop_stat_card("Bonus Points",     sl["most_bonus"],    STAT_COLOURS["green"], fmt_val=lambda v: f"+{v} pts", icon="✨"),
    ])

    stat_grid = "".join(stat_cards)

    # Podium
    medal_icons = ['🥇', '🥈', '🥉']
    podium_html = ""

    for i, p in enumerate(payload['podium']):
      captain_line = f'{p["captain"]} captain ({p["captain_pts"]})'
      extra_items = []

      hero_name = str(p.get('gw_hero') or '')
      captain_name = str(p.get('captain') or '')
      # Safety guard: the newsletter payload should already exclude captain-as-hero,
      # but avoid duplicated podium info if older payloads are rendered.
      hero_base = hero_name.split(' (')[0].strip()

      if hero_name and hero_base != captain_name.strip():
        hero_pts = p.get("gw_hero_pts")
        if hero_pts is not None:
            extra_items.append(f'Hero: {hero_name} ({hero_pts})')
        else:
            extra_items.append(f'Hero: {hero_name}')

      if p.get('chip', 'None') not in ('None', 'none', ''):
          extra_items.append(p["chip"])

      if p.get('hit', 0) > 0:
          extra_items.append(f'-{p["hit"]} hit')

      separator = '<span class="podium-meta-sep">•</span>'
      extra_line = separator.join(extra_items)

      extra_html = (
          f'<div class="podium-meta-extra">{extra_line}</div>'
          if extra_items
          else ''
      )

      podium_html += (
            f'<div class="podium-row podium-rank-{i + 1}">'
            f'<div class="podium-medal">{medal_icons[i]}</div>'
            f'<div class="podium-main">'
            f'<div class="podium-name">{p["name"]}</div>'
            f'<div class="podium-meta">'
            f'<div class="podium-meta-main">{captain_line}</div>'
            f'{extra_html}'
            f'</div>'
            f'</div>'
            f'<div class="podium-score-box">'
            f'<div class="podium-score">{p["net_gw_points"]}</div>'
            f'<div class="podium-score-label">pts</div>'
            f'</div>'
            f'</div>'
        )

    # Squad Data
    strategy_cards = []

    ncp = payload.get("best_non_captained")
    if ncp:
        manager_names = ncp.get("managers", [])
        managers_display = ", ".join(manager_names)
        strategy_cards.append(
            f'<div class="strategy-card">'
            f'<div class="strategy-top">'
            f'<div style="min-width:0;">'
            f'<div class="strategy-kicker">Best non-captain</div>'
            f'<div class="strategy-player">{ncp.get("player", "—")}</div>'
            f'</div>'
            f'<div class="strategy-score">{ncp.get("points", 0)} pts</div>'
            f'</div>'
            f'<div class="strategy-meta">'
            f'Started by {ncp.get("owners", 0)} managers'
            f'</div>'
            f'<div class="strategy-managers">{managers_display}</div>'
            f'</div>'
        )

    sp = payload.get("strategic_pick")
    if sp:
        manager_names = sp.get("managers", [])
        managers_display = ", ".join(manager_names)
        starter_count = sp.get("owners", 0)
        starter_word = "manager" if starter_count == 1 else "managers"

        meta = (
            f'Started by {starter_count} {starter_word} '
            f'({sp.get("ownership_pct", 0)}% of league)'
        )

        strategy_cards.append(
            f'<div class="strategy-card">'
            f'<div class="strategy-top">'
            f'<div style="min-width:0;">'
            f'<div class="strategy-kicker">Best differential</div>'
            f'<div class="strategy-player">{sp.get("player", "—")}</div>'
            f'</div>'
            f'<div class="strategy-score">{sp.get("points", 0)} pts</div>'
            f'</div>'
            f'<div class="strategy-meta">'
            f'<div class="strategy-meta">{meta}</div>'
            f'</div>'
            f'<div class="strategy-managers">{managers_display}</div>'
            f'</div>'
        )

    if strategy_cards:
        strategic_html = f'<div class="strategy-grid">{"".join(strategy_cards)}</div>'
    else:
        strategic_html = (
            f'<div class="lms-box">'
            f'<div class="lms-title">No strategic picks this week</div>'
            f'<div class="lms-sub">No low-owned or non-captained player returned a standout score.</div>'
            f'</div>'
        )

    template_html = ""

    for p in payload.get("league_template", []):
        template_html += (
            f'<div class="template-row">'
            f'<div class="template-player">{p.get("player", "—")}</div>'
            f'<div class="template-meta">'
            f'{p.get("owners", 0)} managers · {p.get("ownership_pct", 0)}%'
            f'</div>'
            f'</div>'
        )

    if not template_html:
      template_html = '<div class="muted" style="font-size:13px">No template data available</div>'

    # LMS event
    lms_event_html = ""
    if payload.get('lms'):
        ev = payload['lms']

        if ev['type'] == 'elimination':
            escaped_html = ""

            if ev.get("escaped"):
              margin = ev.get("survival_margin")

              margin_html = ""
              if margin is not None:
                  margin_html = (
                      f'<div class="lms-escaped-margin">'
                      f'Survived by {margin} pt(s)'
                      f'</div>'
                  )

              escaped_html = (
                  f'<div class="lms-escaped">'
                  f'<div>'
                  f'<div class="lms-escaped-label">Scraped through</div>'
                  f'<div class="lms-escaped-name">{ev["escaped"]["name"]}</div>'
                  f'{margin_html}'
                  f'</div>'
              )

            eliminated_points_html = ""

            if ev.get("eliminated_points") is not None:
                eliminated_points_html = f' · {ev["eliminated_points"]} pts'

            lms_event_html = (
                f'<div class="lms-box">'
                f'<div class="lms-title">🧟 <span class="lms-key danger">{ev["eliminated"]}</span> eliminated</div>'
                f'<div class="lms-sub">{ev["remaining"]} managers remain{eliminated_points_html}</div>'
                f'{escaped_html}'
                f'</div>'
            )

        elif ev['type'] == 'final':
            lms_event_html = (
                f'<div class="lms-box">'
                f'<div class="lms-title">🏆 LMS Winner: <span class="lms-key good">{ev["winner"]}</span></div>'
                f'<div class="lms-sub">Runner-up: {ev["runner_up"]}</div>'
                f'</div>'
            )
    else:
        lms_event_html = (
            f'<div class="lms-box">'
            f'<div class="lms-title">🛡️ No elimination this gameweek</div>'
            f'<div class="lms-sub">Everyone survives to fight another week</div>'
            f'</div>'
        )
    # Transfers
    transfer_reports_html = ""
    def _transfer_pair_rows(ins, outs):
      rows = ""

      for out_p, in_p in zip(outs, ins):
          out_name = out_p.get("name", "—")
          out_pts = out_p.get("points", 0)

          in_name = in_p.get("name", "—")
          in_pts = in_p.get("points", 0)

          move_gain = in_pts - out_pts
          move_gain_display = f"+{move_gain}" if move_gain > 0 else str(move_gain)
          move_gain_class = "good" if move_gain > 0 else ("bad" if move_gain < 0 else "neutral")

          rows += (
              f'<div class="transfer-move-row">'
              f'<div class="transfer-move-from">{out_name} ({out_pts})</div>'
              f'<div class="transfer-move-arrow">→</div>'
              f'<div class="transfer-move-to">{in_name} ({in_pts})</div>'
              f'<div class="transfer-move-gain {move_gain_class}">{move_gain_display}</div>'
              f'</div>'
          )

      if not rows:
          rows = '<div class="muted" style="font-size:12px">No transfers</div>'

      return rows

    def _transfer_story(label, icon, t):
      if not t:
        return ""

      net_gain = t.get("net_gain", 0)
      gross_gain = t.get("gross_gain", 0)
      hit_cost = t.get("cost", 0)
      transfer_count = t.get("transfer_count", 0)

      net_display = f"+{net_gain}" if net_gain > 0 else str(net_gain)
      gross_display = f"+{gross_gain}" if gross_gain > 0 else str(gross_gain)

      net_class = "good" if net_gain > 0 else ("bad" if net_gain < 0 else "neutral")

      transfer_rows = _transfer_pair_rows(
          t.get("ins", []),
          t.get("outs", [])
      )

      if hit_cost > 0:
          summary_text = f'({gross_display} − {hit_cost} = {net_display})'
      else:
          summary_text = f'({gross_display})'

      return (
          f'<div class="transfer-story">'
          f'<div class="transfer-story-top">'
          f'<div class="transfer-story-main">'
          f'<div class="transfer-story-label"><span class="transfer-medal">{icon}</span>{label}</div>'
          f'<div class="transfer-story-manager">{t.get("manager", "—")}</div>'
          f'<div class="transfer-story-sub">{transfer_count} transfer{"s" if transfer_count != 1 else ""}</div>'
          f'</div>'
          f'<div class="transfer-gain {net_class}">{net_display} pts</div>'
          f'</div>'

          f'<div class="transfer-moves">'
          f'{transfer_rows}'
          f'</div>'

          f'<div class="transfer-summary {net_class}">{summary_text}</div>'
          f'</div>'
      )

    def _transfer_market_card(title, icon, items, mode):
      if not items:
          return ""

      rows = ""
      for item in items:
          if mode == "player":
              count = item.get("count", 0)
              managers = item.get("managers", [])
              meta = f'{count} manager{"s" if count != 1 else ""}'
              if managers:
                  meta += f' · {", ".join(managers[:3])}'
              value = f'{item.get("points", 0)} pts'
              value_class = "good" if item.get("points", 0) > 0 else ("bad" if item.get("points", 0) < 0 else "")
              name = item.get("name", "—")
          else:
              value_raw = item.get("value", 0)
              meta = item.get("team", "")
              value = f'£{value_raw:.1f}m' if isinstance(value_raw, (int, float)) else str(value_raw)
              value_class = ""
              name = item.get("manager", "—")

          rows += (
              f'<div class="transfer-market-row">'
              f'<div style="min-width:0">'
              f'<div class="transfer-market-name">{name}</div>'
              f'<div class="transfer-market-meta">{meta}</div>'
              f'</div>'
              f'<div class="transfer-market-value {value_class}">{value}</div>'
              f'</div>'
          )

      return (
          f'<div class="transfer-market-card">'
          f'<div class="transfer-market-title"><span>{icon}</span><span>{title}</span></div>'
          f'{rows}'
          f'</div>'
      )

    def _transfer_market_html(market):
      if not market:
          return ""

      cards = ""
      cards += _transfer_market_card("Most transferred in", "📥", market.get("most_transferred_in", []), "player")
      cards += _transfer_market_card("Most transferred out", "📤", market.get("most_transferred_out", []), "player")
      cards += _transfer_market_card("Most valuable teams", "💰", market.get("most_valuable_teams", []), "team")
      cards += _transfer_market_card("Lowest value teams", "🪙", market.get("lowest_value_teams", []), "team")

      if not cards:
          return ""

      return (
          f'<div style="height:10px"></div>'
          f'<div class="section-label" style="margin-bottom:6px">Market pulse</div>'
          f'<div class="transfer-market-grid">{cards}</div>'
      )

    tr_payload = payload.get("transfer_reports", {})
    transfer_market_html = _transfer_market_html(payload.get("transfer_market", {}))

    best_story = tr_payload.get("best")
    worst_story = tr_payload.get("worst")

    transfer_reports_html = _transfer_story("Best business", "📈", best_story)

    if worst_story and worst_story != best_story:
        transfer_reports_html += _transfer_story("Market disaster", "📉", worst_story)

    if not transfer_reports_html:
        transfer_reports_html = (
            '<div class="muted" style="font-size:13px">'
            'No meaningful transfer stories this week'
            '</div>'
        )

    # Cup Competeition
    cup_html = ""
    cup_week = payload.get("cup_week")

    if cup_week and cup_week.get("fixtures"):
        fixture_rows = ""

        for f in cup_week["fixtures"]:
            home_score = f.get("home_score")
            away_score = f.get("away_score")

            if home_score is not None and away_score is not None:
                home_score_html = f'<span class="cup-score">{home_score}</span>'
                away_score_html = f'<span class="cup-score">{away_score}</span>'
                note = f.get("note", "")
            else:
                home_score_html = ""
                away_score_html = ""
                note = f'{f.get("home_seed", "")} vs {f.get("away_seed", "")}'.strip(" vs ")

            note_html = f'<div class="cup-note">{note}</div>' if note else ""

            fixture_rows += (
                f'<div class="cup-fixture">'
                f'<div class="cup-side">'
                f'<div class="cup-name">{f.get("home", "—")}</div>'
                f'{home_score_html}'
                f'</div>'
                f'<div class="cup-vs">v</div>'
                f'<div class="cup-side right">'
                f'<div class="cup-name">{f.get("away", "—")}</div>'
                f'{away_score_html}'
                f'</div>'
                f'{note_html}'
                f'</div>'
            )

        cup_html = (
            f'<div class="cup-head">'
            f'<div class="cup-title">{cup_week.get("round", "Cup watch")}</div>'
            f'<div class="cup-status">{cup_week.get("status", "")}</div>'
            f'</div>'
            f'{fixture_rows}'
        )

    else:
        next_fixture_rows = ""
        if cup_week and cup_week.get("next_fixtures"):
            for f in cup_week.get("next_fixtures", []):
                group_note = f.get("group") or f.get("round", "")
                note_html = f'<div class="cup-note">{group_note}</div>' if group_note else ""
                next_fixture_rows += (
                    f'<div class="cup-fixture">'
                    f'<div class="cup-side"><div class="cup-name">{f.get("home", "—")}</div></div>'
                    f'<div class="cup-vs">v</div>'
                    f'<div class="cup-side right"><div class="cup-name">{f.get("away", "—")}</div></div>'
                    f'{note_html}'
                    f'</div>'
                )

        if next_fixture_rows:
            cup_html = (
                f'<div class="cup-head">'
                f'<div class="cup-title">Next cup round</div>'
                f'<div class="cup-status">GW{cup_week.get("next_gw", "")}</div>'
                f'</div>'
                f'{next_fixture_rows}'
            )
        else:
            cup_html = (
                f'<div class="lms-box">'
                f'<div class="lms-title">🏆 Cup watch</div>'
                f'<div class="lms-sub">Cup fixtures will appear here when the next round is ready.</div>'
                f'</div>'
            )

    # Block current
    block_html = ""
    b = payload.get('block')

    if b and b.get('top3'):
        medals_sm = ['🥇', '🥈', '🥉']
        top3 = b['top3'][:3]
        leader_points = top3[0].get("points", 0) if top3 else 0
        is_complete = bool(b.get('winner'))

        rows = ""

        for i, e in enumerate(top3):
            points = e.get("points", 0)

            if is_complete:
                gap_html = ""
            elif i == 0:
                gap_html = '<div class="block-gap">leader</div>'
            else:
                gap = leader_points - points
                gap_html = f'<div class="block-gap">{gap} behind</div>'

            rows += (
                f'<div class="block-row">'
                f'<span class="block-medal">{medals_sm[i]}</span>'
                f'<span class="block-name">{e["name"]}</span>'
                f'<span class="block-score-wrap">'
                f'<div class="block-score">{points} pts</div>'
                f'{gap_html}'
                f'</span>'
                f'</div>'
            )

        complete_html = ""

        if is_complete:
            complete_html = (
                f'<div class="block-complete">'
                f'<div class="block-complete-title">Block winner</div>'
                f'<div class="block-complete-winner">🏅 {b["winner"]}</div>'
                f'</div>'
            )

        status = "Complete" if is_complete else "Live standings"

        block_html = (
            f'<div class="block-head">'
            f'<div class="block-title">{b["name"]}</div>'
            f'<div class="block-status">{status}</div>'
            f'</div>'
            f'{rows}'
            f'{complete_html}'
        )
    else:
        block_html = (
            f'<div class="lms-box">'
            f'<div class="lms-title">No block active</div>'
            f'<div class="lms-sub">The next Manager of the Block race has not started yet.</div>'
            f'</div>'
        )


    # Chips — one row per chip played, adaptive to 0/1/many
    # Impact label is chip-specific; manager name shown as context
    CHIP_DISPLAY = {
      'Bench Boost':    ('🪑', 'final bench points'),
      'Triple Captain': ('👑', 'extra captain points'),
      'Free Hit':       ('⚡', 'gain vs previous XI'),
      'Wildcard':       ('🎯', 'gain vs previous XI'),
    }

    chips_html = ""
    chips = payload.get('chips', [])

    if chips:
        grouped = defaultdict(list)
        for c in chips:
            grouped[c['chip']].append(c)
        for chip_name in sorted(grouped.keys(), key=lambda x: x.lower()):
            entries = sorted(
                grouped[chip_name],
                key=lambda x: x.get('score', 0),
                reverse=True
            )
            icon, context_label = CHIP_DISPLAY.get(chip_name, ('🃏', 'chip score'))
            count = len(entries)
            played_label = "played" if count != 1 else "played"
            rows = ""
            for c in entries:
                score = c.get('score', 0)
                score_display = f"+{score}" if score >= 0 else str(score)
                score_class = "good" if score >= 0 else "bad"

                rows += (
                    f'<div class="chip-manager-row">'
                    f'<span class="chip-manager-name">{c["name"]}</span>'
                    f'<span class="chip-manager-score {score_class}">{score_display}</span>'
                    f'</div>'
                )
            chips_html += (
                f'<div class="chip-group">'
                f'<div class="chip-group-head">'
                f'<div class="chip-group-title">'
                f'<span class="chip-icon">{icon}</span>'
                f'<span>{chip_name}</span>'
                f'</div>'
                f'<div class="chip-group-meta">{count} {played_label} · {context_label}</div>'
                f'</div>'
                f'{rows}'
                f'</div>'
            )
    else:
        chips_html = '<div class="muted" style="font-size:13px">No chips played this week</div>'

    from newsletter_generator import _render_captaincy_lines

    league  = master['league_metadata']['league_name']
    season  = master['league_metadata']['season']
    cap     = payload['captaincy']
    bench   = payload['bench']

    division_weekly_html = ""
    for d in payload.get("division_weekly", []):
      div_name = d.get("division", "")
      icon = DIV_ICONS.get(div_name, "🏟️")

      above_avg = d.get("above_average", 0)
      above_avg_display = f"+{above_avg}" if above_avg >= 0 else str(above_avg)

      division_weekly_html += (
          f'<div class="division-tile">'
          f'<div class="division-tile-head">'
          f'<span class="division-icon">{icon}</span>'
          f'<span class="division-name">{div_name}</span>'
          f'</div>'
          f'<div class="division-best">{d.get("best_manager", "—")}</div>'
          f'<div class="division-score">{d.get("best_score", 0)}</div>'
          f'<div class="division-score-label">pts this GW</div>'
          f'<div class="division-meta">'
          f'Avg {d.get("average", 0)} · <span class="division-gap">{above_avg_display} vs avg</span>'
          f'</div>'
          f'</div>'
      )

    if not division_weekly_html:
        division_weekly_html = '<div class="muted" style="font-size:13px">No division scores available</div>'
    else:
        division_weekly_html = f'<div class="division-grid">{division_weekly_html}</div>'

    best_sub_row = ""
    if bench.get('best_sub_pts', 0) > 0 and bench.get('best_sub_name') not in ('None', '', None):
      best_sub_row = f"""
        <div class="bench-row">
          <div>
            <div class="bench-label">Best auto-sub</div>
            <div class="bench-name">{bench['best_sub_name']}</div>
            <div class="bench-detail">Subbed on for {bench['best_sub_manager']}</div>
          </div>
          <div class="bench-score good">{bench['best_sub_pts']} pts</div>
        </div>
      """

    golden_lines = "".join(
      f"<div>{line}</div>"
      for line in _render_captaincy_lines(cap['golden_armband'])
    )
    dud_lines = "".join(
      f"<div>{line}</div>"
      for line in _render_captaincy_lines(cap['dud_captaincy'])
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0">
<title>GW{gameweek} Debrief — {league}</title>
<style>{BASE_CSS}{_render_css(POSTER_CSS)}</style>
</head>
<body>

<div style="text-align:center;padding:20px 0 16px">
  <div style="font-size:12px;color:var(--muted)">{league} — {season}</div>
  <div style="font-size:22px;font-weight:700;margin:4px 0">Gameweek {gameweek} Debrief</div>
  <div style="display:inline-block;font-size:12px;padding:3px 12px;background:var(--surface);
              border-radius:999px;color:var(--muted);margin-top:6px">League average: {payload['league_avg']} pts</div>
</div>

<div class="card">
  <div class="section-label">The Top Performers</div>
  {podium_html}
  <div style="display:flex;justify-content:space-between;padding-top:10px;margin-top:8px;
              border-top:0.5px solid var(--border);font-size:13px;color:var(--muted)">
    <span>🥄 Wooden spoon</span>
    <span><b>{payload['wooden_spoon']['name']}</b> — {payload['wooden_spoon']['net_gw_points']} pts</span>
  </div>
</div>


<div class="card">
  <button class="toggle" onclick="tog('scores')">
    <span>All scores</span><span class="chev" id="c-scores">▾</span>
  </button>
  <div class="collapsible" id="scores" style="margin-top:10px">
    <div class="scores-list">
      {scores_rows}
    </div>
  </div>
</div>

<div class="card">
  <div class="section-label">Captaincy corner</div>
  {_captaincy_row(
      "❤️",
      "Most captained",
      f"<b>{cap['most_captained']}</b><br><span class='cap-value-muted'>{cap['most_captained_count']} managers</span>"
  )}
  {_captaincy_row("👑", "Golden armband", golden_lines)}
  {_captaincy_row("👻", "Dud Captain", dud_lines)}
</div>

<div class="card">
  <div class="section-label">Transfer Market</div>
  {transfer_reports_html}
  {transfer_market_html}
</div>

<div class="card">
  <div class="section-label">Strategy room</div>
  {strategic_html}

  <div style="height:12px"></div>

  <div class="section-label" style="margin-bottom:6px">League template</div>
  {template_html}
</div>

<div class="card">
  <div class="section-label">Stat leaders</div>
  <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:8px">{stat_grid}</div>
</div>

<div class="card">
  <div class="section-label">Division Breakdown</div>
  {division_weekly_html}
</div>


<div class="card">
  <div class="section-label">Chip Review</div>
  {chips_html}
</div>

<div class="card">
  <div class="section-label">Bench watch</div>

  <div class="bench-row">
    <div>
      <div class="bench-label">Most benched</div>
      <div class="bench-name">{bench['most_bench_manager']}</div>
      <div class="bench-detail">Total unused bench points</div>
    </div>
    <div class="bench-score bad">{bench['most_bench_pts']} pts</div>
  </div>

  <div class="bench-row">
    <div>
      <div class="bench-label">Best left behind</div>
      <div class="bench-name">{bench['best_bench_name']}</div>
      <div class="bench-detail">Highest-scoring player still benched</div>
    </div>
    <div class="bench-score warn">{bench['best_bench_pts']} pts</div>
  </div>
  
  {best_sub_row}
</div>

<div class="card">
  <div class="section-label">Cup Report</div>
  {cup_html}
</div>

<div class="card">
  <div class="section-label">Last Man Standing</div>
  {lms_event_html}
</div>

<div class="card">
  <div class="section-label">Manager of the Block</div>
  {block_html}
</div>

<div style="text-align:center;margin-top:8px">
  <a href="league_hub.html" style="font-size:13px;color:var(--accent);text-decoration:none;
     font-weight:600">← Back to League Hub</a>
</div>

<script>
function tog(id) {{
  const el = document.getElementById(id);
  const ch = document.getElementById('c-' + id);
  el.classList.toggle('open');
  if (ch) ch.classList.toggle('open', el.classList.contains('open'));
}}
</script>
</body></html>"""

    path = os.path.join(output_dir, f"gw_{gameweek}_poster.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  [HTML] GW poster → {path}")
    return path



def _rule_short_label(rule):
    return TB_LABELS.get(rule, "TB").replace("TB ", "")


def _format_rule_value(master, mid, rule, gw=None, cup_stats=None):
    value = _rule_value(master, mid, rule, gw=gw, cup_stats=cup_stats)
    if rule == "overall_rank":
        value = abs(value)
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return _compact_number(value) if isinstance(value, int) else value


def _rules_pills_html(rules):
    pills = ""
    for i, rule in enumerate(rules, 1):
        detail = TB_DETAILS.get(rule, rule.replace("_", " "))
        label = _rule_short_label(rule)
        pills += (
            f'<span class="hub-tb-rule-pill" title="{detail}">'
            f'<span class="hub-tb-rule-no">{i}</span>{label}'
            f'</span>'
        )
    return f'<div class="hub-tb-rules">{pills}</div>'


def _tiebreak_rows(master, entries, rules, main_label, main_value_key, rule, gw=None, cup_stats_by_mid=None):
    if not entries or not rule:
        return ""

    rows = ""
    sorted_entries = _sort_by_official_tiebreakers(
        entries,
        key_fn=lambda x: _tb_sort_key(
            master,
            x.get("manager_id", ""),
            rules,
            gw=gw,
            cup_stats=(cup_stats_by_mid or {}).get(str(x.get("manager_id", ""))),
            primary_value=x.get(main_value_key),
        ),
    )

    for pos, entry in enumerate(sorted_entries, 1):
        mid = str(entry.get("manager_id", ""))
        cup_stats = (cup_stats_by_mid or {}).get(mid)
        decider = _format_rule_value(master, mid, rule, gw=gw, cup_stats=cup_stats)
        rows += (
            f'<div class="hub-tb-row">'
            f'<span class="hub-tb-pos">#{pos}</span>'
            f'<span class="hub-tb-name">{entry.get("name", _manager_name(master, mid))}</span>'
            f'<span class="hub-tb-main">{entry.get(main_value_key, 0)}</span>'
            f'<span class="hub-tb-decider">{_rule_short_label(rule)} {decider}</span>'
            f'</div>'
        )

    return rows


def _tiebreak_group_html(master, title, context, rules, entries, main_label, main_value_key, rule, gw=None, cup_stats_by_mid=None):
    rows = _tiebreak_rows(
        master,
        entries,
        rules,
        main_label,
        main_value_key,
        rule,
        gw=gw,
        cup_stats_by_mid=cup_stats_by_mid,
    )
    if not rows:
        return ""

    return (
        f'<div class="hub-tb-group">'
        f'<div class="hub-tb-context">'
        f'<div class="hub-tb-context-title">{title}</div>'
        f'<div class="hub-tb-context-meta">{context} · sorted by {_rule_short_label(rule)}</div>'
        f'</div>'
        f'{rows}'
        f'</div>'
    )


def _block_points_for_manager(mdata, bname, gws):
    block_stats = mdata.get('block_stats', {}) or {}

    if block_stats.get('current_block_points') is not None:
        return block_stats.get('current_block_points', 0)

    if isinstance(block_stats.get(bname), dict):
        b = block_stats.get(bname, {})
        return b.get('points', b.get('total_points', 0))

    total = 0
    history = mdata.get('gw_history', {}) or {}
    for gw in gws:
        row = history.get(str(gw), history.get(gw, {}))
        total += row.get('net_gw_points', row.get('points', row.get('gw_points', 0)))
    return total


def _tiebreakers_html(master, current_gw, gw_results=None):
    gw_results = gw_results or {}
    managers = master.get('managers', {})

    cards = []

    # Divisions
    div_rules = RULES_REFERENCE["division_tiebreakers"]
    div_groups_html = ""
    for div in DIVISION_ORDER:
        standings = master.get('divisions', {}).get(div, {}).get('standings', {})
        entries = []
        for _, e in sorted(standings.items(), key=lambda x: int(x[0])):
            mid = str(e.get("manager_id"))
            total = e.get("total_points", _manager(master, mid).get("stats", {}).get("total_points", 0))
            entries.append({"manager_id": mid, "name": e.get("name", _manager_name(master, mid)), "total": total})
        for total, tied in _tie_groups_by_value(entries, "total").items():
            tied_ids = [x["manager_id"] for x in tied]
            rule = _first_tb_rule(master, tied_ids, div_rules)
            div_groups_html += _tiebreak_group_html(master, div, f"Total {total}", div_rules, tied, "Total", "total", rule)
    cards.append(("Divisions", "Season tables", div_rules, div_groups_html))

    # Block
    block_rules = RULES_REFERENCE["block_tiebreakers"]
    block_groups_html = ""
    for bname, bdata in master.get('competitions', {}).get('blocks', {}).items():
        gws = bdata.get('gws', [])
        if not gws:
            continue
        won = bdata.get('winner_name')
        is_relevant = bool(won or (gws[0] <= current_gw <= gws[-1]))
        if not is_relevant:
            continue
        entries = []
        for mid, mdata in managers.items():
            points = _block_points_for_manager(mdata, bname, gws)
            entries.append({"manager_id": str(mid), "name": mdata.get("name", str(mid)), "points": points})
        for points, tied in _tie_groups_by_value(entries, "points").items():
            tied_ids = [x["manager_id"] for x in tied]
            rule = _first_tb_rule(master, tied_ids, block_rules)
            block_groups_html += _tiebreak_group_html(master, bname, f"Block points {points}", block_rules, tied, "Pts", "points", rule)
    cards.append(("Manager of the Block", "Active/completed block races", block_rules, block_groups_html))

    # LMS
    lms_rules = RULES_REFERENCE["lms_tiebreakers"]
    lms_groups_html = ""
    lms = master.get('competitions', {}).get('lms', {})
    name_to_mid = {mdata.get("name"): str(mid) for mid, mdata in managers.items()}
    for gw, eliminated_name in sorted(lms.get('eliminated', {}).items(), key=lambda x: int(x[0])):
        elim_mid = name_to_mid.get(eliminated_name)
        if not elim_mid:
            continue
        elim_row = _gw_row(_manager(master, elim_mid), gw)
        elim_score = elim_row.get('net_gw_points', elim_row.get('gw_points', elim_row.get('points')))
        if elim_score is None:
            continue
        tied = []
        for mid, mdata in managers.items():
            row = _gw_row(mdata, gw)
            score = row.get('net_gw_points', row.get('gw_points', row.get('points')))
            if score is not None and _as_num(score) == _as_num(elim_score):
                tied.append({"manager_id": str(mid), "name": mdata.get("name", str(mid)), "score": score})
        if len(tied) > 1:
            rule = _first_tb_rule(master, [x["manager_id"] for x in tied], lms_rules, gw=gw)
            lms_groups_html += _tiebreak_group_html(master, f"GW{gw} elimination", f"GW score {elim_score}", lms_rules, tied, "Score", "score", rule, gw=gw)
    cards.append(("Last Man Standing", "Elimination weeks", lms_rules, lms_groups_html))

    # Cup groups
    cup_rules = RULES_REFERENCE["cup_group_tiebreakers"]
    cup_groups_html = ""
    cup = master.get('competitions', {}).get('cup', {})
    for group_name, member_ids in cup.get('groups', {}).items():
        entries = []
        cup_stats_by_mid = {}
        for mid in member_ids:
            mid = str(mid)
            mdata = _manager(master, mid)
            cs = mdata.get('cup_stats', {}) or {}
            points = cs.get('match_points', cs.get('group_points', 0))
            entries.append({"manager_id": mid, "name": mdata.get("name", mid), "points": points})
            cup_stats_by_mid[mid] = cs
        for points, tied in _tie_groups_by_value(entries, "points").items():
            if len(tied) < 2:
                continue
            tied_ids = [x["manager_id"] for x in tied]
            rule = _first_tb_rule(master, tied_ids, cup_rules, cup_stats_by_mid=cup_stats_by_mid)
            cup_groups_html += _tiebreak_group_html(master, group_name, f"Group points {points}", cup_rules, tied, "Pts", "points", rule, cup_stats_by_mid=cup_stats_by_mid)
    cards.append(("Cup groups", "Group-stage tables", cup_rules, cup_groups_html))

    # Cup knockouts: rules card only for now; live tie explanations can be added once knockout tie rows are stored.
    cards.append(("Cup knockouts", "Two-legged/single-leg knockout ties", RULES_REFERENCE["cup_knockout_tiebreakers"], ""))

    html = ""
    for title, status, rules, groups_html in cards:
        body = groups_html or '<div class="hub-tb-empty">No active tie-break situation to explain right now.</div>'
        html += (
            f'<div class="hub-tb-card">'
            f'<div class="hub-tb-head-row">'
            f'<div class="hub-tb-title">{title}</div>'
            f'<div class="hub-tb-status">{status}</div>'
            f'</div>'
            f'{_rules_pills_html(rules)}'
            f'{body}'
            f'</div>'
        )

    return html

# ─────────────────────────────────────────────────────────────────────────────
# LEAGUE HUB
# ─────────────────────────────────────────────────────────────────────────────

def build_hub(gameweek, master, output_dir=".", gw_results=None):
    """Generates the always-current league hub HTML."""

    div_tables  = _div_tables_html(master, gw_results or {}, gameweek)
    lms_section = _lms_html(master)
    cup_section = _cup_html(master, gameweek)
    blocks_sec  = _blocks_html(master, gameweek)
    prize_h, fun_h = _accolades_html(master)
    chip_leaderboard = _chip_leaderboard_html(master, gw_results or {})
    tiebreakers_section = _tiebreakers_html(master, gameweek, gw_results or {})
    live_status = _live_status_html(master, gameweek)

    league = master['league_metadata']['league_name']
    season = master['league_metadata']['season']

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{league} — League Hub</title>
<style>{BASE_CSS}{_render_css(HUB_CSS)}</style>
</head>
<body class="hub-page">

<div class="hero">
  <div style="font-size:12px;color:var(--muted)">{league}</div>
  <div style="font-size:22px;font-weight:700;margin:4px 0">{season}</div>
  <div style="font-size:13px;color:var(--muted)">Last updated: Gameweek {gameweek}</div>
</div>


<div class="nav">
  <button class="nav-btn active" onclick="show('divs',this)">Divisions</button>
  <button class="nav-btn" onclick="show('lms',this)">LMS</button>
  <button class="nav-btn" onclick="show('cup',this)">Cup</button>
  <button class="nav-btn" onclick="show('block',this)">Block</button>
  <button class="nav-btn" onclick="show('tb',this)">Tie-breakers</button>
  <button class="nav-btn" onclick="show('acc',this)">Accolades</button>
  <button class="nav-btn" onclick="show('chips',this)">Chip Leaderboard</button>
</div>

<div class="section active" id="divs">
  <div class="card">
    <div class="section-label">What’s live this GW</div>
    {live_status}
  </div>
  <div class="card">{div_tables}</div>
</div>

<div class="section" id="lms">
  <div class="card">{lms_section}</div>
</div>

<div class="section" id="cup">
  <div class="card">
    <div class="section-label">Cup centre</div>
    {cup_section}
  </div>
</div>

<div class="section" id="block">
  <div class="card">
    <div class="section-label">Manager of the block</div>
    {blocks_sec}
  </div>
</div>

<div class="section" id="tb">
  <div class="card">
    <div class="section-label">Tie-breakers centre</div>
    {tiebreakers_section}
  </div>
</div>

<div class="section" id="acc">
  <div class="card">
    <div class="section-label">Prized awards</div>
    {prize_h}
  </div>
  <div class="card">
    <div class="section-label">Fun accolades</div>
    {fun_h}
  </div>
</div>

<div class="section" id="chips">
  <div class="card">
    <div class="section-label">Chip Leaderboard</div>
    {chip_leaderboard}
  </div>
</div>

<script>
function show(id, btn) {{
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  btn.classList.add('active');
}}
</script>
</body></html>"""

    path = os.path.join(output_dir, "league_hub.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  [HTML] League hub → {path}")
    return path
