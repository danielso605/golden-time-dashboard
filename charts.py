"""
대시보드 그래프 모음 (matplotlib + seaborn)

각 함수는 dict 를 돌려준다.
  title : 그래프가 보여주는 '결론' 한 문장 (숫자는 선택 조건에 따라 자동으로 바뀜) → 웹페이지 카드 제목
  axes  : 가로축·세로축이 무엇인지 한 줄 설명
  fig   : matplotlib 그림
  kind  : 그래프 종류 (사용한 함수)
  desc  : 읽는 법과 해석 (마지막 줄 = 이번 결과)
  interactive : mpld3 로 바꿔도 깨지지 않는 그래프인지 (선·점 위주 그래프만 True)
"""
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")                      # 서버(Flask)에서 창 없이 그리기
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib import font_manager
from matplotlib.patches import Polygon
import matplotlib.patheffects as pe

from analysis import CRITERIA, GRADES, haversine_km
import korea_outline as K

# ---------------- 공통 스타일 ----------------
_KR_FONTS = ["Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR", "Noto Sans KR"]
_installed = {f.name for f in font_manager.fontManager.ttflist}
_font = next((f for f in _KR_FONTS if f in _installed), "DejaVu Sans")
sns.set_theme(style="white", font=_font)
plt.rcParams.update({
    "axes.unicode_minus": False,           # 한글 폰트에서 마이너스 깨짐 방지
    "axes.titlesize": 11, "axes.labelsize": 11,
    "xtick.labelsize": 10, "ytick.labelsize": 10,
    "axes.edgecolor": "#8a8984", "axes.labelcolor": "#33332f",
})

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
GRAY, INK, MUTED, GRID = "#a3a29c", "#1b1b1a", "#6b6a64", "#e8e7e2"
GRADE_STYLE = {                                  # 등급: 색 + 모양을 함께 써서 색만으로 구분하지 않음
    "권역응급의료센터": dict(color=BLUE, marker="*", s=140),
    "지역응급의료센터": dict(color=ORANGE, marker="^", s=50),
    "지역응급의료기관": dict(color=AQUA, marker="o", s=18),
}
TIME_BINS = [0, 15, 30, 60, 1e9]                 # 이동시간 구간(순차 색: 밝음 → 진함 = 가까움 → 멂)
TIME_LABELS = ["15분 이내", "15~30분", "30~60분", "60분 초과"]
TIME_COLORS = ["#fdd49e", "#fc8d59", "#d7301f", "#7f0000"]
Y_CAP = 150                                      # 섬 지역 극단값 때문에 축이 늘어나지 않게 자르는 기준(분)


def _fig(w=9, h=5):
    return plt.subplots(figsize=(w, h), dpi=110)


def _style(ax, sub, xlabel, ylabel, grid="y"):
    """작은 부제(무엇을 쟀는지) + 축 이름 + 옅은 격자"""
    ax.set_title(sub, loc="left", fontsize=10.5, color=MUTED, pad=10)
    ax.set_xlabel(xlabel); ax.set_ylabel(ylabel)
    if grid:
        ax.grid(axis=grid, color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)                    # 격자는 막대 뒤로
    sns.despine(ax=ax)


def _hline(ax, y, x0, x1, label=None, **kw):
    """기준선: axhline 대신 데이터 좌표로 그려서 mpld3 에서도 제자리에 보이게"""
    ax.plot([x0, x1], [y, y], color=kw.get("color", "#3a3a38"), linestyle="--", linewidth=1.2)
    if label:
        ax.text(x1, y, f" {label}", va="center", ha="left", fontsize=9.5, color="#3a3a38")


def _vline(ax, x, y0, y1, label=None, at="top"):
    ax.plot([x, x], [y0, y1], color="#3a3a38", linestyle="--", linewidth=1.2)
    if label:
        y = y1 if at == "top" else y0
        ax.text(x, y, f" {label}", va="top" if at == "top" else "bottom", ha="left", fontsize=9.5,
                color="#3a3a38", bbox=dict(facecolor="white", edgecolor="none", pad=1.5))


def short(sido):
    """시도 이름 줄이기: 충청북도→충북, 서울특별시→서울"""
    if sido.startswith(("충청", "경상", "전라")):
        return sido[0] + sido[2]
    return {"전북특별자치도": "전북", "전남광주통합특별시": "전남광주"}.get(sido, sido[:2])


def josa(word, a="은", b="는"):
    """받침 있으면 a(은/이), 없으면 b(는/가)"""
    ch = word[-1]
    if "가" <= ch <= "힣":
        return word + (a if (ord(ch) - 0xAC00) % 28 else b)
    return word + b


def _fmt_pop(n):
    return f"{n / 10000:,.1f}만 명" if n >= 10000 else f"{n:,}명"


def _rate(d, col="pop"):
    tot = d[col].sum()
    return d.loc[d["blind"], col].sum() / tot * 100 if tot else 0.0


