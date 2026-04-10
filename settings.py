DATE_FORMAT = '%Y-%m-%d'
TITLE = "PhD Project Gantt Chart"

# --- Dark Palette ---
BG_COLOR        = "#0F1117"
PANEL_COLOR     = "#1A1D27"
GRID_COLOR      = "#2A2D3A"
TEXT_PRIMARY    = "#E8E8F0"
TEXT_SECONDARY  = "#8888AA"
ACCENT_COLOR    = "#E8E8F0"

AIM_PALETTE = [
    "#2EC4B6", "#4E9AF1", "#F4A261",
    "#E76F51", "#8338EC", "#3A86FF",
    "#FB5607", "#FF006E",
]

# Status colours (overrides aim colour when status is set)
STATUS_COLORS = {
    "Not Started": "#555577",
    "In Progress":  "#F4A261",
    "Complete":     "#2EC4B6",
}
STATUS_BORDER = {
    "Not Started": "#7777AA",
    "In Progress":  "#F4A261",
    "Complete":     "#2EC4B6",
}

# Bar geometry
TASK_BAR_ALPHA    = 0.90
TASK_BAR_HEIGHT   = 0.52
GROUP_BAR_HEIGHT  = 0.28
PROGRESS_HEIGHT   = 0.16   # height of progress sub-bar

# Today line
TODAY_COLOR       = "#FF4466"
TODAY_LW          = 1.6
TODAY_ALPHA       = 0.85

# Milestone
MILESTONE_COLOR   = "#FFD700"
MILESTONE_SIZE    = 25

# Critical path
CRITICAL_COLOR    = "#FF4466"
CRITICAL_ALPHA    = 0.55

# Typography
FONT_FAMILY       = "DejaVu Sans"
TITLE_SIZE        = 15
GROUP_LABEL_SIZE  = 8.5
TASK_LABEL_SIZE   = 7.5
TICK_SIZE         = 7
MONTH_SIZE        = 8.5
LEGEND_SIZE       = 4

# Arrows
ARROW_COLOR       = "#555577"
ARROW_LW          = 0.9
