import os
import sys

_current_dir = os.path.dirname(os.path.abspath(__file__))
_parent_dir = os.path.dirname(_current_dir)
sys.path.extend([_current_dir, _parent_dir])

from argoproxy.constants import CHAT_MODELS
from argoproxy.utils import resolve_model_name

MODEL = os.getenv("MODEL", "argo:gpt-4o")
DEFAULT_MODEL = "argo:gpt-4o"

resolved_name = resolve_model_name(MODEL, DEFAULT_MODEL, avail_models=CHAT_MODELS)
print(resolved_name)
