from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / ".test-torch"), str(ROOT / ".test-deps"), str(ROOT / ".test-runtime" / "comfy-source")]
from comfy_execution.graph_utils import ExecutionBlocker
package = types.ModuleType("luis_lists_test")
package.__path__ = [str(ROOT)]
sys.modules.setdefault("luis_lists_test", package)
