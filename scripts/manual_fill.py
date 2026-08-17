#!/usr/bin/env python3
"""OCRで読み切れなかったぶんを、券面を見ながら手で埋める／なおすための道具。

    npm run manual        → ブラウザがひらく（8099。ふさがっていたら次の番号）

画面は2つ。
  うめる … 足りないところを順に聞いてくる
  なおす … 番号や名前で探して、どのピックでも直せる

入れた値は scripts/raw/manual.json に貯まり、parse_official.py が
**いちばん最後に**当てる（人が見て入れたものが最優先）。
npm run update を回しても消えない。

券面にそもそも印字が無いもの（スペシャルの★、ステータス欄の無いプロモ）は
「うめる」には出さない。
"""

import errno
import json
import re
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parent
PICKS = ROOT.parent / "src" / "data" / "picks.json"
IMAGES = ROOT / "raw" / "pick_images"
MANUAL = ROOT / "raw" / "manual.json"
OCR_MOVES = ROOT / "raw" / "ocr_moves.json"
OCR_SPECIAL = ROOT / "raw" / "ocr_special.json"
TYPES_TS = ROOT.parent / "src" / "theme" / "pokemonTypes.ts"
ICONS_PY = ROOT / "ocr" / "export_type_icons.py"
ICONS = ROOT.parent / "assets" / "types"

PORT = 8099

# 読みたい場所だけを拡大して出す。全体を目で追うより速い。
# 座標は OCR 側と同じものを使う（scripts/ocr/header_ocr.py, extra_ocr.py）
CROP_ZOOM = 3
ENERGY_WIN = (325, 490, 510, 630)  # extra_ocr.ENERGY_WIN と同じ


def crop_png(pick_id: str, what: str) -> bytes | None:
    """わざの行／ポケエネの欄だけを切り出して、拡大したPNGを返す"""
    import sys

    sys.path.insert(0, str(ROOT / "ocr"))
    from io import BytesIO

    from PIL import Image

    import header_ocr as H

    f = IMAGES / f"{pick_id}.webp"
    if not f.exists():
        return None
    img = Image.open(f).convert("RGB")

    if what == "energy":
        box = ENERGY_WIN
    else:
        anchor = H.find_anchor(img)
        if anchor is None:
            return None
        ax, ay, sc = anchor
        # わざの行。タイプのマークも入るよう、アイコンの左はしから取る。
        # 2行目は1行目とおなじ幾何のまま70pxだけ下（scripts/ocr の読み取りと同じ）
        shift = 70 if what == "move2" else 0
        left = ax + round(H.MOVE_ORIGIN[0] * sc)
        top = ay + round((H.MOVE_ORIGIN[1] - 4 + shift) * sc)
        box = (left, top, left + round(390 * sc), top + round(60 * sc))

    crop = img.crop(box)
    crop = crop.resize((crop.width * CROP_ZOOM, crop.height * CROP_ZOOM), Image.LANCZOS)
    buf = BytesIO()
    crop.save(buf, "PNG")
    return buf.getvalue()


def types_with_icons() -> list[dict]:
    """タイプの一覧と、券面のマーク画像のファイル名。どちらも既存の定義から読む（二重管理しない）"""
    colors = re.search(
        r"TYPE_COLORS[^=]*=\s*\{(.*?)\n\}", TYPES_TS.read_text(encoding="utf-8"), re.S
    ).group(1)
    order = re.findall(r"^\s*([^\s:]+):", colors, re.M)
    table = re.search(r"ROMAJI\s*=\s*\{(.*?)\n\}", ICONS_PY.read_text(encoding="utf-8"), re.S).group(1)
    romaji = dict(re.findall(r'"([^"]+)":\s*"([a-z]+)"', table))
    return [{"ja": t, "icon": romaji.get(t, "")} for t in order]


def load_manual() -> dict:
    return json.loads(MANUAL.read_text(encoding="utf-8")) if MANUAL.exists() else {}


def load_picks() -> list[dict]:
    return json.loads(PICKS.read_text(encoding="utf-8"))


def current(p: dict, got: dict) -> dict:
    """いま入っている値（手入力があればそれ）を、フォームに出せる形で返す"""
    move = p["moves"][0] if p["moves"] else {}
    return {
        "moveName": got.get("moveName", move.get("name") or ""),
        "moveType": got.get("moveType", move.get("type") or ""),
        "energy": got.get("energy", (p["stats"] or {}).get("energy") or ""),
        "grade": got.get("grade", p["grade"] if p["grade"] is not None else ""),
        "specialMove": got.get("specialMove", p.get("specialMove") or ""),
    }


