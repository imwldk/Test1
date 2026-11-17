import json
import os
import re
import tempfile
import threading
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="쇼핑 리스트", page_icon="🛒", layout="centered")

_MD_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+\-.!~:|<>$&])")


def md_escape(text: str) -> str:
    """사용자 입력이 마크다운/색상 문법으로 해석되지 않도록 이스케이프."""
    return _MD_SPECIAL.sub(r"\\\1", text)


# ---------- 저장 (로컬 JSON 파일) ----------
# 파일이 유일한 원본(source of truth)이다. 모든 변경은 "파일 읽기 -> 수정 -> 파일 쓰기"를
# 락 안에서 수행하므로, 여러 탭/세션이 동시에 써도 서로의 변경을 덮어쓰지 않는다.
DATA_FILE = Path(__file__).parent / "data.json"


@st.cache_resource
def get_lock():
    """같은 서버 프로세스의 모든 세션이 공유하는 락 (스크립트가 재실행돼도 유지됨)."""
    return threading.RLock()


def load_data():
    """(items, next_id)를 반환. 파일이 없거나 손상됐으면 빈 상태.
    읽기 자체가 실패하는 OSError는 호출 쪽에서 처리하도록 그대로 올린다."""
    try:
        text = DATA_FILE.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [], 1
    try:
        data = json.loads(text)
        items = [
            {"id": int(i["id"]), "name": str(i["name"]), "done": bool(i["done"])}
            for i in data["items"]
        ]
        next_id = max([int(data.get("next_id", 1))] + [i["id"] + 1 for i in items])
        return items, next_id
    except (ValueError, KeyError, TypeError, AttributeError):
        # 손상된 파일은 덮어쓰기 전에 백업해 둔다.
        try:
            DATA_FILE.replace(DATA_FILE.with_suffix(".json.bak"))
        except OSError:
            pass
        return [], 1


def write_data(items, next_id) -> bool:
    """임시 파일에 쓴 뒤 교체해서 저장 중 손상을 막는다."""
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(dir=DATA_FILE.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"items": items, "next_id": next_id}, f, ensure_ascii=False, indent=2)
        os.replace(tmp, DATA_FILE)
        return True
    except OSError:
        if tmp:
            try:
                os.remove(tmp)
            except OSError:
                pass
        return False


def update_data(fn):
    """락 안에서 파일을 읽고 fn(data)로 수정한 뒤 저장한다. fn의 반환값을 돌려준다."""
    with get_lock():
        try:
            items, next_id = load_data()
        except OSError:
            st.session_state.save_failed = True
            return None
        data = {"items": items, "next_id": next_id}
        result = fn(data)
        if not write_data(data["items"], data["next_id"]):
            st.session_state.save_failed = True
        return result


# ---------- 상태 ----------
def sync_state():
    """매 실행마다 파일의 최신 내용을 세션에 반영한다 (다른 탭의 변경 포함)."""
    with get_lock():
        try:
            items, next_id = load_data()
        except OSError:
            st.session_state.save_failed = True
            if "shopping_items" in st.session_state:
                return  # 읽기에 실패하면 직전 상태를 유지한다.
            items, next_id = [], 1
    # 주의: st.session_state.items 는 dict.items() 와 충돌하므로 쓰지 않는다.
    st.session_state.shopping_items = items
    st.session_state.next_id = next_id
    # 체크박스 위젯 상태도 파일 기준으로 맞춘다 (다른 탭에서 바뀐 체크 반영).
    for item in items:
        st.session_state[f"check_{item['id']}"] = item["done"]


def init_state():
    if "editing_id" not in st.session_state:
        st.session_state.editing_id = None
    if "edit_error" not in st.session_state:
        st.session_state.edit_error = ""
    sync_state()
    # 수정 중이던 항목이 다른 탭에서 삭제됐으면 수정 상태를 해제한다.
    if st.session_state.editing_id is not None and not any(
        i["id"] == st.session_state.editing_id for i in st.session_state.shopping_items
    ):
        stop_editing()


def find_item(item_id: int):
    for item in st.session_state.shopping_items:
        if item["id"] == item_id:
            return item
    return None