def placeholder(title, reason):
    """데이터가 부족해서 그래프를 그릴 수 없을 때 보여줄 빈 그래프"""
    fig, ax = _fig(7, 2)
    ax.axis("off")
    ax.text(0.5, 0.5, reason, ha="center", va="center", fontsize=12, color=MUTED)
    return dict(title=title, axes="-", fig=fig, kind="-", interactive=False, desc=[
        "선택한 지역에 시군구가 너무 적어서 이 그래프를 그릴 수 없습니다.",
        "지역을 '전국'이나 다른 시도로 바꾸면 그래프가 나타납니다.",
        f"이번 결과: {reason}",
    ])


# =====================================================================
# ① 어디가 골든타임 밖인가?
# =====================================================================
def _land(ax):
    """간략 국토 윤곽을 바다색 배경 위에 그린다"""
    ax.set_facecolor("#e9f1f9")                       # 바다
    for poly in [K.MAINLAND, K.JEJU] + K.ISLANDS + list(K.FAR.values()):
        ax.add_patch(Polygon(poly, closed=True, facecolor="#f7f6f2", edgecolor="#b8b6ad",
                             linewidth=0.9, zorder=1))


def map_chart(scope, er, crit_key, new_er=None, title=None, full=None):
    """전국 지도 위에 시군구를 이동시간 색으로 표시. 시도를 고르면 그 시도만 색칠하고 나머지는 회색으로 둔다."""
    c = CRITERIA[crit_key]
    far = scope[scope["lon"].lt(125.3) | scope["lon"].gt(130.3)]          # 옹진군(백령도)·울릉군
    main = scope.drop(far.index)
    lon0, lon1, lat0, lat1 = 125.75, 129.75, 33.05, 38.70                # 국토 전체가 항상 보이도록 고정 범위
    k = 1 / np.cos(np.radians((lat0 + lat1) / 2))                         # 위도에 따른 가로·세로 비율 보정
    fig, ax = plt.subplots(figsize=(7.2, 9.6), dpi=110)
    _land(ax)
    if full is not None and len(full) > len(scope):                       # 선택하지 않은 시도는 회색 점
        rest = full[~full["rid"].isin(scope["rid"])]
        ax.scatter(rest["lon"], rest["lat"], s=12, c="#cfcdc6", edgecolors="none", zorder=2,
                   label="다른 시도 시군구")

    # 응급의료기관: 이 기준에서 '도착지'로 인정하는 등급만 작게 표시
    use = er[er["grade"].isin(c["grades"])]
    for g in GRADES[::-1]:
        if g not in c["grades"]:
            continue
        e, st = use[use["grade"] == g], GRADE_STYLE[g]
        ax.scatter(e["lon"], e["lat"], c=st["color"], marker=st["marker"], s=st["s"] * 0.55,
                   edgecolors="white", linewidths=0.5, label=g, zorder=5)

    # 시군구: 색 = 이동시간 구간, 크기 = 인구
    pmax = (full if full is not None else scope)["pop"].max()          # 점 크기 기준을 전국과 같게
    size = np.sqrt(scope["pop"]) / np.sqrt(pmax) * 260 + 14
    bins = pd.cut(scope["minutes"], TIME_BINS, labels=TIME_LABELS)
    for lab, col in zip(TIME_LABELS, TIME_COLORS):
        m = bins == lab
        ax.scatter(scope.loc[m, "lon"], scope.loc[m, "lat"], s=size[m], c=col, alpha=0.85,
                   edgecolors="white", linewidths=0.8, label=f"시군구 {lab}", zorder=3)
    if new_er is not None and len(new_er):
        ax.scatter(new_er["lon"], new_er["lat"], marker="P", s=300, c="#6250d6",
                   edgecolors="white", linewidths=1.5, label="신설 응급실(가상)", zorder=7)

    # 인구가 많은 사각지대 3곳 이름 표시
    halo = [pe.withStroke(linewidth=3, foreground="white")]
    for r in main[main["blind"]].nlargest(3, "pop").itertuples():
        ax.annotate(f"{r.sigungu} {r.minutes:.0f}분", (r.lon, r.lat), xytext=(7, 5), textcoords="offset points",
                    fontsize=9, color=INK, path_effects=halo, zorder=8)

    ax.set_xlim(lon0, lon1); ax.set_ylim(lat0, lat1)
    ax.set_aspect(k)
    ax.set_xticks([]); ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_color("#cfd8e3")
    ax.set_title("점 = 시군구 (클수록 인구 많음) · 색 = 가장 가까운 응급실까지 예상 시간",
                 loc="left", fontsize=10.5, color=MUTED, pad=8)

    # 멀리 떨어진 섬은 작은 박스로 따로 표시
    spots = {"옹진군": [0.015, 0.83, 0.13, 0.14], "울릉군": [0.855, 0.83, 0.13, 0.14]}
    for r in far.itertuples():
        ins = ax.inset_axes(spots.get(r.sigungu, [0.02, 0.6, 0.17, 0.17]))
        ins.set_facecolor("#e9f1f9")
        poly = K.FAR.get(r.sigungu)
        if poly:
            ins.add_patch(Polygon(poly, closed=True, facecolor="#f7f6f2", edgecolor="#b8b6ad", linewidth=0.8))
        col = TIME_COLORS[int(np.digitize(r.minutes, TIME_BINS[1:-1]))]
        ins.scatter([r.lon], [r.lat], s=60, c=col, edgecolors="white", linewidths=0.8, zorder=3)
        ins.set_xlim(r.lon - 0.2, r.lon + 0.2); ins.set_ylim(r.lat - 0.12, r.lat + 0.12)
        ins.set_xticks([]); ins.set_yticks([])
        for sp in ins.spines.values():
            sp.set_color("#8a8984")
        ins.set_title(f"{r.sigungu} {r.minutes:.0f}분", fontsize=8.5, color=INK, pad=2)

    hs, ls = ax.get_legend_handles_labels()                   # 범례 순서: 시간 구간 → 응급의료기관 → 기타
    rank = lambda l: (0 if l.startswith("시군구") else 1 if "응급" in l and "신설" not in l else 2)
    pairs = sorted(zip(hs, ls), key=lambda p: rank(p[1]))
    ax.legend([p[0] for p in pairs], [p[1] for p in pairs], loc="upper center", bbox_to_anchor=(0.5, -0.01),
              ncol=4, fontsize=8.5, frameon=False, handletextpad=0.3, columnspacing=1.0)
    fig.tight_layout()
    blind = scope[scope["blind"]]
    head = title or f"골든타임 밖 시군구 {len(blind)}곳에 {_fmt_pop(int(blind['pop'].sum()))}이 산다"
    return dict(title=head, interactive=False, fig=fig, kind="지도형 산점도 (plt.scatter + 국토 윤곽 Polygon)",
                axes="지도 위치 = 실제 위치 · 점 크기 = 인구 · 점 색 = 이동시간 (연한 노랑 → 진한 빨강일수록 멂)",
                desc=[
        f"진한 빨강일수록 응급실이 멀고, 점이 클수록 사람이 많이 사는 곳입니다. ★▲●는 이 기준({c['label']})에서 도착지로 인정하는 응급의료기관입니다.",
        "크고 진한 점이 '사람은 많은데 응급실은 먼' 우선 해결 지역이며, 인구가 많은 사각지대 3곳은 이름을 적었습니다.",
        f"이번 결과: 골든타임 밖 시군구는 {len(blind)}곳, 인구 {_fmt_pop(int(blind['pop'].sum()))}입니다.",
    ])



