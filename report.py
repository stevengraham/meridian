"""Meridian — PDF/PNG report generation (pure Python, no QGIS imports)."""

import math

try:
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.backends.backend_pdf import PdfPages
    from matplotlib.lines import Line2D
    _MPL_OK = True
except ImportError:
    _MPL_OK = False


# ── palette ───────────────────────────────────────────────────────────────────

_C_GRID = "#111111"
_C_TRUE = "#1565C0"
_C_MAG = "#B71C1C"
_DASH = (0, (6, 3))


# ── geometry helpers ──────────────────────────────────────────────────────────

def _deg2xy(a):
    """Unit vector `a` degrees east (clockwise) of vertical."""
    r = math.radians(a)
    return math.sin(r), math.cos(r)


def _arc_pts(cx, cy, radius, a1, a2, n=80):
    """(xs, ys) for arc between a1 and a2 (degrees from vertical, east-positive)."""
    lo, hi = (a1, a2) if a1 <= a2 else (a2, a1)
    ts = [lo + (hi - lo) * i / (n - 1) for i in range(n)]
    xs = [cx + radius * math.sin(math.radians(t)) for t in ts]
    ys = [cy + radius * math.cos(math.radians(t)) for t in ts]
    return xs, ys


# ── diagram primitives ────────────────────────────────────────────────────────

def _arrow(ax, ox, oy, length, angle, color, dashed=False, lw=2.0):
    """Shaft + filled triangular head."""
    dx, dy = _deg2xy(angle)
    x2, y2 = ox + length * dx, oy + length * dy
    ls = _DASH if dashed else "-"
    ax.plot([ox, x2], [oy, y2], color=color, lw=lw, linestyle=ls,
            solid_capstyle="butt", zorder=3)
    hw, hl = 0.011, 0.028
    base = (x2 - dx * hl, y2 - dy * hl)
    p1 = (base[0] - dy * hw, base[1] + dx * hw)
    p2 = (base[0] + dy * hw, base[1] - dx * hw)
    ax.fill([x2, p1[0], p2[0]], [y2, p1[1], p2[1]], color=color, zorder=4)


def _tip_label(ax, ox, oy, length, angle, text, color, extra=0.02, nudge=0.012):
    """Rotated text alongside the arrow tip, nudged left of the shaft.

    extra  : gap in data units between arrowhead tip and text bottom edge.
    nudge  : perpendicular offset in data units (left of shaft direction).
    """
    dx, dy = _deg2xy(angle)
    r = length + extra
    px = ox + r * dx - dy * nudge
    py = oy + r * dy + dx * nudge
    rot = 90 - angle            # matplotlib: 90 = vertical up
    ax.text(px, py, text, rotation=rot, rotation_mode="anchor",
            ha="center", va="bottom", fontsize=8.5, color=color,
            fontweight="bold", clip_on=False, zorder=5)


def _arc_label(ax, ox, oy, radius, a1, a2, color, label=None, side="right"):
    """Arc with tick marks at each end and an optional horizontal callout label."""
    if abs(a1 - a2) < 0.05:
        return
    xs, ys = _arc_pts(ox, oy, radius, a1, a2)
    ax.plot(xs, ys, color=color, lw=1.2, zorder=2)

    # Small tick marks at each end
    for ae in (a1, a2):
        dxe, dye = _deg2xy(ae)
        ax.plot(
            [ox + (radius - 0.012) * dxe, ox + (radius + 0.012) * dxe],
            [oy + (radius - 0.012) * dye, oy + (radius + 0.012) * dye],
            color=color, lw=1.0, zorder=2,
        )

    if label is None:
        return

    # Horizontal callout line from arc midpoint to the chosen side
    a_mid = (a1 + a2) / 2
    mx = ox + radius * math.sin(math.radians(a_mid))
    my = oy + radius * math.cos(math.radians(a_mid))
    callout = 0.14
    if side == "right":
        ex = mx + callout
        ax.plot([mx, ex], [my, my], color=color, lw=0.9,
                ls=(0, (4, 3)), clip_on=False, zorder=2)
        ax.text(ex + 0.018, my, label, ha="left", va="center",
                fontsize=9, color=color, fontweight="bold",
                clip_on=False, zorder=6)
    else:  # left
        ex = mx - callout
        ax.plot([mx, ex], [my, my], color=color, lw=0.9,
                ls=(0, (4, 3)), clip_on=False, zorder=2)
        ax.text(ex - 0.018, my, label, ha="right", va="center",
                fontsize=9, color=color, fontweight="bold",
                clip_on=False, zorder=6)


