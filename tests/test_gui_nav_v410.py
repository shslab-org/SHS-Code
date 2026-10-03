"""v4.1.0 GUI regression tests — navigation slide/hide + Help guide panel.

Pins the user-requested features:
1. Sidebar can be hidden/shown (☰ top-bar button, edge tab, Ctrl/Cmd+B shortcut).
2. Preference persists via localStorage; small screens get an overlay drawer.
3. A beginner-friendly Help / Guide panel exists in the GUI itself.
4. QA panel status badge bug fixed (Python ``True`` leaked into JS context —
   the badge always rendered "unknown").
"""
from __future__ import annotations

from pathlib import Path

import pytest

_GUI = Path(__file__).resolve().parents[1] / "app" / "server" / "static" / "gui.html"


@pytest.fixture(scope="module")
def gui_html() -> str:
    return _GUI.read_text(encoding="utf-8")


class TestNavSlideHide:
    def test_toggle_button_in_topbar(self, gui_html):
        assert 'id="nav-toggle"' in gui_html
        assert 'onclick="toggleNav()"' in gui_html
        assert 'aria-label="Toggle navigation"' in gui_html

    def test_edge_handle_when_hidden(self, gui_html):
        assert 'id="nav-show-handle"' in gui_html
        assert 'body.nav-hidden #nav-show-handle { display: block; }' in gui_html

    def test_slide_transition_css(self, gui_html):
        # smooth slide animation on the sidebar
        assert "transition: margin-left" in gui_html

    def test_keyboard_shortcut_bound(self, gui_html):
        assert "e.ctrlKey || e.metaKey" in gui_html
        assert "'b' || e.key === 'B'" in gui_html

    def test_persistence_via_localstorage(self, gui_html):
        assert "localStorage.setItem(NAV_KEY" in gui_html
        assert "localStorage.getItem(NAV_KEY" in gui_html
        assert "'shs-gui-nav-hidden'" in gui_html

    def test_mobile_overlay_drawer(self, gui_html):
        assert "@media (max-width: 820px)" in gui_html
        assert "position: fixed" in gui_html
        assert "transform: translateX(-100%)" in gui_html
        assert 'id="nav-backdrop"' in gui_html

    def test_backdrop_and_esc_close_drawer(self, gui_html):
        assert "Escape" in gui_html
        assert 'id="nav-backdrop" onclick="toggleNav()"' in gui_html

    def test_toggle_function_defined(self, gui_html):
        assert "function toggleNav(force)" in gui_html
        assert "function navApply(hidden)" in gui_html

    def test_drawer_closes_after_panel_pick_on_mobile(self, gui_html):
        assert "if (mqMobile.matches) navApply(true);" in gui_html


class TestHelpGuidePanel:
    def test_nav_item_registered(self, gui_html):
        assert 'data-panel="help"' in gui_html

    def test_panel_exists(self, gui_html):
        assert 'id="panel-help"' in gui_html

    def test_panels_map_includes_help(self, gui_html):
        assert "help:'Help / Guide'" in gui_html

    def test_beginner_quickstart_present(self, gui_html):
        assert "your first task in 3 steps" in gui_html

    def test_panel_reference_table_present(self, gui_html):
        assert "What each panel does" in gui_html

    def test_task_status_legend_present(self, gui_html):
        assert "What the task statuses mean" in gui_html

    def test_troubleshooting_section_present(self, gui_html):
        assert "Troubleshooting" in gui_html

    def test_no_python_booleans_in_js(self, gui_html):
        # regression: `rep.ok === True` (Python literal) broke the QA badge
        assert "=== True" not in gui_html
        assert "=== False" not in gui_html


class TestGuiRouteServesNav:
    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        monkeypatch.setenv("APP_ENV", "test")
        monkeypatch.setenv("HOME", str(tmp_path))
        from app.db.session import SessionDB
        from app.server import main as srv

        srv.db.close()
        srv.db = SessionDB(db_path=tmp_path / "sessions.db")
        from fastapi.testclient import TestClient

        with TestClient(srv.app) as tc:
            yield tc
        srv.db.close()

    def test_gui_route_contains_nav_toggle(self, client):
        r = client.get("/gui")
        assert r.status_code == 200
        assert 'id="nav-toggle"' in r.text
        assert 'id="nav-show-handle"' in r.text

    def test_gui_route_contains_help_panel(self, client):
        r = client.get("/gui")
        assert r.status_code == 200
        assert 'id="panel-help"' in r.text
        assert 'data-panel="help"' in r.text
