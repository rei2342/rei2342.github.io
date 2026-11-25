# -*- coding: utf-8 -*-
import io,sys
sys.path.insert(0,'.')
from av import avatar
from gen import ACTS  # reuse data
arc = io.open('arc.svg',encoding='utf-8').read().replace('class="arc"','class="arcg"')

CSS = """
:root{--ink:#0A1220;--navy:#141F37;--navy2:#1B2946;--paper:#F2EFE9;--accent:#D9AC97;--accent-hi:#F3D4C0;
 --dim:rgba(242,239,233,.64);--faint:rgba(242,239,233,.4);--ghost:rgba(242,239,233,.17);
 --line:rgba(242,239,233,.12);--line2:rgba(242,239,233,.3);
 --d:'Archivo','Noto Sans JP',sans-serif;--b:'Noto Sans JP','Archivo',sans-serif}
*{box-sizing:border-box;margin:0;padding:0}
html,body{background:#060C16}
.slide{width:1080px;height:1350px;padding:64px 62px 54px;position:relative;overflow:hidden;color:var(--paper);
 font-family:var(--b);display:flex;flex-direction:column;
 background:radial-gradient(118% 72% at 80% -8%,#2B3B60 0%,#16223C 44%,#0A1220 100%)}
.slide::after{content:"";position:absolute;inset:0;opacity:.4;pointer-events:none;
 background-image:radial-gradient(rgba(242,239,233,.1) 1px,transparent 1px);background-size:32px 32px}
.slide>*{position:relative;z-index:1}
.hd{display:flex;align-items:center;gap:18px;margin-bottom:40px}
.hd .lg{font-family:var(--d);font-style:italic;font-weight:900;font-size:27px;letter-spacing:-.055em;display:flex;align-items:center;gap:7px}
.hd .lg i{width:7px;height:7px;background:var(--accent);display:block}
.hd .r{flex:1;height:1px;background:var(--line2)}
.hd .t{font-family:var(--d);font-weight:600;font-size:13px;letter-spacing:.26em;color:var(--faint)}
.ft{margin-top:auto;padding-top:26px;border-top:1px solid var(--line2);display:flex;align-items:flex-end;justify-content:space-between;gap:20px}
.ft .pg{font-family:var(--d);font-weight:700;font-size:14px;letter-spacing:.18em;color:var(--faint)}
.ft .ig{font-family:var(--d);font-weight:700;font-size:16px;letter-spacing:.14em;color:var(--accent)}
.ft .sw{font-size:13px;color:var(--faint);letter-spacing:.04em}

/* act */
.actn{font-family:var(--d);font-style:italic;font-weight:900;font-size:40px;letter-spacing:-.055em;color:var(--accent);line-height:1}
.actt{font-weight:900;font-size:66px;letter-spacing:-.055em;line-height:1.08;margin:12px 0 14px}
.actnote{font-size:17px;color:var(--dim);line-height:1.8}
.rowsx{margin-top:34px;border-top:1px solid var(--line2);display:flex;flex-direction:column;flex:1;justify-content:space-evenly}
.rx{display:grid;grid-template-columns:172px minmax(0,1fr) auto;gap:38px;align-items:center;
 padding:26px 0;border-bottom:1px solid var(--line);flex:1}
.rx .pf{width:172px;height:172px;border-radius:50%;overflow:hidden;box-shadow:0 8px 28px rgba(0,0,0,.35)}
.rx .pf svg{width:100%;height:100%;display:block}
.rx .mo{font-family:var(--d);font-weight:700;font-size:15px;letter-spacing:.18em;color:var(--accent);margin-bottom:9px}
.rx .jp{font-weight:900;font-size:52px;letter-spacing:-.05em;line-height:1.16}
.rx .en{font-family:var(--d);font-weight:600;font-size:13.5px;letter-spacing:.2em;color:var(--faint);margin-top:9px}
.rx .ds{font-size:18px;color:var(--dim);margin-top:13px;line-height:1.65}
.rx .rt{display:flex;flex-direction:column;align-items:flex-end;gap:18px}
.rx .no{font-family:var(--d);font-style:italic;font-weight:900;font-size:70px;line-height:1;letter-spacing:-.06em;
 -webkit-text-stroke:1.8px var(--ghost);color:transparent}
.st{font-family:var(--d);font-weight:700;font-size:13px;letter-spacing:.14em;padding:7px 14px;border-radius:2px;white-space:nowrap}
.st-ok{background:var(--accent);color:#14203A}
.st-soon{border:1.5px solid var(--line2);color:var(--faint)}
.st-free{background:var(--paper);color:#14203A}

/* cover */
.cv{justify-content:center}
.cv .season{font-family:var(--d);font-style:italic;font-weight:900;font-size:168px;line-height:.8;letter-spacing:-.07em;display:block}
.cv .season em{display:block;font-size:232px;line-height:.8;margin-top:-6px}
.cv .season em{font-style:italic;color:var(--accent)}
.cv .sub{font-weight:900;font-size:36px;letter-spacing:-.045em;margin-top:34px}
.cv .per{font-family:var(--d);font-weight:600;font-size:19px;letter-spacing:.24em;color:var(--faint);margin-top:16px}
.arcg{width:100%;height:auto;display:block;margin-top:54px;opacity:.95}
.cv .body{margin:auto 0}

/* expedition */
.xp{background:radial-gradient(108% 70% at 22% 8%,#4A3B38 0%,#26304C 40%,#0B1220 100%)}
.xp .k{font-family:var(--d);font-weight:800;font-size:17px;letter-spacing:.32em;color:var(--accent);margin-bottom:34px}
.xp .xt{font-family:var(--d);font-style:italic;font-weight:900;font-size:122px;line-height:.9;letter-spacing:-.065em;color:var(--accent-hi)}
.xp .jp{font-weight:900;font-size:50px;letter-spacing:-.05em;line-height:1.4;margin-top:44px}
.xp .d{font-family:var(--d);font-style:italic;font-weight:900;font-size:96px;letter-spacing:-.065em;line-height:1;margin-top:40px}
.xp .d i{font-style:normal;color:var(--accent)}
.xp .n{font-size:19px;color:var(--dim);margin-top:24px;line-height:1.8}
.xp .pill{display:inline-block;margin-top:30px;border:1.5px solid rgba(217,172,151,.6);color:var(--accent-hi);
 font-family:var(--d);font-weight:700;font-size:15px;letter-spacing:.16em;padding:11px 20px;border-radius:2px}

/* cta */
.ct .big{font-weight:900;font-size:86px;letter-spacing:-.06em;line-height:1.14}
.ct .big em{font-style:normal;color:var(--accent)}
.ct .lead{font-size:23px;color:var(--dim);line-height:1.95;margin-top:34px;max-width:38ch}
.ct .box{margin-top:46px;border:1.5px solid var(--line2);border-radius:3px;padding:36px 38px;
 background:linear-gradient(100deg,rgba(242,239,233,.07),transparent 72%)}
.ct .box b{display:block;font-weight:900;font-size:40px;letter-spacing:-.05em;margin-bottom:14px}
.ct .box span{font-size:18px;color:var(--dim)}
.ct .hand{margin-top:38px;font-family:var(--d);font-weight:900;font-size:30px;letter-spacing:.06em;color:var(--accent)}
"""

