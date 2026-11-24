"""
SafeLedger UI Theme & Component Styling
A crisp, pure white banking SaaS interface with black/charcoal typography and subtle blue accents.
Inspired by Stripe Dashboard and Mercury Banking.

Color Palette:
- Main Background: #FFFFFF
- Secondary / Sidebar Background: #F8F9FB
- Borders: #E5E7EB
- Primary Typography: #111827 (Black/Deep Charcoal)
- Secondary Typography: #4B5563 (Slate Gray)
- Subtle Blue Accent: #2563EB (Subtle Royal/Indigo Blue)
- Light Blue Tint: #EFF6FF
- Success Green: #16845B
- Warning Amber: #B7791F
- Error Red: #C24141
"""
import streamlit as st

def apply_custom_theme():
    """Injects comprehensive white-first stylesheet that overrides all dark/default elements."""
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    /* 1. Global Reset to Pure White & Clean Black Typography */
    html, body, [class*="css"], [data-testid="stAppViewContainer"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
        background-color: #FFFFFF !important;
        color: #111827 !important;
    }
    
    /* Main Content Container */
    .main, [data-testid="stAppViewBlockContainer"], .block-container {
        background-color: #FFFFFF !important;
        color: #111827 !important;
        padding-top: 1.75rem !important;
        padding-bottom: 3rem !important;
        max-width: 1200px !important;
    }

    /* 2. Sidebar: Soft Clean Off-White with Clean Border */
    [data-testid="stSidebar"], [data-testid="stSidebarContent"] {
        background-color: #F8F9FB !important;
        border-right: 1px solid #E5E7EB !important;
        color: #111827 !important;
    }
    
    /* Ensure all text inside sidebar is black/dark gray */
    [data-testid="stSidebar"] p, 
    [data-testid="stSidebar"] span, 
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] div {
        color: #111827 !important;
    }

    /* Brand Header in Sidebar */
    .brand-container {
        padding: 0.25rem 0.25rem 1rem 0.25rem;
        border-bottom: 1px solid #E5E7EB;
        margin-bottom: 1rem;
    }
    .brand-title {
        font-size: 1.15rem;
        font-weight: 700;
        letter-spacing: -0.025em;
        color: #111827 !important;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }
    .brand-badge {
        display: inline-block;
        font-size: 0.72rem;
        font-weight: 600;
        line-height: 1.3;
        padding: 0.25rem 0.6rem;
        background-color: #EFF6FF !important;
        color: #2563EB !important;
        border: 1px solid #DBEAFE !important;
        border-radius: 4px;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        user-select: none;
        cursor: default;
    }

    /* User Profile Card in Sidebar */
    .user-session-card {
        background-color: #FFFFFF !important;
        border: 1px solid #E5E7EB !important;
        border-radius: 6px;
        padding: 0.75rem 0.85rem;
        margin-bottom: 1rem;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
    }
    .user-session-name {
        font-size: 0.875rem;
        font-weight: 600;
        color: #111827 !important;
    }
    .user-session-role {
        font-size: 0.75rem;
        color: #6B7280 !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-top: 0.1rem;
    }

    /* 3. Metric KPI Cards (White Card with Thin Border) */
    .metric-card {
        background-color: #FFFFFF !important;
        border: 1px solid #E5E7EB !important;
        border-radius: 6px;
        padding: 1rem 1.15rem;
        margin-bottom: 0.75rem;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03);
        transition: border-color 0.15s ease;
    }
    .metric-card:hover {
        border-color: #CBD5E1 !important;
    }
    .metric-title {
        color: #6B7280 !important;
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        font-weight: 600;
        margin-bottom: 0.35rem;
    }
    .metric-value {
        color: #111827 !important;
        font-size: 1.5rem;
        font-weight: 700;
        letter-spacing: -0.025em;
        line-height: 1.2;
    }
    .metric-sub {
        color: #9CA3AF !important;
        font-size: 0.75rem;
        margin-top: 0.25rem;
    }

    /* 4. Streamlit Native Metric Overrides */
    [data-testid="stMetric"] {
        background-color: #FFFFFF !important;
        border: 1px solid #E5E7EB !important;
        border-radius: 6px !important;
        padding: 0.85rem 1rem !important;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02) !important;
    }
    [data-testid="stMetricLabel"] p {
        color: #6B7280 !important;
        font-weight: 600 !important;
        font-size: 0.8rem !important;
        text-transform: uppercase !important;
    }
    [data-testid="stMetricValue"] {
        color: #111827 !important;
        font-weight: 700 !important;
    }

    /* 5. Status Pills */
    .status-pill {
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        padding: 0.18rem 0.55rem;
        border-radius: 9999px;
        font-size: 0.72rem;
        font-weight: 500;
    }
    .status-pill-success {
        background-color: #F0FDF4 !important;
        color: #166534 !important;
        border: 1px solid #BBF7D0 !important;
    }
    .status-pill-warning {
        background-color: #FFFBEB !important;
        color: #92400E !important;
        border: 1px solid #FDE68A !important;
    }
    .status-pill-danger {
        background-color: #FEF2F2 !important;
        color: #991B1B !important;
        border: 1px solid #FECACA !important;
    }
    .status-pill-blue {
        background-color: #EFF6FF !important;
        color: #1E40AF !important;
        border: 1px solid #BFDBFE !important;
    }

    /* 6. Section Headers */
    .section-header-box {
        margin-bottom: 1.5rem;
        padding-bottom: 0.75rem;
        border-bottom: 1px solid #E5E7EB;
    }
    .section-title {
        font-size: 1.35rem;
        font-weight: 700;
        color: #111827 !important;
        letter-spacing: -0.025em;
        margin-top: 0.25rem;
        margin-bottom: 0.25rem;
    }
    .section-desc {
        font-size: 0.875rem;
        color: #6B7280 !important;
        line-height: 1.45;
    }

    /* 7. Tables & DataFrames: Clean White with Subtle Gray Lines */
    [data-testid="stDataFrame"], [data-testid="stTable"] {
        background-color: #FFFFFF !important;
        border: 1px solid #E5E7EB !important;
        border-radius: 6px !important;
    }

    /* 8. Input Fields (Text, Number, Select) */
    .stTextInput>div>div>input, 
    .stNumberInput>div>div>input,
    .stSelectbox>div>div>div,
    .stTextArea>div>div>textarea {
        background-color: #FFFFFF !important;
        color: #111827 !important;
        border: 1px solid #D1D5DB !important;
        border-radius: 5px !important;
        font-size: 0.875rem !important;
    }
    .stTextInput>div>div>input:focus, 
    .stNumberInput>div>div>input:focus,
    .stSelectbox>div>div>div:focus {
        border-color: #2563EB !important;
        box-shadow: 0 0 0 1px #2563EB !important;
    }

    /* 9. Buttons: Professional Subtle Blue */
    .stButton>button {
        background-color: #2563EB !important;
        color: #FFFFFF !important;
        border: 1px solid #1D4ED8 !important;
        border-radius: 5px !important;
        font-weight: 500 !important;
        font-size: 0.875rem !important;
        padding: 0.45rem 1rem !important;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05) !important;
        transition: all 0.15s ease !important;
    }
    .stButton>button:hover {
        background-color: #1D4ED8 !important;
        border-color: #1E40AF !important;
        color: #FFFFFF !important;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.08) !important;
    }
    .stButton>button:active {
        background-color: #1E40AF !important;
    }

    /* 10. Secondary Buttons / Form Submit Buttons */
    button[kind="secondary"] {
        background-color: #FFFFFF !important;
        color: #111827 !important;
        border: 1px solid #D1D5DB !important;
    }
    button[kind="secondary"]:hover {
        background-color: #F8F9FB !important;
        border-color: #9CA3AF !important;
        color: #111827 !important;
    }

    /* 11. Tabs Styling: Minimal Underline */
    .stTabs [data-baseweb="tab-list"] {
        gap: 1.5rem;
        background-color: transparent !important;
        border-bottom: 1px solid #E5E7EB !important;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: transparent !important;
        color: #6B7280 !important;
        font-weight: 500 !important;
        font-size: 0.875rem !important;
        padding: 0.5rem 0.25rem !important;
        border: none !important;
    }
    .stTabs [aria-selected="true"] {
        color: #2563EB !important;
        border-bottom: 2px solid #2563EB !important;
        font-weight: 600 !important;
    }

    /* 12. Expanders */
    [data-testid="stExpander"] {
        background-color: #FFFFFF !important;
        border: 1px solid #E5E7EB !important;
        border-radius: 6px !important;
    }
    [data-testid="stExpander"] summary {
        color: #111827 !important;
        font-weight: 500 !important;
    }

    /* 13. Code blocks */
    code, pre {
        background-color: #F8F9FB !important;
        border: 1px solid #E5E7EB !important;
        color: #111827 !important;
        border-radius: 4px !important;
    }

    /* 14. Radio Items in Sidebar */
    [data-testid="stSidebar"] [data-testid="stRadio"] > div {
        gap: 0.35rem !important;
    }
    [data-testid="stSidebar"] [data-testid="stRadio"] label {
        background-color: transparent !important;
        border-radius: 5px !important;
        padding: 0.35rem 0.5rem !important;
        color: #111827 !important;
        font-size: 0.875rem !important;
    }
    [data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
        background-color: #EFF6FF !important;
        color: #2563EB !important;
    }
    </style>
    """, unsafe_allow_html=True)

def render_metric(title, value, sub="", status=None):
    """Renders a minimal Stripe-style KPI card in white."""
    pill_html = ""
    if status == "success":
        pill_html = '<span class="status-pill status-pill-success">Normal</span>'
    elif status == "warning":
        pill_html = '<span class="status-pill status-pill-warning">Warning</span>'
    elif status == "danger":
        pill_html = '<span class="status-pill status-pill-danger">Critical</span>'
    elif status == "blue":
        pill_html = '<span class="status-pill status-pill-blue">Active</span>'
        
    st.markdown(f"""
    <div class="metric-card">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <div class="metric-title">{title}</div>
            {pill_html}
        </div>
        <div class="metric-value">{value}</div>
        {f'<div class="metric-sub">{sub}</div>' if sub else ''}
    </div>
    """, unsafe_allow_html=True)

def render_header(title, desc, badge="Banking Platform"):
    """Standardized page header with clean divider."""
    st.markdown(f"""
    <div class="section-header-box">
        <span class="brand-badge">{badge}</span>
        <h2 class="section-title">{title}</h2>
        <div class="section-desc">{desc}</div>
    </div>
    """, unsafe_allow_html=True)
