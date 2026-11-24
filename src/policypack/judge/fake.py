"""모델을 부르지 않는 판정자. 해석기 자체를 시험할 때 쓴다(tests 전용)."""

from __future__ import annotations

from policypack.judge.base import Answer, Question, RawAnswer


class FakeJudge:
    """항상 같은 답을 준다. `echo_first_line` 이면 '예'에 코드의 첫 줄을 인용한다."""

    id = "fake"

    def __init__(self, answer: RawAnswer = "아니오", evidence: str = "", echo_first_line: bool = False) -> None:
        self.default = answer
        self.evidence = evidence
        self.echo_first_line = echo_first_line
        self.asked: list[Question] = []

    def ask(self, q: Question) -> Answer:
        self.asked.append(q)
        raw = self.default
        evidence = self.evidence
        if self.echo_first_line and raw == "예" and not evidence:
            # 코드에 실제로 있는 줄을 인용한다 — 근거 관문을 통과하는 '예'
            lines = [ln for ln in q.code.strip().splitlines() if len(ln.strip()) >= 6]
            evidence = lines[0].strip() if lines else ""
        return Answer(raw=raw, evidence=evidence)


def review_transport(read: str = "package.json", delay: float = 0.0, status: str = "확인할 것(저장소 밖)"):
    """review 의 질문(이해·근거 찾기·반박)에 모델 없이 답하는 가짜 전송(tests 전용). 질문마다 도구를 두 번(search,
    read_file) 쓰고 답한다. 근거 찾기는 의무마다 `status`(applies 예, 인용 없음. 기본 '저장소 밖'이라 반박을 묻는다),
    반박은 '유지'다. `delay` 초씩 쉬어 진행 표시가 그릴 틈을 준다."""
    import json
    import re
    import time

    def reply(doc: dict) -> dict:
        text = json.dumps(doc, ensure_ascii=False)
        return {"content": [{"type": "text", "text": text}], "usage": {"input_tokens": 100, "output_tokens": 20}}

    def send(body: dict) -> dict:
        if delay:
            time.sleep(delay)
        first = body["messages"][0]["content"]
        prompt = first if isinstance(first, str) else first[0]["text"]
        turn = len(body["messages"]) // 2
        if body["tool_choice"]["type"] != "none" and turn < 2:
            name, args = ("search", {"pattern": "개인정보|privacy"}) if turn == 0 else ("read_file", {"path": read})
            use = {"type": "tool_use", "id": f"t{turn}", "name": name, "input": args}
            return {"content": [use], "usage": {"input_tokens": 50, "output_tokens": 10}}
        if prompt.startswith("이 저장소가 어떤 서비스인지"):
            return reply({"summary": "가짜 답", "features": [], "flow": {"nodes": [], "edges": []}})
        ids = re.findall(r"^- \[([^\]]+)\]", prompt, re.M)
        if "앞 판단:" in prompt:
            return reply({"results": [{"duty": d, "result": "유지", "reason": "가짜 답"} for d in ids]})
        row = {
            "status": status,
            "citations": [],
            "searches": [],
            "applies": "모름",
            "question": "?",
            "reason": "가짜 답",
        }
        return reply({"results": [{"duty": d, **row} for d in ids]})

    return send
