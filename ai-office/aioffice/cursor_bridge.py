"""Private Cursor SDK adapter: text only, no filesystem or shell capabilities."""
import dataclasses
import hmac
import json
import os
import pathlib
import tempfile
import threading
from decimal import Decimal

import uvicorn
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
slots = threading.BoundedSemaphore(1)


class Prompt(BaseModel):
    text: str = Field(min_length=1, max_length=14000)


@app.get('/health/live')
@app.get('/health/ready')
def healthy():
    return {'status': 'ready', 'model': 'grok-4.7', 'tools': []}


def complete(prompt):
    # SDK's native streaming transport works through the mandatory VM TUN.
    # Python still uses HTTP_PROXY for ordinary HTTP. No direct internet route
    # is permitted even when the JS streaming transport ignores HTTP_PROXY.
    os.environ['NODE_USE_ENV_PROXY'] = '0'
    from cursor_sdk import Agent, AgentOptions, CursorClient, LocalAgentOptions
    key = os.environ['CURSOR_API_KEY']
    home = pathlib.Path('/tmp/cursor-home')
    home.mkdir(mode=0o700, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='text-agent-', dir=home) as tmp:
        local = LocalAgentOptions(cwd=tmp, setting_sources=[])
        with CursorClient.launch_bridge(workspace=tmp, state_root=tmp + '/state', local=local, client_timeout=80, max_retries=0) as client:
            options = AgentOptions(api_key=key, model={'id': 'grok-4.7', 'params': [
                {'id': 'reasoning_effort', 'value': 'low'}, {'id': 'context', 'value': '256k'}, {'id': 'fast', 'value': 'false'}]},
                tools=[], disallowed_tools=['shell', 'mcp', 'task'], local=local)
            with Agent.create(options, client=client) as agent:
                run = agent.send(prompt)
                def cancel():
                    try:
                        run.cancel()
                    except Exception:
                        pass
                timer = threading.Timer(60, cancel)
                timer.start()
                emitted = 0
                try:
                    for message in run.messages():
                        if message.type == 'tool_call':
                            cancel()
                            raise RuntimeError('Unexpected tool request from a text-only agent')
                        if message.type == 'assistant':
                            for block in message.message.content:
                                if getattr(block, 'type', '') == 'text':
                                    emitted += len(block.text)
                            if emitted > 12000:
                                cancel()
                    result = run.wait()
                    if result.status != 'finished' or not result.result:
                        raise RuntimeError('Cursor run did not complete')
                    usage = dataclasses.asdict(result.usage) if result.usage else None
                    estimated = None
                    if usage:
                        estimated = str((Decimal(usage['input_tokens']) * 2 + Decimal(usage['cache_read_tokens']) * Decimal('.5') + Decimal(usage['output_tokens']) * 6) / 1000000)
                    # Actual billing access is unavailable on this account.
                    return {'text': result.result[:12000], 'model': 'grok-4.7', 'usage': usage, 'estimated_usd': estimated,
                            'charged_usd': None, 'run_id': result.id, 'tools_enabled': False}
                finally:
                    timer.cancel()


@app.post('/complete')
def answer(body: Prompt, authorization: str = Header(default='')):
    expected = 'Bearer ' + os.environ['CURSOR_BRIDGE_TOKEN']
    if not hmac.compare_digest(authorization, expected):
        raise HTTPException(403, 'Invalid bridge capability')
    if not slots.acquire(blocking=False):
        raise HTTPException(429, 'One Cursor run at a time')
    try:
        return complete(body.text)
    except Exception as exc:
        # SDK exceptions can embed credentials, prompts or internal URLs.
        name = type(exc).__name__
        if not name.isalpha():
            name = 'Error'
        print('Cursor adapter failure_type=' + name, flush=True)
        raise HTTPException(502, name) from None
    finally:
        slots.release()


if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=8081, access_log=False)

