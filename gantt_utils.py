import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.patheffects as pe
from matplotlib import rcParams
from matplotlib.widgets import Button, Slider
from matplotlib.lines import Line2D
import mplcursors
import warnings
warnings.filterwarnings("ignore")

from settings import *

rcParams['font.family'] = FONT_FAMILY


# ════════════════════════════════════════════════════════════════
#  DATA LOADING
# ════════════════════════════════════════════════════════════════

def _load_numbers(file_path):
    """Read a .numbers file directly using numbers-parser."""
    from numbers_parser import Document
    doc  = Document(file_path)
    sheet = doc.sheets[0]
    table = sheet.tables[0]
    rows  = list(table.rows())

    # Find the header row (contains 'Task ID')
    header_idx = None
    for i, row in enumerate(rows):
        vals = [str(c.value).strip() if c.value is not None else '' for c in row]
        if 'Task ID' in vals:
            header_idx = i
            break
    if header_idx is None:
        raise ValueError("Could not find 'Task ID' header in .numbers file.")

    headers = [str(rows[header_idx][j].value).strip()
               for j in range(len(rows[header_idx]))]

    records = []
    for row in rows[header_idx + 1:]:
        vals = [c.value for c in row]
        if all(v is None or str(v).strip() == '' for v in vals):
            continue
        records.append(dict(zip(headers, vals)))

    return pd.DataFrame(records)


