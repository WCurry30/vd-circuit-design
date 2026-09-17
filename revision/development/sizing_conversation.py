"""One optional sizing call with an explicitly bounded model continuation."""

import json
import re

from sizing_tool import TOOL, SizingTool


def reject_serialized_tool_call(message):
    # Some providers leak their internal tool syntax into ordinary content.
    if re.search(r'<[^>\n]*DSML[^>\n]*tool_calls[^>\n]*>',
                 message.content or ''):
        raise ValueError('serialized tool invocation in content; no SPICE deck returned')


def generate_with_sizing(create, request, *, remaining_calls, events):
    if remaining_calls < 1:
        raise ValueError('synthesis API budget exhausted')
    kwargs = dict(request)
    if events:
        # Replay reconstructs calculator events; latency is audit metadata,
        # not design context, and must not change the exact cached request.
        context_events = [{key: value for key, value in event.items()
                           if key != 'elapsed_seconds'} for event in events]
        kwargs['messages'] = list(request['messages']) + [{
            'role': 'user',
            'content': 'Previous analytical sizing results from this trial (advisory; '
                       'retain their stated assumptions and verify against feedback):\n' +
                       json.dumps(context_events, ensure_ascii=True, allow_nan=False, sort_keys=True)
        }]
    if remaining_calls >= 2:
        kwargs.update(tools=[TOOL], tool_choice='auto', parallel_tool_calls=False)
    response = create(**kwargs)
    message = response.choices[0].message
    calls = getattr(message, 'tool_calls', None)
    if not calls:
        reject_serialized_tool_call(message)
        return response
    if remaining_calls < 2 or len(calls) != 1:
        raise ValueError('unexpected tool calls or insufficient continuation budget')
    call = calls[0]
    tool = SizingTool()
    reply = tool.execute(name=call.function.name, arguments=call.function.arguments, call_id=call.id)
    events.extend(tool.events)
    assistant = {'role': 'assistant', 'content': message.content,
                 'tool_calls': [{'id': call.id, 'type': 'function', 'function': {
                     'name': call.function.name, 'arguments': call.function.arguments}}]}
    continuation = dict(request)
    continuation['messages'] = list(kwargs['messages']) + [assistant, reply, {
        'role': 'user',
        'content': 'The analytical tool step is complete. Use the returned result '
                   'as advisory design context and respect the original requirement. '
                   'Return the complete SPICE deck now. No further tool calls are '
                   'available in this response; omit explanations and tool markup.'
    }]
    # The final answer may not request a second tool invocation.
    continuation.update(tools=[TOOL], tool_choice='none', parallel_tool_calls=False)
    result = create(**continuation)
    if getattr(result.choices[0].message, 'tool_calls', None):
        raise ValueError('repeated tool invocation is not allowed')
    reject_serialized_tool_call(result.choices[0].message)
    return result
