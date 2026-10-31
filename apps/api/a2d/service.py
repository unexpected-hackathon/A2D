"""API가 쓰는 서비스 층: 도메인·소유권, 점검 실행, 점수 계산, 대시보드·발견·조치 가이드·기록.

점검 엔진(engine/)은 자산과 발견만 넘기고, 발견 ID·점수·오늘 할 일·조치 가이드는 여기서 만든다.
"""

from __future__ import annotations

import asyncio
import logging
import re
import secrets
from typing import Any

import dns.asyncresolver
import dns.exception
import dns.resolver

from . import agents
from .agents import handlers as attack_handlers
from .catalog import CHECKS, FIX_MINUTES, GUIDES, SITUATIONS, check_name
from .config import Settings
from .engine.base import Budget, Engine, EngineContext, EngineError, RawAsset, RawFinding, ScanStopped
from .engine.net import DnsResolver
from .errors import ApiError, not_found, validation
from .scoring import (
    CONFIDENCE_FACTOR,
    Scored,
    grade,
    org_formula,
    org_risk_raw,
    pick_today_tasks,
    risk_formula,
    risk_raw,
    round_half_up,
    severity,
)
from .store import Store
from .timeutil import now_iso

log = logging.getLogger("a2d")

FINISHED = ("done", "stopped")
TERMINAL = ("done", "stopped", "failed")

# 추가 점검(Attack 에이전트)을 건너뛰거나 일부만 했을 때 화면에 보이는 문장. 원인은 attack.reason에 남는다.
# 가짜 엔진(fixture)은 시연 화면에 그대로 나오므로 원인을 문장에 쓰지 않는다.
ATTACK_MESSAGES = {
    "llm_not_configured": "AI 서버가 연결되지 않아 추가 점검을 건너뛰었습니다. 기본 점검 결과로 점수를 냈습니다.",
    "llm_unavailable": "AI 서버가 응답하지 않아 추가 점검을 건너뛰었습니다. 기본 점검 결과로 점수를 냈습니다.",
    "fixture_engine": "추가 점검을 건너뛰고 기본 점검 결과로 점수를 냈습니다.",
    "no_handlers": "추가 점검을 건너뛰고 기본 점검 결과로 점수를 냈습니다.",
    "llm_interrupted": "추가 점검 중 AI 서버 응답이 끊겨 일부만 확인했습니다.",
    "error": "추가 점검 중 오류가 나 기본 점검 결과로 점수를 냈습니다.",
}


def attack_state(status: str, reason: str | None = None) -> dict:
    """점검 결과의 attack 필드. status: pending·running·done·skipped·failed·stopped."""
    return {"status": status, "reason": reason, "message": ATTACK_MESSAGES.get(reason) if reason else None}
STAGE_NAMES = {
    "queued": "대기",
    "discovering": "자산 찾는 중",
    "checking": "기본 점검",
    "agent": "추가 점검",
    "scoring": "점수 계산",
    "reporting": "조치 가이드 작성",
    "done": "완료",
    "stopped": "중지됨",
    "failed": "실패",
}
SEVERITIES = ("critical", "high", "medium", "low", "info")
REPORT_TIMEOUT_SEC = 150  # 조치 가이드 LLM 생성 전체 상한. 넘으면 기본 가이드로 나간다
VERIFY_LABEL = "_a2d-verify"
_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")


def normalize_domain(raw: Any) -> str:
    if not isinstance(raw, str):
        raise validation("도메인을 입력해 주세요.")
    d = raw.strip().lower().rstrip(".")
    if "://" in d or "/" in d or ":" in d or " " in d:
        raise validation("주소가 아니라 도메인 이름만 입력해 주세요. 예: example.com")
    try:
        d = d.encode("idna").decode("ascii")
    except UnicodeError:
        raise validation("도메인 형식이 올바르지 않습니다.") from None
    labels = d.split(".")
    if len(d) > 253 or len(labels) < 2 or not all(_LABEL.match(x) for x in labels):
        raise validation("도메인 형식이 올바르지 않습니다. 예: example.com")
    if labels[-1].isdigit():
        raise validation("IP 주소는 등록할 수 없습니다. 도메인 이름을 입력해 주세요.")
    return d


