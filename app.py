"""
우리 동네는 골든타임 안에 있을까?
전국 응급의료 사각지대 지도와 응급실 신설 효과 시뮬레이션 - Flask 웹 대시보드

실행:  python app.py   →  브라우저에서 http://127.0.0.1:5000
"""
import base64
from io import BytesIO

import matplotlib.pyplot as plt
from flask import Flask, render_template, request

import analysis as A
import charts as C

try:
    import mpld3                     # 수업에서 배운 방식: matplotlib 그래프 → HTML(D3.js)
    HAS_MPLD3 = True
except ImportError:
    HAS_MPLD3 = False

app = Flask(__name__)
REGIONS, ER, IS_SAMPLE = A.load_data()
SIDO_LIST = sorted(REGIONS["sido"].unique())


def fig_to_web(fig, mode, interactive=False):
    """그래프를 웹페이지에 넣을 HTML로 바꾼다.
    mode='mpld3' : mpld3.fig_to_html() 로 확대/이동 가능한 인터랙티브 그래프
    mode='png'   : BytesIO + base64 로 PNG 이미지 (수업 Dash 예제의 방법)
    mpld3는 범례·막대 눈금 이름·기준선 위치를 잘못 그리는 경우가 있어서,
    선·점 위주로 깨지지 않는 그래프(interactive=True)만 mpld3로 바꾸고 나머지는 PNG로 보여준다."""
    html, used = None, "png"
    if mode == "mpld3" and HAS_MPLD3 and interactive:
        try:
            html, used = mpld3.fig_to_html(fig), "mpld3"
        except Exception as e:                       # 일부 그래프 요소는 mpld3 미지원
            print("mpld3 변환 실패 → PNG로 대체:", e)
    if html is None:
        buf = BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight")
        data = base64.b64encode(buf.getbuffer()).decode("ascii")
        html = f'<img src="data:image/png;base64,{data}" alt="그래프">'
    plt.close(fig)
    return html, used


def pack(chart, mode, no):
    html, used = fig_to_web(chart["fig"], mode, chart.get("interactive", False))
    return dict(no=no, title=chart["title"], axes=chart.get("axes", ""), kind=chart["kind"],
                desc=chart["desc"], html=html, used=used)


