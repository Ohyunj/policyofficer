"""의무별 제재 표(profile/sanctions.jsonl): 불러올 때의 검사, review 결과의 sanction."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from policypack import profile
from policypack import review as rv
from policypack.judge.agent import AgentJudge
from policypack.judge.fake import review_transport

jsonschema = pytest.importorskip("jsonschema")
SCHEMA = json.loads((Path(__file__).resolve().parents[1] / "schemas" / "review-2.json").read_text(encoding="utf-8"))


def test_the_table_has_one_record_for_each_duty_the_review_asks():
    table = profile.load_sanctions()
    asked = {d["id"] for d in profile.load_duties() if d.get("addressee")}
    assert set(table) == asked and len(table) == 220
    assert {s["class"] for s in table.values()} <= set(profile.SANCTION_CLASSES)
    assert all(i["quote"].strip() for s in table.values() for i in s["items"])
    assert all("duty" not in s for s in table.values())


@pytest.fixture
def table_dir(tmp_path, monkeypatch):
    """표를 tmp 로 옮겨 고쳐 본다. 끝나면 캐시를 비운다."""
    shutil.copy(profile.HERE / "duties.jsonl", tmp_path / "duties.jsonl")
    rows = [json.loads(x) for x in (profile.HERE / "sanctions.jsonl").read_text(encoding="utf-8").splitlines()]
    monkeypatch.setattr(profile, "HERE", tmp_path)
    profile.load_sanctions.cache_clear()

    def write(rows_: list[dict]) -> None:
        text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows_)
        (tmp_path / "sanctions.jsonl").write_text(text, encoding="utf-8")
        profile.load_sanctions.cache_clear()

    yield rows, write
    profile.load_sanctions.cache_clear()


@pytest.mark.parametrize("broken", ["missing", "twice", "extra", "class", "quote"])
def test_a_broken_table_is_refused_when_loaded(table_dir, broken):
    rows, write = table_dir
    rows = json.loads(json.dumps(rows))
    with_item = next(r for r in rows if r["items"])
    if broken == "missing":
        rows = rows[1:]
    elif broken == "twice":
        rows.append(rows[0])
    elif broken == "extra":
        rows.append({**rows[0], "duty": "no-such-duty"})
    elif broken == "class":
        rows[0]["class"] = "사형"
    else:
        with_item["items"][0]["quote"] = "  "
    write(rows)
    with pytest.raises(ValueError, match="sanctions.jsonl"):
        profile.load_sanctions()


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "package.json").write_text(json.dumps({"dependencies": {"express": "^4.0.0"}}), encoding="utf-8")
    (root / "src" / "signup.ts").write_text(
        'router.post("/signup", async (req, res) => {\n  const { email, name } = req.body;\n});\n', encoding="utf-8"
    )
    return root


def test_every_checklist_item_carries_its_sanction_and_matches_the_schema(tmp_path):
    inv, chk = AgentJudge("claude-haiku-5-5", review_transport()), AgentJudge("claude-sonnet-5-5", review_transport())
    doc = rv.review(_repo(tmp_path), inv, chk, rv.Limits(concurrency=4), use_static=False)
    table = profile.load_sanctions()
    assert doc["checklist"]
    for c in doc["checklist"]:
        assert c["sanction"] == table[c["duty"]]
        assert list(c)[: list(c).index("sanction") + 1][-2:] == ["static", "sanction"]
    errors = list(jsonschema.Draft202012Validator(SCHEMA).iter_errors(doc))
    assert not errors, [f"{list(e.path)}: {e.message[:200]}" for e in errors[:5]]