def sido_rate_chart(full, sel_sido):
    g = full.groupby("sido").apply(_rate, include_groups=False).sort_values()
    fig, ax = _fig(9, 6.2)
    colors = [ORANGE if s == sel_sido else BLUE for s in g.index]
    bars = ax.barh([short(s) for s in g.index], g.values, color=colors, height=0.65)
    ax.bar_label(bars, labels=[f"{v:.1f}%" for v in g.values], padding=4, fontsize=9.5, color=INK)
    nat = _rate(full)
    _vline(ax, nat, len(g) - 0.4, -0.6, f"전국 평균 {nat:.1f}%")   # 막대 순서가 위→아래라 아래쪽(0%대 시도 옆)에 표시
    ax.set_xlim(0, max(g.max() * 1.18, 5))
    _style(ax, "시도 인구 중 골든타임 밖에 사는 사람의 비율", "골든타임 밖 인구 비율 (%)", "", grid="x")
    top = g.index[-1]
    head = f"{josa(short(top))} 주민 {g.iloc[-1]:.0f}%가 골든타임 밖, 전국 평균의 {g.iloc[-1] / max(nat, 0.1):.1f}배"
    if sel_sido in g.index and sel_sido != top:
        rank = len(g) - list(g.index).index(sel_sido)
        head = f"{short(sel_sido)}의 골든타임 밖 비율은 {g[sel_sido]:.1f}%, {len(g)}개 시도 중 {rank}위"
    return dict(title=head, interactive=False, fig=fig, kind="가로 막대 (plt.barh)",
                axes="가로축 = 골든타임 밖 인구 비율(%) · 세로축 = 시도",
                desc=[
        "막대가 길수록 그 시도 주민 중 응급실까지 골든타임 안에 못 가는 사람이 많습니다. 점선은 전국 평균입니다.",
        "선택한 시도는 주황색으로 표시됩니다.",
        f"이번 결과: 가장 높은 곳은 {top}({g.iloc[-1]:.1f}%), 0%인 시도는 {int((g == 0).sum())}곳입니다.",
    ])