@app.route("/")
def index():
    # ----- 1) 컨트롤 값 읽기 (form 의 GET 파라미터) -----
    sido = request.args.get("sido", "전체")
    crit = request.args.get("crit", "local30")
    if crit not in A.CRITERIA:
        crit = "local30"
    mode = request.args.get("mode", "png")          # 기본은 정확한 PNG, 원하면 mpld3
    dong = request.args.get("dong", "")
    sim = request.args.get("sim", "")
    auto = request.args.get("auto", "0")
    auto_n = int(auto) if auto in ("1", "3", "5") else 0

    # ----- 2) 분석 -----
    full = A.compute(REGIONS, ER, crit)
    scope = full if sido == "전체" else full[full["sido"] == sido]
    s = A.summary(scope)
    scope_er = ER if sido == "전체" else ER[ER["sido"] == sido]

    # 우리 동네 조회
    dong_list = scope.sort_values("rid")["rid"].tolist()
    if dong not in dong_list:
        dong = dong_list[0] if dong_list else ""
    lookup = None
    if dong:
        row = full[full["rid"] == dong].iloc[0]
        lookup = dict(rid=dong, row=row, near=A.lookup(REGIONS, ER, dong),
                      limit=A.CRITERIA[crit]["limit"], lat=row["lat"], lon=row["lon"])

    # 사각지대 Top 10 표
    top10 = scope[scope["blind"]].sort_values("pop", ascending=False).head(10)

    # ----- 3) 그래프 1~11 -----
    few = len(scope) < 3            # 세종처럼 시군구가 1~2개뿐인 경우
    # 질문별로 그래프를 묶는다: ① 어디가 → ② 누가 → ③ 왜 → ④ 어떻게(시뮬레이션)
    plans = [
        ("where", "사각지대 지도", lambda: C.map_chart(scope, ER, crit, full=full)),
        ("where", "시도별 사각지대 비율", lambda: C.sido_rate_chart(full, sido)),
        ("where", "권역별 누적 도달 인구", lambda: C.cdf_chart(full, crit)),
        ("where", "시도별 이동시간 구성", lambda: C.sido_mix_chart(full, crit)),
        ("who", "취약계층별 사각지대 비율", lambda: C.vulnerable_chart(full, sido)),
        ("who", "고령인구 비율과 이동시간", None if few else lambda: C.regression_chart(scope)),
        ("who", "도시와 농어촌 이동시간", lambda: C.area_kde_chart(scope, crit)),
        ("why", "시도별 응급의료기관 등급 구성", lambda: C.er_count_chart(ER)),
        ("why", "인구 10만 명당 응급의료기관 수", lambda: C.per_capita_chart(full, ER, sido)),
        ("why", "인구 대비 주변 응급의료기관", lambda: C.supply_chart(scope, ER)),
        ("why", "지역 특성 간 상관계수", None if few else lambda: C.corr_heatmap(scope, ER)),
    ]
    graphs = {"where": [], "who": [], "why": []}
    for no, (grp, title, make) in enumerate(plans, start=1):
        try:
            g = make() if make else C.placeholder(title, f"시군구가 {len(scope)}곳뿐이라 분석할 수 없습니다.")
        except Exception as e:                       # 한 그래프가 실패해도 페이지는 계속 보이게
            print("그래프 오류:", title, e)
            g = C.placeholder(title, "이 조건에서는 그래프를 그릴 수 없습니다.")
        graphs[grp].append(pack(g, mode, no))

    # 핵심 요약: 대시보드 전체가 말하려는 세 가지
    grp_rate = {k: (d.loc[d["blind"], "pop"].sum() / d["pop"].sum() * 100) for k, d in full.groupby("group")}
    s_all = A.summary(full)
    # ----- 4) 신설 시뮬레이션 -----
    candidates = scope[scope["blind"]].sort_values("minutes", ascending=False)["rid"].tolist()
    recs = A.recommend(REGIONS, ER, crit, n=5, sido=sido)
    picks = []
    if auto_n > 0:
        picks = recs[:auto_n]
    elif sim in candidates:
        r = REGIONS[REGIONS["rid"] == sim]
        if not r.empty:
            picks = [dict(rid=sim, lat=r.iloc[0]["lat"], lon=r.iloc[0]["lon"])]
    sim_result = None
    if picks:
        new_er = A.new_er_frame(picks)
        after_full = A.compute(REGIONS, ER, crit, extra=new_er)
        after = after_full if sido == "전체" else after_full[after_full["sido"] == sido]
        s_after = A.summary(after)
        sim_graphs = [
            pack(C.sim_bar_chart(s, s_after), mode, 12),
            pack(C.map_chart(after, ER, crit, new_er=new_er, full=after_full,
                             title=f"신설 후 골든타임 밖 인구 {s_after['blind_pop']:,}명 (신설 위치 = 보라색 +)"), mode, 13),
        ]
        sim_result = dict(picks=picks, after=s_after, graphs=sim_graphs,
                          saved=s["blind_pop"] - s_after["blind_pop"])

    # ----- 5) 핵심 요약 3줄 (선택 조건에 따라 숫자 자동 변경) -----
    where = sido if sido != "전체" else "전국"
    findings = [
        dict(q="어디가?", text=f"{where} 인구의 {s['blind_rate']:.1f}%({s['blind_pop']:,}명)가 골든타임 밖에 산다. "
             f"전국으로 보면 수도권 {grp_rate.get('수도권', 0):.1f}%, 도 지역 {grp_rate.get('도 지역', 0):.1f}%로 지방에 몰려 있다."),
        dict(q="누가?", text=f"65세 이상 노인은 {s_all['old_blind_rate']:.1f}%가 골든타임 밖으로, 전체({s_all['blind_rate']:.1f}%)보다 "
             f"{s_all['old_blind_rate'] / max(s_all['blind_rate'], 0.1):.1f}배 취약하다."),
    ]
    if recs:
        rec_after = A.summary(A.compute(REGIONS, ER, crit, extra=A.new_er_frame(recs)).pipe(
            lambda d: d if sido == "전체" else d[d["sido"] == sido]))
        cut = s["blind_pop"] - rec_after["blind_pop"]
        findings.append(dict(q="어떻게?", text=f"추천 위치 {len(recs)}곳({', '.join(r['rid'].split(' ', 1)[1] for r in recs[:3])} 등)에 "
                             f"응급실을 세우면 골든타임 밖 인구가 {cut:,}명({cut / max(s['blind_pop'], 1) * 100:.0f}%) 줄어든다."))
    else:
        findings.append(dict(q="어떻게?", text=f"{where}에는 이 기준의 골든타임 밖 지역이 없다."))

    return render_template(
        "index.html", findings=findings,
        sido=sido, crit=crit, mode=mode, dong=dong, sim=sim, auto_n=auto_n,
        sido_list=SIDO_LIST, criteria=A.CRITERIA, crit_info=A.CRITERIA[crit],
        has_mpld3=HAS_MPLD3, is_sample=IS_SAMPLE,
        s=s, n_er=len(scope_er), dong_list=dong_list, lookup=lookup, top10=top10,
        graphs=graphs, candidates=candidates, recs=recs, sim_result=sim_result,
        detour=A.DETOUR, speed=A.SPEED,
    )


if __name__ == "__main__":
    # Docker 안에서도 접속되도록 0.0.0.0 으로 연다
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
