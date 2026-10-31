"""가짜 지원자 데이터. planted/db.sql과 같은 규칙으로 만든다."""

_LAST = "김이박최정강조윤장임"
_FIRST = [
    "민준", "서연", "도윤", "하은", "시우", "지우", "주원", "서윤", "예준", "지민",
    "건우", "수아", "현우", "채원", "우진", "다은", "선우", "예은", "연우", "소율",
]
_JOBS = ["백엔드 개발자", "프런트엔드 개발자", "데이터 분석가", "UX 디자이너", "인사 담당자", "영업 관리자"]


def applicant(i: int) -> dict:
    return {
        "id": i,
        "name": _LAST[i % 10] + _FIRST[i % 20],
        "email": f"applicant{i:03d}@example.com",
        "phone": f"010-0000-{i:04d}",
        "birth": f"19{88 + i % 10}-0{1 + i % 9}-1{i % 9}",
        "desired_job": _JOBS[i % len(_JOBS)],
        "career_years": i % 12,
        "resume_file": f"resumes/{i:04d}.pdf",
    }


APPLICANT_COUNT = 40
APPLICANTS = [applicant(i) for i in range(1, APPLICANT_COUNT + 1)]
