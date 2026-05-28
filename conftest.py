"""Root pytest configuration.

Makes the application packages importable for the unit-test suites without
requiring Docker, a running database, or the production model files:

  * ``api/app``            -> import the FastAPI app as ``app.main``
  * ``training/scripts``   -> import ``train_all_models`` feature engineering

Tests mock/monkeypatch model loading and the database, so they run anywhere.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()

# Ensure the training models dir defaults to a writable temp path during tests,
# so importing the training module never touches a read-only /app path.
os.environ.setdefault("MODELS_DIR", str(ROOT / ".pytest_models"))

# Make the API app package importable as `app.main`.
_API_DIR = ROOT / "api"
if str(_API_DIR) not in sys.path:
    sys.path.insert(0, str(_API_DIR))

# Make the training scripts importable as `train_all_models` / `db_utils`.
_TRAINING_SCRIPTS = ROOT / "training" / "scripts"
if str(_TRAINING_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_TRAINING_SCRIPTS))
