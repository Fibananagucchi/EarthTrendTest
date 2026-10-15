"""One-time Google Earth Engine login for local development:  python auth.py"""

import os

import ee
from dotenv import load_dotenv

load_dotenv()
project = os.environ.get("GEE_PROJECT")
if not project:
    raise SystemExit("Set GEE_PROJECT in .env first (a Google Cloud project with Earth Engine enabled).")

print("Opening the Earth Engine login…")
ee.Authenticate()
ee.Initialize(project=project)
print(f"Earth Engine is ready (project {project}). Start the app with:  streamlit run app.py")