# ── diagram axes ──────────────────────────────────────────────────────────────

def _draw_north_diagram(ax, declination, grid_convergence):
    """
    Draw the north relationships fan diagram.

    declination      : D in decimal degrees, positive east.
    grid_convergence : γ in decimal degrees (positive = grid east of true),
                       or None when the CRS is geographic.
    """
    gma = (declination - grid_convergence) if grid_convergence is not None else None

    # Angle from vertical (east = positive clockwise)
    a_grid = 0.0
    a_true = (-grid_convergence) if grid_convergence is not None else None
    a_mag = gma if gma is not None else declination

    ox, oy = 0.50, 0.04

    # Staggered lengths so labels at different heights never overprint.
    # Grid North is longest (reference line); True North shortest because it
    # sits closest to Grid North and needs its label pushed well below.
    L_GRID = 0.86
    L_MAG = 0.72
    L_TRUE = 0.58

    ax.set_xlim(-0.12, 1.12)
    ax.set_ylim(-0.02, 1.05)
    ax.set_aspect("equal", adjustable="datalim")
    ax.axis("off")

    # Draw shorter arrows first so Grid North sits on top at the origin.
    if a_true is not None:
        _arrow(ax, ox, oy, L_TRUE, a_true, _C_TRUE, dashed=True, lw=1.8)
    _arrow(ax, ox, oy, L_MAG, a_mag, _C_MAG, lw=1.8)
    _arrow(ax, ox, oy, L_GRID, a_grid, _C_GRID, lw=2.5)   # thicker, drawn last

    # ── tip labels ──
    # Grid and Mag: tiny nudge so text sits right alongside the shaft.
    # True North: wider nudge so it clears Grid North's shaft (near-coincident arrows).
    _tip_label(ax, ox, oy, L_GRID, a_grid, "Grid North", _C_GRID, nudge=0.008)
    if a_true is not None:
        _tip_label(ax, ox, oy, L_TRUE, a_true, "True North", _C_TRUE, nudge=0.025)
    _tip_label(ax, ox, oy, L_MAG, a_mag, "Magnetic North", _C_MAG, nudge=0.008)

    # ── arcs ──
    # γ: Grid ↔ True, label to the LEFT of its arc
    if a_true is not None and abs(grid_convergence) > 0.005:
        _arc_label(ax, ox, oy, 0.20, a_grid, a_true, _C_TRUE,
                   label=f"γ = {grid_convergence:+.3f}°", side="left")

    # D: True ↔ Magnetic (or Grid ↔ Magnetic when no grid CRS), label to the RIGHT
    if a_true is not None:
        _arc_label(ax, ox, oy, 0.38, a_true, a_mag, _C_MAG,
                   label=f"D = {declination:+.3f}°", side="right")
    else:
        _arc_label(ax, ox, oy, 0.35, a_grid, a_mag, _C_MAG,
                   label=f"D = {declination:+.3f}°", side="right")

    # GMA: Grid ↔ Magnetic — arc drawn for visual context, no label
    if gma is not None and abs(gma) > 0.005:
        _arc_label(ax, ox, oy, 0.57, a_grid, a_mag, _C_GRID)

    # Origin dot
    ax.plot(ox, oy, "o", color="black", ms=5, zorder=7)

    # Legend
    handles = [
        Line2D([0], [0], color=_C_GRID, lw=2, label="Grid North"),
    ]
    if a_true is not None:
        handles.append(
            Line2D([0], [0], color=_C_TRUE, lw=2, ls=_DASH, label="True North")
        )
    handles.append(
        Line2D([0], [0], color=_C_MAG, lw=2, label="Magnetic North")
    )
    ax.legend(handles=handles, loc="lower right", fontsize=8.5,
              framealpha=0.92, edgecolor="#aaa")


# ── info table axes ───────────────────────────────────────────────────────────

