"""학습자료 페이지 - 주소 /learning_science_heat (내용은 static/learning/science_heat/)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import importlib  # noqa: E402

import study_page  # noqa: E402

# Streamlit Cloud는 페이지 스크립트만 다시 읽고 임포트된 모듈은 예전 것을 남겨 두므로
# (shared.py 와 같은 문제) 자료 목록이 바뀌어도 반영되도록 매번 다시 읽는다.
importlib.reload(study_page)

study_page.show("science_heat")
