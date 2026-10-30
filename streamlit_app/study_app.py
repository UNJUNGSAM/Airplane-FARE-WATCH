"""학습자료 전용 웹앱 (진입점).

항공권 감시 콘솔(app.py)과 같은 저장소·같은 자료 폴더를 쓰지만, 따로 배포하는 별개의 앱이다.
Streamlit Cloud 에서 새 앱을 만들 때 Main file path 를 streamlit_app/study_app.py 로 지정한다.

st.navigation 을 쓰므로 pages/ 폴더가 자동으로 메뉴가 되지 않는다.
여기서 고른 학습자료 페이지만 보이고, 감시 콘솔 페이지(pages/1~6)는 이 앱에 나타나지 않는다.

주소
    /                        학습자료 목록 (pages/90_learning.py)
    /learning_<과목_주제>      자료 한 개 (pages/9N_learning_<과목_주제>.py)

새 자료는 study_page.py 의 안내대로 추가하면 이 앱에도 자동으로 나타난다.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import streamlit as st  # noqa: E402

import study_page  # noqa: E402

# 페이지 파일들과 같은 이유로 자료 목록이 바뀌면 바로 반영되도록 매번 다시 읽는다.
importlib.reload(study_page)

# 이 앱에서는 목록이 첫 화면(/)이므로 자료 화면의 '학습자료' 링크가 첫 화면으로 가게 한다.
st.session_state[study_page.HOME_KEY] = "./"

pages = [st.Page("pages/90_learning.py", title="학습자료", default=True)]
for item in study_page.CATALOG:
    files = sorted((HERE / "pages").glob(f"*_learning_{item['slug']}.py"))
    if files:
        pages.append(
            st.Page(
                f"pages/{files[0].name}",
                title=item["title"],
                url_path=f"learning_{item['slug']}",
            )
        )

st.navigation(pages, position="hidden").run()
