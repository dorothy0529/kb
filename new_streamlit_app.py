# streamlit_app.py
import streamlit as st
import random
import time
from datetime import datetime

st.set_page_config(page_title="AI Adaptive PayShield - Web Prototype", page_icon="💳", layout="centered")
st.markdown(
    """
    <style>
    /* 모든 입력창(숫자, 텍스트) 스타일 변경 */
    input, textarea {
        background-color: white !important;
        color: black !important;
    }

    /* Streamlit의 기본 input wrapper에도 적용 */
    div[data-baseweb="input"] input {
        background-color: white !important;
        color: black !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.markdown(
    """
    <style>
    * {
        color: black !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

#배경색 및 주요 컬러 적용
st.markdown(
    """
    <style>
    body, .stApp {
        background-color: #f5b800 !important;
    }
    .stButton>button, .stTextInput>div>input, .stNumberInput>div>input, .stCheckbox>label {
        background-color: #FFFFFF !important;
        color: #222 !important;
    }
    .stForm, .stFormContainer, .st-cb, .st-cg {
        background-color: #FFFFFF !important;
        border-radius: 12px;
        padding: 1em;
    }
    </style>
    """,
    unsafe_allow_html=True,
)
st.markdown(
    """
    <style>
    /* 버튼 기본 스타일: 흰 배경 + 회색 테두리 */
    div.stButton > button {
        background-color: white !important;
        color: black !important;
        border: 1px solid #ddd !important;
    }

    /* 마우스 오버 시: 테두리만 검정색 */
    div.stButton > button:hover {
        border: 1px solid black !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# ---------------------------
# 유틸: 세션 상태 초기화
# ---------------------------
def init_state():
    defaults = {
        "risk_score": None,
        "bucket": None,  # low / mid / high
        "simple_captcha": None,
        "complex_captcha": None,
        "order_captcha": None,
        "puzzle_passed": False,
        "txn_confirmed": False,
        "seed": random.randint(1, 10_000),
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()
random.seed(st.session_state.seed)

# ---------------------------
# 0) 결제 요청 입력 폼
# ---------------------------
st.title("AI Adaptive PayShield – Web Prototype")
st.caption("AI가 실시간으로 본인인증 난이도를 조절하고, 퍼즐 통과 시 결제 페이지를 노출합니다.")

with st.form("txn_form", clear_on_submit=False):
    st.subheader("0) 결제 요청 입력")
    col1, col2 = st.columns(2)
    with col1:
        amount = st.number_input("결제 금액(원)", min_value=1000, step=1000, value=35000)
        country = st.text_input("결제 국가/지역(예: US, JP, KR)", value="US")
        hour = st.slider("결제 시간(현지 기준 시)", 0, 23, value=datetime.now().hour)
    with col2:
        freq = st.number_input("최근 30일 결제 횟수", min_value=0, value=8)
        avg_amt = st.number_input("최근 30일 평균 결제금액(원)", min_value=0, value=18000)
        device_change = st.checkbox("새 디바이스/브라우저로 접속", value=False)

    st.markdown("**네트워크/기술 신호**")
    col3, col4 = st.columns(2)
    with col3:
        vpn = st.checkbox("VPN/프록시 사용 의심", value=False)
        ip_geo_shift = st.checkbox("평소 지역과 다른 IP/국가", value=True)
    with col4:
        bot_like = st.checkbox("비정상 입력 속도/패턴 감지(봇 의심)", value=False)

    st.markdown("**선택: 데모용 수동 가중치**")
    manual_bias = st.slider("AI 위험도 보정(+/-)", -20, 20, 0)

    submitted = st.form_submit_button("1) 위험 분석 실행")

# ---------------------------
# 1) 거래 위험성 분석 (AI API 자리)
# ---------------------------
def mock_ai_risk_engine(features: dict) -> float:
    """
    실제 서비스에선 여기서 AI API를 호출합니다.
    예시:
        resp = requests.post(AI_URL, json=features, timeout=2)
        return resp.json()["risk_score"]
    지금은 데모용 휴리스틱 + 난수 약간을 사용합니다.
    """
    score = 0.0
    # 금액이 평균보다 많이 크면 리스크↑
    if features["amount"] > max(1, features["avg_amt"]) * 3:
        score += 25
    elif features["amount"] > max(1, features["avg_amt"]) * 1.5:
        score += 12

    # 해외/지역 변경
    if features["ip_geo_shift"]:
        score += 20
    # 시간대(심야) 리스크
    if features["hour"] <= 5 or features["hour"] >= 23:
        score += 8

    # 사용 패턴
    if features["freq"] == 0:
        score += 10
    elif features["amount"] > 50_000 and features["freq"] < 3:
        score += 8

    # 기술 신호
    if features["vpn"]:
        score += 18
    if features["device_change"]:
        score += 12
    if features["bot_like"]:
        score += 15

    # 약간의 랜덤성
    score += random.uniform(-3, 3)

    # 데모용 수동 보정
    score += features.get("manual_bias", 0)

    # 0~100로 클램프
    return float(max(0, min(100, round(score, 1))))

if submitted:
    feats = dict(
        amount=amount,
        country=country.strip().upper(),
        hour=int(hour),
        freq=int(freq),
        avg_amt=float(avg_amt),
        device_change=bool(device_change),
        vpn=bool(vpn),
        ip_geo_shift=bool(ip_geo_shift),
        bot_like=bool(bot_like),
        manual_bias=int(manual_bias),
    )
    st.session_state.risk_score = mock_ai_risk_engine(feats)

    # 버킷 결정
    rs = st.session_state.risk_score
    if rs <= 30:
        st.session_state.bucket = "low"
    elif rs <= 60:
        st.session_state.bucket = "mid"
    else:
        st.session_state.bucket = "high"

    # 퍼즐 초기화
    st.session_state.puzzle_passed = False
    st.session_state.txn_confirmed = False
    st.session_state.simple_captcha = None
    st.session_state.complex_captcha = None
    st.session_state.order_captcha = None
    st.success("위험 분석 완료! 아래 단계로 진행하세요.")

# ---------------------------
# 2) Risk Score 표시
# ---------------------------
if st.session_state.risk_score is not None:
    st.subheader("2) 거래 위험 점수")
    rs = st.session_state.risk_score
    st.metric(label="Risk Score (0~100)", value=rs)
    st.progress(int(rs))

    bucket = st.session_state.bucket
    if bucket == "low":
        st.info("구간: 0~30 (저위험) → **간단한 CAPTCHA**")
    elif bucket == "mid":
        st.warning("구간: 31~60 (중위험) → **복합 퍼즐**")
    else:
        st.error("구간: 61~100 (고위험) → **고난도 퍼즐(말 순서 맞추기)**")

# ---------------------------
# 3) 구간별 퍼즐
# ---------------------------

def simple_math_captcha():
    """간단한 산술 문제"""
    if st.session_state.simple_captcha is None:
        a, b = random.randint(10, 50), random.randint(1, 9)
        st.session_state.simple_captcha = (a, b, a + b)

    a, b, ans = st.session_state.simple_captcha
    st.write("### 3-A) 간단한 CAPTCHA")
    st.write(f"문제: **{a} + {b} = ?**")
    user = st.number_input("정답 입력", min_value=0, step=1)
    if st.button("정답 확인", key="simple_check"):
        if user == ans:
            st.success("정답입니다.")
            return True
        else:
            st.error("오답입니다. 다시 시도하세요.")
    return False

def complex_puzzle():
    """
    복합 퍼즐: (1) 산술 소문제 + (2) 의미 분류 소문제(동물 고르기)
    두 문제 모두 맞아야 통과.
    """
    if st.session_state.complex_captcha is None:
        # 산술
        a, b = random.randint(20, 60), random.randint(5, 15)
        # 의미 분류
        options = ["사과", "호랑이", "자동차", "토끼", "책상", "기차", "고래"]
        animals = {"호랑이", "토끼", "고래"}
        random.shuffle(options)
        st.session_state.complex_captcha = {
            "arith": (a, b, a - b),
            "opts": options,
            "answer_set": animals,
        }

    data = st.session_state.complex_captcha
    a, b, ans = data["arith"]
    st.write("### 3-B) 복합 퍼즐")
    st.write(f"소문제 1) **{a} - {b} = ?**")
    u1 = st.number_input("정답(정수)", key="arith_input", step=1)

    st.write("소문제 2) 다음 중 **동물**만 모두 고르세요.")
    u2 = st.multiselect("모두 선택", data["opts"], key="sem_sel")

    if st.button("정답 확인", key="complex_check"):
        ok1 = (u1 == ans)
        ok2 = (set(u2) == data["answer_set"])
        if ok1 and ok2:
            st.success("정답입니다. 통과!")
            return True
        else:
            if not ok1:
                st.error("소문제 1 오답")
            if not ok2:
                st.error("소문제 2 오답(동물만 정확히 선택)")
    return False

def high_order_sentence_puzzle():
    """
    고난도 퍼즐: '말(단어) 순서 맞추기'
    - 타겟 문장을 토큰으로 분해하고 순서를 섞음
    - 사용자는 올바른 순서로 클릭(= multiselect의 선택 순서) 해야 함
    """
    if st.session_state.order_captcha is None:
        target = "나는 오늘 35000원을 홍길동에게 보냅니다"
        tokens = target.split()
        shuffled = tokens[:]
        random.shuffle(shuffled)
        st.session_state.order_captcha = {
            "target": target,
            "tokens": tokens,
            "shuffled": shuffled,
        }

    data = st.session_state.order_captcha
    st.write("### 3-C) 고난도 퍼즐 (말 순서 맞추기)")
    st.caption("아래 토큰을 **올바른 순서**로 선택하세요. (선택한 순서가 정답으로 채점됩니다)")
    sel = st.multiselect("토큰을 순서대로 클릭", data["shuffled"], key="order_sel")

    if st.button("정답 확인", key="order_check"):
        user_sentence = " ".join(sel)
        if user_sentence == data["target"]:
            st.success("정답입니다. 통과!")
            return True
        else:
            st.error("오답입니다. 다시 시도하세요.")
            st.info(f"힌트: 총 {len(data['tokens'])}개의 토큰입니다.")
    return False

# 퍼즐 실행
if st.session_state.risk_score is not None and not st.session_state.puzzle_passed:
    bucket = st.session_state.bucket
    if bucket == "low":
        if simple_math_captcha():
            st.session_state.puzzle_passed = True
    elif bucket == "mid":
        if complex_puzzle():
            st.session_state.puzzle_passed = True
    else:
        if high_order_sentence_puzzle():
            st.session_state.puzzle_passed = True

# ---------------------------
# 4) 퍼즐 통과 시 결제 페이지
# ---------------------------
if st.session_state.puzzle_passed and not st.session_state.txn_confirmed:
    st.success("퍼즐 인증을 통과했습니다.")
    st.subheader("4) 결제 페이지")
    st.write("결제 내용을 확인하세요.")

    with st.form("pay_form"):
        st.text_input("카드 소유자명", value="홍길동")
        st.text_input("카드 번호(마스킹)", value="4111-****-****-1234")
        st.text_input("청구 금액(원)", value=f"{amount:,}", disabled=True)
        st.text_input("가맹점/국가", value=f"{country}", disabled=True)
        agree = st.checkbox("위 결제 요청을 승인합니다.")
        pay = st.form_submit_button("결제 승인")

    if pay:
        if not agree:
            st.error("승인 체크를 먼저 해주세요.")
        else:
            st.session_state.txn_confirmed = True
            with st.spinner("결제 처리 중..."):
                time.sleep(1.2)
            st.success("결제가 완료되었습니다. 영수증이 발급됩니다.")

# 리셋 버튼
st.divider()
if st.button("새 결제 시나리오 시작"):
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.rerun()