def cdf_chart(full, crit_key):
    limit = CRITERIA[crit_key]["limit"]
    t = np.arange(0, 121, 1)
    fig, ax = _fig()
    vals = {}
    for grp, col, ls in [("수도권", BLUE, "-"), ("광역시", AQUA, "--"), ("도 지역", ORANGE, "-")]:
        d = full[full["group"] == grp]
        if d.empty:
            continue
        y = [d.loc[d["minutes"] <= m, "pop"].sum() / d["pop"].sum() * 100 for m in t]
        ax.plot(t, y, color=col, linestyle=ls, linewidth=2.4, label=grp)
        vals[grp] = d.loc[d["minutes"] <= limit, "pop"].sum() / d["pop"].sum() * 100
    _vline(ax, limit, 0, 100, f"골든타임 {limit}분", at="bottom")
    ax.legend(loc="lower right", title="권역", frameon=True, framealpha=0.95)
    ax.set_xlim(0, 120); ax.set_ylim(0, 104)
    _style(ax, "가로축의 시간 안에 응급실에 도착할 수 있는 인구 비율 (누적)", "응급실까지 예상 이동시간 (분)", "도착 가능한 인구 비율 (%)", grid="both")
    a, b = vals.get("수도권", 0), vals.get("도 지역", 0)
    return dict(title=f"{limit}분 안에 응급실 도착: 수도권 {a:.0f}% vs 도 지역 {b:.0f}%", interactive=False,
                fig=fig, kind="누적 선그래프 (plt.plot)",
                axes="가로축 = 이동시간(분) · 세로축 = 그 시간 안에 도착 가능한 인구 비율(%)",
                desc=[
        "선이 왼쪽 위로 빨리 올라갈수록 응급실 접근성이 좋은 권역입니다. 세 선 사이의 간격이 곧 지역 격차입니다.",
        "점선(골든타임)과 선이 만나는 높이가 '골든타임 안에 도착할 수 있는 인구 비율'입니다.",
        "이번 결과: " + ", ".join(f"{k} {v:.1f}%" for k, v in vals.items()) + "가 골든타임 안에 도착할 수 있습니다.",
    ])


def sido_mix_chart(full, crit_key):
    """시도별로 시군구를 이동시간 구간으로 나눠 100% 막대로 보여준다"""
    limit = CRITERIA[crit_key]["limit"]
    bins = pd.cut(full["minutes"], TIME_BINS, labels=TIME_LABELS)
    tab = pd.crosstab(full["sido"], bins).reindex(columns=TIME_LABELS, fill_value=0)
    n = tab.sum(axis=1)
    out = full.groupby("sido")["blind"].sum().reindex(tab.index)
    share = (tab.div(n, axis=0) * 100)
    order = (out / n).sort_values(kind="stable").index        # 골든타임 밖 비율이 낮은 순 → 높은 시도가 맨 위
    share, n, out = share.loc[order], n.loc[order], out.loc[order]
    fig, ax = _fig(9.5, 6.4)
    y = np.arange(len(order))
    left = np.zeros(len(order))
    for lab, col in zip(TIME_LABELS, TIME_COLORS):
        v = share[lab].values
        ax.barh(y, v, left=left, color=col, height=0.68, edgecolor="white", linewidth=1.2, label=lab)
        for yi, (l, val) in enumerate(zip(left, v)):           # 칸이 넓을 때만 % 글자
            if val >= 12:
                ax.text(l + val / 2, yi, f"{val:.0f}%", ha="center", va="center", fontsize=8.5,
                        color="white" if lab in TIME_LABELS[2:] else INK)
        left += v
    for yi, s in enumerate(order):
        ax.text(101.5, yi, f"{int(out[s])}/{int(n[s])}곳 밖", va="center", fontsize=9.5,
                color=ORANGE if out[s] else MUTED, fontweight="bold" if out[s] / n[s] >= 0.5 else None)
    ax.set_yticks(y); ax.set_yticklabels([short(s) for s in order])
    ax.set_xlim(0, 100); ax.set_xticks([0, 25, 50, 75, 100]); ax.set_xticklabels(["0%", "25%", "50%", "75%", "100%"])
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.09), ncol=4, frameon=False, fontsize=9.5,
              title="가장 가까운 응급실까지 예상 시간", title_fontsize=9.5)
    _style(ax, "막대 하나 = 시도 하나 · 칸 = 그 시도 시군구 중 해당 시간대 비율 · 오른쪽 = 골든타임 밖 시군구 수",
           "시군구 비율 (%)", "", grid=None)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    ratio = out / n
    half = [short(s) for s in ratio[ratio >= 0.5].sort_values(ascending=False).index]
    top = ratio.idxmax()
    if len(half) > 3:
        head = f"{'·'.join(half[:3])} 등 {len(half)}개 시도는 시군구 절반 이상이 골든타임 밖"
    elif half:
        head = f"{josa('·'.join(half))} 시군구 절반 이상이 골든타임 밖"
    elif ratio.max() > 0:
        head = f"{josa(short(top))} 시군구 {int(n[top])}곳 중 {int(out[top])}곳이 골든타임 밖"
    else:
        head = "모든 시도의 시군구가 골든타임 안에 있다"
    dark = "진한 빨강 칸" if limit >= 60 else "빨강·진한 빨강 칸"
    return dict(title=head, interactive=False, fig=fig, kind="100% 누적 가로 막대 (plt.barh, left=)",
                axes="가로축 = 시도 안 시군구 비율(%, 합계 100%) · 세로축 = 시도(골든타임 밖 비율이 높은 순으로 위)",
                desc=[
        f"막대 하나가 한 시도의 시군구 전체(100%)입니다. 빨간 칸이 길수록 응급실이 먼 동네가 많은 시도입니다.",
        f"이 기준(골든타임 {limit}분)에서는 {dark}이 골든타임 밖이고, 오른쪽 숫자는 '골든타임 밖 시군구 수 / 전체 시군구 수'입니다.",
        f"이번 결과: 골든타임 밖 시군구 비율이 가장 높은 곳은 {top}({int(out[top])}/{int(n[top])}곳)입니다.",
    ])