def load_tasks(file_path, sheet_name='Sheet 1'):
    ext = str(file_path).lower().split('.')[-1]

    if ext == 'numbers':
        df = _load_numbers(file_path)
    else:
        raw = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
        header_row = None
        for i, row in raw.iterrows():
            if any(str(v).strip() == 'Task ID' for v in row.values):
                header_row = i
                break
        if header_row is None:
            raise ValueError("Could not find a 'Task ID' header row.")
        df = pd.read_excel(file_path, sheet_name=sheet_name, header=header_row)
        df.columns = [str(c).strip() for c in df.columns]

    rename = {
        'Task ID':      'task_id',
        'Aim':          'aim',
        'Task':         'task',
        'Description':  'description',
        'Dependencies': 'dependencies',
        'Start Date':   'start_date',
        'End Date':     'end_date',
        'Status':       'status',
        'Progress':     'progress',
        'Milestone':    'milestone',
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

    # Drop empty rows
    df = df[pd.to_numeric(df['task_id'], errors='coerce').notna()].copy()
    df['task_id']    = df['task_id'].astype(int)
    df['start_date'] = pd.to_datetime(df['start_date'])
    df['end_date']   = pd.to_datetime(df['end_date'])
    df['dependencies'] = df['dependencies'].apply(
        lambda x: int(float(x)) if pd.notna(x) and str(x).strip() not in ('', 'nan') else None
    )
    for col in ['task', 'description', 'aim']:
        df[col] = df[col].astype(str).str.replace(r'\s+', ' ', regex=True).str.strip()

    # Status — use column if present, else infer from dates
    if 'status' not in df.columns:
        df['status'] = _infer_status(df)
    else:
        df['status'] = df['status'].astype(str).str.strip().str.replace(r'\s+', ' ', regex=True)
        df['status'] = df['status'].replace('nan', None)
        df['status'] = df['status'].where(df['status'].isin(STATUS_COLORS.keys()), None)
        inferred = pd.Series(_infer_status(df), index=df.index)
        df['status'] = df['status'].fillna(inferred)

    # Progress
    if 'progress' not in df.columns:
        df['progress'] = df['status'].map({'Complete': 100, 'In Progress': 50, 'Not Started': 0})
    df['progress'] = pd.to_numeric(df['progress'], errors='coerce').fillna(0).clip(0, 100)

    # Milestone — True/False
    if 'milestone' not in df.columns:
        df['milestone'] = False
    else:
        df['milestone'] = df['milestone'].apply(
            lambda x: str(x).strip().lower() in ('TRUE', '1', 'yes') if pd.notna(x) else False
        )

    return df.reset_index(drop=True)


def _infer_status(df):
    today = pd.Timestamp.today().normalize()
    out   = []
    for _, r in df.iterrows():
        if r['end_date'] < today:
            out.append('Complete')
        elif r['start_date'] <= today:
            out.append('In Progress')
        else:
            out.append('Not Started')
    return out


# ════════════════════════════════════════════════════════════════
#  SCHEDULING VALIDATION
# ════════════════════════════════════════════════════════════════

def validate_schedule(df):
    conflicts = []
    id_map = df.set_index('task_id')
    for _, task in df.iterrows():
        dep_id = task['dependencies']
        if dep_id is None or dep_id not in id_map.index:
            continue
        dep = id_map.loc[dep_id]
        if task['start_date'] < dep['end_date']:
            conflicts.append(
                f"  ⚠  Task {task['task_id']} '{task['task']}' starts {task['start_date'].date()} "
                f"before dependency Task {dep_id} '{dep['task']}' ends {dep['end_date'].date()}"
            )
    return conflicts


# ════════════════════════════════════════════════════════════════
#  CRITICAL PATH
# ════════════════════════════════════════════════════════════════

def find_critical_path(df):
    id_map = df.set_index('task_id')
    memo   = {}

    def longest(tid):
        if tid in memo:
            return memo[tid]
        row    = id_map.loc[tid]
        dur    = (row['end_date'] - row['start_date']).days
        dep_id = row['dependencies']
        if dep_id is None or dep_id not in id_map.index:
            memo[tid] = (dur, [tid])
        else:
            prev_dur, prev_path = longest(dep_id)
            memo[tid] = (prev_dur + dur, prev_path + [tid])
        return memo[tid]

    best = (0, [])
    for tid in df['task_id']:
        result = longest(tid)
        if result[0] > best[0]:
            best = result
    return set(best[1])


# ════════════════════════════════════════════════════════════════
#  LAYOUT
# ════════════════════════════════════════════════════════════════

def _aim_color_map(aims):
    return {aim: AIM_PALETTE[i % len(AIM_PALETTE)] for i, aim in enumerate(aims)}


def build_layout(df):
    aim_order = df.groupby('aim')['start_date'].min().sort_values().index.tolist()
    cmap      = _aim_color_map(aim_order)
    rows, task_y = [], {}
    y = 0

    for aim in aim_order:
        g_df  = df[df['aim'] == aim].sort_values('start_date')
        color = cmap[aim]
        rows.append(dict(y=y, kind='group', label=aim, aim=aim, color=color,
                         task_row=None,
                         g_start=g_df['start_date'].min(),
                         g_end=g_df['end_date'].max()))
        y += 1
        for _, task in g_df.iterrows():
            task_y[task['task_id']] = y
            rows.append(dict(y=y, kind='task', label=task['task'],
                             task_row=task, aim=aim, color=color))
            y += 1
        y += 0.5

    return rows, task_y, cmap


# ════════════════════════════════════════════════════════════════
#  HELPERS
# ════════════════════════════════════════════════════════════════

def _wrap(text, max_chars=28):
    words, lines, line, length = text.split(), [], [], 0
    for w in words:
        if length + len(w) + 1 > max_chars and line:
            lines.append(' '.join(line))
            line, length = [w], len(w)
        else:
            line.append(w)
            length += len(w) + 1
    if line:
        lines.append(' '.join(line))
    return '\n'.join(lines)


def _summary_header(df):
    today      = pd.Timestamp.today().normalize()
    total_days = (df['end_date'].max() - df['start_date'].min()).days
    n_aims     = df['aim'].nunique()
    n_tasks    = len(df)
    n_done     = (df['status'] == 'Complete').sum()
    n_prog     = (df['status'] == 'In Progress').sum()
    n_todo     = (df['status'] == 'Not Started').sum()
    return (
        f"{n_aims} Aims  ·  {n_tasks} Tasks  ·  {total_days} days total  |  "
        f"✓ {n_done} complete  ·  ▶ {n_prog} in progress  ·  ○ {n_todo} not started"
    )


# ════════════════════════════════════════════════════════════════
#  MAIN PLOT
# ════════════════════════════════════════════════════════════════

def plot_gantt(df, output_path=None):

    conflicts = validate_schedule(df)
    if conflicts:
        print("Scheduling conflicts detected:")
        for c in conflicts:
            print(c)

    critical_ids    = find_critical_path(df)
    rows, task_y, cmap = build_layout(df)
    

    today      = pd.Timestamp.today().normalize()
    start_date = df['start_date'].min()
    end_date   = df['end_date'].max()
    total_days = max((end_date - start_date).days, 1)
    x_pad      = pd.Timedelta(days=4)

    total_rows = max(r['y'] for r in rows) + 1
    fig_h      = max(8, total_rows * 0.58 + 3.0)

    fig = plt.figure(figsize=(19, fig_h), facecolor=BG_COLOR)


    fig.subplots_adjust(left=0.22, right=0.98,
                        top=0.93, bottom=0.14)

    ax = fig.add_subplot(111)
    ax.set_facecolor(PANEL_COLOR)

    # ── Title + summary ───────────────────────────────────────────
    fig.suptitle(TITLE, x=0.5, y=0.980, ha='center',
                 fontsize=TITLE_SIZE, fontweight='bold', color=TEXT_PRIMARY)
    fig.text(0.5, 0.955, _summary_header(df),
             ha='center', va='top',
             fontsize=8.5, color=TEXT_SECONDARY, style='italic')

    # ── Alternating bands ─────────────────────────────────────────
    group_y_ranges  = {}
    current_aim, current_aim_top, prev_y = None, None, 0
    for r in rows:
        if r['kind'] == 'group':
            if current_aim:
                group_y_ranges[current_aim] = (current_aim_top, prev_y)
            current_aim, current_aim_top = r['aim'], r['y'] - 0.5
        prev_y = r['y'] + 0.5
    if current_aim:
        group_y_ranges[current_aim] = (current_aim_top, prev_y)

    for i, (_, (y0, y1)) in enumerate(group_y_ranges.items()):
        if i % 2 == 0:
            ax.axhspan(y0, y1, color="#FFFFFF", alpha=0.04, zorder=0)

    # ── Draw bars ─────────────────────────────────────────────────
    hover_artists = []

    for r in rows:
        y = r['y']

        if r['kind'] == 'group':
            span = max((r['g_end'] - r['g_start']).days, 1)
            ax.barh(y, span, left=r['g_start'], height=GROUP_BAR_HEIGHT,
                    color=r['color'], alpha=0.25, zorder=2, linewidth=0)
            ax.text(-0.01, y, f"▸ {_wrap(r['label'], 34)}",
                    transform=ax.get_yaxis_transform(),
                    ha='right', va='center',
                    fontsize=GROUP_LABEL_SIZE, fontweight='bold',
                    color=r['color'], linespacing=1.3)
        else:
            task      = r['task_row']
            span      = max((task['end_date'] - task['start_date']).days, 1)
            status    = task['status']
            prog      = task['progress']
            bar_color = STATUS_COLORS.get(status, r['color'])
            is_crit   = task['task_id'] in critical_ids

            # Critical glow
            if is_crit:
                ax.barh(y, span, left=task['start_date'],
                        height=TASK_BAR_HEIGHT + 0.18,
                        color=CRITICAL_COLOR, alpha=CRITICAL_ALPHA,
                        zorder=2, linewidth=0)

            # Main bar
            bar = ax.barh(y, span, left=task['start_date'],
                          height=TASK_BAR_HEIGHT,
                          color=bar_color, alpha=TASK_BAR_ALPHA,
                          zorder=3, linewidth=0)

            # Progress sub-bar
            prog_span = span * prog / 100
            if prog_span > 0:
                ax.barh(y, prog_span, left=task['start_date'],
                        height=PROGRESS_HEIGHT,
                        color='white', alpha=0.30, zorder=4, linewidth=0)

            # Duration label
            if span >= 3:
                ax.text(task['end_date'] + pd.Timedelta(days=0.4), y,
                        f"{span}d", va='center', ha='left',
                        fontsize=6.5, color=TEXT_SECONDARY, zorder=5)

            # Text inside bar
            mid = task['start_date'] + (task['end_date'] - task['start_date']) / 2
            ax.text(mid, y, task['task'],
                    ha='center', va='center',
                    fontsize=TASK_LABEL_SIZE, color='white', fontweight='bold',
                    clip_on=True, zorder=6,
                    path_effects=[pe.withStroke(linewidth=1.8, foreground=bar_color)])

            # Milestone diamond
            if task.get('milestone', False):
                ax.scatter([task['end_date']], [y+.3],
                           marker='D', s=MILESTONE_SIZE,
                           color=MILESTONE_COLOR, zorder=8,
                           edgecolors='white', linewidths=0.8)

            # Y-axis label
            ax.text(-0.01, y, f"  {_wrap(task['task'], 30)}",
                    transform=ax.get_yaxis_transform(),
                    ha='right', va='center',
                    fontsize=TASK_LABEL_SIZE, color=TEXT_SECONDARY, linespacing=1.2)

            # Tooltip
            dep_str = f"Task {task['dependencies']}" if task['dependencies'] else "None"
            cp_str  = "  🔴 CRITICAL PATH" if is_crit else ""
            tooltip = (
                f"Task {task['task_id']}: {task['task']}{cp_str}\n"
                f"{'─'*42}\n"
                f"{task['description']}\n"
                f"{'─'*42}\n"
                f"Start:      {task['start_date'].strftime('%d %b %Y')}\n"
                f"End:        {task['end_date'].strftime('%d %b %Y')}\n"
                f"Duration:   {span} day{'s' if span != 1 else ''}\n"
                f"Status:     {status}  ({int(prog)}% done)\n"
                f"Depends on: {dep_str}"
            )
            for patch in bar.patches:
                patch._tooltip = tooltip
                hover_artists.append(patch)

    # ── Hover ─────────────────────────────────────────────────────
    cursor = mplcursors.cursor(hover_artists, hover=mplcursors.HoverMode.Transient)

    @cursor.connect("add")
    def on_hover(sel):
        sel.annotation.set_text(getattr(sel.artist, '_tooltip', ''))
        sel.annotation.get_bbox_patch().set(
            facecolor="#1A1D27", alpha=0.97,
            edgecolor="#555577", boxstyle="round,pad=0.5"
        )
        sel.annotation.set_fontsize(8.5)
        sel.annotation.set_fontfamily("monospace")
        sel.annotation.set_color(TEXT_PRIMARY)

    # ── Dependency arrows ─────────────────────────────────────────
    for _, task in df.iterrows():
        dep_id = task['dependencies']
        if dep_id is None or dep_id not in task_y:
            continue
        dep_row   = df[df['task_id'] == dep_id].iloc[0]
        both_crit = task['task_id'] in critical_ids and dep_id in critical_ids
        ax.annotate('',
                    xy=(task['start_date'], task_y[task['task_id']]),
                    xytext=(dep_row['end_date'], task_y[dep_id]),
                    arrowprops=dict(
                        arrowstyle='->',
                        color=CRITICAL_COLOR if both_crit else ARROW_COLOR,
                        lw=1.4 if both_crit else ARROW_LW,
                        connectionstyle='arc3,rad=0.20'),
                    zorder=7)

    # ── Today line ────────────────────────────────────────────────
    if start_date <= today <= end_date:
        ax.axvline(today, color=TODAY_COLOR, lw=TODAY_LW,
                   alpha=TODAY_ALPHA, zorder=9, linestyle='--')
        ax.text(today, -0.65, f"Today\n{today.strftime('%d %b')}",
                color=TODAY_COLOR, fontsize=7, va='top', ha='center',
                fontweight='bold', zorder=10)

    # ── X axis: day ticks + month secondary ───────────────────────
    mondays = pd.date_range(start=start_date, end=end_date, freq='W-MON')
    ax.set_xticks(mondays)
    ax.set_xticklabels([d.strftime('%-d') for d in mondays],
                       fontsize=TICK_SIZE, color=TEXT_SECONDARY)

    sec = ax.secondary_xaxis('bottom')
    sec.xaxis.set_major_locator(mdates.MonthLocator())
    sec.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
    sec.tick_params(labelsize=MONTH_SIZE, colors=TEXT_PRIMARY, length=0)
    sec.spines['bottom'].set_position(('outward', 22))
    sec.spines['bottom'].set_visible(False)
    for lbl in sec.get_xticklabels():
        lbl.set_fontweight('bold')

    # ── Y / grid / spines ─────────────────────────────────────────
    full_xlim = (start_date - x_pad, end_date + x_pad)
    ax.set_xlim(*full_xlim)
    ax.set_ylim(total_rows + 0.5, -1)
    ax.set_yticks([])
    ax.xaxis.grid(True, color=GRID_COLOR, linestyle='--', linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(axis='x', length=0)

    # ── Legends ───────────────────────────────────────────────────
    aim_handles = [mpatches.Patch(color=cmap[a], label=_wrap(a, 38), alpha=0.88)
                   for a in cmap]
    status_handles = [mpatches.Patch(color=c, label=s, alpha=0.88)
                      for s, c in STATUS_COLORS.items()]
    extra_handles = [
        mpatches.Patch(color=CRITICAL_COLOR, label='Critical Path', alpha=CRITICAL_ALPHA),
        Line2D([0], [0], marker='D', color='w', markerfacecolor=MILESTONE_COLOR,
               markeredgecolor='white', markersize=4, label='Milestone'),
        Line2D([0], [0], color=TODAY_COLOR, lw=1.4, linestyle='--', label='Today'),
    ]
    leg1 = ax.legend(handles=aim_handles,
                     title='Aims', title_fontsize=7.5, loc='upper right',
                     fontsize=LEGEND_SIZE - 0.5, framealpha=0.15,
                     edgecolor=GRID_COLOR, borderpad=0.9,
                     labelcolor=TEXT_PRIMARY, facecolor=PANEL_COLOR)
    leg1.get_title().set_color(TEXT_PRIMARY)

    ax.add_artist(leg1)
    leg2 = ax.legend(handles=status_handles + extra_handles,
              title='Legend', title_fontsize=7.5, loc='upper left',
              fontsize=LEGEND_SIZE - 0.5, framealpha=0.15,
              edgecolor=GRID_COLOR, borderpad=0.9,
              labelcolor=TEXT_PRIMARY, facecolor=PANEL_COLOR)
    leg2.get_title().set_color(TEXT_PRIMARY)
    ax.add_artist(leg2)


    # Export button
    exp_ax = fig.add_axes([0.918, 0.052, 0.055, 0.026],
                           facecolor=GRID_COLOR)
    exp_btn = Button(exp_ax, '💾 Export', color=GRID_COLOR, hovercolor='#3A3D4A')
    exp_btn.label.set_color(TEXT_SECONDARY)
    exp_btn.label.set_fontsize(7.5)

    def export(event):
        out = 'gantt_export.png'
        fig.savefig(out, dpi=200, bbox_inches='tight', facecolor=BG_COLOR)
        print(f"Exported → {out}")
    exp_btn.on_clicked(export)

    if output_path:
        fig.savefig(output_path, dpi=200, bbox_inches='tight', facecolor=BG_COLOR)
        plt.close()
        print(f"Saved → {output_path}")
    else:
        plt.show()
