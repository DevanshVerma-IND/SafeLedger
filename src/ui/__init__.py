"""SafeLedger UI package."""
from ui.styles import apply_custom_theme, render_header, render_metric
import ui.page1_overview as page1_overview
import ui.page2_simulator as page2_simulator
import ui.page3_deadlock as page3_deadlock
import ui.page4_banker as page4_banker
import ui.page5_ml_risk as page5_ml_risk
import ui.page6_benchmark as page6_benchmark
import ui.page7_os_concepts as page7_os_concepts
import ui.page8_dbms as page8_dbms
import ui.page9_banking as page9_banking
import ui.page10_status as page10_status

__all__ = [
    "apply_custom_theme",
    "render_header",
    "render_metric",
    "page1_overview",
    "page2_simulator",
    "page3_deadlock",
    "page4_banker",
    "page5_ml_risk",
    "page6_benchmark",
    "page7_os_concepts",
    "page8_dbms",
    "page9_banking",
    "page10_status",
]