def _build_table_rows(lat, lon, date_str, model, crs_name,
                      declination, grid_convergence, components=None):
    """Build the list of [param, value] rows for the info table.

    Single source of truth used by both _draw_info_table and _table_rows.
    """
    gma = (declination - grid_convergence) if grid_convergence is not None else None
    rows = [
        ["Latitude", f"{lat:+.6f}°"],
        ["Longitude", f"{lon:+.6f}°"],
        ["Date", date_str],
        ["Model", model],
    ]
    if crs_name:
        rows.append(["Grid CRS", crs_name])
    rows.append(["", ""])  # visual separator
    rows.append(["Magnetic Declination  D",
                 f"{declination:+.4f}° E" if not math.isnan(declination) else "—"])
    if grid_convergence is not None:
        rows.append(["Grid Convergence  γ", f"{grid_convergence:+.4f}° E"])
        rows.append(["Grid Magnetic Angle  GMA = D − γ",
                     f"{gma:+.4f}°" if gma is not None else "—"])
    if components:
        rows.append(["", ""])
        rows.append(["Inclination  I", f"{components['I']:+.4f}°"])
        rows.append(["Horizontal intensity  H", f"{components['H']:.2f} nT"])
        rows.append(["Total intensity  F", f"{components['F']:.2f} nT"])
        rows.append(["North component  X", f"{components['X']:.2f} nT"])
        rows.append(["East component  Y", f"{components['Y']:.2f} nT"])
        rows.append(["Vertical component  Z", f"{components['Z']:.2f} nT"])
    return rows


