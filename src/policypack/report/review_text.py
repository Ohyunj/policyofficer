"""review 결과(JSON)의 사람이 읽는 요약. stdout 이 터미널일 때 JSON 대신 낸다(전체 JSON 은 파일로 저장한다).

상태별 개수, '확인할 것' 목록(법·조문·제목·인용 file:line), 걸린 시간, 어림 금액, 저장한 JSON 의 경로. 목록은 갈래
(코드에서 본 것 → 저장소 밖 → 해당 여부) 안에서 제재 등급 순(SANCTION_ORDER), 같은 등급이면 정액 상한(max_won)이 큰
것이 먼저다. 항목에 제재(sanction)가 없으면 체크리스트 순서(rank) 그대로다.
"""

from __future__ import annotations

import os
from pathlib import Path

from policypack.report.progress import SGR, Glyphs, article, clean, clock, fit, fit_tail, pad, title, width
from policypack.review.prompts import ORDER, STATUS_LABEL

TO_CHECK = ("seen-in-code", "check-outside", "check-applicability")
SANCTION_ORDER = ("징역", "과징금", "벌금", "과태료", "명령", "없음")
"""제재 등급(의무별 제재 표의 class)의 무거운 순서."""
NOTE = "법률 자문이 아닙니다. 검토가 필요한 곳을 고를 뿐입니다."
GOODS = "특정 품목을 판다면 확인할 것"


def order_key(c: dict) -> tuple:
    """같은 갈래 안의 순서: 제재 등급, 정액 상한이 큰 것, 체크리스트 순서."""
    s = c.get("sanction") or {}
    cls = s.get("class")
    heavy = SANCTION_ORDER.index(cls) if cls in SANCTION_ORDER else len(SANCTION_ORDER)
    return (heavy, -(s.get("max_won") or 0), c.get("rank", 0))


def law_short(c: dict) -> str:
    """의무 표의 짧은 법 이름(law_short). 표에 없으면 결과의 법 이름."""
    from policypack.profile import load_duties

    global _SHORT
    if _SHORT is None:
        _SHORT = {d["id"]: d.get("law_short") or d["law"] for d in load_duties()}
    return _SHORT.get(c["duty"]) or c.get("law", "")


_SHORT: dict[str, str] | None = None


def home(path: str | Path) -> str:
    p, h = str(path), str(Path.home())
    return "~" + p[len(h) :] if p == h or p.startswith(h + os.sep) else p


def render(doc: dict, saved: str | Path | None, color: bool, cols: int | None, unicode: bool = True) -> str:
    """`cols` 가 None 이면 줄을 자르지 않는다(stdout 이 터미널이 아닐 때)."""
    g = Glyphs(unicode)
    dot = f" {g.dot} "
    run = doc.get("run", {})
    checklist = doc.get("checklist", [])
    lines: list[tuple[str, str | None]] = []

    def add(text: str = "", style: str | None = None, lead: str | None = None) -> None:
        """`lead` 가 있으면 그 뒤의 글(경로)은 앞을 잘라 끝(파일 이름)을 남긴다."""
        if lead is not None:
            text = lead + (fit_tail(text, cols - width(lead), g.more) if cols is not None else text)
        elif cols is not None:
            text = fit(text, cols, g.more)
        lines.append((text, style))

    asked = len(run.get("questions", []))
    usd = run.get("usd_estimate", 0)
    add(f"{g.done} 검토 끝{dot}{clock(run.get('seconds', 0))}{dot}어림 ${usd:.2f}{dot}질문 {asked}개", "bold")
    add()
    counts = {s: sum(1 for c in checklist if c["status"] == s) for s in ORDER}
    label_w = max(width(STATUS_LABEL[s]) for s in ORDER if counts[s]) if any(counts.values()) else 0
    for s in ORDER:
        if counts[s]:
            add(f"  {pad(STATUS_LABEL[s], label_w)}  {counts[s]:>3}", "bold" if s in TO_CHECK else None)
    todo = [c for c in checklist if c["status"] in TO_CHECK]
    n = 0
    for s in TO_CHECK:
        items = sorted((c for c in todo if c["status"] == s and c.get("group") != "goods"), key=order_key)
        goods = [c for c in todo if c["status"] == s and c.get("group") == "goods"]
        if not items and not goods:
            continue
        add()
        add(f"{STATUS_LABEL[s]} ({len(items) + len(goods)})", "bold")
        for c in items:
            n += 1
            law = f"{clean(law_short(c))} {article(c.get('article', ''))}"
            add(f"  {n:>2}  {law}{dot}{clean(title(c.get('title', '')))}")
            cite = next((x for x in c.get("citations", []) if x.get("ok")), None)
            if cite:
                where = f"{cite['file']}:{cite['line']}" if cite.get("line") else cite["file"]
                add(clean(where), "dim", lead="      ")
        if goods:
            add(f"   {g.more} {GOODS} {len(goods)}개", "dim")
    add()
    if saved:
        add(home(saved), lead="전체 결과(JSON): ")
    add(NOTE, "dim")
    return "".join((f"\x1b[{SGR[s]}m{t}\x1b[0m" if color and s and t else t) + "\n" for t, s in lines)
