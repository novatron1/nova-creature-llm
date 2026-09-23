"""Exercise twenty completed chats through Nova's real streaming browser UI."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import time

from playwright.sync_api import sync_playwright, expect
from nova_chitchat_live_probe import PROMPTS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = {'started_at': dt.datetime.now(dt.timezone.utc).isoformat(),
              'surface': 'real browser /nova/v1/chat streaming UI',
              'turns': [], 'checks': {}, 'errors': [], 'quality_review': 'pending'}

    def save():
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1440, 'height': 1000})
        context.tracing.start(screenshots=True, snapshots=True, sources=False)
        page = context.new_page()
        page.set_default_timeout(90_000)
        requests = []
        page.on('pageerror', lambda error: report['errors'].append(str(error)))
        page.on('request', lambda request: requests.append(request.url)
                if request.method == 'POST' and request.url.endswith(('/nova/v1/chat', '/api/chat')) else None)
        try:
            page.goto('http://127.0.0.1:3000/', wait_until='domcontentloaded')
            expect(page.locator('#btnServer')).to_have_text('Connected')
            report['checks']['connected'] = True
            entry, send = page.locator('#input'), page.locator('#sendBtn')
            for number, prompt in enumerate(PROMPTS, 1):
                started = time.monotonic()
                before = len(requests)
                held = []
                if number == 4:
                    # Hold the real request briefly to make the in-flight UI
                    # assertion deterministic. Continue it unchanged afterward.
                    page.route('**/nova/v1/chat', lambda route: held.append(route))
                entry.fill(prompt)
                send.click()
                if number == 4:
                    expect(send).to_have_text('Stop')
                    entry.fill('A draft for after this reply.')
                    entry.press('Enter')
                    expect(entry).to_have_value('A draft for after this reply.')
                    expect(send).to_have_text('Stop')
                    assert len(held) == 1, f'Expected one held request, got {len(held)}'
                    assert len(requests) == before + 1, 'Enter submitted another request'
                    held[0].continue_()
                    page.unroute('**/nova/v1/chat')
                expect(send).to_have_text('Send')
                expect(page.locator('#chat [data-streaming="true"]')).to_have_count(0)
                answer_node = page.locator('#chat .msg.nova').last
                answer = answer_node.evaluate('''el => {
                    const copy = el.cloneNode(true);
                    copy.querySelectorAll('.meta,.answer-status,.correction-bar').forEach(x => x.remove());
                    return copy.textContent.trim();
                }''')
                item = {'number': number, 'prompt': prompt, 'response': answer,
                        'seconds': round(time.monotonic() - started, 3),
                        'model_label': answer_node.locator('.answer-status-chip').inner_text(),
                        'network_requests': len(requests) - before}
                assert item['network_requests'] == 1, item
                assert answer and answer != 'Stopped.' and 'Error:' not in answer, item
                expect(answer_node.locator('.answer-status-details')).to_be_hidden()
                report['turns'].append(item)
                if number == 4:
                    expect(entry).to_have_value('A draft for after this reply.')
                    report['checks']['enter_preserves_pending_reply_and_draft'] = True
                    entry.fill('')
                save()
                print(json.dumps(item, ensure_ascii=False), flush=True)
            report['checks']['all_twenty_completed'] = len(report['turns']) == 20
            report['checks']['diagnostics_collapsed'] = True
            page.screenshot(path=str(args.output.with_suffix('.png')), full_page=False)
            before = len(requests)
            entry.fill('OPEN THE GPU HUB')
            send.click()
            expect(page.locator('#gpu-hub-panel')).to_be_visible()
            assert len(requests) == before, 'Navigation incorrectly invoked a language model'
            report['checks']['gpu_hub_chat_command_opens_panel_without_model'] = True
            page.locator('.nav-tab[data-panel="chat-panel"]').click()
            expect(page.locator('#chat-panel')).to_be_visible()
            page.locator('.answer-status-toggle').last.click()
            expect(page.locator('.answer-status-details').last).to_be_visible()
            report['checks']['details_expand'] = True
        except Exception as error:
            report['error'] = f'{type(error).__name__}: {error}'
            page.screenshot(path=str(args.output.with_suffix('.failure.png')))
            raise
        finally:
            save()
            context.tracing.stop(path=str(args.output.with_suffix('.trace.zip')))
            browser.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
