"""
분석 로직: 가장 가까운 응급실 찾기 → 예상 이동시간 → 골든타임 사각지대 판정
                    → 응급실 신설 시뮬레이션 / 최적 위치 추천
"""
import os
import numpy as np
import pandas as pd

EARTH_R = 6371.0   # 지구 반지름(km)
DETOUR = 1.4       # 직선거리 → 실제 도로거리 보정계수
SPEED = 45.0       # 구급차 평균 이동속도(km/h) 가정

GRADES = ["권역응급의료센터", "지역응급의료센터", "지역응급의료기관"]

# 골든타임 기준 (보건복지부 응급의료 취약지 판단 기준을 참고)
CRITERIA = {
    "local30": {"label": "지역응급의료센터 이상 · 30분", "grades": GRADES[:2], "limit": 30},
    "regional60": {"label": "권역응급의료센터 · 60분", "grades": GRADES[:1], "limit": 60},
    "any30": {"label": "모든 응급의료기관 · 30분", "grades": GRADES, "limit": 30},
}

CAPITAL = ["서울특별시", "인천광역시", "경기도"]
METRO = ["부산광역시", "대구광역시", "광주광역시", "대전광역시", "울산광역시", "세종특별자치시"]
# 육지와 떨어진 섬 지역: 직선거리(바다 위)로는 실제 이송(배·헬기)과 차이가 커서 일부 그래프에서 따로 표시
ISLANDS = ["인천광역시 옹진군", "경상북도 울릉군"]


def load_data(base="data"):
    """실제 데이터(data/processed)가 있으면 그것을, 없으면 샘플을 읽는다."""
    real = os.path.join(base, "processed")
    if os.path.exists(os.path.join(real, "er.csv")) and os.path.exists(os.path.join(real, "regions.csv")):
        folder, is_sample = real, False
    else:
        folder, is_sample = os.path.join(base, "sample"), True
    regions = pd.read_csv(os.path.join(folder, "regions.csv"), encoding="utf-8-sig")
    er = pd.read_csv(os.path.join(folder, "er.csv"), encoding="utf-8-sig")
    regions["rid"] = regions["sido"] + " " + regions["sigungu"]
    if "old_sido" not in regions:
        regions["old_sido"] = ""
    regions["old_sido"] = regions["old_sido"].fillna("")
    if "pop014" not in regions:                      # 어린이 인구가 없는 옛 파일 대비
        regions["pop014"] = 0
    regions["old_ratio"] = regions["pop65"] / regions["pop"]
    regions["child_ratio"] = regions["pop014"] / regions["pop"]
    # 권역 구분: 통합특별시는 옛 광주광역시 구역만 '광역시'로 본다
    is_metro = regions["sido"].isin(METRO) | (regions["old_sido"] == "광주광역시")
    regions["group"] = np.where(regions["sido"].isin(CAPITAL), "수도권",
                                np.where(is_metro, "광역시", "도 지역"))
    regions["island"] = regions["rid"].isin(ISLANDS)
    return regions, er, is_sample


def km_to_min(km):
    return km * DETOUR / SPEED * 60


