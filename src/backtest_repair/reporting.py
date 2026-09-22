"""Portable HTML evidence reports; no CDN, external fonts, or hidden API calls."""

from __future__ import annotations
from html import escape
import json
from pathlib import Path
from .contracts import load_json

STYLE = """:root{font-family:system-ui,'Microsoft YaHei',sans-serif;color:#163040;background:#f3f6f8}
body{max-width:1200px;margin:36px auto;padding:0 24px 70px}h1{font-size:30px;letter-spacing:-.6px}
h2{font-size:20px;margin-top:36px}p{line-height:1.7}.muted{color:#637888}.cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
.card{background:white;border:1px solid #d8e3e8;border-radius:12px;padding:18px;min-width:0}
@media(max-width:650px){.cards{grid-template-columns:repeat(2,minmax(0,1fr))}.value{font-size:22px!important}}
.value{font-size:28px;font-weight:650;display:block;margin-top:8px}table{border-collapse:collapse;width:100%;background:white}
th,td{text-align:left;border-bottom:1px solid #e0e9ed;padding:10px 12px;font-size:13px;vertical-align:top}
th{background:#e8f0f4}a{color:#126689}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#fff;padding:18px;border:1px solid #d8e3e8;border-radius:8px;font-size:12px}
details{margin:12px 0}summary{cursor:pointer;padding:10px;background:#e8f0f4;border-radius:7px}
.pass,.accepted{color:#137449}.fail,.rejected{color:#ab3140}select,input{padding:9px;border:1px solid #bccbd3;border-radius:6px;margin:8px 10px 16px 0}
svg{width:100%;height:auto;background:white;border:1px solid #d8e3e8;border-radius:10px}svg text{font-size:11px;fill:#607380}
.scroll{overflow-x:auto}code{font-family:ui-monospace,Consolas,monospace}footer{margin-top:36px;font-size:12px;color:#607380}
"""


def workflow_report(path, target=None):
    """Render current content-addressed episodes or suite indexes, without credentials."""
    path=Path(path)
    if path.is_dir():
        if (path/'episode.json').exists(): items=[load_json(path/'episode.json')]
        else: items=[load_json(p) for p in sorted(path.glob('*/*/episode.json'))]
    else:
        value=load_json(path)
        items=value if isinstance(value,list) else [value]
    episodes=[item.get('episode',item) for item in items]
    rows=[]
    for episode in episodes:
        evidence=episode.get('visible_evidence',episode.get('report',{}))
        rows.append([escape(str(episode.get('case',''))),escape(str(episode.get('status',''))),str(episode.get('accepted',False)),str(episode.get('known_tokens',0)),*[escape(str(evidence.get(k,{}).get('status','n/a'))) for k in ('financial','invariants','causality','preservation')]])
    content='<h1>Native strategy audit and repair</h1><p>Host-measured acceptance. Finite historical tests do not establish live profitability or universal correctness. Inconclusive outcomes remain separate from passes.</p>'
    content+=table(['Strategy','Outcome','Accepted','Known tokens','Financial','Coverage / rules','Causality','Preservation'],rows)
    for episode in episodes:
        public={k:v for k,v in episode.items() if k not in {'execution_identity','artifact_directory'}}
        content+='<details><summary>'+escape(str(episode.get('case','Evidence')))+'</summary><pre>'+escape(json.dumps(public,ensure_ascii=False,indent=2))+'</pre></details>'
    target=Path(target) if target else (path/'report.html' if path.is_dir() else path.with_suffix('.html'))
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(document('Backtest Repair evidence',content),encoding='utf-8')
    return target


def document(title, content, script=""):
    return (
        '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'
        + escape(title)
        + "</title><style>"
        + STYLE
        + "</style><body>"
        + content
        + "<footer>Backtest Repair · 所有图表和筛选在本地运行。实验结论以冻结配置和完整运行记录为准。</footer><script>"
        + script
        + "</script></body></html>"
    )


def table(headers, rows):
    return (
        '<div class="scroll"><table><thead><tr>'
        + "".join("<th>" + escape(str(h)) + "</th>" for h in headers)
        + "</tr></thead><tbody>"
        + "".join(
            "<tr>" + "".join("<td>" + str(c) + "</td>" for c in row) + "</tr>"
            for row in rows
        )
        + "</tbody></table></div>"
    )


def pretty(value):
    return "<pre>" + escape(json.dumps(value, ensure_ascii=False, indent=2)) + "</pre>"


