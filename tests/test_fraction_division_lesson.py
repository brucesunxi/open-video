import json
from fractions import Fraction
from pathlib import Path
from server.app import Slide


def test_division_lesson_board_cues_and_slide_roundtrip():
    lesson = json.loads(Path('lessons/fraction-division-integer.json').read_text())
    assert len(lesson['slides']) == 10
    for i, slide in enumerate(lesson['slides']):
        model = Slide(**slide, id=str(i), source_ids=['reviewed-source'])
        cues = model.board_anchors
        assert len(cues) == len(model.bullets)
        positions = [model.narration.index(cue) for cue in cues]
        assert positions == sorted(set(positions))
        assert model.model_dump()['board_anchors'] == cues
        assert all(len(line) <= 160 for line in model.bullets)


def test_worked_examples_and_inverse_checks():
    for initial, divisor, equivalent, answer in [
        (Fraction(4, 5), 2, Fraction(4, 5), Fraction(2, 5)),
        (Fraction(4, 5), 3, Fraction(12, 15), Fraction(4, 15)),
        (Fraction(3, 7), 2, Fraction(6, 14), Fraction(3, 14)),
        (Fraction(2, 3), 4, Fraction(8, 12), Fraction(1, 6)),
    ]:
        assert initial == equivalent
        assert initial / divisor == answer
        assert answer * divisor == initial
        assert answer < initial
