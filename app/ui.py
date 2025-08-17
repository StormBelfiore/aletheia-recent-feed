import os, html, glob, subprocess, time
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse, FileResponse, StreamingResponse

OUTBOX = os.environ.get("AOS_OUTBOX", os.path.expanduser("~/AletheiaOS/core/black_room/outbox"))
ALLOWED_SIGNERS = os.path.expanduser(os.environ.get("AOS_ALLOWED_SIGNERS", "~/.config/aletheia/allowed_signers"))
SIGNER_ID = os.environ.get("AOS_SIGNER_ID", "aletheia")

router = APIRouter()

def _verify_status(ans_path: str) -> str:
    sig_path = f"{ans_path}.sig"
    if not os.path.exists(sig_path) or not os.path.exists(ALLOWED_SIGNERS):
        return "unknown"
    try:
        cmd = ["ssh-keygen","-Y","verify","-f",ALLOWED_SIGNERS,"-I",SIGNER_ID,"-n","aletheia","-s",sig_path]
        with open(ans_path, "rb") as fin:
            proc = subprocess.run(cmd, stdin=fin, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
        return "verified" if proc.returncode == 0 else "invalid"
    except Exception:
        return "unknown"

def _safe_name(name: str) -> str:
    base = os.path.basename(name)
    if not base.endswith(".answer.txt"):
        raise ValueError("bad name")
    return base

def _ans_path_from_name(name: str) -> str:
    return os.path.join(OUTBOX, _safe_name(name))

def _sig_path_from_name(name: str) -> str:
    return _ans_path_from_name(name) + ".sig"

def _pub_fingerprint() -> str:
    try:
        p = Path(ALLOWED_SIGNERS)
        if not p.exists():
            return "unknown"
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 3:
                keytype, b64 = parts[1], parts[2]
                tmp = Path("/tmp/_aos_pubkey.pub")
                tmp.write_text(f"{keytype} {b64}\n", encoding="utf-8")
                proc = subprocess.run(["ssh-keygen","-lf",str(tmp)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3)
                try: tmp.unlink()
                except: pass
                if proc.returncode == 0:
                    return proc.stdout.decode("utf-8","ignore").strip()
        return "unknown"
    except Exception:
        return "unknown"

def _recent_items(limit: int = 50):
    paths = sorted(glob.glob(os.path.join(OUTBOX,"*.answer.txt")), key=os.path.getmtime, reverse=True)[:limit]
    items = []
    for p in paths:
        try:
            with open(p,"r",encoding="utf-8",errors="replace") as f:
                body = f.read(4000)
            items.append({
                "path": p,
                "name": os.path.basename(p),
                "when": datetime.fromtimestamp(os.path.getmtime(p)).isoformat(sep=" ", timespec="seconds"),
                "preview": body.strip()[:280],
                "status": _verify_status(p),
            })
        except Exception:
            continue
    return items

@router.get("/ui/recent", response_class=HTMLResponse)
def ui_recent():
    items = _recent_items(100)

    def badge(s):
        if s == "verified": return '<span class="badge ok">verified</span>'
        if s == "invalid":  return '<span class="badge bad">invalid</span>'
        return '<span class="badge unknown">unknown</span>'

    cards = []
    for it in items:
        cards.append(
        f"""
        <div class="card">
          <div class="row">
            <div class="ts">{html.escape(it["when"])}</div>
            <div class="spacer"></div>
            <div class="badge-wrap">{badge(it["status"])}</div>
          </div>
          <div class="body">
            <div class="name">{html.escape(it["name"])}</div>
            <div class="preview">{html.escape(it["preview"])}</div>
          </div>
          <div class="footer">
            <button class="btn" onclick="openAnswer('{html.escape(it["name"])}')">Open</button>
            <a class="btn ghost" href="/ui/answer/{html.escape(it["name"])}/raw">Raw</a>
            <a class="btn ghost" href="/ui/answer/{html.escape(it["name"])}/download">Download</a>
            <a class="btn ghost" href="/ui/answer/{html.escape(it["name"])}/download.sig">Sig</a>
          </div>
        </div>"""
        )

    body_html = "\n".join(cards) or "<p>No answers found.</p>"

    html_page = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Recent Answers</title>
<style>
  :root { --bg:#0d1020; --panel:#1b2040; --muted:#9aa3b2; --ok:#2ecc71; --bad:#e74c3c; --unk:#888; --acc:#7c4dff; }
  body { background:var(--bg); color:#d9def1; font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,Ubuntu; margin:0; }
  .wrap { max-width:1100px; margin:40px auto; padding:0 16px; }
  h1 { margin:0 0 20px; font-size:22px; letter-spacing:0.2px; }
  .grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(320px, 1fr)); gap:16px; }
  .card { background:var(--panel); border-radius:14px; padding:14px 14px 10px; box-shadow:0 6px 20px rgba(0,0,0,.22); }
  .row { display:flex; align-items:center; gap:8px; }
  .spacer { flex:1; }
  .ts { color:var(--muted); font-size:12px; }
  .name { font-weight:600; margin:10px 0 6px; }
  .preview { color:#c9cfec; font-size:13px; min-height:2lh; white-space:pre-wrap; }
  .footer { display:flex; gap:10px; margin-top:10px; }
  .btn { background:var(--acc); color:white; border:none; padding:8px 12px; border-radius:10px; font-weight:600; cursor:pointer; text-decoration:none; }
  .btn.ghost { background:transparent; border:1px solid #586; color:#d9def1; }
  .badge { padding:4px 8px; border-radius:999px; font-size:12px; font-weight:700; text-transform:lowercase; }
  .badge.ok { background:#1e3f2a; color:#9cffbf; }
  .badge.bad { background:#3f1e1e; color:#ffb0b0; }
  .badge.unknown { background:#2b2b3a; color:#d0d0df; }
  dialog { border:none; border-radius:14px; background:#121429; color:#e2e6ff; width:min(900px, 90vw); }
  .modal-head { display:flex; align-items:center; gap:10px; padding:10px 14px; border-bottom:1px solid #2a2d48; }
  .modal-body { padding:14px; white-space:pre-wrap; font-family:ui-monospace, monospace; font-size:13px; }
  .close { margin-left:auto; }
</style>
</head>
<body>
  <div class="wrap">
    <h1>Recent Answers</h1>
    <div class="grid">{BODY}</div>
  </div>

  <dialog id="mb">
    <div class="modal-head">
      <strong id="mtitle">Answer</strong>
      <button class="btn ghost close" onclick="closeModal()">Close</button>
    </div>
    <div class="modal-body" id="mbody">Loading…</div>
  </dialog>

  <script>
    const mb = document.getElementById('mb');
    const title = document.getElementById('mtitle');
    const bodyEl = document.getElementById('mbody');
    async function openAnswer(name) {
      title.textContent = name;
      bodyEl.textContent = 'Loading…';
      mb.showModal();
      try {
        const r = await fetch('/ui/answer/' + encodeURIComponent(name));
        const text = await r.text();
        bodyEl.textContent = text;
      } catch (err) {
        bodyEl.textContent = 'Failed: ' + err;
      }
    }
    function closeModal() { mb.close(); }
    try {
      const es = new EventSource('/ui/events');
      es.onmessage = () => location.reload();
    } catch (e) {}
    window.addEventListener('keydown', (e) => { if (e.key === 'Escape' && mb.open) mb.close(); });
  </script>
</body>
</html>
"""
    html_page = html_page.replace("{BODY}", body_html)
    return HTMLResponse(html_page)

@router.get("/ui/answer/{name}")
def ui_answer(name: str):
    try:
        ans = _ans_path_from_name(name)
        sig = _sig_path_from_name(name)
    except ValueError:
        raise HTTPException(status_code=400, detail="bad name")
    if not os.path.exists(ans):
        raise HTTPException(status_code=404, detail="not found")
    data = Path(ans).read_text(encoding="utf-8", errors="replace")
    status = _verify_status(ans)
    ts = datetime.fromtimestamp(os.path.getmtime(ans)).isoformat(sep=" ", timespec="seconds")
    size = os.path.getsize(ans)
    sig_exists = os.path.exists(sig)
    fp = _pub_fingerprint()
    meta = (
        f"--- Aletheia Answer ---\n"
        f"file: {os.path.basename(ans)}\n"
        f"time: {ts}\n"
        f"bytes: {size}\n"
        f"signature: {status}{' (present)' if sig_exists else ' (missing)'}\n"
        f"signer key: {fp}\n"
        f"download: /ui/answer/{os.path.basename(ans)}/download | sig: /ui/answer/{os.path.basename(ans)}/download.sig\n"
        f"-----------------------\n\n"
    )
    return PlainTextResponse(meta + data)

@router.get("/ui/answer/{name}/raw")
def ui_answer_raw(name: str):
    try:
        ans = _ans_path_from_name(name)
    except ValueError:
        raise HTTPException(status_code=400, detail="bad name")
    if not os.path.exists(ans):
        raise HTTPException(status_code=404, detail="not found")
    return PlainTextResponse(Path(ans).read_text(encoding="utf-8", errors="replace"))

@router.get("/ui/answer/{name}/download")
def ui_answer_download(name: str):
    try:
        ans = _ans_path_from_name(name)
    except ValueError:
        raise HTTPException(status_code=400, detail="bad name")
    if not os.path.exists(ans):
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(ans, media_type="text/plain; charset=utf-8", filename=os.path.basename(ans))

@router.get("/ui/answer/{name}/download.sig")
def ui_answer_download_sig(name: str):
    try:
        sig = _sig_path_from_name(name)
    except ValueError:
        raise HTTPException(status_code=400, detail="bad name")
    if not os.path.exists(sig):
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(sig, media_type="application/octet-stream", filename=os.path.basename(sig))

@router.get("/ui/events")
def ui_events():
    def gen():
        last = None
        while True:
            try:
                paths = sorted(glob.glob(os.path.join(OUTBOX, "*.answer.txt")), key=os.path.getmtime, reverse=True)
                newest = os.path.basename(paths[0]) if paths else ""
                if newest and newest != last:
                    yield f"data: {newest}\n\n"
                    last = newest
            except Exception:
                pass
            time.sleep(2)
    return StreamingResponse(gen(), media_type="text/event-stream")