def haversine_km(lat1, lon1, lat2, lon2):
    """배열끼리 직선거리(km). lat1/lon1 과 lat2/lon2 는 브로드캐스팅 가능."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dlat, dlon = p2 - p1, np.radians(lon2) - np.radians(lon1)
    a = np.sin(dlat / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_R * np.arcsin(np.sqrt(a))


def nearest(regions, er_pts, k=1):
    """각 지역에서 가장 가까운 응급실 k곳의 (거리km, 인덱스).
    지역 × 응급실 거리표(행렬)를 numpy로 한 번에 계산한 뒤 작은 순서로 고른다."""
    d = haversine_km(regions["lat"].values[:, None], regions["lon"].values[:, None],
                     er_pts["lat"].values[None, :], er_pts["lon"].values[None, :])
    idx = np.argsort(d, axis=1)[:, :k]
    return np.take_along_axis(d, idx, axis=1), idx


def compute(regions, er, crit_key, extra=None):
    """골든타임 판정 결과를 붙인 DataFrame을 돌려준다.
    extra: 신설 응급실 좌표 DataFrame(lat, lon) - 시뮬레이션용"""
    c = CRITERIA[crit_key]
    pts = er[er["grade"].isin(c["grades"])][["name", "lat", "lon"]].reset_index(drop=True)
    if extra is not None and len(extra):
        pts = pd.concat([pts, extra[["name", "lat", "lon"]]], ignore_index=True)
    km, idx = nearest(regions, pts)
    out = regions.copy()
    out["km"] = km[:, 0]
    out["minutes"] = km_to_min(out["km"])
    out["nearest_er"] = pts.loc[idx[:, 0], "name"].values
    out["blind"] = out["minutes"] > c["limit"]
    return out


def summary(df):
    tot, blind = df["pop"].sum(), df.loc[df["blind"], "pop"].sum()
    old_tot, old_blind = df["pop65"].sum(), df.loc[df["blind"], "pop65"].sum()
    ch_tot, ch_blind = df["pop014"].sum(), df.loc[df["blind"], "pop014"].sum()
    w_avg = np.average(df["minutes"], weights=df["pop"]) if tot else 0
    return {
        "pop": int(tot), "blind_pop": int(blind), "blind_rate": blind / tot * 100 if tot else 0,
        "old_blind": int(old_blind), "old_blind_rate": old_blind / old_tot * 100 if old_tot else 0,
        "child_blind": int(ch_blind), "child_blind_rate": ch_blind / ch_tot * 100 if ch_tot else 0,
        "avg_min": w_avg, "n_regions": len(df), "n_blind_regions": int(df["blind"].sum()),
    }


def lookup(regions, er, rid, k=3):
    """우리 동네 조회: 선택 지역에서 가까운 응급의료기관 k곳 (등급 무관)."""
    row = regions[regions["rid"] == rid]
    if row.empty:
        return []
    km, idx = nearest(row, er.reset_index(drop=True), k=k)
    res = []
    for d, i in zip(km[0], idx[0]):
        e = er.iloc[i]
        res.append({"name": e["name"], "grade": e["grade"], "km": d, "min": km_to_min(d)})
    return res


def recommend(regions, er, crit_key, n=5, sido=None):
    """사각지대 인구를 가장 많이 줄이는 신설 위치를 하나씩 고르는 탐욕(greedy) 알고리즘.
    후보지 = 현재 사각지대에 있는 지역들의 대표 좌표."""
    limit = CRITERIA[crit_key]["limit"]
    base = compute(regions, er, crit_key)
    scope = base if sido in (None, "", "전체") else base[base["sido"] == sido]
    cur = scope["minutes"].values.copy()
    pop = scope["pop"].values
    cands = scope[scope["blind"]]
    if cands.empty:
        return []
    # 후보지 × 지역 이동시간 행렬
    m = km_to_min(haversine_km(cands["lat"].values[:, None], cands["lon"].values[:, None],
                               scope["lat"].values[None, :], scope["lon"].values[None, :]))
    picks, used = [], set()
    for _ in range(n):
        new_min = np.minimum(cur[None, :], m)
        saved = ((cur > limit) & (new_min <= limit)) @ pop      # 후보지별로 구제되는 인구
        for u in used:
            saved[u] = -1
        best = int(np.argmax(saved))
        if saved[best] <= 0:
            break
        used.add(best)
        cur = new_min[best]
        r = cands.iloc[best]
        picks.append({"rid": r["rid"], "lat": r["lat"], "lon": r["lon"], "saved": int(saved[best])})
    return picks


def new_er_frame(rows):
    return pd.DataFrame([{"name": f"[신설] {r['rid']}", "lat": r["lat"], "lon": r["lon"]} for r in rows])
