"""Context budgets preserve the task while making omitted history explicit."""
import unittest

from pc.development.context import build_context, estimate_tokens


class DevelopmentContextTests(unittest.TestCase):
    def test_empty_and_unicode_token_estimates(self):
        self.assertEqual(estimate_tokens(''), 0)
        self.assertGreater(estimate_tokens('Исправь ошибку 🛠'), 0)
        self.assertGreater(estimate_tokens('a' * 400), estimate_tokens('a' * 40))

    def test_current_task_survives_large_history_and_checkpoint(self):
        prompt = 'Implement secure artifact retrieval.'
        events = [{'id': n, 'type': 'output', 'data': {'text': 'x' * 900}} for n in range(100)]
        context = build_context(prompt, events, {'summary': 'Old state ' + 'y' * 3000}, max_chars=1200)
        self.assertLessEqual(len(context), 1200)
        self.assertIn(prompt, context)
        self.assertIn('truncat', context.lower())
        self.assertIn('99', context)

    def test_ordinary_context_contains_checkpoint_and_event_payload(self):
        result = build_context('Fix tests', [{'id': 7, 'type': 'test', 'data': {'result': '3 passed'}}],
                               {'summary': 'Changed parser'})
        self.assertIn('Fix tests', result)
        self.assertIn('3 passed', result)
        self.assertIn('Changed parser', result)

    def test_huge_task_is_explicitly_truncated_inside_small_budget(self):
        result = build_context('start-' + 'x' * 20000 + '-end', [], max_chars=256)
        self.assertLessEqual(len(result), 256)
        self.assertIn('start-', result)
        self.assertIn('-end', result)
        self.assertIn('truncat', result.lower())

    def test_latest_events_beat_old_events_when_history_is_limited(self):
        events = [{'id': n, 'type': 'note', 'data': {'text': f'MESSAGE-{n}-' + 'z' * 100}} for n in range(20)]
        result = build_context('task', events, max_chars=600)
        self.assertIn('MESSAGE-19-', result)
        self.assertNotIn('MESSAGE-0-', result)

    def test_invalid_budget_is_rejected(self):
        for value in (0, -1, 20, 'large', True):
            with self.assertRaises(ValueError):
                build_context('task', [], max_chars=value)

    def test_omitted_history_is_marked_even_when_task_uses_almost_all_budget(self):
        result = build_context('t' * 210, [{'type': 'output', 'data': 'long history' * 30}], max_chars=256)
        self.assertLessEqual(len(result), 256)
        self.assertIn('truncat', result.lower())

    def test_context_budget_cannot_be_defeated_by_many_exactly_fitting_events(self):
        for budget in range(128, 512, 11):
            events = [{'id': n, 'data': 'x' * (n % 30)} for n in range(40)]
            result = build_context('task', events, {'summary': 'state'}, max_chars=budget)
            self.assertLessEqual(len(result), budget)


if __name__ == '__main__':
    unittest.main()
