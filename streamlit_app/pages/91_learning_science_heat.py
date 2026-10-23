"""학습자료 페이지 - 주소 /learning_science_heat (내용은 static/learning/science_heat/)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import study_page  # noqa: E402

study_page.show("science_heat")