# =====================================================================
# ② 누가 더 위험한가?
# =====================================================================
def vulnerable_chart(full, sel_sido):
    rows = [dict(sido=s, 전체=_rate(d), 고령=_rate(d, "pop65"), 어린이=_rate(d, "pop014"))
            for s, d in full.groupby("sido")]
    t = pd.DataFrame(rows)
    t = t[t["전체"] > 0].sort_values("전체", ascending=False).reset_index(drop=True)
    fig, ax = _fig(10, 5)
    x = np.arange(len(t))
    for k, (col, color, lab) in enumerate([("전체", GRAY, "전체 인구"), ("고령", ORANGE, "고령인구 (65세 이상)"),
                                            ("어린이", AQUA, "어린이 (0~14세)")]):
        ax.bar(x + (k - 1) * 0.27, t[col], width=0.26, color=color, label=lab)
    ax.set_xticks(x)
    ax.set_xticklabels([("▶ " if s == sel_sido else "") + short(s) for s in t["sido"]])
    ax.set_ylim(0, max(t[["전체", "고령", "어린이"]].max().max() * 1.15, 1))
    ax.legend(loc="upper right", frameon=False)
    _style(ax, "각 집단 중 골든타임 밖에 사는 사람의 비율 (사각지대가 있는 시도만)", "", "골든타임 밖 비율 (%)")
    all_r, old_r, ch_r = _rate(full), _rate(full, "pop65"), _rate(full, "pop014")
    return dict(title=f"노인의 {old_r:.1f}%가 골든타임 밖: 전체 인구({all_r:.1f}%)의 {old_r / max(all_r, 0.1):.1f}배",
                interactive=False, fig=fig, kind="묶은 막대 (plt.bar)",
                axes="가로축 = 시도 · 세로축 = 각 집단 중 골든타임 밖 비율(%) · 회색 전체 / 주황 고령 / 초록 어린이",
                desc=[
        "주황 막대가 회색보다 높으면, 그 시도에서는 노인이 응급실에서 먼 곳에 더 많이 산다는 뜻입니다.",
        "응급 상황이 가장 잦은 고령층이 오히려 접근성이 더 나쁜 '이중 취약' 구조인지 확인할 수 있습니다.",
        f"이번 결과: 전국 기준 골든타임 밖 비율은 전체 {all_r:.1f}%, 고령인구 {old_r:.1f}%, 어린이 {ch_r:.1f}%입니다.",
    ])


def regression_chart(scope):
    d = scope[~scope["island"]]
    x, y = d["old_ratio"] * 100, d["minutes"]
    fig, ax = _fig()
    ax.scatter(x, y, s=28, c=BLUE, alpha=0.6, edgecolors="white", linewidths=0.5)
    r = np.corrcoef(x, y)[0, 1] if len(d) > 2 else 0
    slope, inter = np.polyfit(x, y, 1) if len(d) > 2 else (0, 0)
    xs = np.linspace(x.min(), x.max(), 50)
    ax.plot(xs, slope * xs + inter, color=ORANGE, linewidth=2.4)
    ax.text(xs[-1], slope * xs[-1] + inter, f"  회귀선\n  r = {r:.2f}", color=ORANGE, fontsize=10, va="center")
    ax.set_ylim(bottom=0)
    _style(ax, "점 = 시군구 하나 (섬 지역 제외)", "고령인구 비율 (65세 이상, %)", "응급실까지 예상 이동시간 (분)", grid="both")
    strength = "강한" if abs(r) >= 0.6 else "중간 정도의" if abs(r) >= 0.3 else "약한"
    head = (f"노인이 많은 지역일수록 응급실이 멀다 (r = {r:.2f})" if r >= 0.3
            else f"고령인구 비율과 이동시간의 관계는 {strength} 편이다 (r = {r:.2f})")
    return dict(title=head, interactive=True, fig=fig, kind="회귀 산점도 (plt.scatter + np.polyfit)",
                axes="가로축 = 시군구의 고령인구 비율(%) · 세로축 = 가장 가까운 응급실까지 예상 시간(분)",
                desc=[
        "점들이 오른쪽 위로 올라갈수록 '고령인구가 많은 동네일수록 응급실이 멀다'는 뜻입니다. 주황 선은 최소자승법 회귀선입니다.",
        "피어슨 상관계수 r은 -1~1 사이이며, 0.3 이상이면 중간, 0.6 이상이면 강한 양의 상관으로 봅니다.",
        f"이번 결과: r = {r:.2f}({strength} 상관), 회귀식 y = {slope:.2f}x {'+' if inter >= 0 else '-'} {abs(inter):.1f}. "
        f"고령비율이 10%p 높을수록 이동시간이 약 {slope * 10:.0f}분 길어지는 경향입니다.",
    ])


