"""Headless smoke tests of the Streamlit app in offline mode (no Earth Engine, no Groq, no browser)."""

import os
from pathlib import Path

import pytest

os.environ["GEE_PROJECT"] = ""        # load_dotenv() never overrides an existing variable -> offline
os.environ.pop("GROQ_API_KEY", None)

from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def _button(at, text):
    return next(b for b in at.button if text in b.label)


def _markdown(at) -> str:
    return " ".join(m.value for m in at.markdown)


@pytest.fixture(scope="module")
def app():
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    return at


def test_app_starts_offline_without_errors(app):
    assert not app.exception, app.exception
    text = _markdown(app)
    assert "Demo mode" in text
    assert "The answer" in text
    assert "How sure are we?" in text              # answer card with confidence meter
    assert "Pick a place" in text and "What do you want to look at?" in text   # numbered steps


def test_change_layers_are_built_offline(app):
    app.session_state["_inject_map_event"] = {"type": "show_change", "nonce": 100}   # the globe's Watch button
    app.run()
    assert not app.exception, app.exception
    req = app.session_state["change_req"]
    assert req is not None and req["var"] == "ndvi_modis"
    assert any("On the map:" in c.value and "years of maps" in c.value for c in app.caption)


def test_globe_events_update_the_investigation(app):
    app.session_state["_inject_map_event"] = {"type": "pick", "lat": 13.1, "lon": 14.5, "name": "Lake Chad", "nonce": 1}
    app.run()
    assert not app.exception, app.exception
    reg = app.session_state["region"]
    assert (reg["lat"], reg["lon"], reg["name"], reg["preset"]) == (13.1, 14.5, "Lake Chad", None)

    app.session_state["_inject_map_event"] = {"type": "pick", "lat": 13.2, "lon": 14.6, "inspect": True, "nonce": 2}
    app.run()
    assert app.session_state["region"]["radius_km"] <= 1.0     # pixel inspection shrinks to ~one MODIS pixel

    app.session_state["_inject_map_event"] = {"type": "preset", "key": "kakhovka_bed", "variable": "ndvi_modis",
                                              "start_year": 2014, "nonce": 3}
    app.run()
    assert not app.exception, app.exception
    assert app.session_state["region"]["preset"] == "kakhovka_bed"
    assert app.session_state["years"][0] == 2014

    app.session_state["_inject_map_event"] = {"type": "polygon", "coords": [[34.1, 47.4], [34.3, 47.4], [34.2, 47.5]], "nonce": 4}
    app.run()
    assert not app.exception, app.exception
    assert app.session_state["region"]["polygon"] and app.session_state["region"]["area_km2"] > 50

    app.session_state["_inject_map_event"] = {"type": "compare_add", "lat": 45.0, "lon": 60.0, "name": "Aral", "nonce": 5}
    app.run()
    assert not app.exception, app.exception
    assert app.session_state["cmp_list"][-1]["name"] == "Aral" and app.session_state["view"] == "compare"

    app.session_state["_inject_map_event"] = {"type": "night_year", "year": 2012, "nonce": 6}   # year menu, offline
    app.run()
    assert not app.exception, app.exception
    assert app.session_state["night_year"] == 2012


def test_compare_case_file_runs(app):
    app.button(key="story_landcover_temperature").click().run()
    assert not app.exception, app.exception
    cr = app.session_state["cmp_results"]
    assert cr is not None and cr["var"] == "lst_day" and len(cr["items"]) == 2


def test_scan_and_open_variable(app):
    app.segmented_control(key="view").set_value("scan").run()
    _button(app, "Check everything").click().run()
    assert not app.exception, app.exception
    assert "things are clearly changing" in _markdown(app)
    app.button(key="open_water_storage").click().run()
    assert not app.exception, app.exception
    assert app.session_state["var_key"] == "water_storage" and app.session_state["view"] == "trend"
    y0, y1 = app.slider(key="years").value
    assert y0 >= 2002 and y1 <= 2024                             # clamped to the GRACE record


def test_variable_pills_alpha_and_method_view(app):
    app.segmented_control(key="topic").set_value("Snow & ice").run()   # the topic picks its first measurement
    assert not app.exception, app.exception
    assert app.session_state["var_key"] == "snow_cover"
    app.segmented_control(key="alpha").set_value(0.01).run()
    assert not app.exception, app.exception
    app.segmented_control(key="view").set_value("method").run()
    assert not app.exception, app.exception
    assert "How Trend Detective works" in _markdown(app)


def test_example_pin_and_watch_button_events():
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    at.session_state["_inject_map_event"] = {"type": "preset", "key": "kakhovka_bed", "variable": "ndvi_modis",
                                             "start_year": 2014, "nonce": 8}   # example pin on the globe
    at.run()
    assert not at.exception, at.exception
    assert at.session_state["region"]["preset"] == "kakhovka_bed"
    assert at.session_state["change_req"]["var"] == "ndvi_modis"   # time-lapse requested automatically
    at.session_state["_inject_map_event"] = {"type": "pick", "lat": 50.45, "lon": 30.52, "name": "Kyiv", "nonce": 9}
    at.run()
    at.session_state["_inject_map_event"] = {"type": "show_change", "nonce": 10}
    at.run()
    assert not at.exception, at.exception
    assert at.session_state["change_req"]["lat"] == 50.45
    on_map = lambda: any("On the map:" in c.value for c in at.caption)
    assert on_map()
    at.session_state["_inject_map_event"] = {"type": "pick", "lat": 50.46, "lon": 30.53, "inspect": True, "nonce": 11}
    at.run()                                                      # inspecting a spot keeps the maps
    assert not at.exception, at.exception
    assert on_map()
    at.session_state["_inject_map_event"] = {"type": "pick", "lat": 49.84, "lon": 24.03, "name": "Lviv", "nonce": 12}
    at.run()                                                      # a new place: old maps hidden, nothing built by itself
    assert not at.exception, at.exception
    assert not on_map() and at.session_state["change_req"]["lat"] == 50.45
    assert any("Watch it change" in c.value for c in at.caption)
    at.session_state["_inject_map_event"] = {"type": "show_change", "nonce": 13}
    at.run()                                                      # ...until Watch it change is pressed
    assert on_map() and at.session_state["change_req"]["lat"] == 49.84
    at.session_state["_inject_map_event"] = {"type": "radius", "km": 5.0, "nonce": 14}
    at.run()                                                      # a new size hides them too
    assert not on_map() and at.session_state["change_req"]["radius"] != 5.0


def test_example_tiles_open_places_and_comparisons():
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    at.session_state["_inject_example"] = 0                     # Kakhovka Reservoir · plant greenness
    at.run()
    assert not at.exception, at.exception
    assert at.session_state["region"]["preset"] == "kakhovka_bed"
    assert at.session_state["change_req"]["var"] == "ndvi_modis"   # map layers requested right away
    assert at.session_state["example_active"] == 0
    at.session_state["_inject_example"] = 8                     # first comparison
    at.run()
    assert not at.exception, at.exception
    assert at.session_state["view"] == "compare" and len(at.session_state["cmp_list"]) == 2


def test_topic_then_measurement_picker():
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    at.segmented_control(key="topic").set_value("Water").run()
    assert not at.exception, at.exception
    assert at.session_state["var_key"] == "precipitation"       # first measurement of the topic
    labels = " | ".join(at.pills(key="var_key").options)
    assert "Rain & snowfall" in labels and "All water stored" in labels and "Plant greenness" not in labels
