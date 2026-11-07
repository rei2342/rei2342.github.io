"""note へ下書きを投入する（Playwright）。公開ボタンは押さない。

note には公式の投稿APIが無いので、本人のログインセッションでエディタを操作する。
初回だけ `python main.py note-login <account>` で画面ログインし、セッションを data/sessions に保存する。
"""
from __future__ import annotations

import html
import re

from core import config as C
from publishers.base import outbox

EDITOR_URL = "https://note.com/notes/new"


def state_path(key: str):
    return C.data_path("sessions", f"note_{key}.json")


def md_to_html(md: str) -> str:
    out, in_ul, in_ol = [], False, False

    def inline(t: str) -> str:
        t = html.escape(t)
        t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
        t = re.sub(r"\[(.+?)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', t)
        return t

    def close():
        nonlocal in_ul, in_ol
        if in_ul:
            out.append("</ul>")
        if in_ol:
            out.append("</ol>")
        in_ul = in_ol = False

    for line in md.splitlines():
        s = line.rstrip()
        if m := re.match(r"^(#{2,3})\s+(.*)", s):
            close()
            out.append(f"<h{len(m.group(1))}>{inline(m.group(2))}</h{len(m.group(1))}>")
        elif m := re.match(r"^[-*]\s+(.*)", s):
            if not in_ul:
                close()
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{inline(m.group(1))}</li>")
        elif m := re.match(r"^\d+[.)]\s+(.*)", s):
            if not in_ol:
                close()
                out.append("<ol>")
                in_ol = True
            out.append(f"<li>{inline(m.group(1))}</li>")
        elif s.startswith(">"):
            close()
            out.append(f"<blockquote>{inline(s.lstrip('> '))}</blockquote>")
        elif not s.strip():
            close()
        else:
            close()
            out.append(f"<p>{inline(s)}</p>")
    close()
    return "\n".join(out)


def _browser(pw, headless=True):
    return C.launch_chromium(pw, headless=headless)


def login(account_key: str, timeout_sec: int = 300) -> str:
    from playwright.sync_api import sync_playwright

    email, pw_ = C.cred("NOTE_EMAIL", account_key), C.cred("NOTE_PASSWORD", account_key)
    with sync_playwright() as pw:
        b = _browser(pw, headless=False)
        ctx = b.new_context(locale="ja-JP")
        page = ctx.new_page()
        page.goto("https://note.com/login")
        if email and pw_:
            page.fill("input#email, input[name='login'], input[type='email']", email)
            page.fill("input#password, input[type='password']", pw_)
            page.keyboard.press("Enter")
        # 2段階認証などは画面で人が操作する
        page.wait_for_url(re.compile(r"https://note\.com/(?!login).*"), timeout=timeout_sec * 1000)
        ctx.storage_state(path=str(state_path(account_key)))
        b.close()
    return str(state_path(account_key))


def publish(acct, platform, body, draft, settings, dry_run=True) -> dict:
    payload = {"title": body["title"], "html": md_to_html(body["markdown"]), "hashtags": body.get("hashtags", [])}
    if dry_run:
        return {"ok": True, "dry_run": True, "outbox": outbox("note", acct.key, payload)}
    sp = state_path(acct.key)
    if not sp.exists():
        return {"ok": False, "error": f"note セッションが無い。python main.py note-login {acct.key} を先に実行"}
    from playwright.sync_api import sync_playwright

    shot = C.data_path("outbox", "note", f"{draft['id']}.png")
    with sync_playwright() as pw:
        b = _browser(pw)
        ctx = b.new_context(storage_state=str(sp), locale="ja-JP", viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        try:
            page.goto(EDITOR_URL, wait_until="domcontentloaded", timeout=60000)
            title = page.locator("textarea[placeholder*='タイトル'], [data-placeholder*='タイトル']").first
            title.wait_for(timeout=30000)
            title.click()
            title.fill(payload["title"]) if title.evaluate("e => e.tagName") == "TEXTAREA" else page.keyboard.type(payload["title"])
            editor = page.locator("div.ProseMirror[contenteditable='true']").first
            editor.click()
            page.evaluate("""(h) => {
                const dt = new DataTransfer();
                dt.setData('text/html', h);
                dt.setData('text/plain', h.replace(/<[^>]+>/g, ''));
                const el = document.querySelector("div.ProseMirror[contenteditable='true']");
                el.dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true}));
            }""", payload["html"])
            page.wait_for_timeout(1500)
            btn = page.get_by_role("button", name=re.compile("下書き保存"))
            btn.first.click(timeout=15000)
            page.wait_for_timeout(3000)
            page.screenshot(path=str(shot), full_page=False)
            url = page.url
            ctx.storage_state(path=str(sp))  # セッション延命
        except Exception as e:
            try:
                page.screenshot(path=str(shot))
            except Exception:
                pass
            b.close()
            return {"ok": False, "error": f"note エディタ操作に失敗（UI変更の可能性）: {e}"[:400], "screenshot": str(shot)}
        b.close()
    return {"ok": True, "status": "draft", "url": url, "screenshot": str(shot)}