def hd(t="歯科衛生士 2.0"):
    return f'<div class="hd"><span class="lg">WING<i></i></span><span class="r"></span><span class="t">{t}</span></div>'
def ft(n,total=7,sw="SEASON 01｜2027.1 — 2028.1"):
    return (f'<div class="ft"><span class="sw">{sw}</span>'
            f'<span class="pg">{n} / {total}</span><span class="ig">@wing_dh</span></div>')

def act_slide(idx,n,title,note,items):
    rows=''.join(
      f'<div class="rx"><span class="pf">{avatar(int(no))}</span>'
      f'<div><div class="mo">{m}</div><div class="jp">{jp}</div><div class="en">{en}</div><div class="ds">{sub}</div></div>'
      f'<div class="rt"><span class="no">{no}</span><span class="st st-{st}">{stl}</span></div></div>'
      for no,m,jp,en,sub,st,stl in items)
    return (f'<div class="slide" id="s{idx}">{hd()}'
            f'<div><span class="actn">ACT {n}</span><div class="actt">{title}</div>'
            f'<div class="actnote">{note}</div></div>'
            f'<div class="rowsx">{rows}</div>{ft(idx)}</div>')

S=[]
# 1 cover
S.append(f'''<div class="slide cv" id="s1">{hd()}
<div class="body"><h1 class="season">SEASON<em>01</em></h1>
<div class="sub">12 SESSIONS ＋ 1 EXPEDITION</div>
<div class="per">2027.1 — 2028.1</div>
{arc}</div>{ft(1)}</div>''')
# 2,3 acts I,II
S.append(act_slide(2,*ACTS[0]))
S.append(act_slide(3,*ACTS[1]))
# 4 expedition
S.append(f'''<div class="slide xp" id="s4">{hd()}
<div style="margin:auto 0"><div class="k">★ EXPEDITION</div>
<div class="xt">SCANDINAVIAN<br>APPROACH</div>
<div class="jp">予防歯科の本場で、<br>現地のDHを見る。</div>
<div class="d">2027<i>.</i>6</div>
<div class="n">スウェーデン現地研修プログラム／第1期・少人数制<br>全行程に通訳が入ります</div>
<span class="pill">WING CLUB 会員は 5万円割引 ＋ 先行申込</span></div>{ft(4)}</div>''')
# 5,6 acts III,IV
S.append(act_slide(5,*ACTS[2]))
S.append(act_slide(6,*ACTS[3]))
# 7 cta
S.append(f'''<div class="slide ct" id="s7">{hd()}
<div style="margin:auto 0"><div class="big">一歩を、<br><em>外に出す。</em></div>
<div class="lead">毎月1回・90分。ゲスト講師の講義で終わらせず、その場でワークまでやる。学んだことを班で報告し合い、年に一度は世界を見に行く。</div>
<div class="box"><b>第1期メンバー 100名限定</b>
<span>講義 → 対談 → ワーク／班（Pod）での持ち寄り<br>月額 2,980円（Founding Member 価格）</span></div>
<div class="hand">＠wing_dh をフォロー</div></div>{ft(7)}</div>''')

io.open('carousel.html','w',encoding='utf-8').write(
f'''<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:ital,wght@0,600;0,700;0,800;1,800;1,900&family=Noto+Sans+JP:wght@400;500;700;900&display=swap">
<style>{CSS}</style></head><body>{''.join(S)}</body></html>''')
print('carousel html built', len(S),'slides')