def stop_editing():
    editing_id = st.session_state.editing_id
    if editing_id is not None:
        st.session_state.pop(f"edit_input_{editing_id}", None)
    st.session_state.editing_id = None
    st.session_state.edit_error = ""


# ---------- 콜백 ----------
def add_item(name: str) -> bool:
    """공백만 있는 값은 거부하고, 성공 시 True 반환. (중복 이름은 허용)"""
    name = name.strip()
    if not name:
        return False

    def _add(data):
        data["items"].append({"id": data["next_id"], "name": name, "done": False})
        data["next_id"] += 1

    update_data(_add)
    return True


def toggle_item(item_id: int):
    done = bool(st.session_state[f"check_{item_id}"])

    def _toggle(data):
        for item in data["items"]:
            if item["id"] == item_id:
                item["done"] = done

    update_data(_toggle)


def start_edit(item_id: int):
    stop_editing()  # 동시에 하나만 수정 가능
    item = find_item(item_id)
    if item is None:
        return
    st.session_state.editing_id = item_id
    st.session_state[f"edit_input_{item_id}"] = item["name"]


def save_edit(item_id: int):
    new_name = st.session_state.get(f"edit_input_{item_id}", "").strip()
    if not new_name:
        st.session_state.edit_error = "아이템 이름을 입력해 주세요."
        return

    def _rename(data):
        for item in data["items"]:
            if item["id"] == item_id:
                item["name"] = new_name

    update_data(_rename)
    stop_editing()


def cancel_edit():
    stop_editing()


def delete_item(item_id: int):
    if st.session_state.editing_id == item_id:
        stop_editing()

    def _delete(data):
        data["items"] = [i for i in data["items"] if i["id"] != item_id]

    update_data(_delete)
    st.session_state.pop(f"check_{item_id}", None)


def clear_done():
    def _clear(data):
        removed = [i["id"] for i in data["items"] if i["done"]]
        data["items"] = [i for i in data["items"] if not i["done"]]
        return removed

    removed = update_data(_clear) or []
    if st.session_state.editing_id in removed:
        stop_editing()
    for item_id in removed:
        st.session_state.pop(f"check_{item_id}", None)


# ---------- 화면 ----------
# 색상은 하드코딩하지 않고 Streamlit 테마 값(inherit/currentColor)만 사용한다.
# 모바일(<640px)에서 Streamlit 은 columns 를 세로로 쌓으므로, 행/폼 안의 columns 는
# 가로 배치를 유지하도록 강제한다.
CSS = """
<style>
.block-container { padding-top: 2.5rem; padding-bottom: 3rem; }
[class*="st-key-row_"] [data-testid="stHorizontalBlock"],
[class*="st-key-editrow_"] [data-testid="stHorizontalBlock"],
.st-key-add_bar [data-testid="stHorizontalBlock"],
[data-testid="stForm"] [data-testid="stHorizontalBlock"] {
    flex-wrap: nowrap !important;
    gap: 0.5rem;
    align-items: center;
}
[class*="st-key-row_"] [data-testid="stColumn"],
[class*="st-key-editrow_"] [data-testid="stColumn"],
.st-key-add_bar [data-testid="stColumn"],
[data-testid="stForm"] [data-testid="stColumn"] {
    min-width: 0 !important;
}
[class*="st-key-row_"] [data-testid="stCheckbox"] label p {
    font-size: 1.05rem;
    overflow-wrap: anywhere;
}
[class*="st-key-row_"] button { min-height: 2.5rem; min-width: 2.5rem; position: relative; }
/* 아이콘 버튼의 텍스트 라벨은 화면에서만 숨기고 스크린리더에는 남긴다 */
[class*="st-key-row_"] button [data-testid="stMarkdownContainer"] {
    position: absolute; width: 1px; height: 1px; overflow: hidden;
    clip-path: inset(50%); white-space: nowrap;
}
/* 진행 막대 채움색을 Streamlit 기본 강조색(버튼과 동일한 #ff4b4b)에 맞춘다.
   config.toml 의 [theme] 로 지정하면 시스템 다크 모드 자동 대응이 꺼지므로 CSS 로 처리한다. */
[data-testid="stProgress"] [role="progressbar"] > div > div { background-color: #ff4b4b; }
.empty-state { text-align: center; padding: 2.5rem 0; opacity: 0.7; }
.empty-state .icon { font-size: 3rem; line-height: 1.2; }
</style>
"""