def _draw_info_table(ax, lat, lon, date_str, model, crs_name,
                     declination, grid_convergence, components=None):
    """Render a styled parameter/value table on ax."""
    ax.axis("off")

    rows = _build_table_rows(lat, lon, date_str, model, crs_name,
                             declination, grid_convergence, components)

    col_labels = ["Parameter", "Value"]
    tbl = ax.table(
        cellText=rows,
        colLabels=col_labels,
        cellLoc="left",
        loc="center",
        colWidths=[0.68, 0.32],
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(8.5)
    tbl.scale(1, 1.45)

    # Header row style
    for j in range(2):
        cell = tbl[(0, j)]
        cell.set_facecolor("#2c3e50")
        cell.get_text().set_color("white")
        cell.get_text().set_fontweight("bold")

    # Body rows
    for i, row in enumerate(rows, start=1):
        is_sep = row[0] == ""
        for j in range(2):
            cell = tbl[(i, j)]
            if is_sep:
                cell.set_facecolor("#e8e8e8")
                cell.set_linewidth(0)
            elif i % 2 == 0:
                cell.set_facecolor("#f4f6f8")


# ── worked examples ───────────────────────────────────────────────────────────

def _add_worked_examples(fig, declination, grid_convergence, annual_rate,
                         y_top, y_bottom):
    """
    Render worked-examples text directly onto fig between y_top and y_bottom
    (figure coordinates 0–1).  Shows azimuth=45° converted to grid, plus the
    annual rate of declination change.
    """
    gma = (declination - grid_convergence) if grid_convergence is not None else None
    az = 45.0

    # Thin separator line above the section
    fig.add_artist(
        Line2D([0.06, 0.94], [y_top, y_top],
               transform=fig.transFigure, color="#cccccc", lw=0.8)
    )

    dy = (y_top - y_bottom) / 5.2        # line height in figure coords
    x_lhs = 0.08                         # left column (formula)
    x_ann = 0.40                         # right column (annotation)
    y = y_top - dy * 0.55

    # Heading
    fig.text(x_lhs, y, "Worked Examples — Azimuth Conversion to Grid North",
             fontsize=8.5, fontweight="bold", color="#1a1a1a",
             transform=fig.transFigure)
    y -= dy * 1.1

    # ── True → Grid ──
    if grid_convergence is not None:
        grid_from_true = az - grid_convergence
        fig.text(x_lhs, y,
                 f"True {az:.2f}°  →  Grid {grid_from_true:.2f}°",
                 fontsize=8.5, color="#111111", transform=fig.transFigure)
        fig.text(x_ann, y,
                 f"subtract  γ = {grid_convergence:+.3f}°",
                 fontsize=8, color=_C_TRUE, transform=fig.transFigure)
        y -= dy

    # ── Magnetic → Grid ──
    if gma is not None:
        grid_from_mag = az + gma
        fig.text(x_lhs, y,
                 f"Magnetic {az:.2f}°  →  Grid {grid_from_mag:.2f}°",
                 fontsize=8.5, color="#111111", transform=fig.transFigure)
        fig.text(x_ann, y,
                 f"add  GMA = {gma:+.3f}°",
                 fontsize=8, color=_C_MAG, transform=fig.transFigure)
        y -= dy
    elif not math.isnan(declination):
        # Geographic CRS — only declination applies
        grid_from_mag = az + declination
        fig.text(x_lhs, y,
                 f"Magnetic {az:.2f}°  →  True/Grid {grid_from_mag:.2f}°",
                 fontsize=8.5, color="#111111", transform=fig.transFigure)
        fig.text(x_ann, y,
                 f"add  D = {declination:+.3f}°",
                 fontsize=8, color=_C_MAG, transform=fig.transFigure)
        y -= dy

    # ── Annual rate of change ──
    if annual_rate is not None and not math.isnan(annual_rate):
        direction = "eastward" if annual_rate >= 0 else "westward"
        fig.text(x_lhs, y,
                 f"Declination changing at  {annual_rate:+.4f}°/year"
                 f"  ({direction})",
                 fontsize=8.5, color="#444444", transform=fig.transFigure)

    # No bottom separator — the table's dark header row provides the visual break.


# ── public API ────────────────────────────────────────────────────────────────

def north_diagram_figure(
    *,
    lat: float,
    lon: float,
    date_str: str,
    model: str,
    crs_name: str,
    declination: float,
    grid_convergence,          # float or None
    components=None,           # dict {I,H,F,X,Y,Z} or None
    annual_rate=None,          # float or None
) -> "Figure":
    """
    Build and return a matplotlib Figure (A4/Letter portrait) containing:
      - title + location header
      - north relationships diagram
      - parameter / values table
    """
    if not _MPL_OK:
        raise RuntimeError(
            "matplotlib is not available in this Python environment."
        )

    fig = Figure(figsize=(8.5, 11.0), facecolor="white")
    canvas = FigureCanvasAgg(fig)  # store reference so fig stays attached

    # ── header ──
    fig.text(0.50, 0.965, "North Relationships",
             ha="center", fontsize=20, fontweight="bold", color="#1a1a1a")

    subtitle = f"Lat {lat:+.6f}°    Lon {lon:+.6f}°    Date {date_str}    Model: {model}"
    fig.text(0.50, 0.940, subtitle,
             ha="center", fontsize=9, color="#444444")

    if crs_name:
        fig.text(0.50, 0.921, f"Grid CRS: {crs_name}",
                 ha="center", fontsize=8.5, color="#666666")

    # Separator line under header
    line_y = 0.912
    fig.add_artist(
        Line2D(
            [0.06, 0.94], [line_y, line_y],
            transform=fig.transFigure,
            color="#cccccc", lw=0.8,
        )
    )

    # ── dynamic layout: compute table height from actual row count ──
    # +1 for the header row; 0.016 per row; no upper clamp so all rows are visible
    n_rows = 1 + len(_table_rows(
        lat, lon, date_str, model, crs_name, declination, grid_convergence, components
    ))
    table_height = max(0.14, 0.05 + n_rows * 0.016)
    examples_bot = 0.02 + table_height + 0.01
    examples_top = examples_bot + 0.11
    diag_bot = examples_top + 0.005
    diag_height = max(0.30, 0.905 - diag_bot)

    # ── diagram axes ──
    ax_diag = fig.add_axes([0.07, diag_bot, 0.86, diag_height])
    _draw_north_diagram(ax_diag, declination, grid_convergence)

    # ── worked examples ── (between diagram and table)
    _add_worked_examples(fig, declination, grid_convergence, annual_rate,
                         y_top=examples_top, y_bottom=examples_bot)

    # ── table axes ──
    ax_tbl = fig.add_axes([0.07, 0.02, 0.86, table_height])
    _draw_info_table(ax_tbl, lat, lon, date_str, model, crs_name,
                     declination, grid_convergence, components)

    _ = canvas  # prevent GC of canvas before savefig
    return fig


def _table_rows(lat, lon, date_str, model, crs_name,
                declination, grid_convergence, components):
    """Return the table rows list (delegates to _build_table_rows for single source of truth)."""
    return _build_table_rows(lat, lon, date_str, model, crs_name,
                             declination, grid_convergence, components)


def save_report(path: str, fmt: str, **kwargs) -> None:
    """
    Generate and save a north corrections report.

    path : destination file path
    fmt  : "pdf" or "png"
    **kwargs are forwarded to north_diagram_figure()
    """
    fig = north_diagram_figure(**kwargs)
    if fmt == "pdf":
        with PdfPages(path) as pdf:
            pdf.savefig(fig, dpi=150, facecolor="white")
    else:
        fig.savefig(path, dpi=150, facecolor="white", bbox_inches="tight")
    fig.clf()