def area_kde_chart(scope, crit_key):
    limit = CRITERIA[crit_key]["limit"]
    fig, ax = _fig()
    med = {}
    for area, col, lab in [("도시", BLUE, "시·구 지역"), ("농어촌", ORANGE, "군 지역")]:
        d = scope[(scope["area_type"] == area) & ~scope["island"]]["minutes"]
        if len(d) > 2 and d.std() > 0:
            sns.kdeplot(d, fill=True, color=col, alpha=0.3, linewidth=2.2, clip=(0, Y_CAP), ax=ax)
            med[lab] = d.median()
            _, ymax = ax.get_ylim()
            ax.text(d.median() + 6, ymax * (0.85 if area == "도시" else 0.45), f"{lab}\n중앙값 {d.median():.0f}분",
                    color=col, fontsize=10.5, fontweight="bold", ha="left")
    _, ymax = ax.get_ylim()
    _vline(ax, limit, 0, ymax, f"골든타임 {limit}분")
    ax.set_xlim(0, Y_CAP)
    ax.set_yticks([])
    _style(ax, "곡선 아래 면적 = 시군구 수의 분포 (섬 지역 제외)", "응급실까지 예상 이동시간 (분)", "시군구 분포 (높을수록 많음)", grid=None)
    if len(med) == 2:
        head = f"군 지역은 응급실까지 중앙값 {med['군 지역']:.0f}분, 시·구 지역({med['시·구 지역']:.0f}분)의 {med['군 지역'] / max(med['시·구 지역'], 0.5):.0f}배"
        last = f"시·구 지역 중앙값 {med['시·구 지역']:.1f}분, 군 지역 중앙값 {med['군 지역']:.1f}분입니다."
    else:
        head, last = "선택한 지역은 시·구 또는 군 한 가지 유형만 있다", "전국을 선택하면 도시와 농어촌의 차이가 잘 드러납니다."
    return dict(title=head, interactive=False, fig=fig, kind="커널밀도 그래프 (sns.kdeplot)",
                axes="가로축 = 이동시간(분) · 세로축 = 그 시간대에 있는 시군구가 얼마나 많은지(밀도)",
                desc=[
        "산이 왼쪽에 있을수록 응급실이 가깝고, 오른쪽으로 넓게 퍼질수록 멀고 들쭉날쭉합니다.",
        "군(郡) 지역의 산이 골든타임 점선 오른쪽에 걸쳐 있다면 농어촌 주민 상당수가 사각지대라는 뜻입니다.",
        f"이번 결과: {last}",
    ])


# =====================================================================
# ③ 왜 생기나? (응급의료 공급)
# =====================================================================
def er_count_chart(er):
    t = er.pivot_table(index="sido", columns="grade", values="name", aggfunc="count", fill_value=0)
    t = t.reindex(columns=GRADES, fill_value=0)
    t = t.loc[t.sum(axis=1).sort_values().index]
    fig, ax = _fig(9, 6.2)
    left = np.zeros(len(t))
    for g, col in zip(GRADES, [BLUE, ORANGE, AQUA]):
        ax.barh([short(s) for s in t.index], t[g], left=left, color=col, height=0.65, label=g,
                edgecolor="white", linewidth=1)
        left += t[g].values
    for i, (tot, reg) in enumerate(zip(t.sum(axis=1), t[GRADES[0]])):
        ax.text(tot + 0.6, i, f"{tot}곳 (권역 {reg})", va="center", fontsize=9.5, color=INK)
    ax.set_xlim(0, t.sum(axis=1).max() * 1.25)
    ax.legend(loc="lower right", frameon=False)
    _style(ax, "시도별 응급의료기관 수를 등급별로 쌓은 막대", "응급의료기관 수 (곳)", "", grid="x")
    n_reg = int(t[GRADES[0]].sum())
    return dict(title=f"중증 환자를 보는 권역응급의료센터는 전국 {n_reg}곳, 시도마다 {int(t[GRADES[0]].min())}~{int(t[GRADES[0]].max())}곳",
                interactive=False, fig=fig, kind="누적 가로 막대 (plt.barh)",
                axes="가로축 = 기관 수(곳) · 세로축 = 시도 · 파랑 권역센터 / 주황 지역센터 / 초록 지역기관",
                desc=[
        "권역응급의료센터 > 지역응급의료센터 > 지역응급의료기관 순으로 중증 환자(심근경색, 뇌졸중 등)를 볼 수 있는 능력이 큽니다.",
        "막대 전체가 길어도 초록(지역기관) 비중이 크면 중증 응급에는 대응하기 어렵습니다.",
        f"이번 결과: 전체 {len(er)}곳 중 권역센터 {n_reg}곳, 지역센터 {int(t[GRADES[1]].sum())}곳, 지역기관 {int(t[GRADES[2]].sum())}곳입니다.",
    ])