def render_add_form():
    with st.form("add_form", clear_on_submit=True, border=False):
        with st.container(key="add_bar"):
            col_input, col_btn = st.columns([5, 1.4])
            name = col_input.text_input(
                "아이템 이름",
                placeholder="사야 할 물건을 입력하세요",
                label_visibility="collapsed",
            )
            submitted = col_btn.form_submit_button(
                "추가", type="primary", use_container_width=True
            )
    if submitted:
        if add_item(name):
            sync_state()  # 방금 추가한 항목이 같은 실행 안에서 목록에 보이도록 다시 읽는다.
        else:
            st.warning("아이템 이름을 입력해 주세요.")


def render_view_row(item: dict):
    item_id = item["id"]
    with st.container(border=True, key=f"row_{item_id}"):
        col_check, col_edit, col_delete = st.columns(
            [8, 1.2, 1.2], vertical_alignment="center"
        )
        label = md_escape(item["name"])
        if item["done"]:
            label = f":gray[~~{label}~~]"
        col_check.checkbox(
            label,
            key=f"check_{item_id}",  # 값은 sync_state()가 세션 상태로 미리 채워 둔다
            on_change=toggle_item,
            args=(item_id,),
        )
        col_edit.button(
            "수정", icon=":material/edit:", key=f"edit_{item_id}", help="수정", type="tertiary",
            on_click=start_edit, args=(item_id,), use_container_width=True,
        )
        col_delete.button(
            "삭제", icon=":material/delete:", key=f"delete_{item_id}", help="삭제", type="tertiary",
            on_click=delete_item, args=(item_id,), use_container_width=True,
        )


def render_edit_row(item: dict):
    item_id = item["id"]
    with st.container(border=True, key=f"editrow_{item_id}"):
        with st.form(f"edit_form_{item_id}", border=False):
            st.text_input(
                "아이템 이름 수정",
                key=f"edit_input_{item_id}",
                label_visibility="collapsed",
            )
            col_save, col_cancel = st.columns(2)
            col_save.form_submit_button(
                "저장", type="primary", on_click=save_edit, args=(item_id,),
                use_container_width=True,
            )
            col_cancel.form_submit_button(
                "취소", on_click=cancel_edit, use_container_width=True
            )
        if st.session_state.edit_error:
            st.warning(st.session_state.edit_error)


def render_summary():
    items = st.session_state.shopping_items
    total = len(items)
    done_count = sum(1 for i in items if i["done"])
    st.progress(done_count / total, text=f"전체 {total}개 중 {done_count}개 완료")
    st.button(
        "완료 항목 모두 삭제",
        key="clear_done",
        icon="🧹",
        on_click=clear_done,
        disabled=done_count == 0,
        use_container_width=True,
    )


def render_empty():
    st.markdown(
        '<div class="empty-state"><div class="icon">🛍️</div>'
        "<div><b>리스트가 비어 있어요</b></div>"
        "<div>위 입력창에 사야 할 물건을 추가해 보세요</div></div>",
        unsafe_allow_html=True,  # 고정 문구만 사용 (사용자 입력 없음)
    )


def render_list():
    items = st.session_state.shopping_items
    if not items:
        render_empty()
        return
    for item in items:
        if item["id"] == st.session_state.editing_id:
            render_edit_row(item)
        else:
            render_view_row(item)
    st.write("")
    render_summary()


def main():
    init_state()
    st.markdown(CSS, unsafe_allow_html=True)
    st.title("🛒 쇼핑 리스트")
    if st.session_state.pop("save_failed", False):
        st.error("데이터 파일을 읽거나 저장하지 못했어요. 최근 변경이 반영되지 않았을 수 있어요.")
    render_add_form()
    render_list()


main()
