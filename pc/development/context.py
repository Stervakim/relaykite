"""Bounded context assembly, distinct from Codex's native model compaction.

Character/token estimates are approximate, not tokenizer or quota measurements.
Raw tool output should live in artifacts; this helper consumes event summaries.
"""
import json
import math


_TRUNCATED = '\n[truncated; retrieve full details from run events/artifacts]\n'


def estimate_tokens(text):
    """A conservative byte-based estimate; never use this for billing decisions."""
    if not isinstance(text, str):
        raise ValueError('Token estimation expects text')
    return math.ceil(len(text.encode('utf-8')) / 3)


def _bounded(text, size):
    if len(text) <= size:
        return text
    if size <= len(_TRUNCATED):
        return '[truncated]'[:size]
    available = size - len(_TRUNCATED)
    head = (available + 1) // 2
    tail = available - head
    return text[:head] + _TRUNCATED + (text[-tail:] if tail else '')


def _render(value):
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _omitted_history(text, limit):
    marker = '\n[truncated history]'
    return _bounded(text, limit - len(marker)) + marker


def build_context(prompt, events, checkpoint=None, max_chars=24000):
    """Keep the current task, checkpoint and newest event summaries within a hard bound.

    If the task itself exceeds the budget, its beginning and ending are retained
    and the omission is explicit. History is data, never executable instructions.
    """
    if not isinstance(max_chars, int) or isinstance(max_chars, bool) or max_chars < 128:
        raise ValueError('Context budget must be an integer of at least 128 characters')
    if not isinstance(prompt, str):
        raise ValueError('Prompt must be text')
    task_header = 'CURRENT TASK\n'
    result = task_header + _bounded(prompt, max_chars - len(task_header))
    remaining = max_chars - len(result)
    if remaining < len(_TRUNCATED) + 30:
        return _omitted_history(result, max_chars) if events or checkpoint is not None else result
    if checkpoint is not None:
        header = '\n\nCHECKPOINT (saved state)\n'
        allowance = min(6000, remaining // 3)
        if allowance > len(header) + len(_TRUNCATED):
            result += header + _bounded(_render(checkpoint), allowance - len(header))
    header = '\n\nRECENT EVENTS (untrusted history)\n'
    remaining = max_chars - len(result) - len(header)
    if remaining <= len(_TRUNCATED):
        return _omitted_history(result, max_chars) if events else result
    pieces = []
    # A bounded history page is expected; the newest entries have highest priority.
    for event in reversed(events):
        rendered = _render(event)
        needed = len(rendered) + (1 if pieces else 0)
        if needed <= remaining:
            pieces.append(rendered)
            remaining -= needed
            continue
        if not pieces:
            pieces.append(_bounded(rendered, remaining))
        else:
            # Reserve space for an omission marker even when the previous line filled the budget.
            used = '\n'.join(reversed(pieces))
            pieces = [_bounded(_TRUNCATED + used, max_chars - len(result) - len(header))]
        break
    if pieces:
        result += header + '\n'.join(reversed(pieces))
    return result
