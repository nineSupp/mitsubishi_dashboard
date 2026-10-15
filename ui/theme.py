"""Theme loading: injects the original CSS (assets/css/theme.css, copied unchanged from main_dashboard.py),
the extra drill-down styles, the fixed header/footer and the sidebar auto-close script."""
import base64
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components

import config


def _read(path):
    return Path(path).read_text(encoding='utf-8')


def image_data_uri(path):
    try:
        return 'data:image/png;base64,' + base64.b64encode(Path(path).read_bytes()).decode()
    except Exception:
        return ""


def page_icon():
    return str(config.ICON_FILE) if Path(config.ICON_FILE).exists() else "📊"


def inject_theme():
    css = _read(config.ASSETS_DIR / 'css' / 'theme.css') + "\n" + _read(config.ASSETS_DIR / 'css' / 'extra.css')
    logo = image_data_uri(config.LOGO_FILE)
    logo_html = (f"<img class='nav-logo' src='{logo}' alt='Logo'>" if logo
                 else "<span style='color:#FFF; font-weight:700;'>MITSUBISHI</span>")
    members = "".join(
        f"<div class='footer-member'><span class='footer-member-name'>{n}</span>"
        f"<span class='footer-member-id'>{sid}</span></div>" for n, sid in config.TEAM_MEMBERS)
    header_footer = f"""
    <div class="top-navbar">
    <div class="nav-left">
    {logo_html}
    <div class="nav-title">Mitsubishi Electric<span> x </span>TNIC Dashboard</div>
    <div class="nav-tag">Made by Team 6</div>
    </div>
    <div class="nav-right">
    <div class="status-indicator"><span class="status-dot"></span>Live Telemetry</div>
    </div>
    </div>
    <div class="bottom-footer">
    <div class="footer-left">
    <div class="footer-title">SOE105: Elements of Success Startup Project (Team 6)</div>
    <div class="footer-version">Dashboard Version 1.0 | 2026</div>
    </div>
    <div class="footer-right">
    <div class="footer-label">Members</div>
    {members}
    </div>
    </div>
    """
    # strip indentation and blank lines: 4+ leading spaces would turn the HTML into a Markdown code block
    header_footer = "\n".join(line.strip() for line in header_footer.splitlines() if line.strip())
    st.markdown(f"<style>{css}</style>\n{header_footer}", unsafe_allow_html=True)
    components.html(f"<script>{_read(config.ASSETS_DIR / 'js' / 'sidebar_autoclose.js')}</script>", height=0, width=0)


def sidebar_banner():
    logo = image_data_uri(config.LOGO_FILE)
    inner = (f"<img class='sidebar-header-logo' src='{logo}' alt='Mitsubishi Logo'>" if logo
             else "<span style='color:#FFF; font-weight:700; letter-spacing:1px;'>MITSUBISHI</span>")
    st.markdown(f'<div class="sidebar-header-banner">{inner}</div>', unsafe_allow_html=True)
    st.markdown('<div class="sidebar-title-container"><h3>Main Panel</h3></div>', unsafe_allow_html=True)
    st.markdown("<hr class='tight-divider'>", unsafe_allow_html=True)