def build_todo() -> list[dict]:
    """埋められる穴だけを、だんの順に並べて返す"""
    manual = load_manual()
    # 1行目が「メガ○○ にメガシンカ！」でわざではないものは、2行目に本当のわざがある。
    # そちらは機械で読む方向で進めているので、手入力の対象からは外す。
    reasons = (
        {r["id"]: r.get("reason") for r in json.loads(OCR_MOVES.read_text(encoding="utf-8"))}
        if OCR_MOVES.exists()
        else {}
    )
    # メガシンカのピックは1行目が「メガ○○ にメガシンカ！」で、わざは2行目にある。
    # 拡大して見せる場所も2行目にしないと、まちがった行を見ることになる
    mechanics = (
        {r["id"]: r.get("mechanic") for r in json.loads(OCR_SPECIAL.read_text(encoding="utf-8"))}
        if OCR_SPECIAL.exists()
        else {}
    )

    todo = []
    for p in load_picks():
        got = manual.get(p["id"], {})
        need = []
        # ステータス欄が無いプロモでも、わざの行はある（例: p120 の「１０まんボルト」）
        mega = reasons.get(p["id"]) == "no_text"
        if not p["moves"] and not mega and "moveName" not in got:
            need.append("moveName")
        if not p["moves"] and not mega and "moveType" not in got:
            need.append("moveType")
        elif p["moves"] and p["moves"][0]["type"] is None and "moveType" not in got:
            need.append("moveType")
        # ポケエネはステータスのブロックに入るので、ブロックごと無いピックには入れられない
        if p["stats"] is not None and p["stats"]["energy"] is None and "energy" not in got:
            need.append("energy")
        # 仕組みが付いているのに とくべつなわざ が読めていないもの
        if p["mechanic"] and not p["specialMove"] and "specialMove" not in got:
            need.append("specialMove")
        if need:
            todo.append({
                "id": p["id"], "name": p["name"], "setLabel": p["setLabel"],
                "need": need, "values": current(p, got),
                "row": 2 if mechanics.get(p["id"]) == "メガシンカ" else 1,
                "mechanic": p["mechanic"],
            })
    return todo


def search(q: str) -> list[dict]:
    """番号 か 名前 で探す"""
    manual = load_manual()
    key = q.strip().upper().replace("-", "")
    out = []
    for p in load_picks():
        if q and (q in p["name"] or (key and key in p["id"].upper().replace("-", ""))):
            out.append({
                "id": p["id"], "name": p["name"], "setLabel": p["setLabel"],
                "edited": p["id"] in manual, "mechanic": p["mechanic"],
                "row": 2 if p["mechanic"] == "メガシンカ" else 1,
                "values": current(p, manual.get(p["id"], {})),
            })
        if len(out) >= 60:
            break
    return out