def per_capita_chart(full, er, sel_sido):
    pop = full.groupby("sido")["pop"].sum()
    cnt = er.groupby("sido").size().reindex(pop.index, fill_value=0)
    per = (cnt / pop * 100000).sort_values(ascending=False)
    nat = len(er) / pop.sum() * 100000
    fig, ax = _fig(10, 4.8)
    colors = [ORANGE if s == sel_sido else BLUE for s in per.index]
    bars = ax.bar([short(s) for s in per.index], per.values, color=colors, width=0.65)
    ax.bar_label(bars, labels=[f"{v:.2f}" for v in per.values], padding=3, fontsize=9, color=INK)
    _hline(ax, nat, -0.5, len(per) - 0.5, f"전국 {nat:.2f}")
    ax.set_ylim(0, per.max() * 1.18)
    _style(ax, "응급의료기관 수 ÷ 인구 × 10만", "", "인구 10만 명당 응급의료기관 수 (곳)")
    return dict(title=f"인구 대비 기관 수는 {josa(short(per.index[0]), '이', '가')} 가장 많다: 그런데도 사각지대가 생기는 건 '거리' 때문",
                interactive=False, fig=fig, kind="세로 막대 (plt.bar)",
                axes="가로축 = 시도 · 세로축 = 인구 10만 명당 응급의료기관 수(곳) · 점선 = 전국 평균",
                desc=[
        "기관 수를 인구로 나눠 시도끼리 공정하게 비교했습니다.",
        "인구 대비 기관 수가 많은데도 사각지대 비율이 높다면(강원·경북 등), 기관이 넓은 땅에 흩어져 있어 '거리'가 문제라는 뜻입니다.",
        f"이번 결과: 가장 많은 곳은 {per.index[0]}({per.iloc[0]:.2f}곳), 가장 적은 곳은 {per.index[-1]}({per.iloc[-1]:.2f}곳)입니다.",
    ])


def supply_chart(scope, er, radius=20, top_n=12):
    """골든타임 밖 시군구마다 주변 응급의료기관 수를 롤리팝으로, 골든타임 안 시군구의 보통 수준과 비교"""
    d = haversine_km(scope["lat"].values[:, None], scope["lon"].values[:, None],
                     er["lat"].values[None, :], er["lon"].values[None, :])
    t = scope.assign(er_near=(d <= radius).sum(axis=1))
    ok, bad = t[~t["blind"]], t[t["blind"]]
    if bad.empty:
        g = placeholder("선택한 지역에는 골든타임 밖 시군구가 없다", "골든타임 밖 시군구가 없어 비교할 대상이 없습니다.")
        g["desc"] = ["이 그래프는 골든타임 밖 시군구의 주변 응급의료기관 수를 보여 줍니다.",
                     "선택한 지역은 모든 시군구가 골든타임 안이라 표시할 막대가 없습니다(좋은 결과입니다).",
                     "이번 결과: 골든타임 밖 시군구 0곳"]
        return g
    show = bad.nlargest(top_n, "pop").sort_values("pop")          # 인구 많은 순으로 위
    fig, ax = _fig(9.5, 0.42 * len(show) + 1.9)
    y = np.arange(len(show))
    ax.hlines(y, 0, show["er_near"], color=ORANGE, linewidth=2.2, zorder=2)
    ax.scatter(show["er_near"], y, s=70, c=ORANGE, edgecolors="white", linewidths=1, zorder=3)
    for yi, r in enumerate(show.itertuples()):
        ax.text(r.er_near + 0.6, yi, f"{r.er_near}곳", va="center", fontsize=9.5, color=INK)
    ref = float(ok["er_near"].median()) if len(ok) else None
    xmax = max(show["er_near"].max(), ref or 0) * 1.25 + 2
    if ref is not None:
        _vline(ax, ref, -0.6, len(show) - 0.4, f"골든타임 안 시군구 보통 {ref:.0f}곳")
    ax.set_yticks(y)
    ax.set_yticklabels([f"{short(r.sido)} {r.sigungu} ({r.pop / 10000:.0f}만 명)" for r in show.itertuples()])
    ax.set_xlim(0, xmax); ax.set_ylim(-0.7, len(show) + 0.2)
    _style(ax, f"선 길이 = 시군구 중심에서 반경 {radius}km 안 응급의료기관 수 · 인구 많은 사각지대 {len(show)}곳",
           f"반경 {radius}km 안 응급의료기관 수 (곳)", "", grid="x")
    fig.tight_layout()
    med_bad = float(bad["er_near"].median())
    head = (f"골든타임 밖 지역 주변 {radius}km엔 응급의료기관이 보통 {med_bad:.0f}곳"
            + (f", 골든타임 안 지역은 {ref:.0f}곳" if ref is not None else ""))
    return dict(title=head, interactive=False, fig=fig, kind="롤리팝 차트 (plt.hlines + plt.scatter)",
                axes=f"가로축 = 반경 {radius}km 안 응급의료기관 수(곳) · 세로축 = 골든타임 밖 시군구(괄호 = 인구)",
                desc=[
        "주황 선이 짧을수록 그 동네 주변에 갈 수 있는 응급의료기관이 거의 없다는 뜻입니다.",
        "점선은 골든타임 안 시군구의 보통(중앙값) 수준이라, 선이 점선보다 한참 짧으면 '주변에 응급실이 없어서' 사각지대가 된 것입니다.",
        f"이번 결과: 인구가 가장 많은 사각지대는 {short(show.iloc[-1]['sido'])} {show.iloc[-1]['sigungu']}이고, "
        f"주변 {radius}km 안 기관은 {int(show.iloc[-1]['er_near'])}곳입니다.",
    ])



