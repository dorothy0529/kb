# streamlit_app.py
import os
import json
import random
import time
from datetime import datetime

import streamlit as st
from openai import OpenAI

st.set_page_config(page_title="AI Adaptive PayShield – OpenAI Risk", page_icon="💳", layout="centered")

# ---------------------------
# OpenAI 클라이언트
# ---------------------------
# 환경변수 OPENAI_API_KEY가 반드시 설정되어 있어야 합니다.
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

MODEL_NAME = os.getenv("PAYSHIELD_MODEL", "gpt-4o-mini")  # 필요시 gpt-4o 등으로 교체
TEMPERATURE = float(os.getenv("PAYSHIELD_TEMP", "0.2"))

# ---------------------------
# 세션 상태 초기화
# ---------------------------
def init_state():
    defaults = dict(
        risk_score=None, bucket=None, api_error=None,
        simple_captcha=None, complex_captcha=None, order_captcha=None,
        puzzle_passed=False, txn_confirmed=False,
        seed=random.randint(1, 10_000)
    )
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()
random.seed(st.session_state.seed)

st.title("AI Adaptive PayShield – Web Prototype (OpenAI Risk)")
st.caption("OpenAI Responses API로 위험 점수를 계산하고, 점수 구간별 퍼즐 인증 후 결제 화면을 노출합니다.")

# ---------------------------
# 0) 결제 요청 입력 폼
# ---------------------------
with st.form("txn_form", clear_on_submit=False):
    st.subheader("0) 결제 요청 입력")
    col1, col2 = st.columns(2)
    with col1:
        amount = st.number_input("결제 금액(원)", min_value=1000, step=1000, value=35000)
        country = st.text_input("결제 국가/지역(예: KR, US, JP)", value="US")
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

    submitted = st.form_submit_button("1) OpenAI로 위험 분석 실행")

# ---------------------------
# OpenAI 구조화 출력(JSON) 스키마
# ---------------------------
RISK_SCHEMA = {
    "name": "RiskSchema",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "risk_score": {"type": "number", "minimum": 0, "maximum": 100},
            "bucket": {"type": "string", "enum": ["low", "mid", "high"]},
            "reasons": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 2,
                "maxItems": 5
            },
            "indicators": {
                "type": "object",
                "additionalProperties": True,
                "properties": {
                    "amount_vs_avg": {"type": "number"},
                    "night": {"type": "boolean"},
                    "country_nonKR": {"type": "boolean"},
                    "ip_geo_shift": {"type": "boolean"},
                    "vpn": {"type": "boolean"},
                    "device_change": {"type": "boolean"},
                    "bot_like": {"type": "boolean"},
                }
            }
        },
        "required": ["risk_score", "bucket", "reasons", "indicators"]
    },
    "strict": True
}

def build_prompt(features: dict) -> str:
    """모델에게 줄 간단한 산정 가이드 + 입력값."""
    return f"""
너는 온라인 결제 사기 탐지 보조 모델이다.
다음 피처로 0~100 사이의 위험점수를 산출하고, 버킷(low<=30, mid<=60, high>60)을 정하라.
가중치 가이드(예시):
- 평균 대비 금액 비율(ratio=amount/max(1,avg_amt)) ↑ → 점수↑ (ratio>=3는 강하게↑)
- 해외/한국 외(country != KR), IP 위치 급변(ip_geo_shift) → 점수↑
- VPN/프록시(vpn), 새 디바이스(device_change), 봇 유사 입력(bot_like) → 점수↑
- 심야 시간대(hour<=5 or hour>=23) → 점수 소폭↑
- 빈도(freq)가 낮은데 금액이 크면 → 추가↑
반드시 0~100 범위로 클램프하고, 이유(reasons)에는 핵심 2~5가지를 짧게 한글로 써라.

입력:
amount={features['amount']}, avg_amt={features['avg_amt']}, freq={features['freq']},
hour={features['hour']}, country={features['country']},
ip_geo_shift={features['ip_geo_shift']}, vpn={features['vpn']},
device_change={features['device_change']}, bot_like={features['bot_like']}
"""

def compute_risk_with_openai(features: dict) -> dict:
    """
    OpenAI Responses API를 호출하여
    {risk_score, bucket, reasons[], indicators{...}} 딕셔너리를 반환.
    """
    resp = client.responses.create(
        model=MODEL_NAME,
        instructions="Return only JSON that matches the provided schema.",
        input=build_prompt(features),
        temperature=TEMPERATURE,
        response_format={"type": "json_schema", "json_schema": RISK_SCHEMA},
    )
    # structured outputs → JSON 문자열
    data = json.loads(resp.output_text)
    # 안전 클램프/보정
    rs = float(max(0, min(100, data.get("risk_score", 0))))
    bucket = data.get("bucket") or ("low" if rs <= 30 else "mid" if rs <= 60 else "high")
    data["risk_score"] = round(rs, 1)
    data["bucket"] = bucket
    return data

