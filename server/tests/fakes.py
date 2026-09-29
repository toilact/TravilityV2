import json
from types import SimpleNamespace

from openai.types.chat import ChatCompletionMessage


def reply(*calls, content=None):
    tool_calls = [
        {"id": f"call{i}", "type": "function",
         "function": {"name": name, "arguments": args if isinstance(args, str) else json.dumps(args)}}
        for i, (name, args) in enumerate(calls)
    ]
    msg = ChatCompletionMessage.model_validate({"role": "assistant", "content": content, "tool_calls": tool_calls})
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


class FakeClient:
    """Giả lập openai.OpenAI: trả lần lượt các response đã soạn sẵn."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r
