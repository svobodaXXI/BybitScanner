"""PR #452 review: the Scanner-pass candidate observer is per pass and per thread.

Two overlapping passes on different threads, and a nested pass, must never see
each other's observer or leave one behind. No DB and no network.
"""

import threading
import unittest

import pattern_robot_integration as integration


def _notify(candidate_id):
    integration._notify_candidate_observer(candidate_id)


class CandidateObserverScopeTests(unittest.TestCase):
    def test_interleaved_passes_on_two_threads_never_cross_or_leak(self):
        seen = {"A": [], "B": []}
        a_bound, b_bound, a_done, b_may_finish = (threading.Event() for _ in range(4))
        errors = []

        def pass_a():
            try:
                with integration.robot_candidate_observer(seen["A"].append):
                    a_bound.set()
                    b_bound.wait(5)
                    _notify("a-1")
                # A ends while B is still inside its pass.
                a_done.set()
                _notify("a-after")
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        def pass_b():
            try:
                a_bound.wait(5)
                with integration.robot_candidate_observer(seen["B"].append):
                    b_bound.set()
                    a_done.wait(5)
                    _notify("b-1")
                    b_may_finish.wait(5)
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        threads = [threading.Thread(target=pass_a), threading.Thread(target=pass_b)]
        for thread in threads:
            thread.start()
        a_done.wait(5)
        b_may_finish.set()
        for thread in threads:
            thread.join(5)

        self.assertEqual(errors, [])
        self.assertEqual(seen, {"A": ["a-1"], "B": ["b-1"]})
        # Nothing is left bound for later handoffs outside any pass.
        _notify("outside")
        self.assertEqual(seen, {"A": ["a-1"], "B": ["b-1"]})

    def test_nested_pass_restores_the_outer_observer(self):
        outer, inner = [], []
        with integration.robot_candidate_observer(outer.append):
            _notify("o-1")
            with integration.robot_candidate_observer(inner.append):
                _notify("i-1")
            _notify("o-2")
        _notify("outside")
        self.assertEqual((outer, inner), (["o-1", "o-2"], ["i-1"]))

    def test_unrelated_thread_without_a_pass_sees_no_observer(self):
        seen = []
        other = []
        with integration.robot_candidate_observer(seen.append):
            thread = threading.Thread(target=lambda: other.append(_notify("other-thread")))
            thread.start()
            thread.join(5)
        self.assertEqual(seen, [])


if __name__ == "__main__":
    unittest.main()