def corr_heatmap(scope, er):
    d = haversine_km(scope["lat"].values[:, None], scope["lon"].values[:, None],
                     er["lat"].values[None, :], er["lon"].values[None, :])
    s = scope[~scope["island"].values]
    near = (d <= 20).sum(axis=1)[~scope["island"].values]
    df = pd.DataFrame({
        "인구": s["pop"].values,
        "고령인구 비율": s["old_ratio"].values,
        "어린이 비율": s["child_ratio"].values,
        "20km 안\n응급기관 수": near,
        "응급실까지\n이동시간": s["minutes"].values,
    })
    corr = df.corr()
    fig, ax = _fig(7.5, 6)
    sns.heatmap(corr, annot=True, fmt=".2f", cmap="RdBu_r", vmin=-1, vmax=1, square=True,
                linewidths=2, linecolor="white", cbar_kws=dict(shrink=0.75, label="상관계수 r"),
                annot_kws=dict(fontsize=11), ax=ax)
    ax.set_xticklabels(ax.get_xticklabels(), rotation=0, fontsize=9.5)
    ax.set_yticklabels(ax.get_yticklabels(), rotation=0, fontsize=9.5)
    ax.set_title("빨강 = 함께 커짐(+), 파랑 = 반대로 움직임(−), 진할수록 관계가 강함 (섬 지역 제외)",
                 loc="left", fontsize=10.5, color=MUTED, pad=10)
    r_near = corr.loc["20km 안\n응급기관 수", "응급실까지\n이동시간"]
    r_old = corr.loc["고령인구 비율", "응급실까지\n이동시간"]
    return dict(title=f"이동시간은 주변 기관 수와 반대(r = {r_near:.2f}), 고령인구 비율과 같은 방향(r = {r_old:.2f})",
                interactive=False, fig=fig, kind="상관계수 히트맵 (df.corr, sns.heatmap)",
                axes="가로·세로 = 시군구 특성 5가지 · 칸 안 숫자 = 두 특성의 피어슨 상관계수",
                desc=[
        "가장 아래 줄(응급실까지 이동시간)을 보면, 어떤 특성의 지역이 응급실에서 먼지 한 번에 알 수 있습니다.",
        "인구와 고령비율이 파랑(−)이면 '사람이 적은 곳일수록 노인 비율이 높다'는 뜻으로, 농어촌 고령화를 보여줍니다.",
        f"이번 결과: 이동시간과의 상관은 주변 기관 수 {r_near:.2f}, 고령비율 {r_old:.2f}, "
        f"어린이비율 {corr.loc['어린이 비율', '응급실까지' + chr(10) + '이동시간']:.2f}, 인구 {corr.loc['인구', '응급실까지' + chr(10) + '이동시간']:.2f}입니다.",
    ])


# =====================================================================
# ④ 어떻게 줄이나? (신설 시뮬레이션)
# =====================================================================
def sim_bar_chart(before, after):
    labels = ["전체 인구", "고령인구\n(65세 이상)", "어린이\n(0~14세)"]
    b = [before["blind_pop"] / 10000, before["old_blind"] / 10000, before["child_blind"] / 10000]
    a = [after["blind_pop"] / 10000, after["old_blind"] / 10000, after["child_blind"] / 10000]
    x = np.arange(3)
    fig, ax = _fig(8, 4.6)
    b1 = ax.bar(x - 0.2, b, width=0.38, color=GRAY, label="신설 전")
    b2 = ax.bar(x + 0.2, a, width=0.38, color=BLUE, label="신설 후")
    ax.bar_label(b1, labels=[f"{v:,.1f}" for v in b], padding=3, fontsize=9.5)
    ax.bar_label(b2, labels=[f"{v:,.1f}" for v in a], padding=3, fontsize=9.5)
    ax.set_xticks(x); ax.set_xticklabels(labels)
    ax.set_ylim(0, max(b) * 1.18 if max(b) else 1)
    ax.legend(frameon=False)
    _style(ax, "골든타임 밖에 사는 사람 수, 신설 전과 후", "", "골든타임 밖 인구 (만 명)")
    saved = before["blind_pop"] - after["blind_pop"]
    return dict(title=f"신설하면 골든타임 밖 인구가 {_fmt_pop(saved)}({saved / max(before['blind_pop'], 1) * 100:.0f}%) 줄어든다",
                interactive=False, fig=fig, kind="묶은 막대 (plt.bar)",
                axes="가로축 = 집단(전체·고령·어린이) · 세로축 = 골든타임 밖 인구(만 명) · 회색 전 / 파랑 후",
                desc=[
        "선택한 기준에 맞는 가상의 응급의료센터를 세웠을 때, 골든타임 밖 인구가 얼마나 줄어드는지 비교합니다.",
        "같은 예산으로 응급실 하나를 짓는다면, 회색과 파랑의 차이가 가장 큰 곳이 효과적인 위치입니다.",
        f"이번 결과: {_fmt_pop(before['blind_pop'])} → {_fmt_pop(after['blind_pop'])}. "
        f"고령인구는 {_fmt_pop(before['old_blind'] - after['old_blind'])}, 어린이는 {_fmt_pop(before['child_blind'] - after['child_blind'])} 줄어듭니다.",
    ])