def line_plot(events):
    rows = [e for e in events if e["kind"] == "account" and e.get("equity") is not None]
    if len(rows) < 2:
        return '<p class="muted">本次运行没有足够的原生账户观测。</p>'
    values = [r["equity"] for r in rows]
    low, high = min(values), max(values)
    span = max(high - low, 1)
    points = [
        (55 + i * 1020 / (len(rows) - 1), 190 - (v - low) / span * 145)
        for i, v in enumerate(values)
    ]
    path = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
    dots = "".join(
        f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3" fill="#167994"><title>{escape(r["session"])} · equity {r["equity"]:.6f} · position {r.get("position")}</title></circle>'
        for (x, y), r in zip(points, rows)
    )
    return f'<svg viewBox="0 0 1120 230" role="img" aria-label="原生回测账户权益，可悬停查看数值"><text x="10" y="35">{high:.2f}</text><text x="10" y="200">{low:.2f}</text><polyline points="{path}" fill="none" stroke="#167994" stroke-width="2"/>{dots}<text x="55" y="220">{escape(rows[0]["session"])}</text><text x="990" y="220">{escape(rows[-1]["session"])}</text></svg>'


def episode_report(folder, target=None):
    folder = Path(folder).resolve()
    episode = load_json(folder / "episode.json")
    evaluation = (
        load_json(folder / "evaluation.json")
        if (folder / "evaluation.json").exists()
        else None
    )
    submission = episode.get("submission") or {}
    accepted = bool(
        evaluation
        and evaluation.get("accepted")
        and episode.get("budget_compliant", False)
    )
    label = (
        "隐藏验收通过"
        if accepted
        else "隐藏验收未通过"
        if evaluation
        else "尚无有效隐藏验收"
    )
    if (
        evaluation
        and evaluation.get("accepted")
        and not episode.get("budget_compliant", False)
    ):
        label = "验收通过 · 预算未通过"
    if accepted and evaluation.get("validity") == "development_unisolated":
        label = "开发验收通过（未隔离）"
    usage = episode["usage"]
    cards = [
        ("结果", label),
        ("方法", episode["method"]),
        ("模型", episode["model"]),
        ("Token", f"{usage['input_tokens'] + usage['output_tokens']:,}"),
        ("原生执行", episode["native_runs"]),
        ("耗时", f"{episode['elapsed_seconds']:.1f} s"),
    ]
    body = (
        '<p class="muted">反例驱动回测验证与修复 · 单次运行证据</p><h1>'
        + escape(folder.name)
        + '</h1><div class="cards">'
        + "".join(
            '<div class="card">'
            + escape(k)
            + '<span class="value">'
            + escape(str(v))
            + "</span></div>"
            for k, v in cards
        )
        + "</div>"
    )
    body += (
        "<p>状态：<strong>"
        + escape(episode["status"])
        + "</strong>。隔离方式："
        + escape(episode["isolation"])
        + "。诊断："
        + escape(submission.get("diagnosis", "未提交"))
        + "。</p>"
    )
    if episode.get("error"):
        body += "<pre>" + escape(episode["error"]) + "</pre>"
    body += (
        "<h2>诊断与提交</h2><p>"
        + escape(submission.get("explanation", "本次运行没有提交诊断。"))
        + "</p>"
    )
    body += pretty(
        {
            k: submission.get(k)
            for k in ("fault_categories", "locations", "evidence", "hash")
        }
    )
    events = []
    if (folder / "episode.jsonl").exists():
        events = [
            json.loads(line)
            for line in (folder / "episode.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
    rows = []
    for event in events:
        if event["type"] == "model":
            try:
                reply = json.loads(
                    event["text"].strip().removeprefix("```json").removesuffix("```")
                )
                hypotheses = reply.get("hypotheses")
            except (ValueError, TypeError):
                hypotheses = None
            if hypotheses:
                rows.append(
                    [
                        str(event.get("step", 0) + 1),
                        "假设",
                        escape(json.dumps(hypotheses, ensure_ascii=False)),
                    ]
                )
        elif event["type"] in {"tool", "fixed_diagnostics"}:
            result = event.get("result", {})
            rows.append(
                [
                    str(event.get("step", 0) + 1),
                    escape(event.get("tool", "fixed_diagnostics")),
                    "<details><summary>参数与观测</summary>"
                    + pretty({"args": event.get("args", {}), "result": result})
                    + "</details>",
                ]
            )
    body += "<h2>实验与证据链</h2>" + table(["决策轮次", "动作", "内容"], rows)
    runs = sorted(
        (folder / "native_runs").glob("*/result.json"), key=lambda p: p.stat().st_mtime
    )
    if runs:
        chosen = [("最初运行", runs[0])] + (
            [("最后一次可见运行", runs[-1])] if len(runs) > 1 else []
        )
        for title, path in chosen:
            run = load_json(path)
            body += (
                "<h2>"
                + title
                + '</h2><p class="muted">'
                + escape(run["run_id"])
                + " · "
                + escape(run["status"])
                + "</p>"
                + line_plot(run.get("events", []))
            )
            timeline = [
                e
                for e in run.get("events", [])
                if e["kind"] in {"order", "stop_status", "fill", "data_access"}
            ]
            body += (
                "<details><summary>信号后订单、成交和数据访问时序</summary>"
                + table(
                    ["序号", "交易日", "阶段", "事件", "观测"],
                    [
                        [
                            e["seq"],
                            escape(e["session"]),
                            escape(e["phase"]),
                            escape(e["kind"]),
                            escape(
                                json.dumps(
                                    {
                                        k: v
                                        for k, v in e.items()
                                        if k
                                        not in {
                                            "seq",
                                            "timestamp",
                                            "bar_start",
                                            "bar_end",
                                            "session",
                                            "phase",
                                            "kind",
                                            "provenance",
                                            "source",
                                            "instrument",
                                        }
                                    },
                                    ensure_ascii=False,
                                )
                            ),
                        ]
                        for e in timeline
                    ],
                )
                + "</details>"
            )
    body += (
        "<h2>补丁</h2><pre>"
        + escape(
            (folder / "patches.diff").read_text(encoding="utf-8")
            if (folder / "patches.diff").exists()
            else "没有代码修改。"
        )
        + "</pre>"
    )
    body += "<h2>独立验收与预算</h2>" + pretty(
        {
            "evaluation": evaluation,
            "limits": episode["limits"],
            "budget_compliant": episode.get("budget_compliant"),
            "original_hash": episode["original_hash"],
            "final_hash": episode["final_hash"],
            "billed_cost": episode.get("billed_cost"),
        }
    )
    body += '<p class="muted">权益曲线用于检查账本，不表示投资收益预测。未观测到的行为不会由本报告补充推断；中转服务未返回实际账单费用。</p>'
    target = Path(target) if target else folder / "report.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(document(folder.name, body), encoding="utf-8")
    return target


def dashboard(aggregate_path, target=None):
    aggregate_path = Path(aggregate_path).resolve()
    data = load_json(aggregate_path)
    body = '<p class="muted">反例驱动回测验证与修复 · 对照实验</p><h1>结构化策略修复评测</h1><p>三个方法使用相同模型、工具、任务和预算。B1 自由诊断，B2 固定检查流程，B3 主动选择验证实验。失败和未提交运行均计入分母。</p>'
    body += "<h2>完整修复率</h2>" + table(
        [
            "方法",
            "故障运行",
            "完整修复",
            "修复率",
            "95% 家族聚类区间",
            "正确策略误报",
            "总 Token",
        ],
        [
            [
                m,
                r["bug_tasks_runs"],
                r["repaired"],
                f"{r['repair_rate']:.1%}" if r["repair_rate"] is not None else "—",
                escape(str(r["family_cluster_95_interval"])),
                r["false_positives"],
                f"{r['total_tokens']:,}",
            ]
            for m, r in data["methods"].items()
        ],
    )
    body += "<h2>配对比较</h2>" + pretty(data["paired"])
    body += '<h2>全部运行</h2><input id="query" aria-label="筛选运行" placeholder="输入框架、方法、状态或任务名筛选"><span id="count"></span>'
    rows = []
    for r in data["rows"]:
        name = f"{r['task']}__{r['method']}__{r['seed']}"
        folder = aggregate_path.parent / name
        task_label = escape(r["task"])
        if (folder / "episode.json").exists():
            episode_report(folder)
            task_label = (
                '<a href="'
                + escape(name + "/report.html", quote=True)
                + '">'
                + task_label
                + "</a>"
            )
        outcome = "通过" if r["accepted"] else "未通过"
        rows.append(
            [
                task_label,
                escape(r["engine"]),
                r["method"],
                r["seed"],
                "正确策略" if r["clean"] else "故障策略",
                escape(r["status"]),
                outcome,
                f"{r['tokens']:,}",
                r["native_runs"],
                f"{r['seconds']:.1f}",
            ]
        )
    body += (
        '<div id="episodes">'
        + table(
            [
                "任务",
                "框架",
                "方法",
                "种子",
                "类型",
                "状态",
                "隐藏验收",
                "Token",
                "回测",
                "秒",
            ],
            rows,
        )
        + "</div>"
    )
    body += "<h2>适用范围和可重复性</h2>" + pretty(
        {"formal": data.get("formal"), "limitations": data.get("limitations", [])}
    )
    script = "const q=document.querySelector('#query'),rows=[...document.querySelectorAll('#episodes tbody tr')];function filter(){let n=0;for(const r of rows){const ok=r.innerText.toLowerCase().includes(q.value.toLowerCase());r.hidden=!ok;n+=ok}document.querySelector('#count').textContent=n+' / '+rows.length+' 次运行'}q.addEventListener('input',filter);filter();"
    target = Path(target) if target else aggregate_path.parent / "report.html"
    target.write_text(document("结构化策略修复评测", body, script), encoding="utf-8")
    return target
