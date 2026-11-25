# -*- coding: utf-8 -*-
import io,sys
sys.path.insert(0,'.')
from av import avatar
from gen import ACTS
ITEMS=[it for _,_,_,items in ACTS for it in items]

band=''.join(f'<span class="cast" style="--k:{i}">{avatar(int(it[0]),mono=True)}</span>'
             for i,it in enumerate(ITEMS))
idx=''.join(
  f'<div class="ix{" hot" if st!="soon" else ""}">'
  f'<div class="ixh"><span class="n">{no}</span><span class="m">{m}</span>'
  + (f'<span class="st st-{st}">{stl}</span>' if st!='soon' else '')
  + f'</div><div class="jp">{jp}</div><div class="en">{en}</div></div>'
  for no,m,jp,en,sub,st,stl in ITEMS)

CSS = """
:root{--paper:#F2EFE9;--accent:#D9AC97;--accent-hi:#F3D4C0;
 --dim:rgba(242,239,233,.6);--faint:rgba(242,239,233,.38);--ghost:rgba(242,239,233,.2);
 --line:rgba(242,239,233,.12);--line2:rgba(242,239,233,.28);
 --d:'Archivo','Noto Sans JP',sans-serif;--b:'Noto Sans JP','Archivo',sans-serif}
*{box-sizing:border-box;margin:0;padding:0}
html,body{background:#060C16}
#poster{width:1080px;height:1350px;padding:52px 48px 38px;position:relative;overflow:hidden;color:var(--paper);
 font-family:var(--b);display:flex;flex-direction:column;
 background:radial-gradient(116% 68% at 76% -6%,#2D3D64 0%,#16223C 42%,#09111E 100%)}
#poster::after{content:"";position:absolute;inset:0;opacity:.38;pointer-events:none;
 background-image:radial-gradient(rgba(242,239,233,.1) 1px,transparent 1px);background-size:32px 32px}
#poster>*{position:relative;z-index:1}
.hd{display:flex;align-items:center;gap:16px;margin-bottom:26px}
.hd .lg{font-family:var(--d);font-style:italic;font-weight:900;font-size:24px;letter-spacing:-.055em;display:flex;align-items:center;gap:6px}
.hd .lg i{width:7px;height:7px;background:var(--accent);display:block}
.hd .r{flex:1;height:1px;background:var(--line2)}
.hd .tag{font-family:var(--d);font-weight:600;font-size:12px;letter-spacing:.26em;color:var(--faint)}
h1{font-family:var(--d);font-style:italic;font-weight:900;font-size:124px;line-height:.82;letter-spacing:-.072em}
h1 em{font-style:italic;color:var(--accent)}
.meta{display:flex;align-items:baseline;gap:24px;margin-top:16px}
.meta b{font-weight:900;font-size:21px;letter-spacing:-.04em}
.meta span{font-family:var(--d);font-weight:600;font-size:12.5px;letter-spacing:.22em;color:var(--faint)}

/* cast band — one overlapping row, uniform duotone */
.band{display:flex;justify-content:center;margin:40px 0 6px;padding-left:28px}
.cast{width:128px;height:128px;border-radius:50%;overflow:hidden;display:block;margin-left:-28px;flex:none;
 transform:translateY(calc((var(--k) % 2) * 13px));
 box-shadow:0 10px 26px rgba(6,12,22,.5),0 0 0 3px #16223C}
.cast svg{width:100%;height:100%;display:block}
.bcap{text-align:center;font-family:var(--d);font-weight:700;font-size:11px;letter-spacing:.3em;color:var(--faint);
 margin-top:22px;padding-bottom:22px;border-bottom:1px solid var(--line2)}

/* typographic index */
.idx{display:grid;grid-template-columns:repeat(3,1fr);gap:0;flex:1;align-content:space-evenly}
.ix{padding:16px 20px 16px 0;border-bottom:1px solid var(--line);min-width:0}
.ixh{display:flex;align-items:baseline;gap:10px;margin-bottom:8px}
.ixh .n{font-family:var(--d);font-style:italic;font-weight:900;font-size:20px;letter-spacing:-.05em;color:var(--accent)}
.ixh .m{font-family:var(--d);font-weight:600;font-size:12px;letter-spacing:.14em;color:var(--faint)}
.ix .jp{font-weight:900;font-size:27px;letter-spacing:-.05em;line-height:1.2}
.ix .en{font-family:var(--d);font-weight:600;font-size:9px;letter-spacing:.17em;color:var(--faint);margin-top:7px}
.ix.hot .jp{color:var(--accent-hi)}
.st{font-family:var(--d);font-weight:700;font-size:8.5px;letter-spacing:.1em;padding:3px 7px;border-radius:2px;white-space:nowrap}
.st-ok{background:var(--accent);color:#14203A}
.st-free{background:var(--paper);color:#14203A}

.exp{display:flex;align-items:center;justify-content:space-between;gap:20px;padding:18px 24px;margin-top:18px;
 border:1px solid rgba(217,172,151,.5);border-radius:3px;
 background:linear-gradient(100deg,rgba(217,172,151,.24),rgba(217,172,151,.05) 52%,transparent 90%)}
.exp .k{font-family:var(--d);font-weight:800;font-size:10px;letter-spacing:.28em;color:var(--accent);display:block;margin-bottom:7px}
.exp .t{font-family:var(--d);font-style:italic;font-weight:900;font-size:36px;letter-spacing:-.06em;line-height:1;color:var(--accent-hi)}
.exp .s{font-size:11.5px;color:var(--dim);margin-top:8px;display:block}
.exp .r{text-align:right;flex:none}
.exp .r .d{font-family:var(--d);font-style:italic;font-weight:900;font-size:36px;letter-spacing:-.06em;line-height:1;display:block}
.exp .r .d i{font-style:normal;color:var(--accent)}
.exp .r .n{font-size:10.5px;color:var(--faint);margin-top:7px;display:block}
.ft{margin-top:16px;padding-top:15px;border-top:1px solid var(--line2);display:flex;align-items:flex-end;justify-content:space-between;gap:18px}
.ft b{display:block;font-weight:900;font-size:18px;letter-spacing:-.045em;margin-bottom:4px}
.ft .l span{font-size:11px;color:var(--faint)}
.ft .r{text-align:right;font-family:var(--d);font-weight:700;font-size:13px;letter-spacing:.12em;color:var(--accent)}
.ft .r small{display:block;font-size:10px;letter-spacing:.08em;color:var(--faint);margin-top:4px;font-weight:600}
"""
io.open('allhands.html','w',encoding='utf-8').write(f'''<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:ital,wght@0,600;0,700;0,800;1,800;1,900&family=Noto+Sans+JP:wght@400;500;700;900&display=swap">
<style>{CSS}</style></head><body>
<div id="poster">
  <div class="hd"><span class="lg">WING<i></i></span><span class="r"></span><span class="tag">歯科衛生士 2.0</span></div>
  <h1>SEASON<em>01</em></h1>
  <div class="meta"><b>12 SESSIONS ＋ 1 EXPEDITION</b><span>2027.1 — 2028.1</span></div>
  <div class="band">{band}</div>
  <div class="bcap">T W E L V E &nbsp; G U E S T S</div>
  <div class="idx">{idx}</div>
  <div class="exp"><div><span class="k">★ EXPEDITION</span>
    <span class="t">SCANDINAVIAN APPROACH</span>
    <span class="s">予防歯科の本場スウェーデンで学ぶ、現地研修プログラム／第1期・少人数制</span></div>
    <div class="r"><span class="d">2027<i>.</i>6</span><span class="n">会員は5万円割引＋先行申込</span></div></div>
  <div class="ft"><div class="l"><b>第1期メンバー 100名限定</b>
    <span>毎月1回・90分｜講義 → 対談 → ワーク／班（Pod）での持ち寄り</span></div>
    <div class="r">@wing_dh<small>詳細は LINE にて先行案内</small></div></div>
</div></body></html>''')
print('built')