PAGE = """<!doctype html>
<meta charset="utf-8"><title>ピックデータ 補完ツール</title>
<style>
 body{font-family:-apple-system,sans-serif;margin:0;background:#f2f6fb;color:#1a365d}
 header{background:#2b6cb0;color:#fff;padding:8px 16px;display:flex;gap:10px;align-items:center;position:sticky;top:0;z-index:9}
 header b{font-size:17px;margin-right:8px}
 .tab{background:rgba(255,255,255,.15);color:#fff;border:0;padding:9px 18px;border-radius:16px;font-size:14px;font-weight:700;cursor:pointer}
 .tab.on{background:#fff;color:#2b6cb0}
 .prog{margin-left:auto;opacity:.9;font-size:13px}
 main{display:flex;gap:16px;padding:16px;align-items:flex-start}
 .card{background:#fff;border-radius:12px;padding:16px;box-shadow:0 2px 6px rgba(26,54,93,.08)}
 /* 券面は1枚に おもて／うら が上下でならんでいる（1016x1500）。
    750/1016 = 73.82% ぶんずらすと ちょうど半分になる */
 .half{width:580px;max-width:46vw;aspect-ratio:1016/750;overflow:hidden;border-radius:8px;background:#fff}
 .half img{width:100%;display:block}
 .back img{margin-top:-73.82%}
 .front{width:310px;max-width:25vw}
 .cap{font-size:12px;font-weight:700;color:#7c8da3;margin:10px 0 4px}
 .zoom{width:580px;max-width:46vw;display:block;border-radius:8px;border:1px solid #e2e8f0}
 .form{min-width:380px;flex:1}
 h2{margin:0 0 4px;font-size:20px} .sub{color:#7c8da3;font-size:13px;margin-bottom:14px}
 label{display:block;font-size:12px;font-weight:700;color:#5a6c82;margin:14px 0 6px}
 input{width:100%;font-size:17px;padding:10px;border:2px solid #d6dee8;border-radius:8px;box-sizing:border-box}
 input:focus{outline:none;border-color:#2b6cb0}
 /* 券面にはマークしか出ないので、マークを見ながら選べるようにする */
 .types{display:grid;grid-template-columns:repeat(6,1fr);gap:6px}
 .ty{display:flex;flex-direction:column;align-items:center;gap:2px;padding:6px 2px;border:2px solid #e2e8f0;border-radius:10px;background:#fff;cursor:pointer}
 .ty img{width:30px;height:30px}
 .ty span{font-size:10px;font-weight:700;color:#5a6c82}
 .ty.on{border-color:#2b6cb0;background:#eaf2fb}
 .ty.none{justify-content:center;font-size:11px;color:#7c8da3}
 .row{display:flex;gap:8px;margin-top:18px}
 button.act{flex:1;font-size:15px;font-weight:700;padding:12px;border:0;border-radius:10px;cursor:pointer}
 .save{background:#2f855a;color:#fff} .skip{background:#e2e8f0;color:#1a365d}
 .done{padding:40px;text-align:center;font-size:18px}
 .hint{font-size:12px;color:#7c8da3;margin-top:10px;line-height:1.6}
 .hit{display:flex;gap:10px;align-items:center;padding:9px 10px;border-radius:8px;cursor:pointer}
 .hit:hover{background:#f2f6fb}
 .hit .id{font-size:11px;color:#9aa8b8;min-width:92px}
 .hit .ed{font-size:10px;color:#2f855a;font-weight:800}
 .ok{color:#2f855a;font-weight:700;font-size:13px;margin-top:10px}
</style>
<header>
  <b>ピックデータ 補完</b>
  <button class="tab on" id="t1" onclick="mode('fill')">未入力を埋める</button>
  <button class="tab" id="t2" onclick="mode('edit')">検索して修正</button>
  <span class="prog" id="prog"></span>
</header>
<main id="app"></main>
<script>
let todo=[],types=[],i=0,view='fill',target=null,msg='';
const $=s=>document.querySelector(s);
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

async function boot(){
  const r=await (await fetch('/api/todo')).json();
  todo=r.todo; types=r.types; render();
}
function mode(v){
  view=v; target=null; msg='';
  $('#t1').className='tab'+(v==='fill'?' on':'');
  $('#t2').className='tab'+(v==='edit'?' on':'');
  render();
}

function typePicker(sel){
  const cell=t=>`<div class="ty${sel===t.ja?' on':''}" onclick="pickType('${t.ja}')">
    <img src="/type/${t.icon}.png" alt="${t.ja}"><span>${t.ja}</span></div>`;
  return `<label>わざタイプ（裏面のマークと照合）</label>
    <div class="types">${types.map(cell).join('')}
      <div class="ty none${sel===''?' on':''}" onclick="pickType('')">指定なし</div></div>`;
}
function pickType(t){ (view==='edit'?target:todo[i]).values.moveType=t; keep(); render(); }

// 描き直す前に、いま入力欄に打ってあるものを持ち越す
function keep(){
  const t = view==='edit'?target:todo[i]; if(!t) return;
  for(const k of ['moveName','energy','grade','specialMove']){
    const el=document.getElementById(k); if(el) t.values[k]=el.value;
  }
}

// 読みたい場所を拡大したものを上に出す。全体は下に置いて、必要なときだけ見る
function cardHtml(id, fields, row){
  const z=[];
  if(fields.includes('specialMove'))
    z.push(`<div class="cap">わざ 2行目（拡大）　※とくべつなわざ</div>
      <img class="zoom" src="/crop/${encodeURIComponent(id)}/move2.png">`);
  if(fields.includes('moveName')||fields.includes('moveType')){
    const n = row===2 ? 2 : 1;
    z.push(`<div class="cap">わざ ${n}行目（拡大）${n===2?'　※1行目はメガシンカ表記のため2行目が実際のわざ':''}</div>
      <img class="zoom" src="/crop/${encodeURIComponent(id)}/move${n===2?'2':''}.png">`);
  }
  if(fields.includes('energy'))
    z.push(`<div class="cap">ポケエネ（拡大）</div>
      <img class="zoom" src="/crop/${encodeURIComponent(id)}/energy.png">`);
  return `<div class="card">
    ${z.join('')}
    <div class="cap">裏面</div>
    <div class="half back"><img src="/img/${encodeURIComponent(id)}"></div>
    <div class="cap">表面</div>
    <div class="half front"><img src="/img/${encodeURIComponent(id)}"></div>
  </div>`;
}
function formHtml(t, fields, buttons){
  const v=t.values, f=[];
  if(fields.includes('moveName'))
    f.push(`<label>わざ名（裏面 1行目）</label>
      <input id="moveName" value="${esc(v.moveName)}" placeholder="例: かえんほうしゃ">`);
  if(fields.includes('moveType')) f.push(typePicker(v.moveType));
  if(fields.includes('energy'))
    f.push(`<label>ポケエネ（表面 左下）</label>
      <input id="energy" inputmode="numeric" value="${esc(v.energy)}" placeholder="例: 244">`);
  if(fields.includes('specialMove'))
    f.push(`<label>とくべつなわざ（裏面 2行目。${esc(t.mechanic||'仕組み')}）</label>
      <input id="specialMove" value="${esc(v.specialMove)}" placeholder="例: テラバースト">`);
  if(fields.includes('grade'))
    f.push(`<label>★の数</label><input id="grade" inputmode="numeric" value="${esc(v.grade)}" placeholder="1〜5">`);
  return `<div class="card form"><h2>${esc(t.name)}</h2>
    <div class="sub">${esc(t.setLabel)}　${esc(t.id)}</div>
    ${f.join('')}<div class="row">${buttons}</div>
    <div class="hint">Enter で保存（IME変換確定のEnterでは保存しません）。<br>
    空欄で保存すると手動入力を取り消し、OCRの読み取り結果に戻します。</div>
    ${msg?`<div class="ok">${esc(msg)}</div>`:''}</div>`;
}

function render(){
  if(view==='edit') return renderEdit();
  $('#prog').textContent = todo.length? `${Math.min(i+1,todo.length)} / ${todo.length}　（残り ${Math.max(todo.length-i,0)}件）` : '';
  if(i>=todo.length){
    $('#app').innerHTML='<div class="card done">未入力はありません。<br>ターミナルで <b>npm run build:data</b> を実行してください。</div>';
    return;
  }
  const t=todo[i];
  $('#app').innerHTML = cardHtml(t.id, t.need, t.row) + formHtml(t, t.need,
    `<button class="act save" onclick="save()">保存して次へ</button>
     <button class="act skip" onclick="i++;msg='';render()">スキップ</button>`);
  const el=$('#app input'); if(el) el.focus();
}

function renderEdit(){
  $('#prog').textContent='';
  if(!target){
    $('#app').innerHTML=`<div class="card form">
      <label>ピック番号 または ポケモン名で検索</label>
      <input id="q" placeholder="例: 1-1-026 / ニャオハ" oninput="doSearch(this.value)">
      <div id="hits"></div></div>`;
    const el=$('#q'); if(el) el.focus();
    return;
  }
  $('#app').innerHTML = cardHtml(target.id, ['moveName','moveType','specialMove','energy','grade'], target.row) + formHtml(target, ['moveName','moveType','specialMove','energy','grade'],
    `<button class="act save" onclick="save()">保存</button>
     <button class="act skip" onclick="target=null;msg='';render()">別のピックを検索</button>`);
}

let timer=null;
function doSearch(q){
  clearTimeout(timer);
  timer=setTimeout(async()=>{
    if(!q.trim()){ $('#hits').innerHTML=''; return; }
    const r=await (await fetch('/api/search?q='+encodeURIComponent(q))).json();
    window._hits=r;
    $('#hits').innerHTML = r.length? r.map((x,n)=>
      `<div class="hit" onclick="open_(${n})"><span class="id">${esc(x.id)}</span>
       <b>${esc(x.name)}</b><span class="id">${esc(x.setLabel)}</span>
       ${x.edited?'<span class="ed">手動修正済</span>':''}</div>`).join('')
      : '<div class="hint">該当なし</div>';
  },200);
}
function open_(n){ target=window._hits[n]; msg=''; render(); }

async function save(){
  const t = view==='edit' ? target : todo[i];
  const fields = view==='edit' ? ['moveName','moveType','specialMove','energy','grade'] : t.need;
  keep();
  const v={};
  for(const k of fields) v[k] = t.values[k]===undefined ? '' : String(t.values[k]);
  await fetch('/api/save',{method:'POST',body:JSON.stringify({id:t.id,values:v})});
  if(view==='edit'){
    msg='保存しました';
    target = await (await fetch('/api/pick/'+encodeURIComponent(t.id))).json();
    render();
  } else { i++; msg=''; render(); }
}

addEventListener('keydown',e=>{
  if(e.key!=='Enter') return;
  // かな漢字変換の かくてい も Enter なので、変換中は保存しない。
  // keyCode 229 は Safari が composing 中に返すもの
  if(e.isComposing||e.keyCode===229) return;
  if(view==='edit'&&!target) return;
  e.preventDefault(); save();
});
boot();
</script>
"""