class Service:
    def __init__(self, settings: Settings, store: Store, engine: Engine, llm: agents.LlmClient):
        self.s = settings
        self.store = store
        self.engine = engine
        self.llm = llm
        self._tasks: dict[str, asyncio.Task] = {}
        self._budgets: dict[str, Budget] = {}
        self._live: dict[str, dict] = {}  # 진행 중인 점검의 최신 상태(DB에도 쓴다)

    # ================================================================ 시작·종료

    def recover(self) -> None:
        """서버가 꺼질 때 돌던 점검은 실패로 표시한다."""
        for scan in self.store.running_scans():
            scan.update(status="failed", finished_at=now_iso(),
                        error_message="서버가 다시 시작되어 점검이 중단되었습니다.")
            scan["stage"] = {**scan.get("stage", {}), "name": STAGE_NAMES["failed"]}
            self.store.save_scan(scan)

    async def shutdown(self) -> None:
        for b in self._budgets.values():
            b.stop_requested = True
        for t in list(self._tasks.values()):
            t.cancel()

    # ================================================================ 도메인 (FR-01)

    def _domain_or_404(self, domain_id: str) -> dict:
        d = self.store.get_domain(domain_id)
        if d is None:
            raise not_found("도메인")
        return d

    @staticmethod
    def domain_api(d: dict) -> dict:
        return {
            "domain_id": d["domain_id"],
            "domain": d["domain"],
            "verify_status": d["verify_status"],
            "txt_record": {"name": f"{VERIFY_LABEL}.{d['domain']}", "value": d["txt_value"]},
            "verified_at": d.get("verified_at"),
            "created_at": d["created_at"],
        }

    def register_domain(self, raw: Any) -> tuple[dict, bool]:
        domain = normalize_domain(raw)
        d = self.store.create_domain(domain, {
            "verify_status": "pending",
            "txt_value": f"a2d-verify={secrets.token_hex(8)}",
            "verified_at": None,
            "created_at": now_iso(),
        })
        created = bool(d.pop("_created", False))
        return self.domain_api(d), created

    def get_domain(self, domain_id: str) -> dict:
        return self.domain_api(self._domain_or_404(domain_id))

    def list_domains(self) -> list[dict]:
        return [self.domain_api(d) for d in self.store.list_domains()]

    def delete_domain(self, domain_id: str) -> None:
        self._domain_or_404(domain_id)
        running = self._running(domain_id)
        if running:
            raise ApiError(409, "SCAN_IN_PROGRESS",
                           "진행 중인 점검이 있어 도메인을 삭제할 수 없습니다. 점검을 멈춘 뒤 다시 시도해 주세요.",
                           scan_id=running["scan_id"])
        for sid in self.store.delete_domain(domain_id):
            self._live.pop(sid, None)
            self._budgets.pop(sid, None)
            self._tasks.pop(sid, None)

    async def _lookup_txt(self, name: str) -> list[str] | None:
        """TXT 값 목록. 이름이 없으면 [], 조회 자체가 실패하면 None."""
        if self.s.dns_servers:
            r = dns.asyncresolver.Resolver(configure=False)
            ips, port = [], 53
            for srv in self.s.dns_servers:
                host, _, p = srv.rpartition(":") if srv.count(":") == 1 else (srv, "", "")
                ips.append(host)
                port = int(p) if p else port
            r.nameservers, r.port = ips, port
        else:
            r = dns.asyncresolver.Resolver()
        r.lifetime = 10.0
        try:
            ans = await r.resolve(name, "TXT")
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            return []
        except (dns.exception.Timeout, dns.resolver.NoNameservers):
            return None
        return [b"".join(x.strings).decode("utf-8", "replace") for x in ans]

    async def verify_domain(self, domain_id: str) -> dict:
        d = self._domain_or_404(domain_id)
        reason = None
        if d["verify_status"] != "verified":
            if self.s.verify_mode == "trust":  # TXT 확인을 끈 상태: 조회 없이 통과
                ok = True
            else:
                values = await self._lookup_txt(f"{VERIFY_LABEL}.{d['domain']}")
                ok = bool(values) and d["txt_value"] in values
                if values is None:
                    reason = "DNS 조회에 실패했습니다. 잠시 뒤 다시 시도해 주세요."
                elif not values:
                    reason = "TXT 레코드를 찾지 못했습니다. DNS 반영에 몇 분이 걸릴 수 있습니다."
                elif not ok:
                    reason = "TXT 레코드 값이 발급한 값과 다릅니다. 값을 그대로 복사해 넣어 주세요."
            if ok:
                d.update(verify_status="verified", verified_at=now_iso())
            else:
                d["verify_status"] = "failed"
            self.store.save_domain(d)
        return {"domain_id": d["domain_id"], "verify_status": d["verify_status"],
                "verified_at": d.get("verified_at"), "reason": reason}

    # ================================================================ 점검 실행 (FR-09, NFR-03)

    def _scan_or_404(self, scan_id: str) -> dict:
        scan = self._live.get(scan_id) or self.store.get_scan(scan_id)
        if scan is None:
            raise not_found("점검")
        return scan

    def _finished_or_409(self, scan_id: str) -> dict:
        scan = self._scan_or_404(scan_id)
        if scan["status"] not in FINISHED:
            raise ApiError(409, "SCAN_NOT_FINISHED", "점검이 아직 끝나지 않았습니다.")
        return scan

    def _latest_finished(self, domain_id: str) -> dict | None:
        scans = self.store.scans_for(domain_id, FINISHED)
        return scans[-1] if scans else None

    def _running(self, domain_id: str) -> dict | None:
        for scan in self.store.scans_for(domain_id):
            if scan["status"] not in TERMINAL:
                return scan
        return None

    def start_scan(self, domain_id: str) -> dict:
        d = self._domain_or_404(domain_id)
        if d["verify_status"] != "verified":
            raise ApiError(409, "DOMAIN_NOT_VERIFIED", "도메인 소유권이 확인되지 않아 점검을 시작할 수 없습니다.")
        running = self._running(domain_id)
        if running:
            raise ApiError(409, "SCAN_IN_PROGRESS", "이미 진행 중인 점검이 있습니다.", scan_id=running["scan_id"])
        prev = self._latest_finished(domain_id)
        budget = Budget(self.s.request_limit, self.s.tool_call_limit, self.s.time_limit_sec)
        scan = self.store.create_scan(domain_id, {
            "status": "queued",
            "stage": {"name": STAGE_NAMES["queued"], "done": 0, "total": 0},
            "budget": budget.to_api(),
            # 가짜 엔진의 시나리오 회차. 끝까지 돈 점검만 센다
            "round": len(self.store.scans_for(domain_id, ("done",))) + 1,
            "previous_scan_id": prev["scan_id"] if prev else None,
            "started_at": now_iso(),
            "finished_at": None,
            "safety_score": None,
            "grade": None,
            "error_message": None,
            "attack": attack_state("pending"),
        })
        self._budgets[scan["scan_id"]] = budget
        self._live[scan["scan_id"]] = scan
        self._tasks[scan["scan_id"]] = asyncio.get_running_loop().create_task(self._run(scan["scan_id"], d))
        return {"scan_id": scan["scan_id"], "status": "queued", "previous_scan_id": scan["previous_scan_id"]}

    def _save_live(self, scan: dict) -> None:
        b = self._budgets.get(scan["scan_id"])
        if b:
            scan["budget"] = b.to_api()
        self.store.save_scan(scan)

    async def _run(self, scan_id: str, domain: dict) -> None:
        scan = self._live[scan_id]
        budget = self._budgets[scan_id]
        domain_id = domain["domain_id"]
        assets: dict[str, dict] = {}  # host → 자산
        findings: dict[str, dict] = {}  # finding_id → 발견

        def set_stage(status: str, name: str, done: int, total: int) -> None:
            scan["status"] = status
            scan["stage"] = {"name": name, "done": done, "total": total}
            self._save_live(scan)

        def add_asset(a: RawAsset) -> str:
            asset_id = self.store.asset_id_for(domain_id, a.host.lower())
            assets[a.host.lower()] = {"asset_id": asset_id, **a.__dict__, "host": a.host.lower()}
            return asset_id

        def add_finding(f: RawFinding) -> tuple[str, str]:
            f.validate()
            host = f.host.lower()
            if host not in assets:
                raise ValueError(f"등록되지 않은 자산의 발견: {host}")
            asset_id = assets[host]["asset_id"]
            finding_id = self.store.finding_id_for(domain_id, f"{asset_id}|{f.check_id}|{f.location}")
            findings[finding_id] = {
                "finding_id": finding_id, "scan_id": scan_id, "check_id": f.check_id, "asset_id": asset_id,
                "location": f.location, "situation_key": f.situation, "evidence": f.evidence,
                "cves": f.cves, "detected_at": now_iso(),
            }
            return finding_id, asset_id

        def audit(actor: str, tool: str, args: dict, result_summary: str | None = None,
                  rejected: bool = False, reject_reason: str | None = None) -> None:
            self.store.add_audit(scan_id, {
                "at": now_iso(), "actor": actor, "tool": tool, "args": args,
                "result_summary": result_summary, "rejected": rejected, "reject_reason": reject_reason,
            })

        ctx = EngineContext(scan_id, domain["domain"], scan["round"], budget, set_stage, add_asset, add_finding, audit)
        # 기본 점검(엔진)이 끝까지 돌았는지. 추가 점검(에이전트) 중에 멈춘 것은 기본 점검 결과가 온전하다.
        engine_complete = False
        try:
            try:
                await self.engine.run(ctx)
                engine_complete = True
                set_stage("agent", STAGE_NAMES["agent"], 0, 1)
                try:
                    summary = {
                        "assets": [{"asset_id": a["asset_id"], "host": a["host"], "alias": a["alias"],
                                    "tags": a["tags"], "importance": a["importance"]}
                                   for a in assets.values()],
                        "findings": [{"asset_id": f["asset_id"], "check_id": f["check_id"],
                                      "situation": f["situation_key"]}
                                     for f in findings.values()],
                    }
                    scan["attack"] = attack_state("running")
                    reason = await self._run_attack(ctx, summary)
                    skipped = reason in ("llm_not_configured", "fixture_engine", "no_handlers", "llm_unavailable")
                    scan["attack"] = attack_state("skipped" if skipped else "done",
                                                  None if reason == agents.ATTACK_DONE else reason)
                except ScanStopped:
                    scan["attack"] = attack_state("stopped")
                    raise
                except Exception:  # 에이전트가 실패해도 기본 점검 결과로 진행한다
                    log.exception("추가 점검 실패: %s", scan_id)
                    scan["attack"] = attack_state("failed", "error")
                set_stage("agent", STAGE_NAMES["agent"], 1, 1)
            except ScanStopped as e:
                log.info("점검 %s 멈춤: %s", scan_id, e)

            # 사용자가 멈췄거나 기본 점검을 끝내지 못했으면(시간 초과) stopped다.
            final = "stopped" if budget.stop_requested or not engine_complete else "done"
            stage_name = STAGE_NAMES[final]
            if not engine_complete and not budget.stop_requested:
                stage_name = "중지됨 (제한 시간 초과)"
            scan["partial"] = not engine_complete

            set_stage("scoring", STAGE_NAMES["scoring"], 0, 1)
            self._materialize(scan, list(assets.values()), list(findings.values()), partial=not engine_complete)
            set_stage("scoring", STAGE_NAMES["scoring"], 1, 1)

            set_stage("reporting", STAGE_NAMES["reporting"], 0, 1)
            await self._build_report(scan, use_llm=final == "done")
            scan["status"] = final
            scan["stage"] = {**scan["stage"], "name": stage_name, "done": 1}
        except asyncio.CancelledError:
            scan.update(status="failed", error_message="서버가 종료되어 점검이 중단되었습니다.")
            scan["stage"] = {**scan["stage"], "name": STAGE_NAMES["failed"]}
            raise
        except EngineError as e:
            # 엔진이 이유를 밝힌 실패. 메시지를 그대로 error_message로 보여 준다(API 명세 GET /scans/{scan_id})
            log.warning("점검 실패: %s: %s", scan_id, e)
            scan.update(status="failed", error_message=str(e))
            scan["stage"] = {**scan["stage"], "name": STAGE_NAMES["failed"]}
        except Exception as e:
            log.exception("점검 실패: %s", scan_id)
            scan.update(status="failed", error_message=f"점검 중 오류가 발생했습니다: {type(e).__name__}")
            scan["stage"] = {**scan["stage"], "name": STAGE_NAMES["failed"]}
        finally:
            if scan.get("attack", {}).get("status") in ("pending", "running"):
                # 기본 점검을 끝내지 못해(실패·중지) 추가 점검까지 가지 못했다
                scan["attack"] = attack_state("skipped", None)
            scan["finished_at"] = now_iso()
            self._save_live(scan)
            self._live.pop(scan_id, None)
            self._budgets.pop(scan_id, None)
            self._tasks.pop(scan_id, None)

    async def _run_attack(self, ctx: EngineContext, summary: dict) -> str:
        """추가 점검(Attack 에이전트)을 돌린다. 실제 대상에 요청하는 핸들러는 진짜 엔진일 때만 붙인다.

        fixture 엔진은 시연용 가짜 결과라 대상에 요청을 보내지 않는다. 그래서 핸들러를 붙이지 않고,
        run_attack은 핸들러가 없으면 추가 점검을 건너뛴다(도구 호출·LLM 요청도 하지 않는다).
        진짜 엔진(A2D_ENGINE=패키지.모듈:클래스)일 때만 점검용 httpx 클라이언트를 열어 핸들러를 끼운다.
        돌려주는 값은 끝난 이유다(agents.ATTACK_* 또는 "fixture_engine").
        """
        if not self.llm.configured:
            return agents.ATTACK_NOT_CONFIGURED
        if self.s.engine == "fixture":
            return "fixture_engine"
        resolve = DnsResolver(self.s.dns_servers).a if self.s.dns_servers else None  # 엔진과 같은 점검 DNS
        async with attack_handlers.open_client(resolve=resolve) as client:
            handlers = attack_handlers.build_attack_handlers(ctx, client)
            return await agents.run_attack(self.llm, ctx, summary, handlers=handlers)

    @staticmethod
    def scan_api(scan: dict) -> dict:
        return {
            "scan_id": scan["scan_id"],
            "domain_id": scan["domain_id"],
            "status": scan["status"],
            "stage": scan["stage"],
            "budget": scan["budget"],
            "started_at": scan["started_at"],
            "finished_at": scan["finished_at"],
            "safety_score": scan["safety_score"],
            "grade": scan["grade"],
            "error_message": scan["error_message"],
            "attack": scan.get("attack"),  # 이 필드가 생기기 전 점검은 null
        }

    def get_scan(self, scan_id: str) -> dict:
        scan = self._scan_or_404(scan_id)
        if scan_id in self._budgets:
            scan["budget"] = self._budgets[scan_id].to_api()
        return self.scan_api(scan)

    async def stop_scan(self, scan_id: str) -> dict:
        self._scan_or_404(scan_id)
        budget, task = self._budgets.get(scan_id), self._tasks.get(scan_id)
        if budget is not None:
            budget.stop_requested = True
        if task is not None:
            # 오래 붙잡지 않는다. 그 안에 끝나지 않으면 화면이 폴링으로 stopped를 받는다.
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=1)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
        return self.get_scan(scan_id)

    # ================================================================ 점수 (FR-05, FR-06)

    def _materialize(self, scan: dict, assets: list[dict], findings: list[dict], *, partial: bool = False) -> None:
        """엔진 결과를 점검 스냅숏으로 저장하고 점수를 계산한다.

        partial(기본 점검을 끝내지 못함)이면 이번에 다시 보지 못한 직전 자산·발견을 그대로 이어받는다.
        확인하지 못한 것을 '해결됨'·'사라짐'으로 보지 않기 위해서다. 새로 찾은 자산·발견은 그대로 반영한다.
        """
        prev = scan.get("previous_scan_id")
        prev_assets = {a["asset_id"]: a for a in self.store.scan_assets(prev)} if prev else {}
        out_assets = []
        for a in assets:
            out_assets.append({
                "asset_id": a["asset_id"], "alias": a["alias"], "host": a["host"], "url": a["url"],
                "found_by": a["found_by"], "tags": a["tags"],
                "auto_importance": {"value": a["importance"], "rule": a["importance_rule"]},
                "components": a["components"], "tls_version": a["tls_version"],
                "is_new": bool(prev) and a["asset_id"] not in prev_assets,
            })
        if partial and prev:
            seen_assets = {a["asset_id"] for a in out_assets}
            out_assets += [{**a, "is_new": False} for k, a in prev_assets.items() if k not in seen_assets]
            seen = {f["finding_id"] for f in findings}
            findings = findings + [{**f, "scan_id": scan["scan_id"]} for f in self.store.findings(prev)
                                   if f["finding_id"] not in seen]
        self._score(scan, out_assets, findings)

    def _score(self, scan: dict, assets: list[dict], findings: list[dict]) -> None:
        """자산 중요도(담당자 수정 우선)로 발견 점수, 조직 점수, 오늘 할 일을 다시 계산해 저장한다."""
        manual = self.store.manual_importance(scan["domain_id"])
        by_id = {}
        for a in assets:
            if a["asset_id"] in manual:
                a["importance"] = {"value": manual[a["asset_id"]], "source": "manual", "rule": None}
            else:
                a["importance"] = {**a["auto_importance"], "source": "auto"}
            by_id[a["asset_id"]] = a

        prev = scan.get("previous_scan_id")
        prev_ids = {f["finding_id"] for f in self.store.findings(prev)} if prev else set()
        scored: list[Scored] = []
        for f in findings:
            sit = SITUATIONS[(f["check_id"], f["situation_key"])]
            asset = by_id[f["asset_id"]]
            c = sit.c_fixed if sit.c_fixed is not None else asset["importance"]["value"]
            f.update(
                asset_alias=asset["alias"], situation=sit.text, e=sit.e, x=sit.x, d=sit.d, c=c,
                c_fixed=sit.c_fixed is not None, confidence=sit.confidence,
                status="new" if prev and f["finding_id"] not in prev_ids else "open",
            )
            if sit.info:
                f.update(raw=0.0, risk_score=0, severity="info")
            else:
                raw = risk_raw(sit.e, sit.x, sit.d, c, sit.confidence)
                f.update(raw=raw, risk_score=round_half_up(raw), severity=severity(round_half_up(raw)))
                scored.append(Scored(f["finding_id"], raw, FIX_MINUTES.get(f["check_id"], 60)))

        raws = [x.raw for x in scored]
        safety = round_half_up(100 - org_risk_raw(raws))
        scan.update(
            safety_score=safety,
            grade=grade(safety),
            org_risk_score=round_half_up(org_risk_raw(raws)),
            score_formula=org_formula(raws),
            today_tasks=[t.__dict__ for t in pick_today_tasks(scored)],
        )
        self.store.put_scan_assets(scan["scan_id"], assets)
        self.store.put_findings(scan["scan_id"], findings)
        if scan["scan_id"] in self._live:
            self._save_live(scan)
        else:
            self.store.save_scan(scan)

    def set_importance(self, domain_id: str, asset_id: str, value: Any) -> dict:
        self._domain_or_404(domain_id)
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
            raise validation("중요도는 1~5 사이의 정수여야 합니다.")
        if not self.store.set_manual_importance(domain_id, asset_id, value):
            raise not_found("자산")
        summary = {"safety_score": None, "grade": None}
        scan = self._latest_finished(domain_id)
        if scan:
            self._score(scan, self.store.scan_assets(scan["scan_id"]), self.store.findings(scan["scan_id"]))
            report = self.store.get_report(scan["scan_id"])
            if report is None or report["source"] == "template":
                self.store.put_report(scan["scan_id"], self._template_report(scan))
            summary = {"safety_score": scan["safety_score"], "grade": scan["grade"]}
        return {"asset": {"asset_id": asset_id, "importance": {"value": value, "source": "manual", "rule": None}},
                "summary": summary}

    # ================================================================ 대시보드

    def _task_rows(self, scan: dict) -> list[dict]:
        fs = {f["finding_id"]: f for f in self.store.findings(scan["scan_id"])}
        rows = []
        for rank, t in enumerate(scan.get("today_tasks", []), 1):
            f = fs.get(t["finding_id"])
            if f is None:
                continue
            rows.append({
                "rank": rank, "finding_id": f["finding_id"], "check_id": f["check_id"],
                "title": GUIDES[f["check_id"]].title if f["check_id"] in GUIDES else check_name(f["check_id"]),
                "asset_alias": f["asset_alias"], "risk_score": f["risk_score"], "severity": f["severity"],
                "fix_minutes": FIX_MINUTES.get(f["check_id"], 60),
                "safety_score_after": t["safety_after"], "grade_after": t["grade_after"],
            })
        return rows

    def summary(self, domain_id: str) -> dict:
        d = self._domain_or_404(domain_id)
        running = self._running(domain_id)
        scan = self._latest_finished(domain_id)
        out: dict[str, Any] = {
            "domain_id": domain_id, "domain": d["domain"], "latest_scan": None,
            "running_scan_id": running["scan_id"] if running else None,
            "safety_score": None, "grade": None, "org_risk_score": None, "score_formula": None,
            "counts": {s: 0 for s in SEVERITIES}, "asset_count": 0, "today_tasks": [], "alerts": [],
        }
        if scan is None:
            return out
        findings = self.store.findings(scan["scan_id"])
        assets = self.store.scan_assets(scan["scan_id"])
        for f in findings:
            out["counts"][f["severity"]] += 1
        alerts = [{"type": "new_asset", "message": f"새 하위 도메인 {a['host']}이 발견됐습니다.",
                   "asset_id": a["asset_id"], "finding_id": None} for a in assets if a.get("is_new")]
        alerts += [{"type": "new_finding",
                    "message": f"{f['asset_alias']}에서 새 문제가 발견됐습니다: {check_name(f['check_id'])}",
                    "asset_id": f["asset_id"], "finding_id": f["finding_id"]}
                   for f in sorted(findings, key=lambda f: -f["raw"]) if f["status"] == "new"]
        out.update(
            latest_scan={"scan_id": scan["scan_id"], "finished_at": scan["finished_at"], "status": scan["status"],
                         "attack": scan.get("attack")},
            safety_score=scan["safety_score"], grade=scan["grade"], org_risk_score=scan["org_risk_score"],
            score_formula=scan["score_formula"], asset_count=len(assets),
            today_tasks=self._task_rows(scan), alerts=alerts,
        )
        return out

    def assets(self, scan_id: str) -> dict:
        self._scan_or_404(scan_id)
        findings = self.store.findings(scan_id)
        items = []
        for a in self.store.scan_assets(scan_id):
            mine = [f for f in findings if f["asset_id"] == a["asset_id"]]
            sev = min((SEVERITIES.index(f["severity"]) for f in mine), default=None)
            items.append({
                "asset_id": a["asset_id"], "alias": a["alias"], "host": a["host"], "url": a["url"],
                "found_by": a["found_by"], "tags": a["tags"], "importance": a["importance"],
                "components": a["components"], "tls_version": a["tls_version"], "is_new": a["is_new"],
                "finding_count": len(mine), "max_severity": SEVERITIES[sev] if sev is not None else None,
            })
        return {"items": items}

    # ================================================================ 발견

    def _first_seen(self, domain_id: str, finding_id: str) -> str | None:
        for scan in self.store.scans_for(domain_id, FINISHED):
            if any(f["finding_id"] == finding_id for f in self.store.findings(scan["scan_id"])):
                return scan["scan_id"]
        return None

    def findings(self, scan_id: str, *, asset_id: str | None = None, severity_filter: str | None = None,
                 status: str | None = None, check_id: str | None = None) -> dict:
        scan = self._scan_or_404(scan_id)
        rows = self.store.findings(scan_id)
        statuses = {s.strip() for s in status.split(",")} if status else None
        if statuses and "resolved" in statuses and scan.get("previous_scan_id"):
            # 해결됨은 이번 점검에 없고 직전 점검에 있던 발견이다. 상태 필터로 요청할 때만 넣는다.
            now_ids = {f["finding_id"] for f in rows}
            rows += [{**f, "status": "resolved"} for f in self.store.findings(scan["previous_scan_id"])
                     if f["finding_id"] not in now_ids]
        if asset_id:
            rows = [f for f in rows if f["asset_id"] == asset_id]
        if severity_filter:
            sev = {s.strip() for s in severity_filter.split(",") if s.strip()}
            if not sev <= set(SEVERITIES):
                raise validation("severity 값이 올바르지 않습니다.")
            rows = [f for f in rows if f["severity"] in sev]
        if statuses:
            if not statuses <= {"open", "new", "resolved"}:
                raise validation("status 값이 올바르지 않습니다.")
            rows = [f for f in rows if f["status"] in statuses]
        if check_id is not None:
            try:
                cid = int(check_id)
            except ValueError:
                raise validation("check_id는 정수여야 합니다.") from None
            rows = [f for f in rows if f["check_id"] == cid]
        rows.sort(key=lambda f: (-f["raw"], f["finding_id"]))
        return {"items": [{
            "finding_id": f["finding_id"], "check_id": f["check_id"], "check_name": check_name(f["check_id"]),
            "asset_id": f["asset_id"], "asset_alias": f["asset_alias"], "situation": f["situation"],
            "risk_score": f["risk_score"], "severity": f["severity"], "confidence": f["confidence"],
            "status": f["status"], "first_seen_scan_id": self._first_seen(scan["domain_id"], f["finding_id"]),
        } for f in rows]}

    def finding_detail(self, finding_id: str) -> dict:
        f = self.store.latest_finding(finding_id)
        if f is None:
            raise not_found("발견")
        return {
            "finding_id": f["finding_id"], "scan_id": f["scan_id"], "check_id": f["check_id"],
            "check_name": check_name(f["check_id"]), "asset_id": f["asset_id"], "asset_alias": f["asset_alias"],
            "location": f["location"], "situation": f["situation"], "severity": f["severity"],
            "confidence": f["confidence"], "status": f["status"],
            "score": {
                "exposure": f["e"], "exploitability": f["x"], "data_sensitivity": f["d"],
                "asset_importance": f["c"], "asset_importance_fixed": f["c_fixed"],
                "confidence_factor": CONFIDENCE_FACTOR[f["confidence"]], "risk_score": f["risk_score"],
                "formula": None if f["severity"] == "info" else risk_formula(f["e"], f["x"], f["d"], f["c"], f["confidence"]),
            },
            "evidence": f["evidence"], "cves": f["cves"], "detected_at": f["detected_at"],
        }

    # ================================================================ 조치 가이드 (FR-07, 08, 11)

    def _template_items(self, scan: dict) -> list[dict]:
        items = []
        for row in self._task_rows(scan):
            g = GUIDES.get(row["check_id"])
            if g is None:
                continue
            items.append({
                "rank": row["rank"], "finding_ids": [row["finding_id"]], "title": g.title,
                "why_risky": g.why_risky.format(asset=row["asset_alias"]),
                "expected_damage": g.expected_damage, "fix_steps": list(g.fix_steps),
                "fix_minutes": row["fix_minutes"], "safety_score_after": row["safety_score_after"], "verified": True,
            })
        return items

    def _template_report(self, scan: dict) -> dict:
        items = self._template_items(scan)
        return {"scan_id": scan["scan_id"], "source": "template",
                "verification": {"passed": len(items), "total": len(items)},
                "generated_at": now_iso(), "items": items}

    async def _build_report(self, scan: dict, use_llm: bool) -> None:
        report = self._template_report(scan)
        if use_llm and report["items"] and self.llm.configured:
            rows = self._task_rows(scan)
            details = {r["finding_id"]: self.finding_detail(r["finding_id"]) for r in rows}
            try:
                # LLM이 멈춰도 점검이 'reporting'에 묶이지 않게 전체 시간을 자른다(항목당 최대 2회 × 60초)
                draft = await asyncio.wait_for(
                    agents.write_report(self.llm, rows, report["items"], details), timeout=REPORT_TIMEOUT_SEC)
            except Exception:
                log.exception("조치 가이드 생성 실패, 기본 가이드로 대체: %s", scan["scan_id"])
                draft = None
            if draft is not None:
                report.update(source="llm", items=draft.items,
                              verification={"passed": draft.passed, "total": draft.total})
        self.store.put_report(scan["scan_id"], report)

    def report(self, scan_id: str) -> dict:
        scan = self._finished_or_409(scan_id)
        r = self.store.get_report(scan_id)
        if r is None:  # 예전 점검 등으로 없으면 기본 가이드를 만든다
            r = self._template_report(scan)
            self.store.put_report(scan_id, r)
        return r

    async def ask(self, scan_id: str, question: Any) -> dict:
        self._finished_or_409(scan_id)
        if not isinstance(question, str) or not question.strip():
            raise validation("질문을 입력해 주세요.")
        if len(question) > 500:
            raise validation("질문은 500자 이내로 입력해 주세요.")
        findings = [self.finding_detail(f["finding_id"]) for f in self.store.findings(scan_id)]
        try:
            answer = await asyncio.wait_for(agents.answer_question(self.llm, question.strip(), findings), timeout=30)
        except Exception:
            log.exception("질의응답 실패: %s", scan_id)
            answer = None
        if answer is None:
            raise ApiError(503, "LLM_UNAVAILABLE", "지금은 AI 답변을 받을 수 없습니다. 잠시 뒤 다시 시도해 주세요.")
        return answer

    # ================================================================ 기록 (FR-09, 10, 15, 16)

    def _diff(self, scan: dict) -> tuple[list[dict], list[dict], list[dict], list[dict], dict | None]:
        prev_id = scan.get("previous_scan_id")
        prev = self.store.get_scan(prev_id) if prev_id else None
        cur_f = {f["finding_id"]: f for f in self.store.findings(scan["scan_id"])}
        cur_a = {a["asset_id"]: a for a in self.store.scan_assets(scan["scan_id"])}
        prev_f = {f["finding_id"]: f for f in self.store.findings(prev_id)} if prev else {}
        prev_a = {a["asset_id"]: a for a in self.store.scan_assets(prev_id)} if prev else {}
        resolved = [f for k, f in prev_f.items() if k not in cur_f]
        new = [f for k, f in cur_f.items() if k not in prev_f]
        new_assets = [a for k, a in cur_a.items() if prev and k not in prev_a]
        removed = [a for k, a in prev_a.items() if k not in cur_a]
        return resolved, new, new_assets, removed, prev

    def history(self, domain_id: str) -> dict:
        self._domain_or_404(domain_id)
        items = []
        for scan in self.store.scans_for(domain_id, FINISHED):
            resolved, new, *_ = self._diff(scan)
            items.append({"scan_id": scan["scan_id"], "finished_at": scan["finished_at"], "status": scan["status"],
                          "safety_score": scan["safety_score"], "grade": scan["grade"],
                          "new_count": len(new), "resolved_count": len(resolved)})
        return {"items": items}

    def changes(self, scan_id: str) -> dict:
        scan = self._finished_or_409(scan_id)
        resolved, new, new_assets, removed, prev = self._diff(scan)

        def brief(f: dict) -> dict:
            return {"finding_id": f["finding_id"], "check_id": f["check_id"], "asset_alias": f["asset_alias"],
                    "risk_score": f["risk_score"]}

        def asset_brief(a: dict) -> dict:
            return {"asset_id": a["asset_id"], "alias": a["alias"], "host": a["host"]}

        order = lambda f: (-f["raw"], f["finding_id"])  # noqa: E731
        return {
            "scan_id": scan_id,
            "previous_scan_id": prev["scan_id"] if prev else None,
            "safety_score": {"before": prev["safety_score"] if prev else None, "after": scan["safety_score"]},
            "grade": {"before": prev["grade"] if prev else None, "after": scan["grade"]},
            "resolved_findings": [brief(f) for f in sorted(resolved, key=order)],
            "new_findings": [brief(f) for f in sorted(new, key=order)],
            "new_assets": [asset_brief(a) for a in new_assets],
            "removed_assets": [asset_brief(a) for a in removed],
        }

    def audit(self, scan_id: str, actor: str | None = None, rejected: str | None = None) -> dict:
        self._scan_or_404(scan_id)
        if actor is not None and actor not in ("system", "attack", "defense"):
            raise validation("actor는 system, attack, defense 중 하나입니다.")
        if rejected is not None and rejected not in ("true", "false"):
            raise validation("rejected는 true 또는 false입니다.")
        rows = self.store.audit(scan_id)
        if actor:
            rows = [r for r in rows if r["actor"] == actor]
        if rejected == "true":
            rows = [r for r in rows if r["rejected"]]
        elif rejected == "false":
            rows = [r for r in rows if not r["rejected"]]
        return {"items": rows}

    # ================================================================ 점검 항목

    @staticmethod
    def checks() -> dict:
        return {"items": [c.to_api() for c in CHECKS.values()]}
