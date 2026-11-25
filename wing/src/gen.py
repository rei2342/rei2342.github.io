# -*- coding: utf-8 -*-
import io,sys
sys.path.insert(0,'.')
from av import avatar
arc = io.open('arc.svg', encoding='utf-8').read()

ACTS = [
 ("I","足元を疑う","自分が毎日やっていることを、外の基準で見直す",[
   ("01","2027.1","OHI &amp; TBI","ORAL HYGIENE INSTRUCTION","毎日やっているのに、誰にも習っていない","free","無料公開"),
   ("02","2027.2","歯周病","PERIODONTOLOGY","認定への道と、その前にやるべきこと","soon","COMING SOON"),
   ("03","2027.3","ドクター","THE DENTIST’S VIEW","Drは、DHのどこを見て評価しているのか","soon","COMING SOON")]),
 ("II","世界を見る","日本の当たり前が、当たり前じゃないと知る",[
   ("04","2027.4","スウェーデン","SWEDEN","予防の本場では、DHが何をしているのか","soon","COMING SOON"),
   ("05","2027.5","オランダ","NETHERLANDS","予防が制度として回っている国の中身","soon","COMING SOON"),
   ("06","2027.7","フランス","FRANCE","ヨーロッパのDH教育と資格","ok","GUEST 決定")]),
 ("III","領域を広げる","隣を知ると、担当患者の見え方が変わる",[
   ("07","2027.8","矯正","ORTHODONTICS","DHが関われる範囲は、思っているより広い","soon","COMING SOON"),
   ("08","2027.9","小児","PEDIATRIC DENTISTRY","予防のはじまりを、どう設計するか","soon","COMING SOON"),
   ("09","2027.10","インプラント／外科","IMPLANT &amp; SURGERY","メインテナンスの責任範囲","soon","COMING SOON")]),
 ("IV","出口を見る","チェアサイドの先にある道を、歩いている人から",[
   ("10","2027.11","アメリカ","UNITED STATES","キャリアと収入が、最も開いている国","ok","GUEST 決定"),
   ("11","2027.12","企業","INDUSTRY","チェアサイド以外の働き方を知る","soon","COMING SOON"),
   ("12","2028.1","SNS・発信","MEDIA &amp; VOICE","自分の学びを、仕事につなげる","soon","COMING SOON")]),
]

def row(no,m,jp,en,sub,st,stl,p=False):
    return (f'<div class="row"><span class="rn">{no}</span>'
            f'<span class="ph">{avatar(int(no))}</span>'
            f'<div class="rmain"><span class="rjp">{jp}</span><span class="ren">{en}</span></div>'
            + ('' if p else f'<span class="rsub">{sub}</span>')
            + f'<div class="rr"><span class="rm">{m}</span>'
              f'<span class="st st-{st}">{stl}</span></div></div>')

def act(n,t,note,items,p=False):
    h=(f'<div class="actline"><span class="actno">ACT {n}</span><span class="acttitle">{t}</span>'
       + ('' if p else f'<span class="actnote">{note}</span>') + '<span class="actrule"></span></div>')
    return h+'<div class="rows">'+''.join(row(*i,p=p) for i in items)+'</div>'

EXP=('<div class="exp"><span class="exp-k">★ EXPEDITION</span>'
     '<div class="exp-b"><span class="exp-t">SCANDINAVIAN<br>APPROACH</span>'
     '<span class="exp-d">2027<i>.</i>6</span></div>'
     '<span class="exp-s">予防歯科の本場スウェーデンで学ぶ、現地研修プログラム／第1期・少人数制</span></div>')

web=''.join(act(n,t,no,it)+(EXP if n=='II' else '') for n,t,no,it in ACTS)
pos=''.join(act(n,t,no,it,True)+(EXP if n=='II' else '') for n,t,no,it in ACTS)

tpl=io.open('season-tpl.html',encoding='utf-8').read()
io.open('wing-season01.html','w',encoding='utf-8').write(
    tpl.replace('{{ARC}}',arc).replace('{{WEB}}',web).replace('{{POSTER}}',pos))
print('built')