class Server(HTTPServer):
    # 止めた直後に立ち上げ直しても TIME_WAIT でつまずかないように
    allow_reuse_address = True


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # うるさいので黙らせる
        pass

    def send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def json_out(self, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send(200, body, "application/json; charset=utf-8")

    def send_file(self, path: Path, ctype: str):
        if path.exists():
            self.send(200, path.read_bytes(), ctype)
        else:
            self.send(404, b"", "text/plain")

    def do_GET(self):
        u = urlparse(self.path)
        path = u.path
        if path == "/":
            self.send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        elif path == "/api/todo":
            self.json_out({"todo": build_todo(), "types": types_with_icons()})
        elif path == "/api/search":
            self.json_out(search(parse_qs(u.query).get("q", [""])[0]))
        elif path.startswith("/api/pick/"):
            pid = unquote(path[len("/api/pick/"):])
            p = next((x for x in load_picks() if x["id"] == pid), None)
            if p is None:
                self.send(404, b"{}", "application/json")
                return
            manual = load_manual()
            self.json_out({
                "id": p["id"], "name": p["name"], "setLabel": p["setLabel"],
                "edited": p["id"] in manual, "mechanic": p["mechanic"],
                "row": 2 if p["mechanic"] == "メガシンカ" else 1,
                "values": current(p, manual.get(p["id"], {})),
            })
        elif path.startswith("/type/"):
            self.send_file(ICONS / unquote(path[len("/type/"):]), "image/png")
        elif path.startswith("/img/"):
            self.send_file(IMAGES / f"{unquote(path[5:])}.webp", "image/webp")
        elif path.startswith("/crop/"):
            pick_id, what = unquote(path[len("/crop/"):]).rsplit("/", 1)
            body = crop_png(pick_id, what.removesuffix(".png"))
            self.send(200, body, "image/png") if body else self.send(404, b"", "text/plain")
        else:
            self.send(404, b"", "text/plain")

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        manual = load_manual()
        entry = manual.get(req["id"], {})
        for k, v in req["values"].items():
            # からっぽで送られてきたら、手入力をやめる（もとの読み取り結果にもどす）
            if str(v).strip() == "":
                entry.pop(k, None)
            else:
                entry[k] = str(v).strip()
        if entry:
            manual[req["id"]] = entry
        else:
            manual.pop(req["id"], None)
        MANUAL.write_text(
            json.dumps(dict(sorted(manual.items())), ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
        )
        print(f"  {req['id']}: {entry or '手動入力を削除'}", flush=True)
        self.send(200, b"{}", "application/json")


def main() -> None:
    todo = build_todo()
    # まえのが残っていることがあるので、ふさがっていたら次の番号にずらす
    server = None
    for port in range(PORT, PORT + 10):
        try:
            server = Server(("127.0.0.1", port), Handler)
            break
        except OSError as e:
            if e.errno != errno.EADDRINUSE:
                raise
            print(f"  :{port} は使用中のため次のポートを試行", flush=True)
    if server is None:
        raise SystemExit(f"{PORT}〜{PORT + 9} が全部ふさがっている。`pkill -f manual_fill.py` を試すこと")

    url = f"http://127.0.0.1:{server.server_address[1]}"
    print(f"未入力 残り {len(todo)}件 → {url}", flush=True)
    print("「検索して修正」タブから任意のピックを修正できます", flush=True)
    print("終了後は Ctrl-C で停止し、npm run build:data を実行すること", flush=True)
    webbrowser.open(url)
    server.serve_forever()


if __name__ == "__main__":
    main()
