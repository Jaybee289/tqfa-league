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
    color-scheme:dark;
    --bg:#191919; --surface:#242424; --surface2:#2e2e2e;
    --border:rgba(255,255,255,0.09); --text:#f0ede8; --muted:#888;
    --accent:#185fa5; --green:#00ff87; --amber:#ffc226; --red:#ff4d4d;
    --radius:12px;
  }
  html { background:#191919; }
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
  .lms-warning{{margin-top:9px;border-top:1px solid rgba(255,194,38,0.32);padding-top:8px;font-size:11px;color:#ffc226;font-weight:800;line-height:1.35;}}
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
  .cup-group-title{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.07em;font-weight:900;margin:12px 0 6px;}}
  .cup-group-title:first-child{{margin-top:0;}}
  .cup-match-row{{display:grid;grid-template-columns:minmax(0,1fr) 76px minmax(0,1fr);gap:10px;align-items:center;}}
  .cup-match-team{{font-size:13px;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
  .cup-match-team.away{{text-align:right;}}
  .cup-match-team.loser{{color:var(--muted);font-weight:700;}}
  .cup-match-team.winner{{color:var(--text);font-weight:900;}}
  .cup-match-score{{display:flex;justify-content:center;align-items:center;gap:8px;font-size:18px;font-weight:900;color:var(--text);font-variant-numeric:tabular-nums;white-space:nowrap;}}
  .cup-match-score-value.loser{{color:var(--muted);font-weight:800;}}
  .cup-match-score.muted{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.08em;}}
  .cup-empty-box{{border-radius:12px;padding:12px;background:var(--surface2);border:0.5px solid var(--border);}}
  .cup-empty-title{{font-size:14px;font-weight:800;line-height:1.25;color:var(--text);}}
  .cup-empty-sub{{font-size:12px;color:var(--muted);margin-top:3px;line-height:1.35;}}
  .strategy-grid{{display:grid;grid-template-columns:1fr;gap:8px;}}
  .strategy-card{{background:#1e1e1e;border:0.5px solid var(--border);border-radius:12px;padding:12px;min-width:0;overflow:hidden;}}
  .strategy-top{{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;min-width:0;width:100%;}}
  .strategy-top > div:first-child{{min-width:0;flex:1;}}
  .strategy-kicker{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.07em;font-weight:800;margin-bottom:8px;}}
  .strategy-card-subtitle{{font-size:11px;color:var(--muted);font-weight:700;margin:-1px 0 8px;}}
  .strategy-player{{font-size:16px;font-weight:900;line-height:1.15;white-space:normal;overflow-wrap:anywhere;}}
  .strategy-score{{flex:0 0 auto;white-space:nowrap;font-size:17px;font-weight:900;color:var(--green);line-height:1.1;text-align:right;}}
  .strategy-meta{{font-size:11px;color:var(--muted);margin-top:8px;line-height:1.35;white-space:normal;overflow-wrap:anywhere;}}
  .strategy-managers{{font-size:11px;color:var(--muted);font-weight:700;margin-top:4px;line-height:1.35;white-space:normal;overflow-wrap:anywhere;}}
  .strategy-player-list{{display:flex;flex-direction:column;gap:8px;margin-top:4px;}}
  .strategy-player-row{{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;align-items:start;padding:0 0 8px;border-bottom:1px solid var(--border);}}
  .strategy-player-row:last-child{{padding-bottom:0;border-bottom:none;}}
  .strategy-player-meta{{font-size:11px;color:var(--muted);margin-top:3px;line-height:1.3;}}
  .form-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin-top:10px;}}
  .form-card{{background:#1e1e1e;border:0.5px solid var(--border);border-radius:12px;padding:12px;min-width:0;}}
  .form-kicker{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.07em;font-weight:800;margin-bottom:5px;}}
  .form-value{{font-size:22px;font-weight:900;line-height:1;color:var(--text);}}
  .form-value.good{{color:var(--green);}}
  .form-value.bad{{color:var(--red);}}
  .form-meta{{font-size:11px;color:var(--muted);line-height:1.35;margin-top:7px;}}
  @media(max-width:360px){{.form-grid{{grid-template-columns:1fr;}}}}
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
  .transfer-market-card{{background:#1e1e1e;border:0.5px solid var(--border);border-radius:12px;padding:10px;min-width:0;}}
  .transfer-market-title{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.07em;font-weight:900;margin-bottom:7px;display:flex;align-items:center;gap:5px;}}
  .transfer-market-row{{display:flex;justify-content:space-between;align-items:flex-start;gap:8px;padding:6px 0;border-bottom:0.5px solid var(--border);}}
  .transfer-market-row:last-child{{border-bottom:none;padding-bottom:0;}}
  .transfer-market-name{{font-size:12px;font-weight:800;line-height:1.2;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
  .transfer-market-meta{{font-size:10px;color:var(--muted);margin-top:2px;line-height:1.3;white-space:normal;overflow-wrap:anywhere;}}
  .transfer-market-managers{{margin-top:5px;display:flex;flex-wrap:wrap;gap:5px;justify-content:flex-start;min-width:0;}}
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
  .bench-score.neutral {{
    color:var(--muted);
  }}
  .newsletter-section-spacer{{height:14px;}}
  .cup-centre-section{{margin-top:18px;}}
  .cup-centre-card{{margin-top:14px;}}
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
  .poster-name-pills {{
    display:flex;
    flex-wrap:wrap;
    gap:5px;
    justify-content:flex-start;
    min-width:0;
  }}
  .poster-name-pill {{
    display:inline-block;
    background:rgba(255,255,255,0.06);
    border:0.5px solid rgba(255,255,255,0.10);
    border-radius:999px;
    padding:3px 7px;
    font-size:10px;
    font-weight:800;
    line-height:1.1;
    max-width:100%;
    white-space:nowrap;
    overflow:hidden;
    text-overflow:ellipsis;
  }}
  .strategy-managers .poster-name-pills {{
    justify-content:flex-start;
    margin-top:4px;
  }}
  .muted {{
    color:var(--muted);
  }}
  .stat-grid {{ display:grid;grid-template-columns:repeat(2,1fr);gap:10px; }}

  @media(max-width:600px){{
    td,.score-row,.stat-row,.block-row,.cap-item,.bench-row,.podium-row,.template-row,.transfer-story,.transfer-move-row,.transfer-market-row,.hub-cup-fixture-row,.hub-bracket-row,.hub-tb-row,.hub-lms-elim-row,.hub-block-row,.hub-acc-rank-row,.hub-chip-head,.hub-chip-row{{border-bottom-width:1px;}}
    .block-complete,.lms-escaped,.hub-block-winner,.hub-block-muted,.hub-acc-empty,.hub-tb-empty{{border-top-width:1px;}}
    .hub-acc-detail-pick + .hub-acc-detail-pick{{border-top-width:1px;}}
  }}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Hub CSS
# ─────────────────────────────────────────────────────────────────────────────


HUB_CSS = """
  .hero{{text-align:center;padding:20px 0 16px;border-bottom:0.5px solid var(--border);margin-bottom:16px;}}
  .poster-link{{display:block;background:var(--accent);color:#fff;text-decoration:none;text-align:center;padding:12px;border-radius:var(--radius);font-weight:600;font-size:14px;margin-bottom:16px;}}
  .nav{{display:flex;gap:6px;flex-wrap:wrap;padding-bottom:4px;margin-bottom:16px;}}
  .nav::-webkit-scrollbar{{display:none;}}
  .nav-btn{{white-space:nowrap;font-size:12px;padding:6px 12px;border:0.5px solid var(--border);border-radius:999px;background:var(--surface);color:var(--text);cursor:pointer;font-family:inherit;flex:0 0 auto;}}
  @media(max-width:520px){{.nav-btn{{flex:1 1 calc(50% - 6px);text-align:center;}}}}
  @media(max-width:340px){{.nav-btn{{flex-basis:100%;}}}}
  .nav-btn.active{{background:var(--accent);color:#fff;border-color:transparent;font-weight:600;}}
  .hub-info-pill{{border:0.5px solid var(--border);border-radius:14px;background:var(--surface2);padding:10px 12px;margin-bottom:12px;font-size:12px;color:var(--muted);line-height:1.4;}}
  .hub-info-pill strong{{color:var(--text);font-weight:900;}}
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
  .hub-captain-wrap{{display:inline-flex;align-items:center;gap:4px;min-width:0;max-width:100%;}}
  .hub-captain-text{{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}}
  .hub-chip-mini{{display:inline-flex;align-items:center;justify-content:center;border:0.5px solid var(--border);background:var(--surface2);border-radius:999px;padding:2px 5px;font-size:9px;line-height:1;font-weight:900;color:var(--amber);}}
  .hub-gw-wrap{{display:inline-grid;grid-template-columns:minmax(2.2ch,auto) 24px;align-items:center;justify-content:end;column-gap:4px;white-space:nowrap;width:100%;}}
  .hub-gw-value{{text-align:right;font-variant-numeric:tabular-nums;}}
  .hub-gw-chip-slot{{display:inline-flex;align-items:center;justify-content:flex-start;width:24px;min-width:24px;}}
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

  .hub-debrief-grid{{display:grid;grid-template-columns:1fr;gap:8px;}}
  .hub-debrief-card{{display:flex;align-items:center;justify-content:space-between;gap:12px;background:var(--surface2);border:0.5px solid var(--border);border-radius:12px;padding:11px 12px;text-decoration:none;color:var(--text);}}
  .hub-debrief-card:hover{{border-color:rgba(86,156,255,0.55);background:rgba(86,156,255,0.08);}}
  .hub-debrief-main{{min-width:0;}}
  .hub-debrief-title{{font-size:13px;font-weight:900;line-height:1.2;}}
  .hub-debrief-sub{{font-size:11px;color:var(--muted);margin-top:3px;line-height:1.25;}}
  .hub-debrief-pill{{flex:0 0 auto;border:0.5px solid var(--border);border-radius:999px;padding:4px 8px;font-size:10px;font-weight:900;color:var(--muted);background:var(--surface);white-space:nowrap;}}
  .hub-debrief-card.latest .hub-debrief-pill{{border-color:rgba(86,156,255,0.55);background:rgba(86,156,255,0.14);color:#9ec5ff;}}
  @media(min-width:700px){{.hub-debrief-grid{{grid-template-columns:repeat(2,minmax(0,1fr));}}}}
  .hub-live-link{{display:inline-flex;align-items:center;justify-content:center;align-self:flex-start;width:max-content;max-width:100%;border:0.5px solid rgba(86,156,255,0.55);background:rgba(86,156,255,0.14);color:#9ec5ff;border-radius:999px;padding:5px 8px;text-decoration:none;font-size:10px;font-weight:900;line-height:1;box-shadow:0 4px 14px rgba(0,0,0,0.12);}}
  .hub-live-link:hover{{border-color:rgba(86,156,255,0.85);background:rgba(86,156,255,0.2);}}
  .hub-live-card.live{{border-color:rgba(0,255,135,0.28);}}
  .hub-live-card.warn{{border-color:rgba(255,194,38,0.32);}}
  .hub-live-card.idle{{border-color:rgba(255,77,77,0.22);}}
  .hub-live-card.quiet .hub-live-title,
  .hub-live-card.idle .hub-live-title{{color:var(--muted);}}

  /* Hub cup */
  .hub-cup-overview{{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin-bottom:12px;}}
  @media(min-width:700px){{.hub-cup-overview{{grid-template-columns:repeat(5,1fr);}}}}
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
  .hub-cup-fixture-group-title{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.07em;font-weight:900;margin:10px 0 4px;}}
  .hub-cup-fixture-group-title:first-child{{margin-top:0;}}
  .hub-cup-fixture-row{{display:grid;grid-template-columns:minmax(0,1fr) 20px minmax(0,1fr);gap:7px;align-items:center;padding:6px 0;border-bottom:0.5px solid var(--border);font-size:12px;}}
  .hub-cup-fixture-row:last-child{{border-bottom:none;padding-bottom:0;}}
  .hub-cup-side{{font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
  .hub-cup-side.away{{text-align:right;}}
  .hub-cup-vs{{font-size:9px;color:var(--muted);font-weight:900;text-align:center;}}
  .hub-cup-empty{{font-size:13px;color:var(--muted);line-height:1.35;}}
  .hub-cup-table{{width:100%;table-layout:fixed;border-collapse:collapse;}}
  .hub-cup-col-manager{{width:auto;}}
  .hub-cup-col-played{{width:32px;}}
  .hub-cup-col-points{{width:38px;}}
  .hub-cup-col-fpl{{width:44px;}}
  .hub-cup-col-q{{width:44px;}}
  .hub-cup-table th{{font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:0.06em;font-weight:800;padding:6px 0;text-align:right;}}
  .hub-cup-table td{{font-size:12px;padding:7px 0;text-align:right;border-bottom:1px solid var(--border);font-variant-numeric:tabular-nums;}}
  .hub-cup-table tr:last-child td{{border-bottom:none;}}
  .hub-cup-table th:first-child,.hub-cup-table td:first-child{{text-align:left;}}
  .hub-cup-table th:last-child,.hub-cup-table td:last-child{{text-align:center;}}
  .hub-cup-table td:first-child{{border-left:4px solid transparent;padding-left:8px;}}
  .hub-cup-row-auto td:first-child{{border-left-color:var(--green);}}
  .hub-cup-row-playoff td:first-child{{border-left-color:var(--amber);}}
  .hub-cup-path{{display:inline-flex;align-items:center;justify-content:center;min-width:34px;border-radius:999px;padding:2px 6px;font-size:9px;font-weight:900;line-height:1;text-transform:uppercase;}}
  .hub-cup-path.auto{{background:rgba(0,255,135,0.16);color:var(--green);}}
  .hub-cup-path.playoff{{background:rgba(255,194,38,0.16);color:var(--amber);}}
  .hub-cup-results-card{{background:var(--surface2);border:0.5px solid var(--border);border-radius:12px;padding:12px;margin-bottom:10px;}}
  .hub-cup-result-row{{display:grid;grid-template-columns:minmax(0,1fr) 82px minmax(0,1fr);gap:14px;align-items:center;padding:10px 0;border-bottom:1px solid var(--border);font-size:12px;}}
  .hub-cup-result-row:last-child{{border-bottom:none;padding-bottom:0;}}
  .hub-cup-result-score{{font-size:18px;font-weight:900;text-align:center;color:var(--text);font-variant-numeric:tabular-nums;letter-spacing:0.01em;white-space:nowrap;}}
  .hub-cup-score-sep{{display:inline-block;margin:0 7px;color:var(--text);}}
  .hub-cup-score-part{{color:var(--text);}}
  .hub-cup-score-part.loser{{color:var(--muted);font-weight:800;}}
  .hub-cup-result-score.muted{{color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:0.06em;}}
  .hub-cup-winner{{color:var(--text);font-weight:900;}}
  .hub-cup-loser{{color:var(--muted);font-weight:500;}}
  .hub-cup-draw{{color:var(--text);font-weight:800;}}
  .hub-bracket-round{{background:var(--surface2);border:0.5px solid var(--border);border-radius:12px;padding:12px;margin-bottom:10px;}}
  .hub-bracket-round:last-child{{margin-bottom:0;}}
  .hub-bracket-title{{font-size:13px;font-weight:900;margin-bottom:7px;}}
  .hub-bracket-row{{display:grid;grid-template-columns:minmax(0,1fr) 86px minmax(0,1fr);gap:14px;align-items:center;padding:10px 0;border-bottom:1px solid var(--border);font-size:12px;}}
  .hub-bracket-row:last-child{{border-bottom:none;padding-bottom:0;}}
  .hub-bracket-team{{font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}

  .hub-bracket-winner{{font-weight:900;color:var(--text);}}
  .hub-bracket-loser{{color:var(--muted);}}
  .hub-bracket-progress{{font-size:10px;color:var(--green);font-weight:800;text-align:center;margin:0 0 8px;}}
  .hub-bracket-team.away{{text-align:right;}}
  .hub-bracket-score{{font-size:15px;color:var(--text);font-weight:900;white-space:nowrap;text-align:center;font-variant-numeric:tabular-nums;}}
  .hub-bracket-score-main{{display:inline-flex;align-items:center;justify-content:center;gap:8px;font-size:18px;color:var(--text);line-height:1.05;}}
  .hub-bracket-score-part{{color:var(--text);}}
  .hub-bracket-score-part.loser{{color:var(--muted);font-weight:800;}}
  .hub-bracket-score-sub{{display:block;font-size:10px;color:var(--muted);font-weight:800;line-height:1.15;margin-top:3px;}}
  .hub-cup-details{{background:transparent;border:0;margin:0 0 12px;padding:0;}}
  .hub-cup-details>summary{{list-style:none;cursor:pointer;display:flex;justify-content:space-between;align-items:center;gap:10px;background:var(--surface2);border:0.5px solid var(--border);border-radius:12px;padding:10px 12px;margin:12px 0 10px;font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:0.07em;font-weight:900;}}
  .hub-cup-details>summary::-webkit-details-marker{{display:none;}}
  .hub-cup-details>summary::after{{content:'+';font-size:14px;color:var(--muted);}}
  .hub-cup-details[open]>summary::after{{content:'−';}}
  .hub-cup-subdetails{{background:transparent;border:0;margin:0 0 10px;padding:0;}}
  .hub-cup-subdetails>summary{{list-style:none;cursor:pointer;display:flex;justify-content:space-between;align-items:center;gap:10px;border:0.5px solid var(--border);border-radius:10px;padding:8px 10px;margin:8px 0;background:rgba(255,255,255,0.025);font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.06em;font-weight:900;}}
  .hub-cup-subdetails>summary::-webkit-details-marker{{display:none;}}
  .hub-cup-subdetails>summary::after{{content:'+';font-size:12px;color:var(--muted);}}
  .hub-cup-subdetails[open]>summary::after{{content:'−';}}

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
  .hub-tb-subgroup{{border-top:0.5px solid var(--border);padding-top:8px;margin-top:8px;}}
  .hub-tb-subgroup:first-of-type{{border-top:none;padding-top:0;margin-top:0;}}
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
  .hub-lms-warning{{background:rgba(255,194,38,0.08);border:1px solid rgba(255,194,38,0.38);border-radius:12px;padding:12px;margin-bottom:12px;}}
  .hub-lms-warning-title{{font-size:13px;font-weight:900;color:#ffc226;line-height:1.25;}}
  .hub-lms-warning-sub{{font-size:11px;color:var(--muted);margin-top:4px;line-height:1.35;}}
  .hub-lms-label{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.07em;font-weight:800;margin-bottom:6px;}}
  .hub-lms-pill-wrap{{display:flex;flex-wrap:wrap;gap:6px;}}
  .hub-lms-pill{{display:inline-block;background:var(--surface);border:0.5px solid var(--border);border-radius:999px;padding:4px 8px;font-size:11px;font-weight:700;line-height:1.1;}}
  .hub-name-pills{{display:flex;flex-wrap:wrap;gap:6px;min-width:0;justify-content:flex-start;}}
  .hub-name-pill{{display:inline-block;background:var(--surface);border:0.5px solid var(--border);border-radius:999px;padding:4px 8px;font-size:11px;font-weight:700;line-height:1.1;max-width:100%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
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
  .hub-lms-tb-detail{{color:var(--amber);padding-top:0;}}

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
  .hub-block-runner{{display:flex;align-items:center;justify-content:space-between;gap:10px;border-top:0.5px solid var(--border);padding-top:8px;margin-top:7px;font-size:12px;color:var(--muted);}}
  .hub-block-runner span{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.07em;font-weight:800;}}
  .hub-block-runner strong{{font-size:12px;font-weight:800;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}

  .hub-acc-card{{background:var(--surface2);border:0.5px solid var(--border);border-radius:12px;padding:12px;margin-bottom:10px;}}
  .hub-acc-card:last-child{{margin-bottom:0;}}
  .hub-acc-title{{display:flex;align-items:center;gap:7px;font-size:13px;font-weight:900;line-height:1.2;margin-bottom:8px;}}
  .hub-acc-info{{font-size:10px;color:var(--muted);line-height:1.35;margin:-2px 0 8px;padding-left:24px;}}
  .hub-acc-ranks{{margin-top:2px;}}
  .hub-acc-rank-row{{display:flex;align-items:center;gap:8px;padding:8px 0;border-bottom:1.25px solid var(--border);font-size:13px;}}
  .hub-acc-rank-row:last-child{{border-bottom:none;padding-bottom:0;}}
  .hub-acc-medal{{width:22px;text-align:center;font-size:16px;flex:0 0 22px;}}
  .hub-acc-manager{{flex:1;font-weight:700;min-width:0;}}
  .hub-acc-detail{{font-size:10px;color:var(--muted);font-weight:700;line-height:1.25;margin-top:4px;}}
  .hub-acc-detail-pick{{margin-top:6px;}}
  .hub-acc-detail-pick:first-child{{margin-top:0;}}
  .hub-acc-detail-pick + .hub-acc-detail-pick{{border-top:0.75px solid var(--border);padding-top:6px;}}
  .hub-acc-detail-pick-text{{font-size:10px;color:var(--muted);font-weight:800;line-height:1.25;margin-top:3px;}}
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
  .hub-chip-pill{{display:inline-flex;align-items:center;gap:5px;background:var(--surface);border:0.5px solid var(--border);border-radius:999px;padding:4px 8px;font-size:11px;line-height:1.1;max-width:100%;}}
  .hub-chip-pill-meta.good{{color:var(--green);}}
  .hub-chip-pill-meta.bad{{color:var(--red);}}
  .hub-chip-pill-name{{font-weight:900;color:var(--text);white-space:nowrap;}}
  .hub-chip-pill-meta{{font-weight:700;color:var(--muted);white-space:nowrap;}}
  .hub-chip-none{{font-size:10px;color:var(--muted);font-weight:700;}}
  .hub-chip-score{{font-size:13px;font-weight:900;text-align:right;font-variant-numeric:tabular-nums;padding-top:2px;}}
  .hub-chip-score.good{{color:var(--green);}}
  .hub-chip-score.bad{{color:var(--red);}}
  .hub-chip-score.neutral{{color:var(--muted);}}
  .hub-chip-empty{{background:var(--surface2);border:0.5px solid var(--border);border-radius:12px;padding:12px;font-size:13px;color:var(--muted);line-height:1.35;}}
  .hub-chip-events{{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px;justify-content:flex-start;}}
  .hub-chip-event{{display:inline-block;background:var(--surface);border:0.5px solid var(--border);border-radius:999px;padding:4px 8px;font-size:11px;font-weight:700;line-height:1.1;white-space:nowrap;max-width:100%;overflow:hidden;text-overflow:ellipsis;}}
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
    cs = m.get('cup_stats', {}) or {}

    mid = str(manager_id)
    winner_id = str(cup.get('cup_winner_id') or cup.get('winner_id') or '')
    winner_name = cup.get('cup_winner_name') or cup.get('winner_name')
    if winner_id and mid == winner_id:
        return "🏆"
    if winner_name and m.get('name') == winner_name:
        return "🏆"

    group_gws = [int(gw) for gw in (cup.get('group_stage_gws', []) or []) if str(gw).isdigit()]
    knockout_gws = [int(gw) for gw in (cup.get('knockout_gws', []) or []) if str(gw).isdigit()]
    playoff_gws = [int(gw) for gw in (cup.get('playoff_gws', []) or []) if str(gw).isdigit()]
    final_gws = _cup_final_gws(cup)

    # During group stage, nobody is out yet.
    if group_gws and gameweek <= max(group_gws):
        return "✅"

    # After final completion, only the winner keeps the trophy.
    if winner_name or winner_id:
        return "😵"

    # During/after playoffs or knockouts, qualified/active managers remain alive; others are out.
    if (playoff_gws and gameweek >= min(playoff_gws)) or (knockout_gws and gameweek >= min(knockout_gws)) or (final_gws and gameweek >= min(final_gws)):
        if cs.get('qualified') or cs.get('alive') or cs.get('knockout_alive') or mid in {str(x) for x in cup.get('qualified_ids', []) or []}:
            return "✅"
        return "😵"

    # After groups but before playoff/KO, unqualified managers are out.
    if group_gws and gameweek > max(group_gws):
        return "✅" if (cs.get('qualified') or mid in {str(x) for x in cup.get('qualified_ids', []) or []} or mid in {str(x) for x in cup.get('playoff_candidates', []) or []}) else "😵"

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


def _current_block_record(master, current_gw):
    blocks = master.get('competitions', {}).get('blocks', {}) or {}
    for bname, bdata in blocks.items():
        gws = bdata.get('gws', []) or []
        if current_gw in gws:
            return bname, bdata, gws
    return None, {}, []


def _normalise_lms_names(value):
    """Return display names from LMS eliminated/final records of varied shapes."""
    if not value:
        return []
    if isinstance(value, list):
        out = []
        for item in value:
            out.extend(_normalise_lms_names(item))
        return out
    if isinstance(value, dict):
        name = value.get('name') or value.get('manager_name') or value.get('winner_name')
        return [str(name)] if name else []
    return [str(value)]


def _iter_cup_fixtures(fixtures_obj):
    """Yield cup fixture dictionaries from either list or GW-keyed dict shapes."""
    if isinstance(fixtures_obj, dict):
        for gw_key, gw_fixtures in fixtures_obj.items():
            if isinstance(gw_fixtures, dict):
                gw_fixtures = [gw_fixtures]
            if not isinstance(gw_fixtures, list):
                continue
            for fx in gw_fixtures:
                if isinstance(fx, dict):
                    fx = dict(fx)
                    fx.setdefault('gw', gw_key)
                    yield fx
        return

    if isinstance(fixtures_obj, list):
        for fx in fixtures_obj:
            if isinstance(fx, dict):
                yield fx


def _cup_fixture_round_label(fx):
    return str(fx.get('round') or fx.get('stage') or fx.get('label') or '')


def _cup_final_gws(cup):
    gws = set()
    for fx in _iter_cup_fixtures(cup.get('fixtures', []) or []):
        label = _cup_fixture_round_label(fx).lower()
        if 'final' in label and 'semi' not in label and 'quarter' not in label and 'qf' not in label and 'last 16' not in label and 'playoff' not in label and 'po ' not in label:
            gw = fx.get('gw') or fx.get('gameweek') or fx.get('event')
            try:
                gws.add(int(gw))
            except (TypeError, ValueError):
                pass
    return gws


def _chip_short_code(chip):
    chip_l = str(chip or '').strip().lower().replace(' ', '')
    if chip_l in ('benchboost', 'bboost', 'bb'):
        return 'BB'
    if chip_l in ('freehit', 'fh'):
        return 'FH'
    if chip_l in ('triplecaptain', '3xc', 'tc'):
        return 'TC'
    if chip_l in ('wildcard', 'wc'):
        return 'WC'
    return ''


def _display_captain_points_for_division(row):
    """Display-only captain points for the Divisions tab.

    Uses the active captain for this GW. Unlike Captain King/accolades, this
    intentionally preserves Triple Captain as x3 because the table is showing
    the actual GW score context.
    """
    if not row:
        return 0

    chip_code = _chip_short_code(row.get('chip_used') or row.get('chip') or row.get('active_chip'))
    expected_mult = 3 if chip_code == 'TC' else 2

    def _num(value, default=None):
        try:
            if value in (None, '', '—'):
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    points = _num(row.get('captain_points', row.get('captain_pts')), 0) or 0
    raw = _num(row.get('captain_raw_points'), None)

    orig_cap = str(row.get('original_captain_name', row.get('selected_captain_name', '')) or '').strip()
    orig_vice = str(row.get('original_vice_captain_name', row.get('selected_vice_captain_name', '')) or '').strip()
    active_cap = str(row.get('captain_name', row.get('active_captain_name', '')) or '').strip()
    switched = bool(
        row.get('captain_switched_to_vice')
        or row.get('vice_became_captain')
        or row.get('used_vice_captain')
        or (active_cap and orig_vice and active_cap == orig_vice and active_cap != orig_cap)
    )

    if switched:
        vice_raw = _num(
            row.get('original_vice_captain_raw_points', row.get('selected_vice_captain_raw_points', row.get('vice_captain_raw_points'))),
            None,
        )
        if vice_raw is not None:
            val = vice_raw * expected_mult
            return int(val) if float(val).is_integer() else val
        # Older rows sometimes store the active VC's multiplied score only.
        if points:
            if raw is not None and raw == 0:
                return int(points) if float(points).is_integer() else points
            if raw is not None and points == raw:
                val = raw * expected_mult
                return int(val) if float(val).is_integer() else val
            return int(points) if float(points).is_integer() else points

    if raw is not None:
        # If captain_points is raw x1, multiply it. If it already matches x2/x3,
        # keep it. This handles mixed historical rows safely.
        expected = raw * expected_mult
        if points and abs(points - expected) < 0.001:
            return int(points) if float(points).is_integer() else points
        if points and raw and abs(points - raw) > 0.001:
            return int(points) if float(points).is_integer() else points
        val = expected
        return int(val) if float(val).is_integer() else val

    return int(points) if float(points).is_integer() else points

def _division_captain_html(row):
    captain_name = row.get("captain_name", "—") if row else "—"
    if not captain_name or captain_name == 'None':
        captain_name = '—'
    if captain_name == '—':
        return '—'
    captain_pts = _display_captain_points_for_division(row)
    return f'<span class="hub-captain-wrap"><span class="hub-captain-text">{captain_name} ({captain_pts})</span></span>'



DEBRIEF_DIR = "newsletters"

def _debrief_href(gw):
    try:
        gw_int = int(gw)
    except (TypeError, ValueError):
        gw_int = gw
    return f"{DEBRIEF_DIR}/gw_{gw_int}_poster.html"


def _available_debrief_gws(master, current_gw=None):
    """Return gameweeks that should have a generated debrief page."""
    gws = set()
    gw_history = master.get('gw_history', {}) or {}
    if isinstance(gw_history, dict):
        for key in gw_history.keys():
            if str(key).isdigit():
                gws.add(int(key))
    last_processed = (master.get('league_metadata', {}) or {}).get('last_processed_gw')
    if str(last_processed or '').isdigit():
        gws.add(int(last_processed))
    if str(current_gw or '').isdigit():
        gws.add(int(current_gw))
    return sorted(gws)


def _debriefs_html(master, current_gw=None):
    gws = _available_debrief_gws(master, current_gw)
    if not gws:
        return (
            '<div class="hub-info-pill">'
            '<strong>No debriefs yet.</strong> Weekly debrief links will appear here once gameweeks are generated.'
            '</div>'
        )

    latest = max(gws)
    rows = []
    for gw in sorted(gws, reverse=True):
        latest_cls = ' latest' if gw == latest else ''
        pill = 'Latest' if gw == latest else 'Open'
        rows.append(
            f'<a class="hub-debrief-card{latest_cls}" href="{_debrief_href(gw)}">'
            f'<div class="hub-debrief-main">'
            f'<div class="hub-debrief-title">Gameweek {gw} Debrief</div>'
            f'<div class="hub-debrief-sub">Weekly scores, captaincy, stat leaders and competition updates</div>'
            f'</div>'
            f'<span class="hub-debrief-pill">{pill}</span>'
            f'</a>'
        )
    return '<div class="hub-debrief-grid">' + ''.join(rows) + '</div>'


def _live_status_html(master, current_gw):
    comp = master.get('competitions', {}) or {}
    lms = comp.get('lms', {}) or {}
    cup = comp.get('cup', {}) or {}

    block_name, block_data, block_gws = _current_block_record(master, current_gw)
    block_live = bool(block_name)
    block_final = bool(block_gws and current_gw == block_gws[-1])
    block_winner = block_data.get('winner_name') or block_data.get('winner')
    if block_final and block_winner:
        block_title = f'{block_name} final'
        block_sub = f'Winner: {block_winner}'
        block_class = 'live'
    else:
        block_title = block_name or 'No active block'
        block_sub = f'Active · GWs {block_gws[0]}–{block_gws[-1]}' if block_gws else 'Between blocks'
        block_class = 'live' if block_live else 'quiet'

    lms_schedule = sorted(set(int(gw) for gw in (lms.get('schedule', []) or []) if str(gw).isdigit()))
    lms_final = int(lms.get('final_gw') or 0) if str(lms.get('final_gw') or '').isdigit() else lms.get('final_gw')
    double_lms_gws = set(int(gw) for gw in (lms.get('double_elim_gws', []) or []) if str(gw).isdigit())
    lms_live = current_gw in lms_schedule
    next_lms = next((gw for gw in lms_schedule if gw > current_gw), None)
    alive_count = len(lms.get("active_ids", []) or [])
    next_lms_is_double = next_lms in double_lms_gws
    double_next_week = next_lms_is_double and next_lms == current_gw + 1

    current_elims = _normalise_lms_names((lms.get('eliminated', {}) or {}).get(str(current_gw)) or (lms.get('eliminated', {}) or {}).get(current_gw))

    if lms_final == current_gw and lms.get('winner_name'):
        lms_title = 'Final winner'
        lms_sub = f'🏆 {lms.get("winner_name")}'
        lms_class = 'live'
    elif current_elims:
        lms_title = 'Eliminated'
        lms_sub = ', '.join(current_elims[:2]) + (f' +{len(current_elims)-2}' if len(current_elims) > 2 else '')
        lms_class = 'warn'
    elif current_gw in double_lms_gws:
        lms_title = 'Double elimination'
        lms_sub = f'{alive_count} alive · 2 go out'
        lms_class = 'warn'
    elif lms_live:
        lms_title = 'Elimination week'
        lms_sub = f'{alive_count} alive'
        lms_class = 'warn'
    elif double_next_week:
        lms_title = 'Double elimination next'
        lms_sub = f'GW{next_lms} · 2 go out · {alive_count} alive'
        lms_class = 'warn'
    else:
        lms_title = 'No elimination'
        next_text = f'Next GW{next_lms}' + (' · double' if next_lms_is_double else '') if next_lms else None
        lms_sub = f'{next_text} · {alive_count} alive' if next_text else f'{alive_count} alive · no scheduled GW'
        lms_class = 'idle'

    group_gws = [int(gw) for gw in (cup.get('group_stage_gws', []) or []) if str(gw).isdigit()]
    knockout_gws = [int(gw) for gw in (cup.get('knockout_gws', []) or []) if str(gw).isdigit()]
    playoff_gws = [int(gw) for gw in (cup.get('playoff_gws', []) or []) if str(gw).isdigit()]
    playoff_gw = cup.get('playoff_gw')
    if str(playoff_gw or '').isdigit():
        playoff_gws.append(int(playoff_gw))
    final_gws = _cup_final_gws(cup)
    cup_winner = cup.get('cup_winner_name') or cup.get('winner_name')

    if cup_winner and (not final_gws or current_gw >= min(final_gws)):
        cup_title = 'Cup winner'
        cup_sub = f'🏆 {cup_winner}'
        cup_class = 'live'
    elif current_gw in final_gws:
        cup_title = 'Cup final'
        cup_sub = f'GW{current_gw}'
        cup_class = 'live'
    elif current_gw in group_gws:
        cup_title = 'Group matchday'
        cup_sub = f'GW{current_gw}'
        cup_class = 'live'
    elif current_gw in playoff_gws:
        cup_title = 'Playoff week'
        cup_sub = f'GW{current_gw}'
        cup_class = 'live'
    elif current_gw in knockout_gws:
        cup_title = 'Knockout tie'
        cup_sub = f'GW{current_gw}'
        cup_class = 'live'
    else:
        cup_title = 'Cup idle'
        all_cup_gws = sorted(set(group_gws + knockout_gws + playoff_gws))
        next_cup = next((gw for gw in all_cup_gws if gw > current_gw), None)
        cup_sub = f'Next GW{next_cup}' if next_cup else ('Complete' if cup_winner else 'No scheduled GW')
        cup_class = 'idle'

    cards = [
        ('Gameweek', f'GW{current_gw}', f'<a class="hub-live-link" href="{_debrief_href(current_gw)}">↗ Open debrief</a>', 'live'),
        ('Block', block_title, block_sub, block_class),
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
            f'<th class="hub-number-head hub-gw-head"><span class="hub-gw-wrap"><span class="hub-gw-value">GW</span><span class="hub-gw-chip-slot"></span></span></th>'
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

            captain = _division_captain_html(gw)

            gw_score = gw.get("net_gw_points", "—")
            chip_code = _chip_short_code(gw.get('chip_used') or gw.get('chip') or gw.get('active_chip')) if gw else ''
            chip_html = f'<span class="hub-chip-mini">{chip_code}</span>' if chip_code else ''
            gw_score_html = (
                f'<span class="hub-gw-wrap">'
                f'<span class="hub-gw-value">{gw_score}</span>'
                f'<span class="hub-gw-chip-slot">{chip_html}</span>'
                f'</span>'
            )
            total = item["total"]
            movement_html = _division_movement_html(
                current_positions.get(mid, pos),
                previous_positions.get(mid),
            )

            lms_comp = master.get('competitions', {}).get('lms', {}) or {}
            lms_winner_id = str(lms_comp.get('winner_id', ''))
            lms_winner_name = lms_comp.get('winner_name')
            if (lms_winner_id and mid == lms_winner_id) or (lms_winner_name and m.get('name') == lms_winner_name):
                lms_icon = "🏆"
            elif lms_winner_id or lms_winner_name:
                lms_icon = "🧟"
            else:
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
                f'<td class="hub-number-cell hub-gw-cell">{gw_score_html}</td>'
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


def _lms_html(master, current_gw=None):
    lms = master.get('competitions', {}).get('lms', {}) or {}
    mgrs = master.get('managers', {}) or {}

    def _manager_record(mid):
        return mgrs.get(str(mid), mgrs.get(mid, {})) or {}

    def _manager_name_local(mid):
        rec = _manager_record(mid)
        return rec.get('name', str(mid)) if rec else str(mid)

    def _gw_score(mid, gw):
        row = _gw_row(_manager_record(mid), gw)
        if not row:
            row = _gw_snapshot_row(master, mid, gw)
        return row.get('net_gw_points', row.get('gw_points', row.get('points'))) if row else None

    def _lms_sort_key(mid, gw):
        row = _gw_row(_manager_record(mid), gw) or _gw_snapshot_row(master, mid, gw) or {}
        return (
            _as_num(row.get('net_gw_points', row.get('gw_points', row.get('points', 0))), 0),
            _as_num(row.get('captain_points', row.get('captain_pts', 0))),
            _as_num(row.get('goals_scored', row.get('goals', 0))),
            _as_num(row.get('net_defensive_week', row.get('net_defensive_score', row.get('defensive_score', 0)))),
            _as_num(row.get('vice_captain_raw_points', row.get('vice_captain_points', row.get('vice_points', 0)))),
            -_as_num(row.get('overall_rank', row.get('rank', 999999999)), 999999999),
        )

    active_ids_display = [str(mid) for mid in lms.get('active_ids', []) if str(mid) in mgrs or mid in mgrs]
    # After the LMS final the engine may store no active_ids because the
    # competition is complete. For display purposes, keep the winner in the
    # Still alive panel so the final state does not show 0 alive.
    winner_id_display = lms.get('winner_id')
    if not active_ids_display and winner_id_display and str(winner_id_display) in mgrs:
        active_ids_display = [str(winner_id_display)]

    active_names = sorted(
        [_manager_name_local(mid) for mid in active_ids_display],
        key=lambda n: n.lower()
    )
    active_count = len(active_names)
    current_gw = int(current_gw or master.get('league_metadata', {}).get('last_processed_gw', 0) or 0)
    lms_schedule = sorted(int(gw) for gw in (lms.get('schedule', []) or []) if str(gw).isdigit())
    double_lms_gws = set(int(gw) for gw in (lms.get('double_elim_gws', []) or []) if str(gw).isdigit())
    next_lms_gw = next((gw for gw in lms_schedule if gw > current_gw), None)
    next_lms_is_double = next_lms_gw in double_lms_gws if next_lms_gw else False
    next_lms_value = f'GW{next_lms_gw}' + (' · 2 out' if next_lms_is_double else '') if next_lms_gw else '—'
    double_warning_html = ''
    if next_lms_gw and next_lms_is_double:
        timing = 'next gameweek' if next_lms_gw == current_gw + 1 else f'in GW{next_lms_gw}'
        double_warning_html = (
            f'<div class="hub-lms-warning">'
            f'<div class="hub-lms-warning-title">⚠️ Double elimination {timing}</div>'
            f'<div class="hub-lms-warning-sub">Two managers will be eliminated on the next scheduled LMS week. LMS tie-breakers use that gameweek only.</div>'
            f'</div>'
        )

    active_text = ''.join(f'<span class="hub-lms-pill">{name}</span>' for name in active_names) if active_names else '<span class="hub-lms-muted">No managers still alive</span>'

    def _normalise_lms_elim_items(lms_obj):
        """Return [(gw, name)] for single or multi-elimination LMS records."""
        items = []
        for gw, value in (lms_obj.get('eliminated', {}) or {}).items():
            if isinstance(value, list):
                for name in value:
                    items.append((str(gw), name))
            else:
                items.append((str(gw), value))
        for gw, value in (lms_obj.get('final_eliminated', {}) or {}).items():
            if isinstance(value, list):
                for name in value:
                    items.append((str(gw), name))
            elif value:
                items.append((str(gw), value))
        return sorted(items, key=lambda x: (int(x[0]), str(x[1]).lower()))

    elim_items = _normalise_lms_elim_items(lms)
    eliminated_count = len(elim_items)
    name_to_mid = {mdata.get('name'): str(mid) for mid, mdata in mgrs.items()}

    eliminated_ids = [name_to_mid.get(name) for _, name in elim_items if name_to_mid.get(name)]
    active_ids_now = [str(mid) for mid in (lms.get('active_ids', []) or []) if str(mid) in mgrs or mid in mgrs]
    participant_ids = set(active_ids_now) | set(eliminated_ids)
    if not participant_ids:
        participant_ids = set(str(mid) for mid in mgrs.keys())

    alive_ids = set(participant_ids)
    elim_h = ''

    for g, name in elim_items:
        gw = int(g)
        eliminated_mid = name_to_mid.get(name)
        score = _gw_score(eliminated_mid, gw) if eliminated_mid else None
        score_html = f'<span class="hub-lms-score">{score} pts</span>' if score is not None else '<span class="hub-lms-score muted">—</span>'

        escaped_html = ''
        if eliminated_mid and eliminated_mid in alive_ids:
            active_before_elim = set(alive_ids)
            ranked_this_gw = [
                mid for mid in active_before_elim
                if _gw_score(mid, gw) is not None
            ]
            ranked_this_gw = sorted(ranked_this_gw, key=lambda mid: _lms_sort_key(mid, gw))

            # The scraped-through manager is the manager immediately above the
            # eliminated manager in that week's active-pool ranking.
            escaped_mid = None
            if eliminated_mid in ranked_this_gw:
                elim_idx = ranked_this_gw.index(eliminated_mid)
                if elim_idx + 1 < len(ranked_this_gw):
                    escaped_mid = ranked_this_gw[elim_idx + 1]
            elif ranked_this_gw:
                escaped_mid = ranked_this_gw[0]

            if escaped_mid:
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

        # Only show LMS tie-breaker details when the eliminated manager
        # actually tied on GW points with the manager who scraped through. Do
        # not show generic TB badges just because another unrelated manager had
        # the same score.
        tb_html = ''

        tb_detail_html = ''
        if score is not None and escaped_mid and _as_num(_gw_score(escaped_mid, gw), None) == _as_num(score, None):
            def _lms_row_for(mid):
                return _gw_snapshot_row(master, mid, gw) or _gw_row(_manager_record(mid), gw) or {}

            def _lms_rule_value_from_row(row, rule):
                if rule == 'gw_points':
                    return _as_num(row.get('net_gw_points', row.get('gw_points', row.get('points', 0))))
                if rule == 'captain_points':
                    return _as_num(row.get('captain_points', row.get('captain_pts', 0)))
                if rule == 'goals_scored':
                    return _as_num(row.get('goals_scored', row.get('goals', 0)))
                if rule == 'net_defensive_score':
                    return _as_num(row.get('net_defensive_week', row.get('net_defensive_score', row.get('defensive_score', 0))))
                if rule == 'vice_captain_points':
                    return _as_num(row.get('vice_captain_raw_points', row.get('vice_captain_points', row.get('vice_points', 0))))
                if rule == 'overall_rank':
                    return -_as_num(row.get('overall_rank', row.get('rank', 999999999)), 999999999)
                return 0

            elim_row = _lms_row_for(str(eliminated_mid))
            esc_row = _lms_row_for(str(escaped_mid))
            rule = None
            for candidate_rule in RULES_REFERENCE['lms_tiebreakers']:
                if _lms_rule_value_from_row(elim_row, candidate_rule) != _lms_rule_value_from_row(esc_row, candidate_rule):
                    rule = candidate_rule
                    break
            if rule:
                elim_val = _lms_rule_value_from_row(elim_row, rule)
                esc_val = _lms_rule_value_from_row(esc_row, rule)
                if rule == 'overall_rank':
                    elim_val, esc_val = abs(elim_val), abs(esc_val)
                elim_val = int(elim_val) if float(elim_val).is_integer() else elim_val
                esc_val = int(esc_val) if float(esc_val).is_integer() else esc_val
                tb_detail_html = (
                    f'<div class="hub-lms-escaped hub-lms-tb-detail">'
                    f'<span>⚖️ Tie-breaker: <strong>{TB_LABELS.get(rule, rule)}</strong></span>'
                    f'<span>{_manager_name_local(escaped_mid)} {esc_val} · {name} {elim_val}</span>'
                    f'</div>'
                )

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
            f'{tb_detail_html}'
            f'</div>'
        )

    if lms.get('winner_name'):
        final_gw = lms.get('final_gw') or (lms_schedule[-1] if lms_schedule else current_gw)
        runner = lms.get('runner_up_name') or '—'
        elim_h += (
            f'<div class="hub-lms-elim-wrap hub-lms-final-row">'
            f'<div class="hub-lms-elim-row">'
            f'<span class="hub-lms-gw">GW{final_gw}</span>'
            f'<span class="hub-lms-zombie">🏆</span>'
            f'<span class="hub-lms-name"><strong>{lms.get("winner_name")}</strong> wins LMS</span>'
            f'<span class="hub-lms-score">Winner</span>'
            f'</div>'
            f'<div class="hub-lms-escaped"><span>Runner-up: <strong>{runner}</strong></span><span>Final</span></div>'
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
        f'<div class="hub-lms-count-card"><div class="hub-lms-count-number muted-count">{next_lms_value}</div><div class="hub-lms-count-label">Next LMS GW</div></div>'
        f'</div>'
        f'{double_warning_html}'
        f'<div class="hub-lms-box"><div class="hub-lms-label">Still alive</div><div class="hub-lms-pill-wrap">{active_text}</div></div>'
        f'<div class="hub-lms-history"><div class="hub-lms-label">Elimination history</div>{elim_h}</div>'
    )


def _cup_html(master, current_gw=None):
    cup  = master.get('competitions', {}).get('cup', {}) or {}
    mgrs = master.get('managers', {}) or {}
    current_gw = current_gw or master.get('league_metadata', {}).get('last_processed_gw', 0) or 0
    try:
        current_gw_int = int(current_gw or 0)
    except (TypeError, ValueError):
        current_gw_int = 0

    def _cup_sort_key(item):
        mid, cs = item["manager_id"], item["cup_stats"]
        return tuple(_rule_value(master, mid, rule, cup_stats=cs) for rule in RULES_REFERENCE["cup_group_tiebreakers"])

    def _iter_cup_fixtures(fixtures_obj):
        """Yield cup fixture dictionaries from either list or GW-keyed dict shapes."""
        if isinstance(fixtures_obj, dict):
            for gw_key, gw_fixtures in fixtures_obj.items():
                if isinstance(gw_fixtures, dict):
                    gw_fixtures = [gw_fixtures]
                if not isinstance(gw_fixtures, list):
                    continue
                for fx in gw_fixtures:
                    if isinstance(fx, dict):
                        fx = dict(fx)
                        fx.setdefault('gw', gw_key)
                        yield fx
            return

        if isinstance(fixtures_obj, list):
            for fx in fixtures_obj:
                if isinstance(fx, dict):
                    yield fx

    fixtures_raw = cup.get('fixtures', []) or []
    all_fixtures = list(_iter_cup_fixtures(fixtures_raw))

    def _is_po_sf_fixture(fx):
        label = str(fx.get('round') or '').lower().replace('–', '-').replace('—', '-')
        return ('playoff' in label or label.startswith('po')) and ('sf' in label or 'semi' in label)

    def _fixture_gw(fx):
        gw = fx.get('gw') or fx.get('gameweek') or fx.get('event')
        try:
            return int(gw)
        except (TypeError, ValueError):
            return None

    def _is_group_fixture(fx):
        label = str(fx.get('round') or fx.get('group') or '')
        return bool(fx.get('group')) or 'group' in label.lower()

    def _team_name(value, fallback='—'):
        if value in (None, '', '—'):
            return fallback
        return _manager_name(master, value) if str(value).isdigit() else str(value)

    def _group_fixture_sets(fixtures):
        grouped = defaultdict(list)
        order = []
        for fx in fixtures or []:
            label = fx.get('group') or fx.get('round') or 'Cup'
            if label not in grouped:
                order.append(label)
            grouped[label].append(fx)
        return [(label, grouped[label]) for label in order]

    def _hub_group_title(label):
        return f'<div class="hub-cup-fixture-group-title">{label}</div>' if label else ''

    def _gw_score(mid, gw):
        if mid in (None, '', '—') or gw is None:
            return None
        fx_key = str(mid)
        m = mgrs.get(fx_key, mgrs.get(mid, {})) or {}
        hist = m.get('gw_history', {}) or {}
        row = hist.get(str(gw), hist.get(gw, {})) or {}
        for key in ('net_gw_points', 'points', 'gw_points'):
            if row.get(key) is not None:
                return row.get(key)
        return None

    def _played_count(mid):
        mid = str(mid)
        cs = (mgrs.get(mid, {}) or {}).get('cup_stats', {}) or {}
        stored = cs.get('played', cs.get('cup_played'))
        if stored not in (None, ''):
            try:
                return int(stored)
            except (TypeError, ValueError):
                pass
        count = 0
        for fx in all_fixtures:
            gw = _fixture_gw(fx)
            if gw is None or gw > current_gw_int:
                continue
            if str(fx.get('home')) == mid or str(fx.get('away')) == mid:
                count += 1
        return count

    def _as_int_or_none(value):
        try:
            if value in (None, '', '—'):
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    group_count = len(cup.get('groups', {}) or {})
    auto_qualify = _as_int_or_none(
        cup.get('auto_qualify_places', cup.get('auto_qualify', cup.get('auto_qualifiers_per_group')))
    )
    playoff_spots = _as_int_or_none(cup.get('playoff_spots', cup.get('playoff_count')))

    if auto_qualify is None and group_count:
        knockout_size = _as_int_or_none(cup.get('knockout_size', cup.get('knockout_places'))) or 16
        auto_qualify = max(1, knockout_size // group_count)
        if playoff_spots is None:
            playoff_spots = max(0, knockout_size - (auto_qualify * group_count))

    if auto_qualify is None:
        auto_qualify = '—'
    if playoff_spots is None:
        playoff_spots = 0

    auto_places_int = _as_int_or_none(auto_qualify) or 0
    playoff_spots_int = _as_int_or_none(playoff_spots) or 0
    configured_po_sf = _as_int_or_none(
        cup.get('playoff_sf_places', cup.get('playoff_semifinalists', cup.get('playoff_entrants')))
    )
    if configured_po_sf is not None:
        playoff_sf_places = configured_po_sf
    elif playoff_spots_int:
        playoff_sf_places = min(group_count, max(2, playoff_spots_int * 4))
    else:
        playoff_sf_places = 0
    playoff_final_places = min(playoff_sf_places, playoff_spots_int * 2) if playoff_spots_int else 0
    if playoff_sf_places and not any(_is_po_sf_fixture(fx) for fx in all_fixtures):
        playoff_sf_places = 0

    group_gws = cup.get('group_stage_gws', []) or []
    knockout_gws = cup.get('knockout_gws', []) or []

    overview_cards = [
        f'<div class="hub-cup-stat"><div class="hub-cup-stat-value">{len(cup.get("groups", {}) or {})}</div><div class="hub-cup-stat-label">Groups</div></div>',
        f'<div class="hub-cup-stat"><div class="hub-cup-stat-value">{auto_qualify}</div><div class="hub-cup-stat-label">Auto Q</div></div>',
    ]
    if playoff_sf_places:
        overview_cards.append(
            f'<div class="hub-cup-stat"><div class="hub-cup-stat-value">{playoff_sf_places}</div><div class="hub-cup-stat-label">PO SF</div></div>'
        )
    if playoff_final_places:
        overview_cards.append(
            f'<div class="hub-cup-stat"><div class="hub-cup-stat-value">{playoff_final_places}</div><div class="hub-cup-stat-label">PO F</div></div>'
        )
    overview_cards.append(
        f'<div class="hub-cup-stat"><div class="hub-cup-stat-value">{len(knockout_gws)}</div><div class="hub-cup-stat-label">KO GWs</div></div>'
    )
    overview = f'<div class="hub-cup-overview">{"".join(overview_cards)}</div>' 

    sorted_groups = {}
    fourth_place_candidates = []
    for grp, members in (cup.get('groups', {}) or {}).items():
        group_items = []
        for mid in members:
            m = mgrs.get(str(mid), mgrs.get(mid, {})) or {}
            cs = m.get('cup_stats', {}) or {}
            group_items.append({
                "manager_id": str(mid),
                "name": m.get("name", str(mid)),
                "cup_stats": cs,
                "played": _played_count(mid),
                "match_points": cs.get("match_points", cs.get("group_points", 0)),
            })
        group_items = sorted(group_items, key=_cup_sort_key, reverse=True)
        sorted_groups[grp] = group_items
        if auto_places_int and len(group_items) > auto_places_int:
            fourth_place_candidates.append(group_items[auto_places_int])

    playoff_semifinalist_ids = set()
    if playoff_sf_places:
        fourth_place_candidates = sorted(fourth_place_candidates, key=_cup_sort_key, reverse=True)
        playoff_semifinalist_ids = {item["manager_id"] for item in fourth_place_candidates[:playoff_sf_places]}

    groups_html = ""
    for grp, group_items in sorted_groups.items():
        rows = ""

        for pos, item in enumerate(group_items, start=1):
            cs = item["cup_stats"]
            row_class = ''
            path = ''
            if auto_places_int and pos <= auto_places_int:
                row_class = ' class="hub-cup-row-auto"'
                path = '<span class="hub-cup-path auto">Auto</span>'
            elif playoff_sf_places and pos == auto_places_int + 1 and item["manager_id"] in playoff_semifinalist_ids:
                row_class = ' class="hub-cup-row-playoff"'
                po_label = 'PO SF' if len(cup.get('playoff_gws', []) or []) > 1 else 'PO F'
                path = f'<span class="hub-cup-path playoff">{po_label}</span>'
            elif cs.get('qualified'):
                row_class = ' class="hub-cup-row-auto"'
                path = '<span class="hub-cup-path auto">Q</span>'

            rows += (
                f'<tr{row_class}>'
                f'<td><span class="hub-cup-name">{item["name"]}</span></td>'
                f'<td>{item["played"]}</td>'
                f'<td>{item["match_points"]}</td>'
                f'<td>{cs.get("cup_fpl_points_sum",0)}</td>'
                f'<td>{path}</td>'
                f'</tr>'
            )

        groups_html += (
            f'<div class="hub-cup-group">'
            f'<div class="hub-cup-group-title">{grp}</div>'
            f'<table class="hub-cup-table">'
            f'<colgroup>'
            f'<col class="hub-cup-col-manager"><col class="hub-cup-col-played"><col class="hub-cup-col-points"><col class="hub-cup-col-fpl"><col class="hub-cup-col-q">'
            f'</colgroup>'
            f'<tr><th>Manager</th><th>P</th><th>Pts</th><th>FPL</th><th>Path</th></tr>{rows}'
            f'</table>'
            f'</div>'
        )

    if not groups_html:
        groups_html = '<div class="hub-cup-empty">No cup groups have been configured yet.</div>'

    current_results = []
    upcoming = []
    for fx in all_fixtures:
        gw_int = _fixture_gw(fx)
        if gw_int is None or not _is_group_fixture(fx):
            continue
        if gw_int == current_gw_int:
            current_results.append(fx)
        elif gw_int > current_gw_int:
            upcoming.append((gw_int, fx))

    current_results = sorted(current_results, key=lambda fx: (str(fx.get('group', '')), str(fx.get('home', ''))))
    results_html = ""
    if current_results:
        rows = ""
        for group_label, group_fixtures in _group_fixture_sets(current_results):
            rows += _hub_group_title(group_label)
            for fx in group_fixtures:
                gw = _fixture_gw(fx)
                home_id, away_id = fx.get('home'), fx.get('away')
                home = _team_name(home_id, fx.get('home_name', '—'))
                away = _team_name(away_id, fx.get('away_name', '—'))
                hs = fx.get('home_score') if fx.get('home_score') is not None else _gw_score(home_id, gw)
                aw = fx.get('away_score') if fx.get('away_score') is not None else _gw_score(away_id, gw)
                if hs is not None and aw is not None:
                    h_num = _as_num(hs, 0)
                    a_num = _as_num(aw, 0)
                    if h_num > a_num:
                        home_cls = ' hub-cup-winner'
                        away_cls = ' hub-cup-loser'
                        home_score_cls = ''
                        away_score_cls = ' loser'
                    elif a_num > h_num:
                        home_cls = ' hub-cup-loser'
                        away_cls = ' hub-cup-winner'
                        home_score_cls = ' loser'
                        away_score_cls = ''
                    else:
                        home_cls = away_cls = ' hub-cup-draw'
                        home_score_cls = away_score_cls = ''
                    score = (
                        f'<span class="hub-cup-score-part{home_score_cls}">{hs}</span>'
                        f'<span class="hub-cup-score-sep">–</span>'
                        f'<span class="hub-cup-score-part{away_score_cls}">{aw}</span>'
                    )
                    score_cls = 'hub-cup-result-score'
                else:
                    score = 'v'
                    home_cls = away_cls = ''
                    score_cls = 'hub-cup-result-score muted'
                rows += (
                    f'<div class="hub-cup-result-row">'
                    f'<span class="hub-cup-side{home_cls}">{home}</span>'
                    f'<span class="{score_cls}">{score}</span>'
                    f'<span class="hub-cup-side away{away_cls}">{away}</span>'
                    f'</div>'
                )
        results_html = f'<div class="hub-cup-results-card">{rows}</div>'

    upcoming = sorted(upcoming, key=lambda x: (x[0], str(x[1].get('group', '')), str(x[1].get('home', ''))))
    by_gw = defaultdict(list)
    for gw, fx in upcoming:
        by_gw[gw].append(fx)

    fixtures_html = ""
    for gw in sorted(by_gw.keys()):
        rows = ""
        for group_label, group_fixtures in _group_fixture_sets(by_gw[gw]):
            rows += _hub_group_title(group_label)
            for fx in group_fixtures:
                home = _team_name(fx.get('home'), fx.get('home_name', '—'))
                away = _team_name(fx.get('away'), fx.get('away_name', '—'))
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

    completed_by_gw = defaultdict(list)
    for fx in all_fixtures:
        gw_int = _fixture_gw(fx)
        if gw_int is None or gw_int >= current_gw_int or not _is_group_fixture(fx):
            continue
        home_id, away_id = fx.get('home'), fx.get('away')
        hs = fx.get('home_score') if fx.get('home_score') is not None else _gw_score(home_id, gw_int)
        aw = fx.get('away_score') if fx.get('away_score') is not None else _gw_score(away_id, gw_int)
        if hs is None or aw is None:
            continue
        completed_by_gw[gw_int].append(fx)

    group_results_html = ""
    for gw in sorted(completed_by_gw.keys()):
        rows = ""
        sorted_completed = sorted(completed_by_gw[gw], key=lambda x: (str(x.get('group','')), str(x.get('home',''))))
        for group_label, group_fixtures in _group_fixture_sets(sorted_completed):
            rows += _hub_group_title(group_label)
            for fx in group_fixtures:
                home_id, away_id = fx.get('home'), fx.get('away')
                home = _team_name(home_id, fx.get('home_name', '—'))
                away = _team_name(away_id, fx.get('away_name', '—'))
                hs = fx.get('home_score') if fx.get('home_score') is not None else _gw_score(home_id, gw)
                aw = fx.get('away_score') if fx.get('away_score') is not None else _gw_score(away_id, gw)
                h_num, a_num = _as_num(hs, 0), _as_num(aw, 0)
                if h_num > a_num:
                    home_cls, away_cls = ' hub-cup-winner', ' hub-cup-loser'
                    home_score_cls, away_score_cls = '', ' loser'
                elif a_num > h_num:
                    home_cls, away_cls = ' hub-cup-loser', ' hub-cup-winner'
                    home_score_cls, away_score_cls = ' loser', ''
                else:
                    home_cls = away_cls = ' hub-cup-draw'
                    home_score_cls = away_score_cls = ''
                score_html = (
                    f'<span class="hub-cup-score-part{home_score_cls}">{hs}</span>'
                    f'<span class="hub-cup-score-sep">–</span>'
                    f'<span class="hub-cup-score-part{away_score_cls}">{aw}</span>'
                )
                rows += (
                    f'<div class="hub-cup-result-row">'
                    f'<span class="hub-cup-side{home_cls}">{home}</span>'
                    f'<span class="hub-cup-result-score">{score_html}</span>'
                    f'<span class="hub-cup-side away{away_cls}">{away}</span>'
                    f'</div>'
                )
        group_results_html += f'<details class="hub-cup-subdetails"><summary>GW{gw}</summary><div class="hub-cup-results-card">{rows}</div></details>'

    bracket_html = _cup_bracket_html(master, current_gw)

    group_open = ' open' if not current_results else ''
    results_section = ''
    if results_html:
        results_section = f'<details class="hub-cup-details" open><summary>GW{current_gw_int} results</summary>{results_html}</details>'
    group_results_section = f'<details class="hub-cup-details"><summary>Group results</summary>{group_results_html}</details>' if group_results_html else ''
    fixtures_section = ''
    if fixtures_html:
        fixtures_open = ' open' if not current_results and upcoming else ''
        fixtures_section = f'<details class="hub-cup-details"{fixtures_open}><summary>Upcoming fixtures</summary>{fixtures_html}</details>'
    bracket_open = ' open' if not current_results and not upcoming else ''
    return (
        f'{overview}'
        f'<details class="hub-cup-details"{group_open}><summary>Group standings</summary>{groups_html}</details>'
        f'{results_section}'
        f'{group_results_section}'
        f'{fixtures_section}'
        f'<details class="hub-cup-details"{bracket_open}><summary>Knockout bracket</summary>{bracket_html}</details>'
    )

def _cup_bracket_html(master, current_gw=None):
    cup = master.get('competitions', {}).get('cup', {}) or {}
    fixtures = cup.get('fixtures', []) or []
    bracket = cup.get('knockout_bracket', {}) or {}
    results = cup.get('knockout_results', {}) or {}

    def _iter_fixture_dicts(fixtures_obj):
        """Yield fixture dictionaries from either a flat list or GW-keyed dict."""
        if isinstance(fixtures_obj, dict):
            for gw_key, gw_fixtures in fixtures_obj.items():
                if isinstance(gw_fixtures, dict):
                    gw_fixtures = [gw_fixtures]
                if not isinstance(gw_fixtures, list):
                    continue
                for fx in gw_fixtures:
                    if isinstance(fx, dict):
                        item = dict(fx)
                        item.setdefault('gw', gw_key)
                        yield item
            return
        if isinstance(fixtures_obj, list):
            for fx in fixtures_obj:
                if isinstance(fx, dict):
                    yield fx

    def _result_records(results_obj):
        if isinstance(results_obj, dict):
            for gw_key, gw_results in results_obj.items():
                if isinstance(gw_results, dict):
                    gw_results = [gw_results]
                if not isinstance(gw_results, list):
                    continue
                for res in gw_results:
                    if isinstance(res, dict):
                        item = dict(res)
                        item.setdefault('gw', gw_key)
                        yield item

    def _round_base(label):
        lower = str(label or '').lower().replace('—', '-').replace('–', '-')
        if 'playoff' in lower or lower.startswith('po '):
            if 'sf' in lower or 'semi' in lower:
                return 'Playoff SF'
            if 'final' in lower or lower in {'po f', 'pof'}:
                return 'Playoff Final'
            return 'Playoff'
        if 'last 16' in lower:
            return 'Last 16'
        if 'quarter' in lower or lower.startswith('qf'):
            return 'Quarter-final'
        if 'semi' in lower or lower.startswith('sf'):
            return 'Semi-final'
        if 'final' in lower:
            return 'Final'
        return str(label or 'Knockout')

    round_order = {
        'Playoff SF': 10,
        'Playoff Final': 20,
        'Last 16': 30,
        'Quarter-final': 40,
        'Semi-final': 50,
        'Final': 60,
    }

    def _round_label(label):
        base = _round_base(label)
        lower = str(label or '').lower()
        if base in {'Last 16', 'Quarter-final', 'Semi-final'}:
            if '1st' in lower:
                return f'{base} - 1st Leg'
            if '2nd' in lower:
                return f'{base} - 2nd Leg'
        return base

    def _round_sort_key(label):
        base = _round_base(label)
        lower = str(label or '').lower()
        leg = 0
        if '1st' in lower:
            leg = 1
        elif '2nd' in lower:
            leg = 2
        return (round_order.get(base, 999), leg, str(label))

    def _team_label(value, fallback='TBC'):
        if value in (None, '', '—'):
            return fallback
        return _manager_name(master, value) if str(value).isdigit() else str(value)

    def _score_for(fx, side, gw):
        direct = fx.get(f'{side}_score')
        if direct is not None:
            return direct
        gw_value = fx.get(f'{side}_gw')
        if gw_value is not None:
            return gw_value
        mid = fx.get(side) or fx.get(f'{side}_id')
        if mid in (None, '', '—') or gw in (None, '', '—'):
            return None
        row = _gw_snapshot_row(master, str(mid), gw) or _gw_row(_manager(master, str(mid)), gw) or {}
        return row.get('net_gw_points', row.get('gw_points', row.get('points')))

    items = []
    seen = set()

    # Fixtures are the primary source because they include upcoming rounds too.
    for fx in _iter_fixture_dicts(fixtures):
        label = str(fx.get('round') or '')
        if not label or 'group' in label.lower():
            continue
        gw = fx.get('gw') or fx.get('gameweek') or fx.get('event')
        key = (str(gw), str(fx.get('tie_id', '')), str(fx.get('home', fx.get('home_id', ''))), str(fx.get('away', fx.get('away_id', ''))), label)
        seen.add(key)
        items.append({'label': _round_label(label), 'gw': gw, 'fixture': fx})

    # Results backfill clear winners/progression even if fixture scores were not persisted.
    all_result_sources = []
    if results:
        all_result_sources.append(results)
    if cup.get('playoff_results'):
        all_result_sources.append(cup.get('playoff_results'))
    for _results_source in all_result_sources:
      for res in _result_records(_results_source):
        label = str(res.get('round') or '')
        if not label or 'group' in label.lower():
            continue
        gw = res.get('gw') or res.get('gameweek') or res.get('event')
        key = (str(gw), str(res.get('tie_id', '')), str(res.get('home_id', res.get('home', ''))), str(res.get('away_id', res.get('away', ''))), label)
        if key in seen:
            # Merge result into matching item.
            for item in items:
                fx = item['fixture']
                if (str(item.get('gw')) == str(gw) and str(fx.get('tie_id', '')) == str(res.get('tie_id', ''))):
                    fx.update({
                        'home_score': res.get('home_gw', res.get('home_score')),
                        'away_score': res.get('away_gw', res.get('away_score')),
                        'home_agg': res.get('home_agg'),
                        'away_agg': res.get('away_agg'),
                        'winner_id': res.get('winner_id'),
                        'winner_name': res.get('winner_name'),
                        'decided': res.get('decided'),
                    })
                    break
            continue
        fx = {
            'gw': gw,
            'round': label,
            'tie_id': res.get('tie_id'),
            'home': res.get('home_id'),
            'away': res.get('away_id'),
            'home_name': res.get('home_name'),
            'away_name': res.get('away_name'),
            'home_score': res.get('home_gw', res.get('home_score')),
            'away_score': res.get('away_gw', res.get('away_score')),
            'home_agg': res.get('home_agg'),
            'away_agg': res.get('away_agg'),
            'winner_id': res.get('winner_id'),
            'winner_name': res.get('winner_name'),
            'decided': res.get('decided'),
        }
        items.append({'label': _round_label(label), 'gw': gw, 'fixture': fx})

    # Fallback for bare bracket dictionaries/lists.
    if not items and bracket:
        if isinstance(bracket, dict):
            for label, ties in bracket.items():
                iterable = ties.values() if isinstance(ties, dict) else (ties or [])
                for fx in iterable:
                    if isinstance(fx, dict):
                        items.append({'label': _round_label(fx.get('round', label)), 'gw': fx.get('gw'), 'fixture': fx})
        elif isinstance(bracket, list):
            for fx in bracket:
                if isinstance(fx, dict):
                    items.append({'label': _round_label(fx.get('round', 'Knockout')), 'gw': fx.get('gw'), 'fixture': fx})

    if not items:
        return '<div class="hub-cup-empty">The knockout bracket will appear once qualifiers are confirmed.</div>'

    by_round = defaultdict(list)
    for item in items:
        by_round[item['label']].append(item)

    html = ''
    for label in sorted(by_round.keys(), key=_round_sort_key):
        rows = ''
        for item in sorted(by_round[label], key=lambda x: (int(x.get('gw') or 99), str(x['fixture'].get('tie_id', '')))):
            fx = item['fixture']
            gw = item.get('gw')
            home_id = fx.get('home') or fx.get('home_id')
            away_id = fx.get('away') or fx.get('away_id')
            home = _team_label(home_id, fx.get('home_name', 'TBC'))
            away = _team_label(away_id, fx.get('away_name', 'TBC'))
            hs = _score_for(fx, 'home', gw)
            aw = _score_for(fx, 'away', gw)
            home_agg = fx.get('home_agg')
            away_agg = fx.get('away_agg')
            winner = str(fx.get('winner_id') or '')
            decided = bool(fx.get('decided') or winner)

            home_cls = away_cls = ''
            if winner:
                home_cls = ' hub-bracket-winner' if str(home_id) == winner else ' hub-bracket-loser'
                away_cls = ' hub-bracket-winner' if str(away_id) == winner else ' hub-bracket-loser'
            elif hs is not None and aw is not None:
                if _as_num(hs) > _as_num(aw):
                    home_cls, away_cls = ' hub-bracket-winner', ' hub-bracket-loser'
                elif _as_num(aw) > _as_num(hs):
                    home_cls, away_cls = ' hub-bracket-loser', ' hub-bracket-winner'

            home_score_cls = ' loser' if 'hub-bracket-loser' in home_cls else ''
            away_score_cls = ' loser' if 'hub-bracket-loser' in away_cls else ''
            if home_agg is not None and away_agg is not None and hs is not None and aw is not None:
                score = (
                    f'<span class="hub-bracket-score-main">'
                    f'<span class="hub-bracket-score-part{home_score_cls}">{hs}</span>'
                    f'<span class="hub-cup-score-sep">–</span>'
                    f'<span class="hub-bracket-score-part{away_score_cls}">{aw}</span>'
                    f'</span>'
                    f'<span class="hub-bracket-score-sub">({home_agg}–{away_agg} agg)</span>'
                )
            elif home_agg is not None and away_agg is not None:
                home_agg_cls = home_score_cls
                away_agg_cls = away_score_cls
                score = (
                    f'<span class="hub-bracket-score-main">'
                    f'<span class="hub-bracket-score-part{home_agg_cls}">{home_agg}</span>'
                    f'<span class="hub-cup-score-sep">–</span>'
                    f'<span class="hub-bracket-score-part{away_agg_cls}">{away_agg}</span>'
                    f'</span><span class="hub-bracket-score-sub">agg</span>'
                )
            elif hs is not None and aw is not None:
                score = (
                    f'<span class="hub-bracket-score-main">'
                    f'<span class="hub-bracket-score-part{home_score_cls}">{hs}</span>'
                    f'<span class="hub-cup-score-sep">–</span>'
                    f'<span class="hub-bracket-score-part{away_score_cls}">{aw}</span>'
                    f'</span>'
                )
            else:
                score = f'GW{gw}' if gw else 'v'

            progress = ''
            if winner:
                progress_word = 'wins!' if _round_base(label) == 'Final' else 'advances'
                progress = f'<div class="hub-bracket-progress">{_team_label(winner)} {progress_word}</div>'

            rows += (
                f'<div class="hub-bracket-row">'
                f'<span class="hub-bracket-team{home_cls}">{home}</span>'
                f'<span class="hub-bracket-score">{score}</span>'
                f'<span class="hub-bracket-team away{away_cls}">{away}</span>'
                f'</div>'
                f'{progress}'
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

        # Completed blocks may reset current_block_points to 0, so prefer
        # the named block snapshot when it exists. Live/current blocks still
        # fall back to current_block_points.
        if isinstance(block_stats.get(bname), dict):
            b = block_stats.get(bname, {})
            return b.get('points', b.get('total_points', 0))

        # For completed blocks current_block_points may have reset to 0. If we
        # know the block GWs, rebuild the block total from GW history before
        # falling back to the live counter.
        total = 0
        history = mdata.get('gw_history', {}) or {}
        has_history = False
        for gw in gws:
            row = history.get(str(gw), history.get(gw, {})) or {}
            if row:
                has_history = True
            total += row.get('net_gw_points', row.get('points', row.get('gw_points', 0)))
        if has_history:
            return total

        if block_stats.get('current_block_points') is not None:
            return block_stats.get('current_block_points', 0)

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
                    RULES_REFERENCE["block_tiebreakers"][1:],
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
                    RULES_REFERENCE["block_tiebreakers"][1:],
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
            runner_entry = top3[1] if len(top3) > 1 else {}
            runner_up = bdata.get('runner_up_name') or runner_entry.get('name', '')
            runner_points = runner_entry.get('points', runner_entry.get('total_points'))
            runner_points_html = f'<span class="hub-block-gap">{runner_points} pts</span>' if runner_points not in (None, '', '—') else ''
            runner_html = (
                f'<div class="hub-block-runner">'
                f'<span>🥈 Runner-up</span>'
                f'<strong>{runner_up}</strong>'
                f'{runner_points_html}'
                f'</div>'
                if runner_up else ''
            )
            body = (
                f'<div class="hub-block-winner">'
                f'<span>🏅 Winner</span>'
                f'<strong>{won}</strong>'
                f'</div>'
                f'{runner_html}'
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



AWARD_EMOJI = {
    "Golden Boot": "⚽",
    "Playmaker": "🎯",
    "Golden Glove": "🧤",
    "Captain King": "🧢",
    "Bonus Magnet": "🧲",
    "Card Dealer": "🟨",
    "Transfer Wizard": "🪄",
    "Best Transfer": "📈",
    "Worst Transfer": "📉",
    "Highest GW Score": "🚀",
    "Lowest GW Score": "🕳️",
    "Best Captain Haul": "🫡",
    "Bench Warmer": "🪑",
    "Talent Scout": "🔎",
    "Chip Master": "🎲",
    "Hot Streak": "🔥",
    "Out of Form": "🥶",
    "Best Wildcard": "🃏",
    "Best Free Hit": "⚡",
    "Best Triple Captain": "🔱",
    "Best Bench Boost": "💺",
    "Best Vice Captain Haul": "🛟",
    "Best Auto-Sub": "🔁",
    "Best Left Behind": "😬",
    "Most GW Wins": "🏁",
    "Most Podiums": "🥈",
    "Most Wooden Spoons": "🥄",
    "Most Golden Armbands": "🥇",
    "Most Differential Captain Armbands": "🎲",
    "Most Captain Duds": "👻",
    "Most Popular Armband": "❤️",
    "Most Top Scorer Picks": "🌟",
    "Most Best Differential Picks": "💎",
    "Best Pick": "🏅",
    "Best Differential Pick": "💠",
    "Best Differential Captain": "🎲",
    "Most Auto-Sub Points": "🎁",
    "Total Auto-Sub Points": "🎁",
}

AWARD_INFO = {
    "Golden Boot": "Most goals scored by players in managers' final XIs across the season.",
    "Playmaker": "Most assists from players in managers' final XIs across the season.",
    "Golden Glove": "Best net defensive score across the season.",
    "Captain King": "Most captain points using normal x2 captaincy scoring.",
    "Bonus Magnet": "Most FPL bonus points collected across the season.",
    "Card Dealer": "Most yellow/red cards collected across the season. Lower is better; this highlights the biggest offenders.",
    "Transfer Wizard": "Season-long net transfer gain after hits, excluding Free Hit and Wildcard weeks.",
    "Best Transfer": "Best single-GW transfer gain after hits, excluding Free Hit and Wildcard weeks. Shows the transfer and GW.",
    "Worst Transfer": "Worst single-GW transfer loss after hits, excluding Free Hit and Wildcard weeks. Shows the transfer and GW.",
    "Highest GW Score": "Highest single gameweek score posted this season.",
    "Lowest GW Score": "Lowest single gameweek score posted this season.",
    "Best Captain Haul": "Best captain return scored at x2, even on Triple Captain weeks.",
    "Bench Warmer": "Most points left on the bench across the season. Lower is better; this highlights the biggest offenders.",
    "Talent Scout": "Points from final-XI players started by under 20% of the league.",
    "Chip Master": "Best total chip impact across all chip events.",
    "Hot Streak": "Longest run beating the league average, even if the run has ended.",
    "Out of Form": "Longest run below the league average, even if the run has ended.",
    "Best Wildcard": "Best stored Wildcard impact from a single GW.",
    "Best Free Hit": "Best stored Free Hit impact from a single GW.",
    "Best Triple Captain": "Best Triple Captain impact, measured as extra captain points.",
    "Best Bench Boost": "Best Bench Boost impact, measured as final bench points.",
    "Best Vice Captain Haul": "Best vice-captain auto-swap return when the vice became captain.",
    "Best Auto-Sub": "Best return from a player who began on the bench but entered the final XI. Shows the player and GW.",
    "Best Left Behind": "Highest single scorer left on a manager's bench, excluding Bench Boost weeks. Shows the player and GW.",
    "Most GW Wins": "Most gameweeks finished top of the full league standings for that GW.",
    "Most Podiums": "Most top-three gameweek finishes across the season.",
    "Most Wooden Spoons": "Most gameweeks finished bottom of the full league standings for that GW.",
    "Most Golden Armbands": "Most gameweeks with the best captaincy return, using normal x2 scoring.",
    "Most Differential Captain Armbands": "Most times captaining a player selected by under 20% of the league that GW.",
    "Most Captain Duds": "Most gameweeks with the lowest captaincy return.",
    "Most Popular Armband": "Most times a manager backed one of the league's most popular captains that GW.",
    "Most Top Scorer Picks": "Most times a manager started one of the highest-scoring players of the GW.",
    "Most Best Differential Picks": "Most times a manager started one of the best under-20% selected players of the GW.",
    "Best Pick": "Best single-GW player return in a manager's final XI. Shows the player and GW.",
    "Best Differential Pick": "Best single-GW under-20% selected player return in a manager's final XI. Shows the player and GW.",
    "Best Differential Captain": "Best captain return from an active captain selected by under 20% of the league that GW.",
    "Most Auto-Sub Points": "Most total points gained from players auto-subbed into final XIs across the season.",
    "Total Auto-Sub Points": "Most total points gained from players auto-subbed into final XIs across the season.",
}


def _manager_history_rows(manager):
    history = manager.get('gw_history', {}) or {}
    rows = []
    if isinstance(history, dict):
        for gw, row in history.items():
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _normalised_best_captain_haul(manager):
    """Best captain haul using normal x2 scoring, even on Triple Captain weeks."""
    rows = _manager_history_rows(manager)
    best = 0
    for row in rows:
        best = max(best, _row_captain_score_x2(row))
    # If history exists, trust the normalised history value so Triple Captain
    # weeks are capped at normal x2 and vice-captain auto-swaps are counted.
    if rows:
        return best
    season = manager.get('season_totals', {}) or {}
    return season.get('best_captain_score', 0) or 0


def _normalised_total_captain_points(manager):
    """Season captain total using normal active captain x2 scoring.

    Some older masters stored raw captain points in total_captain_pts, which
    made the Captain King wooden-spoon row look like x1 scoring. If GW
    history exists, rebuild the total from each active captain row instead.
    """
    rows = _manager_history_rows(manager)
    if rows:
        return sum(_row_captain_score_x2(row) for row in rows)
    season = manager.get('season_totals', {}) or {}
    return season.get('total_captain_pts', season.get('captain_points_total', 0)) or 0


def _autosub_score_from_row(row):
    stored = row.get('best_sub_score', row.get('best_auto_sub_score', row.get('best_autosub_score')))
    if stored not in (None, ''):
        return stored or 0
    final_ids = {p.get('id') for p in (row.get('starting_xi_players', []) or []) if isinstance(p, dict) and p.get('id') is not None}
    best = 0
    for p in row.get('squad_players', []) or []:
        if not isinstance(p, dict):
            continue
        was_benched = (p.get('is_starting') is False) or (p.get('original_position', 99) > 11)
        if p.get('id') in final_ids and was_benched:
            best = max(best, p.get('points', p.get('total_points', 0)) or 0)
    return best


def _best_autosub_from_history(manager):
    best = 0
    for row in _manager_history_rows(manager):
        best = max(best, _autosub_score_from_row(row))
    season = manager.get('season_totals', {}) or {}
    return max(best, season.get('best_auto_sub_score', season.get('best_autosub_score', 0)) or 0)



def _best_autosub_detail_from_history(manager):
    best = 0
    best_detail = ''
    for row in _manager_history_rows(manager):
        try:
            gw = row.get('gw') or row.get('gameweek') or row.get('event')
        except AttributeError:
            gw = None
        candidates = []
        for sub_event in row.get('auto_subs', []) or []:
            if isinstance(sub_event, dict):
                name = sub_event.get('name') or sub_event.get('player_name') or sub_event.get('web_name') or sub_event.get('element_name') or 'Auto-sub'
                points = sub_event.get('points', sub_event.get('total_points', 0)) or 0
                candidates.append((points, name))
        if not candidates:
            final_ids = {p.get('id') for p in (row.get('starting_xi_players', []) or []) if isinstance(p, dict) and p.get('id') is not None}
            for p in row.get('squad_players', []) or []:
                if not isinstance(p, dict):
                    continue
                was_benched = (p.get('is_starting') is False) or ((p.get('original_position', 99) or 99) > 11)
                made_final = bool(p.get('is_final_xi')) or p.get('id') in final_ids
                if was_benched and made_final:
                    name = p.get('name') or p.get('web_name') or p.get('player_name') or 'Auto-sub'
                    points = p.get('points', p.get('total_points', 0)) or 0
                    candidates.append((points, name))
        if candidates:
            points, name = max(candidates, key=lambda x: x[0])
            if points > best:
                best = points
                best_detail = f'{name} · GW{gw}' if gw else name
    season = manager.get('season_totals', {}) or {}
    stored = season.get('best_auto_sub_detail', season.get('best_autosub_detail', ''))
    if stored and (season.get('best_auto_sub_score', season.get('best_autosub_score', 0)) or 0) >= best:
        return stored
    return best_detail


def _best_left_behind_from_history(manager):
    best = 0
    for row in _manager_history_rows(manager):
        chip = str(row.get('chip_used', row.get('chip', ''))).lower()
        if chip in ('bench boost', 'benchboost', 'bboost'):
            continue
        stored = row.get('best_bench_pts')
        if stored not in (None, ''):
            best = max(best, stored or 0)
            continue
        final_ids = {p.get('id') for p in (row.get('starting_xi_players', []) or []) if isinstance(p, dict) and p.get('id') is not None}
        for p in row.get('squad_players', []) or []:
            if not isinstance(p, dict):
                continue
            is_bench = ((p.get('position', 0) or 0) > 11) or ((p.get('original_position', 0) or 0) > 11)
            if is_bench and p.get('id') not in final_ids:
                best = max(best, p.get('points', p.get('total_points', 0)) or 0)
    season = manager.get('season_totals', {}) or {}
    return max(best, season.get('best_left_behind_score', season.get('best_bench_pts', 0)) or 0)


def _best_left_behind_detail_from_history(manager):
    best = 0
    detail = ''
    for row in _manager_history_rows(manager):
        chip = str(row.get('chip_used', row.get('chip', ''))).lower()
        if chip in ('bench boost', 'benchboost', 'bboost'):
            continue
        gw = row.get('gw') or row.get('gameweek') or row.get('event')
        name = row.get('best_bench_name')
        pts = row.get('best_bench_pts')
        if name and pts not in (None, '') and (pts or 0) > best:
            best = pts or 0
            detail = f'{name} · GW{gw}' if gw else name
            continue
        final_ids = {p.get('id') for p in (row.get('starting_xi_players', []) or []) if isinstance(p, dict) and p.get('id') is not None}
        for p in row.get('squad_players', []) or []:
            if not isinstance(p, dict):
                continue
            is_bench = ((p.get('position', 0) or 0) > 11) or ((p.get('original_position', 0) or 0) > 11)
            points = p.get('points', p.get('total_points', 0)) or 0
            if is_bench and p.get('id') not in final_ids and points > best:
                best = points
                pname = p.get('name') or p.get('web_name') or p.get('player_name') or 'Bench player'
                detail = f'{pname} · GW{gw}' if gw else pname
    season = manager.get('season_totals', {}) or {}
    stored = season.get('best_left_behind_detail', season.get('best_bench_detail', ''))
    if stored and (season.get('best_left_behind_score', season.get('best_bench_pts', 0)) or 0) >= best:
        return stored
    return detail

def _total_autosub_from_history(manager):
    rows = _manager_history_rows(manager)
    if rows:
        return sum((_autosub_score_from_row(row) or 0) for row in rows)
    season = manager.get('season_totals', {}) or {}
    return season.get('total_auto_sub_points', season.get('total_autosub_points', 0)) or 0


def _transfer_wizard_from_history(manager):
    total = 0
    rows = _manager_history_rows(manager)
    found = False
    for row in rows:
        chip = str(row.get('chip_used', row.get('chip', 'None'))).lower()
        if chip in ('free hit', 'freehit', 'wildcard'):
            continue
        report = row.get('transfer_report') or {}
        if 'net_transfer_points' in row or 'net_transfer_points_gained' in row or 'net_gain' in report:
            found = True
            total += (
                row.get('net_transfer_points', row.get('net_transfer_points_gained', None))
                if row.get('net_transfer_points', row.get('net_transfer_points_gained', None)) is not None
                else report.get('net_gain', 0)
            ) or 0
    season = manager.get('season_totals', {}) or {}
    stored = season.get('net_transfer_points_gained')
    return total if found else (stored or 0)




def _normalise_transfer_detail(detail):
    """Convert older one-line stored transfer details into the new multiline format."""
    if not detail:
        return ''
    detail = str(detail)
    if '<br>' in detail or '\n' in detail:
        return detail
    import re
    gw_match = re.search(r'\s*[·-]\s*GW(\d+)\s*$', detail)
    gw = gw_match.group(1) if gw_match else None
    body = detail[:gw_match.start()].strip() if gw_match else detail.strip()
    parts = [part.strip() for part in body.split(',') if part.strip()]
    lines = []
    if gw:
        lines.append(f'GW{gw}')
    for part in parts:
        lines.append(part)
    return '<br>'.join(lines) if lines else detail

def _transfer_detail_from_report(row, gw):
    """Return a compact multi-line transfer detail for accolade cards.

    Format:
    GW3
    Wirtz (3) → Semenyo (2) -1
    Wan-Bissaka (0) → Cash (0) +0
    """
    report = row.get('transfer_report') or {}
    ins = report.get('ins') or row.get('transfers_in') or []
    outs = report.get('outs') or row.get('transfers_out') or []

    def _player_parts(item):
        if isinstance(item, dict):
            name = item.get('name') or item.get('web_name') or item.get('player_name') or item.get('element_name') or 'Player'
            pts = item.get('points', item.get('gw_points', item.get('event_points', item.get('total_points'))))
            pts_num = None
            if pts not in (None, '', '—'):
                pts_num = int(_as_num(pts, 0))
            return name, pts_num
        return (str(item), None) if item else ('', None)

    ins_p = [_player_parts(item) for item in ins]
    outs_p = [_player_parts(item) for item in outs]
    ins_p = [p for p in ins_p if p[0]]
    outs_p = [p for p in outs_p if p[0]]

    def _label(parts):
        name, pts = parts
        return f'{name} ({pts})' if pts is not None else name

    lines = []
    hit_cost = report.get('cost', row.get('net_transfer_cost', row.get('transfer_cost', 0))) or 0
    try:
        hit_cost = int(float(hit_cost))
    except (TypeError, ValueError):
        hit_cost = 0

    if gw:
        gw_line = f'GW{gw}'
        if hit_cost > 0:
            gw_line += f' (Inc. -{hit_cost})'
        lines.append(gw_line)

    max_len = max(len(ins_p), len(outs_p))
    if max_len:
        for i in range(min(max_len, 3)):
            in_item = ins_p[i] if i < len(ins_p) else None
            out_item = outs_p[i] if i < len(outs_p) else None
            if in_item and out_item:
                delta = ''
                if in_item[1] is not None and out_item[1] is not None:
                    diff = int(in_item[1] - out_item[1])
                    delta = f' {diff:+d}'
                lines.append(f'{_label(out_item)} → {_label(in_item)}{delta}')
            elif in_item:
                lines.append(f'In {_label(in_item)}')
            elif out_item:
                lines.append(f'Out {_label(out_item)}')
    else:
        lines.append('Transfer')

    return '<br>'.join(lines)

def _transfer_event_from_history(manager, mode='best'):
    rows = _manager_history_rows(manager)
    best_score = None
    best_detail = ''
    for row in rows:
        chip = str(row.get('chip_used', row.get('chip', 'None'))).lower()
        if chip in ('free hit', 'freehit', 'wildcard'):
            continue
        report = row.get('transfer_report') or {}
        if 'net_transfer_points' in row or 'net_transfer_points_gained' in row:
            score = row.get('net_transfer_points', row.get('net_transfer_points_gained', 0)) or 0
        elif 'net_gain' in report:
            score = report.get('net_gain', 0) or 0
        else:
            continue
        if score == 0:
            continue
        gw = row.get('gw') or row.get('gameweek') or row.get('event')
        if best_score is None or (mode == 'best' and score > best_score) or (mode == 'worst' and score < best_score):
            best_score = score
            best_detail = _transfer_detail_from_report(row, gw)
    if best_score is None:
        season = manager.get('season_totals', {}) or {}
        key = 'best_transfer_score' if mode == 'best' else 'worst_transfer_score'
        detail_key = 'best_transfer_detail' if mode == 'best' else 'worst_transfer_detail'
        stored = season.get(key)
        if stored in (None, '', 0):
            return 0, ''
        return stored, _normalise_transfer_detail(season.get(detail_key, ''))
    return best_score, best_detail

def _best_chip_metric(manager, chip_name):
    chip_stats = manager.get('chip_stats', {}) or manager.get('chips', {}) or {}
    wanted = chip_name.lower().replace(' ', '')
    best = None
    for event in chip_stats.get('events', []) or []:
        chip = str(event.get('chip', '')).lower().replace(' ', '')
        if chip == wanted or (wanted == 'freehit' and chip == 'freehit') or (wanted == 'benchboost' and chip in ('benchboost','bboost')) or (wanted == 'triplecaptain' and chip in ('triplecaptain','3xc')):
            score = event.get('score', 0) or 0
            best = score if best is None else max(best, score)
    return best if best is not None else 0


def _best_vice_captain_haul(manager):
    """Best vice-captain auto-swap haul using normal x2 scoring.

    The new engine stores this directly in season_totals as
    best_vice_captain_score. The history scan remains as a fallback for
    older/partial masters, but the stored season total is preferred when it
    exists so this mirrors best_captain_score.
    """
    season = manager.get('season_totals', {}) or {}
    stored = season.get('best_vice_captain_score', season.get('best_vice_captain_haul', 0)) or 0

    best = 0
    for row in _manager_history_rows(manager):
        switched = bool(row.get('captain_switched_to_vice') or row.get('vice_became_captain') or row.get('used_vice_captain'))

        active_captain = (row.get('captain_name') or row.get('active_captain_name') or '').strip()
        original_captain = (row.get('original_captain_name') or row.get('selected_captain_name') or '').strip()
        original_vice = (row.get('original_vice_captain_name') or row.get('vice_captain_name') or row.get('selected_vice_captain_name') or '').strip()
        original_cap_raw = row.get('original_captain_raw_points', row.get('selected_captain_raw_points'))
        active_cap_raw = row.get('captain_raw_points', row.get('active_captain_raw_points'))

        inferred_switch = (
            bool(active_captain)
            and bool(original_vice)
            and active_captain == original_vice
            and (not original_captain or active_captain != original_captain)
            and (original_cap_raw in (0, None, '', '—'))
            and ((active_cap_raw or 0) > 0)
        )

        if not (switched or inferred_switch):
            continue

        raw = row.get('original_vice_captain_raw_points', row.get('selected_vice_captain_raw_points'))
        if raw in (None, ''):
            raw = row.get('vice_captain_raw_points')
        if raw in (None, ''):
            raw = row.get('captain_raw_points', row.get('active_captain_raw_points'))
        try:
            raw = float(raw or 0)
        except (TypeError, ValueError):
            raw = 0
        best = max(best, int(raw * 2))

    return max(best, stored)


def _best_vice_captain_detail_from_history(manager):
    """Return player/GW detail for the best vice-captain auto-swap haul."""
    season = manager.get('season_totals', {}) or {}
    stored_detail = (
        season.get('best_vice_captain_detail')
        or season.get('best_vice_captain_score_detail')
        or manager.get('best_vice_captain_detail', '')
    )
    stored_score = season.get('best_vice_captain_score', season.get('best_vice_captain_haul', 0)) or 0

    best = 0
    detail = ''
    for row in _manager_history_rows(manager):
        switched = bool(row.get('captain_switched_to_vice') or row.get('vice_became_captain') or row.get('used_vice_captain'))
        active_captain = (row.get('captain_name') or row.get('active_captain_name') or '').strip()
        original_captain = (row.get('original_captain_name') or row.get('selected_captain_name') or '').strip()
        original_vice = (row.get('original_vice_captain_name') or row.get('vice_captain_name') or row.get('selected_vice_captain_name') or '').strip()
        original_cap_raw = row.get('original_captain_raw_points', row.get('selected_captain_raw_points'))
        active_cap_raw = row.get('captain_raw_points', row.get('active_captain_raw_points'))
        inferred_switch = (
            bool(active_captain)
            and bool(original_vice)
            and active_captain == original_vice
            and (not original_captain or active_captain != original_captain)
            and (original_cap_raw in (0, None, '', '—'))
            and ((active_cap_raw or 0) > 0)
        )
        if not (switched or inferred_switch):
            continue
        raw = row.get('original_vice_captain_raw_points', row.get('selected_vice_captain_raw_points'))
        if raw in (None, ''):
            raw = row.get('vice_captain_raw_points')
        if raw in (None, ''):
            raw = row.get('captain_raw_points', row.get('active_captain_raw_points'))
        try:
            score = int((float(raw or 0)) * 2)
        except (TypeError, ValueError):
            score = 0
        if score > best:
            best = score
            player = original_vice or active_captain or 'Vice captain'
            gw = row.get('gw') or row.get('gameweek') or row.get('event')
            detail = f'{player} · GW{gw}' if gw else player

    if stored_detail and stored_score >= best:
        return stored_detail
    return detail


def _row_points(row):
    return _as_num(row.get('net_gw_points', row.get('gw_points', row.get('points', 0))), 0)


def _row_total_points(row):
    return _as_num(row.get('total_points', row.get('overall_points', row.get('season_points', 0))), 0)


def _row_captain_score_x2(row):
    """Normal active-captain score at x2.

    Prefer the active/vice captain raw score when it exists, but do not let an
    older stored original-captain raw value of 0 override a positive active
    captain_points value. This fixes vice-captain auto-swap weeks where the
    selected captain blanked/DNP and the vice became captain.
    """
    points = _as_num(row.get('captain_points', 0), 0)
    chip = str(row.get('chip_used', row.get('chip', ''))).lower()

    original_cap_name = str(row.get('original_captain_name', row.get('selected_captain_name', '')) or '').strip()
    original_vice_name = str(row.get('original_vice_captain_name', row.get('selected_vice_captain_name', '')) or '').strip()
    active_cap_name = str(row.get('captain_name', row.get('active_captain_name', '')) or '').strip()

    explicit_switch = bool(
        row.get('captain_switched_to_vice')
        or row.get('vice_became_captain')
        or row.get('used_vice_captain')
    )
    name_switch = bool(
        active_cap_name
        and original_vice_name
        and active_cap_name == original_vice_name
        and (not original_cap_name or active_cap_name != original_cap_name)
    )
    switched_to_vice = explicit_switch or name_switch

    original_cap_raw = row.get('original_captain_raw_points', row.get('selected_captain_raw_points'))
    if original_cap_raw in (None, '', '—'):
        original_cap_raw = row.get('captain_raw_points')

    # Older snapshots may not have an explicit switch flag. If the original
    # captain raw score is 0 but captain_points is positive, the only sensible
    # interpretation is that an active/vice captain score has already been
    # applied elsewhere.
    try:
        original_cap_num = float(original_cap_raw or 0)
    except (TypeError, ValueError):
        original_cap_num = 0
    vice_raw_probe = row.get('original_vice_captain_raw_points', row.get('selected_vice_captain_raw_points', row.get('vice_captain_raw_points')))
    try:
        vice_raw_probe_num = float(vice_raw_probe or 0)
    except (TypeError, ValueError):
        vice_raw_probe_num = 0
    inferred_vice_swap = (original_cap_num == 0 and (points > 0 or vice_raw_probe_num > 0))

    raw_candidates = []
    if switched_to_vice or inferred_vice_swap:
        raw_candidates.extend([
            row.get('original_vice_captain_raw_points'),
            row.get('selected_vice_captain_raw_points'),
            row.get('vice_captain_raw_points'),
            row.get('active_captain_raw_points'),
        ])
    raw_candidates.extend([
        row.get('active_captain_raw_points'),
        row.get('captain_raw_points'),
    ])

    # Prefer a positive raw score when available. This avoids returning 0 from
    # the original captain on auto-swap weeks.
    for raw in raw_candidates:
        if raw in (None, '', '—'):
            continue
        raw_num = _as_num(raw, 0)
        if raw_num > 0:
            return raw_num * 2

    # Fall back to captain_points, which is normally already normal x2 for the
    # active captain. Triple Captain is normalised back to x2.
    if points:
        if chip in ('triple captain', '3xc', 'tc', 'triplecaptain'):
            return (points / 3) * 2
        return points

    # Genuine captain blank.
    return 0

def _row_final_xi_players(row):
    players = row.get('starting_xi_players') or row.get('final_xi_players') or []
    return [p for p in players if isinstance(p, dict)]


def _player_id(p):
    return p.get('id', p.get('element', p.get('player_id')))


def _player_points(p):
    return _as_num(p.get('points', p.get('total_points', p.get('event_points', 0))), 0)


def _row_captain_name(row):
    return (
        row.get('captain_name')
        or row.get('active_captain_name')
        or row.get('captain')
        or ''
    )


def _set_best_pick(values, mid, metric, points, player_name, gw):
    current = values[mid].get(metric, None)
    if current is None or points > current:
        values[mid][metric] = points
        values[mid][f'{metric}_detail'] = f'{player_name} · GW{gw}'


def _computed_season_story_values(master):
    """Build season-long accolade counters from weekly newsletter-style events."""
    managers = master.get('managers', {}) or {}
    values = {str(mid): defaultdict(float) for mid in managers.keys()}
    rows_by_gw = defaultdict(dict)

    global_history = master.get('gw_history', {}) or {}
    if isinstance(global_history, dict):
        for gw, snapshot in global_history.items():
            if isinstance(snapshot, dict):
                for mid, row in snapshot.items():
                    if isinstance(row, dict):
                        rows_by_gw[int(gw)][str(mid)] = row

    for mid, manager in managers.items():
        for gw, row in (manager.get('gw_history', {}) or {}).items():
            if isinstance(row, dict):
                try:
                    rows_by_gw[int(gw)][str(mid)] = {**rows_by_gw[int(gw)].get(str(mid), {}), **row}
                except (TypeError, ValueError):
                    continue

    for gw in sorted(rows_by_gw):
        gw_rows = {mid: row for mid, row in rows_by_gw[gw].items() if isinstance(row, dict)}
        if not gw_rows:
            continue

        scored = [(mid, _row_points(row)) for mid, row in gw_rows.items()]
        if scored:
            max_score = max(score for _, score in scored)
            min_score = min(score for _, score in scored)
            # Top three score bands count as podium finishes. This keeps ties fair.
            top_score_bands = sorted({score for _, score in scored}, reverse=True)[:3]
            for mid, score in scored:
                if score == max_score:
                    values[mid]['most_gw_wins_count'] += 1
                if score in top_score_bands:
                    values[mid]['podium_count'] += 1
                if score == min_score:
                    values[mid]['wooden_spoon_count'] += 1
                current_low = values[mid].get('lowest_gw_score')
                if current_low in (None, 0) or score < current_low:
                    values[mid]['lowest_gw_score'] = score

        captain_scores = [(mid, _row_captain_score_x2(row)) for mid, row in gw_rows.items()]
        if captain_scores:
            max_cap = max(score for _, score in captain_scores)
            min_cap = min(score for _, score in captain_scores)
            for mid, score in captain_scores:
                if score == max_cap:
                    values[mid]['golden_armband_count'] += 1
                if score == min_cap:
                    values[mid]['captain_dud_count'] += 1
                if score > values[mid].get('best_captain_score', 0):
                    values[mid]['best_captain_score'] = score
                    cap_name = _row_captain_name(gw_rows[mid]) or 'Captain'
                    values[mid]['best_captain_score_detail'] = f'{cap_name} · GW{gw}'

        captain_names = defaultdict(list)
        for mid, row in gw_rows.items():
            cap_name = str(_row_captain_name(row) or '').strip()
            if cap_name:
                captain_names[cap_name].append(mid)
        if captain_names:
            max_pop = max(len(mids) for mids in captain_names.values())
            popular_captains = {name for name, mids in captain_names.items() if len(mids) == max_pop}
            for mid, row in gw_rows.items():
                if str(_row_captain_name(row) or '').strip() in popular_captains:
                    values[mid]['popular_armband_count'] += 1

        # Best differential captain: active captain selected by under 20% of the league.
        league_size = max(len(gw_rows), 1)
        for mid, row in gw_rows.items():
            cap_name = str(_row_captain_name(row) or '').strip()
            if not cap_name:
                continue
            selected_count = len(captain_names.get(cap_name, []))
            selected_pct = (selected_count / league_size) * 100
            if selected_pct >= 20:
                continue
            values[mid]['differential_captain_count'] += 1
            score = _row_captain_score_x2(row)
            if score > values[mid].get('best_differential_captain_score', 0):
                values[mid]['best_differential_captain_score'] = score
                values[mid]['best_differential_captain_score_detail'] = f'{cap_name} · GW{gw}'

        # Strategy room season counters: top scorer picks and under-20% differential picks.
        player_rows = defaultdict(list)
        for mid, row in gw_rows.items():
            for player in _row_final_xi_players(row):
                pid = _player_id(player)
                if pid is None:
                    continue
                player_rows[pid].append((mid, player))

        if player_rows:
            league_size = max(len(gw_rows), 1)
            player_summaries = []
            for pid, entries in player_rows.items():
                points = max((_player_points(p) for _, p in entries), default=0)
                starters = len({mid for mid, _ in entries})
                pct = (starters / league_size) * 100
                name = next((p.get('name') or p.get('web_name') or p.get('player_name') for _, p in entries if p.get('name') or p.get('web_name') or p.get('player_name')), str(pid))
                player_summaries.append({
                    'pid': pid,
                    'name': name,
                    'points': points,
                    'starters': starters,
                    'pct': pct,
                    'entries': entries,
                })

            # Count the weekly Strategy Room-style picks: top 3 raw scorers
            # by points, then starter count, then player name. Everyone who
            # started one of those players receives the counter.
            top_scorer_picks = sorted(
                player_summaries,
                key=lambda p: (-p['points'], -p['starters'], str(p.get('name', '')).lower())
            )[:3]
            for ps in top_scorer_picks:
                for mid, _ in ps['entries']:
                    values[mid]['top_scorer_pick_count'] += 1

            for ps in player_summaries:
                for mid, _ in ps['entries']:
                    _set_best_pick(values, mid, 'best_pick_score', ps['points'], ps.get('name', '—'), gw)

            differential_pool = [p for p in player_summaries if p['pct'] < 20]
            if differential_pool:
                top_diff_picks = sorted(
                    differential_pool,
                    key=lambda p: (-p['points'], -p['starters'], str(p.get('name', '')).lower())
                )[:3]
                top_diff_ids = {p['pid'] for p in top_diff_picks}
                for ps in differential_pool:
                    if ps['pid'] in top_diff_ids:
                        for mid, _ in ps['entries']:
                            values[mid]['best_differential_pick_count'] += 1
                    for mid, _ in ps['entries']:
                        _set_best_pick(values, mid, 'best_differential_pick_score', ps['points'], ps.get('name', '—'), gw)

    # Division movement records, based on total points within each manager's current division.
    divisions = defaultdict(list)
    for mid, manager in managers.items():
        div = manager.get('division') or manager.get('current_division') or 'League'
        divisions[div].append(str(mid))

    for div, mids in divisions.items():
        previous_positions = None
        for gw in sorted(rows_by_gw):
            available = []
            for mid in mids:
                row = rows_by_gw[gw].get(mid)
                if row:
                    available.append((mid, _row_total_points(row), _row_points(row)))
            if not available:
                continue
            current_positions = {
                mid: pos
                for pos, (mid, _, _) in enumerate(sorted(available, key=lambda x: (x[1], x[2]), reverse=True), 1)
            }
            if previous_positions:
                for mid, current_pos in current_positions.items():
                    prev_pos = previous_positions.get(mid)
                    if not prev_pos:
                        continue
                    movement = prev_pos - current_pos
                    if movement > 0:
                        values[mid]['biggest_single_week_climb'] = max(values[mid]['biggest_single_week_climb'], movement)
                    elif movement < 0:
                        values[mid]['biggest_single_week_fall'] = max(values[mid]['biggest_single_week_fall'], abs(movement))
            previous_positions = current_positions

    # Hot/cold season-long form runs from available GW history. These mirror
    # the Form Guide but track the best run even after it has ended.
    def _avg_for_gw(_gw):
        vals = [_row_points(row) for row in rows_by_gw.get(_gw, {}).values() if isinstance(row, dict)]
        return (sum(vals) / len(vals)) if vals else None

    for mid in managers.keys():
        hot_current = cold_current = 0
        hot_best = cold_best = 0
        for gw in sorted(rows_by_gw):
            row = rows_by_gw[gw].get(str(mid))
            avg = _avg_for_gw(gw)
            if not row or avg is None:
                hot_current = cold_current = 0
                continue
            score = _row_points(row)
            if score > avg:
                hot_current += 1
                hot_best = max(hot_best, hot_current)
            else:
                hot_current = 0
            if score < avg:
                cold_current += 1
                cold_best = max(cold_best, cold_current)
            else:
                cold_current = 0
        if hot_best:
            values[str(mid)]['hot_streak_best'] = hot_best
        if cold_best:
            values[str(mid)]['cold_streak_best'] = cold_best

    return values

def _metric_value(manager, metric):
    """Read an accolade/chip metric from the most likely stored locations."""
    season = manager.get('season_totals', {}) or {}
    stats = manager.get('stats', {}) or {}
    computed = manager.get('_computed_awards', {}) or {}

    if metric in computed:
        return computed.get(metric, 0) or 0

    if metric == "cards_total":
        return season.get('cards_total', season.get('yellow_cards', 0) + season.get('red_cards', 0))
    if metric == "total_captain_pts":
        return _normalised_total_captain_points(manager)
    if metric == "best_captain_score":
        return _normalised_best_captain_haul(manager)
    if metric == "net_transfer_points_gained":
        return _transfer_wizard_from_history(manager)
    if metric == "best_transfer_score":
        return _transfer_event_from_history(manager, "best")[0]
    if metric == "worst_transfer_score":
        return _transfer_event_from_history(manager, "worst")[0]
    if metric == "best_wildcard_score":
        return _best_chip_metric(manager, "Wildcard")
    if metric == "best_free_hit_score":
        return _best_chip_metric(manager, "Free Hit")
    if metric == "best_triple_captain_score":
        return _best_chip_metric(manager, "Triple Captain")
    if metric == "best_bench_boost_score":
        return _best_chip_metric(manager, "Bench Boost")
    if metric in ("best_vice_captain_haul", "best_vice_captain_score"):
        return _best_vice_captain_haul(manager)
    if metric in ("best_auto_sub_score", "best_autosub_score"):
        return _best_autosub_from_history(manager)
    if metric in ("best_left_behind_score", "best_bench_left_behind_score"):
        return _best_left_behind_from_history(manager)
    if metric == "total_auto_sub_points":
        return _total_autosub_from_history(manager)
    if metric == "hot_streak_best":
        return season.get('hot_streak_best', season.get('best_hot_streak', 0)) or 0
    if metric == "cold_streak_best":
        return season.get('cold_streak_best', season.get('best_cold_streak', 0)) or 0

    for source in (season, stats, manager, manager.get('accolades', {}) or {}):
        if metric in source:
            return source.get(metric, 0) or 0

    return 0


def _format_acc_value(value):
    """Keep accolade numbers compact while preserving negatives for transfer/chip-style metrics."""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return value



def _manager_has_chip_event(manager, chip_name):
    if not chip_name:
        return True
    wanted = str(chip_name).lower().replace(' ', '')
    chip_stats = manager.get('chip_stats', {}) or manager.get('chips', {}) or {}
    aliases = {
        'freehit': {'freehit', 'freehit'},
        'wildcard': {'wildcard'},
        'triplecaptain': {'triplecaptain', '3xc', 'tc'},
        'benchboost': {'benchboost', 'bboost'},
    }
    allowed = aliases.get(wanted, {wanted})
    for event in chip_stats.get('events', []) or []:
        chip = str(event.get('chip', '')).lower().replace(' ', '')
        if chip in allowed:
            return True
    return False

def _metric_detail(manager, metric):
    computed = manager.get('_computed_awards', {}) or {}
    season = manager.get('season_totals', {}) or {}
    if metric == 'best_captain_score':
        stored = (
            computed.get(f'{metric}_detail', '')
            or season.get(f'{metric}_detail', '')
            or season.get('best_captain_detail', '')
            or season.get('best_captain_score_detail', '')
            or manager.get(f'{metric}_detail', '')
            or manager.get('best_captain_detail', '')
        )
        if stored:
            return stored
        best = -1
        detail = ''
        for row in _manager_history_rows(manager):
            score = _row_captain_score_x2(row)
            if score > best:
                best = score
                name = (
                    _row_captain_name(row)
                    or row.get('original_vice_captain_name')
                    or row.get('selected_vice_captain_name')
                    or row.get('original_captain_name')
                    or row.get('selected_captain_name')
                    or 'Captain'
                )
                gw = row.get('gw') or row.get('gameweek') or row.get('event')
                detail = f'{name} · GW{gw}' if gw else name
        return detail
    if metric in ('best_differential_captain_score', 'best_differential_captain'):
        return (
            computed.get(f'{metric}_detail', '')
            or season.get(f'{metric}_detail', '')
            or manager.get(f'{metric}_detail', '')
            or ''
        )
    if metric in ('best_vice_captain_haul', 'best_vice_captain_score'):
        return _best_vice_captain_detail_from_history(manager)
    if metric in ('best_auto_sub_score', 'best_autosub_score'):
        return _best_autosub_detail_from_history(manager)
    if metric in ('best_left_behind_score', 'best_bench_left_behind_score'):
        return _best_left_behind_detail_from_history(manager)
    if metric == 'best_transfer_score':
        return _transfer_event_from_history(manager, 'best')[1]
    if metric == 'worst_transfer_score':
        return _transfer_event_from_history(manager, 'worst')[1]
    return (
        computed.get(f'{metric}_detail', '')
        or season.get(f'{metric}_detail', '')
        or manager.get(f'{metric}_detail', '')
        or ''
    )




PLAYER_EVENT_AWARD_METRICS = {
    'best_captain_score',
    'best_vice_captain_score',
    'best_vice_captain_haul',
    'best_differential_captain_score',
    'best_differential_captain',
    'best_pick_score',
    'best_differential_pick_score',
    'best_auto_sub_score',
    'best_autosub_score',
    'best_left_behind_score',
    'best_bench_left_behind_score',
}


def _rows_by_gw_from_master(master):
    """Return {gw: {manager_id: row}} using both global and per-manager history."""
    rows_by_gw = defaultdict(dict)
    global_history = master.get('gw_history', {}) or {}
    if isinstance(global_history, dict):
        for gw, snapshot in global_history.items():
            if not isinstance(snapshot, dict):
                continue
            try:
                gw_key = int(gw)
            except (TypeError, ValueError):
                continue
            for mid, row in snapshot.items():
                if isinstance(row, dict):
                    rows_by_gw[gw_key][str(mid)] = row

    for mid, manager in (master.get('managers', {}) or {}).items():
        for gw, row in (manager.get('gw_history', {}) or {}).items():
            if not isinstance(row, dict):
                continue
            try:
                gw_key = int(gw)
            except (TypeError, ValueError):
                continue
            rows_by_gw[gw_key][str(mid)] = {**rows_by_gw[gw_key].get(str(mid), {}), **row}
    return rows_by_gw


def _vice_swap_event_score_and_detail(row, gw):
    switched = bool(row.get('captain_switched_to_vice') or row.get('vice_became_captain') or row.get('used_vice_captain'))
    active_captain = (row.get('captain_name') or row.get('active_captain_name') or '').strip()
    original_captain = (row.get('original_captain_name') or row.get('selected_captain_name') or '').strip()
    original_vice = (row.get('original_vice_captain_name') or row.get('vice_captain_name') or row.get('selected_vice_captain_name') or '').strip()
    original_cap_raw = row.get('original_captain_raw_points', row.get('selected_captain_raw_points'))
    active_cap_raw = row.get('captain_raw_points', row.get('active_captain_raw_points'))

    try:
        original_cap_num = float(original_cap_raw or 0)
    except (TypeError, ValueError):
        original_cap_num = 0
    try:
        active_cap_num = float(active_cap_raw or 0)
    except (TypeError, ValueError):
        active_cap_num = 0

    inferred_switch = (
        bool(active_captain)
        and bool(original_vice)
        and active_captain == original_vice
        and (not original_captain or active_captain != original_captain)
        and original_cap_num == 0
        and active_cap_num > 0
    )
    if not (switched or inferred_switch):
        return None

    raw = row.get('original_vice_captain_raw_points', row.get('selected_vice_captain_raw_points'))
    if raw in (None, ''):
        raw = row.get('vice_captain_raw_points')
    if raw in (None, ''):
        raw = row.get('captain_raw_points', row.get('active_captain_raw_points'))
    try:
        score = int((float(raw or 0)) * 2)
    except (TypeError, ValueError):
        score = 0
    player = original_vice or active_captain or 'Vice captain'
    detail = f'{player} · GW{gw}' if gw else player
    return score, detail


def _event_candidates_for_award(master, metric):
    """Build event-level candidates for player-based awards.

    Unlike normal manager totals, these awards can rank several different picks
    from the same manager across 1st/2nd/3rd if those picks deserve it.
    """
    managers = master.get('managers', {}) or {}
    manager_names = {str(mid): (m.get('name') or '—') for mid, m in managers.items()}
    rows_by_gw = _rows_by_gw_from_master(master)
    candidates = []

    def add(mid, value, detail):
        if value is None:
            return
        value = _as_num(value, 0)
        if value <= 0:
            return
        candidates.append({
            'name': manager_names.get(str(mid), '—'),
            'value': value,
            'detail': detail or '',
        })

    for gw in sorted(rows_by_gw):
        gw_rows = {str(mid): row for mid, row in rows_by_gw[gw].items() if isinstance(row, dict)}
        if not gw_rows:
            continue

        if metric == 'best_captain_score':
            for mid, row in gw_rows.items():
                score = _row_captain_score_x2(row)
                name = _row_captain_name(row) or 'Captain'
                add(mid, score, f'{name} · GW{gw}')
            continue

        if metric in ('best_vice_captain_score', 'best_vice_captain_haul'):
            for mid, row in gw_rows.items():
                event = _vice_swap_event_score_and_detail(row, gw)
                if event:
                    add(mid, event[0], event[1])
            continue

        if metric in ('best_differential_captain_score', 'best_differential_captain'):
            captain_names = defaultdict(list)
            for mid, row in gw_rows.items():
                cap_name = str(_row_captain_name(row) or '').strip()
                if cap_name:
                    captain_names[cap_name].append(mid)
            league_size = max(len(gw_rows), 1)
            for mid, row in gw_rows.items():
                cap_name = str(_row_captain_name(row) or '').strip()
                if not cap_name:
                    continue
                selected_count = len(captain_names.get(cap_name, []))
                selected_pct = (selected_count / league_size) * 100
                if selected_pct < 20:
                    add(mid, _row_captain_score_x2(row), f'{cap_name} · GW{gw}')
            continue

        if metric in ('best_pick_score', 'best_differential_pick_score'):
            player_rows = defaultdict(list)
            for mid, row in gw_rows.items():
                for player in _row_final_xi_players(row):
                    pid = _player_id(player)
                    if pid is None:
                        continue
                    player_rows[pid].append((mid, player))
            league_size = max(len(gw_rows), 1)
            for pid, entries in player_rows.items():
                starters = len({mid for mid, _ in entries})
                selected_pct = (starters / league_size) * 100
                if metric == 'best_differential_pick_score' and selected_pct >= 20:
                    continue
                name = next((p.get('name') or p.get('web_name') or p.get('player_name') for _, p in entries if p.get('name') or p.get('web_name') or p.get('player_name')), str(pid))
                points = max((_player_points(p) for _, p in entries), default=0)
                for mid, _ in entries:
                    add(mid, points, f'{name} · GW{gw}')
            continue

        if metric in ('best_auto_sub_score', 'best_autosub_score'):
            for mid, row in gw_rows.items():
                autosubs = row.get('auto_subs') or row.get('automatic_subs') or []
                for sub in autosubs if isinstance(autosubs, list) else []:
                    player = sub.get('player') or sub.get('in') or sub.get('subbed_in') or sub
                    if not isinstance(player, dict):
                        continue
                    name = player.get('name') or player.get('web_name') or player.get('player_name') or 'Auto-sub'
                    add(mid, _player_points(player), f'{name} · GW{gw}')
                # Fallback for flattened stored rows.
                name = row.get('best_sub_name') or row.get('best_auto_sub_name')
                score = row.get('best_sub_score', row.get('best_auto_sub_score'))
                if name and score:
                    add(mid, score, f'{name} · GW{gw}')
            continue

        if metric in ('best_left_behind_score', 'best_bench_left_behind_score'):
            for mid, row in gw_rows.items():
                chip = str(row.get('chip_used', row.get('chip', ''))).lower().replace(' ', '')
                if chip in ('benchboost', 'bboost'):
                    continue
                bench_players = row.get('bench_players') or []
                if isinstance(bench_players, list):
                    for p in bench_players:
                        if isinstance(p, dict):
                            name = p.get('name') or p.get('web_name') or p.get('player_name') or 'Bench player'
                            add(mid, _player_points(p), f'{name} · GW{gw}')
                name = row.get('best_bench_name') or row.get('best_left_behind_name')
                score = row.get('best_bench_pts', row.get('best_left_behind_score'))
                if name and score:
                    add(mid, score, f'{name} · GW{gw}')
            continue

    return candidates


def _event_award_rankings(master, award):
    metric = award.get('metric') if isinstance(award, dict) else None
    if metric not in PLAYER_EVENT_AWARD_METRICS:
        return None

    candidates = _event_candidates_for_award(master, metric)
    if not candidates:
        return []

    by_value = defaultdict(list)
    seen = set()
    for item in candidates:
        value = item.get('value', 0)
        if award.get('positive_only') and value <= 0:
            continue
        if award.get('nonzero_only') and value == 0:
            continue

        # Event awards can be discovered through both rich GW rows and
        # flattened fallback fields. De-duplicate the same manager/player/GW
        # event so ties such as Best Auto-Sub don't show "Joint x2" when it
        # is actually the same event found twice.
        key = (str(item.get('name', '')), str(item.get('detail', '')), value)
        if key in seen:
            continue
        seen.add(key)
        by_value[value].append(item)

    if not by_value:
        return []

    medals = ["🥇", "🥈", "🥉"]
    values = sorted(by_value.keys(), reverse=not award.get('lower_is_better', False))[:3]
    rankings = []
    for idx, value in enumerate(values):
        group = sorted(by_value[value], key=lambda item: (str(item.get('detail', '')).lower(), item.get('name', '').lower()))
        names = sorted({item.get('name', '—') for item in group}, key=lambda n: n.lower())
        details = sorted({item.get('detail', '') for item in group if item.get('detail')})
        rankings.append({
            'rank': idx + 1,
            'medal': medals[idx],
            'names': names,
            'name': ', '.join(names),
            'value': value,
            'joint_count': len(group),
            'details': details,
            'detail_items': group,
            'event_based': True,
        })
    return rankings

def _award_rankings(master, award):
    """Return the top three accolade value bands. Ties are shared, not broken."""
    managers = master.get('managers', {})
    metric = award.get('metric') if isinstance(award, dict) else None

    event_rankings = _event_award_rankings(master, award) if metric else None
    if event_rankings is not None:
        return event_rankings

    if metric:
        by_value = defaultdict(list)

        for mid, manager in managers.items():
            name = manager.get('name', '—')
            value = _metric_value(manager, metric)
            if award.get('requires_chip_events'):
                chip_stats = manager.get('chip_stats', {}) or manager.get('chips', {}) or {}
                if not (chip_stats.get('events', []) or []):
                    continue
            if award.get('requires_chip_name') and not _manager_has_chip_event(manager, award.get('requires_chip_name')):
                continue
            if award.get('positive_only') and value <= 0:
                continue
            if award.get('nonzero_only') and value == 0:
                continue
            if award.get('min_value') is not None and value < award.get('min_value'):
                continue
            if award.get('max_value') is not None and value > award.get('max_value'):
                continue
            by_value[value].append({
                'name': name,
                'detail': _metric_detail(manager, metric),
            })

        if not by_value:
            return []

        sort_reverse = not award.get('lower_is_better', False)
        values = sorted(by_value.keys(), reverse=sort_reverse)[:3]
        medals = ["🥇", "🥈", "🥉"]
        rankings = []

        for idx, value in enumerate(values):
            group = sorted(by_value[value], key=lambda item: item['name'].lower())
            names = [item['name'] for item in group]
            details = sorted({item.get('detail', '') for item in group if item.get('detail')})
            detail_items = [item for item in group if item.get('detail')]
            rankings.append({
                "rank": idx + 1,
                "medal": medals[idx],
                "names": names,
                "name": ", ".join(names),
                "value": value,
                "joint_count": len(group),
                "details": details,
                "detail_items": detail_items,
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
            "details": [],
        }]

    return []

def _award_worst(master, award):
    """Return the lowest value band for an award, for a wooden-spoon style footnote."""
    if award.get('no_spoon'):
        return None
    managers = master.get('managers', {})
    metric = award.get('metric') if isinstance(award, dict) else None
    if not metric or not managers:
        return None
    by_value = defaultdict(list)
    for mid, manager in managers.items():
        value = _metric_value(manager, metric)
        if award.get('requires_chip_events'):
            chip_stats = manager.get('chip_stats', {}) or manager.get('chips', {}) or {}
            if not (chip_stats.get('events', []) or []):
                continue
        if award.get('requires_chip_name') and not _manager_has_chip_event(manager, award.get('requires_chip_name')):
            continue
        if award.get('positive_only') and value <= 0:
            continue
        if award.get('nonzero_only') and value == 0:
            continue
        if award.get('min_value') is not None and value < award.get('min_value'):
            continue
        if award.get('max_value') is not None and value > award.get('max_value'):
            continue
        by_value[value].append(manager.get('name', '—'))
    if not by_value:
        return None
    worst_value = sorted(by_value.keys(), reverse=award.get('lower_is_better', False))[0]
    # Avoid duplicating the spoon when everyone is tied on the same value.
    if len(by_value) == 1:
        return None
    return {
        'value': worst_value,
        'names': sorted(by_value[worst_value], key=lambda n: n.lower()),
    }

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

                detail_values = entry.get("details", []) or []
                detail_items = entry.get("detail_items", []) or []
                if detail_items and entry.get("event_based"):
                    # Group single-pick awards by the actual pick detail, so
                    # multiple managers with the same player/GW share one pill row.
                    detail_groups = defaultdict(list)
                    for item in detail_items:
                        detail = item.get('detail', '')
                        if detail:
                            detail_groups[detail].append(item.get('name', '—'))

                    pick_blocks = []
                    for detail, names in list(detail_groups.items())[:8]:
                        pick_blocks.append(
                            f'<div class="hub-acc-detail-pick">'
                            f'{_name_pills(sorted(set(names), key=lambda n: n.lower()), "hub-name-pills", "hub-name-pill")}'
                            f'<div class="hub-acc-detail-pick-text">{detail}</div>'
                            f'</div>'
                        )
                    manager_html = ''.join(pick_blocks)
                elif entry.get("joint_count", 1) > 1 and detail_items:
                    # Group tied single-pick awards by the actual pick detail, so
                    # multiple managers with the same player/GW share one pill row.
                    detail_groups = defaultdict(list)
                    for item in detail_items:
                        detail = item.get('detail', '')
                        if detail:
                            detail_groups[detail].append(item.get('name', '—'))

                    pick_blocks = []
                    for detail, names in list(detail_groups.items())[:6]:
                        pick_blocks.append(
                            f'<div class="hub-acc-detail-pick">'
                            f'{_name_pills(sorted(set(names), key=lambda n: n.lower()), "hub-name-pills", "hub-name-pill")}'
                            f'<div class="hub-acc-detail-pick-text">{detail}</div>'
                            f'</div>'
                        )
                    manager_html = ''.join(pick_blocks)
                else:
                    detail_html = (
                        f'<div class="hub-acc-detail">{" · ".join(detail_values[:2])}</div>'
                        if detail_values
                        else ""
                    )
                    manager_html = f'{_name_pills(entry.get("names", [entry.get("name", "—")]), "hub-name-pills", "hub-name-pill")}{detail_html}'

                rank_rows += (
                    f'<div class="hub-acc-rank-row">'
                    f'<span class="hub-acc-medal">{entry.get("medal", medals[i])}</span>'
                    f'<span class="hub-acc-manager">{manager_html}</span>'
                    f'<span class="hub-acc-value-wrap">'
                    f'<span class="hub-acc-value">{value}</span>'
                    f'{joint_html}'
                    f'</span>'
                    f'</div>'
                )

            worst = _award_worst(master, award)
            if worst:
                spoon_count = len(worst.get("names", []) or [])
                spoon_joint_html = (
                    f'<span class="hub-acc-tie">Joint x{spoon_count}</span>'
                    if spoon_count > 1
                    else ""
                )
                rank_rows += (
                    f'<div class="hub-acc-rank-row hub-acc-spoon-row">'
                    f'<span class="hub-acc-medal">🥄</span>'
                    f'<span class="hub-acc-manager">{_name_pills(worst.get("names", []), "hub-name-pills", "hub-name-pill")}</span>'
                    f'<span class="hub-acc-value-wrap"><span class="hub-acc-value">{_format_acc_value(worst.get("value", 0))}</span>{spoon_joint_html}</span>'
                    f'</div>'
                )
        else:
            rank_rows = '<div class="hub-acc-empty">No data available yet</div>'

        info_html = f'<div class="hub-acc-info">{AWARD_INFO.get(award_name, "")}</div>' if AWARD_INFO.get(award_name) else ""

        rows += (
            f'<div class="hub-acc-card">'
            f'<div class="hub-acc-title">'
            f'<span>{AWARD_EMOJI.get(award_name, icon)}</span>'
            f'<span>{award_name}</span>'
            f'</div>'
            f'{info_html}'
            f'<div class="hub-acc-ranks">{rank_rows}</div>'
            f'</div>'
        )

    if not rows:
        rows = '<div class="muted" style="font-size:13px">No accolade data available yet</div>'

    return rows


def _accolades_html(master):
    computed_values = _computed_season_story_values(master)
    for mid, manager in (master.get('managers', {}) or {}).items():
        manager['_computed_awards'] = computed_values.get(str(mid), {})

    accolades = master.get('accolades', {}) or {}
    prizes = dict(accolades.get('prizes', {}) or {})
    stored_fun = dict(accolades.get('fun', {}) or {})

    # Remove awards that are now explicitly organised below. This avoids
    # duplicate cards if the same legacy accolade still exists in master.json.
    organised_names = {
        'Golden Boot', 'Playmaker', 'Golden Glove', 'Captain King', 'Bonus Magnet',
        'Transfer Wizard', 'Talent Scout', 'Bench Warmer', 'Card Dealer',
        'Highest GW Score', 'Lowest GW Score', 'Best Captain Haul', 'Best Auto-Sub',
        'Chip Master', 'Best Wildcard', 'Best Free Hit', 'Best Triple Captain', 'Best Bench Boost',
        'Best Vice Captain Haul', 'Most GW Wins', 'Most Podiums', 'Most Wooden Spoons',
        'Most Golden Armbands', 'Most Differential Captain Armbands', 'Most Captain Duds', 'Most Popular Armband', 'Most Top Scorer Picks',
        'Most Best Differential Picks', 'Best Pick', 'Best Differential Pick', 'Best Differential Captain',
        'Most Auto-Sub Points', 'Total Auto-Sub Points', 'Best Left Behind', 'Hot Streak', 'Out of Form'
    }
    extra_fun = {k: v for k, v in stored_fun.items() if k not in organised_names}

    performance_defs = {
        'Most GW Wins': {'metric': 'most_gw_wins_count', 'positive_only': True, 'no_spoon': True},
        'Most Podiums': {'metric': 'podium_count', 'positive_only': True, 'no_spoon': True},
        'Most Wooden Spoons': {'metric': 'wooden_spoon_count', 'positive_only': True, 'no_spoon': True},
        'Highest GW Score': {'metric': 'highest_gw_score', 'no_spoon': True},
        'Lowest GW Score': {'metric': 'lowest_gw_score', 'lower_is_better': True, 'no_spoon': True},
        'Card Dealer': {'metric': 'cards_total', 'no_spoon': True},
    }

    player_pick_defs = {
        'Golden Boot': prizes.get('Golden Boot', {'metric': 'goals_scored'}),
        'Playmaker': prizes.get('Playmaker', {'metric': 'assists'}),
        'Golden Glove': prizes.get('Golden Glove', {'metric': 'net_defensive_score'}),
        'Bonus Magnet': prizes.get('Bonus Magnet', {'metric': 'bonus_points'}),
    }

    captaincy_defs = {
        'Captain King': prizes.get('Captain King', {'metric': 'total_captain_pts'}),
        'Most Popular Armband': {'metric': 'popular_armband_count', 'positive_only': True, 'no_spoon': True},
        'Most Golden Armbands': {'metric': 'golden_armband_count', 'positive_only': True, 'no_spoon': True},
        'Most Differential Captain Armbands': {'metric': 'differential_captain_count', 'positive_only': True, 'no_spoon': True},
        'Most Captain Duds': {'metric': 'captain_dud_count', 'positive_only': True, 'no_spoon': True},
        'Best Captain Haul': {'metric': 'best_captain_score', 'no_spoon': True},
        'Best Vice Captain Haul': {'metric': 'best_vice_captain_score', 'positive_only': True, 'no_spoon': True},
        'Best Differential Captain': {'metric': 'best_differential_captain_score', 'positive_only': True, 'no_spoon': True},
    }

    strategy_defs = {
        'Talent Scout': {'metric': 'differential_points', 'no_spoon': True},
        'Most Top Scorer Picks': {'metric': 'top_scorer_pick_count', 'positive_only': True, 'no_spoon': True},
        'Most Best Differential Picks': {'metric': 'best_differential_pick_count', 'positive_only': True, 'no_spoon': True},
        'Best Pick': {'metric': 'best_pick_score', 'positive_only': True, 'no_spoon': True},
        'Best Differential Pick': {'metric': 'best_differential_pick_score', 'positive_only': True, 'no_spoon': True},
    }

    transfer_defs = {
        'Transfer Wizard': {'metric': 'net_transfer_points_gained', 'nonzero_only': True},
        'Best Transfer': {'metric': 'best_transfer_score', 'positive_only': True, 'no_spoon': True},
        'Worst Transfer': {'metric': 'worst_transfer_score', 'lower_is_better': True, 'max_value': -1, 'no_spoon': True},
    }

    bench_defs = {
        'Bench Warmer': {'metric': 'bench_points_total', 'no_spoon': True},
        'Best Left Behind': {'metric': 'best_left_behind_score', 'positive_only': True, 'no_spoon': True},
        'Best Auto-Sub': {'metric': 'best_auto_sub_score', 'positive_only': True, 'no_spoon': True},
        'Most Auto-Sub Points': {'metric': 'total_auto_sub_points', 'positive_only': True, 'no_spoon': True},
    }

    form_defs = {
        'Hot Streak': {'metric': 'hot_streak_best', 'positive_only': True, 'no_spoon': True},
        'Out of Form': {'metric': 'cold_streak_best', 'positive_only': True, 'no_spoon': True},
        **extra_fun,
    }

    chip_defs = {
        'Chip Master': {'metric': 'chip_total_score', 'requires_chip_events': True},
        # Individual chip awards include negative scores, but only rank managers
        # who actually played that chip. A -4 Wildcard is still valid data.
        'Best Wildcard': {'metric': 'best_wildcard_score', 'requires_chip_name': 'Wildcard'},
        'Best Free Hit': {'metric': 'best_free_hit_score', 'requires_chip_name': 'Free Hit'},
        'Best Triple Captain': {'metric': 'best_triple_captain_score', 'requires_chip_name': 'Triple Captain'},
        'Best Bench Boost': {'metric': 'best_bench_boost_score', 'requires_chip_name': 'Bench Boost'},
    }

    # Populate chip_total_score dynamically so it can be ranked like other metrics.
    for _, manager in (master.get('managers', {}) or {}).items():
        chip_stats = manager.get('chip_stats', {}) or manager.get('chips', {}) or {}
        manager['chip_total_score'] = chip_stats.get('total_score', sum((e.get('score', 0) or 0) for e in chip_stats.get('events', []) or []))

    return (
        _award_rows_from_defs(master, player_pick_defs, '⚽'),
        _award_rows_from_defs(master, captaincy_defs, '🧢'),
        _award_rows_from_defs(master, strategy_defs, '🧠'),
        _award_rows_from_defs(master, transfer_defs, '🪄'),
        _award_rows_from_defs(master, bench_defs, '🪑'),
        _award_rows_from_defs(master, performance_defs, '🏆'),
        _award_rows_from_defs(master, form_defs, '📈'),
        _award_rows_from_defs(master, chip_defs, '🃏'),
    )

def _chip_leaderboard_html(master, gw_results=None):
    """Season chip leaderboard with chip-use pills, best/worst events and totals."""
    gw_results = gw_results or {}
    managers = master.get('managers', {}) or {}

    def _chip_event_key(ev):
        return (str(ev.get('chip', '')), ev.get('gw'), ev.get('score'))

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
            meta_class = ''
            if score not in (None, ''):
                score_display = f'+{score}' if score > 0 else str(score)
                meta_bits.append(score_display)
                if score > 10:
                    meta_class = ' good'
                elif score < 0:
                    meta_class = ' bad'
            meta = f'<span class="hub-chip-pill-meta{meta_class}">{" · ".join(meta_bits)}</span>' if meta_bits else ''

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
            avg = round((total_score or 0) / chips_count, 1) if chips_count else 0
            entries.append({
                'name': manager.get('name', '—'),
                'total_score': total_score or 0,
                'chips_count': chips_count,
                'chips_used_label': f'{chips_count}/8 used',
                'chip_pills': chip_pills,
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

        rows += (
            f'<div class="hub-chip-row">'
            f'<div class="hub-chip-rank">#{pos}</div>'
            f'<div class="hub-chip-main">'
            f'<div class="hub-chip-manager-line"><span class="hub-chip-manager">{entry["name"]}</span><span class="hub-chip-used">{entry["chips_used_label"]} · avg {entry["avg"]}</span></div>'
            f'<div class="hub-chip-pills">{chip_pills}</div>'
            f'</div>'
            f'<div class="hub-chip-score {score_class}">{score_display}</div>'
            f'</div>'
        )

    return f'<div class="hub-chip-leaderboard"><div class="hub-chip-head"><span>Rank</span><span>Manager & chips</span><span>Score</span></div>{rows}</div>'


# ─────────────────────────────────────────────────────────────────────────────
# GW POSTER
# ─────────────────────────────────────────────────────────────────────────────

def _name_pills(names, wrap_class="poster-name-pills", pill_class="poster-name-pill"):
    """Render manager names as compact wrap-friendly pills."""
    if names in (None, "", []):
        return '<span class="muted">—</span>'
    if not isinstance(names, list):
        names = [str(names)]
    clean_names = [str(n) for n in names if str(n).strip()]
    if not clean_names:
        return '<span class="muted">—</span>'
    return (
        f'<div class="{wrap_class}">'
        + ''.join(f'<span class="{pill_class}">{name}</span>' for name in clean_names)
        + '</div>'
    )


def _names_sentence(names):
    """Render manager names as readable wrapping text for compact newsletter meta lines."""
    if names in (None, "", []):
        return ""
    if not isinstance(names, list):
        names = [str(names)]
    clean_names = [str(n) for n in names if str(n).strip()]
    if not clean_names:
        return ""
    if len(clean_names) == 1:
        return clean_names[0]
    if len(clean_names) == 2:
        return f"{clean_names[0]} and {clean_names[1]}"
    return ", ".join(clean_names[:-1]) + f" and {clean_names[-1]}"


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
      names_html = _name_pills(names) if isinstance(names, list) else _name_pills([names])

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
        _pop_stat_card("Most BPS",         sl["most_bonus"],    STAT_COLOURS["green"], fmt_val=lambda v: f"+{v} pts", icon="✨"),
    ])

    stat_grid = "".join(stat_cards)

    # Podium
    medal_icons = ['🥇', '🥈', '🥉']
    podium_html = ""

    for i, p in enumerate(payload['podium']):
      captain_line = f'Captain: {p["captain"]} ({p["captain_pts"]})'
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

    def _strategy_collection_card(kicker, players, subtitle=None, suppress_meta_for=None):
        players = players or []
        if not players:
            return ""

        suppress_meta_for = suppress_meta_for or set()
        rows = ""
        for item in players:
            player_name = item.get("player", "—")
            duplicate_context = player_name in suppress_meta_for
            manager_names = [] if duplicate_context else item.get("managers", [])
            managers_display = _name_pills(manager_names) if manager_names else ""
            starter_count = item.get("owners", 0)
            starter_word = "manager" if starter_count == 1 else "managers"
            meta = f'Started by {starter_count} {starter_word} ({item.get("ownership_pct", 0)}% of league)'
            meta_html = f'<div class="strategy-player-meta">{meta}</div>' if meta else ""
            managers_html = f'<div class="strategy-managers">{managers_display}</div>' if managers_display else ""
            rows += (
                f'<div class="strategy-player-row">'
                f'<div style="min-width:0;">'
                f'<div class="strategy-player">{player_name}</div>'
                f'{meta_html}'
                f'{managers_html}'
                f'</div>'
                f'<div class="strategy-score">{item.get("points", 0)} pts</div>'
                f'</div>'
            )

        subtitle_html = f'<div class="strategy-card-subtitle">{subtitle}</div>' if subtitle else ""
        return (
            f'<div class="strategy-card">'
            f'<div class="strategy-kicker">{kicker}</div>'
            f'{subtitle_html}'
            f'<div class="strategy-player-list">{rows}</div>'
            f'</div>'
        )

    highest_players = payload.get("highest_scoring_players") or ([payload.get("highest_scoring_player")] if payload.get("highest_scoring_player") else [])
    differential_players = payload.get("strategic_picks") or ([payload.get("strategic_pick")] if payload.get("strategic_pick") else [])
    strategy_cards.append(_strategy_collection_card("Highest scorers", highest_players))
    strategy_cards.append(_strategy_collection_card("Best differentials — Under 20% selected", differential_players))
    strategy_cards = [card for card in strategy_cards if card]

    if strategy_cards:
        strategic_html = f'<div class="strategy-grid">{"".join(strategy_cards)}</div>'
    else:
        strategic_html = (
            f'<div class="lms-box">'
            f'<div class="lms-title">No strategic picks this week</div>'
            f'<div class="lms-sub">No low-owned or non-captained player returned a standout score.</div>'
            f'</div>'
        )

    # Active form streaks — consecutive GWs above/below league average.
    form = payload.get("form_streaks", {}) or {}

    def _form_card(kind, title, data):
        names = data.get("names", []) if data else []
        streak = data.get("streak", 0) if data else 0
        cls = "good" if kind == "hot" else "bad"
        if form.get("is_gw1"):
            label = "GW1 starter" if streak else "No run yet"
        else:
            label = f'{streak} GW streak' if streak == 1 else f'{streak} GW streak'
        names_html = _name_pills(names) if names else '<span class="muted">—</span>'
        descriptor = "above league average" if kind == "hot" else "below league average"
        return (
            f'<div class="form-card">'
            f'<div class="form-kicker">{title}</div>'
            f'<div class="form-value {cls}">{label}</div>'
            f'<div class="form-meta">Longest active run {descriptor}</div>'
            f'<div class="strategy-managers">{names_html}</div>'
            f'</div>'
        )

    form_html = (
        f'<div class="form-grid">'
        f'{_form_card("hot", "Hot Streak", form.get("hot", {}))}'
        f'{_form_card("cold", "Out of Form", form.get("cold", {}))}'
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
            eliminated_display = ev.get("eliminated", "")
            if isinstance(eliminated_display, list):
                eliminated_display = ", ".join(str(x) for x in eliminated_display)

            if ev.get("escaped"):
              margin = ev.get("survival_margin")

              margin_html = ""
              if margin is not None:
                  tb = ev.get("survival_tiebreaker")
                  if margin == 0 and tb:
                      margin_html = (
                          f'<div class="lms-escaped-margin">'
                          f'Survived on {tb.get("label", "tie-breaker")} · '
                          f'{tb.get("escaped_value", "—")} vs {tb.get("eliminated_value", "—")}'
                          f'</div>'
                      )
                  else:
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
                  f'</div>'
              )

            eliminated_points_html = ""

            if ev.get("eliminated_points") is not None:
                eliminated_points_html = f' · {ev["eliminated_points"]} pts'

            lms_event_html = (
                f'<div class="lms-box">'
                f'<div class="lms-title">🧟 <span class="lms-key danger">{eliminated_display}</span> eliminated</div>'
                f'<div class="lms-sub">{ev["remaining"]} managers remain{eliminated_points_html}</div>'
                f'{escaped_html}'
                f'</div>'
            )

        elif ev['type'] == 'upcoming_double':
            lms_event_html = (
                f'<div class="lms-box">'
                f'<div class="lms-title">⚠️ <span class="lms-key warn">Double elimination next</span></div>'
                f'<div class="lms-sub">GW{ev.get("gw", "—")} · two managers go out · {ev.get("remaining", 0)} still alive</div>'
                f'<div class="lms-warning">LMS tie-breakers will use GW{ev.get("gw", "—")} data only.</div>'
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
              manager_pills = _name_pills(managers) if managers else ""
              meta = f'{count} manager{"s" if count != 1 else ""}'
              if manager_pills:
                  meta += f'<div class="transfer-market-managers">{manager_pills}</div>'
              pts = item.get("points", 0) or 0
              value = f'{pts} pts'
              if title.lower().endswith("in"):
                  value_class = "good" if pts > 3 else ("bad" if pts < 0 else "neutral")
              elif title.lower().endswith("out"):
                  value_class = "bad" if pts > 3 else ("good" if pts < 0 else "neutral")
              else:
                  value_class = "good" if pts > 3 else ("bad" if pts < 0 else "neutral")
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

    def _cup_grouped_fixture_html(fixtures, include_scores=False):
        grouped = defaultdict(list)
        order = []
        for f in fixtures or []:
            label = f.get("group") or f.get("round") or "Cup fixtures"
            if label not in grouped:
                order.append(label)
            grouped[label].append(f)

        html = ""
        for label in order:
            html += f'<div class="cup-group-title">{label}</div>'
            for f in grouped[label]:
                home_score = f.get("home_score")
                away_score = f.get("away_score")
                note = f.get("note", "")

                if include_scores and home_score is not None and away_score is not None:
                    try:
                        h_num = float(home_score)
                        a_num = float(away_score)
                    except (TypeError, ValueError):
                        h_num = a_num = 0

                    if h_num > a_num:
                        home_cls, away_cls = " winner", " loser"
                        home_score_cls, away_score_cls = "", " loser"
                    elif a_num > h_num:
                        home_cls, away_cls = " loser", " winner"
                        home_score_cls, away_score_cls = " loser", ""
                    else:
                        home_cls = away_cls = ""
                        home_score_cls = away_score_cls = ""

                    score_html = (
                        f'<span class="cup-match-score-value{home_score_cls}">{home_score}</span>'
                        f'<span>–</span>'
                        f'<span class="cup-match-score-value{away_score_cls}">{away_score}</span>'
                    )
                    score_wrap = f'<span class="cup-match-score">{score_html}</span>'
                else:
                    home_cls = away_cls = ""
                    score_wrap = '<span class="cup-match-score muted">v</span>'
                    if not note and not include_scores:
                        note = f'{f.get("home_seed", "")} vs {f.get("away_seed", "")}'.strip(" vs ")

                note_html = f'<div class="cup-note">{note}</div>' if note else ""
                html += (
                    f'<div class="cup-fixture">'
                    f'<div class="cup-match-row">'
                    f'<div class="cup-match-team{home_cls}">{f.get("home", "—")}</div>'
                    f'{score_wrap}'
                    f'<div class="cup-match-team away{away_cls}">{f.get("away", "—")}</div>'
                    f'</div>'
                    f'{note_html}'
                    f'</div>'
                )
        return html

    if cup_week and cup_week.get("winner"):
        cup_html = (
            f'<div class="cup-empty-box">'
            f'<div class="cup-empty-title">🏆 Cup winner</div>'
            f'<div class="cup-empty-sub">{cup_week.get("winner")}</div>'
            f'</div>'
        )

    elif cup_week and cup_week.get("fixtures"):
        fixture_rows = _cup_grouped_fixture_html(cup_week.get("fixtures", []), include_scores=True)

        cup_html = (
            f'<div class="cup-head">'
            f'<div class="cup-title">{cup_week.get("round", "Cup fixtures")}</div>'
            f'<div class="cup-status">{cup_week.get("status", "")}</div>'
            f'</div>'
            f'{fixture_rows}'
        )

    else:
        next_fixture_rows = ""
        if cup_week and cup_week.get("next_fixtures"):
            next_fixture_rows = _cup_grouped_fixture_html(cup_week.get("next_fixtures", []), include_scores=False)

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
                f'<div class="cup-empty-box">'
                f'<div class="cup-empty-title">🏆 Cup fixtures</div>'
                f'<div class="cup-empty-sub">Cup fixtures will appear here when the next round is ready.</div>'
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
    best_sub_manager = bench.get('best_sub_manager') or ''
    best_sub_out = bench.get('best_sub_out_name') or ''
    if bench.get('best_sub_pts', 0) > 0 and best_sub_manager:
        best_sub_detail = f"Auto-subbed into {best_sub_manager}'s final XI"
        if best_sub_out:
            best_sub_detail += f" for {best_sub_out}"
    else:
        best_sub_detail = 'No automatic substitutions this GW'

    best_bench_manager = bench.get('best_bench_manager') or bench.get('most_bench_manager') or ''
    if bench.get('best_bench_pts', 0) > 0 and best_bench_manager:
        best_bench_detail = f"Left on {best_bench_manager}'s bench"
    else:
        best_bench_detail = 'Highest-scoring player still benched'

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
          f'Div Avg {d.get("average", 0)} · <span class="division-gap">{above_avg_display} vs avg</span>'
          f'</div>'
          f'</div>'
      )

    if not division_weekly_html:
        division_weekly_html = '<div class="muted" style="font-size:13px">No division scores available</div>'
    else:
        division_weekly_html = f'<div class="division-grid">{division_weekly_html}</div>'

    golden_lines_list = _render_captaincy_lines(cap['golden_armband'])
    diff_cap = cap.get('differential_captain')
    diff_cap_row = ""
    if diff_cap:
        managers = diff_cap.get('managers', []) or []
        if len(managers) == 1:
            manager_line = managers[0]
        elif len(managers) > 1:
            manager_line = f'{len(managers)} managers'
        else:
            manager_line = f'Selected by {diff_cap.get("selected_count", 0)} managers'
        selected_count = diff_cap.get('selected_count', len(managers)) or len(managers)
        selected_word = 'manager' if selected_count == 1 else 'managers'
        if len(managers) == 1:
            diff_cap_meta = f"{managers[0]} ({diff_cap.get('selected_pct', 0)}% of league)"
        else:
            diff_cap_meta = f"{selected_count} {selected_word} ({diff_cap.get('selected_pct', 0)}% of league)"
        diff_cap_html = (
            f"<b>{diff_cap.get('player', '—')} ({diff_cap.get('points', 0)} pts)</b>"
            f"<br><span class='cap-value-muted'>{diff_cap_meta}</span>"
        )
        diff_cap_row = _captaincy_row("🎲", "Best differential captain", diff_cap_html)

    vice_hero = cap.get('vice_captain_hero')
    vice_hero_row = ""
    if vice_hero:
        managers = vice_hero.get('managers', [])
        manager_count = len(managers)
        manager_word = "manager" if manager_count == 1 else "managers"
        if manager_count == 1:
            manager_line = managers[0]
        else:
            manager_line = f"{manager_count} {manager_word}" if manager_count else "Vice-captain auto-swap"

        if (vice_hero.get('points', 0) or 0) > 5:
            vice_hero_html = (
                f"<b>{vice_hero.get('player', '—')} ({vice_hero.get('points', 0)} pts)</b>"
                f"<br><span class='cap-value-muted'>{manager_line}</span>"
            )
            vice_hero_row = _captaincy_row("🛟", "Vice-captain hero", vice_hero_html)

    golden_lines = "".join(f"<div>{line}</div>" for line in golden_lines_list)
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
  <div class="section-label">Top Performers</div>
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
  <div class="section-label">Captaincy Corner</div>
  {_captaincy_row(
      "❤️",
      "Most captained",
      f"<b>{cap['most_captained']} ({cap.get('most_captained_pts', 0)} pts)</b><br><span class='cap-value-muted'>{cap['most_captained_count']} managers</span>"
  )}
  {_captaincy_row("👑", "Golden armband", golden_lines)}
  {diff_cap_row}
  {vice_hero_row}
  {_captaincy_row("👻", "Captain dud", dud_lines)}
</div>

<div class="card">
  <div class="section-label">Gameweek Leaders</div>
  <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:8px">{stat_grid}</div>
</div>

<div class="card">
  <div class="section-label">Strategy Room</div>
  {strategic_html}

  <div style="height:12px"></div>

  <div class="section-label" style="margin-bottom:6px">League template</div>
  {template_html}
</div>

<div class="card">
  <div class="section-label">Form Guide</div>
  {form_html}
</div>

<div class="card">
  <div class="section-label">Transfer Market</div>
  {transfer_reports_html}
  {transfer_market_html}
</div>

<div class="card">
  <div class="section-label">Bench Watch</div>

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
      <div class="bench-detail">{best_bench_detail}</div>
    </div>
    <div class="bench-score warn">{bench['best_bench_pts']} pts</div>
  </div>

  <div class="bench-row">
    <div>
      <div class="bench-label">Best auto-sub</div>
      <div class="bench-name">{bench.get('best_sub_name') or 'No auto-subs'}</div>
      <div class="bench-detail">{best_sub_detail}</div>
    </div>
    <div class="bench-score {'good' if bench.get('best_sub_pts', 0) > 0 else 'neutral'}">{str(bench.get('best_sub_pts', 0)) + ' pts' if bench.get('best_sub_pts', 0) > 0 else '—'}</div>
  </div>

</div>

<div class="card">
  <div class="section-label">Chip Review</div>
  {chips_html}
</div>

<div class="card">
  <div class="section-label">Division Breakdown</div>
  {division_weekly_html}
</div>

<div class="card">
  <div class="section-label">Manager of the Block</div>
  {block_html}
</div>

<div class="card">
  <div class="section-label">Last Man Standing</div>
  {lms_event_html}
</div>

<div class="card cup-centre-section">
  <div class="section-label">Cup Centre</div>
  {cup_html}
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

    # Also mirror debriefs into /newsletters so GitHub Pages links from the hub work cleanly.
    mirror_dir = os.path.join(output_dir, DEBRIEF_DIR)
    try:
        os.makedirs(mirror_dir, exist_ok=True)
        mirror_path = os.path.join(mirror_dir, f"gw_{gameweek}_poster.html")
        mirror_html = html.replace('href="league_hub.html"', 'href="../league_hub.html"')
        with open(mirror_path, "w", encoding="utf-8") as f:
            f.write(mirror_html)
    except OSError:
        mirror_path = None

    print(f"  [HTML] GW poster → {path}")
    if mirror_path:
        print(f"  [HTML] GW debrief mirror → {mirror_path}")
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

    # Completed blocks may reset current_block_points to 0, so prefer
    # the named block snapshot when it exists. Live/current blocks still
    # fall back to current_block_points.
    if isinstance(block_stats.get(bname), dict):
        b = block_stats.get(bname, {})
        return b.get('points', b.get('total_points', 0))

    total = 0
    history = mdata.get('gw_history', {}) or {}
    has_history = False
    for gw in gws:
        row = history.get(str(gw), history.get(gw, {})) or {}
        if row:
            has_history = True
        total += row.get('net_gw_points', row.get('points', row.get('gw_points', 0)))
    if has_history:
        return total

    if block_stats.get('current_block_points') is not None:
        return block_stats.get('current_block_points', 0)

    return total


def _tiebreakers_html(master, current_gw, gw_results=None, scope=None):
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
    if scope in (None, "divisions"):
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
        standings = bdata.get('standings', {}) or {}
        name_to_mid = {mdata.get('name'): str(mid) for mid, mdata in managers.items()}
        if won and standings:
            standing_items = standings.values() if isinstance(standings, dict) else standings
            for e in standing_items:
                if not isinstance(e, dict):
                    continue
                mid = str(e.get('manager_id') or name_to_mid.get(e.get('name'), ''))
                if not mid:
                    continue
                points = e.get('points', e.get('total_points'))
                if points in (None, ''):
                    points = _block_points_for_manager(managers.get(mid, {}), bname, gws)
                entries.append({"manager_id": mid, "name": e.get('name', _manager_name(master, mid)), "points": points})
        else:
            for mid, mdata in managers.items():
                points = _block_points_for_manager(mdata, bname, gws)
                entries.append({"manager_id": str(mid), "name": mdata.get("name", str(mid)), "points": points})

        entries = sorted(entries, key=lambda e: _as_num(e.get("points", 0)), reverse=True)
        # If a completed block has no stored standings/history and every rebuilt
        # score is 0, do not manufacture a giant tie-breaker card.
        if won and (not standings) and entries and all(_as_num(e.get('points', 0)) == 0 for e in entries):
            continue
        point_groups = []
        current_pos = 1
        i = 0
        while i < len(entries):
            points = entries[i].get("points", 0)
            tied = [entries[i]]
            j = i + 1
            while j < len(entries) and _as_num(entries[j].get("points", 0)) == _as_num(points):
                tied.append(entries[j])
                j += 1

            group_size = len(tied)
            start_rank = current_pos
            end_rank = current_pos + group_size - 1
            current_pos = end_rank + 1
            i = j

            # Live blocks: only explain ties that affect the top three.
            # Complete blocks: only show a tie-breaker if the winning spot itself was tied.
            show_block_tb = group_size > 1 and ((won and start_rank == 1) or ((not won) and start_rank <= 3))
            if show_block_tb:
                tied_ids = [x["manager_id"] for x in tied]
                rule = _first_tb_rule(master, tied_ids, block_rules[1:])
                tied = _sort_by_official_tiebreakers(
                    tied,
                    key_fn=lambda x: _tb_sort_key(
                        master,
                        x.get("manager_id", ""),
                        block_rules[1:],
                        primary_value=x.get("points"),
                    ),
                )
                point_groups.append((points, tied, rule))

        if point_groups:
            block_groups_html += f'<div class="hub-tb-group"><div class="hub-tb-context"><div class="hub-tb-context-title">{bname}</div><div class="hub-tb-context-meta">Top-three tie situations only</div></div>'
            for points, tied, rule in point_groups:
                block_groups_html += (
                    f'<div class="hub-tb-subgroup">'
                    f'<div class="hub-tb-context-meta" style="text-align:left;margin-bottom:4px;">{points} block pts · sorted by {_rule_short_label(rule)}</div>'
                    f'{_tiebreak_rows(master, tied, block_rules[1:], "Pts", "points", rule)}'
                    f'</div>'
                )
            block_groups_html += '</div>'

    if scope in (None, "block"):
        cards.append(("Manager of the Block", "Top-three block tie situations", block_rules, block_groups_html))

    # LMS
    lms_rules = RULES_REFERENCE["lms_tiebreakers"]
    lms_groups_html = ""
    lms = master.get('competitions', {}).get('lms', {})
    name_to_mid = {mdata.get("name"): str(mid) for mid, mdata in managers.items()}
    for gw, eliminated_value in sorted(lms.get('eliminated', {}).items(), key=lambda x: int(x[0])):
        # LMS eliminations may be stored as a single manager name/id, a list of
        # names/ids for double-elimination weeks, or richer dictionaries.
        if isinstance(eliminated_value, (list, tuple, set)):
            eliminated_items = list(eliminated_value)
        else:
            eliminated_items = [eliminated_value]

        for eliminated_item in eliminated_items:
            eliminated_name = eliminated_item
            elim_mid = None

            if isinstance(eliminated_item, dict):
                elim_mid = eliminated_item.get('id') or eliminated_item.get('manager_id') or eliminated_item.get('entry_id')
                eliminated_name = eliminated_item.get('name') or eliminated_item.get('manager_name') or eliminated_item.get('entry_name')

            if elim_mid is None:
                elim_mid = name_to_mid.get(eliminated_name)

            # Some engines store manager ids directly in the eliminated map.
            if elim_mid is None and str(eliminated_name) in managers:
                elim_mid = str(eliminated_name)

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
    if scope in (None, "lms"):
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
            rule = _first_tb_rule(master, tied_ids, cup_rules[1:], cup_stats_by_mid=cup_stats_by_mid)
            cup_groups_html += _tiebreak_group_html(master, group_name, f"Group points {points}", cup_rules[1:], tied, "Pts", "points", rule, cup_stats_by_mid=cup_stats_by_mid)
    if scope in (None, "cup"):
        cards.append(("Cup groups", "Group-stage tables", cup_rules, cup_groups_html))

    # Cup knockouts: rules card only for now; live tie explanations can be added once knockout tie rows are stored.
    if scope in (None, "cup"):
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



def _competition_info_html(master, section):
    """Small info pill explaining each hub competition area."""
    pr = master.get('promotion_relegation', {}) or {}
    places = pr.get('places', 2)
    cup = master.get('competitions', {}).get('cup', {}) or {}
    blocks = master.get('competitions', {}).get('blocks', {}) or {}
    lms = master.get('competitions', {}).get('lms', {}) or {}

    copy = {
        'divisions': f'<strong>Divisions</strong> — Top {places} are marked green for prize/promotion places; bottom {places} are marked red where relegation applies.',
        'lms': f'<strong>Last Man Standing</strong> — Scheduled elimination weeks remove the lowest scoring active manager after official LMS tie-breakers.',
        'cup': f'<strong>Cup</strong> — Group-stage standings decide qualification before the knockout bracket. Fixtures/results appear as rounds become active.',
        'block': f'<strong>Manager of the Block</strong> — Short GW blocks reward the highest points scored during the active block only.',
        'chips': '<strong>Chip Leaderboard</strong> — Ranks managers by stored chip impact across the season.',
        'acc': '<strong>Accolades</strong> — Season-long award races and active form streaks. Weekly stories stay in the GW debrief.',
    }
    text = copy.get(section)
    if not text:
        return ''
    return f'<div class="hub-info-pill">{text}</div>'


def _hub_form_streaks_html(master, current_gw):
    """Season-long best runs above/below league average for the Accolades tab."""
    manager_items = list((master.get('managers', {}) or {}).items())
    managers = [m for _, m in manager_items]
    if not managers or not current_gw:
        return '<div class="hub-acc-empty">No form streak data available yet</div>'

    def _row(mid, m, gw):
        history = m.get('gw_history', {}) or {}
        row = history.get(str(gw), history.get(gw, {})) or {}
        if row:
            return row
        global_history = master.get('gw_history', {}) or {}
        snapshot = global_history.get(str(gw), global_history.get(gw, {})) or {}
        return snapshot.get(str(mid), snapshot.get(mid, {})) or {}

    def _score(mid, m, gw):
        r = _row(mid, m, gw)
        if not r:
            return None
        return r.get('net_gw_points', r.get('gw_points', r.get('points')))

    def _avg(gw):
        vals = [x for x in (_score(mid, m, gw) for mid, m in manager_items) if x is not None]
        return sum(vals) / len(vals) if vals else None

    def _best_run(mid, m, mode):
        best = 0
        current = 0
        for gw in range(1, int(current_gw) + 1):
            score = _score(mid, m, gw)
            avg = _avg(gw)
            if score is None or avg is None:
                current = 0
                continue
            ok = score > avg if mode == 'hot' else score < avg
            if ok:
                current += 1
                best = max(best, current)
            else:
                current = 0
        return best

    def _ranked_runs(mode):
        by_value = defaultdict(list)
        for mid, m in manager_items:
            streak = _best_run(mid, m, mode)
            if streak > 0:
                by_value[streak].append(m.get('name', '—'))
        medals = ['🥇', '🥈', '🥉']
        rows = ''
        for idx, streak in enumerate(sorted(by_value.keys(), reverse=True)[:3]):
            names = sorted(by_value[streak], key=lambda n: n.lower())
            value = streak
            joint_html = f'<span class="hub-acc-tie">Joint x{len(names)}</span>' if len(names) > 1 else ''
            rows += (
                f'<div class="hub-acc-rank-row">'
                f'<span class="hub-acc-medal">{medals[idx]}</span>'
                f'<span class="hub-acc-manager">{_name_pills(names, "hub-name-pills", "hub-name-pill")}</span>'
                f'<span class="hub-acc-value-wrap"><span class="hub-acc-value">{value}</span>{joint_html}</span>'
                f'</div>'
            )
        return rows or '<div class="hub-acc-empty">No data available yet</div>'

    def _card(title, cls, mode):
        info_html = f'<div class="hub-acc-info">{AWARD_INFO.get(title, "")}</div>' if AWARD_INFO.get(title) else ''
        return (
            f'<div class="hub-acc-card">'
            f'<div class="hub-acc-title"><span>{"🔥" if cls == "good" else "🥶"}</span><span>{title}</span></div>'
            f'{info_html}'
            f'<div class="hub-acc-ranks">{_ranked_runs(mode)}</div>'
            f'</div>'
        )

    return _card('Hot Streak', 'good', 'hot') + _card('Out of Form', 'bad', 'cold')


# ─────────────────────────────────────────────────────────────────────────────
# LEAGUE HUB
# ─────────────────────────────────────────────────────────────────────────────

def build_hub(gameweek, master, output_dir=".", gw_results=None):
    """Generates the always-current league hub HTML."""

    div_tables  = _div_tables_html(master, gw_results or {}, gameweek)
    lms_section = _lms_html(master, gameweek)
    cup_section = _cup_html(master, gameweek)
    blocks_sec  = _blocks_html(master, gameweek)
    player_pick_h, captaincy_awards_h, strategy_awards_h, transfer_awards_h, bench_awards_h, performance_h, form_awards_h, chip_awards_h = _accolades_html(master)
    chip_leaderboard = _chip_leaderboard_html(master, gw_results or {})
    div_tiebreakers = _tiebreakers_html(master, gameweek, gw_results or {}, scope="divisions")
    lms_tiebreakers = _tiebreakers_html(master, gameweek, gw_results or {}, scope="lms")
    cup_tiebreakers = _tiebreakers_html(master, gameweek, gw_results or {}, scope="cup")
    block_tiebreakers = _tiebreakers_html(master, gameweek, gw_results or {}, scope="block")
    form_streaks_hub = _hub_form_streaks_html(master, gameweek)
    live_status = _live_status_html(master, gameweek)
    debriefs_section = _debriefs_html(master, gameweek)

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
  <button class="nav-btn" onclick="show('debriefs',this)">Debriefs</button>
  <button class="nav-btn" onclick="show('lms',this)">LMS</button>
  <button class="nav-btn" onclick="show('cup',this)">Cup</button>
  <button class="nav-btn" onclick="show('block',this)">Block</button>
  <button class="nav-btn" onclick="show('acc',this)">Accolades</button>
  <button class="nav-btn" onclick="show('chips',this)">Chip Leaderboard</button>
</div>

<div class="section active" id="divs">
  <div class="card">
    <div class="section-label">What’s live this GW</div>
    {live_status}
  </div>
  <div class="card">
    {_competition_info_html(master, "divisions")}
    {div_tables}
  </div>
  <div class="card">
    <div class="section-label">Division tie-breakers</div>
    {div_tiebreakers}
  </div>
</div>


<div class="section" id="debriefs">
  <div class="card">
    <div class="section-label">Debrief archive</div>
    <div class="hub-info-pill"><strong>Weekly archive</strong> — Open previous GW debriefs from one place.</div>
    {debriefs_section}
  </div>
</div>

<div class="section" id="lms">
  <div class="card">
    {_competition_info_html(master, "lms")}
    {lms_section}
  </div>
</div>

<div class="section" id="cup">
  <div class="card">
    <div class="section-label">Cup centre</div>
    {_competition_info_html(master, "cup")}
    {cup_section}
  </div>
  <div class="card">
    <div class="section-label">Cup tie-breakers</div>
    {cup_tiebreakers}
  </div>
</div>

<div class="section" id="block">
  <div class="card">
    <div class="section-label">Manager of the block</div>
    {_competition_info_html(master, "block")}
    {blocks_sec}
  </div>
  <div class="card">
    <div class="section-label">Block tie-breakers</div>
    {block_tiebreakers}
  </div>
</div>


<div class="section" id="acc">
  <div class="card">
    <div class="section-label">Accolades info</div>
    {_competition_info_html(master, "acc")}
  </div>
  <div class="card">
    <div class="section-label">Player pick awards</div>
    {player_pick_h}
  </div>
  <div class="card">
    <div class="section-label">Captaincy awards</div>
    {captaincy_awards_h}
  </div>
  <div class="card">
    <div class="section-label">Strategy awards</div>
    {strategy_awards_h}
  </div>
  <div class="card">
    <div class="section-label">Transfer awards</div>
    {transfer_awards_h}
  </div>
  <div class="card">
    <div class="section-label">Bench awards</div>
    {bench_awards_h}
  </div>
  <div class="card">
    <div class="section-label">Performance awards</div>
    {performance_h}
  </div>
  <div class="card">
    <div class="section-label">Form awards</div>
    {form_awards_h}
  </div>
  <div class="card">
    <div class="section-label">Chip awards</div>
    {chip_awards_h}
  </div>
</div>

<div class="section" id="chips">
  <div class="card">
    <div class="section-label">Chip Leaderboard</div>
    {_competition_info_html(master, "chips")}
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
