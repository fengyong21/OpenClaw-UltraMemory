#!/usr/bin/env python3
"""
Claw Memory V4 - 子智能体并行执行
借鉴 Hermes Agent：多步骤任务拆成子 Agent 并行跑，结果汇总。

触发条件：
- 单次任务涉及 >= 3 个独立子步骤
- 子步骤之间无强依赖关系

用法：
    python3 child_agent.py plan "帮我部署 GEO 项目到 Sealos"
    python3 child_agent.py execute '[{"task": "构建镜像", "context": {...}}, ...]'
"""
import json
import subprocess
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

# ────────────────── 路径配置 ──────────────────
SCRIPTS_DIR = Path(__file__).parent
HOT_WINDOW = SCRIPTS_DIR / "hot_window.py"
AUTO_SKILL = SCRIPTS_DIR / "auto_skill.py"

# ────────────────── 主任务规划 ──────────────────
SUB_AGENT_TEMPLATES = {
    "deploy": [
        {"step": "docker_build", "label": "构建 Docker 镜像", "depends": []},
        {"step": "docker_push", "label": "推送镜像到仓库", "depends": ["docker_build"]},
        {"step": "k8s_apply", "label": "应用 Kubernetes 配置", "depends": ["docker_push"]},
        {"step": "verify", "label": "验证部署状态", "depends": ["k8s_apply"]},
    ],
    "code_review": [
        {"step": "lint", "label": "运行代码检查", "depends": []},
        {"step": "test", "label": "运行测试套件", "depends": []},
        {"step": "security", "label": "安全扫描", "depends": []},
        {"step": "report", "label": "生成审查报告", "depends": ["lint", "test", "security"]},
    ],
    "research": [
        {"step": "web_search", "label": "全网搜索相关信息", "depends": []},
        {"step": "doc_fetch", "label": "抓取官方文档", "depends": []},
        {"step": "summarize", "label": "汇总并提炼结论", "depends": ["web_search", "doc_fetch"]},
    ],
}


def plan_task(main_goal: str) -> dict:
    """
    分析主任务，自动拆分为可并行的子任务。
    简化版：基于关键词匹配模板。
    """
    goal_lower = main_goal.lower()

    # 匹配模板
    for template_name, steps in SUB_AGENT_TEMPLATES.items():
        if template_name in goal_lower:
            return {
                "template": template_name,
                "steps": steps,
                "parallel_groups": _build_parallel_groups(steps),
            }

    # 无模板匹配：默认 3 步拆分
    return {
        "template": "generic",
        "steps": [
            {"step": "step1", "label": "步骤一：理解任务", "depends": []},
            {"step": "step2", "label": "步骤二：执行核心操作", "depends": ["step1"]},
            {"step": "step3", "label": "步骤三：验证结果", "depends": ["step2"]},
        ],
        "parallel_groups": [["step1"], ["step2"], ["step3"]],
    }


def _build_parallel_groups(steps: list) -> list:
    """根据依赖关系构建可并行执行的批次"""
    executed = set()
    groups = []

    while len(executed) < len(steps):
        # 找所有依赖都已执行的步骤
        ready = [
            s["step"] for s in steps
            if s["step"] not in executed
            and all(d in executed for d in s["depends"])
        ]
        if not ready:
            break
        groups.append(ready)
        executed.update(ready)

    return groups


# ────────────────── 子 Agent 执行 ──────────────────
def run_sub_agent(step_id: str, label: str, context: dict) -> dict:
    """
    执行单个子任务（子进程隔离）。
    这里简化为调用 hot_window.py write 记录执行状态。
    实际使用时替换为真实 Agent 调用。
    """
    try:
        result = subprocess.run(
            [
                sys.executable, str(HOT_WINDOW), "write",
                f"[{step_id}] {label}"
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return {
            "step": step_id,
            "status": "success" if result.returncode == 0 else "failed",
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except subprocess.TimeoutExpired:
        return {"step": step_id, "status": "timeout", "stderr": "执行超时"}
    except Exception as e:
        return {"step": step_id, "status": "error", "stderr": str(e)}


def execute_steps(plan: dict, context: dict) -> list:
    """
    按批次并行执行子任务。
    """
    results = []
    for group in plan["parallel_groups"]:
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {}
            for step_id in group:
                step_info = next(s for s in plan["steps"] if s["step"] == step_id)
                future = executor.submit(run_sub_agent, step_id, step_info["label"], context)
                futures[future] = step_id

            for future in as_completed(futures):
                step_id = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    results.append({"step": step_id, "status": "error", "stderr": str(e)})

    return results


# ────────────────── 主流程 ──────────────────
def run(main_goal: str, context: dict | None = None) -> dict:
    """主入口：规划 → 并行执行 → 汇总结果"""
    context = context or {}

    # 1. 规划
    plan = plan_task(main_goal)

    # 2. 写入锚点
    try:
        subprocess.run(
            [sys.executable, str(AUTO_SKILL), "check", "1", main_goal],
            capture_output=True,
        )
    except Exception:
        pass

    # 3. 执行
    results = execute_steps(plan, context)

    # 4. 汇总
    success_count = sum(1 for r in results if r["status"] == "success")
    failed = [r for r in results if r["status"] != "success"]

    summary = {
        "total": len(results),
        "success": success_count,
        "failed": len(failed),
        "results": results,
    }

    if failed:
        summary["failed_details"] = failed

    return summary


# ────────────────── CLI 入口 ──────────────────
if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    if cmd == "plan":
        goal = sys.argv[2] if len(sys.argv) > 2 else "帮我完成某项任务"
        plan = plan_task(goal)
        print(f"📋 任务规划（模板: {plan['template']}）:")
        print(f"   并行批次: {len(plan['parallel_groups'])}")
        for i, group in enumerate(plan["parallel_groups"], 1):
            print(f"   Batch {i}: {group}")

    elif cmd == "execute":
        tasks_json = sys.argv[2] if len(sys.argv) > 2 else "[]"
        try:
            tasks = json.loads(tasks_json)
        except json.JSONDecodeError:
            print("❌ JSON 解析失败")
            sys.exit(1)
        plan = {"parallel_groups": [[t["step"] for t in tasks]], "steps": tasks}
        results = execute_steps(plan, {})
        for r in results:
            status_icon = "✅" if r["status"] == "success" else "❌"
            print(f"{status_icon} {r['step']}: {r['status']}")

    elif cmd == "run":
        goal = sys.argv[2] if len(sys.argv) > 2 else "帮我部署 GEO 项目"
        result = run(goal)
        print(f"\n📊 执行完成：{result['success']}/{result['total']} 成功")
        if result.get("failed"):
            print("❌ 失败步骤:")
            for f in result["failed"]:
                print(f"   - {f['step']}: {f.get('stderr', f['status'])}")

    else:
        print("用法:")
        print("  child_agent.py plan '任务描述'")
        print("  child_agent.py run '任务描述'")
        print("  child_agent.py execute '[{\"step\":\"s1\",\"label\":\"l1\"}]'")