# ---------------------------
# 1) 위험 분석 실행
# ---------------------------
if submitted:
    features = dict(
        amount=float(amount),
        avg_amt=float(avg_amt),
        freq=int(freq),
        hour=int(hour),
        country=country.strip().upper(),
        ip_geo_shift=bool(ip_geo_shift),
        vpn=bool(vpn),
        device_change=bool(device_change),
        bot_like=bool(bot_like),
    )
    try:
        st.session_state.api_error = None
        with st.spinner("OpenAI에 요청 중..."):
            data = compute_risk_with_openai(features)

        st.session_state.risk_score = data["risk_score"]
        st.session_state.bucket = data["bucket"]
        st.success("위험 분석 완료! 아래 단계로 진행하세요.")
        # 퍼즐 리셋
        st.session_state.puzzle_passed = False
        st.session_state.txn_confirmed = False
        st.session_state.simple_captcha = None
        st.session_state.complex_captcha = None
        st.session_state.order_captcha = None

        # 디버그/설명용
        with st.expander("모델 근거(Reasons / Indicators) 보기"):
            st.write(data.get("reasons", []))
            st.json(data.get("indicators", {}))
    except Exception as e:
        st.session_state.api_error = str(e)
        st.error(f"OpenAI 호출 실패: {e}")

if st.session_state.api_error:
    st.stop()

# ---------------------------
# 2) Risk Score 표시
# ---------------------------
if st.session_state.risk_score is not None:
    st.subheader("2) 거래 위험 점수")
    rs = st.session_state.risk_score
    st.metric("Risk Score (0~100)", rs)
    st.progress(int(min(100, max(0, rs))))

    if st.session_state.bucket == "low":
        st.info("구간: 0~30 (저위험) → **간단한 CAPTCHA**")
    elif st.session_state.bucket == "mid":
        st.warning("구간: 31~60 (중위험) → **복합 퍼즐**")
    else:
        st.error("구간: 61~100 (고위험) → **고난도 퍼즐(말 순서 맞추기)**")

# ---------------------------
# 3) 구간별 퍼즐
# ---------------------------
def simple_math_captcha():
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
    if st.session_state.complex_captcha is None:
        a, b = random.randint(20, 60), random.randint(5, 15)
        options = ["사과", "호랑이", "자동차", "토끼", "책상", "기차", "고래"]
        animals = {"호랑이", "토끼", "고래"}
        random.shuffle(options)
        st.session_state.complex_captcha = {"arith": (a, b, a - b), "opts": options, "answer_set": animals}
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
            if not ok1: st.error("소문제 1 오답")
            if not ok2: st.error("소문제 2 오답(동물만 정확히 선택)")
    return False

def high_order_sentence_puzzle():
    if st.session_state.order_captcha is None:
        target = "나는 오늘 35000원을 홍길동에게 보냅니다"
        tokens = target.split()
        shuffled = tokens[:]; random.shuffle(shuffled)
        st.session_state.order_captcha = {"target": target, "tokens": tokens, "shuffled": shuffled}
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

if st.session_state.risk_score is not None and not st.session_state.puzzle_passed:
    bucket = st.session_state.bucket
    if bucket == "low":
        if simple_math_captcha(): st.session_state.puzzle_passed = True
    elif bucket == "mid":
        if complex_puzzle(): st.session_state.puzzle_passed = True
    else:
        if high_order_sentence_puzzle(): st.session_state.puzzle_passed = True

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
        st.text_input("청구 금액(원)", value=f"{int(amount):,}", disabled=True)
        st.text_input("가맹점/국가", value=f"{country}", disabled=True)
        agree = st.checkbox("위 결제 요청을 승인합니다.")
        pay = st.form_submit_button("결제 승인")
    if pay:
        if not agree:
            st.error("승인 체크를 먼저 해주세요.")
        else:
            st.session_state.txn_confirmed = True
            with st.spinner("결제 처리 중..."):
                time.sleep(1.0)
            st.success("결제가 완료되었습니다. 영수증이 발급됩니다.")

st.divider()
if st.button("새 결제 시나리오 시작"):
    for k in list(st.session_state.keys()): del st.session_state[k]
    st.rerun()
